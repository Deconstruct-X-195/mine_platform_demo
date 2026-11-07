# -*- coding: utf-8 -*-
"""E2E 全链路测试公共封装（PRD 10.2）：HTTP 客户端、断言助手、账号发现。"""
import os

import requests

# 目标服务地址，可用 MINE_BASE 覆盖（如对全新数据库验证时指向其他端口）
BASE = os.environ.get('MINE_BASE', 'http://127.0.0.1:8000') + '/api/v1'
PASS = 'demo123456'

# 管理员账号（seed 与清理后基线均保留）
ADMIN = ('13800000000', 'admin123456')

# E2E 直连库：与被测服务一致，多环境验证时用 MINE_PG_DSN 覆盖
PG_DSN = os.environ.get(
    'MINE_PG_DSN', 'postgresql://postgres:Langchain2026@127.0.0.1:5432/mine_platform')


def pg_one(sql, args=()):
    """只读直连查询：用于断言库内持久化状态（如企业类型归一结果）。"""
    import psycopg
    with psycopg.connect(PG_DSN) as conn:
        return conn.execute(sql, args).fetchone()


def discover_accounts():
    """自适应发现基线企业账号（兼容"清理后基线"与"seed 演示数据"两种环境）。

    返回 {'steel': [...], 'suppliers': [...], 'carrier': [...]}（username 列表）。
    """
    import psycopg
    with psycopg.connect(PG_DSN) as conn:
        rows = conn.execute("""
            SELECT u.username, c.company_types
            FROM sys_user u
            JOIN ent_company c ON c.id = u.company_id
            WHERE u.status = 'ENABLED' AND u.is_deleted = 0
              AND c.audit_status = 'APPROVED' AND c.is_deleted = 0
            ORDER BY u.id
            """).fetchall()
    steel, suppliers, carrier = [], [], []
    for username, types in rows:
        t = (types or '').upper()
        if 'STEEL' in t:
            steel.append(username)
        if 'SUPPLIER' in t:
            suppliers.append(username)
        if 'LOGISTICS' in t:
            carrier.append(username)
    return {'steel': steel, 'suppliers': suppliers, 'carrier': carrier}

_passed = 0
_failed = []


def check(name, cond, detail=''):
    global _passed
    if cond:
        _passed += 1
        print('  PASS %s' % name)
    else:
        _failed.append(name)
        print('  FAIL %s  %s' % (name, detail))


def summary():
    print('\n==== E2E 结果：PASS %d / FAIL %d ====' % (_passed, len(_failed)))
    for f in _failed:
        print('  FAILED: %s' % f)
    return not _failed


class Client:
    """带 token 的 API 客户端：resp 断言 code==0 并返回 data。"""

    def __init__(self, token=None):
        self.s = requests.Session()
        if token:
            self.s.headers['Authorization'] = 'Bearer ' + token

    @classmethod
    def login(cls, username, password):
        c = cls()
        d = c.post('/auth/login', {'username': username, 'password': password})
        c.s.headers['Authorization'] = 'Bearer ' + d['token']
        c.user = d['user']
        return c

    def _req(self, method, path, **kw):
        r = self.s.request(method, BASE + path, timeout=15, **kw)
        try:
            body = r.json()
        except ValueError:
            body = {}
        return r, body

    def get(self, path, expect=0, **params):
        r, b = self._req('GET', path, params=params)
        assert r.status_code == 200 and b.get('code') == expect, \
            'GET %s -> %s %s' % (path, r.status_code, b)
        return b.get('data')

    def post(self, path, body=None, expect=0, **kw):
        r, b = self._req('POST', path, json=body or {}, **kw)
        assert r.status_code == 200 and b.get('code') == expect, \
            'POST %s -> %s %s' % (path, r.status_code, b)
        return b.get('data')

    def put(self, path, body=None, expect=0, **kw):
        r, b = self._req('PUT', path, json=body or {}, **kw)
        assert r.status_code == 200 and b.get('code') == expect, \
            'PUT %s -> %s %s' % (path, r.status_code, b)
        return b.get('data')

    def try_code(self, method, path, body=None):
        """期望业务失败：返回 (http, code, message)。"""
        r, b = self._req(method, path, json=body or {})
        return r.status_code, b.get('code'), b.get('message')


def dl_bytes(client, path):
    """带鉴权下载二进制（归档导出 zip 用）。"""
    r = client.s.get(BASE + path, timeout=30)
    assert r.status_code == 200, '下载 %s -> HTTP %s' % (path, r.status_code)
    return r.content
