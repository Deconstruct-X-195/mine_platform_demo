# -*- coding: utf-8 -*-
"""数据报表&大屏看板模块 (PRD-13)：采购汇总/交易汇总/物流时效/结算汇总四张报表 +
R4 运营大屏聚合接口，支持时间区间筛选与 R1/R2 数据权限隔离"""
from flask import Blueprint, request, g
from ..db import get_db, _now
from ..utils import ok, err, log_action
from ..auth import roles_required, company_approved_required

bp = Blueprint('report', __name__)


def _range(args):
    start = args.get('start_date')
    end = args.get('end_date')
    conds, params = [], []
    if start:
        conds.append(">= ?"); params.append(start)
    if end:
        conds.append("<= ?"); params.append(end + ' 23:59:59')
    return conds, params


def _time_cond(col, conds):
    return " AND " + " AND ".join(f"{col} {c}" for c in conds) if conds else ""


# ================= 1. 采购汇总报表 =================

@bp.get('/report/summary')
@roles_required('R1', 'R4')
@company_approved_required
def report_summary():
    db = get_db()
    conds, params = _range(request.args)
    args = list(params)
    cond = _time_cond('d.create_time', conds)
    is_r4 = g.current_user['role_code'] == 'R4'
    cid = g.current_user['company_id']
    if not is_r4:
        cond += " AND d.company_id=?"; args.append(cid)

    by_category = [dict(r) for r in db.execute(
        f"SELECT d.ore_category, COUNT(*) AS demand_cnt, COALESCE(SUM(d.quantity),0) AS total_qty"
        f" FROM purchase_demand d WHERE 1=1{cond} GROUP BY d.ore_category ORDER BY total_qty DESC", args).fetchall()]
    by_period = [dict(r) for r in db.execute(
        f"SELECT d.period_type, COUNT(*) AS demand_cnt, COALESCE(SUM(d.quantity),0) AS total_qty"
        f" FROM purchase_demand d WHERE 1=1{cond} GROUP BY d.period_type", args).fetchall()]
    by_company = [dict(r) for r in db.execute(
        f"SELECT c.company_name, COUNT(*) AS demand_cnt, COALESCE(SUM(d.quantity),0) AS total_qty"
        f" FROM purchase_demand d JOIN company c ON c.company_id=d.company_id WHERE 1=1{cond}"
        f" GROUP BY d.company_id ORDER BY total_qty DESC LIMIT 10", args).fetchall()]
    status_rows = [dict(r) for r in db.execute(
        f"SELECT d.status, COUNT(*) AS cnt FROM purchase_demand d WHERE 1=1{cond} GROUP BY d.status", args).fetchall()]
    return ok({'by_category': by_category, 'by_period': by_period,
               'by_company': by_company, 'by_status': status_rows})


# ================= 2. 交易汇总报表 =================

@bp.get('/report/trade')
@roles_required('R2', 'R4')
@company_approved_required
def report_trade():
    db = get_db()
    conds, params = _range(request.args)
    cond = _time_cond('o.create_time', conds)
    args = list(params)
    is_r4 = g.current_user['role_code'] == 'R4'
    cid = g.current_user['company_id']
    if not is_r4:
        cond += " AND o.supplier_id=?"; args.append(cid)

    by_month = [dict(r) for r in db.execute(
        f"SELECT substr(o.create_time,1,7) AS month, COUNT(*) AS order_cnt,"
        f" COALESCE(SUM(o.total_qty),0) AS total_qty, COALESCE(SUM(o.total_amount),0) AS total_amount"
        f" FROM collective_order o WHERE 1=1{cond} GROUP BY month ORDER BY month", args).fetchall()]
    by_category = [dict(r) for r in db.execute(
        f"SELECT o.ore_category, COUNT(*) AS order_cnt, COALESCE(SUM(o.total_qty),0) AS total_qty,"
        f" COALESCE(SUM(o.total_amount),0) AS total_amount, ROUND(AVG(o.unit_price),2) AS avg_price"
        f" FROM collective_order o WHERE 1=1{cond} GROUP BY o.ore_category ORDER BY total_amount DESC",
        args).fetchall()]
    by_supplier = [dict(r) for r in db.execute(
        f"SELECT c.company_name, COUNT(*) AS order_cnt, COALESCE(SUM(o.total_qty),0) AS total_qty,"
        f" COALESCE(SUM(o.total_amount),0) AS total_amount"
        f" FROM collective_order o JOIN company c ON c.company_id=o.supplier_id WHERE 1=1{cond}"
        f" GROUP BY o.supplier_id ORDER BY total_amount DESC LIMIT 10", args).fetchall()]
    return ok({'by_month': by_month, 'by_category': by_category, 'by_supplier': by_supplier})


# ================= 3. 物流时效报表 =================

@bp.get('/report/logistics')
@roles_required('R1', 'R2', 'R3', 'R4')
@company_approved_required
def report_logistics():
    db = get_db()
    conds, params = _range(request.args)
    cond = _time_cond('t.create_time', conds)
    args = list(params)
    role, cid = g.current_user['role_code'], g.current_user['company_id']
    if role == 'R3':
        cond += (" AND (t.sea_partner_id=? OR t.port_partner_id=? OR t.warehouse_partner_id=?"
                 " OR t.land_partner_id=?)")
        args.extend([cid, cid, cid, cid])
    elif role == 'R1':
        cond += " AND t.alloc_id IN (SELECT alloc_id FROM allocation_order WHERE company_id=?)"
        args.append(cid)
    elif role == 'R2':
        cond += " AND t.order_id IN (SELECT order_id FROM collective_order WHERE supplier_id=?)"
        args.append(cid)

    rows = [dict(r) for r in db.execute(
        f"SELECT * FROM logistics_task t WHERE 1=1{cond} ORDER BY t.create_time DESC LIMIT 500", args).fetchall()]
    stats = []
    for t in rows:
        nodes = db.execute("SELECT node_code, done_time FROM logistics_node WHERE logi_id=? AND status='DONE'"
                           " ORDER BY node_code", (t['logi_id'],)).fetchall()
        start = nodes[0]['done_time'] if nodes else None
        end = nodes[-1]['done_time'] if len(nodes) == 7 else None
        days = None
        if start and end:
            from datetime import datetime as dt
            try:
                days = round((dt.strptime(end[:19], '%Y-%m-%d %H:%M:%S') -
                              dt.strptime(start[:19], '%Y-%m-%d %H:%M:%S')).total_seconds() / 86400, 1)
            except ValueError:
                days = None
        stats.append({'logi_no': t['logi_no'], 'current_node': t['current_node'], 'finished': len(nodes),
                      'days': days, 'create_time': t['create_time']})
    finished = [s for s in stats if s['days'] is not None]
    avg_days = round(sum(s['days'] for s in finished) / len(finished), 1) if finished else None
    done_cnt = db.execute(f"SELECT COUNT(*) FROM logistics_task t WHERE 1=1{cond} AND t.current_node=7",
                          args).fetchone()[0]
    return ok({'stats': stats[:100], 'avg_days': avg_days,
               'finish_rate': round(done_cnt * 100.0 / len(stats), 1) if stats else None,
               'total': len(stats)})


# ================= 4. 结算汇总报表 =================

@bp.get('/report/settlement')
@roles_required('R1', 'R2', 'R4')
@company_approved_required
def report_settlement():
    db = get_db()
    conds, params = _range(request.args)
    cond = _time_cond('b.create_time', conds)
    args = list(params)
    role, cid = g.current_user['role_code'], g.current_user['company_id']
    if role == 'R1':
        cond += " AND b.company_id=?"; args.append(cid)
    elif role == 'R2':
        cond += " AND b.supplier_id=?"; args.append(cid)

    by_company = [dict(r) for r in db.execute(
        f"SELECT c.company_name, COUNT(*) AS bill_cnt, COALESCE(SUM(b.total_amount),0) AS total_amount,"
        f" COALESCE(SUM(CASE WHEN b.status='CONFIRMED' THEN b.total_amount ELSE 0 END),0) AS confirmed_amount,"
        f" COALESCE(SUM(CASE WHEN b.status='PENDING' THEN b.total_amount ELSE 0 END),0) AS pending_amount"
        f" FROM company_bill b JOIN company c ON c.company_id=b.company_id WHERE 1=1{cond}"
        f" GROUP BY b.company_id ORDER BY total_amount DESC", args).fetchall()]
    return ok({'by_company': by_company})


# ================= 5. 价格趋势（R4 报表中心 + 大屏） =================

@bp.get('/report/price-trend')
@roles_required('R4')
def report_price_trend():
    db = get_db()
    cat = request.args.get('ore_category') or 'IRON'
    conds, params = _range(request.args)
    cond = _time_cond('q.quote_date', conds)
    args = [cat] + params
    rows = [dict(r) for r in db.execute(
        f"SELECT date(q.quote_date) AS quote_date, q.market_price, q.avg_deal_price FROM ore_price_quote q"
        f" WHERE q.ore_category=?{cond} ORDER BY q.quote_date", args).fetchall()]
    return ok({'category': cat, 'trend': rows})


# ================= R4 运营大屏聚合 =================

@bp.get('/dashboard/overview')
@roles_required('R4')
def dashboard_overview():
    db = get_db()
    total_companies = db.execute("SELECT COUNT(*) FROM company").fetchone()[0]
    pending_audit = db.execute("SELECT COUNT(*) FROM company WHERE audit_status='PENDING'").fetchone()[0]
    total_demands = db.execute("SELECT COUNT(*) FROM purchase_demand").fetchone()[0]
    total_qty = db.execute("SELECT COALESCE(SUM(quantity),0) FROM purchase_demand").fetchone()[0] or 0
    locked_qty = db.execute("SELECT COALESCE(SUM(total_qty),0) FROM collective_order").fetchone()[0] or 0
    trade_amount = db.execute("SELECT COALESCE(SUM(total_amount),0) FROM collective_order").fetchone()[0] or 0
    logi_running = db.execute("SELECT COUNT(*) FROM logistics_task WHERE current_node<7").fetchone()[0]
    logi_done = db.execute("SELECT COUNT(*) FROM logistics_task WHERE current_node=7").fetchone()[0]
    bill_total = db.execute("SELECT COALESCE(SUM(total_amount),0) FROM company_bill").fetchone()[0] or 0
    bill_confirmed = db.execute("SELECT COALESCE(SUM(total_amount),0) FROM company_bill WHERE status='CONFIRMED'").fetchone()[0] or 0

    order_trend = [dict(r) for r in db.execute(
        "SELECT substr(create_time,1,7) AS month, COUNT(*) AS cnt,"
        " COALESCE(SUM(total_amount),0) AS amount FROM collective_order"
        " GROUP BY month ORDER BY month DESC LIMIT 6").fetchall()]
    order_trend.reverse()
    alloc_map = [dict(r) for r in db.execute(
        "SELECT c.company_name, COUNT(*) AS cnt, COALESCE(SUM(a.qty),0) AS qty FROM allocation_order a"
        " JOIN company c ON c.company_id=a.company_id GROUP BY a.company_id ORDER BY qty DESC LIMIT 8").fetchall()]
    node_map = [dict(r) for r in db.execute(
        "SELECT current_node AS node, COUNT(*) AS cnt FROM logistics_task GROUP BY current_node ORDER BY node").fetchall()]
    unread_warn = db.execute(
        "SELECT COUNT(*) FROM ore_message WHERE msg_type=3 AND is_read=0").fetchone()[0]
    return ok({
        'cards': {
            'total_companies': total_companies, 'pending_audit': pending_audit,
            'total_demands': total_demands, 'total_qty': round(total_qty, 2),
            'locked_qty': round(locked_qty, 2), 'trade_amount': round(trade_amount, 2),
            'logi_running': logi_running, 'logi_done': logi_done,
            'bill_total': round(bill_total, 2), 'bill_confirmed': round(bill_confirmed, 2),
            'unread_warn': unread_warn
        },
        'order_trend': order_trend, 'alloc_map': alloc_map, 'node_map': node_map
    })
