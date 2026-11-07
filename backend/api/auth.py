"""认证模块（PRD T02）：企业注册、登录、当前用户与菜单权限码。"""
import hashlib
import os
import uuid

from flask import g, request

from .. import UPLOAD_DIR
from ..common import (ApiError, get_params, json_payload, ok, op_log,
                      require_fields, validate_credit_code, validate_password,
                      validate_phone)
from ..db import execute, q1
from ..security import (auth_required, hash_password, issue_token,
                        menus_for, roles_from_company_types, verify_password)
from . import bp

ALLOWED_LICENSE_EXT = {'pdf', 'jpg', 'jpeg', 'png'}
LICENSE_MAX_SIZE = 20 * 1024 * 1024


@bp.post('/auth/license')
def register_license():
    """注册专用：营业执照上传（免登录——注册时企业账号尚不存在）。

    与 /files 一致的扩展名白名单与 20MB 上限，仅落 sys_file（company_id/created_by 为空）。
    """
    f = request.files.get('file')
    if not f or not f.filename:
        raise ApiError(40001, '缺少上传文件（字段名 file）')
    ext = os.path.splitext(f.filename)[1].lower().lstrip('.')
    if ext not in ALLOWED_LICENSE_EXT:
        raise ApiError(40001, '仅支持 %s 格式' % '/'.join(sorted(ALLOWED_LICENSE_EXT)))
    data = f.read()
    if len(data) > LICENSE_MAX_SIZE:
        raise ApiError(40001, '文件大小不能超过 20MB')
    file_id = uuid.uuid4().hex
    name = '%s.%s' % (file_id, ext)
    path = os.path.join(UPLOAD_DIR, name)
    with open(path, 'wb') as out:
        out.write(data)
    execute(g.conn, """
        INSERT INTO sys_file (file_id, file_name, content_type, size_bytes, path)
        VALUES (%s,%s,%s,%s,%s)
        """, (file_id, f.filename, f.content_type, len(data), path))
    return ok({'fileId': file_id, 'fileName': f.filename, 'sha256': hashlib.sha256(data).hexdigest()})


@bp.post('/auth/register')
def register():
    p = get_params()
    require_fields(p, 'companyName', 'creditCode', 'companyTypes', 'province',
                   'contactName', 'contactPhone', 'username', 'password',
                   'licenseFileId')
    validate_credit_code(p['creditCode'])
    validate_phone(p['username'])
    validate_password(p['password'])

    # 前端选项编码 → 库内规范编码（ent_company.company_types 统一存 STEEL/SUPPLIER/LOGISTICS）
    type_alias = {'STEEL': 'STEEL', 'STEEL_BUYER': 'STEEL', 'SUPPLIER': 'SUPPLIER',
                  'LOGISTICS': 'LOGISTICS', 'LOGISTICS_CARRIER': 'LOGISTICS'}
    types = []
    for t in (s.strip() for s in str(p['companyTypes']).split(',')):
        if not t:
            continue
        t = type_alias.get(t, t)
        if t not in ('STEEL', 'SUPPLIER', 'LOGISTICS') or t in types:
            raise ApiError(40001, '企业类型不合法（STEEL/SUPPLIER/LOGISTICS 逗号分隔）')
        types.append(t)
    if not types:
        raise ApiError(40001, '企业类型不合法（STEEL/SUPPLIER/LOGISTICS 逗号分隔）')

    if q1(g.conn, "SELECT id FROM ent_company WHERE credit_code=%s AND is_deleted=0", (p['creditCode'],)):
        raise ApiError(40902, '统一社会信用代码已存在')
    if q1(g.conn, "SELECT id FROM sys_user WHERE username=%s AND is_deleted=0", (p['username'],)):
        raise ApiError(40902, '手机号已被注册')

    lic = q1(g.conn, "SELECT * FROM sys_file WHERE file_id=%s AND is_deleted=0", (p['licenseFileId'],))
    if not lic:
        raise ApiError(40401, '营业执照附件不存在，请先上传')

    roles = ','.join(roles_from_company_types(','.join(types)))
    if not roles:
        raise ApiError(40001, '企业类型不合法')
    cid = execute(g.conn, """
        INSERT INTO ent_company (company_name, credit_code, company_types, province, city,
                                 address, legal_person, contact_name, contact_phone,
                                 contact_email, business_scope, bank_name, bank_account,
                                 audit_status, created_by, updated_by)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'PENDING',0,0) RETURNING id
        """, (p['companyName'].strip(), p['creditCode'], ','.join(types), p['province'],
              p.get('city'), p.get('address'), p.get('legalPerson'), p['contactName'].strip(),
              p['contactPhone'], p.get('contactEmail'), p.get('businessScope'),
              p.get('bankName'), p.get('bankAccount')), returning_id=True)
    uid = execute(g.conn, """
        INSERT INTO sys_user (company_id, username, password_hash, real_name, roles, created_by)
        VALUES (%s,%s,%s,%s,%s,%s) RETURNING id
        """, (cid, p['username'], hash_password(p['password']),
              p.get('realName') or p['contactName'], roles, None), returning_id=True)
    execute(g.conn, "UPDATE sys_user SET created_by=%s WHERE id=%s", (uid, uid))
    execute(g.conn, "UPDATE ent_company SET created_by=%s, updated_by=%s WHERE id=%s", (uid, uid, cid))
    execute(g.conn, """
        INSERT INTO ent_qualification (company_id, file_id, file_name, file_type, created_by)
        VALUES (%s,%s,%s,'BUSINESS_LICENSE',%s)
        """, (cid, p['licenseFileId'], lic['file_name'], uid))
    op_log(g.conn, None, 'ent_company', cid, 'REGISTER', None, {'companyName': p['companyName']})
    return ok({'companyId': cid, 'userId': uid, 'auditStatus': 'PENDING'})


@bp.post('/auth/login')
def login():
    p = get_params()
    require_fields(p, 'username', 'password')
    user = q1(g.conn, "SELECT * FROM sys_user WHERE username=%s AND is_deleted=0", (p['username'],))
    if not user or not verify_password(p['password'], user['password_hash']):
        raise ApiError(40001, '用户名或密码错误')
    if user['status'] != 'ENABLED':
        raise ApiError(40301, '账号已被禁用')
    company = None
    if user['company_id']:
        company = q1(g.conn, "SELECT * FROM ent_company WHERE id=%s AND is_deleted=0", (user['company_id'],))
        if company and company['status'] != 'ENABLED':
            raise ApiError(40301, '企业已被停用')
    roles = [r for r in (user['roles'] or '').split(',') if r]
    token = issue_token(user, company, roles)
    op_log(g.conn, None, 'sys_user', user['id'], 'LOGIN', None, None)
    return ok({'token': token, 'user': _user_view(user, company, roles)})


@bp.get('/auth/me')
@auth_required
def me():
    ctx = g.ctx
    return ok(_user_view(ctx.user, ctx.company, ctx.roles))


def _user_view(user, company, roles):
    return {
        'userId': user['id'],
        'username': user['username'],
        'realName': user['real_name'],
        'roles': roles,
        'menus': menus_for(roles),
        'company': json_payload({
            'id': company['id'], 'companyName': company['company_name'],
            'companyTypes': company['company_types'], 'auditStatus': company['audit_status'],
            'status': company['status'],
        }) if company else None,
    }
