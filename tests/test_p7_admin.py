# -*- coding: utf-8 -*-
"""PRD-08 后台管理与权限模块测试：指标模板维护 / 全局看板 / 全量单据检索与穿透 / 日志导出 / 子账号 / RBAC硬隔离"""
from conftest import api, login, make_user
from test_p3_trading import setup_env, create_task, quote, get_inquiries, DEADLINE
from openpyxl import load_workbook
import io


# ============ 指标模板 (§2.3) ============
def test_indicator_template_crud(client):
    admin = login(client, 'admin', 'admin123')
    # 新增
    code, body = api(client, 'POST', '/api/admin/indicator/template', admin, json_body={
        'ore_category': 'IRON', 'field_name': 'fe', 'field_label': '铁品位(%)', 'field_type': 'number', 'required': 1})
    assert code == 200, body
    code, body = api(client, 'POST', '/api/admin/indicator/template', admin, json_body={
        'ore_category': 'IRON', 'field_name': 'moisture', 'field_label': '水分(%)', 'field_type': 'number'})
    assert code == 200, body
    # 列表
    _, body = api(client, 'GET', '/api/admin/indicator/template', admin)
    rows = [r for r in body['data']['list'] if r['ore_category'] == 'IRON' and r['field_name'] == 'fe']
    assert rows and rows[0]['field_label'] == '铁品位(%)' and rows[0]['required'] == 1
    tid = rows[0]['id']
    # 业务表单按品类带出（全员可访问）
    r1, _ = make_user(client, '模板校验钢厂')
    code, body = api(client, 'GET', '/api/indicator/template/IRON', r1)
    assert code == 200 and {r['field_name'] for r in body['data']} >= {'fe', 'moisture'}
    # 更新
    code, _ = api(client, 'POST', '/api/admin/indicator/template', admin, json_body={
        'id': tid, 'ore_category': 'IRON', 'field_name': 'fe', 'field_label': 'TFe(%)', 'field_type': 'number', 'required': 1})
    assert code == 200
    _, body = api(client, 'GET', '/api/indicator/template/IRON', r1)
    assert next(r for r in body['data'] if r['field_name'] == 'fe')['field_label'] == 'TFe(%)'
    # 校验：品类缺失 / 字段类型无效 / 删除
    code, body = api(client, 'POST', '/api/admin/indicator/template', admin, json_body={'field_name': 'x', 'field_label': 'y'})
    assert code == 400 and '品类' in body['message']
    code, _ = api(client, 'POST', '/api/admin/indicator/template', admin, json_body={
        'ore_category': 'IRON', 'field_name': 'x', 'field_label': 'y', 'field_type': 'bool'})
    assert code == 400
    code, _ = api(client, 'POST', f'/api/admin/indicator/template/{tid}/delete', admin)
    assert code == 200
    _, body = api(client, 'GET', '/api/indicator/template/IRON', r1)
    assert 'fe' not in {r['field_name'] for r in body['data']}
    # 不存在的ID删除 → 404
    code, _ = api(client, 'POST', '/api/admin/indicator/template/99999/delete', admin)
    assert code == 404


# ============ 全局数据统计看板 (§2.4) ============
def test_dashboard_summary(client):
    env = setup_env(client)
    _, body = create_task(client, env)
    tid = body['data']['task']['task_id']
    ia = get_inquiries(client, env['ra'])
    quote(client, env['ra'], ia[0]['inquiry_id'], 650, 1200)
    code, body = api(client, 'POST', f'/api/admin/task/{tid}/lock', env['admin'], json_body={
        'locks': [{'inquiry_id': ia[0]['inquiry_id'], 'unit_price': 650, 'qty': 1000}]})
    assert code == 200, body
    code, body = api(client, 'GET', '/api/admin/dashboard/summary', env['admin'])
    assert code == 200, body
    d = body['data']
    assert d['companies']['DOWNSTREAM'] >= 1 and d['companies']['SUPPLIER'] >= 2
    assert d['execution']['list_count'] >= 1 and d['execution']['task_count'] >= 1 and d['execution']['order_count'] >= 1
    assert d['locked']['total_qty'] == 1000 and d['locked']['total_amount'] == 650000
    dp = next(x for x in d['demand_by_period'] if x['period'] == '2026-01')
    assert dp['total_qty'] == 1000 and dp['demand_count'] == 1
    assert d['order_trend'] and d['order_trend'][-1]['total_qty'] == 1000
    assert next(x for x in d['demand_pie'] if x['ore_category'] == 'IRON')['total_qty'] == 1000
    # 时间筛选：仅统计今天以后 → 锁货归零
    code, body = api(client, 'GET', '/api/admin/dashboard/summary?start_date=2099-01-01', env['admin'])
    d2 = body['data']
    assert d2['locked']['total_qty'] == 0 and d2['order_trend'] == []


# ============ 全量单据检索与穿透 (§2.5) ============
def test_ledger_search_and_doc(client):
    env = setup_env(client)
    _, body = create_task(client, env)
    tid = body['data']['task']['task_id']
    ia = get_inquiries(client, env['ra'])
    quote(client, env['ra'], ia[0]['inquiry_id'], 650, 1200)
    _, lb = api(client, 'POST', f'/api/admin/task/{tid}/lock', env['admin'], json_body={
        'locks': [{'inquiry_id': ia[0]['inquiry_id'], 'unit_price': 650, 'qty': 1000}]})
    order_no = lb['data']['orders'][0]['order_no']
    order_id = lb['data']['orders'][0]['order_id']
    # 全类型检索
    code, body = api(client, 'GET', '/api/admin/ledger/search', env['admin'])
    assert code == 200, body
    groups = {g['doc_type']: g for g in body['data']['groups']}
    assert set(groups) == {'demand', 'list', 'task', 'order', 'alloc', 'logistics', 'bill'}
    assert groups['demand']['total'] >= 1 and groups['task']['total'] >= 1 and groups['order']['total'] >= 1
    assert groups['logistics']['total'] == 0  # 未建物流
    # 关键字过滤：按订单号
    code, body = api(client, 'GET', f'/api/admin/ledger/search?doc_type=order&keyword={order_no}', env['admin'])
    g = body['data']['groups'][0]
    assert g['total'] == 1 and g['list'][0]['doc_no'] == order_no
    # 无效类型
    code, _ = api(client, 'GET', '/api/admin/ledger/search?doc_type=hack', env['admin'])
    assert code == 400
    # 穿透详情 + 操作轨迹（订单：有新增账号/锁货等日志）
    code, body = api(client, 'GET', f'/api/admin/ledger/doc?doc_type=order&id={order_id}', env['admin'])
    assert code == 200, body
    assert body['data']['doc']['order_no'] == order_no
    assert len(body['data']['logs']) >= 1
    # 穿透需求单
    _, dl = api(client, 'GET', '/api/admin/demand/list', env['admin'])
    did = dl['data']['list'][0]['demand_id']
    code, body = api(client, 'GET', f'/api/admin/ledger/doc?doc_type=demand&id={did}', env['admin'])
    assert code == 200 and body['data']['doc']['demand_id'] == did
    # 单据不存在
    code, _ = api(client, 'GET', '/api/admin/ledger/doc?doc_type=order&id=99999', env['admin'])
    assert code == 404


# ============ 操作日志检索与导出 (§2.6) ============
def test_log_list_and_export(client):
    env = setup_env(client)
    _, body = create_task(client, env)
    admin = env['admin']
    # 检索：按操作类型过滤
    code, body = api(client, 'GET', '/api/admin/log/list?action=%E8%AF%A2%E4%BB%B7', admin)
    assert code == 200 and body['data']['total'] >= 1
    assert all('询价' in r['action'] for r in body['data']['list'])
    # 日志字段完整（操作人/角色/前后状态/关联）
    row = body['data']['list'][0]
    for f in ('operator_name', 'role_code', 'action', 'create_time'):
        assert row[f], row
    # 导出 Excel
    code, body = api(client, 'GET', '/api/admin/log/export?action=%E8%AF%A2%E4%BB%B7', admin)
    assert code == 200, body
    wb = load_workbook(io.BytesIO(body))
    ws = wb.active
    assert ws.max_row >= 2
    assert '操作' in [c.value for c in ws[1]]
    # 角色筛选
    code, body = api(client, 'GET', '/api/admin/log/list?role_code=R4', admin)
    assert code == 200 and all(r['role_code'] == 'R4' for r in body['data']['list'])


# ============ 子账号管理 (§2.2) ============
def test_account_lifecycle(client):
    admin = login(client, 'admin', 'admin123')
    r1, c1 = make_user(client, '子账号测试钢厂')
    # 创建平台 R4 子账号
    code, _ = api(client, 'POST', '/api/admin/account/create', admin, json_body={
        'username': 'admin_sub', 'password': '123456', 'role_code': 'R4', 'real_name': '审核员小王'})
    assert code == 200
    sub = login(client, 'admin_sub', '123456')
    code, _ = api(client, 'GET', '/api/admin/account/list', sub)
    assert code == 200  # 子账号同样具备后台权限
    # 企业子账号：角色与企业类型不匹配 → 400
    code, body = api(client, 'POST', '/api/admin/account/create', admin, json_body={
        'username': 'bad_role', 'password': '123456', 'role_code': 'R2', 'company_id': c1})
    assert code == 400 and '不匹配' in body['message']
    # 缺企业绑定 → 400
    code, _ = api(client, 'POST', '/api/admin/account/create', admin, json_body={
        'username': 'no_company', 'password': '123456', 'role_code': 'R1'})
    assert code == 400
    # 正确创建企业子账号（同一企业第二个操作员）
    code, _ = api(client, 'POST', '/api/admin/account/create', admin, json_body={
        'username': 'steel_sub', 'password': '123456', 'role_code': 'R1', 'company_id': c1, 'real_name': '采购小张'})
    assert code == 200
    sub1 = login(client, 'steel_sub', '123456')
    code, body = api(client, 'GET', '/api/demand/list', sub1)
    assert code == 200  # 同企业数据可见
    # 用户名重复
    code, _ = api(client, 'POST', '/api/admin/account/create', admin, json_body={
        'username': 'steel_sub', 'password': '123456', 'role_code': 'R1', 'company_id': c1})
    assert code == 400
    # 启停：停用后登录被拒
    _, body = api(client, 'GET', '/api/admin/account/list?keyword=steel_sub', admin)
    uid = body['data']['list'][0]['user_id']
    code, _ = api(client, 'PUT', f'/api/admin/account/{uid}', admin, json_body={'status': 'DISABLED'})
    assert code == 200
    code, body = api(client, 'POST', '/api/auth/login', None, json_body={'username': 'steel_sub', 'password': '123456'})
    assert code != 200 and '停用' in body['message']
    # 重新启用
    code, _ = api(client, 'PUT', f'/api/admin/account/{uid}', admin, json_body={'status': 'ACTIVE'})
    assert code == 200 and login(client, 'steel_sub', '123456')
    # 重置密码
    code, _ = api(client, 'PUT', f'/api/admin/account/{uid}', admin, json_body={'password': 'abc12345'})
    assert code == 200 and login(client, 'steel_sub', 'abc12345')
    # 不能停用自己
    _, body = api(client, 'GET', '/api/admin/account/list?keyword=admin', admin)
    my_id = body['data']['list'][0]['user_id']
    code, body = api(client, 'PUT', f'/api/admin/account/{my_id}', admin, json_body={'status': 'DISABLED'})
    assert code == 400 and '自己' in body['message']
    # 密码过短
    code, _ = api(client, 'POST', '/api/admin/account/create', admin, json_body={
        'username': 'shortpwd', 'password': '123', 'role_code': 'R4'})
    assert code == 400


# ============ RBAC 权限硬隔离 (§2.2.3) ============
def test_admin_endpoints_rbac(client):
    r1, _ = make_user(client, '隔离测试钢厂')
    admin = login(client, 'admin', 'admin123')
    admin_endpoints = [
        ('GET', '/api/admin/account/list'), ('POST', '/api/admin/account/create'),
        ('GET', '/api/admin/dashboard/summary'), ('GET', '/api/admin/ledger/search'),
        ('GET', '/api/admin/log/list'), ('GET', '/api/admin/log/export'),
        ('POST', '/api/admin/indicator/template'), ('GET', '/api/admin/company/list'),
        ('GET', '/api/admin/dict/list'),
    ]
    for method, path in admin_endpoints:
        code, body = api(client, method, path, r1)
        assert code == 403, f'{path} 应拒绝R1，实际 {code} {body.get("message")}'
    # 未登录 401
    code, _ = api(client, 'GET', '/api/admin/dashboard/summary', None)
    assert code == 401
