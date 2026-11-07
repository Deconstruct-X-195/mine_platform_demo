"""定时任务（PRD 4.8/T16）：小时级调度线程。

职责：
1. 询价报价截止 → 自动揭示比价（复用 reveal_inquiry，含响应不足标记）。
2. 订单供应商 48h 未确认 → 订单失效 CANCELLED，中标报价回退 SUBMITTED，
   询价无其余中标报价时重开 CLOSED（可重新定标），需求明细成交回退。
3. 五类预警扫描（alerts.scan_alerts，去重 + 自动关闭已解除项）。

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
    """供应商 48h 未确认的订单失效并回退报价/询价/需求量。"""
    rows = qall(conn, """
        SELECT id, order_no, inquiry_id, quote_id, quantity, buyer_id, supplier_id
        FROM biz_order
        WHERE is_deleted=0 AND status='PENDING_CONFIRM'
          AND confirm_deadline IS NOT NULL AND confirm_deadline < now()
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
                inq = q1(conn, "SELECT status, demand_item_id FROM biz_inquiry WHERE id=%s AND is_deleted=0",
                         (o['inquiry_id'],))
                if inq and inq['status'] == 'AWARDED' and not remain:
                    transition(conn, None, 'biz_inquiry', '询价单', 'biz_inquiry',
                               o['inquiry_id'], 'CLOSED')
                # 需求明细成交回填回退
                if inq and inq['demand_item_id']:
                    execute(conn, """
                        UPDATE biz_demand_item
                        SET deal_qty = GREATEST(deal_qty - %s, 0), updated_at=now()
                        WHERE id=%s
                    """, (o['quantity'], inq['demand_item_id']))
            for cid in (o['buyer_id'], o['supplier_id']):
                send_msg(conn, cid, '订单超时失效',
                         '订单 %s 超过 48 小时未确认已失效，可重新定标' % o['order_no'], 'ORDER', o['id'])
            n += 1
        except Exception:
            traceback.print_exc()
    return n


def _tick(conn):
    now = datetime.now()
    revealed = _reveal_due_inquiries(conn)
    expired = _expire_orders(conn)
    alerts = scan_alerts(conn, now)
    if revealed or expired or alerts:
        print('[mine-jobs] reveal=%s expire=%s alerts=%s' % (revealed, expired, alerts))


def run_loop():
    interval = int(os.environ.get('MINE_JOBS_INTERVAL', 3600))
    while True:
        try:
            with with_db() as conn:
                _tick(conn)
        except Exception:
            traceback.print_exc()
        time.sleep(interval)
