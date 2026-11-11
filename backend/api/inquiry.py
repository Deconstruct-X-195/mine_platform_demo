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


def _check_invites(supplier_ids):
    rows = qall(g.conn, """
        SELECT id FROM ent_company
        WHERE id = ANY(%s) AND audit_status='APPROVED' AND status='ENABLED' AND is_deleted=0
        """, (list(supplier_ids),))
    got = {r['id'] for r in rows}
    missing = [s for s in supplier_ids if s not in got]
    if missing:
        raise ApiError(40001, '以下供应商不存在或未准入：%s' % missing)


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
        where += ' AND i.buyer_id=%s'
        args.append(g.ctx.company['id'])
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
    is_buyer = g.ctx.company and row['buyer_id'] == g.ctx.company['id']
    is_supplier = g.ctx.company and q1(
        g.conn, "SELECT id FROM biz_inquiry_invite WHERE inquiry_id=%s AND supplier_id=%s AND is_deleted=0",
        (iid, g.ctx.company['id']))
    if not (g.ctx.is_plat or is_buyer or is_supplier):
        raise ApiError(40301, '无权限查看该询价单')
    data = json_payload(dict(row))
    data['notice'] = '密封报价：报价截止前不展示任何报价价格'
    if g.ctx.is_plat or is_buyer:
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
    default_valid = (row['deadline'] + timedelta(days=7)).date() if hasattr(row['deadline'], 'date') else row['deadline']
    qid = execute(g.conn, """
        INSERT INTO biz_quote (quote_no, inquiry_id, supplier_id, price, quantity, delivery_date,
            delivery_place, pay_terms, quality_commit, valid_until, remark, version, status,
            created_by, updated_by)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,1,'SUBMITTED',%s,%s) RETURNING id
        """, (doc_no(g.conn, 'BJ'), iid, g.ctx.company['id'], price, qty, delivery_date,
              p.get('deliveryPlace'), p.get('paymentTerms'), p.get('qualityTerms'),
              parse_date(p, 'validUntil', required=False) or default_valid, p.get('remark'),
              g.ctx.user['id'], g.ctx.user['id']), returning_id=True)
    if row['status'] == 'SENT':
        transition(g.conn, g.ctx, 'biz_inquiry', '询价单', 'biz_inquiry', iid, 'QUOTING')
    execute(g.conn, "UPDATE biz_inquiry_invite SET status='RECEIVED' WHERE inquiry_id=%s AND supplier_id=%s",
            (iid, g.ctx.company['id']))
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
    execute(g.conn, """
        UPDATE biz_quote SET price=%s, quantity=%s, delivery_date=%s, delivery_place=%s,
            pay_terms=%s, quality_commit=%s, valid_until=%s, remark=%s,
            version=version+1, updated_by=%s, updated_at=now() WHERE id=%s
        """, (price, qty, delivery_date, p.get('deliveryPlace'), p.get('paymentTerms'),
              p.get('qualityTerms'), parse_date(p, 'validUntil', required=False) or row['valid_until'],
              p.get('remark'), g.ctx.user['id'], qid))
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
               q.pay_terms, q.valid_until, q.status
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
    if not row or row['buyer_id'] != g.ctx.company['id']:
        raise ApiError(40401, '询价单不存在')
    if datetime.now() < row['deadline']:
        raise ApiError(40901, '报价尚未截止，不可揭示')
    snapshot = json_payload(reveal_inquiry(g.conn, iid, g.ctx))
    send_msg(g.conn, row['buyer_id'], '报价已揭示',
             '询价单 %s 报价截止，共 %d 家报价，请查看比价表。' % (row['inquiry_no'], len(snapshot['rows'])),
             'INQUIRY', iid)
    return ok(snapshot)


@bp.get('/inquiries/<int:iid>/quotes/reveal')
@roles_required(ROLE_STEEL)
def get_reveal(iid):
    row = q1(g.conn, "SELECT * FROM biz_inquiry WHERE id=%s AND is_deleted=0", (iid,))
    if not row or row['buyer_id'] != g.ctx.company['id']:
        raise ApiError(40401, '询价单不存在')
    if datetime.now() < row['deadline'] and row['status'] in ('DRAFT', 'SENT', 'QUOTING'):
        raise ApiError(40901, '报价尚未截止，不可揭示')
    return ok(json_payload(reveal_inquiry(g.conn, iid, g.ctx)))


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
