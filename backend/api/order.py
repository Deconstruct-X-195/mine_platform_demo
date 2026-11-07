"""订单（PRD 4.5/T12）：定标生成订单、供应商 48h 确认、超时失效回退、列表与详情。

定标锁定：品种、品位、数量+溢短装、成交单价、交货方式与地点、交货期、结算方式、
质检扣罚标准；一期不支持一单拆多家。
"""
from datetime import datetime, timedelta
from decimal import Decimal

from flask import g, request

from ..common import (ApiError, doc_no, get_params, json_payload, ok, op_log,
                      page_args, page_data, require_fields, send_msg)
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
    # 成交回填明细
    if item:
        execute(g.conn, "UPDATE biz_demand_item SET deal_qty = deal_qty + %s, updated_at=now() WHERE id=%s",
                (qty, item['id']))
    # 通知供应商
    send_msg(g.conn, quote['supplier_id'], '订单待确认',
             '询价单 %s 已定标，生成订单，请在 48 小时内确认（%s 前）。' %
             (inq['inquiry_no'], (datetime.now() + timedelta(hours=48)).strftime('%Y-%m-%d %H:%M:%S')),
             'ORDER', oid)
    op_log(g.conn, g.ctx, 'biz_order', oid, 'AWARD', None,
           {'quoteId': quote['id'], 'price': str(price), 'quantity': str(qty)})
    return ok({'orderId': oid, 'confirmDeadline': (datetime.now() + timedelta(hours=48)).strftime('%Y-%m-%d %H:%M:%S')})


@bp.put('/orders/<int:oid>/confirm')
@roles_required(ROLE_SUPPLIER)
def confirm_order(oid):
    row = _own(oid, ROLE_SUPPLIER)
    if row['status'] != 'PENDING_CONFIRM':
        raise ApiError(40901, '订单状态为 %s，不可确认' % row['status'])
    if datetime.now() > row['confirm_deadline']:
        raise ApiError(40901, '已超过确认截止时间（48h）')
    transition(g.conn, g.ctx, 'biz_order', '订单', 'biz_order', oid, 'PENDING_CONTRACT',
               node_biz_type='ORDER', node_code='ORDER_CONFIRMED')
    send_msg(g.conn, row['buyer_id'], '订单已确认', '订单 %s 供应商已确认，请生成并签署合同。' % row['order_no'],
             'ORDER', oid)
    return ok({'id': oid, 'status': 'PENDING_CONTRACT'})


def _own(oid, role=None):
    row = q1(g.conn, "SELECT * FROM biz_order WHERE id=%s AND is_deleted=0", (oid,))
    if not row:
        raise ApiError(40401, '订单不存在')
    cid = g.ctx.company['id'] if g.ctx.company else None
    if not g.ctx.is_plat and cid not in (row['buyer_id'], row['supplier_id']):
        raise ApiError(40301, '无权限访问该订单')
    return row


@bp.get('/orders')
@auth_required
def list_orders():
    params = request.args.to_dict()
    page, size = page_args(params)
    where, args = 'WHERE o.is_deleted=0', []
    if not g.ctx.is_plat:
        where += ' AND (o.buyer_id=%s OR o.supplier_id=%s)'
        args += [g.ctx.company['id'] or -1, g.ctx.company['id'] or -1]
    if params.get('status'):
        where += ' AND o.status=%s'
        args.append(params['status'])
    total = q1(g.conn, 'SELECT count(*) AS c FROM biz_order o ' + where, args)['c']
    rows = qall(g.conn, """
        SELECT o.*, v.variety_name AS "varietyName",
               b.company_name AS "buyerName", s.company_name AS "supplierName"
        FROM biz_order o
        JOIN base_variety v ON v.id=o.variety_id
        LEFT JOIN ent_company b ON b.id=o.buyer_id
        LEFT JOIN ent_company s ON s.id=o.supplier_id
        %s ORDER BY o.id DESC LIMIT %%s OFFSET %%s
        """ % where, args + [size, (page - 1) * size])
    return ok(page_data(rows, total, page, size))


@bp.get('/orders/<int:oid>')
@auth_required
def order_detail(oid):
    row = _own(oid)
    data = json_payload(dict(row))
    data['varietyName'] = (q1(g.conn, "SELECT variety_name AS n FROM base_variety WHERE id=%s", (row['variety_id'],)) or {}).get('n')
    data['buyerName'] = (q1(g.conn, "SELECT company_name AS n FROM ent_company WHERE id=%s", (row['buyer_id'],)) or {}).get('n')
    data['supplierName'] = (q1(g.conn, "SELECT company_name AS n FROM ent_company WHERE id=%s", (row['supplier_id'],)) or {}).get('n')
    contracts = qall(g.conn, """
        SELECT id, contract_no AS "contractNo", version, status, file_url AS "fileUrl",
               file_hash AS "fileHash", buyer_sign_at AS "buyerSignAt", supplier_sign_at AS "supplierSignAt",
               void_reason AS "voidReason", created_at AS "createdAt"
        FROM biz_contract WHERE order_id=%s AND is_deleted=0 ORDER BY version DESC
        """, (oid,))
    data['contracts'] = json_payload(contracts)
    return ok(data)
