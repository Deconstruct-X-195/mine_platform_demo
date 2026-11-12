"""状态机服务（PRD 4.4/T02）：全部单据状态流转集中校验，非法流转拒绝 40901。

每次流转同步写 sys_operation_log；指定 biz_type 时追加 biz_track_node 履约节点。
"""
from .common import ApiError, op_log
from .db import execute, q1

# 实体表名 → 允许的状态流转 {from: [to...]}（与 PRD 3.2 严格一致）
TRANSITIONS = {
    'biz_demand': {
        'DRAFT': ['SUBMITTED', 'WITHDRAWN'],
        'SUBMITTED': ['WITHDRAWN', 'INQUIRING', 'CLOSED'],
        'WITHDRAWN': ['SUBMITTED'],  # 撤回重提生成新版本
        'INQUIRING': ['DEALT', 'CLOSED', 'SUBMITTED'],  # SUBMITTED: 归集订单关闭后扣量释放回退
        'DEALT': ['CLOSED'],
    },
    'biz_aggregated_order': {
        'OPEN': ['INQUIRING', 'CLOSED'],   # OPEN: 已归集待询价
        'INQUIRING': ['AWARDED', 'CLOSED'],
        'AWARDED': ['CLOSED'],
    },
    'biz_demand_change': {
        'PENDING': ['APPROVED', 'REJECTED'],
    },
    'biz_inquiry': {
        'DRAFT': ['SENT'],
        'SENT': ['QUOTING', 'CLOSED', 'FAILED'],
        'QUOTING': ['CLOSED', 'FAILED'],
        'CLOSED': ['BARGAINING', 'AWARDED', 'FAILED', 'FEEDBACK'],  # FEEDBACK：钢厂不认可比价结果，待运营处理
        'FEEDBACK': ['CLOSED'],  # 运营重新发起询价后标记旧单已处理
        'BARGAINING': ['AWARDED', 'FAILED'],
        'AWARDED': ['CLOSED'],  # 订单超时失效后重新开放定标（PRD 4.5）
    },
    'biz_quote': {
        'SUBMITTED': ['REVEALED', 'REJECTED'],
        'REVEALED': ['BARGAINING', 'WIN', 'LOSE'],
        'BARGAINING': ['WIN', 'LOSE'],
        'WIN': ['SUBMITTED', 'LOSE'],  # 订单超时失效后回退/重新定标落选
    },
    'biz_bargain': {
        # PRD 4.5 字段枚举：待响应/已接受/已拒绝/已失效（3.2 中 ONGOING 等价待响应）
        'PENDING': ['ACCEPTED', 'REJECTED', 'EXPIRED'],
        'ONGOING': ['ACCEPTED', 'REJECTED', 'EXPIRED'],
    },
    'biz_order': {
        'PENDING_CONFIRM': ['PENDING_CONTRACT', 'CANCELLED'],
        'PENDING_CONTRACT': ['PENDING_EFFECT', 'CANCELLED'],
        'PENDING_EFFECT': ['PERFORMING', 'PENDING_CONTRACT', 'CANCELLED'],  # 作废合同回到待生成
        'PERFORMING': ['COMPLETED'],
    },
    'biz_contract': {
        'PENDING_GENERATE': ['PENDING_BUYER', 'VOID'],
        'PENDING_BUYER': ['PENDING_SUPPLIER', 'VOID'],
        'PENDING_SUPPLIER': ['EFFECTIVE', 'VOID'],
    },
    'biz_waybill': {
        'PENDING_ASSIGN': ['PENDING_ACCEPT', 'CANCELLED'],
        'PENDING_ACCEPT': ['PENDING_DEPART', 'CANCELLED'],
        'PENDING_DEPART': ['IN_TRANSIT'],
        'IN_TRANSIT': ['ARRIVED'],
        'ARRIVED': ['SIGNED'],
    },
    'biz_settlement': {
        'PENDING_CONFIRM_SUPPLIER': ['PENDING_CONFIRM_BUYER'],
        'PENDING_CONFIRM_BUYER': ['CONFIRMED'],
        'CONFIRMED': ['COMPLETED'],
    },
    'biz_alert': {
        'PENDING': ['PROCESSING', 'CLOSED'],
        'PROCESSING': ['CLOSED'],
    },
    'ent_company': {
        'PENDING': ['APPROVED', 'REJECTED'],
        'REJECTED': ['PENDING'],
        'APPROVED': ['PENDING'],  # 关键信息变更重新审核
    },
}

# ent_company 的状态机字段为 audit_status（status 为独立启停字段 ENABLED/DISABLED）
STATUS_COL = {'ent_company': 'audit_status'}

NODE_TITLES = {
    'ORDER': {
        'AWARDED': '定标完成',
        'ORDER_CREATED': '订单生成',
        'ORDER_CONFIRMED': '供应商确认订单',
        'ORDER_EXPIRED': '订单超时失效',
        'ORDER_CANCELLED': '订单已取消',
        'CONTRACT_GENERATED': '合同生成',
        'CONTRACT_BUYER_SIGNED': '需方签署合同',
        'CONTRACT_SIGNED': '双方签署完成',
        'CONTRACT_EFFECTIVE': '合同生效',
        'CONTRACT_VOIDED': '合同作废',
        'PLAN_CONFIGURED': '物流方案配置',
        'QUALITY_CHECKED': '到货质检完成',
        'SETTLEMENT_CREATED': '结算单生成',
        'SETTLEMENT_CONFIRMED': '结算确认完成',
        'PAYMENT_REGISTERED': '付款已登记',
        'ORDER_ARCHIVED': '订单归档完成',
        'MANUAL': '手工节点',
    },
    'WAYBILL': {
        'WB_CREATED': '运单生成',
        'WB_ASSIGNED': '已指派承运商',
        'WB_ACCEPTED': '承运商接单',
        'WB_DEPARTED': '已发运',
        'WB_ARRIVED': '已到达',
        'WB_SIGNED': '已签收',
        'MANUAL': '手工节点',
    },
    'SETTLEMENT': {
        'SETTLE_CREATED': '结算单生成',
        'SETTLE_SUPPLIER_CONFIRMED': '供应商确认结算',
        'SETTLE_BUYER_CONFIRMED': '钢厂确认结算',
        'SETTLE_PAID': '付款完成',
        'MANUAL': '手工节点',
    },
}


def assert_status(row, expected, entity='单据'):
    if row is None:
        raise ApiError(40401, '%s不存在' % entity)
    if row['status'] != expected:
        raise ApiError(40901, '%s当前状态为 %s，禁止该操作' % (entity, row['status']))


def transition(conn, ctx, table, entity_label, biz_type, biz_id, to_status, extra_sql='',
               node_biz_type=None, node_code=None, node_biz_id=None):
    """校验并执行状态流转：UPDATE + 操作日志 + 履约节点。

    跨表节点（如合同签署挂订单时间轴）须显式传 node_biz_id，避免节点错挂到
    合同/询价等实体 id 上。
    """
    id_col = {'biz_demand': 'id', 'biz_demand_change': 'id', 'biz_inquiry': 'id', 'biz_quote': 'id',
              'biz_bargain': 'id', 'biz_order': 'id', 'biz_contract': 'id', 'biz_waybill': 'id',
              'biz_settlement': 'id', 'biz_alert': 'id', 'biz_aggregated_order': 'id',
              'ent_company': 'id'}[table]
    col = STATUS_COL.get(table, 'status')
    row = q1(conn, "SELECT %s AS status FROM %s WHERE %s=%%s AND is_deleted=0" % (col, table, id_col), (biz_id,))
    if row is None:
        raise ApiError(40401, '%s不存在' % entity_label)
    frm = row['status']
    allowed = TRANSITIONS.get(table, {}).get(frm, [])
    if to_status not in allowed:
        raise ApiError(40901, '%s状态不允许从 %s 变更为 %s' % (entity_label, frm, to_status))
    sql = "UPDATE %s SET %s=%%s, updated_at=now()" % (table, col)
    args = [to_status]
    if extra_sql:
        sql += ', ' + extra_sql
    sql += ' WHERE %s=%%s' % id_col
    execute(conn, sql, args + [biz_id])
    op_log(conn, ctx, table, biz_id, 'STATUS %s->%s' % (frm, to_status), {'status': frm}, {'status': to_status})
    if node_biz_type and node_code:
        add_node(conn, ctx, node_biz_type, node_biz_id if node_biz_id is not None else biz_id,
                 node_code, occur=None, remark=to_status)
    return frm


def add_node(conn, ctx, biz_type, biz_id, node_code, occur=None, remark=None):
    """写履约节点（只增不改）。occur 为 None 时取当前时间。"""
    titles = NODE_TITLES.get(biz_type, {})
    node_name = titles.get(node_code, node_code)
    execute(
        conn,
        """
        INSERT INTO biz_track_node (biz_type, biz_id, node_code, node_name, occur_time,
                                    source, remark, created_by)
        VALUES (%s, %s, %s, %s, COALESCE(%s, now()), 'SYSTEM', %s, %s)
        """,
        (biz_type, biz_id, node_code, node_name, occur, remark, ctx.user['id'] if ctx else None),
    )
