# -*- coding: utf-8 -*-
"""PRD-03 货源资源模块测试：货源CRUD/上下架流转/平台台账/强制下架/优选/权限"""
from conftest import api, login, register_company, make_user


def valid_res(**over):
    body = {
        'ore_category': 'IRON', 'origin': '澳大利亚皮尔巴拉', 'grade': 'TFe 62.5%',
        'granularity': '6.3-40mm', 'moisture': '6.5', 'impurity': 'P 0.08%',
        'max_qty': 50000, 'supply_period': '2026-01 ~ 2026-06', 'action': 'submit'
    }
    body.update(over)
    return body


def create_res(client, token, **over):
    return api(client, 'POST', '/api/resource/create', token, json_body=valid_res(**over))


# ============ 功能测试 ============
def test_create_draft_submit_flow(client):
    """草稿 → 编辑 → 提交上架"""
    r2, _ = make_user(client, '矿山集团A', 'SUPPLIER', extra={'supplier_type': 'OVERSEAS'})
    code, body = create_res(client, r2, action='draft')
    assert code == 200
    rid = body['data']['resource_id']
    _, lst = api(client, 'GET', '/api/resource/list', r2)
    assert lst['data']['list'][0]['status'] == 'DRAFT'
    # 编辑
    code, _ = api(client, 'PUT', f'/api/resource/{rid}', r2, json_body=valid_res(max_qty=80000, action='draft'))
    assert code == 200
    _, det = api(client, 'GET', f'/api/resource/{rid}', r2)
    assert det['data']['max_qty'] == 80000.0
    # 提交上架
    code, _ = api(client, 'POST', f'/api/resource/{rid}/submit', r2)
    assert code == 200
    _, lst = api(client, 'GET', '/api/resource/list', r2)
    assert lst['data']['list'][0]['status'] == 'ON_SHELF'
    # 上架后不可直接编辑
    code, body = api(client, 'PUT', f'/api/resource/{rid}', r2, json_body=valid_res())
    assert code == 400 and '下架' in body['message']


def test_off_on_cycle(client):
    """上架 → 主动下架 → 重新上架"""
    r2, _ = make_user(client, '矿山集团B', 'SUPPLIER')
    _, body = create_res(client, r2)
    rid = body['data']['resource_id']
    code, _ = api(client, 'POST', f'/api/resource/{rid}/off', r2)
    assert code == 200
    code, body = api(client, 'POST', f'/api/resource/{rid}/off', r2)
    assert code == 400  # 重复下架
    code, _ = api(client, 'POST', f'/api/resource/{rid}/on', r2)
    assert code == 200
    _, lst = api(client, 'GET', '/api/resource/list', r2)
    assert lst['data']['list'][0]['status'] == 'ON_SHELF'


def test_admin_ledger_and_filters(client):
    r2a, _ = make_user(client, '矿山C', 'SUPPLIER')
    r2b, _ = make_user(client, '矿山D', 'SUPPLIER')
    create_res(client, r2a, ore_category='IRON')
    create_res(client, r2b, ore_category='CHROME')
    admin = login(client, 'admin', 'admin123')
    _, all_ = api(client, 'GET', '/api/admin/resource/list', admin)
    assert all_['data']['total'] == 2
    _, iron = api(client, 'GET', '/api/admin/resource/list?ore_category=IRON', admin)
    assert iron['data']['total'] == 1 and iron['data']['list'][0]['company_name'] == '矿山C'
    # 台账导出
    resp = client.post('/api/admin/resource/export', headers={'Authorization': 'Bearer ' + admin}, json={})
    assert resp.status_code == 200 and 'spreadsheetml' in resp.content_type


def test_force_off_and_reason(client):
    """强制下架：必须填原因，仅上架状态可执行，供方可见并可重新上架"""
    r2, _ = make_user(client, '矿山E', 'SUPPLIER')
    _, body = create_res(client, r2)
    rid = body['data']['resource_id']
    admin = login(client, 'admin', 'admin123')
    # 无原因拒绝
    code, body = api(client, 'POST', f'/api/admin/resource/{rid}/force_off', admin, json_body={})
    assert code == 400
    code, _ = api(client, 'POST', f'/api/admin/resource/{rid}/force_off', admin,
                  json_body={'reason': '质检报告造假'})
    assert code == 200
    _, lst = api(client, 'GET', '/api/resource/list', r2)
    assert lst['data']['list'][0]['status'] == 'FORCE_OFF'
    # 强制下架状态也不可再强制
    code, _ = api(client, 'POST', f'/api/admin/resource/{rid}/force_off', admin,
                  json_body={'reason': 'x'})
    assert code == 400
    # 供方整改后可重新上架
    code, _ = api(client, 'POST', f'/api/resource/{rid}/on', r2)
    assert code == 200


def test_prefer_marking(client):
    r2, _ = make_user(client, '矿山F', 'SUPPLIER')
    _, body = create_res(client, r2, action='draft')
    rid = body['data']['resource_id']
    admin = login(client, 'admin', 'admin123')
    # 草稿不能优选
    code, body = api(client, 'POST', f'/api/admin/resource/{rid}/prefer', admin,
                     json_body={'is_preferred': True})
    assert code == 400
    api(client, 'POST', f'/api/resource/{rid}/submit', r2)
    code, _ = api(client, 'POST', f'/api/admin/resource/{rid}/prefer', admin,
                  json_body={'is_preferred': True})
    assert code == 200
    _, lst = api(client, 'GET', '/api/admin/resource/list?ore_category=IRON', admin)
    assert lst['data']['list'][0]['is_preferred'] == 1
    # 取消优选
    code, _ = api(client, 'POST', f'/api/admin/resource/{rid}/prefer', admin,
                  json_body={'is_preferred': False})
    assert code == 200


# ============ 边界/权限测试 ============
def test_validation_boundaries(client):
    r2, _ = make_user(client, '矿山G', 'SUPPLIER')
    cases = [
        ({'max_qty': 0}, '最大吨数'), ({'max_qty': -1}, '最大吨数'),
        ({'ore_category': ''}, '品类'), ({'origin': ''}, '产地'),
        ({'grade': ''}, '品位'), ({'supply_period': ''}, '供应周期'),
        ({'remark': 'x' * 501}, '备注'),
    ]
    for over, kw in cases:
        code, body = create_res(client, r2, **over)
        assert code == 400, f'应拒绝: {kw}'


def test_role_isolation(client):
    """R1/R3/R4 不能维护货源；R2 不能访问台账"""
    r1, _ = make_user(client, '货源越权厂', 'DOWNSTREAM')
    code, _ = api(client, 'POST', '/api/resource/create', r1, json_body=valid_res())
    assert code == 403
    r3, _ = make_user(client, '货源越权物流', 'PARTNER', extra={'partner_type': 'PORT'})
    code, _ = api(client, 'GET', '/api/resource/list', r3)
    assert code == 403
    r2, _ = make_user(client, '矿山H', 'SUPPLIER')
    code, _ = api(client, 'GET', '/api/admin/resource/list', r2)
    assert code == 403
    create_res(client, r2)
    # R1 不能看货源详情
    _, lst = api(client, 'GET', '/api/resource/list', r2)
    code, _ = api(client, 'GET', f"/api/resource/{lst['data']['list'][0]['resource_id']}", r1)
    assert code == 403


def test_cross_supplier_write_blocked(client):
    r2a, _ = make_user(client, '矿山I', 'SUPPLIER')
    r2b, _ = make_user(client, '矿山J', 'SUPPLIER')
    _, body = create_res(client, r2b, action='draft')
    rid = body['data']['resource_id']
    code, _ = api(client, 'PUT', f'/api/resource/{rid}', r2a, json_body=valid_res())
    assert code == 404
    code, _ = api(client, 'POST', f'/api/resource/{rid}/submit', r2a)
    assert code == 404
    code, _ = api(client, 'POST', f'/api/resource/{rid}/off', r2a)
    assert code == 404


def test_unapproved_supplier_blocked(client):
    username, password, cid = register_company(client, '未审核矿山', 'SUPPLIER')
    token = login(client, username, password)
    code, body = create_res(client, token)
    assert code == 403 and '资质' in body['message']


def test_resource_log_written(client):
    r2, _ = make_user(client, '矿山K', 'SUPPLIER')
    create_res(client, r2)
    admin = login(client, 'admin', 'admin123')
    _, body = api(client, 'GET', '/api/admin/log/list?action=货源', admin)
    assert body['data']['total'] >= 1
