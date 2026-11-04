# -*- coding: utf-8 -*-
"""认证与 RBAC 权限控制"""
import hashlib
import secrets
from functools import wraps
from flask import Blueprint, request, g, current_app
from datetime import datetime, timedelta
from .db import get_db, _now
from .utils import ok, err, log_action

SESSION_DAYS = 7


def create_auth_bp():
    """每次 create_app 构造全新蓝图，避免测试中重复注册路由"""
    bp = Blueprint('auth', __name__)
    register_routes(bp)
    return bp


def hash_password(pwd, salt):
    return hashlib.sha256((salt + pwd).encode()).hexdigest()


def _token_from_request():
    h = request.headers.get('Authorization', '')
    if h.startswith('Bearer '):
        return h[7:]
    return request.args.get('token')


def current_user():
    """解析当前登录用户，未登录返回 None"""
    token = _token_from_request()
    if not token:
        return None
    db = get_db()
    row = db.execute(
        "SELECT u.*, s.token, s.expire_time FROM sys_session s JOIN sys_user u ON u.user_id=s.user_id"
        " WHERE s.token=?", (token,)).fetchone()
    if not row:
        return None
    if row['expire_time'] < _now():
        db.execute("DELETE FROM sys_session WHERE token=?", (token,))
        db.commit()
        return None
    if row['status'] != 'ACTIVE':
        return None
    return dict(row)


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        user = current_user()
        if not user:
            return err('未登录或登录已过期', code=401, http=401)
        g.current_user = user
        return fn(*args, **kwargs)
    return wrapper


def roles_required(*roles):
    """角色权限校验（RBAC）"""
    def deco(fn):
        @login_required
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if g.current_user['role_code'] not in roles:
                return err('无权访问该功能', code=403, http=403)
            return fn(*args, **kwargs)
        return wrapper
    return deco


def company_approved_required(fn):
    """企业资质审核通过才能使用业务功能（PRD-01 硬约束，R4 平台账号不受限）"""
    @wraps(fn)
    def wrapper(*args, **kwargs):
        user = g.current_user
        if user['role_code'] == 'R4':
            return fn(*args, **kwargs)
        if not user['company_id']:
            return err('账号未绑定企业主体', code=403, http=403)
        comp = get_db().execute("SELECT audit_status FROM company WHERE company_id=?",
                                (user['company_id'],)).fetchone()
        if not comp or comp['audit_status'] != 'APPROVED':
            return err('企业资质尚未审核通过，暂不能使用业务功能', code=403, http=403)
        return fn(*args, **kwargs)
    return wrapper


def register_routes(bp):
    @bp.post('/auth/register')
    def register():
        """企业主体注册（提交资质，待审核）。body: company_type, company_name, credit_code,
        contact, phone, password, username, partner_type/supplier_type, qualifications:[{cert_type,file_url,file_name}]"""
        db = get_db()
        d = request.get_json(force=True)
        required = ['company_type', 'company_name', 'username', 'password', 'contact', 'phone']
        for f in required:
            if not d.get(f):
                return err(f"缺少必填字段: {f}")
        if d['company_type'] not in ('DOWNSTREAM', 'SUPPLIER', 'PARTNER'):
            return err('无效的企业类型')
        if len(d['password']) < 6:
            return err('密码长度不得少于6位')
        if db.execute("SELECT 1 FROM company WHERE company_name=?", (d['company_name'],)).fetchone():
            return err('企业名称已存在')
        if db.execute("SELECT 1 FROM sys_user WHERE username=?", (d['username'],)).fetchone():
            return err('用户名已存在')
        role_map = {'DOWNSTREAM': 'R1', 'SUPPLIER': 'R2', 'PARTNER': 'R3'}
        now = _now()
        cur = db.execute(
            "INSERT INTO company(company_name,credit_code,company_type,partner_type,supplier_type,contact,phone,create_time)"
            " VALUES(?,?,?,?,?,?,?,?)",
            (d['company_name'], d.get('credit_code'), d['company_type'],
             d.get('partner_type'), d.get('supplier_type'), d['contact'], d['phone'], now))
        company_id = cur.lastrowid
        salt = secrets.token_hex(8)
        db.execute(
            "INSERT INTO sys_user(company_id,role_code,username,password_hash,salt,real_name,status,create_time)"
            " VALUES(?,?,?,?,?,?,'ACTIVE',?)",
            (company_id, role_map[d['company_type']], d['username'],
             hash_password(d['password'], salt), salt, d['contact'], now))
        for q in (d.get('qualifications') or []):
            if q.get('file_url'):
                db.execute("INSERT INTO qualification(company_id,cert_type,file_url,file_name,create_time)"
                           " VALUES(?,?,?,?,?)",
                           (company_id, q.get('cert_type', 'BUSINESS_LICENSE'), q['file_url'],
                            q.get('file_name'), now))
        db.commit()
        return ok({'company_id': company_id}, message='注册成功，等待平台资质审核')

    @bp.post('/auth/login')
    def login():
        d = request.get_json(force=True)
        db = get_db()
        u = db.execute("SELECT * FROM sys_user WHERE username=?", (d.get('username'),)).fetchone()
        if not u or hash_password(d.get('password', ''), u['salt']) != u['password_hash']:
            return err('用户名或密码错误')
        if u['status'] != 'ACTIVE':
            return err('账号已被停用')
        token = secrets.token_hex(24)
        now = datetime.now()
        db.execute("INSERT INTO sys_session(token,user_id,create_time,expire_time) VALUES(?,?,?,?)",
                   (token, u['user_id'], now.strftime('%Y-%m-%d %H:%M:%S'),
                    (now + timedelta(days=SESSION_DAYS)).strftime('%Y-%m-%d %H:%M:%S')))
        comp = None
        if u['company_id']:
            comp = dict(db.execute("SELECT company_id,company_name,company_type,audit_status FROM company"
                                   " WHERE company_id=?", (u['company_id'],)).fetchone())
        db.commit()
        return ok({'token': token, 'user': {
            'user_id': u['user_id'], 'username': u['username'], 'real_name': u['real_name'],
            'role_code': u['role_code'], 'company': comp}})

    @bp.post('/auth/logout')
    @login_required
    def logout():
        db = get_db()
        db.execute("DELETE FROM sys_session WHERE token=?", (_token_from_request(),))
        db.commit()
        return ok(message='已退出登录')

    @bp.get('/auth/me')
    @login_required
    def me():
        u = g.current_user
        db = get_db()
        comp = None
        if u['company_id']:
            comp = dict(db.execute(
                "SELECT company_id,company_name,company_type,audit_status,audit_remark FROM company"
                " WHERE company_id=?", (u['company_id'],)).fetchone())
        return ok({'user_id': u['user_id'], 'username': u['username'], 'real_name': u['real_name'],
                   'role_code': u['role_code'], 'company': comp})

    @bp.post('/auth/password')
    @login_required
    def change_password():
        d = request.get_json(force=True)
        db = get_db()
        u = db.execute("SELECT * FROM sys_user WHERE user_id=?", (g.current_user['user_id'],)).fetchone()
        if hash_password(d.get('old_password', ''), u['salt']) != u['password_hash']:
            return err('原密码错误')
        if len(d.get('new_password', '')) < 6:
            return err('新密码长度不得少于6位')
        salt = secrets.token_hex(8)
        db.execute("UPDATE sys_user SET password_hash=?, salt=? WHERE user_id=?",
                   (hash_password(d['new_password'], salt), salt, u['user_id']))
        db.commit()
        return ok(message='密码修改成功')
