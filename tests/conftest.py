# -*- coding: utf-8 -*-
"""pytest 公共夹具"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest


@pytest.fixture()
def app(tmp_path, monkeypatch):
    """每个测试使用独立临时数据库"""
    monkeypatch.setattr('backend.db.DB_PATH', str(tmp_path / 'test.db'))
    monkeypatch.setattr('backend.db.UPLOAD_DIR', str(tmp_path / 'uploads'))
    os.makedirs(str(tmp_path / 'uploads'), exist_ok=True)
    from backend import create_app
    application = create_app()
    application.config['TESTING'] = True
    yield application


@pytest.fixture()
def client(app):
    return app.test_client()


# ---------------- 通用辅助 ----------------
def api(client, method, path, token=None, json_body=None, **kw):
    headers = kw.pop('headers', {})
    if token:
        headers['Authorization'] = f'Bearer {token}'
    resp = client.open(path, method=method, headers=headers, json=json_body, **kw)
    if resp.content_type and resp.content_type.startswith('application/json'):
        return resp.status_code, resp.get_json()
    return resp.status_code, resp.data


def login(client, username, password):
    code, body = api(client, 'POST', '/api/auth/login',
                     json_body={'username': username, 'password': password})
    assert code == 200, body
    return body['data']['token']


def register_company(client, name, ctype='DOWNSTREAM', username=None, password='pass123456',
                     extra=None):
    """注册企业并返回 (username, password, company_id)"""
    username = username or f'user_{name}'
    body = {
        'company_type': ctype, 'company_name': name, 'credit_code': f'CODE{name}',
        'username': username, 'password': password,
        'contact': '张三', 'phone': '13800000000',
        'qualifications': [{'cert_type': 'BUSINESS_LICENSE', 'file_url': '/api/files/x.pdf',
                            'file_name': '执照.pdf'}],
    }
    if extra:
        body.update(extra)
    code, resp = api(client, 'POST', '/api/auth/register', json_body=body)
    assert code == 200, resp
    return username, password, resp['data']['company_id']


def make_user(client, name, ctype='DOWNSTREAM', extra=None):
    """注册 + 管理员审核通过 → 可用业务账号 token"""
    username, password, cid = register_company(client, name, ctype, extra=extra)
    admin = login(client, 'admin', 'admin123')
    code, _ = api(client, 'POST', f'/api/admin/company/{cid}/audit', admin,
                  json_body={'result': 'APPROVED'})
    assert code == 200
    token = login(client, username, password)
    return token, cid
