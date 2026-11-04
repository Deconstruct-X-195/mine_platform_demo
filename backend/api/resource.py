# -*- coding: utf-8 -*-
"""货源资源模块 (PRD-03)：供方货源维护 / 上下架 / 平台台账 / 强制下架 / 优选标记 / 导出"""
from flask import Blueprint, request
from ..db import get_db, _now
from ..utils import ok, err, log_action, paginate, round2, export_excel
from ..auth import roles_required, company_approved_required

bp = Blueprint('resource', __name__)

SHELF_STATUSES = ('DRAFT', 'ON_SHELF', 'OFF_SHELF', 'FORCE_OFF')


def _validate_resource(d):
    if not (d.get('ore_category') or '').strip():
        return '矿石品类必填'
    if not (d.get('origin') or '').strip():
        return '产地必填'
    if not (d.get('grade') or '').strip():
        return '品位必填'
    qty = d.get('max_qty')
    if qty is None or not isinstance(qty, (int, float)) or qty <= 0:
        return '可供应最大吨数必须大于0'
    if qty > 1_000_000_000:
        return '可供应吨数超出合理范围'
    if not (d.get('supply_period') or '').strip():
        return '可供应周期必填'
    if d.get('remark') and len(d['remark']) > 500:
        return '备注最多500字'
    return None


def _save_attachments(db, resource_id, attachments):
    for a in attachments or []:
        if a.get('file_url'):
            db.execute("INSERT INTO resource_attachment(resource_id,file_url,file_name) VALUES(?,?,?)",
                       (resource_id, a['file_url'], a.get('file_name')))


def _get_own(db, rid):
    from flask import g
    return db.execute("SELECT * FROM ore_resource WHERE resource_id=? AND supplier_id=?",
                      (rid, g.current_user['company_id'])).fetchone()


# ---------------- 供方端 (R2) ----------------
@bp.post('/resource/create')
@roles_required('R2')
@company_approved_required
def resource_create():
    d = request.get_json(force=True)
    if msg := _validate_resource(d):
        return err(msg)
    db = get_db()
    now = _now()
    status = 'DRAFT' if d.get('action', 'submit') == 'draft' else 'ON_SHELF'
    cur = db.execute(
        "INSERT INTO ore_resource(supplier_id,ore_category,origin,grade,granularity,moisture,impurity,"
        "max_qty,supply_period,status,create_time,update_time) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
        (g_company(), d['ore_category'], d['origin'].strip(), d['grade'], d.get('granularity'),
         d.get('moisture'), d.get('impurity'), round2(d['max_qty']), d['supply_period'].strip(),
         status, now, now))
    rid = cur.lastrowid
    _save_attachments(db, rid, d.get('attachments'))
    db.commit()
    log_action('新增货源', f"品类 {d['ore_category']} 产地 {d['origin']} 最大量 {round2(d['max_qty'])}吨 ({status})",
               after=status, ref_type='resource', ref_id=rid)
    return ok({'resource_id': rid}, message='保存成功')


def g_company():
    from flask import g
    return g.current_user['company_id']


@bp.put('/resource/<int:rid>')
@roles_required('R2')
@company_approved_required
def resource_update(rid):
    db = get_db()
    row = _get_own(db, rid)
    if not row:
        return err('货源记录不存在', http=404)
    if row['status'] != 'DRAFT':
        return err('仅草稿状态可编辑；已上架货源可先下架再修改')
    d = request.get_json(force=True)
    if msg := _validate_resource(d):
        return err(msg)
    now = _now()
    status = 'DRAFT' if d.get('action', 'draft') == 'draft' else 'ON_SHELF'
    db.execute(
        "UPDATE ore_resource SET ore_category=?,origin=?,grade=?,granularity=?,moisture=?,impurity=?,"
        "max_qty=?,supply_period=?,status=?,update_time=? WHERE resource_id=?",
        (d['ore_category'], d['origin'].strip(), d['grade'], d.get('granularity'), d.get('moisture'),
         d.get('impurity'), round2(d['max_qty']), d['supply_period'].strip(), status, now, rid))
    if d.get('attachments') is not None:
        db.execute("DELETE FROM resource_attachment WHERE resource_id=?", (rid,))
        _save_attachments(db, rid, d['attachments'])
    db.commit()
    log_action('编辑货源', f"货源#{rid} 已更新", before=row['status'], after=status,
               ref_type='resource', ref_id=rid)
    return ok(message='保存成功')


@bp.post('/resource/<int:rid>/submit')
@roles_required('R2')
@company_approved_required
def resource_submit(rid):
    db = get_db()
    row = _get_own(db, rid)
    if not row:
        return err('货源记录不存在', http=404)
    if row['status'] != 'DRAFT':
        return err('仅草稿可提交上架')
    db.execute("UPDATE ore_resource SET status='ON_SHELF', update_time=? WHERE resource_id=?",
               (_now(), rid))
    db.commit()
    log_action('货源上架', f"货源#{rid} 提交上架", before='DRAFT', after='ON_SHELF',
               ref_type='resource', ref_id=rid)
    return ok(message='上架成功')


@bp.post('/resource/<int:rid>/off')
@roles_required('R2')
@company_approved_required
def resource_off(rid):
    db = get_db()
    row = _get_own(db, rid)
    if not row:
        return err('货源记录不存在', http=404)
    if row['status'] != 'ON_SHELF':
        return err('仅上架状态可主动下架')
    db.execute("UPDATE ore_resource SET status='OFF_SHELF', update_time=? WHERE resource_id=?",
               (_now(), rid))
    db.commit()
    log_action('货源下架', f"货源#{rid} 供方主动下架", before='ON_SHELF', after='OFF_SHELF',
               ref_type='resource', ref_id=rid)
    return ok(message='已下架')


@bp.post('/resource/<int:rid>/on')
@roles_required('R2')
@company_approved_required
def resource_on(rid):
    db = get_db()
    row = _get_own(db, rid)
    if not row:
        return err('货源记录不存在', http=404)
    if row['status'] not in ('OFF_SHELF', 'FORCE_OFF'):
        return err('仅已下架/强制下架状态可重新上架')
    db.execute("UPDATE ore_resource SET status='ON_SHELF', update_time=? WHERE resource_id=?",
               (_now(), rid))
    db.commit()
    log_action('货源重新上架', f"货源#{rid} 重新上架", before=row['status'], after='ON_SHELF',
               ref_type='resource', ref_id=rid)
    return ok(message='重新上架成功')


@bp.get('/resource/list')
@roles_required('R2')
@company_approved_required
def resource_list():
    db = get_db()
    page = int(request.args.get('page', 1)); size = int(request.args.get('page_size', 10))
    sql = "SELECT r.*, c.company_name FROM ore_resource r JOIN company c ON c.company_id=r.supplier_id WHERE r.supplier_id=?"
    args = [g_company()]
    if request.args.get('ore_category'):
        sql += " AND r.ore_category=?"; args.append(request.args['ore_category'])
    if request.args.get('status'):
        sql += " AND r.status=?"; args.append(request.args['status'])
    sql += " ORDER BY r.update_time DESC"
    rows, total = paginate(db, sql, args, page, size)
    return ok({'list': rows, 'total': total, 'page': page, 'page_size': size})


@bp.get('/resource/<int:rid>')
@roles_required('R2', 'R4')
def resource_detail(rid):
    db = get_db()
    row = db.execute(
        "SELECT r.*, c.company_name, c.contact, c.phone FROM ore_resource r"
        " JOIN company c ON c.company_id=r.supplier_id WHERE resource_id=?", (rid,)).fetchone()
    if not row:
        return err('货源记录不存在', http=404)
    if g_role() == 'R2' and row['supplier_id'] != g_company():
        return err('无权查看他人货源', code=403, http=403)
    attachments = [dict(a) for a in db.execute(
        "SELECT id,file_url,file_name FROM resource_attachment WHERE resource_id=?", (rid,)).fetchall()]
    return ok({**dict(row), 'attachments': attachments})


def g_role():
    from flask import g
    return g.current_user['role_code']


# ---------------- 平台端 (R4) ----------------
@bp.get('/admin/resource/list')
@roles_required('R4')
def admin_resource_list():
    db = get_db()
    page = int(request.args.get('page', 1)); size = int(request.args.get('page_size', 10))
    sql = ("SELECT r.*, c.company_name, c.supplier_type FROM ore_resource r"
           " JOIN company c ON c.company_id=r.supplier_id WHERE 1=1")
    args = []
    if request.args.get('ore_category'):
        sql += " AND r.ore_category=?"; args.append(request.args['ore_category'])
    if request.args.get('status'):
        sql += " AND r.status=?"; args.append(request.args['status'])
    if request.args.get('supplier'):
        sql += " AND c.company_name LIKE ?"; args.append(f"%{request.args['supplier']}%")
    sql += " ORDER BY r.update_time DESC"
    rows, total = paginate(db, sql, args, page, size)
    return ok({'list': rows, 'total': total, 'page': page, 'page_size': size})


@bp.post('/admin/resource/<int:rid>/force_off')
@roles_required('R4')
def admin_force_off(rid):
    d = request.get_json(force=True)
    reason = (d.get('reason') or '').strip()
    if not reason:
        return err('强制下架必须填写原因')
    db = get_db()
    row = db.execute("SELECT * FROM ore_resource WHERE resource_id=?", (rid,)).fetchone()
    if not row:
        return err('货源记录不存在', http=404)
    if row['status'] != 'ON_SHELF':
        return err('仅上架状态的货源可强制下架')
    db.execute("UPDATE ore_resource SET status='FORCE_OFF', down_reason=?, update_time=? WHERE resource_id=?",
               (reason, _now(), rid))
    db.commit()
    log_action('货源强制下架', f"货源#{rid} 原因: {reason}", before='ON_SHELF', after='FORCE_OFF',
               ref_type='resource', ref_id=rid)
    return ok(message='已强制下架')


@bp.post('/admin/resource/<int:rid>/prefer')
@roles_required('R4')
def admin_prefer(rid):
    d = request.get_json(force=True)
    flag = 1 if d.get('is_preferred') else 0
    db = get_db()
    row = db.execute("SELECT * FROM ore_resource WHERE resource_id=?", (rid,)).fetchone()
    if not row:
        return err('货源记录不存在', http=404)
    if flag and row['status'] != 'ON_SHELF':
        return err('仅上架状态的货源可标记优选')
    db.execute("UPDATE ore_resource SET is_preferred=?, update_time=? WHERE resource_id=?",
               (flag, _now(), rid))
    db.commit()
    log_action('优选标记', f"货源#{rid} 优选标记: {'开' if flag else '关'}",
               after=str(flag), ref_type='resource', ref_id=rid)
    return ok(message='操作成功')


@bp.post('/admin/resource/export')
@roles_required('R4')
def admin_resource_export():
    db = get_db()
    rows = db.execute(
        "SELECT r.*, c.company_name FROM ore_resource r JOIN company c ON c.company_id=r.supplier_id"
        " ORDER BY r.create_time DESC").fetchall()
    data = [[r['resource_id'], r['company_name'], r['ore_category'], r['origin'], r['grade'],
             r['granularity'] or '', r['moisture'] or '', r['impurity'] or '',
             r['max_qty'], r['supply_period'], r['status'], '是' if r['is_preferred'] else '否',
             r['create_time']] for r in rows]
    return export_excel(
        ['ID', '供方', '品类', '产地', '品位', '粒度', '水分', '杂质', '最大吨数', '供应周期', '状态', '优选', '创建时间'],
        [('货源台账', data)], '上游资源台账.xlsx')
