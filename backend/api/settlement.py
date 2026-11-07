"""交割结算与归档（PRD 4.9/T17-T19）：质检录入、结算生成与双向确认、付款登记、完成归档。

核心规则：
- 质检拒收（REJECT）不允许生成正常结算单，走退货说明文本。
- 结算金额只能由服务端 Decimal 计算：（单价+质量调价元/吨）×结算数量 − 扣款，quantize(0.01)。
- 双方确认后结算冻结，后续调整需新增结算单并备注。
- 归档三条件：全部运单已签收 + 结算已完成 + 无未关闭预警。
"""
import io
import json
import zipfile
from decimal import Decimal, ROUND_HALF_UP

from flask import g, send_file

from ..alerts import create_alert
from ..common import (ApiError, decimal_field, doc_no, get_params, json_payload,
                      ok, op_log, page_args, page_data, parse_date, require_fields,
                      send_msg)
from ..db import execute, q1, qall
from ..security import ROLE_STEEL, ROLE_SUPPLIER, auth_required, roles_required
from ..state_machine import add_node, transition
from . import bp

TWO = Decimal('0.01')


def _order_of(oid):
    row = q1(g.conn, "SELECT * FROM biz_order WHERE id=%s AND is_deleted=0", (oid,))
    if not row:
        raise ApiError(40401, '订单不存在')
    return row


def _order_visible(order):
    if not g.ctx.is_plat and (not g.ctx.company or
                              g.ctx.company['id'] not in (order['buyer_id'], order['supplier_id'])):
        raise ApiError(40301, '无权限访问该订单')


def _settlement_view(sid):
    row = q1(g.conn, """
        SELECT s.*, o.order_no AS "orderNo", o.buyer_id AS "buyerId", o.supplier_id AS "supplierId",
               v.variety_name AS "varietyName"
        FROM biz_settlement s
        JOIN biz_order o ON o.id = s.order_id
        LEFT JOIN base_variety v ON v.id = o.variety_id
        WHERE s.id=%s AND s.is_deleted=0
    """, (sid,))
    if not row:
        raise ApiError(40401, '结算单不存在')
    return row


# ---------------- 质检录入（FR-09-02） ----------------

@bp.post('/orders/<int:oid>/quality-check')
@roles_required(ROLE_STEEL)
def create_quality_check(oid):
    order = _order_of(oid)
    _order_visible(order)
    if order['status'] != 'PERFORMING':
        raise ApiError(40901, '订单当前状态为 %s，不能录入质检' % order['status'])
    p = get_params()
    require_fields(p, 'arrivedQty', 'conclusion')
    if p['conclusion'] not in ('ACCEPT', 'REJECT'):
        raise ApiError(40001, 'conclusion 须为 ACCEPT 或 REJECT')
    arrived = decimal_field(p, 'arrivedQty')
    check_no = doc_no(g.conn, 'ZJ')  # TODO(PRD待确认): 质检单前缀未在 PRD 3.3 定义，最小实现 ZJ
    cid = execute(g.conn, """
        INSERT INTO biz_quality_check (check_no, order_id, arrived_qty, indicators,
                                       conclusion, check_desc, file_url, created_by)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id
    """, (check_no, oid, arrived, p.get('indicators'), p['conclusion'],
          p.get('checkDesc'), p.get('fileId'), g.ctx.user['id']), returning_id=True)
    # 数量偏差超溢短装比例 → 生成 QTY_DIFF 预警（需方、供方）
    qty = order['quantity']
    rate = order['more_less_rate'] or Decimal('5.00')
    if abs(arrived - qty) / qty * 100 > rate:
        create_alert(
            g.conn, 'QTY_DIFF', 'ORDER', oid, [order['buyer_id'], order['supplier_id']],
            content='到货数量 %s 与订单数量 %s 偏差超过允差 %s%%，请双方确认处理意见'
                    % (arrived, qty, rate),
        )
    add_node(g.conn, g.ctx, 'ORDER', oid, 'QUALITY_CHECKED',
             remark='质检 %s，结论 %s' % (check_no, p['conclusion']))
    op_log(g.conn, g.ctx, 'biz_quality_check', cid, 'CREATE', None,
           {'checkNo': check_no, 'arrivedQty': str(arrived), 'conclusion': p['conclusion']})
    send_msg(g.conn, order['supplier_id'], '到货质检完成', '订单 %s 质检结论：%s' % (order['order_no'], p['conclusion']),
             'ORDER', oid)
    return ok({'id': cid, 'checkNo': check_no})


@bp.get('/orders/<int:oid>/quality-checks')
@auth_required
def list_quality_checks(oid):
    _order_visible(_order_of(oid))
    rows = qall(g.conn, """
        SELECT id, check_no AS "checkNo", order_id AS "orderId", arrived_qty AS "arrivedQty",
               indicators, conclusion, check_desc AS "checkDesc", file_url AS "fileUrl",
               created_at AS "createdAt"
        FROM biz_quality_check WHERE order_id=%s AND is_deleted=0 ORDER BY id DESC
    """, (oid,))
    return ok({'list': json_payload(rows)})


# ---------------- 结算生成（FR-09-03） ----------------

@bp.post('/orders/<int:oid>/settlements')
@roles_required(ROLE_STEEL)
def create_settlement(oid):
    order = _order_of(oid)
    _order_visible(order)
    if order['status'] != 'PERFORMING':
        raise ApiError(40901, '订单当前状态为 %s，不能生成结算单' % order['status'])
    last_check = q1(g.conn, """
        SELECT conclusion, arrived_qty FROM biz_quality_check
        WHERE order_id=%s AND is_deleted=0 ORDER BY id DESC LIMIT 1
    """, (oid,))
    if last_check and last_check['conclusion'] == 'REJECT':
        raise ApiError(40901, '质检结论为拒收，不允许生成正常结算单')
    p = get_params()
    # 结算数量默认实收（最近一次质检到货量），可调但须 >0
    default_qty = (last_check['arrived_qty'] if last_check and last_check['conclusion'] == 'ACCEPT'
                   else order['quantity'])
    settle_qty = decimal_field(p, 'settleQty', required=False) or default_qty
    adjust = decimal_field(p, 'adjustAmount', positive=False, required=False) or Decimal('0')
    deduct = decimal_field(p, 'deductAmount', positive=False, required=False) or Decimal('0')
    if deduct < 0:
        raise ApiError(40001, 'deductAmount 不能为负')
    # 金额只能由系统计算（PRD 4.9）：（单价+调价）×数量 − 扣款
    total = ((order['unit_price'] + adjust) * settle_qty - deduct).quantize(TWO, rounding=ROUND_HALF_UP)
    settle_no = doc_no(g.conn, 'JS')
    sid = execute(g.conn, """
        INSERT INTO biz_settlement (settle_no, order_id, settle_qty, unit_price, adjust_amount,
                                    deduct_amount, total_amount, settle_desc, created_by)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id
    """, (settle_no, oid, settle_qty, order['unit_price'], adjust, deduct, total,
          p.get('settleDesc'), g.ctx.user['id']), returning_id=True)
    add_node(g.conn, g.ctx, 'SETTLEMENT', sid, 'SETTLE_CREATED',
             remark='结算金额 %s' % total)
    op_log(g.conn, g.ctx, 'biz_settlement', sid, 'CREATE', None,
           {'settleNo': settle_no, 'totalAmount': str(total)})
    send_msg(g.conn, order['supplier_id'], '结算单待确认',
             '订单 %s 已生成结算单 %s，金额 %s 元，请确认' % (order['order_no'], settle_no, total),
             'SETTLEMENT', sid)
    return ok(_settlement_view(sid))


# ---------------- 双向确认（FR-09-04） ----------------

@bp.put('/settlements/<int:sid>/confirm')
@auth_required
def confirm_settlement(sid):
    s = _settlement_view(sid)
    is_buyer = g.ctx.company and g.ctx.company['id'] == s['buyerId']
    is_supplier = g.ctx.company and g.ctx.company['id'] == s['supplierId']
    if not g.ctx.is_plat and not (is_buyer or is_supplier):
        raise ApiError(40301, '无权限确认该结算单')
    if s['status'] == 'PENDING_CONFIRM_SUPPLIER':
        if not (is_supplier or g.ctx.is_plat):
            raise ApiError(40901, '当前等待供应商确认')
        transition(g.conn, g.ctx, 'biz_settlement', '结算单', 'biz_settlement', sid,
                   'PENDING_CONFIRM_BUYER')
        execute(g.conn, "UPDATE biz_settlement SET supplier_confirm_at=now() WHERE id=%s", (sid,))
        add_node(g.conn, g.ctx, 'SETTLEMENT', sid, 'SETTLE_SUPPLIER_CONFIRMED')
        send_msg(g.conn, s['buyerId'], '结算单待确认', '结算单 %s 供应商已确认，请需方确认' % s['settle_no'],
                 'SETTLEMENT', sid)
    elif s['status'] == 'PENDING_CONFIRM_BUYER':
        if not (is_buyer or g.ctx.is_plat):
            raise ApiError(40901, '当前等待需方确认')
        transition(g.conn, g.ctx, 'biz_settlement', '结算单', 'biz_settlement', sid, 'CONFIRMED')
        execute(g.conn, "UPDATE biz_settlement SET buyer_confirm_at=now() WHERE id=%s", (sid,))
        add_node(g.conn, g.ctx, 'SETTLEMENT', sid, 'SETTLE_BUYER_CONFIRMED')
        send_msg(g.conn, s['supplierId'], '结算单已确认', '结算单 %s 双方确认完成，已冻结' % s['settle_no'],
                 'SETTLEMENT', sid)
    else:
        raise ApiError(40901, '结算单当前状态为 %s，禁止确认' % s['status'])
    return ok(_settlement_view(sid))


# ---------------- 付款登记（FR-09-05） ----------------

@bp.post('/settlements/<int:sid>/payments')
@roles_required(ROLE_STEEL)
def register_payment(sid):
    s = _settlement_view(sid)
    if not g.ctx.is_plat and (not g.ctx.company or g.ctx.company['id'] != s['buyerId']):
        raise ApiError(40301, '仅需方可登记付款')
    if s['status'] not in ('CONFIRMED', 'COMPLETED'):
        raise ApiError(40901, '结算单当前状态为 %s，须双方确认后方可登记付款' % s['status'])
    p = get_params()
    require_fields(p, 'amount', 'payDate')
    amount = decimal_field(p, 'amount')
    pay_date = parse_date(p, 'payDate')
    payment_no = doc_no(g.conn, 'FK')  # TODO(PRD待确认): 付款单前缀未在 PRD 3.3 定义，最小实现 FK
    pid = execute(g.conn, """
        INSERT INTO biz_payment (payment_no, settlement_id, payer_id, amount, pay_date,
                                 pay_desc, file_url, created_by)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id
    """, (payment_no, sid, s['buyerId'], amount, pay_date, p.get('payDesc'),
          p.get('fileId'), g.ctx.user['id']), returning_id=True)
    if s['status'] == 'CONFIRMED':
        transition(g.conn, g.ctx, 'biz_settlement', '结算单', 'biz_settlement', sid, 'COMPLETED')
    add_node(g.conn, g.ctx, 'SETTLEMENT', sid, 'SETTLE_PAID',
             remark='付款 %s，金额 %s' % (payment_no, amount))
    op_log(g.conn, g.ctx, 'biz_payment', pid, 'CREATE', None,
           {'paymentNo': payment_no, 'amount': str(amount)})
    send_msg(g.conn, s['supplierId'], '付款已登记',
             '结算单 %s 已登记付款 %s，金额 %s 元' % (s['settle_no'], payment_no, amount),
             'SETTLEMENT', sid)
    return ok({'id': pid, 'paymentNo': payment_no})


# ---------------- 完成归档（FR-09-06） ----------------

@bp.post('/orders/<int:oid>/archive')
@roles_required(ROLE_STEEL)
def archive_order(oid):
    order = _order_of(oid)
    _order_visible(order)
    if order['status'] != 'PERFORMING':
        raise ApiError(40901, '订单当前状态为 %s，不能归档' % order['status'])
    # 条件一：全部运单已签收
    w = q1(g.conn, """
        SELECT count(*) AS total, count(*) FILTER (WHERE status='SIGNED') AS signed
        FROM biz_waybill WHERE order_id=%s AND is_deleted=0
    """, (oid,))
    if w['total'] != w['signed']:
        raise ApiError(40901, '存在未签收运单，不能归档')
    # 条件二：结算已完成（付款已登记）
    s = q1(g.conn, """
        SELECT count(*) AS c FROM biz_settlement
        WHERE order_id=%s AND status='COMPLETED' AND is_deleted=0
    """, (oid,))
    if not s['c']:
        raise ApiError(40901, '结算未完成（须双方确认并登记付款），不能归档')
    # 条件三：无未关闭预警（订单与其运单）
    open_alert = q1(g.conn, """
        SELECT count(*) AS c FROM biz_alert
        WHERE is_deleted=0 AND status IN ('PENDING','PROCESSING')
          AND ((biz_type='ORDER' AND biz_id=%s)
               OR (biz_type='WAYBILL' AND biz_id IN (SELECT id FROM biz_waybill WHERE order_id=%s)))
    """, (oid, oid))
    if open_alert['c']:
        raise ApiError(40901, '存在未关闭预警，不能归档')
    transition(g.conn, g.ctx, 'biz_order', '订单', 'biz_order', oid, 'COMPLETED',
               node_biz_type='ORDER', node_code='ORDER_ARCHIVED')
    send_msg(g.conn, order['supplier_id'], '订单已归档', '订单 %s 已完成归档' % order['order_no'],
             'ORDER', oid)
    return ok({'id': oid, 'status': 'COMPLETED'})


@bp.get('/orders/<int:oid>/archive/export')
@auth_required
def export_archive(oid):
    """订单档案导出：单据 JSON 清单 + 关联盖章件/凭证打包 zip。"""
    order = _order_of(oid)
    _order_visible(order)
    manifest = {
        'order': json_payload(order),
        'contracts': json_payload(qall(g.conn, "SELECT * FROM biz_contract WHERE order_id=%s AND is_deleted=0 ORDER BY version", (oid,))),
        'logisticsPlans': json_payload(qall(g.conn, "SELECT * FROM biz_logistics_plan WHERE order_id=%s AND is_deleted=0", (oid,))),
        'waybills': json_payload(qall(g.conn, "SELECT * FROM biz_waybill WHERE order_id=%s AND is_deleted=0 ORDER BY segment_no", (oid,))),
        'qualityChecks': json_payload(qall(g.conn, "SELECT * FROM biz_quality_check WHERE order_id=%s AND is_deleted=0", (oid,))),
        'settlements': json_payload(qall(g.conn, "SELECT * FROM biz_settlement WHERE order_id=%s AND is_deleted=0", (oid,))),
        'payments': json_payload(qall(g.conn, """
            SELECT p.* FROM biz_payment p JOIN biz_settlement s ON s.id=p.settlement_id
            WHERE s.order_id=%s AND p.is_deleted=0
        """, (oid,))),
        'trackNodes': json_payload(qall(g.conn, """
            SELECT * FROM biz_track_node WHERE (biz_type='ORDER' AND biz_id=%s)
               OR (biz_type='WAYBILL' AND biz_id IN (SELECT id FROM biz_waybill WHERE order_id=%s))
               OR (biz_type='SETTLEMENT' AND biz_id IN (SELECT id FROM biz_settlement WHERE order_id=%s))
            ORDER BY occur_time, id
        """, (oid, oid, oid))),
        'alerts': json_payload(qall(g.conn, """
            SELECT * FROM biz_alert WHERE (biz_type='ORDER' AND biz_id=%s)
               OR (biz_type='WAYBILL' AND biz_id IN (SELECT id FROM biz_waybill WHERE order_id=%s))
            ORDER BY id
        """, (oid, oid))),
    }
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('manifest.json', json.dumps(manifest, ensure_ascii=False, indent=2, default=str))
        # 关联附件（fileId → sys_file 实际文件）
        file_ids = []
        for c in manifest['contracts'] or []:
            if c.get('file_url'):
                file_ids.append(c['file_url'])
        for t in ('qualityChecks', 'payments'):
            for r in manifest[t] or []:
                if r.get('file_url'):
                    file_ids.append(r['file_url'])
        for fid in dict.fromkeys(file_ids):  # 去重保序
            f = q1(g.conn, "SELECT file_name, path FROM sys_file WHERE file_id=%s AND is_deleted=0", (fid,))
            if f:
                import os
                full = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                                    'uploads', f['path'])
                if os.path.isfile(full):
                    z.write(full, 'files/%s' % f['file_name'])
    buf.seek(0)
    return send_file(buf, mimetype='application/zip', as_attachment=True,
                     download_name='archive-%s.zip' % order['order_no'])


# ---------------- 结算查询 ----------------

@bp.get('/settlements')
@auth_required
def list_settlements():
    p = get_params()
    page, size = page_args(p)
    where = ['s.is_deleted=0']
    args = []
    if not g.ctx.is_plat:
        if not g.ctx.company:
            return ok(page_data([], 0, page, size))
        where.append('(o.buyer_id=%s OR o.supplier_id=%s)')
        args += [g.ctx.company['id'], g.ctx.company['id']]
    if p.get('status'):
        where.append('s.status=%s')
        args.append(p['status'])
    if p.get('orderId'):
        where.append('s.order_id=%s')
        args.append(p['orderId'])
    w = ' AND '.join(where)
    total = q1(g.conn, "SELECT count(*) AS c FROM biz_settlement s JOIN biz_order o ON o.id=s.order_id WHERE " + w, args)['c']
    rows = qall(g.conn, """
        SELECT s.id, s.settle_no AS "settleNo", s.order_id AS "orderId", o.order_no AS "orderNo",
               s.settle_qty AS "settleQty", s.unit_price AS "unitPrice",
               s.adjust_amount AS "adjustAmount", s.deduct_amount AS "deductAmount",
               s.total_amount AS "totalAmount", s.status,
               s.supplier_confirm_at AS "supplierConfirmAt", s.buyer_confirm_at AS "buyerConfirmAt",
               s.created_at AS "createdAt"
        FROM biz_settlement s JOIN biz_order o ON o.id=s.order_id
        WHERE """ + w + " ORDER BY s.id DESC LIMIT %s OFFSET %s",
        args + [size, (page - 1) * size])
    return ok(page_data(rows, total, page, size))


@bp.get('/settlements/<int:sid>')
@auth_required
def settlement_detail(sid):
    s = _settlement_view(sid)
    _order_visible(_order_of(s['order_id']))
    payments = qall(g.conn, """
        SELECT id, payment_no AS "paymentNo", settlement_id AS "settlementId", amount,
               pay_date AS "payDate", pay_desc AS "payDesc", file_url AS "fileUrl",
               created_at AS "createdAt"
        FROM biz_payment WHERE settlement_id=%s AND is_deleted=0 ORDER BY id
    """, (sid,))
    data = json_payload(s)
    data['payments'] = json_payload(payments)
    return ok(data)
