"""企业档案模块（PRD T03/T04/Fr-01-06）：本企业档案、信息维护与重提、企业目录。"""
import json

from flask import g

from ..common import ApiError, get_params, json_payload, ok, op_log
from ..db import execute, qall, q1
from ..security import auth_required, plat_required
from . import bp


def _pending_changes(row):
    """解析企业待审核变更 JSON（无则返回 None）。"""
    raw = row.get('pending_changes') if isinstance(row, dict) else None
    if not raw:
        return None
    try:
        return json.loads(raw)
    except Exception:
        return None


@bp.get('/companies/me')
@auth_required
def my_company():
    ctx = g.ctx
    if not ctx.company:
        return ok({'company': None, 'qualifications': []})  # 平台管理员
    quals = qall(g.conn, """
        SELECT id, file_id AS "fileId", file_name AS "fileName", file_type AS "fileType",
               created_at AS "createdAt"
        FROM ent_qualification WHERE company_id=%s AND is_deleted=0 ORDER BY id
        """, (ctx.company['id'],))
    data = json_payload(dict(ctx.company))
    data['pendingChanges'] = _pending_changes(ctx.company)
    data['qualifications'] = json_payload(quals)
    return ok(data)


@bp.post('/companies/me/qualifications')
@auth_required
def add_qualification():
    """企业用户上传资质证照：文件先经 POST /files 落 sys_file，本接口做归属校验与资质关联。"""
    ctx = g.ctx
    if not ctx.company:
        raise ApiError(40301, '平台管理员无企业档案')
    p = get_params()
    f = q1(g.conn, "SELECT * FROM sys_file WHERE file_id=%s AND is_deleted=0", (p.get('fileId'),))
    if not f:
        raise ApiError(40401, '附件不存在，请先上传文件')
    if f['company_id'] and f['company_id'] != ctx.company['id']:
        raise ApiError(40301, '附件不属于当前企业')
    ftype = (p.get('fileType') or 'OTHER').upper()
    if ftype not in ('BUSINESS_LICENSE', 'OTHER'):
        raise ApiError(40001, '资质类型不合法')
    qid = execute(g.conn, """
        INSERT INTO ent_qualification (company_id, file_id, file_name, file_type, created_by)
        VALUES (%s,%s,%s,%s,%s) RETURNING id
        """, (ctx.company['id'], p.get('fileId'), f['file_name'], ftype, ctx.user['id']),
        returning_id=True)
    op_log(g.conn, ctx, 'ent_qualification', qid, 'UPLOAD',
           None, {'fileName': f['file_name'], 'fileType': ftype})
    return ok({'id': qid, 'fileId': p.get('fileId'), 'fileName': f['file_name'], 'fileType': ftype})


@bp.put('/companies/me')
@auth_required
def update_my_company():
    """信息维护：普通字段即时生效；关键信息（名称/信用代码/开户信息）变更重新审核（PRD 4.1）。"""
    ctx = g.ctx
    if not ctx.company:
        raise ApiError(40301, '平台账号无企业档案')
    p = get_params()
    cur = ctx.company
    key_fields = {'companyName': 'company_name', 'creditCode': 'credit_code',
                  'bankName': 'bank_name', 'bankAccount': 'bank_account'}
    normal = {'province': 'province', 'city': 'city', 'address': 'address',
              'legalPerson': 'legal_person', 'contactName': 'contact_name',
              'contactPhone': 'contact_phone', 'contactEmail': 'contact_email',
              'businessScope': 'business_scope'}
    updates, changed = {}, {}
    for jp, col in normal.items():
        if p.get(jp) is not None:
            updates[col] = str(p[jp])
            changed[jp] = p[jp]
    key_changed = False
    for jp, col in key_fields.items():
        if p.get(jp) is not None and str(p[jp]) != str(cur[col]):
            if jp == 'creditCode':
                from ..common import validate_credit_code
                validate_credit_code(p['creditCode'])
                dup = q1(g.conn, "SELECT id FROM ent_company WHERE credit_code=%s AND id<>%s AND is_deleted=0",
                         (p['creditCode'], cur['id']))
                if dup:
                    raise ApiError(40902, '统一社会信用代码已存在')
            updates[col] = str(p[jp])
            changed[jp] = p[jp]
            key_changed = True
    if not updates:
        raise ApiError(40001, '无有效变更字段')
    resubmit = str(p.get('resubmit') or '') == 'true'
    # 已准入企业（非重新提交登记）：变更不即时生效，暂存待运营端审核，审核通过后自动更新
    if cur['audit_status'] == 'APPROVED' and not resubmit:
        execute(g.conn, """
            UPDATE ent_company SET pending_changes=%s, audit_status='PENDING',
                   audit_remark='企业信息变更，待运营端审核', updated_by=%s, updated_at=now()
             WHERE id=%s
            """, (json.dumps(changed, ensure_ascii=False), ctx.user['id'], cur['id']))
        op_log(g.conn, ctx, 'ent_company', cur['id'], 'CHANGE REQUEST', None, changed)
        from ..common import send_msg
        send_msg(g.conn, cur['id'], '信息变更已提交',
                 '您提交的企业信息变更已进入运营端审核，审核通过后企业信息将自动更新。', 'COMPANY', cur['id'])
        return ok({'keyChanged': key_changed, 'auditStatus': 'PENDING', 'changePending': True})
    sets = ', '.join('%s=%%s' % c for c in updates)
    args = list(updates.values())
    new_status = None
    if key_changed or resubmit:
        new_status = 'PENDING'
        sets += ', audit_status=%s, audit_remark=%s'
        args += ['PENDING', '关键信息变更，重新审核' if key_changed else '企业重新提交准入登记']
    sets += ', updated_by=%s, updated_at=now() WHERE id=%s'
    args += [ctx.user['id'], cur['id']]
    execute(g.conn, 'UPDATE ent_company SET ' + sets, args)
    op_log(g.conn, ctx, 'ent_company', cur['id'], 'UPDATE', None, changed)
    if new_status:
        op_log(g.conn, ctx, 'ent_company', cur['id'], 'STATUS %s->PENDING' % cur['audit_status'],
               {'auditStatus': cur['audit_status']}, {'auditStatus': 'PENDING'})
    return ok({'keyChanged': key_changed, 'auditStatus': new_status or cur['audit_status']})


@bp.get('/companies')
@auth_required
def company_directory():
    """企业目录：邀请供应商/指派承运商时选用（仅返回已准入企业概要）。"""
    from flask import request
    typ = request.args.get('type')
    sql = """SELECT id, company_name AS "companyName", company_types AS "companyTypes",
                    contact_name AS "contactName"
             FROM ent_company WHERE audit_status='APPROVED' AND status='ENABLED' AND is_deleted=0"""
    args = []
    if typ:
        sql += " AND ',' || company_types || ',' LIKE %s"
        args.append('%%,%s,%%' % typ)
    sql += ' ORDER BY id'
    return ok({'list': json_payload(qall(g.conn, sql, args))})


@bp.get('/companies/<int:cid>')
@auth_required
def company_detail(cid):
    ctx = g.ctx
    if not ctx.is_plat and (not ctx.company or ctx.company['id'] != cid):
        raise ApiError(40301, '无权限查看该企业')
    row = q1(g.conn, "SELECT * FROM ent_company WHERE id=%s AND is_deleted=0", (cid,))
    if not row:
        raise ApiError(40401, '企业不存在')
    quals = qall(g.conn, """
        SELECT id, file_id AS "fileId", file_name AS "fileName", file_type AS "fileType"
        FROM ent_qualification WHERE company_id=%s AND is_deleted=0 ORDER BY id
        """, (cid,))
    users = []
    if ctx.is_plat:
        users = qall(g.conn, """
            SELECT id, username, real_name AS "realName", roles, status, created_at AS "createdAt"
            FROM sys_user WHERE company_id=%s AND is_deleted=0 ORDER BY id
            """, (cid,))
    data = json_payload(dict(row))
    data['pendingChanges'] = _pending_changes(row)
    data['qualifications'] = json_payload(quals)
    data['users'] = json_payload(users)
    # 企业变更信息：企业档案操作留痕（含操作人姓名）
    logs = qall(g.conn, """
        SELECT l.action, l.after_value, l.created_at AS "createdAt",
               u.real_name AS "operator"
        FROM sys_operation_log l
        LEFT JOIN sys_user u ON u.id = l.user_id
        WHERE l.biz_type='ent_company' AND l.biz_id=%s
        ORDER BY l.id DESC LIMIT 20
        """, (cid,))
    data['changeLogs'] = json_payload(logs)
    # 合作信息：需求/订单/合同合作统计
    coop = q1(g.conn, """
        SELECT
          (SELECT count(*) FROM biz_demand
            WHERE company_id=%s AND is_deleted=0 AND status<>'DRAFT') AS "demandCount",
          (SELECT count(*) FROM biz_order
            WHERE (buyer_id=%s OR supplier_id=%s) AND is_deleted=0) AS "orderCount",
          (SELECT coalesce(sum(quantity),0) FROM biz_order
            WHERE (buyer_id=%s OR supplier_id=%s) AND is_deleted=0) AS "totalQty",
          (SELECT coalesce(sum(amount),0) FROM biz_order
            WHERE (buyer_id=%s OR supplier_id=%s) AND is_deleted=0) AS "totalAmount",
          (SELECT count(*) FROM biz_contract c JOIN biz_order o ON o.id=c.order_id
            WHERE (o.buyer_id=%s OR o.supplier_id=%s) AND c.is_deleted=0) AS "contractCount",
          (SELECT max(created_at) FROM biz_order
            WHERE (buyer_id=%s OR supplier_id=%s) AND is_deleted=0) AS "lastDealAt"
        """, (cid,) * 11)
    data['coop'] = json_payload(dict(coop)) if coop else None
    return ok(data)
