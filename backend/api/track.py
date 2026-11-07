"""履约时间轴（PRD 4.8/T15）：订单/运单/结算节点聚合、手工节点与纠偏。

规则：节点只增不改，纠偏用新增"纠正记录"标注原节点；source 区分 SYSTEM/CARRIER/MANUAL。
"""
from flask import g, request

from ..common import (ApiError, get_params, json_payload, ok, op_log,
                      parse_datetime, require_fields)
from ..db import qall, q1
from ..security import ROLE_STEEL, auth_required, roles_required
from ..state_machine import add_node
from . import bp


def _order_view(oid):
    row = q1(g.conn, "SELECT * FROM biz_order WHERE id=%s AND is_deleted=0", (oid,))
    if not row:
        raise ApiError(40401, '订单不存在')
    if not g.ctx.is_plat and (not g.ctx.company or
                              g.ctx.company['id'] not in (row['buyer_id'], row['supplier_id'])):
        raise ApiError(40301, '无权限访问该订单')
    return row


@bp.get('/orders/<int:oid>/timeline')
@auth_required
def timeline(oid):
    _order_view(oid)
    nodes = qall(g.conn, """
        SELECT id, biz_type AS "bizType", biz_id AS "bizId", node_code AS "nodeCode",
               node_name AS "nodeName", occur_time AS "occurTime", source, remark,
               correct_node_id AS "correctNodeId", created_at AS "createdAt"
        FROM biz_track_node
        WHERE biz_type='ORDER' AND biz_id=%s
           OR (biz_type='WAYBILL' AND biz_id IN (SELECT id FROM biz_waybill WHERE order_id=%s))
           OR (biz_type='SETTLEMENT' AND biz_id IN (SELECT id FROM biz_settlement WHERE order_id=%s))
        ORDER BY occur_time, id
        """, (oid, oid, oid))
    return ok({'list': json_payload(nodes)})


@bp.post('/orders/<int:oid>/nodes')
@roles_required(ROLE_STEEL)
def manual_node(oid):
    """手工节点/纠正记录：source=MANUAL；correctionNodeId 指向被纠正节点（只增不改）。"""
    row = _order_view(oid)
    p = get_params()
    require_fields(p, 'nodeCode')
    occur = parse_datetime(p, 'occurTime', required=False)
    correct_id = p.get('correctionNodeId')
    remark = p.get('remark') or ''
    if correct_id:
        orig = q1(g.conn, "SELECT * FROM biz_track_node WHERE id=%s", (correct_id,))
        if not orig:
            raise ApiError(40401, '被纠正节点不存在')
        remark = ('【纠正节点 %s】' % orig['node_name']) + remark
    from ..state_machine import NODE_TITLES
    name = NODE_TITLES.get(p['nodeCode'], p['nodeCode'])
    from ..db import execute
    nid = execute(g.conn, """
        INSERT INTO biz_track_node (biz_type, biz_id, node_code, node_name, occur_time,
            source, remark, correct_node_id, created_by)
        VALUES ('ORDER', %s, %s, %s, %s, 'MANUAL', %s, %s, %s) RETURNING id
        """, (oid, p['nodeCode'], name + ('（纠正）' if correct_id else ''),
              occur, remark, correct_id, g.ctx.user['id']), returning_id=True)
    op_log(g.conn, g.ctx, 'biz_track_node', nid, 'MANUAL_NODE', None, p)
    return ok({'id': nid})


@bp.post('/waybills/<int:wid>/sign')
@roles_required(ROLE_STEEL)
def sign_waybill(wid):
    """钢厂签收：ARRIVED → SIGNED（需方到货登记 FR-09-01）。"""
    row = q1(g.conn, "SELECT * FROM biz_waybill WHERE id=%s AND is_deleted=0", (wid,))
    if not row:
        raise ApiError(40401, '运单不存在')
    order = q1(g.conn, "SELECT * FROM biz_order WHERE id=%s AND is_deleted=0", (row['order_id'],))
    if not g.ctx.is_plat and (not g.ctx.company or order['buyer_id'] != g.ctx.company['id']):
        raise ApiError(40301, '只有需方钢厂可签收')
    p = get_params()
    occur = parse_datetime(p, 'occurTime', required=False)
    from ..db import execute
    from ..state_machine import transition
    transition(g.conn, g.ctx, 'biz_waybill', '运单', 'biz_waybill', wid, 'SIGNED',
               node_biz_type='WAYBILL', node_code='WAYBILL_SIGNED')
    from datetime import datetime
    execute(g.conn, """
        UPDATE biz_waybill SET actual_arrive_at=coalesce(actual_arrive_at, %s), updated_by=%s, updated_at=now() WHERE id=%s
        """, (occur or datetime.now(), g.ctx.user['id'], wid))
    op_log(g.conn, g.ctx, 'biz_waybill', wid, 'SIGN', None, p)
    return ok({'id': wid, 'status': 'SIGNED'})
