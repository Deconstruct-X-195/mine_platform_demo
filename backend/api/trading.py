# -*- coding: utf-8 -*-
"""集采交易模块 (PRD-04)：集采任务创建/批量询价下发/供方报价-修改-拒绝/比价视图/锁货生成集采订单"""
import re
from flask import Blueprint, request, g
from ..db import get_db, _now
from ..utils import ok, err, log_action, paginate, round2, gen_no, export_excel
from ..auth import roles_required, company_approved_required

bp = Blueprint('trading', __name__)

DEADLINE_RE = re.compile(r'^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$')

# 询价任务状态机: WAIT_QUOTE → QUOTED / REFUSED；终态 NOT_SELECTED / LOCKED
# 集采任务状态机: WAIT_QUOTE(待询价) → QUOTING(比价中) → LOCKED(已锁货)


def _get_task(db, tid):
    return db.execute("SELECT * FROM collective_task WHERE task_id=?", (tid,)).fetchone()


# ================= 平台端 (R4) =================

@bp.post('/admin/task/create')
@roles_required('R4')
def task_create():
    """创建集采任务并批量下发询价（从清单 + 资源台账多选）"""
    d = request.get_json(force=True)
    db = get_db()
    if not d.get('list_id'):
        return err('缺少集采清单')
    head = db.execute("SELECT * FROM collective_list WHERE list_id=?", (d['list_id'],)).fetchone()
    if not head:
        return err('集采清单不存在', http=404)
    if head['status'] != 'ACTIVE':
        return err('该清单已建询价任务，不可重复创建')
    rid_list = d.get('resource_ids') or []
    if not isinstance(rid_list, list) or len(set(rid_list)) < 1:
        return err('请至少选择1家供货方货源')
    if len(rid_list) != len(set(rid_list)):
        return err('供货方货源不可重复选择')
    deadline = (d.get('quote_deadline') or '').strip()
    if not DEADLINE_RE.match(deadline):
        return err('报价截止时间格式应为 YYYY-MM-DD HH:MM')
    now = _now()
    if deadline <= now:
        return err('报价截止时间必须晚于当前时间')

    cat = db.execute("SELECT DISTINCT ore_category FROM collective_list_detail WHERE list_id=?",
                     (d['list_id'],)).fetchall()
    if len(cat) != 1:
        return err('清单品类异常，无法发起询价')
    category = cat[0]['ore_category']

    resources = db.execute(
        f"SELECT * FROM ore_resource WHERE resource_id IN ({','.join('?' * len(rid_list))})",
        rid_list).fetchall()
    if len(resources) != len(rid_list):
        return err('部分货源不存在')
    for r in resources:
        if r['status'] != 'ON_SHELF':
            return err(f"货源 #{r['resource_id']} 不在架（{r['status']}），不可询价")
        if r['ore_category'] != category:
            return err(f"货源 #{r['resource_id']} 品类与清单不符")

    cur = db.execute(
        "INSERT INTO collective_task(list_id,ore_category,total_qty,indicator_req,supply_time,"
        "quote_deadline,status,creator_id,create_time) VALUES(?,?,?,?,?,?,?,?,?)",
        (d['list_id'], category, head['total_qty'],
         (d.get('indicator_req') or '').strip() or None,
         (d.get('supply_time') or '').strip() or None,
         deadline, 'WAIT_QUOTE', g.current_user['user_id'], now))
    task_id = cur.lastrowid
    db.execute("UPDATE collective_task SET task_no=? WHERE task_id=?", (gen_no('CT', task_id), task_id))
    for r in resources:
        db.execute(
            "INSERT INTO inquiry_task(task_id,supplier_id,resource_id,status,create_time,update_time)"
            " VALUES(?,?,?,?,?,?)", (task_id, r['supplier_id'], r['resource_id'], 'WAIT_QUOTE', now, now))
    db.execute("UPDATE collective_list SET status='INQUIRED' WHERE list_id=?", (d['list_id'],))
    db.commit()
    log_action('创建集采任务并下发询价', f"任务CT-{task_id}，供方{len(resources)}家，截止{deadline}",
               ref_type='collective_task', ref_id=task_id)
    task = _get_task(db, task_id)
    return ok({'task': dict(task), 'inquiry_count': len(resources)})


@bp.get('/admin/task/list')
@roles_required('R4')
def task_list():
    db = get_db()
    page = int(request.args.get('page', 1)); size = int(request.args.get('page_size', 10))
    sql = ("SELECT t.*, l.list_no FROM collective_task t"
           " JOIN collective_list l ON l.list_id=t.list_id WHERE 1=1")
    args = []
    if request.args.get('status'):
        sql += " AND t.status=?"; args.append(request.args['status'])
    if request.args.get('ore_category'):
        sql += " AND t.ore_category=?"; args.append(request.args['ore_category'])
    sql += " ORDER BY t.create_time DESC"
    rows, total = paginate(db, sql, args, page, size)
    for r in rows:
        r['inquiry_total'] = db.execute(
            "SELECT COUNT(*) FROM inquiry_task WHERE task_id=?", (r['task_id'],)).fetchone()[0]
        r['quoted_total'] = db.execute(
            "SELECT COUNT(*) FROM inquiry_task WHERE task_id=? AND status IN ('QUOTED','LOCKED')",
            (r['task_id'],)).fetchone()[0]
        r['order_count'] = db.execute(
            "SELECT COUNT(*) FROM collective_order WHERE task_id=?", (r['task_id'],)).fetchone()[0]
    return ok({'list': rows, 'total': total, 'page': page, 'page_size': size})


@bp.get('/admin/task/<int:tid>/compare')
@roles_required('R4')
def task_compare(tid):
    """比价视图：所有供方报价按单价升序"""
    db = get_db()
    task = _get_task(db, tid)
    if not task:
        return err('集采任务不存在', http=404)
    head = db.execute("SELECT * FROM collective_list WHERE list_id=?", (task['list_id'],)).fetchone()
    rows = [dict(x) for x in db.execute(
        "SELECT i.*, c.company_name, r.origin, r.grade, r.max_qty AS resource_max_qty"
        " FROM inquiry_task i"
        " JOIN company c ON c.company_id=i.supplier_id"
        " LEFT JOIN ore_resource r ON r.resource_id=i.resource_id"
        " WHERE i.task_id=?"
        " ORDER BY CASE WHEN i.quote_price IS NULL THEN 1 ELSE 0 END, i.quote_price ASC",
        (tid,))]
    return ok({'task': dict(task), 'list_no': head['list_no'] if head else None, 'compares': rows})


@bp.post('/admin/task/<int:tid>/lock')
@roles_required('R4')
def task_lock(tid):
    """锁货确认：生成集采总供货订单（一家一单），保留下游申报明细"""
    d = request.get_json(force=True)
    locks = d.get('locks')
    if not isinstance(locks, list) or not locks:
        return err('请提供锁货明细 locks')
    db = get_db()
    task = _get_task(db, tid)
    if not task:
        return err('集采任务不存在', http=404)
    if task['status'] not in ('WAIT_QUOTE', 'QUOTING'):
        return err('任务当前状态不可锁货')
    now = _now()
    total_lock = 0.0
    plan = []
    for lk in locks:
        try:
            iid = int(lk.get('inquiry_id'))
        except (TypeError, ValueError):
            return err('锁货明细缺少 inquiry_id')
        inq = db.execute("SELECT * FROM inquiry_task WHERE inquiry_id=?", (iid,)).fetchone()
        if not inq or inq['task_id'] != tid:
            return err(f"询价记录 #{iid} 不属于该任务")
        if inq['status'] != 'QUOTED':
            return err(f"询价记录 #{iid} 当前状态不可锁货（{inq['status']}）")
        try:
            price = round2(lk.get('unit_price')); qty = round2(lk.get('qty'))
        except (TypeError, ValueError):
            return err('锁货单价/吨数必须为数字')
        if price <= 0 or qty <= 0:
            return err('锁货单价、吨数必须大于0')
        if qty > (inq['quote_qty'] or 0):
            return err(f"锁货吨数不可超过供方报价量（#{iid}）")
        plan.append((inq, price, qty))
        total_lock += qty
    if total_lock + 1e-9 < task['total_qty']:
        return err(f"锁货合计 {total_lock} 吨未覆盖需求量 {task['total_qty']} 吨")

    details = db.execute(
        "SELECT * FROM collective_list_detail WHERE list_id=?", (task['list_id'],)).fetchall()
    locked_ids = []
    for inq, price, qty in plan:
        cur = db.execute(
            "INSERT INTO collective_order(task_id,supplier_id,ore_category,total_qty,unit_price,"
            "total_amount,supply_time,status,create_time) VALUES(?,?,?,?,?,?,?,?,?)",
            (tid, inq['supplier_id'], task['ore_category'], qty, price,
             round2(price * qty), (d.get('supply_time') or task['supply_time']), 'LOCKED', now))
        oid = cur.lastrowid
        db.execute("UPDATE collective_order SET order_no=? WHERE order_id=?", (gen_no('CO', oid), oid))
        for dt in details:
            db.execute(
                "INSERT INTO collective_order_detail(order_id,demand_id,company_id,ore_category,"
                "qty,grade_req,expected_arrival) VALUES(?,?,?,?,?,?,?)",
                (oid, dt['demand_id'], dt['company_id'], dt['ore_category'],
                 dt['qty'], dt['grade_req'], dt['expected_arrival']))
        db.execute("UPDATE inquiry_task SET status='LOCKED',update_time=? WHERE inquiry_id=?",
                   (now, inq['inquiry_id']))
        log_action('锁货生成订单', f"任务{task['task_no']} 锁定供方订单（含明细）",
                   ref_type='collective_order', ref_id=oid)
        locked_ids.append(inq['inquiry_id'])
    # 未锁货报价方 → 未选中
    db.execute(
        "UPDATE inquiry_task SET status='NOT_SELECTED',update_time=?"
        " WHERE task_id=? AND status IN ('WAIT_QUOTE','QUOTED')", (now, tid))
    db.execute("UPDATE collective_task SET status='LOCKED' WHERE task_id=?", (tid,))
    # 需求进入集采执行中（含商城预购订单，明细 demand_id 负数对应 mall_order.order_id）
    db.execute(
        "UPDATE purchase_demand SET status='IN_EXEC',update_time=?"
        " WHERE demand_id IN (SELECT demand_id FROM collective_list_detail WHERE list_id=?)"
        " AND status='IN_LIST'", (now, task['list_id']))
    db.execute(
        "UPDATE mall_order SET status='IN_EXEC'"
        " WHERE order_id IN (SELECT -demand_id FROM collective_list_detail WHERE list_id=?)"
        " AND status='IN_LIST'", (task['list_id'],))
    db.commit()
    log_action('确认锁货', f"任务{task['task_no']}，锁货{len(plan)}家合计{total_lock}吨",
               before='QUOTING', after='LOCKED', ref_type='collective_task', ref_id=tid)
    orders = [dict(x) for x in db.execute(
        "SELECT * FROM collective_order WHERE task_id=?", (tid,))]
    return ok({'orders': orders})


@bp.get('/admin/order/list')
@roles_required('R4')
def order_list():
    db = get_db()
    page = int(request.args.get('page', 1)); size = int(request.args.get('page_size', 10))
    sql = ("SELECT o.*, c.company_name AS supplier_name, t.task_no FROM collective_order o"
           " JOIN company c ON c.company_id=o.supplier_id"
           " JOIN collective_task t ON t.task_id=o.task_id WHERE 1=1")
    args = []
    if request.args.get('status'):
        sql += " AND o.status=?"; args.append(request.args['status'])
    sql += " ORDER BY o.create_time DESC"
    rows, total = paginate(db, sql, args, page, size)
    return ok({'list': rows, 'total': total, 'page': page, 'page_size': size})


@bp.get('/admin/order/<int:oid>')
@roles_required('R4')
def order_detail(oid):
    """订单详情：含下游企业申报明细（仅平台可见）"""
    db = get_db()
    o = db.execute(
        "SELECT o.*, c.company_name AS supplier_name, t.task_no, l.list_no FROM collective_order o"
        " JOIN company c ON c.company_id=o.supplier_id"
        " JOIN collective_task t ON t.task_id=o.task_id"
        " JOIN collective_list l ON l.list_id=t.list_id WHERE order_id=?", (oid,)).fetchone()
    if not o:
        return err('集采订单不存在', http=404)
    details = [dict(x) for x in db.execute(
        "SELECT d.*, c.company_name FROM collective_order_detail d"
        " JOIN company c ON c.company_id=d.company_id WHERE d.order_id=?", (oid,))]
    return ok({**dict(o), 'details': details})


@bp.get('/admin/task/<int:tid>/compare/export')
@roles_required('R4')
def compare_export(tid):
    """导出报价对比表"""
    db = get_db()
    task = _get_task(db, tid)
    if not task:
        return err('集采任务不存在', http=404)
    rows = []
    for x in db.execute(
            "SELECT i.*, c.company_name, r.origin, r.grade FROM inquiry_task i"
            " JOIN company c ON c.company_id=i.supplier_id"
            " LEFT JOIN ore_resource r ON r.resource_id=i.resource_id"
            " WHERE i.task_id=?"
            " ORDER BY CASE WHEN i.quote_price IS NULL THEN 1 ELSE 0 END, i.quote_price ASC", (tid,)):
        rows.append([task['task_no'], x['company_name'], x['origin'], x['grade'],
                     x['quote_price'], x['quote_qty'], x['supply_period'],
                     x['indicator_commit'], x['remark'], x['status']])
    log_action('导出报价对比表', f"任务{task['task_no']}", ref_type='collective_task', ref_id=tid)
    return export_excel(
        ['任务编号', '供方', '产地', '品位', '报价单价(元/吨)', '可供吨数', '供货周期',
         '指标承诺', '备注', '状态'],
        [('报价对比', rows)], f"报价对比表-{task['task_no']}.xlsx")


# ================= 供方端 (R2) =================

@bp.get('/supplier/inquiry/list')
@roles_required('R2')
@company_approved_required
def supplier_inquiry_list():
    """供方询价任务列表（不含下游企业明细）"""
    db = get_db()
    page = int(request.args.get('page', 1)); size = int(request.args.get('page_size', 10))
    sql = ("SELECT i.task_id,i.inquiry_id,i.status,i.quote_price,i.quote_qty,i.supply_period,"
           "i.indicator_commit,i.remark,i.refuse_reason,i.create_time,i.update_time,"
           "t.task_no,t.ore_category,t.total_qty,t.indicator_req,t.supply_time,t.quote_deadline,"
           "t.status AS task_status, r.origin, r.grade, r.max_qty AS resource_max_qty"
           " FROM inquiry_task i JOIN collective_task t ON t.task_id=i.task_id"
           " LEFT JOIN ore_resource r ON r.resource_id=i.resource_id"
           " WHERE i.supplier_id=?")
    args = [g.current_user['company_id']]
    if request.args.get('status'):
        sql += " AND i.status=?"; args.append(request.args['status'])
    sql += " ORDER BY i.create_time DESC"
    rows, total = paginate(db, sql, args, page, size)
    return ok({'list': rows, 'total': total, 'page': page, 'page_size': size})


def _quote_validate(db, iid, d, modify):
    """报价/修改报价共用校验，返回 (inquiry, error)"""
    inq = db.execute("SELECT * FROM inquiry_task WHERE inquiry_id=?", (iid,)).fetchone()
    if not inq:
        return None, ('询价记录不存在', 404)
    if inq['supplier_id'] != g.current_user['company_id']:
        return None, ('无权操作他人询价', 403)
    task = _get_task(db, inq['task_id'])
    if task['status'] == 'LOCKED':
        return None, ('该任务已锁货，不可再报价', 400)
    expect = 'QUOTED' if modify else 'WAIT_QUOTE'
    if inq['status'] != expect:
        return None, (f"当前状态不可{'修改' if modify else '提交'}报价（{inq['status']}）", 400)
    if task['quote_deadline'] and task['quote_deadline'] < _now():
        return None, ('已过报价截止时间', 400)
    try:
        price = round2(d.get('quote_price')); qty = round2(d.get('quote_qty'))
    except (TypeError, ValueError):
        return None, ('报价单价/可供吨数必须为数字', 400)
    if price <= 0 or qty <= 0:
        return None, ('报价单价、可供吨数必须大于0', 400)
    if inq['resource_id']:
        res = db.execute("SELECT max_qty FROM ore_resource WHERE resource_id=?",
                         (inq['resource_id'],)).fetchone()
        if res and qty > res['max_qty']:
            return None, (f"可供货吨数不可超过货源可供应量 {res['max_qty']} 吨", 400)
    period = (d.get('supply_period') or '').strip()
    if not period:
        return None, ('供货周期必填', 400)
    if len(period) > 100:
        return None, ('供货周期长度不可超过100', 400)
    return (inq, task, price, qty, period,
            (d.get('indicator_commit') or '').strip() or None,
            (d.get('remark') or '').strip() or None), None


@bp.post('/supplier/inquiry/<int:iid>/quote')
@roles_required('R2')
@company_approved_required
def inquiry_quote(iid):
    """提交报价"""
    db = get_db()
    packed, error = _quote_validate(db, iid, request.get_json(force=True), modify=False)
    if error:
        return err(error[0], http=error[1])
    inq, task, price, qty, period, commit, remark = packed
    now = _now()
    db.execute(
        "UPDATE inquiry_task SET status='QUOTED',quote_price=?,quote_qty=?,supply_period=?,"
        "indicator_commit=?,remark=?,refuse_reason=NULL,update_time=? WHERE inquiry_id=?",
        (price, qty, period, commit, remark, now, iid))
    db.execute("INSERT INTO quote_history(inquiry_id,quote_price,quote_qty,create_time) VALUES(?,?,?,?)",
               (iid, price, qty, now))
    if task['status'] == 'WAIT_QUOTE':
        db.execute("UPDATE collective_task SET status='QUOTING' WHERE task_id=?", (task['task_id'],))
    db.commit()
    log_action('提交报价', f"任务{task['task_no']}，单价{price}元/吨，可供{qty}吨",
               ref_type='inquiry_task', ref_id=iid)
    return ok({'inquiry_id': iid, 'status': 'QUOTED'})


@bp.put('/supplier/inquiry/<int:iid>/quote')
@roles_required('R2')
@company_approved_required
def inquiry_quote_modify(iid):
    """修改报价（截止前，保留历史版本）"""
    db = get_db()
    packed, error = _quote_validate(db, iid, request.get_json(force=True), modify=True)
    if error:
        return err(error[0], http=error[1])
    inq, task, price, qty, period, commit, remark = packed
    now = _now()
    db.execute(
        "UPDATE inquiry_task SET quote_price=?,quote_qty=?,supply_period=?,indicator_commit=?,"
        "remark=?,update_time=? WHERE inquiry_id=?", (price, qty, period, commit, remark, now, iid))
    db.execute("INSERT INTO quote_history(inquiry_id,quote_price,quote_qty,create_time) VALUES(?,?,?,?)",
               (iid, price, qty, now))
    db.commit()
    log_action('修改报价', f"任务{task['task_no']}，单价{price}元/吨，可供{qty}吨",
               ref_type='inquiry_task', ref_id=iid)
    return ok({'inquiry_id': iid, 'status': 'QUOTED'})


@bp.post('/supplier/inquiry/<int:iid>/refuse')
@roles_required('R2')
@company_approved_required
def inquiry_refuse(iid):
    """拒绝本次询价"""
    d = request.get_json(force=True)
    reason = (d.get('reason') or '').strip()
    if not reason:
        return err('拒绝原因必填')
    if len(reason) > 200:
        return err('拒绝原因不可超过200字')
    db = get_db()
    inq = db.execute("SELECT * FROM inquiry_task WHERE inquiry_id=?", (iid,)).fetchone()
    if not inq:
        return err('询价记录不存在', http=404)
    if inq['supplier_id'] != g.current_user['company_id']:
        return err('无权操作他人询价', code=403, http=403)
    if inq['status'] not in ('WAIT_QUOTE', 'QUOTED'):
        return err(f"当前状态不可拒绝（{inq['status']}）")
    now = _now()
    db.execute("UPDATE inquiry_task SET status='REFUSED',refuse_reason=?,update_time=? WHERE inquiry_id=?",
               (reason, now, iid))
    db.commit()
    log_action('拒绝询价', reason, ref_type='inquiry_task', ref_id=iid)
    return ok({'inquiry_id': iid, 'status': 'REFUSED'})
