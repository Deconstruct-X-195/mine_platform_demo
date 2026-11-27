"""订单（PRD 4.5/T12）：定标生成订单、供应商 48h 确认、超时失效回退、列表与详情。

定标锁定：品种、品位、数量+溢短装、成交单价、交货方式与地点、交货期、结算方式、
质检扣罚标准；一期不支持一单拆多家。
"""
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation

from flask import g, request

from ..common import (ApiError, doc_no, get_params, json_payload, ok, op_log,
                      page_args, page_data, parse_date, require_fields, send_msg)
from ..db import execute, qall, q1
from ..security import ROLE_STEEL, ROLE_SUPPLIER, auth_required, roles_required
from ..state_machine import transition
from . import bp


@bp.post('/inquiries/<int:iid>/award')
@roles_required(ROLE_STEEL)
def award(iid):
    p = get_params()
    require_fields(p, 'quoteId')
    inq = q1(g.conn, "SELECT * FROM biz_inquiry WHERE id=%s AND is_deleted=0", (iid,))
    if not inq or inq['buyer_id'] != g.ctx.company['id']:
        raise ApiError(40401, '询价单不存在')
    if inq['status'] not in ('CLOSED', 'BARGAINING', 'AWARDED'):
        raise ApiError(40901, '询价单状态为 %s，不可定标（需先揭示报价）' % inq['status'])
    if inq['status'] == 'AWARDED':
        # 重新定标：仅当存在已失效订单（前次 48h 超时）时允许
        lost = qall(g.conn, """
            SELECT id FROM biz_order WHERE inquiry_id=%s AND status='CANCELLED' AND is_deleted=0
            """, (iid,))
        if not lost:
            raise ApiError(40901, '询价单已定标')

    quote = q1(g.conn, "SELECT * FROM biz_quote WHERE id=%s AND is_deleted=0", (p['quoteId'],))
    if not quote or quote['inquiry_id'] != iid:
        raise ApiError(40401, '报价不存在')
    if quote['status'] not in ('REVEALED', 'BARGAINING', 'WIN'):
        raise ApiError(40901, '报价状态为 %s，不可定标' % quote['status'])

    # 若有议价：必须存在 ACCEPTED 轮次，且以接受轮次的价格/数量定标
    price, qty = quote['price'], quote['quantity']
    delivery_date, settle_type = quote['delivery_date'], inq['settle_type']
    accepted = q1(g.conn, """
        SELECT * FROM biz_bargain WHERE quote_id=%s AND status='ACCEPTED' AND is_deleted=0
        ORDER BY round_no DESC LIMIT 1
        """, (p['quoteId'],))
    if accepted:
        price = accepted['price'] or price
        qty = accepted['quantity'] or qty
        delivery_date = accepted['delivery_date'] or delivery_date
        settle_type = accepted['settle_type'] or settle_type
    if qty > quote['quantity']:
        raise ApiError(40001, '定标数量不能超过报价可供量 %.3f' % quote['quantity'])

    # 询价重新开放场景：原 WIN 报价回退
    if inq['status'] == 'AWARDED':
        for q in qall(g.conn, "SELECT id, status FROM biz_quote WHERE inquiry_id=%s AND status='WIN' AND is_deleted=0", (iid,)):
            if q['id'] != quote['id']:
                transition(g.conn, g.ctx, 'biz_quote', '报价', 'biz_quote', q['id'], 'LOSE')
    if inq['status'] == 'AWARDED':
        transition(g.conn, g.ctx, 'biz_inquiry', '询价单', 'biz_inquiry', iid, 'CLOSED')

    item = q1(g.conn, "SELECT * FROM biz_demand_item WHERE id=%s", (inq['demand_item_id'],))
    more_less = item['more_less_rate'] if item else 5
    amount = (price * qty).quantize(Decimal('0.01'))
    oid = execute(g.conn, """
        INSERT INTO biz_order (order_no, inquiry_id, quote_id, demand_id, buyer_id, supplier_id,
            variety_id, grade, quantity, more_less_rate, unit_price, amount, price_basis,
            delivery_type, delivery_place, delivery_date, settle_type, quality_terms,
            confirm_deadline, status, created_by, updated_by)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'PENDING_CONFIRM',%s,%s)
        RETURNING id
        """, (doc_no(g.conn, 'DD'), iid, quote['id'], inq['demand_id'], inq['buyer_id'],
              quote['supplier_id'], inq['variety_id'], inq['grade'], qty, more_less,
              price, amount, 'WET', inq['delivery_type'], inq['delivery_place'],
              delivery_date, settle_type, quote['quality_commit'],
              datetime.now() + timedelta(hours=48), g.ctx.user['id'], g.ctx.user['id']),
           returning_id=True)
    transition(g.conn, g.ctx, 'biz_quote', '报价', 'biz_quote', quote['id'], 'WIN',
               node_biz_type='ORDER', node_code='AWARDED', node_biz_id=oid)
    # 其余报价置 LOSE
    for q in qall(g.conn, """
            SELECT id, status FROM biz_quote
            WHERE inquiry_id=%s AND id<>%s AND status IN ('REVEALED','BARGAINING') AND is_deleted=0
            """, (iid, quote['id'])):
        transition(g.conn, g.ctx, 'biz_quote', '报价', 'biz_quote', q['id'], 'LOSE')
    # 议价冻结（未决轮次置 EXPIRED）
    execute(g.conn, "UPDATE biz_bargain SET status='EXPIRED', updated_at=now() WHERE inquiry_id=%s AND status='PENDING'", (iid,))
    transition(g.conn, g.ctx, 'biz_inquiry', '询价单', 'biz_inquiry', iid, 'AWARDED',
               node_biz_type='ORDER', node_code='ORDER_CREATED', node_biz_id=oid)
    # 成交回填明细：成交吨数计入 deal_qty，并释放该询价占用的可询锁定量
    if item:
        execute(g.conn, "UPDATE biz_demand_item SET deal_qty = deal_qty + %s, updated_at=now() WHERE id=%s",
                (qty, item['id']))
        execute(g.conn, """
            UPDATE biz_demand_item SET inquired_qty = GREATEST(inquired_qty - %s, 0), updated_at=now() WHERE id=%s
            """, (inq['quantity'], item['id']))
    # 通知供应商
    send_msg(g.conn, quote['supplier_id'], '订单待确认',
             '询价单 %s 已定标，生成订单，请在 48 小时内确认（%s 前）。' %
             (inq['inquiry_no'], (datetime.now() + timedelta(hours=48)).strftime('%Y-%m-%d %H:%M:%S')),
             'ORDER', oid, need_action=True)
    op_log(g.conn, g.ctx, 'biz_order', oid, 'AWARD', None,
           {'quoteId': quote['id'], 'price': str(price), 'quantity': str(qty)})
    return ok({'orderId': oid, 'confirmDeadline': (datetime.now() + timedelta(hours=48)).strftime('%Y-%m-%d %H:%M:%S')})


@bp.post('/orders/<int:oid>/confirm-buyer')
@roles_required(ROLE_STEEL)
def confirm_order_buyer(oid):
    """钢厂确认中标订单：记录本钢厂成员行确认时间（前端按钮转「已确认」），不改订单状态。"""
    row = _own(oid, ROLE_STEEL)
    if row['status'] != 'PENDING_CONFIRM':
        raise ApiError(40901, '订单状态为 %s，不可确认' % row['status'])
    member = q1(g.conn, """
        SELECT id, buyer_confirm_at FROM biz_order_member
        WHERE order_id=%s AND company_id=%s AND is_deleted=0 LIMIT 1
        """, (oid, g.ctx.company['id']))
    if not member:
        raise ApiError(40401, '贵司不在该订单的参与钢厂中')
    if member['buyer_confirm_at']:
        return ok({'id': oid, 'buyerConfirmAt': member['buyer_confirm_at'].strftime('%Y-%m-%d %H:%M:%S')})
    execute(g.conn, "UPDATE biz_order_member SET buyer_confirm_at=now() WHERE id=%s", (member['id'],))
    op_log(g.conn, g.ctx, 'biz_order', oid, 'BUYER CONFIRM', None, None)
    return ok({'id': oid, 'buyerConfirmAt': datetime.now().strftime('%Y-%m-%d %H:%M:%S')})


@bp.put('/orders/<int:oid>/confirm')
@roles_required(ROLE_SUPPLIER)
def confirm_order(oid):
    row = _own(oid, ROLE_SUPPLIER)
    if row['status'] != 'PENDING_CONFIRM':
        raise ApiError(40901, '订单状态为 %s，不可确认' % row['status'])
    if datetime.now() > row['confirm_deadline']:
        raise ApiError(40901, '已超过确认截止时间（48h）')
    # 集采聚合订单（buyer_id 为空）：供应商确认后进入提货计划收集；普通订单进入合同环节
    aggregated = row['buyer_id'] is None
    to = 'PENDING_PICKUP' if aggregated else 'PENDING_CONTRACT'
    transition(g.conn, g.ctx, 'biz_order', '订单', 'biz_order', oid, to,
               node_biz_type='ORDER', node_code='ORDER_CONFIRMED')
    if aggregated:
        members = qall(g.conn, """
            SELECT company_id, quantity FROM biz_order_member
            WHERE order_id=%s AND is_deleted=0
            """, (oid,))
        for m in members:
            send_msg(g.conn, m['company_id'], '订单已确认，请提交提货计划',
                     '订单 %s 供应商已确认，贵司份额 %s 湿吨，请在「订单」页提交提货计划（开始提货日期、日提货吨数）。'
                     % (row['order_no'], format(m['quantity'], '.3f')), 'ORDER', oid,
                     need_action=True)
    else:
        send_msg(g.conn, row['buyer_id'], '订单已确认', '订单 %s 供应商已确认，请生成并签署合同。' % row['order_no'],
                 'ORDER', oid, need_action=True)
    return ok({'id': oid, 'status': to})


def _own(oid, role=None):
    row = q1(g.conn, "SELECT * FROM biz_order WHERE id=%s AND is_deleted=0", (oid,))
    if not row:
        raise ApiError(40401, '订单不存在')
    cid = g.ctx.company['id'] if g.ctx.company else None
    allowed = g.ctx.is_plat or cid in (row['buyer_id'], row['supplier_id'])
    # 集采聚合订单（buyer_id 为空）：参与钢厂成员亦可访问
    if not allowed and cid and row['buyer_id'] is None:
        allowed = q1(g.conn, """
            SELECT id FROM biz_order_member WHERE order_id=%s AND company_id=%s AND is_deleted=0
            """, (oid, cid)) is not None
    if not allowed:
        raise ApiError(40301, '无权限访问该订单')
    return row


@bp.get('/orders')
@auth_required
def list_orders():
    params = request.args.to_dict()
    page, size = page_args(params)
    cid = g.ctx.company['id'] if g.ctx.company else -1
    where, args = 'WHERE o.is_deleted=0', []
    if not g.ctx.is_plat:
        # 需方 / 供方 / 集采聚合订单的参与钢厂成员均可见
        where += (' AND (o.buyer_id=%s OR o.supplier_id=%s OR EXISTS ('
                  'SELECT 1 FROM biz_order_member m WHERE m.order_id=o.id'
                  ' AND m.company_id=%s AND m.is_deleted=0))')
        args += [cid, cid, cid]
    if params.get('status'):
        where += ' AND o.status=%s'
        args.append(params['status'])
    total = q1(g.conn, 'SELECT count(*) AS c FROM biz_order o ' + where, args)['c']
    rows = qall(g.conn, """
        SELECT o.*, v.variety_name AS "varietyName",
               b.company_name AS "buyerName", s.company_name AS "supplierName",
               o.supplier_confirm_at AS "supplierConfirmAt",
               o.demand_confirm_at AS "demandConfirmAt",
               o.supplier_finish_confirm_at AS "supplierFinishConfirmAt",
               o.buyer_finish_confirm_at AS "buyerFinishConfirmAt",
               (SELECT count(*) FROM biz_waybill w
                 WHERE w.order_id=o.id AND w.is_deleted=0) AS "waybillTotal",
               (SELECT count(*) FROM biz_waybill w
                 WHERE w.order_id=o.id AND w.is_deleted=0 AND w.status='SIGNED') AS "waybillSigned",
               (SELECT m.quantity FROM biz_order_member m
                 WHERE m.order_id=o.id AND m.company_id=%%s AND m.is_deleted=0 LIMIT 1) AS "myQty",
               (SELECT m.pickup_status FROM biz_order_member m
                 WHERE m.order_id=o.id AND m.company_id=%%s AND m.is_deleted=0 LIMIT 1) AS "myPickupStatus",
               (SELECT m.confirm_at FROM biz_order_member m
                 WHERE m.order_id=o.id AND m.company_id=%%s AND m.is_deleted=0 LIMIT 1) AS "myConfirmAt",
               (SELECT m.buyer_confirm_at FROM biz_order_member m
                 WHERE m.order_id=o.id AND m.company_id=%%s AND m.is_deleted=0 LIMIT 1) AS "myBuyerConfirmAt",
               (SELECT m.finish_confirm_at FROM biz_order_member m
                 WHERE m.order_id=o.id AND m.company_id=%%s AND m.is_deleted=0 LIMIT 1) AS "myFinishConfirmAt",
               CASE WHEN o.supplier_id=%%s THEN EXISTS (
                        SELECT 1 FROM biz_logistics_publish lp WHERE lp.order_id=o.id
                          AND lp.target='SUPPLIER' AND lp.trace_json IS NOT NULL)
                    ELSE EXISTS (
                        SELECT 1 FROM biz_logistics_publish lp WHERE lp.order_id=o.id
                          AND lp.target='MILL' AND lp.trace_json IS NOT NULL) END AS "logiPublished",
               (SELECT q.freight_price FROM biz_quote q
                 WHERE q.id=o.quote_id AND q.is_deleted=0 LIMIT 1) AS "freight_price",
               (SELECT q.tax_type FROM biz_quote q
                 WHERE q.id=o.quote_id AND q.is_deleted=0 LIMIT 1) AS "tax_type",
               (SELECT q.price_sign FROM biz_quote q
                 WHERE q.id=o.quote_id AND q.is_deleted=0 LIMIT 1) AS "priceSign",
               (SELECT q.price_float FROM biz_quote q
                 WHERE q.id=o.quote_id AND q.is_deleted=0 LIMIT 1) AS "priceFloat",
               (SELECT string_agg(c2.company_name, '、') FROM biz_order_member m2
                 JOIN ent_company c2 ON c2.id=m2.company_id
                 WHERE m2.order_id=o.id AND m2.is_deleted=0) AS "buyerNames"
        FROM biz_order o
        JOIN base_variety v ON v.id=o.variety_id
        LEFT JOIN ent_company b ON b.id=o.buyer_id
        LEFT JOIN ent_company s ON s.id=o.supplier_id
        %s ORDER BY o.id DESC LIMIT %%s OFFSET %%s
        """ % where, [cid, cid, cid, cid, cid, cid] + args + [size, (page - 1) * size])
    return ok(page_data(rows, total, page, size))


@bp.get('/orders/<int:oid>')
@auth_required
def order_detail(oid):
    row = _own(oid)
    data = json_payload(dict(row))
    data['varietyName'] = (q1(g.conn, "SELECT variety_name AS n FROM base_variety WHERE id=%s", (row['variety_id'],)) or {}).get('n')
    data['buyerName'] = (q1(g.conn, "SELECT company_name AS n FROM ent_company WHERE id=%s", (row['buyer_id'],)) or {}).get('n')
    data['supplierName'] = (q1(g.conn, "SELECT company_name AS n FROM ent_company WHERE id=%s", (row['supplier_id'],)) or {}).get('n')
    # 成交报价运费/含税标志 + 申报的上下浮方向与金额 + 参与本单集采的全部钢厂（聚合订单需方为平台）
    qrow = q1(g.conn, "SELECT freight_price, tax_type, price_sign, price_float FROM biz_quote WHERE id=%s AND is_deleted=0",
              (row['quote_id'],)) if row['quote_id'] else None
    data['freight_price'] = qrow['freight_price'] if qrow else None
    data['tax_type'] = qrow['tax_type'] if qrow else None
    data['priceSign'] = qrow['price_sign'] if qrow else None
    data['priceFloat'] = str(qrow['price_float']) if qrow and qrow['price_float'] is not None else None
    data['buyerNames'] = (q1(g.conn, """
        SELECT string_agg(c.company_name, '、') AS n FROM biz_order_member m
        JOIN ent_company c ON c.id=m.company_id
        WHERE m.order_id=%s AND m.is_deleted=0""", (oid,)) or {}).get('n')
    # 本厂提货计划（集采聚合订单按成员行存储；普通订单无成员行返回 None）
    data['myPickupPlan'] = json_payload(q1(g.conn, """
        SELECT pickup_start_date AS "startDate", daily_qty AS "dailyQty",
               pickup_remark AS "remark", pickup_status AS "status", submitted_at AS "submittedAt"
        FROM biz_order_member
        WHERE order_id=%s AND company_id=%s AND is_deleted=0
        """, (oid, g.ctx.company['id']))) if g.ctx.company else None
    # 本厂份额数量（集采聚合订单成员行数量；普通订单为 None）
    data['myQty'] = (q1(g.conn, """
        SELECT quantity FROM biz_order_member
        WHERE order_id=%s AND company_id=%s AND is_deleted=0 LIMIT 1
        """, (oid, g.ctx.company['id'])) or {}).get('quantity') if g.ctx.company else None
    contracts = qall(g.conn, """
        SELECT id, contract_no AS "contractNo", version, status, file_url AS "fileUrl",
               file_hash AS "fileHash", buyer_sign_at AS "buyerSignAt", supplier_sign_at AS "supplierSignAt",
               void_reason AS "voidReason", created_at AS "createdAt"
        FROM biz_contract WHERE order_id=%s AND is_deleted=0 ORDER BY version DESC
        """, (oid,))
    data['contracts'] = json_payload(contracts)
    return ok(data)


@bp.get('/orders/<int:oid>/fulfillment')
@auth_required
def order_fulfillment(oid):
    """钢厂端履约跟踪：全链信息一次取数（询价/议价反馈/订单/提货计划/物流/交付验收/结算）。

    钢厂对归集询价的认可反馈存于 biz_agg_inquiry_feedback；提货计划取本厂 biz_order_member 成员行
    （普通订单无成员行，pickup 为空，前端展示「不适用」）。
    """
    row = _own(oid)
    cid = g.ctx.company['id'] if g.ctx.company else -1
    data = json_payload(dict(row))
    data['varietyName'] = (q1(g.conn, "SELECT variety_name AS n FROM base_variety WHERE id=%s", (row['variety_id'],)) or {}).get('n')
    data['buyerName'] = (q1(g.conn, "SELECT company_name AS n FROM ent_company WHERE id=%s", (row['buyer_id'],)) or {}).get('n') if row['buyer_id'] else None
    data['supplierName'] = (q1(g.conn, "SELECT company_name AS n FROM ent_company WHERE id=%s", (row['supplier_id'],)) or {}).get('n') if row['supplier_id'] else None
    # 询价信息（成交来源）：钢厂端履约跟踪展示 品类/吨数/中标报价总价（WIN 报价 单价×数量）
    inq = q1(g.conn, """
        SELECT i.inquiry_no, i.status, i.quantity, i.deadline, i.created_at,
               v.variety_name AS "varietyName", wq.price AS "winPrice", wq.quantity AS "winQty",
               wq.price_sign AS "priceSign", wq.price_float AS "priceFloat"
        FROM biz_inquiry i
        JOIN base_variety v ON v.id = i.variety_id
        LEFT JOIN LATERAL (
            SELECT q.price, q.quantity, q.price_sign, q.price_float FROM biz_quote q
            WHERE q.inquiry_id = i.id AND q.status = 'WIN' AND q.is_deleted = 0
            ORDER BY q.price ASC, q.id ASC LIMIT 1) wq ON TRUE
        WHERE i.id = %s AND i.is_deleted = 0""", (row['inquiry_id'],)) if row['inquiry_id'] else None
    data['inquiry'] = json_payload(inq)
    # 本厂对归集询价的评审反馈（认可/不认可）
    data['feedback'] = json_payload(q1(g.conn, """
        SELECT decision, reason, created_at FROM biz_agg_inquiry_feedback
        WHERE inquiry_id = %s AND company_id = %s AND is_deleted = 0""", (row['inquiry_id'], cid))) if row['inquiry_id'] else None
    # 提货计划（本厂成员行）
    data['pickup'] = json_payload(q1(g.conn, """
        SELECT pickup_start_date, daily_qty, pickup_remark, pickup_status, submitted_at
        FROM biz_order_member WHERE order_id = %s AND company_id = %s AND is_deleted = 0""", (oid, cid)))
    # 物流方案
    data['plan'] = json_payload(q1(g.conn, """
        SELECT plan_no, org_mode, created_at FROM biz_logistics_plan
        WHERE order_id = %s AND is_deleted = 0""", (oid,)))
    # 运单（物流信息）：含起运/到达轨迹要素（钢厂端履约跟踪运单行展示物流运输轨迹）
    data['waybills'] = json_payload(qall(g.conn, """
        SELECT id, waybill_no, transport_mode, segment_no, plan_qty, actual_qty, status, created_at,
               depart_place, arrive_place, actual_depart_at, actual_arrive_at
        FROM biz_waybill WHERE order_id = %s AND is_deleted = 0 ORDER BY id""", (oid,)))
    # 交付验收：质检记录（签收情况由运单状态聚合）
    data['qualityChecks'] = json_payload(qall(g.conn, """
        SELECT check_no, arrived_qty, conclusion, created_at FROM biz_quality_check
        WHERE order_id = %s AND is_deleted = 0 ORDER BY id DESC""", (oid,)))
    # 结算
    data['settlement'] = json_payload(q1(g.conn, """
        SELECT settle_no, settle_qty, unit_price, adjust_amount, status, created_at
        FROM biz_settlement WHERE order_id = %s AND is_deleted = 0 ORDER BY id DESC""", (oid,)))
    return ok(data)


@bp.post('/orders/<int:oid>/pickup-plan')
@auth_required
def submit_pickup_plan(oid):
    """钢厂提交提货计划（集采聚合订单）：写入本厂成员行。

    全部成员提交后，订单由 PENDING_PICKUP 推进到 PENDING_TRANSPORT（待制定运输方案）；
    重复提交允许覆盖，但订单已离开收集阶段时拒绝。
    """
    row = q1(g.conn, "SELECT * FROM biz_order WHERE id=%s AND is_deleted=0", (oid,))
    if not row:
        raise ApiError(40401, '订单不存在')
    cid = g.ctx.company['id'] if g.ctx.company else None
    member = q1(g.conn, """
        SELECT * FROM biz_order_member WHERE order_id=%s AND company_id=%s AND is_deleted=0
        """, (oid, cid))
    if not member:
        raise ApiError(40301, '当前企业不是该订单的参与钢厂')
    if row['status'] != 'PENDING_PICKUP':
        raise ApiError(40901, '订单状态为 %s，已停止收集提货计划' % row['status'])
    p = get_params()
    start = parse_date(p, 'startDate')
    try:
        daily = Decimal(str(p.get('dailyQty')))
    except (InvalidOperation, TypeError, ValueError):
        raise ApiError(40001, '日提货吨数必须为数字')
    if daily <= 0:
        raise ApiError(40001, '日提货吨数必须大于 0')
    remark = (p.get('remark') or '').strip()
    if len(remark) > 200:
        raise ApiError(40001, '备注不能超过 200 字')
    execute(g.conn, """
        UPDATE biz_order_member SET pickup_start_date=%s, daily_qty=%s, pickup_remark=%s,
               pickup_status='SUBMITTED', submitted_at=now()
        WHERE id=%s
        """, (start, daily, remark or None, member['id']))
    pending = q1(g.conn, """
        SELECT count(*) AS c FROM biz_order_member
        WHERE order_id=%s AND is_deleted=0 AND pickup_status<>'SUBMITTED'
        """, (oid,))['c']
    status = row['status']
    if pending == 0:
        transition(g.conn, g.ctx, 'biz_order', '订单', 'biz_order', oid, 'PENDING_TRANSPORT')
        status = 'PENDING_TRANSPORT'
    send_msg(g.conn, None, '钢厂已提交提货计划',
             '订单 %s：%s 已提交提货计划（%s 起，日提货 %s 湿吨）。'
             % (row['order_no'], g.ctx.company['company_name'],
                start.strftime('%Y-%m-%d'), format(daily, 'f')), 'ORDER', oid)
    op_log(g.conn, g.ctx, 'biz_order', oid, 'PICKUP_PLAN', None,
           {'startDate': str(start), 'dailyQty': str(daily), 'remark': remark})
    return ok({'orderId': oid, 'pickupStatus': 'SUBMITTED', 'orderStatus': status,
               'pendingMills': pending})


@bp.get('/buyer/overview')
@roles_required(ROLE_STEEL)
def buyer_overview():
    """钢厂端总览：KPI 面板 + 采购全流程各阶段计数 + 待办事项（结构同供应商端）。"""
    cid = g.ctx.company['id']
    # 归属条件：传统订单（需方）或集采聚合订单的参与钢厂成员
    own = ('(o.buyer_id=%s OR EXISTS (SELECT 1 FROM biz_order_member m'
           ' WHERE m.order_id=o.id AND m.company_id=%s AND m.is_deleted=0))')
    oa = [cid, cid]

    def count(sql, args):
        return q1(g.conn, sql, args)['c']

    in_transit_sql = ("SELECT count(*) AS c FROM biz_waybill w JOIN biz_order o ON o.id=w.order_id"
                      " WHERE w.is_deleted=0 AND w.status='IN_TRANSIT' AND " + own)
    kpi = {
        'orderTotal': count('SELECT count(*) AS c FROM biz_order o WHERE o.is_deleted=0 AND ' + own, oa),
        'pendingInquiry': count(
            "SELECT count(*) AS c FROM biz_demand d WHERE d.company_id=%s"
            " AND d.status='SUBMITTED' AND d.is_deleted=0", (cid,)),
        'inTransit': count(in_transit_sql, oa),
        'pendingPay': count(
            "SELECT count(*) AS c FROM biz_settlement st JOIN biz_order o ON o.id=st.order_id"
            " WHERE st.is_deleted=0 AND st.status='CONFIRMED' AND " + own, oa),
    }

    # 全流程 8 阶段计数（hash 为可跳转菜单，付款结算板块已下线故无跳转）
    flow = [
        {'label': '需求确认', 'hash': '#/demand', 'count': count(
            "SELECT count(*) AS c FROM biz_demand d WHERE d.company_id=%s"
            " AND d.status='SUBMITTED' AND d.is_deleted=0", (cid,))},
        {'label': '采购询价', 'hash': '#/inquiry', 'count': count(
            "SELECT count(*) AS c FROM biz_inquiry i WHERE i.buyer_id=%s"
            " AND i.status IN ('SENT','QUOTING') AND i.is_deleted=0", (cid,))},
        {'label': '报价接收', 'hash': '#/inquiry', 'count': count(
            "SELECT count(*) AS c FROM biz_quote q JOIN biz_inquiry i ON i.id=q.inquiry_id"
            " WHERE i.buyer_id=%s AND q.status='SUBMITTED' AND q.is_deleted=0", (cid,))},
        {'label': '评审决策', 'hash': '#/bargain', 'count': count(
            "SELECT count(*) AS c FROM biz_inquiry i WHERE i.buyer_id=%s"
            " AND i.status IN ('CLOSED','BARGAINING') AND i.is_deleted=0", (cid,))},
        {'label': '采购订单', 'hash': '#/order', 'count': count(
            "SELECT count(*) AS c FROM biz_order o WHERE o.is_deleted=0"
            " AND o.status NOT IN ('CANCELLED','COMPLETED') AND " + own, oa)},
        {'label': '货物运输', 'hash': '#/logistics', 'count': kpi['inTransit']},
        {'label': '到货验收', 'hash': '#/track', 'count': count(
            "SELECT count(*) AS c FROM biz_waybill w JOIN biz_order o ON o.id=w.order_id"
            " WHERE w.is_deleted=0 AND w.status='ARRIVED' AND " + own, oa)},
        {'label': '付款结算', 'hash': '', 'count': count(
            "SELECT count(*) AS c FROM biz_settlement st JOIN biz_order o ON o.id=st.order_id"
            " WHERE st.is_deleted=0 AND st.status IN ('PENDING_CONFIRM_SUPPLIER',"
            "'PENDING_CONFIRM_BUYER','CONFIRMED') AND " + own, oa)},
    ]

    # 待办事项（与供应商端 todos 结构一致，与小铃铛任务页签同口径）：
    # 采购计划待提交/重提 · 询价待评审/议价中 · 订单待确认 · 合同待签署 · 结算单待确认 · 到货待签收
    todos = []
    for r in qall(g.conn, """
            SELECT d.demand_no, d.status, d.updated_at FROM biz_demand d
            WHERE d.company_id=%s AND d.is_deleted=0 AND d.status IN ('DRAFT','WITHDRAWN')
            ORDER BY d.updated_at DESC LIMIT 20""", (cid,)):
        todos.append({'kind': 'DEMAND',
                      'main': '需求 %s 待%s' % (r['demand_no'],
                                               '提交' if r['status'] == 'DRAFT' else '重提（已撤回）'),
                      'time': r['updated_at']})
    # 询价待办口径与询价列表一致：本钢厂询价 + 归集成员的平台询价（buyer_id 为空）
    own_inq = """i.is_deleted=0 AND (i.buyer_id=%s OR (i.agg_id IS NOT NULL AND EXISTS (
        SELECT 1 FROM biz_aggregated_order_item m
        JOIN biz_demand d ON d.id=m.demand_id
        WHERE m.agg_id=i.agg_id AND m.is_deleted=0 AND d.is_deleted=0 AND d.company_id=%s)))"""
    for r in qall(g.conn, """
            SELECT i.inquiry_no, i.updated_at FROM biz_inquiry i
            WHERE """ + own_inq + """ AND i.status='CLOSED'
            ORDER BY i.updated_at DESC LIMIT 20""", (cid, cid)):
        todos.append({'kind': 'REVIEW', 'main': '询价单 %s 已揭示待评审' % r['inquiry_no'],
                      'time': r['updated_at']})
    for r in qall(g.conn, """
            SELECT i.inquiry_no, i.updated_at FROM biz_inquiry i
            WHERE """ + own_inq + """ AND i.status='BARGAINING'
            ORDER BY i.updated_at DESC LIMIT 20""", (cid, cid)):
        todos.append({'kind': 'BARGAIN', 'main': '询价单 %s 议价中待处理' % r['inquiry_no'],
                      'time': r['updated_at']})
    # 订单待确认：需方或集采成员，且本钢厂尚未确认（成员行 buyer_confirm_at 为空）
    for r in qall(g.conn, """
            SELECT o.order_no, o.updated_at FROM biz_order o
            WHERE o.is_deleted=0 AND o.status='PENDING_CONFIRM' AND """ + own + """
              AND NOT EXISTS (SELECT 1 FROM biz_order_member m2
                WHERE m2.order_id=o.id AND m2.company_id=%s AND m2.is_deleted=0
                  AND m2.buyer_confirm_at IS NOT NULL)
            ORDER BY o.updated_at DESC LIMIT 20""", oa + [cid]):
        todos.append({'kind': 'CONFIRM', 'main': '订单 %s 待确认' % r['order_no'],
                      'time': r['updated_at']})
    for r in qall(g.conn, """
            SELECT c.contract_no, c.updated_at FROM biz_contract c
            JOIN biz_order o ON o.id=c.order_id
            WHERE c.is_deleted=0 AND c.status='PENDING_BUYER' AND """ + own + """
            ORDER BY c.updated_at DESC LIMIT 20""", oa):
        todos.append({'kind': 'CONTRACT', 'main': '合同 %s 待签署（需方）' % r['contract_no'],
                      'time': r['updated_at']})
    for r in qall(g.conn, """
            SELECT s.settle_no, s.updated_at FROM biz_settlement s
            JOIN biz_order o ON o.id=s.order_id
            WHERE s.is_deleted=0 AND s.status='PENDING_CONFIRM_BUYER' AND """ + own + """
            ORDER BY s.updated_at DESC LIMIT 20""", oa):
        todos.append({'kind': 'SETTLE', 'main': '结算单 %s 待确认' % r['settle_no'],
                      'time': r['updated_at']})
    for r in qall(g.conn, """
            SELECT w.waybill_no, w.updated_at FROM biz_waybill w JOIN biz_order o ON o.id=w.order_id
            WHERE w.is_deleted=0 AND w.status='ARRIVED' AND """ + own + """
            ORDER BY w.updated_at DESC LIMIT 20""", oa):
        todos.append({'kind': 'ARRIVED', 'main': '运单 %s 已到货待签收' % r['waybill_no'],
                      'time': r['updated_at']})
    return ok({'kpi': kpi, 'flow': flow, 'todos': todos})


@bp.get('/supplier/overview')
@roles_required(ROLE_SUPPLIER)
def supplier_overview():
    """供应商端总览：KPI 面板（订单/交易额/待报价/运输中/已完成）+ 待办事项 + 近期动态。"""
    cid = g.ctx.company['id']

    def count(sql, args):
        return q1(g.conn, sql, args)['c']

    # 待报价：受邀的平台询价、本人未报价、仍处报价期
    pending_quote_sql = ("SELECT count(*) AS c FROM biz_inquiry i WHERE i.is_deleted=0"
                         " AND i.source='PLATFORM' AND i.status IN ('SENT','QUOTING')"
                         " AND EXISTS (SELECT 1 FROM biz_inquiry_invite inv WHERE inv.inquiry_id=i.id"
                         " AND inv.supplier_id=%s AND inv.is_deleted=0)"
                         " AND NOT EXISTS (SELECT 1 FROM biz_quote q WHERE q.inquiry_id=i.id"
                         " AND q.supplier_id=%s AND q.is_deleted=0)")
    kpi = {
        'orderTotal': count('SELECT count(*) AS c FROM biz_order o WHERE o.is_deleted=0 AND o.supplier_id=%s', (cid,)),
        # 总吨数：已完成订单的总吨数（湿吨）
        'totalQty': str(q1(g.conn, 'SELECT COALESCE(SUM(o.quantity),0) AS s FROM biz_order o'
                           " WHERE o.is_deleted=0 AND o.supplier_id=%s AND o.status='COMPLETED'", (cid,))['s']),
        'pendingQuote': count(pending_quote_sql, (cid, cid)),
        'inTransit': count("SELECT count(*) AS c FROM biz_waybill w JOIN biz_order o ON o.id=w.order_id"
                           " WHERE w.is_deleted=0 AND w.status='IN_TRANSIT' AND o.supplier_id=%s", (cid,)),
        'completed': count("SELECT count(*) AS c FROM biz_order o WHERE o.is_deleted=0"
                           " AND o.supplier_id=%s AND o.status='COMPLETED'", (cid,)),
    }

    # 待办事项：待报价询价单 / 待确认订单（48h）；议价待办已随供应商端议价定标下线移除
    todos = []
    for r in qall(g.conn, """
            SELECT i.id, i.inquiry_no, i.deadline, v.variety_name AS "varietyName", i.quantity
            FROM biz_inquiry i JOIN base_variety v ON v.id=i.variety_id
            WHERE i.is_deleted=0 AND i.source='PLATFORM' AND i.status IN ('SENT','QUOTING')
              AND EXISTS (SELECT 1 FROM biz_inquiry_invite inv WHERE inv.inquiry_id=i.id
                          AND inv.supplier_id=%s AND inv.is_deleted=0)
              AND NOT EXISTS (SELECT 1 FROM biz_quote q WHERE q.inquiry_id=i.id
                          AND q.supplier_id=%s AND q.is_deleted=0)
            ORDER BY i.deadline LIMIT 20""", (cid, cid)):
        todos.append({'kind': 'QUOTE', 'main': '询价单 %s 待报价（%s，%s 湿吨，%s 截止）' % (
            r['inquiry_no'], r['varietyName'], r['quantity'],
            r['deadline'].strftime('%m-%d %H:%M') if r['deadline'] else '-')})
    for r in qall(g.conn, """
            SELECT o.id, o.order_no, o.created_at FROM biz_order o
            WHERE o.is_deleted=0 AND o.supplier_id=%s AND o.status='PENDING_CONFIRM'
            ORDER BY o.id DESC LIMIT 20""", (cid,)):
        todos.append({'kind': 'CONFIRM', 'main': '订单 %s 待确认（48 小时期限内）' % r['order_no'],
                      'time': r['created_at']})

    # 近期动态：仅显示运营端（平台）发布的公告/活动类信息（含平台广播），最近 10 条；
    # 订单相关的任务与消息仅在小铃铛（消息抽屉）中显示
    recent = qall(g.conn, """
        SELECT id, title, content, biz_type AS "bizType", biz_id AS "bizId",
               msg_category AS "category", need_action AS "needAction", created_at
        FROM sys_message
        WHERE (receiver_company_id=%s OR receiver_company_id IS NULL)
          AND sender_company_id IS NULL
          AND msg_category IN ('ANNOUNCE', 'ACTIVITY')
        ORDER BY id DESC LIMIT 10""", (cid,))
    return ok({'kpi': kpi, 'todos': todos, 'recent': recent})
