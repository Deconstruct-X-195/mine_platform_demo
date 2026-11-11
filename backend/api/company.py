"""企业档案模块（PRD T03/T04/Fr-01-06）：本企业档案、信息维护与重提、企业目录。"""
from flask import g

from ..common import ApiError, get_params, json_payload, ok, op_log
from ..db import qall, q1
from ..security import auth_required, plat_required
from . import bp


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
    data['qualifications'] = json_payload(quals)
    return ok(data)


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
    sets = ', '.join('%s=%%s' % c for c in updates)
    args = list(updates.values())
    new_status = None
    resubmit = str(p.get('resubmit') or '') == 'true'
    if key_changed or resubmit:
        new_status = 'PENDING'
        sets += ', audit_status=%s, audit_remark=%s'
        args += ['PENDING', '关键信息变更，重新审核' if key_changed else '企业重新提交准入登记']
    sets += ', updated_by=%s, updated_at=now() WHERE id=%s'
    args += [ctx.user['id'], cur['id']]
    from ..db import execute
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
