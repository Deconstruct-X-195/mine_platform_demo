"""定时任务（PRD 4.8/T16）：小时级调度线程。

职责：
1. 询价报价截止 → 自动揭示比价（复用 reveal_inquiry，含响应不足标记）。
2. 订单供应商 48h 未确认 → 订单失效 CANCELLED，中标报价回退 SUBMITTED，
   询价无其余中标报价时重开 CLOSED（可重新定标），需求明细成交回退。
3. 五类预警扫描（alerts.scan_alerts，去重 + 24h 生成节流；扫描默认每天一次，
   MINE_ALERT_SCAN_INTERVAL 秒可配，避免业务端频繁收到预警提醒）。

测试中通过 MINE_DISABLE_JOBS=1 禁用；调度间隔 MINE_JOBS_INTERVAL 秒（默认 3600）。
"""
import os
import time
import traceback
from datetime import datetime

from .alerts import scan_alerts, send_msg
from .db import execute, q1, qall, with_db


def _reveal_due_inquiries(conn):
    """报价截止的询价自动揭示（SENT/QUOTING → CLOSED + 快照）。"""
    rows = qall(conn, """
        SELECT id FROM biz_inquiry
        WHERE is_deleted=0 AND status IN ('SENT','QUOTING') AND deadline <= now()
    """)
    if not rows:
        return 0
    from .api.inquiry import reveal_inquiry
    n = 0
    for r in rows:
        try:
            reveal_inquiry(conn, r['id'], None)
            n += 1
        except Exception:
            traceback.print_exc()
    return n


def _expire_orders(conn):
    """供应商 48h 未确认的订单失效并回退报价/询价/需求量。

    普通订单：中标报价回退、询价重开、需求明细 deal_qty 回退。
    集采聚合订单（buyer_id 为空）：按成员明细回退 deal_qty 与归集锁定量（inquired_qty）、
    需求单 DEALT 回退 SUBMITTED、归集订单 AWARDED 重开 INQUIRING（可重新发起询价），
    并通知全部参与钢厂与中标供应商。
    """
    rows = qall(conn, """
        SELECT o.id, o.order_no, o.inquiry_id, o.quote_id, o.quantity, o.buyer_id, o.supplier_id,
               i.agg_id
        FROM biz_order o
        LEFT JOIN biz_inquiry i ON i.id=o.inquiry_id AND i.is_deleted=0
        WHERE o.is_deleted=0 AND o.status='PENDING_CONFIRM'
          AND o.confirm_deadline IS NOT NULL AND o.confirm_deadline < now()
    """)
    n = 0
    for o in rows:
        try:
            from .state_machine import transition
            transition(conn, None, 'biz_order', '订单', 'biz_order', o['id'], 'CANCELLED',
                       node_biz_type='ORDER', node_code='ORDER_EXPIRED')
            # 中标报价回退，可重新定标
            if o['quote_id']:
                q = q1(conn, "SELECT status FROM biz_quote WHERE id=%s AND is_deleted=0", (o['quote_id'],))
                if q and q['status'] == 'WIN':
                    transition(conn, None, 'biz_quote', '报价', 'biz_quote', o['quote_id'], 'SUBMITTED')
            # 询价无其余中标报价 → 重开（AWARDED → CLOSED，可重新定标）
            if o['inquiry_id']:
                remain = q1(conn, """
                    SELECT count(*) AS c FROM biz_quote
                    WHERE inquiry_id=%s AND status='WIN' AND is_deleted=0
                """, (o['inquiry_id'],))['c']
                inq = q1(conn, "SELECT status, demand_item_id, agg_id FROM biz_inquiry WHERE id=%s AND is_deleted=0",
                         (o['inquiry_id'],))
                if inq and inq['status'] == 'AWARDED' and not remain:
                    transition(conn, None, 'biz_inquiry', '询价单', 'biz_inquiry',
                               o['inquiry_id'], 'CLOSED')
                if inq and inq['agg_id']:
                    _rollback_agg_order(conn, inq['agg_id'])
                elif inq and inq['demand_item_id']:
                    # 需求明细成交回填回退（自发询价历史数据路径）
                    execute(conn, """
                        UPDATE biz_demand_item
                        SET deal_qty = GREATEST(deal_qty - %s, 0), updated_at=now()
                        WHERE id=%s
                    """, (o['quantity'], inq['demand_item_id']))
            if o['buyer_id'] or o['supplier_id']:
                for cid in (o['buyer_id'], o['supplier_id']):
                    send_msg(conn, cid, '订单超时失效',
                             '订单 %s 超过 48 小时未确认已失效，可重新定标' % o['order_no'], 'ORDER', o['id'])
            else:
                # 集采聚合订单：通知全部参与钢厂、中标供应商与平台
                members = [m['company_id'] for m in qall(conn, """
                    SELECT DISTINCT company_id FROM biz_order_member
                    WHERE order_id=%s AND is_deleted=0
                """, (o['id'],))]
                for cid in members + [o['supplier_id'], None]:
                    send_msg(conn, cid, '订单超时失效',
                             '订单 %s 超过 48 小时未确认已失效，可重新发起询价' % o['order_no'], 'ORDER', o['id'])
            n += 1
        except Exception:
            traceback.print_exc()
    return n


def _rollback_agg_order(conn, agg_id):
    """聚合订单失效：回退成员需求明细成交回填与归集锁定量，需求/归集订单状态回退。"""
    from .state_machine import transition
    execute(conn, """
        UPDATE biz_demand_item di
        SET deal_qty = GREATEST(COALESCE(di.deal_qty, 0) - m.quantity, 0),
            inquired_qty = GREATEST(COALESCE(di.inquired_qty, 0) - m.quantity, 0),
            updated_at = now()
        FROM biz_aggregated_order_item m
        WHERE m.agg_id=%s AND m.is_deleted=0 AND m.demand_item_id=di.id
    """, (agg_id,))
    agg = q1(conn, "SELECT status FROM biz_aggregated_order WHERE id=%s AND is_deleted=0", (agg_id,))
    if agg and agg['status'] == 'AWARDED':
        transition(conn, None, 'biz_aggregated_order', '归集订单', 'biz_aggregated_order',
                   agg_id, 'INQUIRING')
    for drow in qall(conn, """
            SELECT d.id, d.status, SUM(di.quantity) AS qty, SUM(COALESCE(di.deal_qty, 0)) AS deal
            FROM biz_demand d
            JOIN biz_demand_item di ON di.demand_id=d.id AND di.is_deleted=0
            WHERE d.id IN (SELECT m.demand_id FROM biz_aggregated_order_item m
                            WHERE m.agg_id=%s AND m.is_deleted=0)
              AND d.is_deleted=0
            GROUP BY d.id, d.status
            """, (agg_id,)):
        if drow['status'] == 'DEALT' and drow['deal'] < drow['qty']:
            transition(conn, None, 'biz_demand', '需求单', 'biz_demand', drow['id'], 'SUBMITTED')


_last_alert_scan = 0.0  # 上次预警扫描时间戳（预警扫描节流，避免业务端频繁收到预警提醒）


def _tick(conn):
    global _last_alert_scan
    now = datetime.now()
    revealed = _reveal_due_inquiries(conn)
    expired = _expire_orders(conn)
    # 预警扫描节流：默认每 24 小时一次（MINE_ALERT_SCAN_INTERVAL 秒可配），
    # 询价揭示/订单失效仍按小时级执行
    alerts = 0
    if now.timestamp() - _last_alert_scan >= int(os.environ.get('MINE_ALERT_SCAN_INTERVAL', 86400)):
        _last_alert_scan = now.timestamp()
        alerts = scan_alerts(conn, now)
    if revealed or expired or alerts:
        print('[mine-jobs] reveal=%s expire=%s alerts=%s' % (revealed, expired, alerts))


def run_once():
    """单轮执行（C4，部署适配方案 §5）：执行一轮任务后立即返回。

    供独立任务进程调用（run.py --jobs / systemd timer），与 Web 进程解耦，
    避免多进程/多实例下定时任务重复执行。
    """
    with with_db() as conn:
        _tick(conn)


def run_loop():
    interval = int(os.environ.get('MINE_JOBS_INTERVAL', 3600))
    while True:
        try:
            with with_db() as conn:
                _tick(conn)
        except Exception:
            traceback.print_exc()
        time.sleep(interval)
