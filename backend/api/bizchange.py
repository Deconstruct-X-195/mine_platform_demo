# -*- coding: utf-8 -*-
"""单据变更&红冲管理模块 (PRD-15)：化验单/分拨单/对账单/合同四类单据的
变更申请审核、红冲申请审核；红冲通过后原单标记作废不再参与结算"""
from flask import Blueprint, request, g
from ..db import get_db, _now
from ..utils import ok, err, log_action, paginate
from ..auth import roles_required, company_approved_required

bp = Blueprint('bizchange', __name__)

BIZ_TYPES = ['INSPECT', 'ALLOC', 'BILL', 'CONTRACT']
BIZ_NAME = {'INSPECT': '化验单', 'ALLOC': '分拨单', 'BILL': '对账单', 'CONTRACT': '合同'}
BIZ_TABLE = {'INSPECT': ('ore_inspect_report', 'report_id', 'report_no'),
             'ALLOC': ('allocation_order', 'alloc_id', 'alloc_no'),
             'BILL': ('company_bill', 'bill_id', 'bill_no'),
             'CONTRACT': ('ore_contract', 'contract_id', 'contract_no')}


def _biz_info(db, biz_type, biz_id):
    if biz_type not in BIZ_TABLE:
        return None
    table, id_col, no_col = BIZ_TABLE[biz_type]
    row = db.execute(f"SELECT * FROM {table} WHERE {id_col}=?", (biz_id,)).fetchone()
    return (dict(row), table, id_col, no_col) if row else None


def _check_biz_permission(db, biz_type, info):
    """R1/R2/R3 发起时校验单据归属（R3 仅可红冲自己录入的化验单）"""
    role, cid = g.current_user['role_code'], g.current_user['company_id']
    if role == 'R4':
        return True
    if role not in ('R1', 'R2', 'R3'):
        return False
    row = info[0]
    if biz_type == 'INSPECT':
        return row.get('create_by') == g.current_user['user_id'] or _alloc_owner(db, row.get('alloc_id'), cid)
    if biz_type == 'ALLOC':
        return row.get('company_id') == cid
    if biz_type == 'BILL':
        return row.get('company_id') == cid if role == 'R1' else row.get('supplier_id') == cid
    if biz_type == 'CONTRACT':
        return row.get('enterprise_id') == cid or _contract_supplier(db, row, cid)
    return False


def _alloc_owner(db, alloc_id, cid):
    if not alloc_id:
        return False
    return db.execute("SELECT 1 FROM allocation_order WHERE alloc_id=? AND company_id=?",
                      (alloc_id, cid)).fetchone() is not None


def _contract_supplier(db, row, cid):
    return bool(row.get('order_id')) and db.execute(
        "SELECT 1 FROM collective_order WHERE order_id=? AND supplier_id=?",
        (row['order_id'], cid)).fetchone() is not None


# ================= 变更申请（R1/R2 发起，R4 审核） =================

@bp.post('/biz/change/apply')
@roles_required('R1', 'R2')
@company_approved_required
def change_apply():
    d = request.get_json(force=True)
    db = get_db()
    biz_type = (d.get('biz_type') or '').strip()
    if biz_type not in BIZ_TYPES:
        return err('无效的单据类型')
    try:
        biz_id = int(d.get('biz_id'))
    except (TypeError, ValueError):
        return err('缺少业务单据')
    info = _biz_info(db, biz_type, biz_id)
    if not info:
        return err('业务单据不存在', http=404)
    if not _check_biz_permission(db, biz_type, info):
        return err('无权对该单据发起变更', code=403, http=403)
    before, after = (d.get('before_content') or '').strip(), (d.get('after_content') or '').strip()
    if not before or not after:
        return err('变更前内容与变更后内容均必填')
    if before == after:
        return err('变更前后内容相同，无需变更申请')

    cur = db.execute("INSERT INTO ore_biz_change(biz_type,biz_id,before_content,after_content,reason,"
                     "attachment_url,file_name,status,create_by,create_time) VALUES(?,?,?,?,?,?,?,?,?,?)",
                     (biz_type, biz_id, before, after, d.get('reason'), d.get('attachment_url'),
                      d.get('file_name'), 'PENDING', g.current_user['user_id'], _now()))
    db.commit()
    log_action('发起变更申请', f"{BIZ_NAME[biz_type]} #{biz_id}", ref_type='ore_biz_change', ref_id=cur.lastrowid)
    from .message import notify_role
    notify_role('R4', 1, '变更申请待审核',
                f"{g.current_user['real_name']} 对{BIZ_NAME[biz_type]}发起了变更申请，请审核",
                'BIZ_CHANGE', cur.lastrowid)
    return ok({'change_id': cur.lastrowid})


# ================= 红冲申请（R1/R2/R3 发起，R4 审核；R3 仅限自己录入的化验单） =================

@bp.post('/biz/redback/apply')
@roles_required('R1', 'R2', 'R3')
@company_approved_required
def redback_apply():
    d = request.get_json(force=True)
    db = get_db()
    biz_type = (d.get('biz_type') or '').strip()
    if biz_type not in BIZ_TYPES:
        return err('无效的单据类型')
    try:
        biz_id = int(d.get('biz_id'))
    except (TypeError, ValueError):
        return err('缺少业务单据')
    info = _biz_info(db, biz_type, biz_id)
    if not info:
        return err('业务单据不存在', http=404)
    if not _check_biz_permission(db, biz_type, info):
        return err('无权对该单据发起红冲', code=403, http=403)
    row, table, id_col, no_col = info
    if row.get('is_redbacked'):
        return err('该单据已被红冲作废，不可重复红冲')
    reason = (d.get('reason') or '').strip()
    if not reason or len(reason) < 5:
        return err('红冲原因必填且不少于5个字')

    redback_ton = redback_amount = None
    try:
        if d.get('redback_ton') not in (None, ''):
            redback_ton = round(float(d['redback_ton']), 2)
        if d.get('redback_amount') not in (None, ''):
            redback_amount = round(float(d['redback_amount']), 2)
    except (TypeError, ValueError):
        return err('红冲吨数/金额必须为数字')

    now = _now()
    cur = db.execute("INSERT INTO ore_biz_redback(biz_type,source_biz_id,redback_ton,redback_amount,reason,"
                     "status,create_by,create_time) VALUES(?,?,?,?,?, 'PENDING', ?, ?)",
                     (biz_type, biz_id, redback_ton, redback_amount, reason,
                      g.current_user['user_id'], now))
    rid = cur.lastrowid
    db.execute("UPDATE ore_biz_redback SET redback_no=? WHERE redback_id=?",
               (f"HC{now.replace('-', '').replace(':', '').replace(' ', '')}{rid:04d}", rid))
    db.commit()
    log_action('发起红冲申请', f"{BIZ_NAME[biz_type]} #{biz_id}", ref_type='ore_biz_redback', ref_id=rid)
    from .message import notify_role
    notify_role('R4', 1, '红冲申请待审核',
                f"{g.current_user['real_name']} 对{BIZ_NAME[biz_type]}发起了红冲申请，请审核",
                'BIZ_REDBACK', rid)
    return ok({'redback_id': rid})


# ================= 审核列表（R4） =================

@bp.get('/biz/apply/list')
@roles_required('R4')
def apply_list():
    db = get_db()
    kind = request.args.get('kind', 'change')  # change / redback / history
    page = int(request.args.get('page', 1)); size = int(request.args.get('page_size', 10))
    if kind == 'redback':
        sql = "SELECT r.* FROM ore_biz_redback r WHERE 1=1"
        if request.args.get('status'):
            sql += " AND r.status=?"; args0 = [request.args['status']]
        else:
            args0 = []
        sql += " ORDER BY r.create_time DESC"
        rows, total = paginate(db, sql, args0, page, size)
        for r in rows:
            _enrich_apply(db, r, 'redback')
        return ok({'list': rows, 'total': total, 'page': page, 'page_size': size})

    sql = "SELECT c.* FROM ore_biz_change c WHERE 1=1"
    args0 = []
    if request.args.get('status'):
        sql += " AND c.status=?"; args0.append(request.args['status'])
    if request.args.get('biz_type'):
        sql += " AND c.biz_type=?"; args0.append(request.args['biz_type'])
    sql += " ORDER BY c.create_time DESC"
    rows, total = paginate(db, sql, args0, page, size)
    for r in rows:
        _enrich_apply(db, r, 'change')
    return ok({'list': rows, 'total': total, 'page': page, 'page_size': size})


def _enrich_apply(db, r, kind):
    r['biz_type_name'] = BIZ_NAME.get(r['biz_type'], r['biz_type'])
    info = _biz_info(db, r['biz_type'], r['source_biz_id'] if kind == 'redback' else r['biz_id'])
    if info:
        r['biz_no'] = info[3] and info[0].get(info[3]) or f"#{info[0].get(info[2])}"
    else:
        r['biz_no'] = '-'
    if kind == 'change':
        u = db.execute("SELECT real_name FROM sys_user WHERE user_id=?", (r.get('create_by'),)).fetchone()
        r['apply_user'] = u['real_name'] if u else '-'
    else:
        u = db.execute("SELECT real_name FROM sys_user WHERE user_id=?", (r.get('create_by'),)).fetchone()
        r['apply_user'] = u['real_name'] if u else '-'


# ================= 变更审核（R4） =================

@bp.post('/biz/change/audit')
@roles_required('R4')
def change_audit():
    d = request.get_json(force=True)
    db = get_db()
    row = db.execute("SELECT * FROM ore_biz_change WHERE change_id=?", (d.get('change_id'),)).fetchone()
    if not row:
        return err('变更申请不存在', http=404)
    if row['status'] != 'PENDING':
        return err('该变更申请已审核')
    result = d.get('result')
    if result not in ('APPROVED', 'REJECTED'):
        return err('审核结论无效')
    remark = (d.get('review_remark') or '').strip()
    if result == 'REJECTED' and not remark:
        return err('驳回必须填写审核备注')
    now = _now()
    db.execute("UPDATE ore_biz_change SET status=?,review_remark=?,review_time=? WHERE change_id=?",
               (result, remark, now, row['change_id']))
    db.commit()
    log_action('变更申请审核', f"{BIZ_NAME.get(row['biz_type'])} #{row['biz_id']}",
               before='PENDING', after=result, ref_type='ore_biz_change', ref_id=row['change_id'])
    _notify_apply_result(db, row['create_by'], '变更申请', result, remark)
    return ok({'change_id': row['change_id'], 'status': result})


# ================= 红冲审核（R4）：通过 → 原单标记作废不参与结算 =================

@bp.post('/biz/redback/audit')
@roles_required('R4')
def redback_audit():
    d = request.get_json(force=True)
    db = get_db()
    row = db.execute("SELECT * FROM ore_biz_redback WHERE redback_id=?", (d.get('redback_id'),)).fetchone()
    if not row:
        return err('红冲申请不存在', http=404)
    if row['status'] != 'PENDING':
        return err('该红冲申请已审核')
    result = d.get('result')
    if result not in ('APPROVED', 'REJECTED'):
        return err('审核结论无效')
    remark = (d.get('review_remark') or '').strip()
    if result == 'REJECTED' and not remark:
        return err('驳回必须填写审核备注')
    now = _now()

    if result == 'APPROVED':
        info = _biz_info(db, row['biz_type'], row['source_biz_id'])
        if not info:
            return err('原业务单据已不存在，无法红冲')
        src, table, id_col, no_col = info
        if src.get('is_redbacked'):
            return err('原单已被红冲作废，不可重复操作')
        db.execute(f"UPDATE {table} SET is_redbacked=1 WHERE {id_col}=?", (row['source_biz_id'],))
        # 化验单红冲后状态标记，明细查询侧同步过滤
        if row['biz_type'] == 'INSPECT':
            db.execute("UPDATE ore_inspect_report SET status='REDBACKED',update_time=? WHERE report_id=?",
                       (now, row['source_biz_id']))

    db.execute("UPDATE ore_biz_redback SET status=?,review_remark=?,review_time=? WHERE redback_id=?",
               (result, remark, now, row['redback_id']))
    db.commit()
    log_action('红冲申请审核', f"{BIZ_NAME.get(row['biz_type'])} #{row['source_biz_id']}",
               before='PENDING', after=result, ref_type='ore_biz_redback', ref_id=row['redback_id'])
    _notify_apply_result(db, row['create_by'], '红冲申请', result, remark)
    return ok({'redback_id': row['redback_id'], 'status': result})


def _notify_apply_result(db, apply_user, label, result, remark):
    from .message import notify
    notify([apply_user], 2, f"{label}审核{'通过' if result == 'APPROVED' else '驳回'}",
           f"您的{label}审核{('通过' if result == 'APPROVED' else '驳回')}{('：' + remark) if remark else ''}")


# ================= 单据历史轨迹 =================

@bp.get('/biz/history')
@roles_required('R1', 'R2', 'R4')
@company_approved_required
def biz_history():
    db = get_db()
    biz_type = (request.args.get('biz_type') or '').strip()
    biz_id = request.args.get('biz_id')
    if biz_type not in BIZ_TYPES or not biz_id:
        return err('缺少单据类型或单据ID')
    changes = [dict(r) for r in db.execute(
        "SELECT * FROM ore_biz_change WHERE biz_type=? AND biz_id=? ORDER BY create_time DESC",
        (biz_type, biz_id)).fetchall()]
    redbacks = [dict(r) for r in db.execute(
        "SELECT * FROM ore_biz_redback WHERE biz_type=? AND source_biz_id=? ORDER BY create_time DESC",
        (biz_type, biz_id)).fetchall()]
    return ok({'changes': changes, 'redbacks': redbacks})
