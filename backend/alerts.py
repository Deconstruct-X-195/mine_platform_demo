"""预警中心（PRD 4.8）：五类预警的生成（去重）、自动关闭、人工处理。

五类：OVERDUE_DEPART 超期未发运 / TRANSIT_TIMEOUT 在途超时 / QTY_DIFF 数量差异 /
CONTRACT_SIGN_DELAY 合同逾期未签 / SETTLE_CONFIRM_DELAY 结算逾期未确认。
去重：同对象同类型仅保留一条未关闭预警（部分唯一索引）。
"""
from .common import doc_no, send_msg
from .db import execute, q1, qall

ALERT_CONTENT = {
    'OVERDUE_DEPART': '运单超期未发运，请尽快安排发运或联系承运商',
    'TRANSIT_TIMEOUT': '运单在途超过计划到达时间，请关注到货进度',
    'QTY_DIFF': '到货数量与订单数量偏差超过允差范围，请双方确认处理意见',
    'CONTRACT_SIGN_DELAY': '合同待签署已超过 3 日，请尽快完成签署',
    'SETTLE_CONFIRM_DELAY': '结算单待确认已超过 5 日，请尽快完成确认',
}


def create_alert(conn, alert_type, biz_type, biz_id, company_ids, content=None):
    """生成预警（去重：已有未关闭同类型同对象预警则跳过）。"""
    row = q1(
        conn,
        """
        INSERT INTO biz_alert (alert_no, alert_type, biz_type, biz_id, company_ids, content)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (alert_type, biz_type, biz_id) WHERE status IN ('PENDING','PROCESSING') AND is_deleted = 0
        DO NOTHING
        RETURNING id
        """,
        (doc_no(conn, 'YJ'), alert_type, biz_type, biz_id,
         ','.join(str(c) for c in company_ids or []), content or ALERT_CONTENT.get(alert_type, '')),
    )
    if row:
        for cid in company_ids or []:
            send_msg(conn, cid, '预警提醒：%s' % alert_type, ALERT_CONTENT.get(alert_type, ''),
                     'ALERT', row['id'])
    return row['id'] if row else None


def close_alert(conn, alert_type, biz_type, biz_id, handler_id=None, remark=None):
    """自动/人工关闭预警。"""
    return execute(
        conn,
        """
        UPDATE biz_alert SET status='CLOSED', handler_id=COALESCE(%s, handler_id),
               handler_remark=COALESCE(%s, handler_remark), handled_at=now(), updated_at=now()
        WHERE alert_type=%s AND biz_type=%s AND biz_id=%s AND status IN ('PENDING','PROCESSING') AND is_deleted=0
        """,
        (handler_id, remark, alert_type, biz_type, biz_id),
    )


def scan_alerts(conn, now=None):
    """定时扫描（小时级）：对满足条件的对象生成预警、自动关闭已解除的预警。"""
    created = 0
    # 1. 超期未发运：计划发运时间+24h 仍未发运
    rows = qall(conn, """
        SELECT w.id, w.order_id, w.carrier_id, o.buyer_id
        FROM biz_waybill w JOIN biz_order o ON o.id = w.order_id
        WHERE w.is_deleted=0 AND o.is_deleted=0
          AND w.status NOT IN ('IN_TRANSIT','ARRIVED','SIGNED')
          AND w.plan_depart_date IS NOT NULL
          AND (w.plan_depart_date + interval '1 day') < %s
    """, (now,))
    for w in rows:
        if create_alert(conn, 'OVERDUE_DEPART', 'WAYBILL', w['id'], [w['buyer_id'], w['carrier_id']]):
            created += 1
    # 自动关闭：已发运
    execute(conn, """
        UPDATE biz_alert a SET status='CLOSED', handled_at=now(), updated_at=now(),
               handler_remark='发运时间已更新，自动解除'
        WHERE a.alert_type='OVERDUE_DEPART' AND a.status IN ('PENDING','PROCESSING')
          AND EXISTS (SELECT 1 FROM biz_waybill w
                      WHERE w.id=a.biz_id AND w.actual_depart_at IS NOT NULL)
    """)
    # 2. 在途超时：计划到达日期已过仍未到达
    rows = qall(conn, """
        SELECT w.id, w.order_id, w.carrier_id, o.buyer_id
        FROM biz_waybill w JOIN biz_order o ON o.id = w.order_id
        WHERE w.is_deleted=0 AND o.is_deleted=0
          AND w.status NOT IN ('ARRIVED','SIGNED')
          AND w.plan_arrive_date IS NOT NULL AND w.plan_arrive_date < %s::date
    """, (now,))
    for w in rows:
        if create_alert(conn, 'TRANSIT_TIMEOUT', 'WAYBILL', w['id'], [w['buyer_id'], w['carrier_id']]):
            created += 1
    execute(conn, """
        UPDATE biz_alert a SET status='CLOSED', handled_at=now(), updated_at=now(),
               handler_remark='已回填到达时间，自动解除'
        WHERE a.alert_type='TRANSIT_TIMEOUT' AND a.status IN ('PENDING','PROCESSING')
          AND EXISTS (SELECT 1 FROM biz_waybill w
                      WHERE w.id=a.biz_id AND w.actual_arrive_at IS NOT NULL)
    """)
    # 3. 合同逾期未签：待签超 3 日
    rows = qall(conn, """
        SELECT c.id, c.order_id, o.buyer_id, o.supplier_id
        FROM biz_contract c JOIN biz_order o ON o.id = c.order_id
        WHERE c.is_deleted=0 AND o.is_deleted=0
          AND c.status IN ('PENDING_BUYER','PENDING_SUPPLIER')
          AND c.created_at < %s - interval '3 days'
    """, (now,))
    for c in rows:
        if create_alert(conn, 'CONTRACT_SIGN_DELAY', 'ORDER', c['order_id'], [c['buyer_id'], c['supplier_id']]):
            created += 1
    execute(conn, """
        UPDATE biz_alert a SET status='CLOSED', handled_at=now(), updated_at=now(),
               handler_remark='合同已生效或失效，自动解除'
        WHERE a.alert_type='CONTRACT_SIGN_DELAY' AND a.status IN ('PENDING','PROCESSING')
          AND EXISTS (
            SELECT 1 FROM biz_order o WHERE o.id=a.biz_id AND o.status NOT IN
              ('PENDING_EFFECT','PENDING_CONTRACT'))
    """)
    # 4. 结算逾期未确认：待确认超 5 日
    rows = qall(conn, """
        SELECT s.id, s.order_id, o.buyer_id, o.supplier_id
        FROM biz_settlement s JOIN biz_order o ON o.id = s.order_id
        WHERE s.is_deleted=0 AND o.is_deleted=0
          AND s.status IN ('PENDING_CONFIRM_SUPPLIER','PENDING_CONFIRM_BUYER')
          AND s.created_at < %s - interval '5 days'
    """, (now,))
    for s in rows:
        if create_alert(conn, 'SETTLE_CONFIRM_DELAY', 'ORDER', s['order_id'], [s['buyer_id'], s['supplier_id']]):
            created += 1
    execute(conn, """
        UPDATE biz_alert a SET status='CLOSED', handled_at=now(), updated_at=now(),
               handler_remark='结算已确认，自动解除'
        WHERE a.alert_type='SETTLE_CONFIRM_DELAY' AND a.status IN ('PENDING','PROCESSING')
          AND EXISTS (SELECT 1 FROM biz_settlement s WHERE s.id=a.biz_id AND s.status NOT LIKE 'PENDING%%')
    """)
    return created
