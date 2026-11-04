# -*- coding: utf-8 -*-
"""矿石质检&化验管理模块 (PRD-09)：四类化验单（货源预检/船检/仓检/出库检）、
指标动态模板、扣水扣杂规则、自动计算结算干基吨数、审核留痕、数据权限隔离"""
from flask import Blueprint, request, g
from ..db import get_db, _now
from ..utils import ok, err, log_action, paginate, round2
from ..auth import roles_required, company_approved_required

bp = Blueprint('inspect', __name__)

REPORT_TYPES = {1: '货源预检', 2: '到港船检', 3: '仓内抽检', 4: '分拨出库检'}
TYPE_LINK = {1: 'source_id', 2: 'order_id', 3: 'alloc_id', 4: 'alloc_id'}


def _report_indexes(db, report_id):
    return [dict(r) for r in db.execute(
        "SELECT * FROM ore_inspect_index WHERE report_id=? ORDER BY id", (report_id,)).fetchall()]


def _enrich(db, r):
    r['report_type_name'] = REPORT_TYPES.get(r['report_type'], str(r['report_type']))
    if r.get('source_id'):
        src = db.execute("SELECT ore_category, resource_id FROM ore_resource WHERE resource_id=?",
                         (r['source_id'],)).fetchone()
        r['source_no'] = f"#{src['resource_id']}" if src else None
    if r.get('order_id'):
        o = db.execute("SELECT order_no FROM collective_order WHERE order_id=?", (r['order_id'],)).fetchone()
        r['order_no'] = o['order_no'] if o else None
    if r.get('logi_id'):
        t = db.execute("SELECT logi_no FROM logistics_task WHERE logi_id=?", (r['logi_id'],)).fetchone()
        r['logi_no'] = t['logi_no'] if t else None
    if r.get('alloc_id'):
        a = db.execute("SELECT alloc_no, company_id FROM allocation_order WHERE alloc_id=?",
                       (r['alloc_id'],)).fetchone()
        if a:
            r['alloc_no'] = a['alloc_no']
            c = db.execute("SELECT company_name FROM company WHERE company_id=?", (a['company_id'],)).fetchone()
            r['alloc_company'] = c['company_name'] if c else None
    return r


def _calc_deduct(db, category, wet_ton, indexes):
    """按启用的扣水扣杂规则计算扣减吨数：指标值超过阈值 → 湿基吨数 × 扣减比例%"""
    rules = db.execute("SELECT * FROM ore_inspect_deduct_rule WHERE status=1 AND ore_category=?",
                       (category,)).fetchall()
    idx_map = {i[0]: i[1] for i in indexes}  # indexes 为 (指标名, 指标值, 单位) 元组列表
    deduct_ton, rule_id = 0.0, None
    for rule in rules:
        val = idx_map.get(rule['index_name'])
        try:
            val = float(val)
        except (TypeError, ValueError):
            continue
        if val >= rule['threshold']:
            deduct_ton += wet_ton * rule['deduct_rate'] / 100.0
            if rule_id is None:
                rule_id = rule['rule_id']
    return round2(deduct_ton), rule_id


def _check_type_links(d, db):
    """按化验单类型校验关联业务单据，返回 (矿石品类, 错误提示, HTTP状态码)"""
    rtype = d['report_type']
    if rtype == 1:
        if not d.get('source_id'):
            return None, '货源预检化验单必须关联货源', 400
        src = db.execute("SELECT ore_category, supplier_id FROM ore_resource WHERE resource_id=?",
                         (d['source_id'],)).fetchone()
        if not src:
            return None, '关联货源不存在', 404
        if g.current_user['role_code'] == 'R2' and src['supplier_id'] != g.current_user['company_id']:
            return None, '只能为自有货源创建预检化验单', 403
        return src['ore_category'], None, None
    if rtype == 2:
        if not d.get('order_id'):
            return None, '到港船检化验单必须关联集采总订单', 400
        o = db.execute("SELECT ore_category FROM collective_order WHERE order_id=?", (d['order_id'],)).fetchone()
        if not o:
            return None, '集采总订单不存在', 404
        return o['ore_category'], None, None
    if rtype in (3, 4):
        if not d.get('alloc_id'):
            return None, f'{REPORT_TYPES[rtype]}化验单必须关联分拨单', 400
        a = db.execute("SELECT ore_category FROM allocation_order WHERE alloc_id=?", (d['alloc_id'],)).fetchone()
        if not a:
            return None, '分拨单不存在', 404
        return a['ore_category'], None, None
    return None, '无效的化验单类型', 400


# ================= 化验单保存（R4 / R3 录入，R2 预检） =================

@bp.post('/inspect/report/save')
@roles_required('R2', 'R3', 'R4')
@company_approved_required
def report_save():
    d = request.get_json(force=True)
    try:
        rtype = int(d.get('report_type'))
    except (TypeError, ValueError):
        return err('化验单类型无效')
    if rtype not in REPORT_TYPES:
        return err('化验单类型无效')
    if rtype == 1 and g.current_user['role_code'] not in ('R2', 'R4'):
        return err('货源预检化验单仅限供方或平台创建')
    if rtype in (2, 3, 4) and g.current_user['role_code'] not in ('R3', 'R4'):
        return err('船检/仓检/出库化验单仅限化验机构或平台录入')

    db = get_db()
    category, emsg, ehttp = _check_type_links(d, db)
    if emsg:
        return err(emsg, http=ehttp)

    indexes = d.get('indexes') or []
    if not isinstance(indexes, list):
        return err('化验指标格式错误')
    idx_rows = []
    for i in indexes:
        name = (i.get('index_name') or '').strip()
        if not name:
            return err('化验指标名称不能为空')
        idx_rows.append((name, str(i.get('index_value') or '').strip(), (i.get('index_unit') or '').strip() or None))

    wet_ton = None
    if d.get('wet_ton') not in (None, ''):
        try:
            wet_ton = round2(d['wet_ton'])
        except (TypeError, ValueError):
            return err('湿基吨数必须为数字')
        if wet_ton <= 0:
            return err('湿基吨数必须大于0')

    submit = bool(d.get('submit'))
    now = _now()
    report_id = d.get('report_id')

    if report_id:
        rpt = db.execute("SELECT * FROM ore_inspect_report WHERE report_id=?", (report_id,)).fetchone()
        if not rpt:
            return err('化验单不存在', http=404)
        if rpt['status'] in ('PENDING', 'APPROVED', 'REDBACKED'):
            return err('当前状态禁止修改（待审核/已审核/已红冲），如需调整走变更申请')
        if rpt['create_by'] != g.current_user['user_id'] and g.current_user['role_code'] != 'R4':
            return err('只能修改自己创建的草稿/驳回化验单')
        prev_deduct, prev_settle = rpt['deduct_ton'] or 0, rpt['settle_ton']

    deduct_ton, settle_ton, rule_id = 0.0, None, None
    if wet_ton and category:
        deduct_ton, rule_id = _calc_deduct(db, category, wet_ton, idx_rows)
        settle_ton = round2(wet_ton - deduct_ton)

    status = 'PENDING' if submit else 'DRAFT'
    if report_id:
        db.execute(
            "UPDATE ore_inspect_report SET report_type=?,source_id=?,order_id=?,logi_id=?,alloc_id=?,"
            "ore_category=?,inspect_org=?,sample_date=?,test_date=?,wet_ton=?,deduct_ton=?,settle_ton=?,"
            "rule_id=?,vessel_no=?,batch_no=?,sample_place=?,conclusion=?,attachment_url=?,file_name=?,"
            "remark=?,status=?,reject_reason=NULL,update_time=? WHERE report_id=?",
            (rtype, d.get('source_id'), d.get('order_id'), d.get('logi_id'), d.get('alloc_id'),
             category, d.get('inspect_org'), d.get('sample_date'), d.get('test_date'), wet_ton,
             deduct_ton if wet_ton else prev_deduct, settle_ton if wet_ton else prev_settle, rule_id,
             d.get('vessel_no'), d.get('batch_no'), d.get('sample_place'), d.get('conclusion'),
             d.get('attachment_url'), d.get('file_name'), d.get('remark'), status, now, report_id))
        db.execute("DELETE FROM ore_inspect_index WHERE report_id=?", (report_id,))
        rid = report_id
        log_action('更新化验单', f"{REPORT_TYPES[rtype]}", before='DRAFT', after=status,
                   ref_type='ore_inspect_report', ref_id=rid)
    else:
        cur = db.execute(
            "INSERT INTO ore_inspect_report(report_type,source_id,order_id,logi_id,alloc_id,ore_category,"
            "inspect_org,sample_date,test_date,wet_ton,deduct_ton,settle_ton,rule_id,vessel_no,batch_no,"
            "sample_place,conclusion,attachment_url,file_name,remark,status,create_by,create_time,update_time)"
            " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (rtype, d.get('source_id'), d.get('order_id'), d.get('logi_id'), d.get('alloc_id'),
             category, d.get('inspect_org'), d.get('sample_date'), d.get('test_date'), wet_ton,
             deduct_ton if wet_ton else 0, settle_ton, rule_id, d.get('vessel_no'), d.get('batch_no'),
             d.get('sample_place'), d.get('conclusion'), d.get('attachment_url'), d.get('file_name'),
             d.get('remark'), status, g.current_user['user_id'], now, now))
        rid = cur.lastrowid
        db.execute("UPDATE ore_inspect_report SET report_no=? WHERE report_id=?",
                   (f"IR{now.replace('-','').replace(':','').replace(' ','')}{rid:04d}", rid))
        log_action('创建化验单', f"{REPORT_TYPES[rtype]}", after=status,
                   ref_type='ore_inspect_report', ref_id=rid)

    for name, value, unit in idx_rows:
        db.execute("INSERT INTO ore_inspect_index(report_id,index_name,index_value,index_unit) VALUES(?,?,?,?)",
                   (rid, name, value, unit))
    db.commit()

    # 提交审核 → 通知平台管理员待办
    if submit:
        from .message import notify_role
        notify_role('R4', 1, '化验单待审核',
                    f"{g.current_user['real_name']} 提交了{REPORT_TYPES[rtype]}化验单，请及时审核",
                    'INSPECT', rid)
    rpt = db.execute("SELECT * FROM ore_inspect_report WHERE report_id=?", (rid,)).fetchone()
    out = _enrich(db, dict(rpt))
    out['indexes'] = _report_indexes(db, rid)
    return ok(out)


# ================= 化验单列表（数据权限隔离） =================

@bp.get('/inspect/report/list')
@roles_required('R1', 'R2', 'R3', 'R4')
@company_approved_required
def report_list():
    db = get_db()
    page = int(request.args.get('page', 1)); size = int(request.args.get('page_size', 10))
    sql = ("SELECT r.* FROM ore_inspect_report r WHERE r.is_redbacked=0")
    args = []
    role = g.current_user['role_code']
    cid = g.current_user['company_id']

    if role == 'R4':
        pass  # 平台全量
    elif role == 'R1':  # 下游：自己分拨单对应的化验单
        sql += " AND r.alloc_id IN (SELECT alloc_id FROM allocation_order WHERE company_id=?)"
        args.append(cid)
    elif role == 'R2':  # 供方：自己货源预检 + 自己供货订单的船检
        sql += " AND (r.source_id IN (SELECT resource_id FROM ore_resource WHERE supplier_id=?)"
        sql += "  OR r.order_id IN (SELECT order_id FROM collective_order WHERE supplier_id=?))"
        args.extend([cid, cid])
    elif role == 'R3':  # 配套方：自己录入的化验单 + 自己参与物流任务的船检
        sql += " AND (r.create_by=? OR r.logi_id IN (SELECT logi_id FROM logistics_task"
        sql += "  WHERE sea_partner_id=? OR port_partner_id=? OR warehouse_partner_id=? OR land_partner_id=?))"
        args.extend([g.current_user['user_id'], cid, cid, cid, cid])

    if request.args.get('report_type'):
        sql += " AND r.report_type=?"; args.append(int(request.args['report_type']))
    if request.args.get('ore_category'):
        sql += " AND r.ore_category=?"; args.append(request.args['ore_category'])
    if request.args.get('order_id'):
        sql += " AND r.order_id=?"; args.append(int(request.args['order_id']))
    if request.args.get('alloc_id'):
        sql += " AND r.alloc_id=?"; args.append(int(request.args['alloc_id']))
    if request.args.get('status'):
        sql += " AND r.status=?"; args.append(request.args['status'])
    if request.args.get('start_date'):
        sql += " AND r.sample_date>=?"; args.append(request.args['start_date'])
    if request.args.get('end_date'):
        sql += " AND r.sample_date<=?"; args.append(request.args['end_date'] + ' 23:59:59')
    sql += " ORDER BY r.create_time DESC"
    rows, total = paginate(db, sql, args, page, size)
    for r in rows:
        _enrich(db, r)
    return ok({'list': rows, 'total': total, 'page': page, 'page_size': size})


# ================= 化验单详情 =================

@bp.get('/inspect/report/detail')
@roles_required('R1', 'R2', 'R3', 'R4')
@company_approved_required
def report_detail():
    rid = request.args.get('report_id')
    db = get_db()
    rpt = db.execute("SELECT * FROM ore_inspect_report WHERE report_id=?", (rid,)).fetchone()
    if not rpt:
        return err('化验单不存在', http=404)
    d = _enrich(db, dict(rpt))
    # 数据权限校验
    role, cid = g.current_user['role_code'], g.current_user['company_id']
    allowed = role == 'R4' or d.get('create_by') == g.current_user['user_id']
    if not allowed and role == 'R1':
        allowed = db.execute("SELECT 1 FROM allocation_order WHERE alloc_id=? AND company_id=?",
                             (d.get('alloc_id'), cid)).fetchone() is not None
    if not allowed and role == 'R2':
        allowed = (d.get('source_id') and db.execute(
            "SELECT 1 FROM ore_resource WHERE resource_id=? AND supplier_id=?",
            (d['source_id'], cid)).fetchone()) or (d.get('order_id') and db.execute(
            "SELECT 1 FROM collective_order WHERE order_id=? AND supplier_id=?",
            (d['order_id'], cid)).fetchone())
    if not allowed and role == 'R3':
        allowed = db.execute(
            "SELECT 1 FROM logistics_task WHERE logi_id=? AND (sea_partner_id=? OR port_partner_id=?"
            " OR warehouse_partner_id=? OR land_partner_id=?)",
            (d.get('logi_id'), cid, cid, cid, cid)).fetchone() is not None
    if not allowed:
        return err('无权查看该化验单', code=403, http=403)
    d['indexes'] = _report_indexes(db, d['report_id'])
    return ok(d)


# ================= 化验单审核（R4） =================

@bp.post('/inspect/report/audit')
@roles_required('R4')
def report_audit():
    d = request.get_json(force=True)
    rid = d.get('report_id')
    result = d.get('result')
    if result not in ('APPROVED', 'REJECTED'):
        return err('审核结论无效')
    db = get_db()
    rpt = db.execute("SELECT * FROM ore_inspect_report WHERE report_id=?", (rid,)).fetchone()
    if not rpt:
        return err('化验单不存在', http=404)
    if rpt['status'] != 'PENDING':
        return err('仅待审核状态可审核')
    if result == 'REJECTED' and not (d.get('reject_reason') or '').strip():
        return err('驳回必须填写原因')
    now = _now()
    db.execute("UPDATE ore_inspect_report SET status=?,reject_reason=?,update_time=? WHERE report_id=?",
               (result, d.get('reject_reason'), now, rid))
    db.commit()
    log_action('化验单审核', f"{rpt['report_no']} {REPORT_TYPES.get(rpt['report_type'])}",
               before='PENDING', after=result, ref_type='ore_inspect_report', ref_id=rid)
    from .message import notify
    notify([rpt['create_by']], 2,
           f"化验单审核{'通过' if result == 'APPROVED' else '驳回'}",
           f"化验单 {rpt['report_no']} 审核{('通过' if result == 'APPROVED' else '驳回：' + (d.get('reject_reason') or ''))}",
           'INSPECT', rid)
    db.execute(
        "UPDATE ore_message SET is_finish=1 WHERE link_biz_type='INSPECT' AND biz_id=? AND msg_type=1",
        (str(rid),))
    db.commit()
    return ok({'report_id': int(rid), 'status': result})


# ================= 扣水扣杂规则（R4） =================

@bp.get('/inspect/rule/list')
@roles_required('R2', 'R3', 'R4')
def rule_list():
    db = get_db()
    sql = "SELECT * FROM ore_inspect_deduct_rule WHERE 1=1"
    args = []
    if request.args.get('ore_category'):
        sql += " AND ore_category=?"; args.append(request.args['ore_category'])
    sql += " ORDER BY rule_id"
    rows = [dict(r) for r in db.execute(sql, args).fetchall()]
    return ok({'list': rows, 'total': len(rows), 'page': 1, 'page_size': len(rows) or 10})


@bp.post('/inspect/rule/save')
@roles_required('R4')
def rule_save():
    d = request.get_json(force=True)
    db = get_db()
    name = (d.get('rule_name') or '').strip()
    cat = (d.get('ore_category') or '').strip()
    idx = (d.get('index_name') or '').strip()
    if not name or not cat or not idx:
        return err('规则名称、矿石品类、指标名称均必填')
    try:
        threshold = round2(d.get('threshold')); rate = round2(d.get('deduct_rate'))
    except (TypeError, ValueError):
        return err('阈值与扣减比例必须为数字')
    if threshold <= 0 or rate <= 0:
        return err('阈值与扣减比例必须大于0')
    if rate > 100:
        return err('扣减比例不可超过100%')
    now = _now()
    if d.get('rule_id'):
        db.execute("UPDATE ore_inspect_deduct_rule SET rule_name=?,ore_category=?,index_name=?,"
                   "threshold=?,deduct_rate=?,status=? WHERE rule_id=?",
                   (name, cat, idx, threshold, rate, 1 if d.get('status', 1) else 0, d['rule_id']))
        rid = d['rule_id']
    else:
        cur = db.execute("INSERT INTO ore_inspect_deduct_rule(rule_name,ore_category,index_name,"
                         "threshold,deduct_rate,status,create_time) VALUES(?,?,?,?,?,?,?)",
                         (name, cat, idx, threshold, rate, 1 if d.get('status', 1) else 0, now))
        rid = cur.lastrowid
    db.commit()
    log_action('保存扣水扣杂规则', f"{name}（{cat}/{idx}≥{threshold} 扣{rate}%）",
               ref_type='ore_inspect_deduct_rule', ref_id=rid)
    return ok({'rule_id': rid})


@bp.post('/inspect/rule/<int:rid>/toggle')
@roles_required('R4')
def rule_toggle(rid):
    db = get_db()
    row = db.execute("SELECT * FROM ore_inspect_deduct_rule WHERE rule_id=?", (rid,)).fetchone()
    if not row:
        return err('规则不存在', http=404)
    db.execute("UPDATE ore_inspect_deduct_rule SET status=? WHERE rule_id=?",
               (0 if row['status'] else 1, rid))
    db.commit()
    log_action('启用/停用扣减规则', row['rule_name'], ref_type='ore_inspect_deduct_rule', ref_id=rid)
    return ok({'status': 0 if row['status'] else 1})


# ================= 导出 =================

@bp.get('/inspect/report/export')
@roles_required('R1', 'R2', 'R3', 'R4')
@company_approved_required
def report_export():
    db = get_db()
    sql = ("SELECT r.* FROM ore_inspect_report r WHERE r.is_redbacked=0")
    args = []
    role, cid = g.current_user['role_code'], g.current_user['company_id']
    if role == 'R1':
        sql += " AND r.alloc_id IN (SELECT alloc_id FROM allocation_order WHERE company_id=?)"; args.append(cid)
    elif role == 'R2':
        sql += " AND (r.source_id IN (SELECT resource_id FROM ore_resource WHERE supplier_id=?)"
        sql += "  OR r.order_id IN (SELECT order_id FROM collective_order WHERE supplier_id=?))"
        args.extend([cid, cid])
    elif role == 'R3':
        sql += " AND r.create_by=?"; args.append(g.current_user['user_id'])
    if request.args.get('report_type'):
        sql += " AND r.report_type=?"; args.append(int(request.args['report_type']))
    if request.args.get('status'):
        sql += " AND r.status=?"; args.append(request.args['status'])
    sql += " ORDER BY r.create_time DESC"
    rows = [dict(r) for r in db.execute(sql, args).fetchall()]
    headers = ['化验单编号', '类型', '品类', '化验机构', '采样日期', '湿基吨数', '扣减吨数', '结算吨数', '状态', '结论']
    data = [[r['report_no'], REPORT_TYPES.get(r['report_type']), r['ore_category'], r['inspect_org'] or '-',
             r['sample_date'] or '-', r['wet_ton'] or '-', r['deduct_ton'] or 0, r['settle_ton'] or '-',
             r['status'], r['conclusion'] or '-'] for r in rows]
    log_action('导出化验单', f"{len(data)} 条")
    return _excel(headers, data, f'化验单台账_{_now()[:10]}.xlsx')


def _excel(headers, data, filename):
    from ..utils import export_excel
    return export_excel(headers, [('化验单台账', data)], filename)
