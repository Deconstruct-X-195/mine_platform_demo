# -*- coding: utf-8 -*-
"""PRD-01 全局基座测试：认证 / RBAC / 资质审核前置 / 字典 / 操作日志"""
from conftest import api, login, register_company, make_user


# ============ 功能测试 ============
def test_admin_seed_login(client):
    """管理员种子账号可登录"""
    token = login(client, 'admin', 'admin123')
    code, body = api(client, 'GET', '/api/auth/me', token)
    assert code == 200 and body['data']['role_code'] == 'R4'


def test_register_and_audit_flow(client):
    """注册 → 待审核 → 审核通过 全流程"""
    username, password, cid = register_company(client, '测试钢厂')
    admin = login(client, 'admin', 'admin123')
    code, body = api(client, 'GET', '/api/admin/company/list?audit_status=PENDING', admin)
    assert code == 200
    item = next(x for x in body['data']['list'] if x['company_id'] == cid)
    assert item['audit_status'] == 'PENDING' and item['qualifications']
    code, _ = api(client, 'POST', f'/api/admin/company/{cid}/audit', admin,
                  json_body={'result': 'APPROVED'})
    assert code == 200
    _, body = api(client, 'GET', '/api/admin/company/list?audit_status=APPROVED', admin)
    item = next(x for x in body['data']['list'] if x['company_id'] == cid)
    assert item['audit_status'] == 'APPROVED'
    # 审核日志留痕
    _, body = api(client, 'GET', '/api/admin/log/list?action=企业资质审核', admin)
    assert body['data']['total'] >= 1


def test_reject_flow_with_reason(client):
    """驳回必须填写原因，用户可见驳回状态"""
    username, password, cid = register_company(client, '驳回钢厂')
    admin = login(client, 'admin', 'admin123')
    # 边界：驳回不带原因应被拒绝
    code, body = api(client, 'POST', f'/api/admin/company/{cid}/audit', admin,
                     json_body={'result': 'REJECTED'})
    assert code == 400
    code, _ = api(client, 'POST', f'/api/admin/company/{cid}/audit', admin,
                  json_body={'result': 'REJECTED', 'reject_reason': '执照模糊'})
    assert code == 200
    token = login(client, username, password)
    _, body = api(client, 'GET', '/api/auth/me', token)
    assert body['data']['company']['audit_status'] == 'REJECTED'
    assert body['data']['company']['audit_remark'] == '执照模糊'


def test_dict_query(client):
    """字典查询：矿石品类/周期/港口"""
    token = login(client, 'admin', 'admin123')
    for cat, expect in [('ORE_CATEGORY', '铁矿石'), ('PERIOD_TYPE', '月度'), ('PORT', '青岛港')]:
        _, body = api(client, 'GET', f'/api/dict/{cat}', token)
        assert any(d['item_name'] == expect for d in body['data']), cat


# ============ 权限/边界测试 ============
def test_login_wrong_password(client):
    code, body = api(client, 'POST', '/api/auth/login',
                     json_body={'username': 'admin', 'password': 'wrong'})
    assert code == 400


def test_unauthorized_access_blocked(client):
    code, _ = api(client, 'GET', '/api/auth/me')
    assert code == 401
    code, _ = api(client, 'GET', '/api/admin/company/list')
    assert code == 401


def test_rbac_role_isolation(client):
    """R1 不能访问管理员接口；R4 不能被企业业务接口误伤"""
    r1, _ = make_user(client, 'RBAC钢厂', 'DOWNSTREAM')
    code, body = api(client, 'GET', '/api/admin/company/list', r1)
    assert code == 403 and '无权' in body['message']
    admin = login(client, 'admin', 'admin123')
    code, body = api(client, 'GET', '/api/admin/account/list', admin)
    assert code == 200


def test_business_blocked_before_audit(client):
    """硬约束：资质审核通过前不能使用业务功能（这里以管理员接口+账号本身验证审核门禁逻辑，
    具体业务接口门禁在各模块测试中验证）"""
    username, password, cid = register_company(client, '未审核钢厂')
    token = login(client, username, password)
    _, body = api(client, 'GET', '/api/auth/me', token)
    assert body['data']['company']['audit_status'] == 'PENDING'
    admin = login(client, 'admin', 'admin123')
    # 边界：重复审核
    api(client, 'POST', f'/api/admin/company/{cid}/audit', admin, json_body={'result': 'APPROVED'})
    code, body = api(client, 'POST', f'/api/admin/company/{cid}/audit', admin,
                     json_body={'result': 'APPROVED'})
    assert code == 400 and '不可重复审核' in body['message']


def test_register_duplicate_boundary(client):
    """注册边界：企业名/用户名重复、密码过短、非法类型"""
    register_company(client, '重复企业')
    code, body = api(client, 'POST', '/api/auth/register', json_body={
        'company_type': 'DOWNSTREAM', 'company_name': '重复企业', 'username': 'u1',
        'password': 'pass123456', 'contact': 'a', 'phone': 'b'})
    assert code == 400 and '企业名称已存在' in body['message']
    code, body = api(client, 'POST', '/api/auth/register', json_body={
        'company_type': 'DOWNSTREAM', 'company_name': '另一企业', 'username': 'user_重复企业',
        'password': 'pass123456', 'contact': 'a', 'phone': 'b'})
    assert code == 400 and '用户名已存在' in body['message']
    code, body = api(client, 'POST', '/api/auth/register', json_body={
        'company_type': 'DOWNSTREAM', 'company_name': '短密码企业', 'username': 'u2',
        'password': '123', 'contact': 'a', 'phone': 'b'})
    assert code == 400
    code, body = api(client, 'POST', '/api/auth/register', json_body={
        'company_type': 'XXX', 'company_name': '非法类型企业', 'username': 'u3',
        'password': 'pass123456', 'contact': 'a', 'phone': 'b'})
    assert code == 400


def test_password_change(client):
    token, _ = make_user(client, '改密企业')
    code, _ = api(client, 'POST', '/api/auth/password', token,
                  json_body={'old_password': 'wrong', 'new_password': 'abc12345'})
    assert code == 400
    code, _ = api(client, 'POST', '/api/auth/password', token,
                  json_body={'old_password': 'pass123456', 'new_password': 'abc12345'})
    assert code == 200
    code, _ = api(client, 'POST', '/api/auth/login',
                  json_body={'username': 'user_改密企业', 'password': 'abc12345'})
    assert code == 200


def test_logout_invalidates_token(client):
    token = login(client, 'admin', 'admin123')
    code, _ = api(client, 'POST', '/api/auth/logout', token)
    assert code == 200
    code, _ = api(client, 'GET', '/api/auth/me', token)
    assert code == 401


def test_account_lifecycle(client):
    """子账号创建/停用边界（P8 功能在基座中已可用，回归验证）"""
    admin = login(client, 'admin', 'admin123')
    code, body = api(client, 'POST', '/api/admin/account/create', admin, json_body={
        'username': 'sub_admin', 'password': 'pass123456', 'role_code': 'R4', 'real_name': '子管理员'})
    assert code == 200
    code, body = api(client, 'POST', '/api/admin/account/create', admin, json_body={
        'username': 'sub_admin', 'password': 'pass123456', 'role_code': 'R4'})
    assert code == 400 and '已存在' in body['message']
    # 企业角色必须绑定企业
    code, body = api(client, 'POST', '/api/admin/account/create', admin, json_body={
        'username': 'r1_no_company', 'password': 'pass123456', 'role_code': 'R1'})
    assert code == 400
    token = login(client, 'sub_admin', 'pass123456')
    code, body = api(client, 'GET', '/api/admin/company/list', token)
    assert code == 200
