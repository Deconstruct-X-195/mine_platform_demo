"""安全层：BCrypt 口令、JWT（HS256，8 小时有效期）、登录态与角色鉴权。

JWT 契约（PRD 6.3）：Authorization: Bearer <token>，exp=签发+8h，过期/无效返回
HTTP 401 + {"code":40101,"message":"未登录或登录已过期","data":null}。
"""
import base64
import hashlib
import hmac
import json
import os
import time
import uuid
from datetime import datetime

from flask import g, request

from .common import ApiError
from .db import q1

# TODO(PRD待确认): 演示环境使用固定密钥，生产必须从环境变量/密管注入。
JWT_SECRET = os.environ.get('MINE_JWT_SECRET', 'mine-platform-demo-secret-2026')
JWT_TTL_SECONDS = 8 * 3600

ROLES_PLAT = ['PLAT_ADMIN']
ROLE_STEEL = 'STEEL_BUYER'
ROLE_SUPPLIER = 'SUPPLIER'
ROLE_CARRIER = 'LOGISTICS_CARRIER'


def hash_password(plain: str) -> str:
    import bcrypt
    return bcrypt.hashpw(plain.encode('utf-8'), bcrypt.gensalt(rounds=10)).decode('ascii')


def verify_password(plain: str, hashed: str) -> bool:
    import bcrypt
    try:
        return bcrypt.checkpw(plain.encode('utf-8'), hashed.encode('ascii'))
    except ValueError:
        return False


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b'=').decode('ascii')


def _b64url_decode(s: str) -> bytes:
    pad = '=' * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)


def jwt_encode(payload: dict) -> str:
    header = {'alg': 'HS256', 'typ': 'JWT'}
    seg = '.'.join([
        _b64url(json.dumps(header, separators=(',', ':')).encode()),
        _b64url(json.dumps(payload, separators=(',', ':')).encode()),
    ])
    sig = hmac.new(JWT_SECRET.encode(), seg.encode(), hashlib.sha256).digest()
    return seg + '.' + _b64url(sig)


def jwt_decode(token: str) -> dict:
    try:
        h, p, s = token.split('.')
        seg = h + '.' + p
        expect = _b64url(hmac.new(JWT_SECRET.encode(), seg.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(expect, s):
            raise ValueError('bad signature')
        payload = json.loads(_b64url_decode(p))
        if float(payload.get('exp', 0)) < time.time():
            raise ValueError('expired')
        return payload
    except Exception:
        raise ApiError(40101, '未登录或登录已过期', http=401)


class Ctx:
    """当前登录上下文。"""

    def __init__(self, user, company, roles, ip):
        self.user = user
        self.company = company
        self.roles = roles
        self.ip = ip

    @property
    def is_plat(self):
        return 'PLAT_ADMIN' in self.roles

    def has_role(self, *roles):
        return bool(set(self.roles) & set(roles))


MENUS = {
    ROLE_STEEL: ['demand', 'price', 'inquiry', 'bargain', 'order', 'contract',
                 'logistics', 'track', 'settlement', 'profile'],
    ROLE_SUPPLIER: ['pool', 'forecast', 'inquiry', 'bargain', 'order', 'contract',
                    'track', 'settlement', 'profile'],
    ROLE_CARRIER: ['waybill', 'track', 'profile'],
    'PLAT_ADMIN': ['dashboard', 'admin_companies', 'base_data', 'doc_overview',
                   'alerts', 'dict', 'logs'],
}


def menus_for(roles):
    out = []
    for r in roles:
        for m in MENUS.get(r, []):
            if m not in out:
                out.append(m)
    return out


def build_ctx(conn):
    token = ''
    auth = request.headers.get('Authorization', '')
    if auth.startswith('Bearer '):
        token = auth[7:].strip()
    if not token:
        raise ApiError(40101, '未登录或登录已过期', http=401)
    payload = jwt_decode(token)
    user = q1(conn, "SELECT * FROM sys_user WHERE id=%s AND is_deleted=0", (payload['uid'],))
    if not user or user['status'] != 'ENABLED':
        raise ApiError(40101, '账号不可用或已禁用', http=401)
    company = None
    if user['company_id']:
        company = q1(conn, "SELECT * FROM ent_company WHERE id=%s AND is_deleted=0", (user['company_id'],))
        if not company:
            raise ApiError(40101, '所属企业不存在', http=401)
        if company['status'] != 'ENABLED':
            raise ApiError(40301, '企业已被停用')
    roles = [r for r in (user['roles'] or '').split(',') if r]
    return Ctx(user, company, roles, payload.get('ip') or '')


def auth_required(fn):
    """登录鉴权装饰器；ctx 存于 flask.g.ctx。"""

    from functools import wraps

    @wraps(fn)
    def wrapper(*args, **kwargs):
        ctx = build_ctx(g.conn)
        g.ctx = ctx
        return fn(*args, **kwargs)

    return wrapper


def roles_required(*roles):
    """角色鉴权装饰器：须持有指定角色之一（平台管理员不自动放行业务接口）。"""

    from functools import wraps

    def deco(fn):
        @wraps(fn)
        @auth_required
        def wrapper(*args, **kwargs):
            if not g.ctx.has_role(*roles):
                raise ApiError(40301, '无权限执行该操作')
            return fn(*args, **kwargs)
        return wrapper

    return deco


def plat_required(fn):
    from functools import wraps

    @wraps(fn)
    @auth_required
    def wrapper(*args, **kwargs):
        if not g.ctx.is_plat:
            raise ApiError(40301, '仅平台运营可执行该操作')
        return fn(*args, **kwargs)

    return wrapper


def issue_token(user, company, roles):
    payload = {
        'uid': user['id'],
        'cid': company['id'] if company else None,
        'roles': roles,
        'iat': int(time.time()),
        'exp': int(time.time()) + JWT_TTL_SECONDS,
        'jti': uuid.uuid4().hex,
    }
    return jwt_encode(payload)


def roles_from_company_types(company_types: str):
    """企业类型 → 首个注册用户的平台角色映射。"""
    mapping = {'STEEL': ROLE_STEEL, 'SUPPLIER': ROLE_SUPPLIER, 'LOGISTICS': ROLE_CARRIER}
    roles = []
    for t in (company_types or '').split(','):
        r = mapping.get(t.strip())
        if r and r not in roles:
            roles.append(r)
    return roles
