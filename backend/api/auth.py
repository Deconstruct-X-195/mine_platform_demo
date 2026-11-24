"""认证模块（PRD T02）：企业注册、登录、当前用户与菜单权限码。"""
import hashlib
import os
import threading
import time
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

# ---- C7（部署适配方案 §5）：登录失败限流（进程内滑动窗口）----
# 同一 IP+用户名 60 秒内失败 5 次 → 锁定 10 分钟；登录成功即清零。
# 仅拦截暴力破解，不改变登录业务语义（密码校验/账号状态判断逻辑不变）。
_LOGIN_WINDOW = 60.0
_LOGIN_MAX_FAILS = 5
_LOGIN_LOCK_SECONDS = 600.0
_login_fails = {}      # (ip, username) -> [失败时间戳]
_login_locks = {}      # (ip, username) -> 锁定截止时间戳
_login_mutex = threading.Lock()


def _client_ip():
    """登录限流客户端 IP（P1-1）：生产经 Nginx 反代部署（app 仅监听 127.0.0.1）时，
    优先取反代注入的 X-Real-IP——否则全体客户端 remote_addr 均为 127.0.0.1，
    任一来源 5 次失败即锁定全体用户 10 分钟。本地直连（无反代头）回退 remote_addr。"""
    return request.headers.get('X-Real-IP') or request.remote_addr or '-'


def _login_locked(key):
    with _login_mutex:
        now = time.monotonic()
        _login_fails[key] = [t for t in _login_fails.get(key, []) if now - t < _LOGIN_WINDOW]
        locked_until = _login_locks.get(key)
        return bool(locked_until and now < locked_until)


def _login_record_fail(key):
    with _login_mutex:
        now = time.monotonic()
        fails = [t for t in _login_fails.get(key, []) if now - t < _LOGIN_WINDOW]
        fails.append(now)
        if len(fails) >= _LOGIN_MAX_FAILS:
            _login_locks[key] = now + _LOGIN_LOCK_SECONDS
            _login_fails.pop(key, None)  # 锁定后清空计数，锁定解除后重新计窗
        else:
            _login_fails[key] = fails


def _login_clear(key):
    with _login_mutex:
        _login_fails.pop(key, None)
        _login_locks.pop(key, None)


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
    # 注册页不再采集 省份/城市/开户银行/银行账号；地址改为必填（前端校验），province 降为可选
    require_fields(p, 'companyName', 'creditCode', 'companyTypes',
                   'contactName', 'contactPhone', 'username', 'password',
                   'legalPerson', 'licenseFileId')
    validate_credit_code(p['creditCode'])
    validate_phone(p['username'])
    validate_password(p['password'])

    # 前端选项编码 → 库内规范编码（ent_company.company_types 统一存 STEEL/SUPPLIER）
    type_alias = {'STEEL': 'STEEL', 'STEEL_BUYER': 'STEEL', 'SUPPLIER': 'SUPPLIER'}
    types = []
    for t in (s.strip() for s in str(p['companyTypes']).split(',')):
        if not t:
            continue
        t = type_alias.get(t, t)
        if t not in ('STEEL', 'SUPPLIER') or t in types:
            raise ApiError(40001, '企业类型不合法（STEEL/SUPPLIER 逗号分隔）')
        types.append(t)
    if not types:
        raise ApiError(40001, '企业类型不合法（STEEL/SUPPLIER 逗号分隔）')

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
        """, (p['companyName'].strip(), p['creditCode'], ','.join(types), p.get('province'),
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
    key = (_client_ip(), p['username'])
    if _login_locked(key):
        raise ApiError(40001, '登录尝试过于频繁，请 10 分钟后再试')
    user = q1(g.conn, "SELECT * FROM sys_user WHERE username=%s AND is_deleted=0", (p['username'],))
    if not user or not verify_password(p['password'], user['password_hash']):
        _login_record_fail(key)
        raise ApiError(40001, '用户名或密码错误')
    if user['status'] != 'ENABLED':
        raise ApiError(40301, '账号已被禁用')
    company = None
    if user['company_id']:
        company = q1(g.conn, "SELECT * FROM ent_company WHERE id=%s AND is_deleted=0", (user['company_id'],))
        if company and company['status'] != 'ENABLED':
            raise ApiError(40301, '企业已被停用')
    roles = [r for r in (user['roles'] or '').split(',') if r]
    # 承运商端已下线：仅承运商角色的账号不可登录本平台
    if roles and all(r == 'LOGISTICS_CARRIER' for r in roles):
        raise ApiError(40301, '本平台暂不开放承运商端登录')
    _login_clear(key)  # 登录成功清零失败计数（C7）
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
