# -*- coding: utf-8 -*-
"""对账结算模块 (PRD-07)：分拨单生成/到货确认/异常反馈/企业对账单/供方对账单/结清/归档/履约台账"""
import io
from flask import Blueprint, request, g
from ..db import get_db, _now
from ..utils import ok, err, log_action, paginate, round2, export_excel
from ..auth import roles_required, company_approved_required

bp = Blueprint('settlement', __name__)

# 分拨单状态机: TRANSIT(配送在途) → WAIT_CONFIRM(待企业确认到货) → DONE(已完成)
# 对账单状态机: PENDING(待确认) → CONFIRMED(已确认)/DISPUTE(有异议) → SETTLED(已结清)


def _get_alloc(db, aid):
    return db.execute("SELECT * FROM allocation_order WHERE alloc_id=?", (aid,)).fetchone()


def _period_of_order(db, order_id):
    r = db.execute(
        "SELECT l.period_type, l.period FROM collective_order o"
        " JOIN collective_task t ON t.task_id=o.task_id"
        " JOIN collective_list l ON l.list_id=t.list_id WHERE o.order_id=?", (order_id,)).fetchone()
    if not r:
        return None, None
    return r['period_type'], r['period']


def _gen_no(db, table, col, prefix):
    now = _now().replace('-', '').replace(':', '').replace(' ', '')
    r = db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    return f"{prefix}{now}{r + 1:04d}"


# ================= 分拨单 =================

@bp.post('/admin/allocation/create')
@roles_required('R4')
def allocation_create():
    """入库后（N5完成）按下游企业分拨生成单据"""
    d = request.get_json(force=True)
    db = get_db()
    if not d.get('order_id'):
        return err('缺少集采订单')
    o = db.execute("SELECT * FROM collective_order WHERE order_id=?", (d['order_id'],)).fetchone()
    if not o:
        return err('集采订单不存在', http=404)
    lt = db.execute("SELECT * FROM logistics_task WHERE order_id=?", (o['order_id'],)).fetchone()
    if not lt:
        return err('该订单尚未创建物流任务，无法分拨')
    if lt['current_node'] < 5:
        return err(f'货物尚未完成入仓储（当前节点 N{lt["current_node"]}），不可分拨')
    dup = db.execute("SELECT COUNT(*) FROM allocation_order WHERE order_id=?", (o['order_id'],)).fetchone()[0]
    if dup:
        return err('该订单已完成分拨，不可重复分拨')
    allocs = d.get('allocs')
    if not isinstance(allocs, list) or not allocs:
        return err('请提供分拨明细')
    now = _now()
    total = 0.0
    plan = []
    for a in allocs:
        try:
            cid = int(a.get('company_id')); qty = round2(a.get('qty')); price = round2(a.get('unit_price'))
        except (TypeError, ValueError):
            return err('分拨明细缺少有效字段')
        if qty <= 0 or price <= 0:
            return err('分拨吨数、单价必须大于0')
        c = db.execute("SELECT * FROM company WHERE company_id=?", (cid,)).fetchone()
        if not c or c['company_type'] != 'DOWNSTREAM':
            return err('分拨对象必须是下游需求企业')
        if c['audit_status'] != 'APPROVED':
            return err(f'企业 {c["company_name"]} 资质未审核通过')
        plan.append((cid, qty, price, (a.get('destination') or '').strip() or None))
        total += qty
    if total > o['total_qty'] + 1e-9:
        return err(f'分拨合计 {total} 吨不可超过集采实际到货 {o["total_qty"]} 吨')
    period_type, period = _period_of_order(db, o['order_id'])
    created = []
    for cid, qty, price, dest in plan:
        cur = db.execute(
            "INSERT INTO allocation_order(order_id,company_id,ore_category,qty,unit_price,amount,"
            "destination,status,create_time) VALUES(?,?,?,?,?,?,?,?,?)",
            (o['order_id'], cid, o['ore_category'], qty, price, round2(qty * price),
             dest, 'TRANSIT', now))
        aid = cur.lastrowid
        alloc_no = _gen_no(db, 'allocation_order', 'alloc_no', 'AL')
        db.execute("UPDATE allocation_order SET alloc_no=? WHERE alloc_id=?", (alloc_no, aid))
        created.append(aid)
    db.commit()
    log_action('生成分拨单', f"订单{o['order_no']} 分拨{len(created)}家下游企业合计{total}吨",
               ref_type='allocation_order', ref_id=o['order_id'])
    rows = [dict(x) for x in db.execute(
        "SELECT a.*, c.company_name FROM allocation_order a JOIN company c ON c.company_id=a.company_id"
        " WHERE a.order_id=?", (o['order_id'],))]
    return ok({'list': rows})


@bp.get('/admin/allocation/list')
@roles_required('R4')
def allocation_list():
    db = get_db()
    page = int(request.args.get('page', 1)); size = int(request.args.get('page_size', 10))
    sql = ("SELECT a.*, c.company_name, o.order_no FROM allocation_order a"
           " JOIN company c ON c.company_id=a.company_id"
           " JOIN collective_order o ON o.order_id=a.order_id WHERE 1=1")
    args = []
    if request.args.get('status'):
        sql += " AND a.status=?"; args.append(request.args['status'])
    if request.args.get('order_no'):
        sql += " AND o.order_no LIKE ?"; args.append(f"%{request.args['order_no']}%")
    if request.args.get('company'):
        sql += " AND c.company_name LIKE ?"; args.append(f"%{request.args['company']}%")
    sql += " ORDER BY a.create_time DESC"
    rows, total = paginate(db, sql, args, page, size)
    return ok({'list': rows, 'total': total, 'page': page, 'page_size': size})


# ================= 到货确认 / 异常反馈 =================

@bp.get('/company/allocation/list')
@roles_required('R1')
@company_approved_required
def company_allocation_list():
    """下游企业：我的分拨单（含对账与反馈状态）"""
    db = get_db()
    cid = g.current_user['company_id']
    rows = []
    for a in db.execute(
            "SELECT a.*, o.order_no, o.supplier_id FROM allocation_order a"
            " JOIN collective_order o ON o.order_id=a.order_id"
            " WHERE a.company_id=? ORDER BY a.create_time DESC", (cid,)):
        item = dict(a)
        fb = db.execute("SELECT * FROM arrival_feedback WHERE alloc_id=? ORDER BY create_time DESC",
                        (a['alloc_id'],)).fetchone()
        item['feedback'] = dict(fb) if fb else None
        # 归档状态：由订单状态判断
        o = db.execute("SELECT status FROM collective_order WHERE order_id=?", (a['order_id'],)).fetchone()
        item['order_archived'] = bool(o and o['status'] == 'ARCHIVED')
        rows.append(item)
    return ok({'list': rows, 'total': len(rows), 'page': 1, 'page_size': len(rows) or 10})


@bp.post('/company/allocation/<int:aid>/confirm')
@roles_required('R1')
@company_approved_required
def allocation_confirm(aid):
    """企业确认到货：分拨单 → 已完成"""
    db = get_db()
    a = _get_alloc(db, aid)
    if not a:
        return err('分拨单不存在', http=404)
    if a['company_id'] != g.current_user['company_id']:
        return err('仅可确认本企业分拨单', code=403, http=403)
    if a['status'] not in ('TRANSIT', 'WAIT_CONFIRM'):
        return err(f'当前状态不可确认到货（{a["status"]}）')
    o = db.execute("SELECT status FROM collective_order WHERE order_id=?", (a['order_id'],)).fetchone()
    if o and o['status'] == 'ARCHIVED':
        return err('订单已归档，单据只读')
    db.execute("UPDATE allocation_order SET status='DONE' WHERE alloc_id=?", (aid,))
    db.commit()
    log_action('企业确认到货', f"分拨单 {a['alloc_no']} 确认完成",
               before=a['status'], after='DONE', ref_type='allocation_order', ref_id=aid)
    return ok({'alloc_id': aid, 'status': 'DONE'})


@bp.post('/company/allocation/<int:aid>/feedback')
@roles_required('R1')
@company_approved_required
def allocation_feedback(aid):
    """企业提交到货异常反馈"""
    d = request.get_json(force=True)
    desc = (d.get('description') or '').strip()
    if not desc:
        return err('异常描述必填')
    if len(desc) > 500:
        return err('异常描述不可超过500字')
    db = get_db()
    a = _get_alloc(db, aid)
    if not a:
        return err('分拨单不存在', http=404)
    if a['company_id'] != g.current_user['company_id']:
        return err('仅可反馈本企业分拨单', code=403, http=403)
    o = db.execute("SELECT status FROM collective_order WHERE order_id=?", (a['order_id'],)).fetchone()
    if o and o['status'] == 'ARCHIVED':
        return err('订单已归档，单据只读')
    cur = db.execute(
        "INSERT INTO arrival_feedback(alloc_id,company_id,description,attachment_url,status,create_time)"
        " VALUES(?,?,?,?, 'PENDING', ?)",
        (aid, g.current_user['company_id'], desc, (d.get('attachment') or '').strip() or None, _now()))
    db.commit()
    log_action('提交到货异常反馈', f"分拨单 {a['alloc_no']}：{desc[:50]}", ref_type='arrival_feedback', ref_id=cur.lastrowid)
    return ok({'feedback_id': cur.lastrowid, 'status': 'PENDING'})


@bp.get('/admin/feedback/list')
@roles_required('R4')
def admin_feedback_list():
    db = get_db()
    page = int(request.args.get('page', 1)); size = int(request.args.get('page_size', 10))
    sql = ("SELECT f.*, c.company_name, a.alloc_no FROM arrival_feedback f"
           " JOIN company c ON c.company_id=f.company_id"
           " JOIN allocation_order a ON a.alloc_id=f.alloc_id WHERE 1=1")
    args = []
    if request.args.get('status'):
        sql += " AND f.status=?"; args.append(request.args['status'])
    sql += " ORDER BY f.create_time DESC"
    rows, total = paginate(db, sql, args, page, size)
    return ok({'list': rows, 'total': total, 'page': page, 'page_size': size})


@bp.post('/admin/feedback/<int:fid>/resolve')
@roles_required('R4')
def feedback_resolve(fid):
    d = request.get_json(force=True)
    remark = (d.get('resolve_remark') or '').strip()
    if not remark:
        return err('处理结果说明必填')
    db = get_db()
    f = db.execute("SELECT * FROM arrival_feedback WHERE id=?", (fid,)).fetchone()
    if not f:
        return err('反馈记录不存在', http=404)
    if f['status'] != 'PENDING':
        return err('该反馈已处理')
    db.execute("UPDATE arrival_feedback SET status='RESOLVED',resolve_remark=? WHERE id=?",
               (remark, fid))
    db.commit()
    log_action('处理到货异常反馈', f"反馈#{fid}：{remark[:50]}", before='PENDING', after='RESOLVED',
               ref_type='arrival_feedback', ref_id=fid)
    return ok({'feedback_id': fid, 'status': 'RESOLVED'})


# ================= 对账单 =================

def _bill_status_of(db, table, bill_id):
    return db.execute(f"SELECT status FROM {table} WHERE bill_id=?", (bill_id,)).fetchone()


@bp.post('/admin/bill/company/create')
@roles_required('R4')
def company_bill_create():
    """按订单生成下游企业对账单（按企业聚合分拨明细，已生成企业跳过）"""
    d = request.get_json(force=True)
    db = get_db()
    if not d.get('order_id'):
        return err('缺少集采订单')
    o = db.execute("SELECT * FROM collective_order WHERE order_id=?", (d['order_id'],)).fetchone()
    if not o:
        return err('集采订单不存在', http=404)
    allocs = db.execute(
        "SELECT a.* FROM allocation_order a WHERE a.order_id=?", (o['order_id'],)).fetchall()
    if not allocs:
        return err('该订单尚无分拨单，无法生成企业对账单')
    period_type, period = _period_of_order(db, o['order_id'])
    now = _now()
    by_company = {}
    for a in allocs:
        used = db.execute("SELECT COUNT(*) FROM company_bill_detail WHERE alloc_id=?", (a['alloc_id'],)).fetchone()[0]
        if not used:
            by_company.setdefault(a['company_id'], []).append(a)
    created = []
    for cid, items in by_company.items():
        total = round2(sum(x['amount'] for x in items))
        cur = db.execute(
            "INSERT INTO company_bill(company_id,period,total_amount,status,create_time)"
            " VALUES(?,?,?,'PENDING',?)", (cid, period, total, now))
        bid = cur.lastrowid
        db.execute("UPDATE company_bill SET bill_no=? WHERE bill_id=?",
                   (_gen_no(db, 'company_bill', 'bill_no', 'CB'), bid))
        for x in items:
            db.execute(
                "INSERT INTO company_bill_detail(bill_id,alloc_id,ore_category,qty,unit_price,amount)"
                " VALUES(?,?,?,?,?,?)",
                (bid, x['alloc_id'], x['ore_category'], x['qty'], x['unit_price'], x['amount']))
        created.append(bid)
    db.commit()
    log_action('生成企业对账单', f"订单{o['order_no']} 新生成{len(created)}份（跳过已生成）",
               ref_type='company_bill')
    return ok({'created': len(created),
               'skipped_companies': len({a['company_id'] for a in allocs}) - len(created)})


@bp.post('/admin/bill/supplier/create')
@roles_required('R4')
def supplier_bill_create():
    """按订单生成上游供方对账单（一单一供方，防重复）"""
    d = request.get_json(force=True)
    db = get_db()
    if not d.get('order_id'):
        return err('缺少集采订单')
    o = db.execute("SELECT * FROM collective_order WHERE order_id=?", (d['order_id'],)).fetchone()
    if not o:
        return err('集采订单不存在', http=404)
    dup = db.execute("SELECT bill_id FROM supplier_bill WHERE order_id=?", (o['order_id'],)).fetchone()
    if dup:
        return err('该订单已生成供方对账单')
    period_type, period = _period_of_order(db, o['order_id'])
    now = _now()
    cur = db.execute(
        "INSERT INTO supplier_bill(supplier_id,order_id,period,total_amount,status,create_time)"
        " VALUES(?,?,?,?, 'PENDING', ?)", (o['supplier_id'], o['order_id'], period, o['total_amount'], now))
    bid = cur.lastrowid
    db.execute("UPDATE supplier_bill SET bill_no=? WHERE bill_id=?",
               (_gen_no(db, 'supplier_bill', 'bill_no', 'SB'), bid))
    db.commit()
    log_action('生成供方对账单', f"订单{o['order_no']} 金额{o['total_amount']}元",
               ref_type='supplier_bill', ref_id=bid)
    return ok({'bill_id': bid})


def _bill_action(db, table, bill_id, action, d, owner_col):
    """校验并执行对账单确认/异议；失败返回错误响应，成功返回状态字符串"""
    b = db.execute(f"SELECT * FROM {table} WHERE bill_id=?", (bill_id,)).fetchone()
    if not b:
        return err('对账单不存在', http=404)
    if b[owner_col] != g.current_user['company_id']:
        return err('仅可操作本企业对账单', code=403, http=403)
    if b['status'] == 'SETTLED':
        return err('对账单已结清，不可再操作')
    if action == 'confirm':
        if b['status'] not in ('PENDING', 'DISPUTE'):
            return err(f'当前状态不可确认（{b["status"]}）')
        db.execute(f"UPDATE {table} SET status='CONFIRMED',confirm_time=? WHERE bill_id=?", (_now(), bill_id))
        return 'CONFIRMED'
    # dispute
    reason = (d.get('reason') or '').strip()
    if not reason:
        return err('异议原因必填')
    if len(reason) > 300:
        return err('异议原因不可超过300字')
    if b['status'] not in ('PENDING', 'CONFIRMED'):
        return err(f'当前状态不可提出异议（{b["status"]}）')
    db.execute(f"UPDATE {table} SET status='DISPUTE',dispute_reason=? WHERE bill_id=?", (reason, bill_id))
    return 'DISPUTE'


@bp.post('/company/bill/<int:bid>/confirm')
@roles_required('R1')
@company_approved_required
def company_bill_confirm(bid):
    db = get_db()
    res = _bill_action(db, 'company_bill', bid, 'confirm', request.get_json(force=True, silent=True) or {}, 'company_id')
    if isinstance(res, str):
        db.commit()
        log_action('企业确认对账单', f"对账单#{bid} 确认无误", ref_type='company_bill', ref_id=bid)
        return ok({'bill_id': bid, 'status': res})
    return res


@bp.post('/company/bill/<int:bid>/dispute')
@roles_required('R1')
@company_approved_required
def company_bill_dispute(bid):
    db = get_db()
    d = request.get_json(force=True)
    res = _bill_action(db, 'company_bill', bid, 'dispute', d, 'company_id')
    if isinstance(res, str):
        db.commit()
        log_action('企业对账异议', f"对账单#{bid} 异议：{(d.get('reason') or '')[:50]}",
                   ref_type='company_bill', ref_id=bid)
        return ok({'bill_id': bid, 'status': res})
    return res


@bp.post('/supplier/bill/<int:bid>/confirm')
@roles_required('R2')
@company_approved_required
def supplier_bill_confirm(bid):
    db = get_db()
    res = _bill_action(db, 'supplier_bill', bid, 'confirm', request.get_json(force=True, silent=True) or {}, 'supplier_id')
    if isinstance(res, str):
        db.commit()
        log_action('供方确认对账单', f"供方对账单#{bid} 确认无误", ref_type='supplier_bill', ref_id=bid)
        return ok({'bill_id': bid, 'status': res})
    return res


@bp.post('/supplier/bill/<int:bid>/dispute')
@roles_required('R2')
@company_approved_required
def supplier_bill_dispute(bid):
    db = get_db()
    d = request.get_json(force=True)
    res = _bill_action(db, 'supplier_bill', bid, 'dispute', d, 'supplier_id')
    if isinstance(res, str):
        db.commit()
        log_action('供方对账异议', f"供方对账单#{bid} 异议：{(d.get('reason') or '')[:50]}",
                   ref_type='supplier_bill', ref_id=bid)
        return ok({'bill_id': bid, 'status': res})
    return res


@bp.post('/admin/bill/company/<int:bid>/settle')
@roles_required('R4')
def company_bill_settle(bid):
    d = request.get_json(force=True)
    db = get_db()
    b = db.execute("SELECT * FROM company_bill WHERE bill_id=?", (bid,)).fetchone()
    if not b:
        return err('对账单不存在', http=404)
    if b['status'] not in ('CONFIRMED', 'DISPUTE'):
        return err(f'当前状态不可结清（{b["status"]}）')
    db.execute("UPDATE company_bill SET status='SETTLED',settle_remark=?,settle_time=? WHERE bill_id=?",
               ((d.get('remark') or '').strip() or None, _now(), bid))
    db.commit()
    log_action('企业对账结清', f"对账单#{bid} 已结清", after='SETTLED', ref_type='company_bill', ref_id=bid)
    return ok({'bill_id': bid, 'status': 'SETTLED'})


@bp.post('/admin/bill/supplier/<int:bid>/settle')
@roles_required('R4')
def supplier_bill_settle(bid):
    d = request.get_json(force=True)
    db = get_db()
    b = db.execute("SELECT * FROM supplier_bill WHERE bill_id=?", (bid,)).fetchone()
    if not b:
        return err('对账单不存在', http=404)
    if b['status'] not in ('CONFIRMED', 'DISPUTE'):
        return err(f'当前状态不可结清（{b["status"]}）')
    db.execute("UPDATE supplier_bill SET status='SETTLED',settle_remark=?,settle_time=? WHERE bill_id=?",
               ((d.get('remark') or '').strip() or None, _now(), bid))
    db.commit()
    log_action('供方对账结清', f"供方对账单#{bid} 已结清", after='SETTLED', ref_type='supplier_bill', ref_id=bid)
    return ok({'bill_id': bid, 'status': 'SETTLED'})


@bp.get('/company/bill/list')
@roles_required('R1')
@company_approved_required
def company_bill_list():
    db = get_db()
    rows = [dict(x) for x in db.execute(
        "SELECT * FROM company_bill WHERE company_id=? ORDER BY create_time DESC",
        (g.current_user['company_id'],))]
    for r in rows:
        r['details'] = [dict(x) for x in db.execute(
            "SELECT d.*, a.alloc_no, o.order_no, a.destination FROM company_bill_detail d"
            " JOIN allocation_order a ON a.alloc_id=d.alloc_id"
            " JOIN collective_order o ON o.order_id=a.order_id"
            " WHERE d.bill_id=?", (r['bill_id'],))]
    return ok({'list': rows, 'total': len(rows), 'page': 1, 'page_size': len(rows) or 10})


@bp.get('/supplier/bill/list')
@roles_required('R2')
@company_approved_required
def supplier_bill_list():
    db = get_db()
    rows = [dict(x) for x in db.execute(
        "SELECT b.*, o.order_no, o.ore_category, o.total_qty FROM supplier_bill b"
        " JOIN collective_order o ON o.order_id=b.order_id"
        " WHERE b.supplier_id=? ORDER BY b.create_time DESC", (g.current_user['company_id'],))]
    return ok({'list': rows, 'total': len(rows), 'page': 1, 'page_size': len(rows) or 10})


@bp.get('/admin/bill/list')
@roles_required('R4')
def admin_bill_list():
    """平台对账总台账：企业单与供方单合并视图"""
    db = get_db()
    kind = request.args.get('kind', 'company')
    page = int(request.args.get('page', 1)); size = int(request.args.get('page_size', 10))
    if kind == 'supplier':
        base = ("SELECT b.*, c.company_name AS peer_name, o.order_no FROM supplier_bill b"
                " JOIN company c ON c.company_id=b.supplier_id"
                " JOIN collective_order o ON o.order_id=b.order_id WHERE 1=1")
    else:
        base = ("SELECT b.*, c.company_name AS peer_name FROM company_bill b"
                " JOIN company c ON c.company_id=b.company_id WHERE 1=1")
    args = []
    if request.args.get('status'):
        base += " AND b.status=?"; args.append(request.args['status'])
    if request.args.get('period'):
        base += " AND b.period=?"; args.append(request.args['period'])
    base += " ORDER BY b.create_time DESC"
    rows, total = paginate(db, base, args, page, size)
    return ok({'list': rows, 'total': total, 'page': page, 'page_size': size})


@bp.get('/company/bill/<int:bid>/export')
@roles_required('R1')
@company_approved_required
def company_bill_export(bid):
    """导出企业对账单 Excel"""
    db = get_db()
    b = db.execute("SELECT * FROM company_bill WHERE bill_id=? AND company_id=?",
                   (bid, g.current_user['company_id'])).fetchone()
    if not b:
        return err('对账单不存在', http=404)
    c = db.execute("SELECT company_name FROM company WHERE company_id=?", (b['company_id'],)).fetchone()
    rows = [[d['alloc_no'], d['order_no'], d['ore_category'], d['qty'], d['unit_price'], d['amount'],
             d['destination']]
            for d in db.execute(
                "SELECT d.*, a.alloc_no, o.order_no, a.destination FROM company_bill_detail d"
                " JOIN allocation_order a ON a.alloc_id=d.alloc_id"
                " JOIN collective_order o ON o.order_id=a.order_id WHERE d.bill_id=?", (bid,))]
    log_action('导出企业对账单', f"{b['bill_no']}", ref_type='company_bill', ref_id=bid)
    return export_excel(
        ['分拨单号', '集采订单号', '品类', '吨数', '单价(元/吨)', '金额(元)', '交货地'],
        [(f"对账明细 {b['bill_no']}（周期 {b['period']} · {c['company_name']} · 合计 {b['total_amount']} 元 · 状态 {b['status']}）", rows)],
        f"企业对账单-{b['bill_no']}.xlsx")


# ================= 归档 =================

@bp.post('/admin/archive')
@roles_required('R4')
def archive_order():
    """归档：全部分拨确认完成 + 企业/供方对账单全部结清"""
    d = request.get_json(force=True)
    db = get_db()
    if not d.get('order_id'):
        return err('缺少集采订单')
    o = db.execute("SELECT * FROM collective_order WHERE order_id=?", (d['order_id'],)).fetchone()
    if not o:
        return err('集采订单不存在', http=404)
    if o['status'] == 'ARCHIVED':
        return err('该订单已归档')
    allocs = db.execute("SELECT * FROM allocation_order WHERE order_id=?", (o['order_id'],)).fetchall()
    if not allocs:
        return err('该订单尚未分拨，不可归档')
    undone = [a['alloc_no'] for a in allocs if a['status'] != 'DONE']
    if undone:
        return err(f'存在未确认到货的分拨单：{",".join(undone[:5])}')
    uncovered = [a['alloc_no'] for a in allocs if not db.execute(
        "SELECT 1 FROM company_bill_detail WHERE alloc_id=?", (a['alloc_id'],)).fetchone()]
    if uncovered:
        return err(f'存在未生成企业对账单的分拨单：{",".join(uncovered[:5])}')
    unf_c = db.execute(
        "SELECT COUNT(*) FROM company_bill WHERE status!='SETTLED' AND bill_id IN"
        " (SELECT bill_id FROM company_bill_detail WHERE alloc_id IN"
        "  (SELECT alloc_id FROM allocation_order WHERE order_id=?))", (o['order_id'],)).fetchone()[0]
    if unf_c:
        return err(f'存在未结清的企业对账单 {unf_c} 份，不可归档')
    sup = db.execute("SELECT bill_id FROM supplier_bill WHERE order_id=?", (o['order_id'],)).fetchone()
    if not sup:
        return err('尚未生成供方对账单，不可归档')
    unf_s = db.execute("SELECT COUNT(*) FROM supplier_bill WHERE order_id=? AND status!='SETTLED'",
                       (o['order_id'],)).fetchone()[0]
    if unf_s:
        return err('供方对账单未结清，不可归档')
    task = db.execute("SELECT * FROM collective_task WHERE task_id=?", (o['task_id'],)).fetchone()
    period_type, period = _period_of_order(db, o['order_id'])
    now = _now()
    db.execute(
        "INSERT INTO archive_record(order_id,task_id,archive_time,operator_id,archive_summary)"
        " VALUES(?,?,?,?,?)",
        (o['order_id'], o['task_id'], now, g.current_user['user_id'],
         d.get('summary') or ''))
    db.execute("UPDATE collective_order SET status='ARCHIVED' WHERE order_id=?", (o['order_id'],))
    db.execute("UPDATE collective_task SET status='ARCHIVED' WHERE task_id=?", (o['task_id'],))
    # 需求闭环 → DISTRIBUTED（含商城预购订单，明细 demand_id 负数对应 mall_order.order_id）
    db.execute(
        "UPDATE purchase_demand SET status='DISTRIBUTED',update_time=?"
        " WHERE demand_id IN (SELECT demand_id FROM collective_list_detail WHERE list_id=("
        " SELECT list_id FROM collective_task WHERE task_id=?)) AND status='IN_EXEC'",
        (now, o['task_id']))
    db.execute(
        "UPDATE mall_order SET status='DISTRIBUTED'"
        " WHERE order_id IN (SELECT -demand_id FROM collective_list_detail WHERE list_id=("
        " SELECT list_id FROM collective_task WHERE task_id=?)) AND status='IN_EXEC'",
        (o['task_id'],))
    db.commit()
    log_action('订单归档', f"订单{o['order_no']} 归档完成，需求全链路闭环", before=o['status'],
               after='ARCHIVED', ref_type='collective_order', ref_id=o['order_id'])
    return ok({'order_id': o['order_id'], 'status': 'ARCHIVED', 'archive_time': now})


@bp.get('/admin/archive/list')
@roles_required('R4')
def archive_list():
    db = get_db()
    rows = [dict(x) for x in db.execute(
        "SELECT ar.*, o.order_no, o.ore_category, o.total_amount FROM archive_record ar"
        " JOIN collective_order o ON o.order_id=ar.order_id"
        " ORDER BY ar.archive_time DESC")]
    return ok({'list': rows})


# ================= 履约台账 =================

@bp.get('/admin/ledger')
@roles_required('R4')
def ledger():
    """全周期履约台账：分拨 + 对账 + 归档状态联合视图"""
    db = get_db()
    page = int(request.args.get('page', 1)); size = int(request.args.get('page_size', 10))
    sql = ("SELECT a.*, c.company_name, o.order_no, o.status AS order_status,"
           " t.task_no, l.period, l.period_type"
           " FROM allocation_order a"
           " JOIN company c ON c.company_id=a.company_id"
           " JOIN collective_order o ON o.order_id=a.order_id"
           " JOIN collective_task t ON t.task_id=o.task_id"
           " JOIN collective_list l ON l.list_id=t.list_id WHERE 1=1")
    args = []
    if request.args.get('period'):
        sql += " AND l.period=?"; args.append(request.args['period'])
    if request.args.get('company'):
        sql += " AND c.company_name LIKE ?"; args.append(f"%{request.args['company']}%")
    if request.args.get('ore_category'):
        sql += " AND a.ore_category=?"; args.append(request.args['ore_category'])
    if request.args.get('status'):
        sql += " AND a.status=?"; args.append(request.args['status'])
    sql += " ORDER BY a.create_time DESC"
    rows, total = paginate(db, sql, args, page, size)
    for r in rows:
        cb = db.execute(
            "SELECT b.status FROM company_bill b JOIN company_bill_detail d ON d.bill_id=b.bill_id"
            " WHERE d.alloc_id=? LIMIT 1", (r['alloc_id'],)).fetchone()
        r['bill_status'] = cb['status'] if cb else None
        r['archived'] = 1 if r['order_status'] == 'ARCHIVED' else 0
    return ok({'list': rows, 'total': total, 'page': page, 'page_size': size})


@bp.get('/admin/ledger/export')
@roles_required('R4')
def ledger_export():
    db = get_db()
    rows = []
    for r in db.execute(
            "SELECT a.*, c.company_name, o.order_no, o.status AS order_status, l.period"
            " FROM allocation_order a"
            " JOIN company c ON c.company_id=a.company_id"
            " JOIN collective_order o ON o.order_id=a.order_id"
            " JOIN collective_task t ON t.task_id=o.task_id"
            " JOIN collective_list l ON l.list_id=t.list_id ORDER BY a.create_time DESC"):
        cb = db.execute(
            "SELECT b.status FROM company_bill b JOIN company_bill_detail d ON d.bill_id=b.bill_id"
            " WHERE d.alloc_id=? LIMIT 1", (r['alloc_id'],)).fetchone()
        rows.append([r['period'], r['alloc_no'], r['order_no'], r['company_name'],
                     r['ore_category'], r['qty'], r['unit_price'], r['amount'],
                     r['destination'], r['status'], cb['status'] if cb else '未生成',
                     '已归档' if r['order_status'] == 'ARCHIVED' else '未归档'])
    log_action('导出履约台账', f"共{len(rows)}行", ref_type='allocation_order')
    return export_excel(
        ['周期', '分拨单号', '订单号', '下游企业', '品类', '吨数', '单价(元/吨)', '金额(元)',
         '交货地', '分拨状态', '对账状态', '归档'],
        [('履约台账', rows)], '履约台账.xlsx')
