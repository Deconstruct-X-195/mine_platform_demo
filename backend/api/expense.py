# -*- coding: utf-8 -*-
"""结算明细&费用分摊模块 (PRD-11)：集采杂费归集（海运/港杂/仓储/装卸/陆运/代理）、
按结算吨数权重分摊到下游分拨单、分摊撤销重跑、分项结算明细查询、费用台账导出"""
from flask import Blueprint, request, g
from ..db import get_db, _now
from ..utils import ok, err, log_action, paginate, round2, export_excel
from ..auth import roles_required, company_approved_required

bp = Blueprint('expense', __name__)

ALLOC_STATUS = {'ACTIVE': '已分摊', 'REVOKED': '已撤销'}


def _enrich_bill(db, b):
    o = db.execute("SELECT order_no FROM collective_order WHERE order_id=?", (b['order_id'],)).fetchone()
    b['order_no'] = o['order_no'] if o else None
    n = db.execute("SELECT COUNT(*) FROM ore_expense_allocate WHERE expense_bill_id=? AND status='ACTIVE'",
                   (b['expense_id'],)).fetchone()[0]
    b['allocated_count'] = n
    return b


def _order_settle_weights(db, order_id):
    """分摊权重：每张分拨单的结算吨数（船检化验单审核通过后按其出库检/分拨吨数，否则按分拨吨数）。
    化验单前置校验：该订单必须存在审核通过的到港船检化验单。"""
    approved = db.execute(
        "SELECT 1 FROM ore_inspect_report WHERE order_id=? AND report_type=2 AND status='APPROVED'"
        " AND is_redbacked=0 LIMIT 1", (order_id,)).fetchone()
    if not approved:
        return None, '该集采订单尚无审核通过的到港船检化验单，暂不可费用分摊'
    allocs = [dict(r) for r in db.execute(
        "SELECT alloc_id, alloc_no, company_id, qty, is_redbacked FROM allocation_order WHERE order_id=?",
        (order_id,)).fetchall() if not r['is_redbacked']]
    if not allocs:
        return None, '该集采订单下没有可分摊的分拨单'
    weights = []
    for a in allocs:
        # 出库检（report_type=4）审核通过的结算吨数优先，否则用分拨吨数
        rpt = db.execute(
            "SELECT settle_ton FROM ore_inspect_report WHERE alloc_id=? AND report_type=4 AND status='APPROVED'"
            " AND is_redbacked=0 ORDER BY report_id DESC LIMIT 1", (a['alloc_id'],)).fetchone()
        ton = rpt['settle_ton'] if rpt and rpt['settle_ton'] else a['qty']
        weights.append({**a, 'weight_ton': round2(ton)})
    return weights, None


# ================= 费用单（R4） =================

@bp.post('/expense/bill/save')
@roles_required('R4')
def bill_save():
    d = request.get_json(force=True)
    db = get_db()
    if not d.get('order_id'):
        return err('必须关联集采总订单')
    order = db.execute("SELECT order_id FROM collective_order WHERE order_id=?", (d['order_id'],)).fetchone()
    if not order:
        return err('集采总订单不存在', http=404)
    etype = (d.get('expense_type') or '').strip()
    if not etype:
        return err('费用类型必填')
    try:
        amount = round(float(d.get('expense_amount')))
    except (TypeError, ValueError):
        return err('费用金额必须为数字')
    if amount <= 0:
        return err('费用金额必须大于0')
    now = _now()
    cur = db.execute(
        "INSERT INTO ore_expense_bill(order_id,expense_type,expense_amount,happen_date,payee,"
        "attachment_url,file_name,remark,create_by,create_time) VALUES(?,?,?,?,?,?,?,?,?,?)",
        (d['order_id'], etype, amount, d.get('happen_date'), d.get('payee'),
         d.get('attachment_url'), d.get('file_name'), d.get('remark'), g.current_user['user_id'], now))
    eid = cur.lastrowid
    db.execute("UPDATE ore_expense_bill SET expense_no=? WHERE expense_id=?",
               (f"EX{now.replace('-', '').replace(':', '').replace(' ', '')}{eid:04d}", eid))
    db.commit()
    log_action('新增费用单', f"EX{eid:04d} {etype} {amount}元", ref_type='ore_expense_bill', ref_id=eid)
    row = db.execute("SELECT * FROM ore_expense_bill WHERE expense_id=?", (eid,)).fetchone()
    return ok(_enrich_bill(db, dict(row)))


@bp.get('/expense/bill/list')
@roles_required('R4')
def bill_list():
    db = get_db()
    page = int(request.args.get('page', 1)); size = int(request.args.get('page_size', 10))
    sql = "SELECT b.* FROM ore_expense_bill b WHERE b.is_deleted=0"
    args = []
    if request.args.get('order_id'):
        sql += " AND b.order_id=?"; args.append(int(request.args['order_id']))
    if request.args.get('expense_type'):
        sql += " AND b.expense_type=?"; args.append(request.args['expense_type'])
    if request.args.get('start_date'):
        sql += " AND b.happen_date>=?"; args.append(request.args['start_date'])
    if request.args.get('end_date'):
        sql += " AND b.happen_date<=?"; args.append(request.args['end_date'])
    sql += " ORDER BY b.create_time DESC"
    rows, total = paginate(db, sql, args, page, size)
    for r in rows:
        _enrich_bill(db, r)
    return ok({'list': rows, 'total': total, 'page': page, 'page_size': size})


@bp.post('/expense/bill/<int:eid>/delete')
@roles_required('R4')
def bill_delete(eid):
    db = get_db()
    row = db.execute("SELECT * FROM ore_expense_bill WHERE expense_id=? AND is_deleted=0", (eid,)).fetchone()
    if not row:
        return err('费用单不存在', http=404)
    shared = db.execute("SELECT 1 FROM ore_expense_allocate WHERE expense_bill_id=? AND status='ACTIVE'",
                        (eid,)).fetchone()
    if shared:
        return err('该费用单已执行分摊，请先撤销分摊再删除')
    db.execute("UPDATE ore_expense_bill SET is_deleted=1 WHERE expense_id=?", (eid,))
    db.commit()
    log_action('删除费用单', row['expense_no'], ref_type='ore_expense_bill', ref_id=eid)
    return ok(message='已删除')


# ================= 执行分摊 / 撤销分摊（R4） =================

@bp.post('/expense/share/run')
@roles_required('R4')
def share_run():
    d = request.get_json(force=True)
    db = get_db()
    order_id = d.get('order_id')
    if not order_id:
        return err('请选择集采总订单')
    weights, error = _order_settle_weights(db, order_id)
    if error:
        return err(error)
    # 待分摊费用：该订单下未分摊（无 ACTIVE 记录）的费用单
    bills = [dict(r) for r in db.execute(
        "SELECT * FROM ore_expense_bill WHERE order_id=? AND is_deleted=0"
        " AND expense_id NOT IN (SELECT expense_bill_id FROM ore_expense_allocate WHERE status='ACTIVE')",
        (order_id,)).fetchall()]
    if d.get('expense_ids'):
        bills = [b for b in bills if b['expense_id'] in d['expense_ids']]
    if not bills:
        return err('没有待分摊的费用单')
    total_weight = round2(sum(w['weight_ton'] for w in weights))
    if total_weight <= 0:
        return err('分摊权重吨数合计必须大于0')

    now = _now()
    created = 0
    for b in bills:
        allocated = 0.0
        for i, w in enumerate(weights):
            if i == len(weights) - 1:  # 最后一单兜尾差，保证金额守恒
                amt = round2(b['expense_amount'] - allocated)
            else:
                amt = round2(b['expense_amount'] * w['weight_ton'] / total_weight)
                allocated = round2(allocated + amt)
            db.execute("INSERT INTO ore_expense_allocate(expense_bill_id,alloc_id,share_ton,share_amount,"
                       "status,create_time) VALUES(?,?,?,?, 'ACTIVE', ?)",
                       (b['expense_id'], w['alloc_id'], w['weight_ton'], amt, now))
            created += 1
    db.commit()
    log_action('执行费用分摊', f"订单#{order_id}：{len(bills)}笔费用分摊到{len(weights)}张分拨单",
               ref_type='ore_expense_bill', ref_id=order_id)
    # 通知下游企业
    from .message import notify_company
    comp_ids = {w['company_id'] for w in weights}
    for cid in comp_ids:
        notify_company(db, cid, 2, '分项结算明细已生成',
                       f'您参与的集采订单已完成费用分摊，可在「费用结算明细」查看分项明细', 'EXPENSE', order_id)
    return ok({'allocated_rows': created, 'bills': len(bills), 'alloc_orders': len(weights)})


@bp.post('/expense/share/revoke')
@roles_required('R4')
def share_revoke():
    d = request.get_json(force=True)
    db = get_db()
    order_id = d.get('order_id')
    if not order_id:
        return err('请选择集采总订单')
    cur = db.execute(
        "UPDATE ore_expense_allocate SET status='REVOKED', revoke_time=? WHERE status='ACTIVE'"
        " AND expense_bill_id IN (SELECT expense_id FROM ore_expense_bill WHERE order_id=?)",
        (_now(), order_id))
    if cur.rowcount == 0:
        return err('该订单没有可撤销的分摊记录')
    db.commit()
    log_action('撤销费用分摊', f"订单#{order_id} 撤销 {cur.rowcount} 条分摊记录",
               before='ACTIVE', after='REVOKED', ref_type='ore_expense_bill', ref_id=order_id)
    return ok({'revoked': cur.rowcount})


# ================= 分摊明细查询 =================

@bp.get('/expense/share/detail')
@roles_required('R1', 'R4')
@company_approved_required
def share_detail():
    """分项结算明细：按分拨单（R4 可传 alloc_id/order_id，R1 仅限自有分拨单）"""
    db = get_db()
    alloc_id = request.args.get('alloc_id')
    order_id = request.args.get('order_id')
    if g.current_user['role_code'] == 'R1':
        if not alloc_id:
            return err('请选择分拨单')
        own = db.execute("SELECT 1 FROM allocation_order WHERE alloc_id=? AND company_id=?",
                         (alloc_id, g.current_user['company_id'])).fetchone()
        if not own:
            return err('无权查看该分拨单', code=403, http=403)
    if not alloc_id and not order_id:
        return err('请提供分拨单或集采订单')

    sql = ("SELECT a.*, b.expense_no, b.expense_type, b.happen_date FROM ore_expense_allocate a"
           " JOIN ore_expense_bill b ON b.expense_id=a.expense_bill_id AND b.is_deleted=0"
           " WHERE a.status='ACTIVE'")
    args = []
    if alloc_id:
        sql += " AND a.alloc_id=?"; args.append(int(alloc_id))
    else:
        sql += " AND a.alloc_id IN (SELECT alloc_id FROM allocation_order WHERE order_id=?)"
        args.append(int(order_id))
    rows = [dict(r) for r in db.execute(sql, args).fetchall()]

    alloc = None
    if alloc_id:
        alloc = dict(db.execute("SELECT * FROM allocation_order WHERE alloc_id=?", (alloc_id,)).fetchone())
        # 货款 = 分拨单价 × 分拨吨数
        alloc['ore_amount'] = round2(alloc['unit_price'] * alloc['qty'])
    # 按费用类型汇总
    summary = {}
    for r in rows:
        key = r['expense_type']
        summary.setdefault(key, {'expense_type': key, 'total': 0.0, 'count': 0})
        summary[key]['total'] = round2(summary[key]['total'] + r['share_amount'])
        summary[key]['count'] += 1
    expense_total = round2(sum(s['total'] for s in summary.values()))
    return ok({
        'alloc': alloc,
        'details': rows,
        'summary': list(summary.values()),
        'expense_total': expense_total,
        'total_payable': round2(alloc['ore_amount'] + expense_total) if alloc else None
    })


# ================= 费用台账导出（R4） =================

@bp.get('/expense/bill/export')
@roles_required('R4')
def bill_export():
    db = get_db()
    sql = ("SELECT b.*, (SELECT COALESCE(SUM(share_amount),0) FROM ore_expense_allocate x"
           " WHERE x.expense_bill_id=b.expense_id AND x.status='ACTIVE') AS shared_amount"
           " FROM ore_expense_bill b WHERE b.is_deleted=0 ORDER BY b.create_time DESC")
    rows = [dict(r) for r in db.execute(sql).fetchall()]
    headers = ['费用单号', '集采订单号', '费用类型', '金额', '发生日期', '收款方', '已分摊金额', '备注']
    data = []
    for r in rows:
        _enrich_bill(db, r)
        data.append([r['expense_no'], r['order_no'] or r['order_id'], r['expense_type'], r['expense_amount'],
                     r['happen_date'] or '-', r['payee'] or '-', r['shared_amount'], r['remark'] or '-'])
    log_action('导出费用台账', f"{len(data)} 条")
    return export_excel(headers, [('费用台账', data)], f'费用台账_{_now()[:10]}.xlsx')
