"""物流选型与调度（PRD 4.7/T14）：方案配置、分段运单、承运商指派/接单、节点回填。

规则：仅生效合同对应订单可配置；分段计划量合计与订单数量偏差 >5% 需填写说明；
承运商只能操作本企业运单；运费仅记录不参与结算。
"""
from flask import g, request

from ..common import (ApiError, doc_no, get_params, json_payload, ok, op_log,
                      page_args, page_data, parse_date, parse_datetime,
                      require_fields, send_msg)
from ..db import execute, qall, q1
from ..security import ROLE_CARRIER, ROLE_STEEL, auth_required, roles_required
from ..state_machine import transition
from . import bp


def _order_for_logistics(oid):
    row = q1(g.conn, "SELECT * FROM biz_order WHERE id=%s AND is_deleted=0", (oid,))
    if not row:
        raise ApiError(40401, '订单不存在')
    if row['status'] != 'PERFORMING':
        raise ApiError(40901, '仅生效合同对应的履约中订单可配置物流（当前 %s）' % row['status'])
    return row


@bp.post('/orders/<int:oid>/logistics-plan')
@roles_required(ROLE_STEEL)
def create_plan(oid):
    row = _order_for_logistics(oid)
    if q1(g.conn, "SELECT id FROM biz_logistics_plan WHERE order_id=%s AND is_deleted=0", (oid,)):
        raise ApiError(40902, '该订单已存在物流方案')
    p = get_params()
    require_fields(p, 'orgMode')
    if p['orgMode'] not in ('SELF', 'PLATFORM'):
        raise ApiError(40001, '组织方式仅支持 SELF/PLATFORM')
    pid = execute(g.conn, """
        INSERT INTO biz_logistics_plan (plan_no, order_id, org_mode, remark, created_by, updated_by)
        VALUES (%s,%s,%s,%s,%s,%s) RETURNING id
        """, (doc_no(g.conn, 'WL'), oid, p['orgMode'], p.get('remark'),
              g.ctx.user['id'], g.ctx.user['id']), returning_id=True)
    op_log(g.conn, g.ctx, 'biz_logistics_plan', pid, 'CREATE', None, p)
    return ok({'planId': pid, 'planNo': None})


@bp.get('/orders/<int:oid>/logistics-plan')
@auth_required
def get_plan(oid):
    """订单物流方案查询（前端 P.logistics 用）：无方案返回 null，有则校验双方可见性。"""
    order = q1(g.conn, "SELECT id, buyer_id, supplier_id FROM biz_order WHERE id=%s AND is_deleted=0", (oid,))
    if not order:
        raise ApiError(40401, '订单不存在')
    if not g.ctx.is_plat and (not g.ctx.company or
                              g.ctx.company['id'] not in (order['buyer_id'], order['supplier_id'])):
        raise ApiError(40301, '无权限访问该订单')
    row = q1(g.conn, "SELECT * FROM biz_logistics_plan WHERE order_id=%s AND is_deleted=0", (oid,))
    if not row:
        return ok(None)
    return ok(json_payload(dict(row)))


def _segment_total(order_id, exclude_waybill=None):
    row = q1(g.conn, """
        SELECT coalesce(sum(plan_qty),0) AS t FROM biz_waybill
        WHERE order_id=%s AND is_deleted=0 AND status<>'CANCELLED'
        """, (order_id,))
    return row['t']


@bp.post('/logistics-plans/<int:pid>/waybills')
@roles_required(ROLE_STEEL)
def create_waybill(pid):
    plan = q1(g.conn, """
        SELECT p.*, o.quantity AS order_qty, o.id AS oid
        FROM biz_logistics_plan p JOIN biz_order o ON o.id=p.order_id
        WHERE p.id=%s AND p.is_deleted=0
        """, (pid,))
    if not plan:
        raise ApiError(40401, '物流方案不存在')
    if not q1(g.conn, "SELECT id FROM biz_order WHERE id=%s AND status='PERFORMING' AND is_deleted=0", (plan['order_id'],)):
        raise ApiError(40901, '订单不在履约中，不可创建运单')
    p = get_params()
    require_fields(p, 'segmentNo', 'transportMode', 'planQty', 'planDepartDate', 'planArriveDate')
    if p['transportMode'] not in ('SEA', 'RAIL', 'ROAD', 'MULTIMODAL'):
        raise ApiError(40001, '运输方式仅支持 SEA/RAIL/ROAD/MULTIMODAL')
    if parse_date(p, 'planArriveDate') < parse_date(p, 'planDepartDate'):
        raise ApiError(40001, '计划到达日不能早于计划发运日')
    plan_qty = p['planQty']
    if plan_qty <= 0:
        raise ApiError(40001, '计划量必须大于0')
    # 分段合计与订单数量偏差 >5% 需填说明（PRD 4.7）
    dup = q1(g.conn, "SELECT id FROM biz_waybill WHERE plan_id=%s AND segment_no=%s AND is_deleted=0",
             (pid, p['segmentNo']))
    if dup:
        raise ApiError(40902, '分段序号 %s 已存在' % p['segmentNo'])
    new_total = _segment_total(plan['order_id']) + plan_qty
    deviation = abs(new_total - plan['order_qty']) / plan['order_qty'] * 100
    if deviation > 5 and not (p.get('deviationReason') or '').strip():
        raise ApiError(40001, '分段计划量合计与订单数量偏差 %.2f%% 超过 5%%，必须填写偏差说明' % deviation)

    carrier_id = p.get('carrierId')
    if carrier_id:
        _check_carrier(carrier_id)
        status = 'PENDING_ACCEPT'
    else:
        status = 'PENDING_ASSIGN'
    wid = execute(g.conn, """
        INSERT INTO biz_waybill (waybill_no, order_id, plan_id, segment_no, carrier_id, transport_mode,
            depart_place, arrive_place, plan_depart_date, plan_arrive_date, plan_qty, freight,
            vehicle_no, status, created_by, updated_by)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id
        """, (doc_no(g.conn, 'YD'), plan['order_id'], pid, p['segmentNo'], carrier_id,
              p['transportMode'], p.get('departPlace'), p.get('arrivePlace'),
              parse_date(p, 'planDepartDate'), parse_date(p, 'planArriveDate'), plan_qty,
              p.get('freight'), p.get('vehicleNo'), status, g.ctx.user['id'], g.ctx.user['id']),
        returning_id=True)
    if deviation > 5:
        op_log(g.conn, g.ctx, 'biz_waybill', wid, 'DEVIATION', None,
               {'deviationRate': '%.2f%%' % deviation, 'reason': p.get('deviationReason')})
    if status == 'PENDING_ACCEPT' and carrier_id:
        send_msg(g.conn, carrier_id, '运单待接单', '运单已指派，请接单确认。', 'WAYBILL', wid)
    op_log(g.conn, g.ctx, 'biz_waybill', wid, 'CREATE', None, {'planQty': str(plan_qty), 'status': status})
    return ok({'id': wid, 'status': status, 'planTotalDeviation': '%.2f%%' % deviation})


def _check_carrier(cid):
    row = q1(g.conn, """
        SELECT id FROM ent_company WHERE id=%s AND audit_status='APPROVED' AND status='ENABLED'
        AND ',' || company_types || ',' LIKE '%%,LOGISTICS,%%' AND is_deleted=0
        """, (cid,))
    if not row:
        raise ApiError(40001, '承运商不存在或未准入物流角色')


@bp.put('/waybills/<int:wid>/assign')
@roles_required(ROLE_STEEL)
def assign_waybill(wid):
    p = get_params()
    require_fields(p, 'carrierId')
    _check_carrier(p['carrierId'])
    row = q1(g.conn, "SELECT * FROM biz_waybill WHERE id=%s AND is_deleted=0", (wid,))
    if not row:
        raise ApiError(40401, '运单不存在')
    if row['status'] != 'PENDING_ASSIGN':
        raise ApiError(40901, '运单状态为 %s，不可指派' % row['status'])
    execute(g.conn, "UPDATE biz_waybill SET carrier_id=%s, status='PENDING_ACCEPT', updated_by=%s, updated_at=now() WHERE id=%s",
            (p['carrierId'], g.ctx.user['id'], wid))
    send_msg(g.conn, p['carrierId'], '运单待接单', '运单 %s 已指派给贵司，请接单确认。' % row['waybill_no'], 'WAYBILL', wid)
    op_log(g.conn, g.ctx, 'biz_waybill', wid, 'ASSIGN', None, {'carrierId': p['carrierId']})
    return ok({'id': wid, 'status': 'PENDING_ACCEPT'})


def _carrier_own(wid):
    row = q1(g.conn, "SELECT * FROM biz_waybill WHERE id=%s AND is_deleted=0", (wid,))
    if not row:
        raise ApiError(40401, '运单不存在')
    if not g.ctx.is_plat and (not g.ctx.company or row['carrier_id'] != g.ctx.company['id']):
        raise ApiError(40301, '承运商只能操作本企业运单')
    return row


@bp.put('/waybills/<int:wid>/accept')
@roles_required(ROLE_CARRIER)
def accept_waybill(wid):
    row = _carrier_own(wid)
    transition(g.conn, g.ctx, 'biz_waybill', '运单', 'biz_waybill', wid, 'PENDING_DEPART',
               node_biz_type='WAYBILL', node_code='WAYBILL_ACCEPTED')
    return ok({'id': wid, 'status': 'PENDING_DEPART'})


@bp.put('/waybills/<int:wid>/node')
@roles_required(ROLE_CARRIER)
def waybill_node(wid):
    """承运商节点回填：DEPART（发运）/ARRIVE（到达）。SIGN 由钢厂触发。"""
    row = _carrier_own(wid)
    p = get_params()
    require_fields(p, 'node')
    node = p['node']
    occur = parse_datetime(p, 'occurTime', required=False) or None
    if node == 'DEPART':
        if row['status'] != 'PENDING_DEPART':
            raise ApiError(40901, '运单状态为 %s，不可回填发运' % row['status'])
        transition(g.conn, g.ctx, 'biz_waybill', '运单', 'biz_waybill', wid, 'IN_TRANSIT',
                   node_biz_type='WAYBILL', node_code='WAYBILL_DEPARTED')
        execute(g.conn, """
            UPDATE biz_waybill SET actual_depart_at=%s,
                actual_qty=%s, updated_by=%s, updated_at=now() WHERE id=%s
            """, (occur, p.get('actualQty') or row['plan_qty'], g.ctx.user['id'], wid))
    elif node == 'ARRIVE':
        if row['status'] != 'IN_TRANSIT':
            raise ApiError(40901, '运单状态为 %s，不可回填到达' % row['status'])
        transition(g.conn, g.ctx, 'biz_waybill', '运单', 'biz_waybill', wid, 'ARRIVED',
                   node_biz_type='WAYBILL', node_code='WAYBILL_ARRIVED')
        execute(g.conn, """
            UPDATE biz_waybill SET actual_arrive_at=%s, updated_by=%s, updated_at=now() WHERE id=%s
            """, (occur, g.ctx.user['id'], wid))
    else:
        raise ApiError(40001, '承运商仅可回填 DEPART/ARRIVE 节点')
    op_log(g.conn, g.ctx, 'biz_waybill', wid, 'NODE %s' % node, None, p)
    return ok({'id': wid, 'node': node})


@bp.get('/waybills')
@auth_required
def list_waybills():
    params = request.args.to_dict()
    page, size = page_args(params)
    where, args = 'WHERE w.is_deleted=0', []
    if g.ctx.is_plat:
        pass
    elif g.ctx.has_role(ROLE_CARRIER):
        where += ' AND w.carrier_id=%s'
        args.append(g.ctx.company['id'] or -1)
    else:
        where += """ AND w.order_id IN (SELECT id FROM biz_order
                     WHERE buyer_id=%s OR supplier_id=%s)"""
        args += [g.ctx.company['id'] or -1, g.ctx.company['id'] or -1]
    if params.get('orderId'):
        where += ' AND w.order_id=%s'
        args.append(params['orderId'])
    if params.get('status'):
        where += ' AND w.status=%s'
        args.append(params['status'])
    total = q1(g.conn, 'SELECT count(*) AS c FROM biz_waybill w ' + where, args)['c']
    rows = qall(g.conn, """
        SELECT w.*, o.order_no AS "orderNo", c.company_name AS "carrierName"
        FROM biz_waybill w JOIN biz_order o ON o.id=w.order_id
        LEFT JOIN ent_company c ON c.id=w.carrier_id
        %s ORDER BY w.id DESC LIMIT %%s OFFSET %%s
        """ % where, args + [size, (page - 1) * size])
    return ok(page_data(rows, total, page, size))


@bp.get('/waybills/<int:wid>')
@auth_required
def waybill_detail(wid):
    row = q1(g.conn, """
        SELECT w.*, o.order_no AS "orderNo", c.company_name AS "carrierName"
        FROM biz_waybill w JOIN biz_order o ON o.id=w.order_id
        LEFT JOIN ent_company c ON c.id=w.carrier_id
        WHERE w.id=%s AND w.is_deleted=0
        """, (wid,))
    if not row:
        raise ApiError(40401, '运单不存在')
    if not g.ctx.is_plat and g.ctx.company:
        order = q1(g.conn, "SELECT buyer_id, supplier_id FROM biz_order WHERE id=%s", (row['order_id'],))
        if g.ctx.company['id'] not in (row['carrier_id'], order['buyer_id'], order['supplier_id']):
            raise ApiError(40301, '无权限查看该运单')
    return ok(json_payload(dict(row)))
