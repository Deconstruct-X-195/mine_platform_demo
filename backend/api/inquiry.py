"""询价与报价（PRD 4.4/T08-T10）：询价创建/邀请/发出、密封报价、截止揭示与比价快照、流标。

核心规则：
- 报价截止 ≥ 当前+2h 且 ≤ 到货日期前 7 天；
- 密封报价：截止前供应商只见自己的报价，任何一方都看不到他人价格；
- 截止后揭示生成比价表快照（按价格升序固化），响应不足标记"响应不足"；
- 可询量 = 明细数量 - 已询量累计，发单时扣减。
"""
from datetime import datetime, timedelta
from decimal import Decimal
import json

from flask import g, request

from ..common import (ApiError, decimal_field, doc_no, get_params, json_payload,
                      ok, op_log, page_args, page_data, parse_date, parse_datetime,
                      require_fields, send_msg)
from ..db import execute, qall, q1
from ..security import ROLE_STEEL, ROLE_SUPPLIER, auth_required, roles_required
from ..state_machine import assert_status, transition
from . import bp


# ---------------- 询价 ----------------

@bp.post('/inquiries')
@roles_required(ROLE_STEEL)
def create_inquiry():
    p = get_params()
    require_fields(p, 'demandId', 'demandItemId', 'quantity', 'arriveDate', 'deadline')
    item = q1(g.conn, """
        SELECT i.*, d.company_id, d.status AS demand_status, d.id AS demand_id2
        FROM biz_demand_item i JOIN biz_demand d ON d.id=i.demand_id
        WHERE i.id=%s AND i.demand_id=%s AND i.is_deleted=0 AND d.is_deleted=0
        """, (p['demandItemId'], p['demandId']))
    if not item or item['company_id'] != g.ctx.company['id']:
        raise ApiError(40401, '需求明细不存在')
    if item['demand_status'] not in ('SUBMITTED', 'INQUIRING'):
        raise ApiError(40901, '需求单状态为 %s，不可发起询价' % item['demand_status'])
    qty = p['quantity']
    remain = item['quantity'] - item['inquired_qty']
    if qty <= 0:
        raise ApiError(40001, '询价数量必须大于0')
    if qty > remain:
        raise ApiError(40001, '询价数量 %.3f 超过剩余可询量 %.3f' % (qty, remain))

    arrive = parse_date(p, 'arriveDate')
    deadline = parse_datetime(p, 'deadline')
    if deadline < datetime.now() + timedelta(hours=2):
        raise ApiError(40001, '报价截止时间必须至少为当前时间 +2 小时')
    if deadline.date() > arrive - timedelta(days=7):
        raise ApiError(40001, '报价截止时间不能晚于到货日期前 7 天')

    invites = p.get('inviteSupplierIds') or []
    if invites:
        _check_invites(invites)
    else:
        # 邀请供应商改为自动邀请：未指定时邀请全部已准入且启用的供应商
        invites = [r['id'] for r in qall(g.conn, """
            SELECT id FROM ent_company
            WHERE position('SUPPLIER' in company_types) > 0
              AND audit_status='APPROVED' AND status='ENABLED' AND is_deleted=0
        """)]
    min_response = p.get('minResponse') or 2
    if not (1 <= int(min_response) <= 10):
        raise ApiError(40001, '最少响应家数取值 1~10')

    iid = execute(g.conn, """
        INSERT INTO biz_inquiry (inquiry_no, demand_id, demand_item_id, buyer_id, variety_id, grade,
            quantity, delivery_type, delivery_place, expect_arrive_date, settle_type,
            deadline, min_response, inquiry_desc, status, created_by, updated_by)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'DRAFT',%s,%s) RETURNING id
        """, (doc_no(g.conn, 'XJ'), p['demandId'], p['demandItemId'], g.ctx.company['id'],
              item['variety_id'], item['grade'], qty, p.get('deliveryType'), p.get('deliveryPlace'),
              arrive, p.get('settleType'), deadline, int(min_response), p.get('remark'),
              g.ctx.user['id'], g.ctx.user['id']), returning_id=True)
    for sid in dict.fromkeys(invites):  # 去重保序
        execute(g.conn, "INSERT INTO biz_inquiry_invite (inquiry_id, supplier_id) VALUES (%s,%s)",
                (iid, sid))
    op_log(g.conn, g.ctx, 'biz_inquiry', iid, 'CREATE', None, {'quantity': str(qty), 'invites': invites})
    return ok({'id': iid, 'status': 'DRAFT', 'remainQty': str(remain)})


def create_and_send_platform_inquiry(conn, buyer_id, user_id, item, quantity,
                                     arrive, deadline, min_response, supplier_ids,
                                     batch_no, remark=None, demand_id=None):
    """平台代发询价（运营端「报价询价」专用，只增不改现有链路）。

    与钢厂自发询价同语义：DRAFT→SENT 状态机流转、发单扣减可询量、
    需求单转 INQUIRING、受邀供应商站内通知。buyer_id 为需求归属钢厂，
    钢厂端现有页面因此天然可见（即"价格返回钢厂"的可见性基础）。
    参数 item 为 biz_demand_item 行（含 variety_id/grade/demand_item 主键）。
    返回询价单 id。
    """
    did = demand_id or item['demand_id']
    iid = execute(conn, """
        INSERT INTO biz_inquiry (inquiry_no, demand_id, demand_item_id, buyer_id, variety_id, grade,
            quantity, expect_arrive_date, deadline, min_response, inquiry_desc, status,
            source, batch_no, created_by, updated_by)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'DRAFT','PLATFORM',%s,%s,%s) RETURNING id
        """, (doc_no(conn, 'XJ'), did, item['id'], buyer_id, item['variety_id'], item['grade'],
              quantity, arrive, deadline, int(min_response), remark,
              batch_no, user_id, user_id), returning_id=True)
    for sid in dict.fromkeys(supplier_ids):  # 去重保序
        execute(conn, "INSERT INTO biz_inquiry_invite (inquiry_id, supplier_id) VALUES (%s,%s)",
                (iid, sid))
    transition(conn, None, 'biz_inquiry', '询价单', 'biz_inquiry', iid, 'SENT')
    execute(conn, "UPDATE biz_inquiry SET sent_at=now(), updated_by=%s WHERE id=%s", (user_id, iid))
    # 扣减可询量 + 需求转入 INQUIRING（与 send_inquiry 同语义）
    execute(conn, """
        UPDATE biz_demand_item SET inquired_qty = inquired_qty + %s, updated_at=now() WHERE id=%s
        """, (quantity, item['id']))
    drow = q1(conn, "SELECT id, status FROM biz_demand WHERE id=%s", (did,))
    if drow and drow['status'] == 'SUBMITTED':
        transition(conn, None, 'biz_demand', '需求单', 'biz_demand', did, 'INQUIRING')
    ino = q1(conn, "SELECT inquiry_no, deadline FROM biz_inquiry WHERE id=%s", (iid,))
    for sid in dict.fromkeys(supplier_ids):
        send_msg(conn, sid, '收到询价邀请',
                 '询价单 %s 已发出（平台集中询价），请于 %s 前报价。' % (ino['inquiry_no'], ino['deadline']),
                 'INQUIRY', iid)
    return iid


def create_and_send_agg_inquiry(conn, agg, user_id, arrive, deadline,
                                min_response, supplier_ids, batch_no, remark):
    """归集订单整单询价：buyer_id 为空（多钢厂联合），量已在归集时锁定，不再扣减。返回询价单 id。"""
    # 交货/结算条件取归集成员需求单第一行（成员需求同批次归集，地点口径一致）
    first_demand = q1(conn, """
        SELECT d.delivery_type, d.delivery_place, d.settle_type
        FROM biz_aggregated_order_item m JOIN biz_demand d ON d.id=m.demand_id
        WHERE m.agg_id=%s AND m.is_deleted=0 ORDER BY m.id LIMIT 1
        """, (agg['id'],)) or {}
    iid = execute(conn, """
        INSERT INTO biz_inquiry (inquiry_no, buyer_id, variety_id, grade, quantity,
            delivery_type, delivery_place, settle_type,
            expect_arrive_date, deadline, min_response, inquiry_desc, status,
            source, batch_no, agg_id, created_by, updated_by)
        VALUES (%s, NULL, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'DRAFT', 'PLATFORM', %s, %s, %s, %s)
        RETURNING id
        """, (doc_no(conn, 'XJ'), agg['variety_id'], agg['grade'], agg['total_qty'],
              first_demand.get('delivery_type'), first_demand.get('delivery_place'),
              first_demand.get('settle_type'),
              arrive, deadline, int(min_response), remark, batch_no, agg['id'],
              user_id, user_id), returning_id=True)
    for sid in dict.fromkeys(supplier_ids):  # 去重保序
        execute(conn, "INSERT INTO biz_inquiry_invite (inquiry_id, supplier_id) VALUES (%s,%s)",
                (iid, sid))
    transition(conn, None, 'biz_inquiry', '询价单', 'biz_inquiry', iid, 'SENT')
    execute(conn, "UPDATE biz_inquiry SET sent_at=now(), updated_by=%s WHERE id=%s", (user_id, iid))
    ino = q1(conn, "SELECT inquiry_no, deadline FROM biz_inquiry WHERE id=%s", (iid,))
    mills = qall(conn, """
        SELECT DISTINCT company_id FROM biz_aggregated_order_item
        WHERE agg_id=%s AND is_deleted=0
        """, (agg['id'],))
    for m in mills:
        send_msg(conn, m['company_id'], '归集需求已发起询价',
                 '归集订单 %s 已向 %s 家供应商发出询价（含贵司需求份额），报价汇总后将推送贵司。'
                 % (agg['agg_no'], len(set(supplier_ids))), 'AGG_ORDER', agg['id'])
    for sid in dict.fromkeys(supplier_ids):
        send_msg(conn, sid, '收到询价邀请',
                 '归集订单 %s 询价已发出（平台集采），请于 %s 前报价。' % (agg['agg_no'], ino['deadline']),
                 'INQUIRY', iid)
    return iid


def _check_invites(supplier_ids):
    rows = qall(g.conn, """
        SELECT id FROM ent_company
        WHERE id = ANY(%s) AND audit_status='APPROVED' AND status='ENABLED' AND is_deleted=0
        """, (list(supplier_ids),))
    got = {r['id'] for r in rows}
    missing = [s for s in supplier_ids if s not in got]
    if missing:
        raise ApiError(40001, '以下供应商不存在或未准入：%s' % missing)


def _agg_member_company_ids(conn, agg_id):
    """归集订单全部成员钢厂 id（去重）。"""
    return [r['company_id'] for r in qall(conn, """
        SELECT DISTINCT d.company_id FROM biz_aggregated_order_item m
        JOIN biz_demand d ON d.id=m.demand_id
        WHERE m.agg_id=%s AND m.is_deleted=0 AND d.is_deleted=0
        """, (agg_id,))]


def _is_agg_member(conn, iid, company_id):
    """当前询价单是否为归集询价且该公司是归集成员钢厂。"""
    if not company_id:
        return False
    return bool(q1(conn, """
        SELECT 1 FROM biz_inquiry i
        JOIN biz_aggregated_order_item m ON m.agg_id=i.agg_id AND m.is_deleted=0
        JOIN biz_demand d ON d.id=m.demand_id AND d.is_deleted=0
        WHERE i.id=%s AND d.company_id=%s LIMIT 1
        """, (iid, company_id)))


@bp.post('/inquiries/<int:iid>/send')
@roles_required(ROLE_STEEL)
def send_inquiry(iid):
    row = q1(g.conn, "SELECT * FROM biz_inquiry WHERE id=%s AND is_deleted=0", (iid,))
    if not row or row['buyer_id'] != g.ctx.company['id']:
        raise ApiError(40401, '询价单不存在')
    assert_status(row, 'DRAFT', '询价单')
    transition(g.conn, g.ctx, 'biz_inquiry', '询价单', 'biz_inquiry', iid, 'SENT')
    execute(g.conn, "UPDATE biz_inquiry SET sent_at=now(), updated_by=%s WHERE id=%s",
            (g.ctx.user['id'], iid))
    # 扣减可询量 + 需求转入 INQUIRING
    execute(g.conn, """
        UPDATE biz_demand_item SET inquired_qty = inquired_qty + %s, updated_at=now() WHERE id=%s
        """, (row['quantity'], row['demand_item_id']))
    drow = q1(g.conn, "SELECT id, status FROM biz_demand WHERE id=%s", (row['demand_id'],))
    if drow and drow['status'] == 'SUBMITTED':
        transition(g.conn, g.ctx, 'biz_demand', '需求单', 'biz_demand', row['demand_id'], 'INQUIRING')
    # 通知受邀供应商
    for inv in qall(g.conn, "SELECT supplier_id FROM biz_inquiry_invite WHERE inquiry_id=%s AND is_deleted=0", (iid,)):
        send_msg(g.conn, inv['supplier_id'], '收到询价邀请',
                 '询价单 %s 已发出，请于 %s 前报价。' % (row['inquiry_no'], row['deadline']),
                 'INQUIRY', iid)
    return ok({'id': iid, 'status': 'SENT'})


@bp.get('/inquiries')
@auth_required
def list_inquiries():
    params = request.args.to_dict()
    page, size = page_args(params)
    where, args = 'WHERE i.is_deleted=0', []
    if g.ctx.has_role(ROLE_STEEL):
        # 本钢厂询价 + 本钢厂作为归集成员的归集询价（buyer_id 为空）
        where += """ AND (i.buyer_id=%s OR (i.agg_id IS NOT NULL AND EXISTS (
            SELECT 1 FROM biz_aggregated_order_item m
            JOIN biz_demand d ON d.id=m.demand_id
            WHERE m.agg_id=i.agg_id AND m.is_deleted=0 AND d.is_deleted=0 AND d.company_id=%s)))"""
        args.extend([g.ctx.company['id'], g.ctx.company['id']])
        if params.get('status'):
            where += ' AND i.status=%s'
            args.append(params['status'])
        total = q1(g.conn, 'SELECT count(*) AS c FROM biz_inquiry i ' + where, args)['c']
        rows = qall(g.conn, """
            SELECT i.*, v.variety_name AS "varietyName",
                   (SELECT count(*) FROM biz_inquiry_invite inv WHERE inv.inquiry_id=i.id AND inv.is_deleted=0) AS "inviteCount",
                   (SELECT count(*) FROM biz_quote q WHERE q.inquiry_id=i.id AND q.is_deleted=0) AS "quoteCount"
            FROM biz_inquiry i JOIN base_variety v ON v.id=i.variety_id
            %s ORDER BY i.id DESC LIMIT %%s OFFSET %%s
            """ % where, args + [size, (page - 1) * size])
    elif g.ctx.has_role(ROLE_SUPPLIER):
        where += """ AND EXISTS (SELECT 1 FROM biz_inquiry_invite inv
                     WHERE inv.inquiry_id=i.id AND inv.supplier_id=%s AND inv.is_deleted=0)"""
        args.append(g.ctx.company['id'])
        if params.get('status'):
            where += ' AND i.status=%s'
            args.append(params['status'])
        total = q1(g.conn, 'SELECT count(*) AS c FROM biz_inquiry i ' + where, args)['c']
        # 占位符文本顺序：myQuoteId、myQuoteStatus 两个子查询，再 where 中 EXISTS 的 supplier_id 与可选 status
        sargs = [g.ctx.company['id']] * 3
        if params.get('status'):
            sargs.append(params['status'])
        rows = qall(g.conn, """
            SELECT i.id, i.inquiry_no AS "inquiryNo", i.variety_id AS "varietyId",
                   v.variety_name AS "varietyName", i.grade, i.quantity,
                   i.delivery_type AS "deliveryType", i.delivery_place AS "deliveryPlace",
                   i.expect_arrive_date AS "expectArriveDate", i.settle_type AS "settleType",
                   i.deadline, i.status, i.created_at AS "createdAt",
                   (SELECT q.id FROM biz_quote q WHERE q.inquiry_id=i.id AND q.supplier_id=%%s AND q.is_deleted=0) AS "myQuoteId",
                   (SELECT q.status FROM biz_quote q WHERE q.inquiry_id=i.id AND q.supplier_id=%%s AND q.is_deleted=0) AS "myQuoteStatus"
            FROM biz_inquiry i JOIN base_variety v ON v.id=i.variety_id
            %s ORDER BY i.id DESC LIMIT %%s OFFSET %%s
            """ % where, sargs + [size, (page - 1) * size])
    else:
        total = 0
        rows = []
    return ok(page_data(rows, total, page, size))


@bp.get('/inquiries/<int:iid>')
@auth_required
def inquiry_detail(iid):
    row = q1(g.conn, """
        SELECT i.*, v.variety_name AS "varietyName"
        FROM biz_inquiry i JOIN base_variety v ON v.id=i.variety_id
        WHERE i.id=%s AND i.is_deleted=0
        """, (iid,))
    if not row:
        raise ApiError(40401, '询价单不存在')
    is_buyer = g.ctx.company and (row['buyer_id'] == g.ctx.company['id']
                                  or _is_agg_member(g.conn, iid, g.ctx.company['id']))
    is_supplier = g.ctx.company and q1(
        g.conn, "SELECT id FROM biz_inquiry_invite WHERE inquiry_id=%s AND supplier_id=%s AND is_deleted=0",
        (iid, g.ctx.company['id']))
    if not (g.ctx.is_plat or is_buyer or is_supplier):
        raise ApiError(40301, '无权限查看该询价单')
    data = json_payload(dict(row))
    data['notice'] = '密封报价：报价截止前不展示任何报价价格'
    # 归集成员钢厂：返回本钢厂需求份额（前端按钢厂自己的询价信息展示）
    data['aggView'] = bool(row['agg_id'] and g.ctx.company
                           and _is_agg_member(g.conn, iid, g.ctx.company['id']))
    if data['aggView']:
        data['shareQty'] = json_payload(q1(g.conn, """
            SELECT COALESCE(SUM(m.quantity), 0) AS s FROM biz_aggregated_order_item m
            JOIN biz_demand d ON d.id=m.demand_id
            WHERE m.agg_id=%s AND m.is_deleted=0 AND d.is_deleted=0 AND d.company_id=%s
            """, (row['agg_id'], g.ctx.company['id']))['s'])
        # 报价供应商名单（仅公司名与报价状态，不含价格——密封期原则）
        data['quoteSuppliers'] = qall(g.conn, """
            SELECT c.company_name AS "supplierName", q.status AS "quoteStatus",
                   to_char(q.created_at, 'YYYY-MM-DD HH24:MI') AS "quotedAt"
            FROM biz_quote q JOIN ent_company c ON c.id=q.supplier_id
            WHERE q.inquiry_id=%s AND q.is_deleted=0 ORDER BY q.created_at
            """, (iid,))
    if g.ctx.is_plat or (is_buyer and not data['aggView']):
        invites = qall(g.conn, """
            SELECT inv.supplier_id AS "supplierId", c.company_name AS "supplierName", inv.status,
                   (SELECT q.id FROM biz_quote q WHERE q.inquiry_id=i.id AND q.supplier_id=inv.supplier_id
                     AND q.is_deleted=0) AS "quoteId",
                   (SELECT q.status FROM biz_quote q WHERE q.inquiry_id=i.id AND q.supplier_id=inv.supplier_id
                     AND q.is_deleted=0) AS "quoteStatus"
            FROM biz_inquiry_invite inv
            JOIN ent_company c ON c.id=inv.supplier_id
            CROSS JOIN (SELECT %s AS id) i
            WHERE inv.inquiry_id=%s AND inv.is_deleted=0 ORDER BY inv.id
            """, (iid, iid))
        # 截止前只给"已报价/未报价"标记，不给价格（密封）
        revealed = row['status'] in ('CLOSED', 'BARGAINING', 'AWARDED', 'FAILED')
        if not revealed:
            invites = [{k: v for k, v in inv.items() if k not in ('price', 'quantity')} for inv in invites]
        data['invites'] = json_payload(invites)
    if g.ctx.company and is_supplier:
        mine = q1(g.conn, """
            SELECT * FROM biz_quote WHERE inquiry_id=%s AND supplier_id=%s AND is_deleted=0
            """, (iid, g.ctx.company['id']))
        data['myQuote'] = json_payload(dict(mine)) if mine else None
    return ok(data)


# ---------------- 报价（密封） ----------------

def _quote_payload_check(conn, inq, p):
    require_fields(p, 'deliveryDate')
    # 数值字段统一规范化：前端 <input> 的 value 为字符串，非法值返回 40001 而非 500
    price = decimal_field(p, 'price', positive=False)
    qty = decimal_field(p, 'quantity', positive=False)
    if price <= 0:
        raise ApiError(40001, '报价单价必须大于0')
    if qty <= 0:
        raise ApiError(40001, '可供数量必须大于0')
    if qty < Decimal(str(inq['quantity'])) * Decimal('0.8') and not (p.get('remark') or '').strip():
        raise ApiError(40001, '可供数量低于询价量 80% 时必须填写备注说明')
    delivery_date = parse_date(p, 'deliveryDate')
    if inq['expect_arrive_date'] and delivery_date > inq['expect_arrive_date']:
        raise ApiError(40001, '交货期承诺晚于期望到货日期')
    return price, qty, delivery_date


def _quote_extra_fields(p):
    """报价扩展字段：含税标志（必填）、运价（必填 ≥0）、交货方式（必填枚举）。"""
    tax = p.get('taxType') or ''
    if tax not in ('INC_TAX', 'EX_TAX'):
        raise ApiError(40001, '请选择含税/不含税')
    freight = decimal_field(p, 'freightPrice', positive=False, required=True)
    if freight < 0:
        raise ApiError(40001, '运价必须 ≥ 0')
    dtype = p.get('deliveryType') or ''
    if dtype not in ('PORT_FOB', 'PORT_TRUCK', 'PLANT'):
        raise ApiError(40001, '请选择交货方式（港口离岸/港口自提/厂内自提）')
    return tax, freight, dtype


@bp.post('/inquiries/<int:iid>/quotes')
@roles_required(ROLE_SUPPLIER)
def submit_quote(iid):
    row = q1(g.conn, "SELECT * FROM biz_inquiry WHERE id=%s AND is_deleted=0", (iid,))
    if not row:
        raise ApiError(40401, '询价单不存在')
    if row['status'] not in ('SENT', 'QUOTING'):
        raise ApiError(40901, '询价单已停止报价（%s）' % row['status'])
    if datetime.now() >= row['deadline']:
        raise ApiError(40901, '报价已截止')
    inv = q1(g.conn, "SELECT id FROM biz_inquiry_invite WHERE inquiry_id=%s AND supplier_id=%s AND is_deleted=0",
             (iid, g.ctx.company['id']))
    if not inv:
        raise ApiError(40301, '未被邀请，无法报价')
    exists = q1(g.conn, "SELECT id FROM biz_quote WHERE inquiry_id=%s AND supplier_id=%s AND is_deleted=0",
                (iid, g.ctx.company['id']))
    if exists:
        raise ApiError(40902, '已提交过报价，请走修改（PUT /quotes/{id}）')
    p = get_params()
    price, qty, delivery_date = _quote_payload_check(g.conn, row, p)
    tax_type, freight_price, delivery_type = _quote_extra_fields(p)
    default_valid = (row['deadline'] + timedelta(days=7)).date() if hasattr(row['deadline'], 'date') else row['deadline']
    qid = execute(g.conn, """
        INSERT INTO biz_quote (quote_no, inquiry_id, supplier_id, price, quantity, delivery_date,
            delivery_place, pay_terms, quality_commit, valid_until, remark, tax_type,
            freight_price, delivery_type, version, status, created_by, updated_by)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,1,'SUBMITTED',%s,%s) RETURNING id
        """, (doc_no(g.conn, 'BJ'), iid, g.ctx.company['id'], price, qty, delivery_date,
              p.get('deliveryPlace'), p.get('paymentTerms'), p.get('qualityTerms'),
              parse_date(p, 'validUntil', required=False) or default_valid, p.get('remark'),
              tax_type, freight_price, delivery_type,
              g.ctx.user['id'], g.ctx.user['id']), returning_id=True)
    if row['status'] == 'SENT':
        transition(g.conn, g.ctx, 'biz_inquiry', '询价单', 'biz_inquiry', iid, 'QUOTING')
    execute(g.conn, "UPDATE biz_inquiry_invite SET status='RECEIVED' WHERE inquiry_id=%s AND supplier_id=%s",
            (iid, g.ctx.company['id']))
    # 报价单推送运营端：站内消息提醒平台（receiver_company_id 为空 = 平台消息）
    send_msg(g.conn, None, '收到新报价',
             '供应商「%s」已对询价单 %s 提交报价（可供 %s 吨、交期 %s），请前往「报价询价」查看汇总。'
             % (g.ctx.company['company_name'], row['inquiry_no'], qty, delivery_date),
             'INQUIRY', iid)
    op_log(g.conn, g.ctx, 'biz_quote', qid, 'CREATE', None,
           {'price': str(price), 'quantity': str(qty)})
    return ok({'id': qid, 'status': 'SUBMITTED', 'sealed': True})


@bp.put('/quotes/<int:qid>')
@roles_required(ROLE_SUPPLIER)
def update_quote(qid):
    row = q1(g.conn, "SELECT * FROM biz_quote WHERE id=%s AND is_deleted=0", (qid,))
    if not row:
        raise ApiError(40401, '报价不存在')
    if row['supplier_id'] != g.ctx.company['id']:
        raise ApiError(40301, '无权限修改该报价')
    if row['status'] != 'SUBMITTED':
        raise ApiError(40901, '报价已揭示/结束，不可修改')
    inq = q1(g.conn, "SELECT * FROM biz_inquiry WHERE id=%s AND is_deleted=0", (row['inquiry_id'],))
    if datetime.now() >= inq['deadline']:
        raise ApiError(40901, '报价已截止，不可修改')
    p = get_params()
    price, qty, delivery_date = _quote_payload_check(g.conn, inq, p)
    tax_type, freight_price, delivery_type = _quote_extra_fields(p)
    execute(g.conn, """
        UPDATE biz_quote SET price=%s, quantity=%s, delivery_date=%s, delivery_place=%s,
            pay_terms=%s, quality_commit=%s, valid_until=%s, remark=%s,
            tax_type=%s, freight_price=%s, delivery_type=%s,
            version=version+1, updated_by=%s, updated_at=now() WHERE id=%s
        """, (price, qty, delivery_date, p.get('deliveryPlace'), p.get('paymentTerms'),
              p.get('qualityTerms'), parse_date(p, 'validUntil', required=False) or row['valid_until'],
              p.get('remark'), tax_type, freight_price, delivery_type,
              g.ctx.user['id'], qid))
    op_log(g.conn, g.ctx, 'biz_quote', qid, 'UPDATE', json_payload(row),
           {'price': str(price), 'quantity': str(qty), 'version': row['version'] + 1})
    return ok({'id': qid, 'version': row['version'] + 1, 'status': 'SUBMITTED'})


@bp.get('/quotes/<int:qid>')
@auth_required
def quote_detail(qid):
    row = q1(g.conn, "SELECT * FROM biz_quote WHERE id=%s AND is_deleted=0", (qid,))
    if not row:
        raise ApiError(40401, '报价不存在')
    inq = q1(g.conn, "SELECT buyer_id FROM biz_inquiry WHERE id=%s", (row['inquiry_id'],))
    allowed = (g.ctx.is_plat or (g.ctx.company and row['supplier_id'] == g.ctx.company['id']))
    if not allowed:
        raise ApiError(40301, '密封报价截止前仅供应商本人可见')
    data = json_payload(dict(row))
    data['notice'] = '密封报价'
    return ok(data)


# ---------------- 揭示与比价快照 ----------------

def reveal_inquiry(conn, iid, ctx):
    """截止后揭示全部报价并生成比价表快照（按价格升序固化）。定时任务与手动接口共用。"""
    row = q1(conn, "SELECT * FROM biz_inquiry WHERE id=%s AND is_deleted=0", (iid,))
    if not row:
        raise ApiError(40401, '询价单不存在')
    if row['status'] in ('CLOSED', 'BARGAINING', 'AWARDED', 'FAILED'):
        snap = row['reveal_snapshot']
        return json.loads(snap) if snap else None
    if row['status'] == 'DRAFT':
        raise ApiError(40901, '询价尚未发出，无报价可揭示')

    quotes = qall(conn, """
        SELECT q.id, q.supplier_id, q.price, q.quantity, q.delivery_date,
               q.pay_terms, q.valid_until, q.status, q.tax_type, q.freight_price
        FROM biz_quote q WHERE q.inquiry_id=%s AND q.is_deleted=0 ORDER BY q.price, q.id
        """, (iid,))
    min_resp = row['min_response'] or 2
    shortage = len(quotes) < min_resp
    snapshot = {
        'revealedAt': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'inquiryNo': row['inquiry_no'],
        'minResponse': min_resp,
        'responseShortage': shortage,
        'rows': [
            {'seq': i + 1, 'quoteId': qt['id'], 'unitPrice': str(qt['price']),
             'quantity': str(qt['quantity']),
             'taxType': qt['tax_type'],
             'freightPrice': str(qt['freight_price']) if qt['freight_price'] is not None else None,
             'responseRate': str(round(qt['quantity'] / row['quantity'] * 100, 2)) + '%',
             'deliveryDate': qt['delivery_date'].strftime('%Y-%m-%d') if qt['delivery_date'] else None,
             'payTerms': qt['pay_terms'], 'validUntil': qt['valid_until'].strftime('%Y-%m-%d') if qt['valid_until'] else None}
            for i, qt in enumerate(quotes)
        ],
    }
    snapshot_text = json.dumps(json_payload(snapshot), ensure_ascii=False)
    if row['status'] in ('SENT', 'QUOTING'):
        transition(conn, ctx, 'biz_inquiry', '询价单', 'biz_inquiry', iid, 'CLOSED')
        for qt in quotes:
            if qt['status'] == 'SUBMITTED':
                execute(conn, "UPDATE biz_quote SET status='REVEALED', updated_at=now() WHERE id=%s", (qt['id'],))
    execute(conn, "UPDATE biz_inquiry SET reveal_snapshot=%s, updated_at=now() WHERE id=%s",
            (snapshot_text, iid))
    return json_payload(snapshot)


@bp.post('/inquiries/<int:iid>/reveal')
@roles_required(ROLE_STEEL)
def manual_reveal(iid):
    row = q1(g.conn, "SELECT * FROM biz_inquiry WHERE id=%s AND is_deleted=0", (iid,))
    is_owner = g.ctx.company and (row and (row['buyer_id'] == g.ctx.company['id']
                                           or _is_agg_member(g.conn, iid, g.ctx.company['id'])))
    if not row or not is_owner:
        raise ApiError(40401, '询价单不存在')
    if datetime.now() < row['deadline']:
        raise ApiError(40901, '报价尚未截止，不可揭示')
    snapshot = json_payload(reveal_inquiry(g.conn, iid, g.ctx))
    # 归集询价揭示后通知全部成员钢厂；单钢厂询价通知买方
    if row['agg_id']:
        for cid in _agg_member_company_ids(g.conn, row['agg_id']):
            send_msg(g.conn, cid, '报价已揭示',
                     '归集订单询价 %s 报价截止，共 %d 家报价，请查看比价表。'
                     % (row['inquiry_no'], len(snapshot['rows'])), 'INQUIRY', iid)
    else:
        send_msg(g.conn, row['buyer_id'], '报价已揭示',
                 '询价单 %s 报价截止，共 %d 家报价，请查看比价表。' % (row['inquiry_no'], len(snapshot['rows'])),
                 'INQUIRY', iid)
    return ok(snapshot)


@bp.get('/inquiries/<int:iid>/quotes/reveal')
@roles_required(ROLE_STEEL)
def get_reveal(iid):
    row = q1(g.conn, "SELECT * FROM biz_inquiry WHERE id=%s AND is_deleted=0", (iid,))
    is_owner = g.ctx.company and (row and (row['buyer_id'] == g.ctx.company['id']
                                           or _is_agg_member(g.conn, iid, g.ctx.company['id'])))
    if not row or not is_owner:
        raise ApiError(40401, '询价单不存在')
    if datetime.now() < row['deadline'] and row['status'] in ('DRAFT', 'SENT', 'QUOTING'):
        raise ApiError(40901, '报价尚未截止，不可揭示')
    snap = json_payload(reveal_inquiry(g.conn, iid, g.ctx))
    if not snap:
        return ok(snap)
    # 归集询价：按当前钢厂的需求份额拆分推送（数量=该钢厂份额，价格/运价/交期沿用供应商报价）
    if row['agg_id'] and _is_agg_member(g.conn, iid, g.ctx.company['id']):
        share = q1(g.conn, """
            SELECT COALESCE(SUM(m.quantity), 0) AS s FROM biz_aggregated_order_item m
            JOIN biz_demand d ON d.id=m.demand_id
            WHERE m.agg_id=%s AND m.is_deleted=0 AND d.is_deleted=0 AND d.company_id=%s
            """, (row['agg_id'], g.ctx.company['id']))['s']
        snap = dict(snap)
        snap['shareQty'] = str(share)
        snap['rows'] = [dict(r, quantity=str(share)) for r in snap['rows']]
    return ok(snap)


@bp.post('/inquiries/<int:iid>/feedback')
@roles_required(ROLE_STEEL)
def agg_inquiry_feedback(iid):
    """钢厂对归集询价比价结果表态：确认（ACCEPTED）/不认可（REJECTED，必填原因）。

    表态结果推送运营端（平台消息），由平台决定是否重新发起询价。
    """
    p = get_params()
    require_fields(p, 'decision')
    if p['decision'] not in ('ACCEPTED', 'REJECTED'):
        raise ApiError(40001, 'decision 仅支持 ACCEPTED/REJECTED')
    row = q1(g.conn, "SELECT * FROM biz_inquiry WHERE id=%s AND is_deleted=0", (iid,))
    if not row or not row['agg_id']:
        raise ApiError(40401, '询价单不存在或非归集询价')
    if not _is_agg_member(g.conn, iid, g.ctx.company['id']):
        raise ApiError(40301, '仅归集订单成员钢厂可反馈')
    reason = p.get('reason')
    if p['decision'] == 'REJECTED' and not (reason and str(reason).strip()):
        raise ApiError(40001, '不认可报价必须填写原因')
    execute(g.conn, """
        INSERT INTO biz_agg_inquiry_feedback (inquiry_id, agg_id, company_id, decision, reason, created_by)
        VALUES (%s,%s,%s,%s,%s,%s)
        ON CONFLICT (inquiry_id, company_id)
        DO UPDATE SET decision=EXCLUDED.decision, reason=EXCLUDED.reason,
                      created_at=now(), created_by=EXCLUDED.created_by
        """, (iid, row['agg_id'], g.ctx.company['id'], p['decision'],
              (str(reason).strip()[:200] if reason else None), g.ctx.user['id']))
    verb = '认可' if p['decision'] == 'ACCEPTED' else '不认可'
    # 不认可：询价单转「反馈待处理」，待运营重新发起询价后回退已截止
    if p['decision'] == 'REJECTED' and row['status'] == 'CLOSED':
        transition(g.conn, g.ctx, 'biz_inquiry', '询价单', 'biz_inquiry', iid, 'FEEDBACK')
    send_msg(g.conn, None, '钢厂对归集询价反馈',
             '钢厂「%s」对归集询价 %s 的比价结果反馈为【%s】%s。如需调整采购条件，可重新发起询价。'
             % (g.ctx.company['company_name'], row['inquiry_no'], verb,
                ('，原因：' + str(reason).strip()) if reason else ''),
             'INQUIRY', iid)
    op_log(g.conn, g.ctx, 'biz_inquiry', iid, 'AGG FEEDBACK', None,
           {'decision': p['decision'], 'reason': reason})
    return ok({'decision': p['decision']})


# ---------------- 流标 ----------------

@bp.post('/inquiries/<int:iid>/fail')
@roles_required(ROLE_STEEL)
def fail_inquiry(iid):
    row = q1(g.conn, "SELECT * FROM biz_inquiry WHERE id=%s AND is_deleted=0", (iid,))
    if not row or row['buyer_id'] != g.ctx.company['id']:
        raise ApiError(40401, '询价单不存在')
    if row['status'] not in ('SENT', 'QUOTING', 'CLOSED', 'BARGAINING'):
        raise ApiError(40901, '询价单状态为 %s，不可流标' % row['status'])
    p = get_params()
    require_fields(p, 'reason')
    frm = row['status']
    transition(g.conn, g.ctx, 'biz_inquiry', '询价单', 'biz_inquiry', iid, 'FAILED')
    execute(g.conn, "UPDATE biz_inquiry SET inquiry_desc=concat_ws(' | ', inquiry_desc, %s::VARCHAR), updated_by=%s WHERE id=%s",
            ('流标原因：' + p['reason'], g.ctx.user['id'], iid))
    # 归还可询量
    execute(g.conn, """
        UPDATE biz_demand_item SET inquired_qty = inquired_qty - %s, updated_at=now() WHERE id=%s
        """, (row['quantity'], row['demand_item_id']))
    for inv in qall(g.conn, "SELECT supplier_id FROM biz_inquiry_invite WHERE inquiry_id=%s AND is_deleted=0", (iid,)):
        send_msg(g.conn, inv['supplier_id'], '询价已流标',
                 '询价单 %s 已流标：%s' % (row['inquiry_no'], p['reason']), 'INQUIRY', iid)
    op_log(g.conn, g.ctx, 'biz_inquiry', iid, 'STATUS %s->FAILED' % frm, None, {'reason': p['reason']})
    return ok({'id': iid, 'status': 'FAILED'})


# ---------------- 议价对标数据 ----------------

@bp.get('/inquiries/<int:iid>/bargain-context')
@auth_required
def bargain_context(iid):
    """议价页同屏对标：基准价、其他供应商匿名报价、同品种近三月成交均价（PRD 4.5）。"""
    row = q1(g.conn, "SELECT * FROM biz_inquiry WHERE id=%s AND is_deleted=0", (iid,))
    if not row:
        raise ApiError(40401, '询价单不存在')
    if not (g.ctx.is_plat or (g.ctx.company and row['buyer_id'] == g.ctx.company['id']) or
            q1(g.conn, "SELECT id FROM biz_inquiry_invite WHERE inquiry_id=%s AND supplier_id=%s AND is_deleted=0",
               (iid, g.ctx.company['id']))):
        raise ApiError(40301, '无权限查看')

    base = q1(g.conn, """
        SELECT price, price_date AS "priceDate", price_basis AS "priceBasis"
        FROM base_price WHERE variety_id=%s AND is_deleted=0
        ORDER BY price_date DESC LIMIT 1
        """, (row['variety_id'],))
    revealed = row['status'] in ('CLOSED', 'BARGAINING', 'AWARDED', 'FAILED')
    others = []
    if revealed:
        sql = """
            SELECT q.price, q.quantity FROM biz_quote q
            WHERE q.inquiry_id=%s AND q.is_deleted=0 AND q.status NOT IN ('REJECTED')
        """
        args = [iid]
        if g.ctx.company and not g.ctx.is_plat and q1(
                g.conn, "SELECT 1 AS x FROM sys_user WHERE company_id=%s LIMIT 1", (g.ctx.company['id'],)):
            mine = q1(g.conn, "SELECT id FROM biz_quote WHERE inquiry_id=%s AND supplier_id=%s AND is_deleted=0",
                      (iid, g.ctx.company['id']))
            if mine:
                sql += ' AND q.id <> %s'
                args.append(mine['id'])
        rows = qall(g.conn, sql, args)
        others = ['%.2f' % r['price'] for r in rows]
    avg = q1(g.conn, """
        SELECT round(avg(o.unit_price), 2) AS avg_price, count(*) AS c
        FROM biz_order o
        WHERE o.variety_id=%s AND o.is_deleted=0 AND o.status NOT IN ('CANCELLED')
          AND o.created_at >= now() - interval '90 days'
        """, (row['variety_id'],))
    return ok({
        'basePrice': json_payload(base),
        'otherAnonymousPrices': others,
        'recentAvgPrice': str(avg['avg_price']) if avg and avg['avg_price'] is not None else None,
        'recentDealCount': avg['c'] if avg else 0,
    })
