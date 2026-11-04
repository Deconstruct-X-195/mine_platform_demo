# -*- coding: utf-8 -*-
"""合同管理模块 (PRD-10)：上游供货/下游分拨两类合同台账、生命周期状态流转、
附件留存、变更记录、到期预警联动消息模块、数据权限隔离、台账导出"""
from flask import Blueprint, request, g
from ..db import get_db, _now
from ..utils import ok, err, log_action, paginate, round2, export_excel
from ..auth import roles_required, company_approved_required

bp = Blueprint('contract', __name__)

CONTRACT_STATUS = ['DRAFT', 'PENDING_STAMP', 'EFFECTIVE', 'EXECUTING', 'FINISHED', 'TERMINATED']
STATUS_NAME = {'DRAFT': '草稿', 'PENDING_STAMP': '待盖章', 'EFFECTIVE': '已生效',
               'EXECUTING': '履约中', 'FINISHED': '已完成', 'TERMINATED': '已终止'}


def _enrich(db, c):
    c['status_name'] = STATUS_NAME.get(c['status'], c['status'])
    c['contract_type_name'] = '上游供货合同' if c['contract_type'] == 1 else '下游分拨合同'
    e = db.execute("SELECT company_name FROM company WHERE company_id=?", (c['enterprise_id'],)).fetchone()
    c['enterprise_name'] = e['company_name'] if e else None
    if c.get('order_id'):
        o = db.execute("SELECT order_no FROM collective_order WHERE order_id=?", (c['order_id'],)).fetchone()
        c['order_no'] = o['order_no'] if o else None
    if c.get('alloc_id'):
        a = db.execute("SELECT alloc_no FROM allocation_order WHERE alloc_id=?", (c['alloc_id'],)).fetchone()
        c['alloc_no'] = a['alloc_no'] if a else None
    return c


def _attach_list(db, contract_id):
    return [dict(r) for r in db.execute(
        "SELECT * FROM ore_contract_attach WHERE contract_id=? ORDER BY id", (contract_id,)).fetchall()]


def _visible(db, role, cid):
    """返回当前角色可见合同的基础 SQL 条件"""
    if role == 'R4':
        return "1=1", []
    if role == 'R1':
        return ("(contract_type=2 AND (enterprise_id=? OR alloc_id IN"
                " (SELECT alloc_id FROM allocation_order WHERE company_id=?)))", [cid, cid])
    if role == 'R2':
        return ("(contract_type=1 AND (enterprise_id=? OR order_id IN"
                " (SELECT order_id FROM collective_order WHERE supplier_id=?)))", [cid, cid])
    return "1=0", []


# ================= 合同保存（R4） =================

@bp.post('/contract/save')
@roles_required('R4')
def contract_save():
    d = request.get_json(force=True)
    db = get_db()
    try:
        ctype = int(d.get('contract_type'))
    except (TypeError, ValueError):
        return err('合同类型无效')
    if ctype not in (1, 2):
        return err('合同类型无效')
    if ctype == 1 and not d.get('order_id'):
        return err('上游供货合同必须关联集采总订单')
    if ctype == 2 and not d.get('alloc_id'):
        return err('下游分拨合同必须关联分拨单')

    order = alloc = None
    if ctype == 1:
        order = db.execute("SELECT * FROM collective_order WHERE order_id=?", (d['order_id'],)).fetchone()
        if not order:
            return err('集采总订单不存在', http=404)
        enterprise_id = d.get('enterprise_id') or order['supplier_id']
    else:
        alloc = db.execute("SELECT * FROM allocation_order WHERE alloc_id=?", (d['alloc_id'],)).fetchone()
        if not alloc:
            return err('分拨单不存在', http=404)
        enterprise_id = d.get('enterprise_id') or alloc['company_id']
    ent = db.execute("SELECT company_id, company_name FROM company WHERE company_id=?", (enterprise_id,)).fetchone()
    if not ent:
        return err('合同相对方企业不存在', http=404)

    category = d.get('ore_category') or (order['ore_category'] if order else alloc['ore_category'])
    plan_ton = unit_price = amount = None
    for key, val in (('plan_ton', d.get('plan_ton')), ('unit_price', d.get('unit_price')),
                     ('contract_amount', d.get('contract_amount'))):
        if val not in (None, ''):
            try:
                v = round2(val)
            except (TypeError, ValueError):
                return err(f'{key} 必须为数字')
            if v <= 0:
                return err(f'{key} 必须大于0')
            if key == 'plan_ton':
                plan_ton = v
            elif key == 'unit_price':
                unit_price = v
            else:
                amount = v

    from datetime import datetime as _dt
    for date_key in ('sign_date', 'effective_date', 'expire_date'):
        if d.get(date_key):
            try:
                _dt.strptime(str(d[date_key]), '%Y-%m-%d')
            except ValueError:
                return err(f'{date_key} 格式应为 YYYY-MM-DD')

    now = _now()
    contract_id = d.get('contract_id')
    if contract_id:
        old = db.execute("SELECT * FROM ore_contract WHERE contract_id=?", (contract_id,)).fetchone()
        if not old:
            return err('合同不存在', http=404)
        if old['status'] != 'DRAFT':
            return err('仅草稿状态合同可编辑，已生效合同调整请走变更协议')
        db.execute(
            "UPDATE ore_contract SET contract_type=?,order_id=?,alloc_id=?,enterprise_id=?,ore_category=?,"
            "plan_ton=?,unit_price=?,contract_amount=?,sign_date=?,effective_date=?,expire_date=?,"
            "pay_remark=?,remark=?,update_time=? WHERE contract_id=?",
            (ctype, d.get('order_id'), d.get('alloc_id'), enterprise_id, category, plan_ton, unit_price,
             amount, d.get('sign_date'), d.get('effective_date'), d.get('expire_date'),
             d.get('pay_remark'), d.get('remark'), now, contract_id))
        log_action('编辑合同草稿', old['contract_no'], ref_type='ore_contract', ref_id=contract_id)
    else:
        cur = db.execute(
            "INSERT INTO ore_contract(contract_type,order_id,alloc_id,enterprise_id,ore_category,plan_ton,"
            "unit_price,contract_amount,sign_date,effective_date,expire_date,status,pay_remark,remark,"
            "create_by,create_time,update_time) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (ctype, d.get('order_id'), d.get('alloc_id'), enterprise_id, category, plan_ton, unit_price,
             amount, d.get('sign_date'), d.get('effective_date'), d.get('expire_date'), 'DRAFT',
             d.get('pay_remark'), d.get('remark'), g.current_user['user_id'], now, now))
        contract_id = cur.lastrowid
        contract_no = f"HT{now.replace('-', '').replace(':', '').replace(' ', '')}{contract_id:04d}"
        db.execute("UPDATE ore_contract SET contract_no=? WHERE contract_id=?", (contract_no, contract_id))
        log_action('创建合同草稿', contract_no, ref_type='ore_contract', ref_id=contract_id)

    for att in (d.get('attachments') or []):
        if att.get('file_url'):
            db.execute("INSERT INTO ore_contract_attach(contract_id,attach_type,file_url,file_name,upload_time)"
                       " VALUES(?,?,?,?,?)",
                       (contract_id, att.get('attach_type', 'MAIN'), att['file_url'], att.get('file_name'), now))
    db.commit()
    row = db.execute("SELECT * FROM ore_contract WHERE contract_id=?", (contract_id,)).fetchone()
    out = _enrich(db, dict(row))
    out['attachments'] = _attach_list(db, contract_id)
    return ok(out)


# ================= 合同台账（数据权限隔离） =================

@bp.get('/contract/list')
@roles_required('R1', 'R2', 'R4')
@company_approved_required
def contract_list():
    db = get_db()
    page = int(request.args.get('page', 1)); size = int(request.args.get('page_size', 10))
    cond, args = _visible(db, g.current_user['role_code'], g.current_user['company_id'])
    sql = f"SELECT c.* FROM ore_contract c WHERE {cond}"
    if request.args.get('contract_type'):
        sql += " AND c.contract_type=?"; args.append(int(request.args['contract_type']))
    if request.args.get('enterprise_id'):
        sql += " AND c.enterprise_id=?"; args.append(int(request.args['enterprise_id']))
    if request.args.get('status'):
        sql += " AND c.status=?"; args.append(request.args['status'])
    if request.args.get('keyword'):
        kw = f"%{request.args['keyword']}%"
        sql += " AND (c.contract_no LIKE ? OR c.ore_category LIKE ?)"; args.extend([kw, kw])
    if request.args.get('effective_start'):
        sql += " AND c.effective_date>=?"; args.append(request.args['effective_start'])
    if request.args.get('effective_end'):
        sql += " AND c.effective_date<=?"; args.append(request.args['effective_end'])
    sql += " ORDER BY c.create_time DESC"
    rows, total = paginate(db, sql, args, page, size)
    for r in rows:
        _enrich(db, r)
    return ok({'list': rows, 'total': total, 'page': page, 'page_size': size})


# ================= 合同详情 =================

@bp.get('/contract/detail')
@roles_required('R1', 'R2', 'R4')
@company_approved_required
def contract_detail():
    cid = request.args.get('contract_id')
    db = get_db()
    row = db.execute("SELECT * FROM ore_contract WHERE contract_id=?", (cid,)).fetchone()
    if not row:
        return err('合同不存在', http=404)
    cond, args = _visible(db, g.current_user['role_code'], g.current_user['company_id'])
    if not db.execute(f"SELECT 1 FROM ore_contract WHERE contract_id=? AND {cond}",
                      [int(cid)] + args).fetchone():
        return err('无权查看该合同', code=403, http=403)
    d = _enrich(db, dict(row))
    d['attachments'] = _attach_list(db, row['contract_id'])
    d['changes'] = [dict(r) for r in db.execute(
        "SELECT * FROM ore_contract_change WHERE contract_id=? ORDER BY id DESC", (row['contract_id'],)).fetchall()]
    return ok(d)


# ================= 状态流转（R4） =================

TRANSITIONS = {
    'DRAFT': ['PENDING_STAMP'],
    'PENDING_STAMP': ['EFFECTIVE'],
    'EFFECTIVE': ['EXECUTING', 'TERMINATED'],
    'EXECUTING': ['FINISHED', 'TERMINATED'],
    'FINISHED': [], 'TERMINATED': [],
}


@bp.post('/contract/status/update')
@roles_required('R4')
def status_update():
    d = request.get_json(force=True)
    db = get_db()
    row = db.execute("SELECT * FROM ore_contract WHERE contract_id=?", (d.get('contract_id'),)).fetchone()
    if not row:
        return err('合同不存在', http=404)
    target = d.get('status')
    if target not in TRANSITIONS.get(row['status'], []):
        return err(f"合同状态不允许从 {STATUS_NAME.get(row['status'])} 变更为 {STATUS_NAME.get(target, target)}")
    if target == 'PENDING_STAMP' and not row['contract_no']:
        return err('合同编号缺失，无法提交盖章')
    if target == 'EFFECTIVE':
        stamp_no = (d.get('stamp_no') or '').strip()
        if not stamp_no:
            return err('录入盖章信息（盖章编号）后方可生效')
        if not row['effective_date'] and not d.get('effective_date'):
            return err('请提供合同生效日期')
        eff = d.get('effective_date') or row['effective_date']
        db.execute("UPDATE ore_contract SET status='EFFECTIVE',effective_date=?,update_time=? WHERE contract_id=?",
                   (eff, _now(), row['contract_id']))
        detail = f"盖章编号 {stamp_no}"
    elif target == 'TERMINATED':
        reason = (d.get('terminate_reason') or '').strip()
        if not reason:
            return err('终止必须填写终止原因')
        db.execute("UPDATE ore_contract SET status='TERMINATED',terminate_reason=?,update_time=? WHERE contract_id=?",
                   (reason, _now(), row['contract_id']))
        detail = f"终止原因：{reason}"
    else:
        db.execute("UPDATE ore_contract SET status=?,update_time=? WHERE contract_id=?",
                   (target, _now(), row['contract_id']))
        detail = STATUS_NAME[target]

    db.commit()
    log_action('合同状态变更', f"{row['contract_no']} → {detail}", before=row['status'], after=target,
               ref_type='ore_contract', ref_id=row['contract_id'])
    # 通知相对方
    from .message import notify_company
    notify_company(db, row['enterprise_id'], 2,
                   f"合同状态更新：{row['contract_no']}",
                   f"合同 {row['contract_no']} 当前状态：{STATUS_NAME.get(target)}（{detail}）",
                   'CONTRACT', row['contract_id'])
    return ok({'contract_id': row['contract_id'], 'status': target})


# ================= 变更记录 + 补充协议 =================

@bp.post('/contract/change/add')
@roles_required('R2', 'R4')
@company_approved_required
def change_add():
    d = request.get_json(force=True)
    db = get_db()
    row = db.execute("SELECT * FROM ore_contract WHERE contract_id=?", (d.get('contract_id'),)).fetchone()
    if not row:
        return err('合同不存在', http=404)
    if g.current_user['role_code'] == 'R2':
        cond, args = _visible(db, 'R2', g.current_user['company_id'])
        if not db.execute(f"SELECT 1 FROM ore_contract WHERE contract_id=? AND {cond}",
                          [row['contract_id']] + args).fetchone():
            return err('无权操作该合同', code=403, http=403)
    content = (d.get('change_content') or '').strip()
    if not content:
        return err('变更内容必填')
    now = _now()
    cur = db.execute("INSERT INTO ore_contract_change(contract_id,change_content,reason,attachment_url,"
                     "file_name,create_by,create_time) VALUES(?,?,?,?,?,?,?)",
                     (row['contract_id'], content, d.get('reason'), d.get('attachment_url'),
                      d.get('file_name'), g.current_user['user_id'], now))
    if d.get('attachment_url'):  # 补充协议附件同步进附件表
        db.execute("INSERT INTO ore_contract_attach(contract_id,attach_type,file_url,file_name,upload_time)"
                   " VALUES(?,?,?,?,?)",
                   (row['contract_id'], 'CHANGE', d['attachment_url'], d.get('file_name'), now))
    db.commit()
    log_action('新增合同变更记录', f"{row['contract_no']}：{content[:50]}",
               ref_type='ore_contract', ref_id=row['contract_id'])
    from .message import notify_role
    notify_role('R4', 1, '合同变更记录待关注',
                f"合同 {row['contract_no']} 新增变更/补充协议，请知悉",
                'CONTRACT', row['contract_id'])
    return ok({'change_id': cur.lastrowid})


# ================= 导出 =================

@bp.get('/contract/export')
@roles_required('R1', 'R2', 'R4')
@company_approved_required
def contract_export():
    db = get_db()
    cond, args = _visible(db, g.current_user['role_code'], g.current_user['company_id'])
    sql = f"SELECT c.* FROM ore_contract c WHERE {cond} ORDER BY c.create_time DESC"
    rows = [dict(r) for r in db.execute(sql, args).fetchall()]
    headers = ['合同编号', '类型', '相对方', '品类', '预估吨数', '合同金额', '签订日期', '生效日期', '到期日期', '状态']
    data = []
    for r in rows:
        _enrich(db, r)
        data.append([r['contract_no'], r['contract_type_name'], r['enterprise_name'], r['ore_category'] or '-',
                     r['plan_ton'] or '-', r['contract_amount'] or '-', r['sign_date'] or '-',
                     r['effective_date'] or '-', r['expire_date'] or '-', r['status_name']])
    log_action('导出合同台账', f"{len(data)} 条")
    return export_excel(headers, [('合同台账', data)], f'合同台账_{_now()[:10]}.xlsx')
