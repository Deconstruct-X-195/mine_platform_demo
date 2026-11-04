# -*- coding: utf-8 -*-
"""需求申报模块 (PRD-02)：企业申报 CRUD / 草稿 / 变更申请 / 平台归集生成集采清单 / Excel 导出"""
import re
from flask import Blueprint, request
from ..db import get_db, _now
from ..utils import ok, err, log_action, paginate, round2, export_excel
from ..auth import roles_required, company_approved_required

bp = Blueprint('demand', __name__)

VALID_STATUSES = ('DRAFT', 'SUBMITTED', 'IN_PROCESS', 'IN_LIST', 'IN_EXEC', 'DISTRIBUTED', 'CANCELLED')


def _validate_demand(d):
    """申报字段校验，返回错误信息或 None"""
    if d.get('period_type') not in ('MONTH', 'QUARTER'):
        return '申报周期类型必须是 月度/季度'
    period = (d.get('period') or '').strip()
    if d['period_type'] == 'MONTH' and not re.match(r'^\d{4}-(0[1-9]|1[0-2])$', period):
        return '月度周期格式应为 YYYY-MM'
    if d['period_type'] == 'QUARTER' and not re.match(r'^\d{4}-Q[1-4]$', period):
        return '季度周期格式应为 YYYY-Qn'
    if not (d.get('ore_category') or '').strip():
        return '矿石品类必填'
    qty = d.get('quantity')
    if qty is None or not isinstance(qty, (int, float)) or qty <= 0:
        return '采购数量必须大于0'
    if qty > 1_000_000_000:
        return '采购数量超出合理范围'
    if not (d.get('grade_req') or '').strip():
        return '品位要求必填'
    if not (d.get('expected_arrival') or '').strip():
        return '期望到货时间必填'
    if d.get('remark') and len(d['remark']) > 500:
        return '备注最多500字'
    return None


def _save_attachments(db, demand_id, attachments):
    for a in attachments or []:
        if a.get('file_url'):
            db.execute("INSERT INTO demand_attachment(demand_id,file_url,file_name) VALUES(?,?,?)",
                       (demand_id, a['file_url'], a.get('file_name')))


# ---------------- 企业端 (R1) ----------------
@bp.post('/demand/create')
@roles_required('R1')
@company_approved_required
def demand_create():
    d = request.get_json(force=True)
    if msg := _validate_demand(d):
        return err(msg)
    db = get_db()
    now = _now()
    action = d.get('action', 'submit')  # draft / submit
    status = 'DRAFT' if action == 'draft' else 'SUBMITTED'
    cur = db.execute(
        "INSERT INTO purchase_demand(company_id,period_type,period,ore_category,quantity,grade_req,"
        "granularity_req,moisture_req,impurity_req,expected_arrival,delivery_place,remark,status,"
        "create_time,update_time) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (g_company_id(), d['period_type'], d['period'].strip(), d['ore_category'],
         round2(d['quantity']), d['grade_req'], d.get('granularity_req'), d.get('moisture_req'),
         d.get('impurity_req'), d['expected_arrival'], d.get('delivery_place'),
         d.get('remark'), status, now, now))
    demand_id = cur.lastrowid
    db.execute("UPDATE purchase_demand SET demand_no=? WHERE demand_id=?",
               (f"PD{now.replace('-', '').replace(':', '').replace(' ', '')}{demand_id:05d}", demand_id))
    _save_attachments(db, demand_id, d.get('attachments'))
    db.commit()
    log_action('新增采购需求申报', f"周期 {d['period']} 品类 {d['ore_category']} 数量 {round2(d['quantity'])}吨 ({status})",
               after=status, ref_type='demand', ref_id=demand_id)
    return ok({'demand_id': demand_id}, message='保存成功')


def g_company_id():
    from flask import g
    return g.current_user['company_id']


@bp.put('/demand/<int:did>')
@roles_required('R1')
@company_approved_required
def demand_update(did):
    db = get_db()
    row = db.execute("SELECT * FROM purchase_demand WHERE demand_id=? AND company_id=?",
                     (did, g_company_id())).fetchone()
    if not row:
        return err('申报记录不存在', http=404)
    if row['status'] != 'DRAFT':
        return err('仅草稿状态可编辑；已提交需求请使用变更申请')
    d = request.get_json(force=True)
    if msg := _validate_demand(d):
        return err(msg)
    now = _now()
    db.execute(
        "UPDATE purchase_demand SET period_type=?,period=?,ore_category=?,quantity=?,grade_req=?,"
        "granularity_req=?,moisture_req=?,impurity_req=?,expected_arrival=?,delivery_place=?,remark=?,"
        "status=?,update_time=? WHERE demand_id=?",
        (d['period_type'], d['period'].strip(), d['ore_category'], round2(d['quantity']), d['grade_req'],
         d.get('granularity_req'), d.get('moisture_req'), d.get('impurity_req'), d['expected_arrival'],
         d.get('delivery_place'), d.get('remark'),
         'DRAFT' if d.get('action', 'draft') == 'draft' else 'SUBMITTED', now, did))
    if d.get('attachments') is not None:
        db.execute("DELETE FROM demand_attachment WHERE demand_id=?", (did,))
        _save_attachments(db, did, d['attachments'])
    db.commit()
    log_action('编辑采购需求申报', f"申报 {row['demand_no']} 已更新", before=row['status'],
               after='DRAFT' if d.get('action', 'draft') == 'draft' else 'SUBMITTED',
               ref_type='demand', ref_id=did)
    return ok(message='保存成功')


@bp.post('/demand/<int:did>/submit')
@roles_required('R1')
@company_approved_required
def demand_submit(did):
    db = get_db()
    row = db.execute("SELECT * FROM purchase_demand WHERE demand_id=? AND company_id=?",
                     (did, g_company_id())).fetchone()
    if not row:
        return err('申报记录不存在', http=404)
    if row['status'] != 'DRAFT':
        return err('仅草稿可提交')
    db.execute("UPDATE purchase_demand SET status='SUBMITTED', update_time=? WHERE demand_id=?",
               (_now(), did))
    db.commit()
    log_action('提交采购需求申报', f"申报 {row['demand_no']} 已提交", before='DRAFT',
               after='SUBMITTED', ref_type='demand', ref_id=did)
    return ok(message='提交成功')


@bp.post('/demand/<int:did>/delete')
@roles_required('R1')
@company_approved_required
def demand_delete(did):
    db = get_db()
    row = db.execute("SELECT * FROM purchase_demand WHERE demand_id=? AND company_id=?",
                     (did, g_company_id())).fetchone()
    if not row:
        return err('申报记录不存在', http=404)
    if row['status'] != 'DRAFT':
        return err('仅草稿可删除')
    db.execute("DELETE FROM demand_attachment WHERE demand_id=?", (did,))
    db.execute("DELETE FROM purchase_demand WHERE demand_id=?", (did,))
    db.commit()
    log_action('删除采购需求草稿', f"草稿 {row['demand_no']} 已删除", before='DRAFT',
               after='DELETED', ref_type='demand', ref_id=did)
    return ok(message='删除成功')


@bp.get('/demand/list')
@roles_required('R1')
@company_approved_required
def demand_list():
    db = get_db()
    page = int(request.args.get('page', 1)); size = int(request.args.get('page_size', 10))
    sql = "SELECT d.*, c.company_name FROM purchase_demand d JOIN company c ON c.company_id=d.company_id WHERE d.company_id=?"
    args = [g_company_id()]
    if request.args.get('period'):
        sql += " AND d.period=?"; args.append(request.args['period'])
    if request.args.get('ore_category'):
        sql += " AND d.ore_category=?"; args.append(request.args['ore_category'])
    if request.args.get('status'):
        sql += " AND d.status=?"; args.append(request.args['status'])
    sql += " ORDER BY d.update_time DESC"
    rows, total = paginate(db, sql, args, page, size)
    return ok({'list': rows, 'total': total, 'page': page, 'page_size': size})


@bp.get('/demand/<int:did>')
@roles_required('R1', 'R4')
def demand_detail(did):
    db = get_db()
    row = db.execute(
        "SELECT d.*, c.company_name FROM purchase_demand d JOIN company c ON c.company_id=d.company_id"
        " WHERE demand_id=?", (did,)).fetchone()
    if not row:
        return err('申报记录不存在', http=404)
    if g_current_role() == 'R1' and row['company_id'] != g_company_id():
        return err('无权查看他人申报', code=403, http=403)
    attachments = [dict(a) for a in db.execute(
        "SELECT id,file_url,file_name FROM demand_attachment WHERE demand_id=?", (did,)).fetchall()]
    changes = [dict(c) for c in db.execute(
        "SELECT * FROM demand_change WHERE demand_id=? ORDER BY id DESC", (did,)).fetchall()]
    return ok({**dict(row), 'attachments': attachments, 'changes': changes})


def g_current_role():
    from flask import g
    return g.current_user['role_code']


@bp.post('/demand/<int:did>/change')
@roles_required('R1')
@company_approved_required
def demand_change(did):
    db = get_db()
    row = db.execute("SELECT * FROM purchase_demand WHERE demand_id=? AND company_id=?",
                     (did, g_company_id())).fetchone()
    if not row:
        return err('申报记录不存在', http=404)
    if row['status'] == 'DISTRIBUTED':
        return err('需求已完成分拨归档，单据只读不可变更')
    if row['status'] in ('DRAFT', 'CANCELLED'):
        return err('草稿可直接编辑，已取消需求无需变更')
    d = request.get_json(force=True)
    if d.get('change_type') not in ('QTY', 'SPEC', 'CANCEL'):
        return err('无效的变更类型')
    if not (d.get('change_desc') or '').strip():
        return err('变更说明必填')
    new_qty = d.get('new_quantity')
    if d['change_type'] == 'QTY':
        if new_qty is None or new_qty <= 0:
            return err('数量变更需提供有效的新数量')
    db.execute(
        "INSERT INTO demand_change(demand_id,company_id,change_type,change_desc,attachment_url,file_name,"
        "new_quantity,status,create_time) VALUES(?,?,?,?,?,?,?,'PENDING',?)",
        (did, g_company_id(), d['change_type'], d['change_desc'].strip(), d.get('attachment_url'),
         d.get('file_name'), round2(new_qty) if new_qty else None, _now()))
    db.commit()
    log_action('提交变更申请', f"申报 {row['demand_no']} 变更类型 {d['change_type']}",
               before=row['status'], after='PENDING', ref_type='demand_change', ref_id=did)
    return ok(message='变更申请已提交，待平台处理')


# ---------------- 平台端 (R4) ----------------
@bp.get('/admin/demand/list')
@roles_required('R4')
def admin_demand_list():
    db = get_db()
    page = int(request.args.get('page', 1)); size = int(request.args.get('page_size', 10))
    sql = ("SELECT d.*, c.company_name, c.contact FROM purchase_demand d"
           " JOIN company c ON c.company_id=d.company_id WHERE 1=1")
    args = []
    if request.args.get('period'):
        sql += " AND d.period=?"; args.append(request.args['period'])
    if request.args.get('company'):
        sql += " AND c.company_name LIKE ?"; args.append(f"%{request.args['company']}%")
    if request.args.get('ore_category'):
        sql += " AND d.ore_category=?"; args.append(request.args['ore_category'])
    if request.args.get('status'):
        sql += " AND d.status=?"; args.append(request.args['status'])
    sql += " ORDER BY d.update_time DESC"
    rows, total = paginate(db, sql, args, page, size)
    return ok({'list': rows, 'total': total, 'page': page, 'page_size': size})


@bp.get('/admin/demand/change/list')
@roles_required('R4')
def admin_change_list():
    db = get_db()
    page = int(request.args.get('page', 1)); size = int(request.args.get('page_size', 10))
    sql = ("SELECT dc.*, d.demand_no, d.ore_category, d.quantity AS old_qty, d.status AS demand_status,"
           " c.company_name FROM demand_change dc"
           " JOIN purchase_demand d ON d.demand_id=dc.demand_id"
           " JOIN company c ON c.company_id=dc.company_id WHERE 1=1")
    args = []
    if request.args.get('status'):
        sql += " AND dc.status=?"; args.append(request.args['status'])
    sql += " ORDER BY dc.id DESC"
    rows, total = paginate(db, sql, args, page, size)
    return ok({'list': rows, 'total': total})


@bp.post('/admin/demand/change/<int:cid>/review')
@roles_required('R4')
def admin_change_review(cid):
    db = get_db()
    ch = db.execute("SELECT * FROM demand_change WHERE id=?", (cid,)).fetchone()
    if not ch:
        return err('变更申请不存在', http=404)
    if ch['status'] != 'PENDING':
        return err('该变更申请已处理')
    d = request.get_json(force=True)
    result = d.get('result')
    if result not in ('AGREED', 'REJECTED'):
        return err('无效的处理结论')
    now = _now()
    if result == 'AGREED':
        demand = db.execute("SELECT * FROM purchase_demand WHERE demand_id=?", (ch['demand_id'],)).fetchone()
        if not demand:
            return err('原申报记录不存在')
        if demand['status'] == 'DISTRIBUTED':
            return err('该需求已分拨归档，单据只读，不可执行变更')
        if ch['change_type'] == 'QTY':
            db.execute("UPDATE purchase_demand SET quantity=?, update_time=? WHERE demand_id=?",
                       (ch['new_quantity'], now, ch['demand_id']))
        elif ch['change_type'] == 'CANCEL':
            db.execute("UPDATE purchase_demand SET status='CANCELLED', update_time=? WHERE demand_id=?",
                       (now, ch['demand_id']))
        # SPEC 变更：记录说明（规格文本变更由管理员依据说明人工核定，此处记录审计轨迹）
    db.execute("UPDATE demand_change SET status=?, review_remark=?, review_time=? WHERE id=?",
               (result, d.get('review_remark'), now, cid))
    db.commit()
    log_action('变更申请审核', f"变更#{cid} 结论 {result}", before='PENDING', after=result,
               ref_type='demand_change', ref_id=cid)
    return ok(message='处理完成')


@bp.post('/admin/collective/create')
@roles_required('R4')
def collective_create():
    """生成集采清单：按 周期+品类 汇总，保留各企业明细"""
    d = request.get_json(force=True)
    period_type, period = d.get('period_type'), (d.get('period') or '').strip()
    if period_type not in ('MONTH', 'QUARTER') or not period:
        return err('必须指定申报周期')
    db = get_db()
    demands = db.execute(
        "SELECT * FROM purchase_demand WHERE period_type=? AND period=? AND status IN ('SUBMITTED','IN_PROCESS')"
        " ORDER BY company_id", (period_type, period)).fetchall()
    if not demands:
        return err('该周期下没有可归集的有效需求（需为已提交/归集处理中状态）')
    now = _now()
    groups = {}
    for dm in demands:
        groups.setdefault(dm['ore_category'], []).append(dm)
    created = []
    for category, items in groups.items():
        total = round2(sum(x['quantity'] for x in items))
        cur = db.execute(
            "INSERT INTO collective_list(period_type,period,total_qty,status,creator_id,create_time)"
            " VALUES(?,?,?,'ACTIVE',?,?)", (period_type, period, total, g_admin_id(), now))
        list_id = cur.lastrowid
        db.execute("UPDATE collective_list SET list_no=? WHERE list_id=?",
                   (f"CL{now.replace('-', '').replace(':', '').replace(' ', '')}{list_id:04d}", list_id))
        for it in items:
            db.execute(
                "INSERT INTO collective_list_detail(list_id,demand_id,company_id,ore_category,qty,grade_req,expected_arrival)"
                " VALUES(?,?,?,?,?,?,?)",
                (list_id, it['demand_id'], it['company_id'], category, it['quantity'],
                 it['grade_req'], it['expected_arrival']))
            db.execute("UPDATE purchase_demand SET status='IN_LIST', update_time=? WHERE demand_id=?",
                       (now, it['demand_id']))
        created.append({'list_id': list_id, 'ore_category': category, 'total_qty': total,
                        'detail_count': len(items)})
        log_action('生成集采清单', f"周期 {period} 品类 {category} 总量 {total}吨 含{len(items)}家企业",
                   after='IN_LIST', ref_type='collective_list', ref_id=list_id)
    db.commit()
    return ok({'lists': created}, message=f'已生成 {len(created)} 份集采清单')


def g_admin_id():
    from flask import g
    return g.current_user['user_id']


@bp.get('/admin/collective/list')
@roles_required('R4')
def collective_list():
    db = get_db()
    page = int(request.args.get('page', 1)); size = int(request.args.get('page_size', 10))
    sql = "SELECT * FROM collective_list WHERE 1=1"
    args = []
    if request.args.get('period'):
        sql += " AND period=?"; args.append(request.args['period'])
    if request.args.get('ore_category'):
        sql += """ AND list_id IN (SELECT list_id FROM collective_list_detail WHERE ore_category=?)"""
        args.append(request.args['ore_category'])
    sql += " ORDER BY create_time DESC"
    rows, total = paginate(db, sql, args, page, size)
    for r in rows:
        r['ore_categories'] = [x['ore_category'] for x in db.execute(
            "SELECT DISTINCT ore_category FROM collective_list_detail WHERE list_id=?", (r['list_id'],))]
        r['detail_count'] = db.execute(
            "SELECT COUNT(*) FROM collective_list_detail WHERE list_id=?", (r['list_id'],)).fetchone()[0]
    return ok({'list': rows, 'total': total, 'page': page, 'page_size': size})


@bp.get('/admin/collective/<int:lid>')
@roles_required('R4')
def collective_detail(lid):
    db = get_db()
    head = db.execute("SELECT * FROM collective_list WHERE list_id=?", (lid,)).fetchone()
    if not head:
        return err('集采清单不存在', http=404)
    details = [dict(x) for x in db.execute(
        "SELECT cld.*, c.company_name FROM collective_list_detail cld"
        " JOIN company c ON c.company_id=cld.company_id WHERE cld.list_id=? ORDER BY cld.company_id", (lid,))]
    return ok({**dict(head), 'details': details})


@bp.route('/admin/collective/export', methods=['GET', 'POST'])
@roles_required('R4')
def collective_export():
    """导出集采清单 Excel：汇总页 + 明细页"""
    d = request.get_json(force=True) if request.data else {}
    db = get_db()
    if d.get('list_id'):
        heads = db.execute("SELECT * FROM collective_list WHERE list_id=?", (d['list_id'],)).fetchall()
    else:
        heads = db.execute("SELECT * FROM collective_list ORDER BY create_time DESC").fetchall()
    if not heads:
        return err('没有可导出的集采清单')
    summary_rows, detail_rows = [], []
    for h in heads:
        cats = db.execute(
            "SELECT ore_category, SUM(qty) total, COUNT(*) cnt FROM collective_list_detail"
            " WHERE list_id=? GROUP BY ore_category", (h['list_id'],)).fetchall()
        for c in cats:
            summary_rows.append([h['list_no'], h['period_type'], h['period'], c['ore_category'],
                                 c['total'], c['cnt'], h['create_time']])
        for x in db.execute(
                "SELECT cld.*, c.company_name FROM collective_list_detail cld"
                " JOIN company c ON c.company_id=cld.company_id WHERE cld.list_id=?", (h['list_id'],)):
            detail_rows.append([h['list_no'], x['company_name'], x['ore_category'], x['qty'],
                                x['grade_req'], x['expected_arrival']])
    return export_excel(
        ['清单编号', '周期类型', '周期', '矿石品类', '汇总吨数', '企业数', '生成时间'],
        [('汇总', summary_rows), ('企业明细', detail_rows)],
        '集采清单导出.xlsx')
