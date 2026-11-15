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
                     '订单 %s 供应商已确认，贵司份额 %s 吨，请在「订单」页提交提货计划（开始提货日期、日提货吨数）。'
                     % (row['order_no'], format(m['quantity'], '.3f')), 'ORDER', oid)
    else:
        send_msg(g.conn, row['buyer_id'], '订单已确认', '订单 %s 供应商已确认，请生成并签署合同。' % row['order_no'],
                 'ORDER', oid)
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
               (SELECT m.quantity FROM biz_order_member m
                 WHERE m.order_id=o.id AND m.company_id=%%s AND m.is_deleted=0 LIMIT 1) AS "myQty",
               (SELECT m.pickup_status FROM biz_order_member m
                 WHERE m.order_id=o.id AND m.company_id=%%s AND m.is_deleted=0 LIMIT 1) AS "myPickupStatus"
        FROM biz_order o
        JOIN base_variety v ON v.id=o.variety_id
        LEFT JOIN ent_company b ON b.id=o.buyer_id
        LEFT JOIN ent_company s ON s.id=o.supplier_id
        %s ORDER BY o.id DESC LIMIT %%s OFFSET %%s
        """ % where, [cid, cid] + args + [size, (page - 1) * size])
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
             '订单 %s：%s 已提交提货计划（%s 起，日提货 %s 吨）。'
             % (row['order_no'], g.ctx.company['company_name'],
                start.strftime('%Y-%m-%d'), format(daily, 'f')), 'ORDER', oid)
    op_log(g.conn, g.ctx, 'biz_order', oid, 'PICKUP_PLAN', None,
           {'startDate': str(start), 'dailyQty': str(daily), 'remark': remark})
    return ok({'orderId': oid, 'pickupStatus': 'SUBMITTED', 'orderStatus': status,
               'pendingMills': pending})


@bp.get('/buyer/overview')
@roles_required(ROLE_STEEL)
def buyer_overview():
    """钢厂端总览：KPI 面板 + 采购全流程各阶段计数 + 最新采购订单（滚动列表）。"""
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

    # 最新 20 条采购订单（滚动列表）
    orders = qall(g.conn, """
        SELECT o.id, o.order_no, v.variety_name AS "varietyName", o.grade,
               o.quantity, o.unit_price, o.amount, o.delivery_date, o.status,
               s.company_name AS "supplierName",
               (SELECT m.quantity FROM biz_order_member m
                 WHERE m.order_id=o.id AND m.company_id=%s AND m.is_deleted=0 LIMIT 1) AS "myQty"
        FROM biz_order o
        JOIN base_variety v ON v.id=o.variety_id
        LEFT JOIN ent_company s ON s.id=o.supplier_id
        WHERE o.is_deleted=0 AND """ + own + " ORDER BY o.id DESC LIMIT 20",
        [cid] + oa)
    return ok({'kpi': kpi, 'flow': flow, 'orders': orders})


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
        'totalAmount': str(q1(g.conn, 'SELECT COALESCE(SUM(o.amount),0) AS s FROM biz_order o'
                              ' WHERE o.is_deleted=0 AND o.supplier_id=%s', (cid,))['s']),
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
        todos.append({'kind': 'QUOTE', 'main': '询价单 %s 待报价（%s，%s 吨，%s 截止）' % (
            r['inquiry_no'], r['varietyName'], r['quantity'],
            r['deadline'].strftime('%m-%d %H:%M') if r['deadline'] else '-')})
    for r in qall(g.conn, """
            SELECT o.id, o.order_no, o.created_at FROM biz_order o
            WHERE o.is_deleted=0 AND o.supplier_id=%s AND o.status='PENDING_CONFIRM'
            ORDER BY o.id DESC LIMIT 20""", (cid,)):
        todos.append({'kind': 'CONFIRM', 'main': '订单 %s 待确认（48 小时期限内）' % r['order_no'],
                      'time': r['created_at']})

    # 近期动态：本企业站内消息最近 10 条
    recent = qall(g.conn, """
        SELECT id, title, content, biz_type AS "bizType", biz_id AS "bizId",
               msg_category AS "category", created_at
        FROM sys_message WHERE receiver_company_id=%s ORDER BY id DESC LIMIT 10""", (cid,))
    return ok({'kpi': kpi, 'todos': todos, 'recent': recent})
