# -*- coding: utf-8 -*-
"""后台管理模块：企业资质审核（全局前置）、账号管理、字典维护、看板、单据检索、日志审计"""
from flask import Blueprint, request, g
from ..db import get_db, _now
from ..utils import ok, err, log_action, paginate, export_excel
from ..auth import roles_required, current_user
import secrets, hashlib

bp = Blueprint('admin', __name__)


# ---------------- 工作台统计（各角色首页） ----------------
@bp.get('/dashboard/workbench')
def workbench():
    """按角色返回首页统计卡片数据"""
    user = current_user()
    if not user:
        return err('未登录', code=401, http=401)
    db = get_db()
    role = user['role_code']
    data = {}
    if role == 'R4':
        data = {
            'comp_total': db.execute("SELECT COUNT(*) FROM company").fetchone()[0],
            'comp_pending': db.execute("SELECT COUNT(*) FROM company WHERE audit_status='PENDING'").fetchone()[0],
            'demand_total': db.execute("SELECT COUNT(*) FROM purchase_demand").fetchone()[0],
            'order_total': db.execute("SELECT COUNT(*) FROM collective_order").fetchone()[0],
        }
    elif role == 'R1':
        data = {
            'demand_mine': db.execute("SELECT COUNT(*) FROM purchase_demand WHERE company_id=?",
                                      (user['company_id'],)).fetchone()[0],
            'alloc_wait': db.execute("SELECT COUNT(*) FROM allocation_order WHERE company_id=? AND status IN ('WAIT_CONFIRM')",
                                     (user['company_id'],)).fetchone()[0],
            'bill_wait': db.execute("SELECT COUNT(*) FROM company_bill WHERE company_id=? AND status='PENDING'",
                                    (user['company_id'],)).fetchone()[0],
        }
    elif role == 'R2':
        data = {
            'res_mine': db.execute("SELECT COUNT(*) FROM ore_resource WHERE supplier_id=?",
                                   (user['company_id'],)).fetchone()[0],
            'inq_wait': db.execute("SELECT COUNT(*) FROM inquiry_task WHERE supplier_id=? AND status='WAIT_QUOTE'",
                                   (user['company_id'],)).fetchone()[0],
        }
    elif role == 'R3':
        data = {
            'logi_mine': db.execute(
                "SELECT COUNT(*) FROM logistics_task WHERE sea_partner_id=? OR port_partner_id=?"
                " OR warehouse_partner_id=? OR land_partner_id=?",
                (user['company_id'],) * 4).fetchone()[0],
        }
    return ok(data)


# ---------------- 企业资质审核 (PRD-08 §2.1，PRD-01 硬约束前置) ----------------
@bp.get('/admin/company/list')
@roles_required('R4')
def company_list():
    db = get_db()
    kw = request.args.get('keyword', '').strip()
    ctype = request.args.get('company_type', '')
    status = request.args.get('audit_status', '')
    page = int(request.args.get('page', 1)); size = int(request.args.get('page_size', 10))
    sql = ("SELECT c.*, u.username, u.user_id, u.status AS user_status FROM company c"
           " LEFT JOIN sys_user u ON u.company_id=c.company_id AND u.role_code != 'R4' WHERE 1=1")
    args = []
    if kw:
        sql += " AND (c.company_name LIKE ? OR c.contact LIKE ?)"
        args += [f'%{kw}%', f'%{kw}%']
    if ctype:
        sql += " AND c.company_type=?"; args.append(ctype)
    if status:
        sql += " AND c.audit_status=?"; args.append(status)
    sql += " ORDER BY c.create_time DESC"
    rows, total = paginate(db, sql, args, page, size,
                           f"SELECT COUNT(*) FROM ({sql})")
    for r in rows:
        r['qualifications'] = [dict(q) for q in db.execute(
            "SELECT id,cert_type,file_url,file_name,status,reject_reason FROM qualification"
            " WHERE company_id=?", (r['company_id'],)).fetchall()]
    return ok({'list': rows, 'total': total, 'page': page, 'page_size': size})


@bp.post('/admin/company/<int:cid>/audit')
@roles_required('R4')
def audit_company(cid):
    d = request.get_json(force=True)
    result = d.get('result')
    if result not in ('APPROVED', 'REJECTED'):
        return err('无效的审核结论')
    if result == 'REJECTED' and not (d.get('reject_reason') or '').strip():
        return err('驳回必须填写原因')
    db = get_db()
    comp = db.execute("SELECT * FROM company WHERE company_id=?", (cid,)).fetchone()
    if not comp:
        return err('企业不存在', http=404)
    if comp['audit_status'] == 'APPROVED':
        return err('该企业已审核通过，不可重复审核')
    now = _now()
    db.execute("UPDATE company SET audit_status=?, audit_remark=?, auditor_id=?, audit_time=? WHERE company_id=?",
               (result, d.get('reject_reason') or '审核通过', g.current_user['user_id'], now, cid))
    if result == 'APPROVED':
        db.execute("UPDATE qualification SET status='APPROVED', auditor_id=?, audit_time=? WHERE company_id=?",
                   (g.current_user['user_id'], now, cid))
    else:
        db.execute("UPDATE qualification SET status='REJECTED', auditor_id=?, audit_time=?, reject_reason=?"
                   " WHERE company_id=?", (g.current_user['user_id'], now, d.get('reject_reason'), cid))
    db.commit()
    log_action('企业资质审核', f"{comp['company_name']} 审核结果: {result}",
               before=comp['audit_status'], after=result, ref_type='company', ref_id=cid)
    return ok(message='审核完成')


# ---------------- 字典维护 (PRD-08 §2.3) ----------------
@bp.get('/admin/dict/list')
@roles_required('R4')
def dict_list():
    db = get_db()
    category = request.args.get('category', '')
    rows = db.execute("SELECT * FROM dict_item WHERE category=? ORDER BY sort, id",
                      (category,)).fetchall()
    return ok({'list': [dict(r) for r in rows], 'total': len(rows)})


@bp.post('/admin/dict')
@roles_required('R4')
def dict_save():
    d = request.get_json(force=True)
    category, code, name = d.get('category'), d.get('item_code'), d.get('item_name')
    if not all([category, code, name]):
        return err('缺少必填字段')
    db = get_db()
    if d.get('id'):
        db.execute("UPDATE dict_item SET item_name=?, sort=?, status=? WHERE id=? AND category=?",
                   (name, d.get('sort', 0), d.get('status', 1), d['id'], category))
    else:
        if db.execute("SELECT 1 FROM dict_item WHERE category=? AND item_code=?", (category, code)).fetchone():
            return err('该字典项已存在')
        db.execute("INSERT INTO dict_item(category,item_code,item_name,sort,status) VALUES(?,?,?,?,?)",
                   (category, code, name, d.get('sort', 0), d.get('status', 1)))
    db.commit()
    log_action('字典维护', f"{category}/{code}: {name}", ref_type='dict', ref_id=category)
    return ok(message='保存成功')


@bp.post('/admin/dict/<int:dict_id>/delete')
@roles_required('R4')
def dict_delete(dict_id):
    db = get_db()
    row = db.execute("SELECT * FROM dict_item WHERE id=?", (dict_id,)).fetchone()
    if not row:
        return err('字典项不存在', http=404)
    # PRD-14：已被业务单据引用的字典项不允许删除，只能停用
    used = _dict_item_used(db, row['category'], row['item_code'], row['item_name'])
    if used:
        return err('该字典项已被业务单据引用，不可删除，仅可停用')
    db.execute("DELETE FROM dict_item WHERE id=?", (dict_id,))
    db.commit()
    log_action('字典删除', f"{row['category']}/{row['item_code']}", ref_type='dict', ref_id=row['category'])
    return ok(message='删除成功')


def _dict_item_used(db, category, item_code, item_name):
    """检查字典项是否被业务数据引用：品类/周期等业务枚举列 + 指标模板"""
    checks = []
    if category in ('ORE_CATEGORY', 'PERIOD_TYPE'):
        checks.append(("SELECT 1 FROM purchase_demand WHERE ore_category=? OR period_type=? LIMIT 1",
                       (item_code, item_code)))
        checks.append(("SELECT 1 FROM ore_resource WHERE ore_category=? LIMIT 1", (item_code,)))
        checks.append(("SELECT 1 FROM collective_order WHERE ore_category=? LIMIT 1", (item_code,)))
        checks.append(("SELECT 1 FROM ore_inspect_report WHERE ore_category=? LIMIT 1", (item_code,)))
        checks.append(("SELECT 1 FROM ore_contract WHERE ore_category=? LIMIT 1", (item_code,)))
    if category == 'EXPENSE_TYPE':
        checks.append(("SELECT 1 FROM ore_expense_bill WHERE expense_type=? LIMIT 1", (item_code,)))
    if category == 'ORIGIN':
        checks.append(("SELECT 1 FROM ore_resource WHERE origin=? LIMIT 1", (item_name,)))
    checks.append(("SELECT 1 FROM ore_indicator_template WHERE ore_category=? LIMIT 1", (item_code,)))
    for sql, args in checks:
        if db.execute(sql, args).fetchone():
            return True
    return False


# ---------------- 指标模板 (PRD-08 §2.3) ----------------
@bp.get('/admin/indicator/template')
@roles_required('R4')
def indicator_templates():
    rows = get_db().execute("SELECT * FROM ore_indicator_template ORDER BY ore_category, sort").fetchall()
    return ok({'list': [dict(r) for r in rows], 'total': len(rows)})


@bp.post('/admin/indicator/template')
@roles_required('R4')
def indicator_template_save():
    """新增/更新指标模板字段（按品类驱动业务表单）"""
    d = request.get_json(force=True)
    if not (d.get('ore_category') or '').strip():
        return err('矿石品类必填')
    if not (d.get('field_name') or '').strip() or not (d.get('field_label') or '').strip():
        return err('字段名与显示名必填')
    if d.get('field_type') not in (None, '', 'text', 'number'):
        return err('字段类型仅支持 text/number')
    db = get_db()
    unit = (d.get('unit') or '').strip() or None
    if d.get('id'):
        row = db.execute("SELECT id FROM ore_indicator_template WHERE id=?", (d['id'],)).fetchone()
        if not row:
            return err('模板字段不存在', http=404)
        db.execute("UPDATE ore_indicator_template SET ore_category=?,field_name=?,field_label=?,"
                   "field_type=?,required=?,unit=?,sort=? WHERE id=?",
                   (d['ore_category'].strip(), d['field_name'].strip(), d['field_label'].strip(),
                    d.get('field_type') or 'text', 1 if d.get('required') else 0, unit, d.get('sort', 0), d['id']))
    else:
        db.execute("INSERT INTO ore_indicator_template(ore_category,field_name,field_label,field_type,required,unit,sort)"
                   " VALUES(?,?,?,?,?,?,?)",
                   (d['ore_category'].strip(), d['field_name'].strip(), d['field_label'].strip(),
                    d.get('field_type') or 'text', 1 if d.get('required') else 0, unit, d.get('sort', 0)))
    db.commit()
    log_action('指标模板维护', f"{d['ore_category']}/{d['field_name']}: {d['field_label']}",
               ref_type='indicator_template', ref_id=d.get('id') or d['field_name'])
    return ok(message='保存成功')


@bp.post('/admin/indicator/template/<int:tid>/delete')
@roles_required('R4')
def indicator_template_delete(tid):
    db = get_db()
    row = db.execute("SELECT * FROM ore_indicator_template WHERE id=?", (tid,)).fetchone()
    if not row:
        return err('模板字段不存在', http=404)
    db.execute("DELETE FROM ore_indicator_template WHERE id=?", (tid,))
    db.commit()
    log_action('指标模板删除', f"{row['ore_category']}/{row['field_name']}",
               ref_type='indicator_template', ref_id=tid)
    return ok(message='删除成功')


@bp.get('/indicator/template/<ore_category>')
def indicator_by_category(ore_category):
    """业务表单按品类带出指标字段（全员可用）"""
    rows = get_db().execute(
        "SELECT field_name, field_label, field_type, required, unit FROM ore_indicator_template"
        " WHERE ore_category=? ORDER BY sort", (ore_category,)).fetchall()
    return ok([dict(r) for r in rows])


# ---------------- 操作日志审计 (PRD-08 §2.6，PRD-01 全局留痕) ----------------
@bp.get('/admin/log/list')
@roles_required('R4')
def log_list():
    db = get_db()
    page = int(request.args.get('page', 1)); size = int(request.args.get('page_size', 20))
    action = request.args.get('action', '')
    role = request.args.get('role_code', '')
    start = request.args.get('start_date', '')
    end = request.args.get('end_date', '')
    sql = "SELECT * FROM sys_log WHERE 1=1"
    args = []
    if action:
        sql += " AND action LIKE ?"; args.append(f'%{action}%')
    if role:
        sql += " AND role_code=?"; args.append(role)
    if start:
        sql += " AND create_time >= ?"; args.append(f'{start} 00:00:00')
    if end:
        sql += " AND create_time <= ?"; args.append(f'{end} 23:59:59')
    sql += " ORDER BY id DESC"
    rows, total = paginate(db, sql, args, page, size)
    return ok({'list': rows, 'total': total})


# ---------------- 账号管理 (PRD-08 §2.2) ----------------
@bp.get('/admin/account/list')
@roles_required('R4')
def account_list():
    db = get_db()
    page = int(request.args.get('page', 1)); size = int(request.args.get('page_size', 10))
    kw = request.args.get('keyword', '').strip()
    role = request.args.get('role_code', '')
    sql = ("SELECT u.user_id, u.username, u.real_name, u.role_code, u.status, u.create_time,"
           " c.company_name FROM sys_user u LEFT JOIN company c ON c.company_id=u.company_id WHERE 1=1")
    args = []
    if kw:
        sql += " AND (u.username LIKE ? OR u.real_name LIKE ?)"; args += [f'%{kw}%', f'%{kw}%']
    if role:
        sql += " AND u.role_code=?"; args.append(role)
    sql += " ORDER BY u.create_time DESC"
    rows, total = paginate(db, sql, args, page, size)
    return ok({'list': rows, 'total': total})


@bp.post('/admin/account/create')
@roles_required('R4')
def account_create():
    d = request.get_json(force=True)
    for f in ('username', 'password', 'role_code'):
        if not d.get(f):
            return err(f'缺少必填字段: {f}')
    if d['role_code'] not in ('R1', 'R2', 'R3', 'R4'):
        return err('无效角色编码')
    if len(d['password']) < 6:
        return err('密码长度不得少于6位')
    db = get_db()
    if db.execute("SELECT 1 FROM sys_user WHERE username=?", (d['username'],)).fetchone():
        return err('用户名已存在')
    company_id = d.get('company_id')
    if d['role_code'] != 'R4':
        if not company_id:
            return err('企业角色账号必须绑定企业主体')
        comp = db.execute("SELECT company_type FROM company WHERE company_id=?", (company_id,)).fetchone()
        if not comp:
            return err('企业主体不存在')
        type_role = {'DOWNSTREAM': 'R1', 'SUPPLIER': 'R2', 'PARTNER': 'R3'}
        if type_role[comp['company_type']] != d['role_code']:
            return err('角色与企业主体类型不匹配')
    salt = secrets.token_hex(8)
    db.execute("INSERT INTO sys_user(company_id,role_code,username,password_hash,salt,real_name,status,create_time)"
               " VALUES(?,?,?,?,?,?,'ACTIVE',?)",
               (company_id, d['role_code'], d['username'],
                hashlib.sha256((salt + d['password']).encode()).hexdigest(), salt,
                d.get('real_name', d['username']), _now()))
    db.commit()
    log_action('新增账号', f"{d['username']}({d['role_code']})", ref_type='user', ref_id=d['username'])
    return ok(message='创建成功')


@bp.put('/admin/account/<int:uid>')
@roles_required('R4')
def account_update(uid):
    db = get_db()
    u = db.execute("SELECT * FROM sys_user WHERE user_id=?", (uid,)).fetchone()
    if not u:
        return err('账号不存在', http=404)
    d = request.get_json(force=True)
    if u['role_code'] == 'R4' and d.get('status') == 'DISABLED' and u['user_id'] == g.current_user['user_id']:
        return err('不能停用自己的账号')
    if 'status' in d:
        if d['status'] not in ('ACTIVE', 'DISABLED'):
            return err('无效状态')
        db.execute("UPDATE sys_user SET status=? WHERE user_id=?", (d['status'], uid))
    if 'real_name' in d:
        db.execute("UPDATE sys_user SET real_name=? WHERE user_id=?", (d['real_name'], uid))
    if d.get('password'):
        if len(d['password']) < 6:
            return err('密码长度不得少于6位')
        salt = secrets.token_hex(8)
        db.execute("UPDATE sys_user SET password_hash=?, salt=? WHERE user_id=?",
                   (hashlib.sha256((salt + d['password']).encode()).hexdigest(), salt, uid))
    db.commit()
    log_action('账号变更', f"{u['username']}: {','.join(d.keys())}",
               before=u['status'], after=d.get('status', u['status']), ref_type='user', ref_id=uid)
    return ok(message='更新成功')


# ---------------- 全局数据统计看板 (PRD-08 §2.4) ----------------
@bp.get('/admin/dashboard/summary')
@roles_required('R4')
def dashboard_summary():
    db = get_db()
    start = (request.args.get('start_date') or '').strip()
    end = (request.args.get('end_date') or '').strip()
    t0 = f'{start} 00:00:00' if start else '0000-01-01 00:00:00'
    t1 = f'{end} 23:59:59' if end else '9999-12-31 23:59:59'
    one = lambda sql, args=(): db.execute(sql, args).fetchone()[0]  # noqa: E731

    companies = {
        'DOWNSTREAM': one("SELECT COUNT(*) FROM company WHERE company_type='DOWNSTREAM'"),
        'SUPPLIER': one("SELECT COUNT(*) FROM company WHERE company_type='SUPPLIER'"),
        'PARTNER': one("SELECT COUNT(*) FROM company WHERE company_type='PARTNER'"),
        'PENDING': one("SELECT COUNT(*) FROM company WHERE audit_status='PENDING'"),
    }
    demand_by_period = [dict(r) for r in db.execute(
        "SELECT period, period_type, SUM(quantity) total_qty, COUNT(*) demand_count"
        " FROM purchase_demand WHERE status NOT IN ('DRAFT','CANCELLED') AND create_time BETWEEN ? AND ?"
        " GROUP BY period, period_type ORDER BY period", (t0, t1))]
    execution = {
        'list_count': one("SELECT COUNT(*) FROM collective_list"),
        'task_count': one("SELECT COUNT(*) FROM collective_task"),
        'order_count': one("SELECT COUNT(*) FROM collective_order"),
    }
    locked = {
        'total_qty': one("SELECT COALESCE(SUM(total_qty),0) FROM collective_order WHERE create_time BETWEEN ? AND ?", (t0, t1)),
        'total_amount': one("SELECT COALESCE(SUM(total_amount),0) FROM collective_order WHERE create_time BETWEEN ? AND ?", (t0, t1)),
    }
    platform = {
        'allocated_done_qty': one("SELECT COALESCE(SUM(qty),0) FROM allocation_order WHERE status='DONE'"),
        'archived_count': one("SELECT COUNT(*) FROM archive_record"),
        'partner_count': one("SELECT COUNT(*) FROM logistics_task"),
    }
    order_trend = [dict(r) for r in db.execute(
        "SELECT substr(create_time,1,7) ym, COUNT(*) order_count,"
        " COALESCE(SUM(total_qty),0) total_qty, COALESCE(SUM(total_amount),0) total_amount"
        " FROM collective_order WHERE create_time BETWEEN ? AND ? GROUP BY ym ORDER BY ym", (t0, t1))]
    demand_pie = [dict(r) for r in db.execute(
        "SELECT ore_category, COALESCE(SUM(quantity),0) total_qty FROM purchase_demand"
        " WHERE status NOT IN ('DRAFT','CANCELLED') AND create_time BETWEEN ? AND ?"
        " GROUP BY ore_category", (t0, t1))]
    return ok({'companies': companies, 'demand_by_period': demand_by_period, 'execution': execution,
               'locked': locked, 'platform': platform, 'order_trend': order_trend, 'demand_pie': demand_pie})


# ---------------- 全量业务单据检索 (PRD-08 §2.5) ----------------
DOC_CONF = {
    'demand':    {'label': '申报需求', 'table': 'purchase_demand d JOIN company c ON c.company_id=d.company_id',
                  'idcol': 'd.demand_id', 'no': 'd.demand_no', 'time': 'd.create_time',
                  'company': 'c.company_name', 'status': 'd.status',
                  'select': 'd.demand_id AS id, d.demand_no AS doc_no, c.company_name, d.period, d.ore_category, d.quantity, d.status, d.create_time'},
    'list':      {'label': '集采清单', 'table': 'collective_list l',
                  'idcol': 'l.list_id', 'no': 'l.list_no', 'time': 'l.create_time', 'company': None,
                  'status': 'l.status',
                  'select': 'l.list_id AS id, l.list_no AS doc_no, l.period, l.period_type, l.total_qty AS quantity, l.status, l.create_time'},
    'task':      {'label': '询价任务', 'table': 'collective_task t',
                  'idcol': 't.task_id', 'no': 't.task_no', 'time': 't.create_time', 'company': None,
                  'status': 't.status',
                  'select': 't.task_id AS id, t.task_no AS doc_no, t.ore_category, t.total_qty AS quantity, t.status, t.create_time'},
    'order':     {'label': '集采订单', 'table': 'collective_order o JOIN company s ON s.company_id=o.supplier_id',
                  'idcol': 'o.order_id', 'no': 'o.order_no', 'time': 'o.create_time',
                  'company': 's.company_name', 'status': 'o.status',
                  'select': 'o.order_id AS id, o.order_no AS doc_no, s.company_name, o.total_qty AS quantity, o.total_amount, o.status, o.create_time'},
    'alloc':     {'label': '分拨单', 'table': 'allocation_order a JOIN company c ON c.company_id=a.company_id',
                  'idcol': 'a.alloc_id', 'no': 'a.alloc_no', 'time': 'a.create_time',
                  'company': 'c.company_name', 'status': 'a.status',
                  'select': 'a.alloc_id AS id, a.alloc_no AS doc_no, c.company_name, a.ore_category, a.qty AS quantity, a.amount AS total_amount, a.status, a.create_time'},
    'logistics': {'label': '物流任务', 'table': 'logistics_task t',
                  'idcol': 't.logi_id', 'no': 't.logi_no', 'time': 't.create_time', 'company': None,
                  'status': None,
                  'select': 't.logi_id AS id, t.logi_no AS doc_no, t.current_node, t.create_time'},
    'bill':      {'label': '对账单', 'table': None, 'status': None},
}


@bp.get('/admin/ledger/search')
@roles_required('R4')
def ledger_search():
    """统一检索：申报需求/集采清单/询价任务/集采订单/分拨单/物流/对账单"""
    d = DOC_CONF
    db = get_db()
    doc_type = request.args.get('doc_type', '')
    if doc_type and doc_type not in d:
        return err('无效的单据类型')
    kw = (request.args.get('keyword') or '').strip()
    company = (request.args.get('company') or '').strip()
    status = (request.args.get('status') or '').strip()
    start = (request.args.get('start_date') or '').strip()
    end = (request.args.get('end_date') or '').strip()
    page = int(request.args.get('page', 1)); size = int(request.args.get('page_size', 10))

    types = [doc_type] if doc_type else list(d.keys())
    result = []
    for t in types:
        conf = d[t]
        if conf.get('table') is None:
            # 对账单：企业单 + 供方单 UNION
            sql = ("SELECT bill_id AS id, bill_no AS doc_no, company_name, period, total_amount AS quantity,"
                   " status, create_time FROM ("
                   " SELECT b.bill_id, b.bill_no, c.company_name, b.period, b.total_amount, b.status, b.create_time"
                   " FROM company_bill b JOIN company c ON c.company_id=b.company_id UNION ALL"
                   " SELECT b.bill_id, b.bill_no, s.company_name, b.period, b.total_amount, b.status, b.create_time"
                   " FROM supplier_bill b JOIN company s ON s.company_id=b.supplier_id) WHERE 1=1")
            args = []
            for cond, val in ((" AND doc_no LIKE ?", f'%{kw}%'), (" AND company_name LIKE ?", f'%{company}%'),
                              (" AND status=?", status), (" AND create_time >= ?", f'{start} 00:00:00' if start else ''),
                              (" AND create_time <= ?", f'{end} 23:59:59' if end else '')):
                if val:
                    sql += cond; args.append(val)
            sql += " ORDER BY create_time DESC"
            rows = db.execute(sql, args).fetchall()
            result.append({'doc_type': t, 'label': conf['label'], 'list': [dict(r) for r in rows], 'total': len(rows)})
            continue
        where, args = " WHERE 1=1", []
        if kw:
            where += f" AND {conf['no']} LIKE ?"; args.append(f'%{kw}%')
        if company and conf.get('company'):
            where += f" AND {conf['company']} LIKE ?"; args.append(f'%{company}%')
        if status and conf.get('status'):
            where += f" AND {conf['status']}=?"; args.append(status)
        if start:
            where += f" AND {conf['time']} >= ?"; args.append(f'{start} 00:00:00')
        if end:
            where += f" AND {conf['time']} <= ?"; args.append(f'{end} 23:59:59')
        base = f"SELECT {conf['select']} FROM {conf['table']}" + where + f" ORDER BY {conf['time']} DESC"
        rows = db.execute(base, args).fetchall()
        result.append({'doc_type': t, 'label': conf['label'], 'list': [dict(r) for r in rows], 'total': len(rows)})
    return ok({'groups': result})


DOC_REF = {'demand': 'demand', 'list': 'collective_list', 'task': 'collective_task',
           'order': 'collective_order', 'alloc': 'allocation_order',
           'logistics': 'logistics_task', 'bill': 'company_bill'}


@bp.get('/admin/ledger/doc')
@roles_required('R4')
def ledger_doc():
    """穿透查看任意单据详情与操作轨迹"""
    doc_type = request.args.get('doc_type', '')
    did = request.args.get('id')
    if doc_type not in DOC_REF or not did:
        return err('无效的单据类型或ID')
    db = get_db()
    doc = None
    if doc_type == 'demand':
        doc = db.execute("SELECT d.*, c.company_name FROM purchase_demand d JOIN company c"
                         " ON c.company_id=d.company_id WHERE demand_id=?", (did,)).fetchone()
    elif doc_type == 'list':
        doc = db.execute("SELECT * FROM collective_list WHERE list_id=?", (did,)).fetchone()
    elif doc_type == 'task':
        doc = db.execute("SELECT t.*, l.period, l.period_type FROM collective_task t"
                         " JOIN collective_list l ON l.list_id=t.list_id WHERE task_id=?", (did,)).fetchone()
    elif doc_type == 'order':
        doc = db.execute("SELECT o.*, s.company_name FROM collective_order o"
                         " JOIN company s ON s.company_id=o.supplier_id WHERE order_id=?", (did,)).fetchone()
    elif doc_type == 'alloc':
        doc = db.execute("SELECT a.*, c.company_name FROM allocation_order a"
                         " JOIN company c ON c.company_id=a.company_id WHERE alloc_id=?", (did,)).fetchone()
    elif doc_type == 'logistics':
        doc = db.execute("SELECT * FROM logistics_task WHERE logi_id=?", (did,)).fetchone()
    elif doc_type == 'bill':
        doc = db.execute("SELECT b.*, c.company_name FROM company_bill b"
                         " JOIN company c ON c.company_id=b.company_id WHERE b.bill_id=?", (did,)).fetchone()
        if not doc:
            doc = db.execute("SELECT b.*, c.company_name FROM supplier_bill b"
                             " JOIN company c ON c.company_id=b.supplier_id WHERE b.bill_id=?", (did,)).fetchone()
    if not doc:
        return err('单据不存在', http=404)
    no = doc['demand_no'] if doc_type == 'demand' else (doc['order_no'] if doc_type == 'order' else
         doc['alloc_no'] if doc_type == 'alloc' else doc['doc_no'] if 'doc_no' in doc.keys() else
         (doc['task_no'] if doc_type == 'task' else doc['logi_no'] if doc_type == 'logistics' else doc['bill_no']))
    # 操作轨迹：ref_type + ref_id(单号或ID) 双匹配
    logs = [dict(r) for r in db.execute(
        "SELECT operator_name, role_code, action, detail, before_status, after_status, create_time"
        " FROM sys_log WHERE ref_type=? AND (ref_id=? OR ref_id=?) ORDER BY id",
        (DOC_REF[doc_type], str(did), str(no)))]
    return ok({'doc': dict(doc), 'doc_type': doc_type, 'logs': logs})


# ---------------- 日志导出 (PRD-08 §2.6) ----------------
@bp.get('/admin/log/export')
@roles_required('R4')
def log_export():
    db = get_db()
    action = request.args.get('action', '')
    role = request.args.get('role_code', '')
    start = request.args.get('start_date', '')
    end = request.args.get('end_date', '')
    sql = "SELECT id, operator_name, role_code, action, detail, before_status, after_status, ref_type, ref_id, create_time FROM sys_log WHERE 1=1"
    args = []
    if action:
        sql += " AND action LIKE ?"; args.append(f'%{action}%')
    if role:
        sql += " AND role_code=?"; args.append(role)
    if start:
        sql += " AND create_time >= ?"; args.append(f'{start} 00:00:00')
    if end:
        sql += " AND create_time <= ?"; args.append(f'{end} 23:59:59')
    sql += " ORDER BY id"
    rows = db.execute(sql, args).fetchall()
    headers = ['日志ID', '操作人', '角色', '操作', '详情', '前状态', '后状态', '关联类型', '关联ID', '时间']
    data = [[r['id'], r['operator_name'], r['role_code'], r['action'], r['detail'] or '',
             r['before_status'] or '', r['after_status'] or '', r['ref_type'] or '', r['ref_id'] or '',
             r['create_time']] for r in rows]
    buf = export_excel(headers, [('操作日志', data)], f'操作日志_{_now()[:10]}.xlsx')
    log_action('导出操作日志', f'共{len(data)}条', ref_type='sys_log', ref_id='export')
    return buf
