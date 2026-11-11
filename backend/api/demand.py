"""需求申报（PRD 4.2/T06）：草稿增改、明细维护、提交、撤回、关闭、脱敏需求池。

规则：提交后品种/数量/交货条件/到货时间锁定；被询价引用的需求不可撤回只能关闭；
供应商只见脱敏概要（品种、数量区间、交货区域、期望月份），看不到钢厂名称与价格意向。
"""
from flask import g, request

from ..common import (ApiError, doc_no, get_params, json_payload, ok, op_log,
                      page_args, page_data, parse_date, require_fields)
from ..db import execute, qall, q1
from ..security import ROLE_CARRIER, ROLE_STEEL, ROLE_SUPPLIER, auth_required
from ..state_machine import assert_status, transition
from . import bp


def _save_items(conn, demand_id, items, user_id):
    execute(conn, "DELETE FROM biz_demand_item WHERE demand_id=%s", (demand_id,))
    for it in items:
        require_fields(it, 'varietyId', 'grade', 'quantity')
        v = q1(conn, "SELECT id FROM base_variety WHERE id=%s AND is_deleted=0", (it['varietyId'],))
        if not v:
            raise ApiError(40401, '品种不存在：%s' % it['varietyId'])
        qty = _num(it['quantity'], 'quantity')
        if qty <= 0:
            raise ApiError(40001, '数量必须大于0')
        rate = _num(it.get('moreLessRate') or 5, 'moreLessRate')
        execute(conn, """
            INSERT INTO biz_demand_item (demand_id, variety_id, grade, quantity, more_less_rate, created_by)
            VALUES (%s,%s,%s,%s,%s,%s)
            """, (demand_id, it['varietyId'], _num(it['grade'], 'grade'), qty, rate, user_id))


def _num(v, name):
    from decimal import Decimal, InvalidOperation
    try:
        return Decimal(str(v))
    except (InvalidOperation, TypeError, ValueError):
        raise ApiError(40001, '数值格式错误：%s' % name)


@bp.post('/demands')
@auth_required
def create_demand():
    if not g.ctx.has_role(ROLE_STEEL):
        raise ApiError(40301, '仅钢厂可创建需求')
    p = get_params()
    _validate_demand(p)
    did = execute(g.conn, """
        INSERT INTO biz_demand (demand_no, company_id, demand_name, delivery_type, delivery_place,
                                expect_arrive_start, expect_arrive_end, price_intent, settle_type,
                                quality_req, remark, status, created_by, updated_by)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'DRAFT',%s,%s) RETURNING id
        """, (doc_no(g.conn, 'XQ'), g.ctx.company['id'], p['demandName'], p['deliveryType'],
              p['deliveryPlace'], parse_date(p, 'expectArriveStart'), parse_date(p, 'expectArriveEnd'),
              p.get('priceIntent'), p['settleType'], p.get('qualityReq'),
              p.get('remark'), g.ctx.user['id'], g.ctx.user['id']), returning_id=True)
    _save_items(g.conn, did, p.get('items') or [], g.ctx.user['id'])
    op_log(g.conn, g.ctx, 'biz_demand', did, 'CREATE', None, {'demandName': p['demandName']})
    return ok({'id': did, 'status': 'DRAFT'})


def _validate_demand(p):
    require_fields(p, 'demandName', 'deliveryType', 'deliveryPlace',
                   'expectArriveStart', 'expectArriveEnd', 'settleType')
    if len(str(p['demandName'])) > 50:
        raise ApiError(40001, '需求名称不超过50字')
    if p.get('deliveryType') not in ('PORT_FOB', 'PORT_TRUCK', 'PLANT'):
        raise ApiError(40001, '交货方式不合法（PORT_FOB/PORT_TRUCK/PLANT）')
    start = parse_date(p, 'expectArriveStart')
    end = parse_date(p, 'expectArriveEnd')
    if end < start:
        raise ApiError(40001, '期望到货结束日期不能早于开始日期')
    if p.get('settleType') not in ('PREPAY', 'COD', 'CREDIT'):
        raise ApiError(40001, '结算方式不合法（PREPAY/COD/CREDIT，账期天数放 settleDays）')
    if p.get('remark') and len(str(p['remark'])) > 500:
        raise ApiError(40001, '备注不超过500字')


@bp.put('/demands/<int:did>')
@auth_required
def update_demand(did):
    row = _own_demand(did)
    assert_status(row, 'DRAFT', '需求单')
    p = get_params()
    _validate_demand(p)
    execute(g.conn, """
        UPDATE biz_demand SET demand_name=%s, delivery_type=%s, delivery_place=%s,
            expect_arrive_start=%s, expect_arrive_end=%s, price_intent=%s, settle_type=%s,
            quality_req=%s, remark=%s, updated_by=%s, updated_at=now()
        WHERE id=%s
        """, (p['demandName'], p['deliveryType'], p['deliveryPlace'],
              parse_date(p, 'expectArriveStart'), parse_date(p, 'expectArriveEnd'),
              p.get('priceIntent'), p['settleType'], p.get('qualityReq'),
              p.get('remark'), g.ctx.user['id'], did))
    _save_items(g.conn, did, p.get('items') or [], g.ctx.user['id'])
    op_log(g.conn, g.ctx, 'biz_demand', did, 'UPDATE', None, {'demandName': p['demandName']})
    return ok({'id': did})


@bp.post('/demands/<int:did>/submit')
@auth_required
def submit_demand(did):
    row = _own_demand(did)
    if row['status'] not in ('DRAFT', 'WITHDRAWN'):
        raise ApiError(40901, '需求单当前状态为 %s，禁止提交' % row['status'])
    items = qall(g.conn, "SELECT * FROM biz_demand_item WHERE demand_id=%s AND is_deleted=0", (did,))
    if not items:
        raise ApiError(40001, '需求至少需要一条明细')
    frm = row['status']
    to_version = row['version'] + 1 if frm == 'WITHDRAWN' else row['version']
    execute(g.conn, """
        UPDATE biz_demand SET status='SUBMITTED', version=%s, submitted_at=now(),
               updated_by=%s, updated_at=now() WHERE id=%s
        """, (to_version, g.ctx.user['id'], did))
    op_log(g.conn, g.ctx, 'biz_demand', did, 'STATUS %s->SUBMITTED' % frm,
           {'status': frm, 'version': row['version']}, {'status': 'SUBMITTED', 'version': to_version})
    return ok({'id': did, 'status': 'SUBMITTED', 'version': to_version})


@bp.post('/demands/<int:did>/withdraw')
@auth_required
def withdraw_demand(did):
    row = _own_demand(did)
    assert_status(row, 'SUBMITTED', '需求单')
    ref = q1(g.conn, "SELECT id FROM biz_inquiry WHERE demand_id=%s AND is_deleted=0 LIMIT 1", (did,))
    if ref:
        raise ApiError(40901, '需求已被询价引用，不可撤回，只能关闭')
    transition(g.conn, g.ctx, 'biz_demand', '需求单', 'biz_demand', did, 'WITHDRAWN')
    return ok({'id': did, 'status': 'WITHDRAWN'})


@bp.post('/demands/<int:did>/close')
@auth_required
def close_demand(did):
    row = _own_demand(did)
    p = get_params()
    require_fields(p, 'reason')
    frm = row['status']
    if frm not in ('SUBMITTED', 'INQUIRING', 'DEALT'):
        raise ApiError(40901, '需求单当前状态为 %s，禁止关闭' % frm)
    execute(g.conn, """
        UPDATE biz_demand SET status='CLOSED', remark=concat_ws(' | ', remark, %s),
               updated_by=%s, updated_at=now() WHERE id=%s
        """, ('关闭原因：' + p['reason'], g.ctx.user['id'], did))
    op_log(g.conn, g.ctx, 'biz_demand', did, 'STATUS %s->CLOSED' % frm,
           {'status': frm}, {'status': 'CLOSED', 'reason': p['reason']})
    return ok({'id': did, 'status': 'CLOSED'})


def _own_demand(did):
    row = q1(g.conn, "SELECT * FROM biz_demand WHERE id=%s AND is_deleted=0", (did,))
    if not row:
        raise ApiError(40401, '需求单不存在')
    if not g.ctx.is_plat and row['company_id'] != g.ctx.company['id']:
        raise ApiError(40301, '无权限操作该需求单')
    return row


def _mask_demand(row):
    """脱敏概要：品种、数量区间、交货区域、期望月份（PRD 4.2）。"""
    items = qall(g.conn, """
        SELECT i.id, v.variety_name AS "varietyName", i.grade, i.quantity, i.more_less_rate AS "moreLessRate",
               i.quantity - i.inquired_qty AS "remainQty"
        FROM biz_demand_item i JOIN base_variety v ON v.id=i.variety_id
        WHERE i.demand_id=%s AND i.is_deleted=0 ORDER BY i.id
        """, (row['id'],))
    total = sum(i['quantity'] for i in items) if items else 0
    return {
        'id': row['id'], 'demandNo': row['demand_no'],
        'items': json_payload(items),
        'totalQty': str(total),
        'deliveryType': row['delivery_type'],
        'deliveryRegion': row['delivery_place'],
        'expectMonth': (row['expect_arrive_start'].strftime('%Y-%m') if row['expect_arrive_start'] else None),
        'createdAt': row['created_at'],
    }


@bp.get('/demands')
@auth_required
def demand_list():
    params = request.args.to_dict()
    page, size = page_args(params)
    if g.ctx.has_role(ROLE_STEEL):
        return _own_demand_list(params, page, size)
    # 供应商/物流/其他：只看已提交需求池的脱敏概要
    where = "WHERE d.status='SUBMITTED' AND d.is_deleted=0"
    args = []
    if params.get('varietyId'):
        where += (' AND EXISTS (SELECT 1 FROM biz_demand_item i '
                  'WHERE i.demand_id=d.id AND i.variety_id=%s AND i.is_deleted=0)')
        args.append(params['varietyId'])
    total = q1(g.conn, 'SELECT count(*) AS c FROM biz_demand d ' + where, args)['c']
    rows = qall(g.conn, 'SELECT d.* FROM biz_demand d ' + where +
                ' ORDER BY d.id DESC LIMIT %s OFFSET %s', args + [size, (page - 1) * size])
    return ok(page_data([_mask_demand(r) for r in rows], total, page, size))


def _own_demand_list(params, page, size):
    where = 'WHERE company_id=%s AND is_deleted=0'
    args = [g.ctx.company['id']]
    if params.get('status'):
        where += ' AND status=%s'
        args.append(params['status'])
    total = q1(g.conn, 'SELECT count(*) AS c FROM biz_demand ' + where, args)['c']
    rows = qall(g.conn, """
        SELECT * FROM biz_demand %s ORDER BY id DESC LIMIT %%s OFFSET %%s
        """ % where, args + [size, (page - 1) * size])
    out = []
    for r in rows:
        d = json_payload(dict(r))
        d['items'] = json_payload(qall(g.conn, """
            SELECT i.id, i.variety_id AS "varietyId", v.variety_name AS "varietyName", i.grade,
                   i.quantity, i.more_less_rate AS "moreLessRate", i.inquired_qty AS "inquiredQty",
                   i.quantity - i.inquired_qty AS "remainQty", i.deal_qty AS "dealQty"
            FROM biz_demand_item i JOIN base_variety v ON v.id=i.variety_id
            WHERE i.demand_id=%s AND i.is_deleted=0 ORDER BY i.id
            """, (r['id'],)))
        out.append(d)
    return ok(page_data(out, total, page, size))


@bp.get('/demands/<int:did>')
@auth_required
def demand_detail(did):
    row = q1(g.conn, "SELECT * FROM biz_demand WHERE id=%s AND is_deleted=0", (did,))
    if not row:
        raise ApiError(40401, '需求单不存在')
    if g.ctx.is_plat or (g.ctx.company and row['company_id'] == g.ctx.company['id']):
        d = json_payload(dict(row))
        d['items'] = json_payload(qall(g.conn, """
            SELECT i.id, i.variety_id AS "varietyId", v.variety_name AS "varietyName", i.grade,
                   i.quantity, i.more_less_rate AS "moreLessRate", i.inquired_qty AS "inquiredQty",
                   i.quantity - i.inquired_qty AS "remainQty", i.deal_qty AS "dealQty"
            FROM biz_demand_item i JOIN base_variety v ON v.id=i.variety_id
            WHERE i.demand_id=%s AND i.is_deleted=0 ORDER BY i.id
            """, (did,)))
        return ok(d)
    if row['status'] == 'SUBMITTED':
        return ok(_mask_demand(row))
    raise ApiError(40301, '无权限查看该需求单')
