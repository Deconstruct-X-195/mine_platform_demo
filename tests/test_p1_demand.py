# -*- coding: utf-8 -*-
"""PRD-02 需求申报模块测试：申报CRUD/草稿流转/变更申请/归集生成集采清单/Excel导出/权限隔离"""
from conftest import api, login, register_company, make_user
import io
from openpyxl import load_workbook


def valid_body(**over):
    body = {
        'period_type': 'MONTH', 'period': '2026-01', 'ore_category': 'IRON', 'ore_type': 'PB_FINES',
        'quantity': 1000.5, 'grade_req': 'TFe>=62%', 'expected_arrival': '2026-03-01',
        'action': 'submit'
    }
    body.update(over)
    return body


def create_demand(client, token, **over):
    return api(client, 'POST', '/api/demand/create', token, json_body=valid_body(**over))


# ============ 功能测试 ============
def test_create_draft_and_submit_flow(client):
    """草稿 → 编辑 → 提交 完整流转"""
    r1, _ = make_user(client, '申报钢厂A')
    code, body = create_demand(client, r1, action='draft')
    assert code == 200
    did = body['data']['demand_id']
    _, lst = api(client, 'GET', '/api/demand/list', r1)
    assert lst['data']['list'][0]['status'] == 'DRAFT'
    # 编辑草稿
    code, _ = api(client, 'PUT', f'/api/demand/{did}', r1, json_body=valid_body(quantity=2000, action='draft'))
    assert code == 200
    _, det = api(client, 'GET', f'/api/demand/{did}', r1)
    assert det['data']['quantity'] == 2000.0
    # 提交
    code, _ = api(client, 'POST', f'/api/demand/{did}/submit', r1)
    assert code == 200
    _, lst = api(client, 'GET', '/api/demand/list', r1)
    assert lst['data']['list'][0]['status'] == 'SUBMITTED'
    # 提交后不可编辑/删除
    code, body = api(client, 'PUT', f'/api/demand/{did}', r1, json_body=valid_body())
    assert code == 400 and '变更申请' in body['message']
    code, _ = api(client, 'POST', f'/api/demand/{did}/delete', r1)
    assert code == 400


def test_direct_submit(client):
    r1, _ = make_user(client, '直接提交厂')
    code, body = create_demand(client, r1)
    assert code == 200
    _, lst = api(client, 'GET', '/api/demand/list', r1)
    assert lst['data']['list'][0]['status'] == 'SUBMITTED'


def test_change_qty_approved(client):
    """变更申请 → 平台同意 → 数量更新 + 历史记录"""
    r1, _ = make_user(client, '变更钢厂')
    _, body = create_demand(client, r1)
    did = body['data']['demand_id']
    code, _ = api(client, 'POST', f'/api/demand/{did}/change', r1, json_body={
        'change_type': 'QTY', 'change_desc': '产能调整', 'new_quantity': 1500})
    assert code == 200
    admin = login(client, 'admin', 'admin123')
    _, lst = api(client, 'GET', '/api/admin/demand/change/list?status=PENDING', admin)
    ch = next(x for x in lst['data']['list'] if x['demand_id'] == did)
    code, _ = api(client, 'POST', f"/api/admin/demand/change/{ch['id']}/review", admin,
                  json_body={'result': 'AGREED', 'review_remark': '同意'})
    assert code == 200
    _, det = api(client, 'GET', f'/api/demand/{did}', r1)
    assert det['data']['quantity'] == 1500.0
    assert det['data']['changes'][0]['status'] == 'AGREED'
    # 已处理的变更不能重复审核
    code, body = api(client, 'POST', f"/api/admin/demand/change/{ch['id']}/review", admin,
                     json_body={'result': 'REJECTED'})
    assert code == 400


def test_change_cancel_approved(client):
    r1, _ = make_user(client, '取消钢厂')
    _, body = create_demand(client, r1)
    did = body['data']['demand_id']
    api(client, 'POST', f'/api/demand/{did}/change', r1,
        json_body={'change_type': 'CANCEL', 'change_desc': '项目取消'})
    admin = login(client, 'admin', 'admin123')
    _, lst = api(client, 'GET', '/api/admin/demand/change/list?status=PENDING', admin)
    ch = next(x for x in lst['data']['list'] if x['demand_id'] == did)
    code, _ = api(client, 'POST', f"/api/admin/demand/change/{ch['id']}/review", admin,
                  json_body={'result': 'AGREED'})
    assert code == 200
    _, det = api(client, 'GET', f'/api/demand/{did}', r1)
    assert det['data']['status'] == 'CANCELLED'


def test_admin_sees_all_company_sees_own(client):
    """权限：企业只见自己申报；管理员见全量"""
    r1a, cida = make_user(client, '隔离厂A')
    r1b, cidb = make_user(client, '隔离厂B')
    create_demand(client, r1a)
    create_demand(client, r1b)
    _, la = api(client, 'GET', '/api/demand/list', r1a)
    assert la['data']['total'] == 1 and la['data']['list'][0]['company_name'] == '隔离厂A'
    admin = login(client, 'admin', 'admin123')
    _, lb = api(client, 'GET', '/api/admin/demand/list', admin)
    assert lb['data']['total'] == 2
    # R1 不能访问管理员归集列表
    code, _ = api(client, 'GET', '/api/admin/demand/list', r1a)
    assert code == 403
    # R1 不能看他人申报详情
    _, lb2 = api(client, 'GET', '/api/admin/demand/list', admin)
    other_id = next(x['demand_id'] for x in lb2['data']['list'] if x['company_id'] == cidb)
    code, _ = api(client, 'GET', f'/api/demand/{other_id}', r1a)
    assert code == 403


def test_collective_list_generation(client):
    """核心：生成集采清单（按周期+品类汇总、保留企业明细、状态流转）"""
    r1a, _ = make_user(client, '集采厂A')
    r1b, _ = make_user(client, '集采厂B')
    create_demand(client, r1a, quantity=1000)                       # 2026-01 IRON
    create_demand(client, r1a, quantity=300, period='2026-02')      # 2026-02 IRON
    create_demand(client, r1b, quantity=500.25, ore_category='CHROME', ore_type=None)  # 2026-01 CHROME
    create_demand(client, r1b, quantity=200, ore_category='CHROME', ore_type=None)     # 2026-01 CHROME 同品类合并
    admin = login(client, 'admin', 'admin123')
    code, body = api(client, 'POST', '/api/admin/collective/create', admin,
                     json_body={'period_type': 'MONTH', 'period': '2026-01'})
    assert code == 200
    lists = body['data']['lists']
    assert len(lists) == 2  # IRON + CHROME 各一份
    iron = next(x for x in lists if x['ore_category'] == 'IRON')
    chrome = next(x for x in lists if x['ore_category'] == 'CHROME')
    assert iron['total_qty'] == 1000.0 and iron['detail_count'] == 1
    assert chrome['total_qty'] == 700.25 and chrome['detail_count'] == 2
    # 需求状态 → IN_LIST
    _, la = api(client, 'GET', '/api/demand/list', r1a)
    assert la['data']['list'][0]['status'] == 'IN_LIST'
    # 其他周期不受影响
    _, lb = api(client, 'GET', '/api/demand/list', r1a)
    assert any(x['status'] == 'SUBMITTED' and x['period'] == '2026-02' for x in lb['data']['list'])
    # 清单详情保留企业明细
    _, det = api(client, 'GET', f"/api/admin/collective/{chrome['list_id']}", admin)
    comps = {x['company_name'] for x in det['data']['details']}
    assert comps == {'集采厂B'}
    # 二次生成（新周期需求）
    code, _ = api(client, 'POST', '/api/admin/collective/create', admin,
                  json_body={'period_type': 'MONTH', 'period': '2026-02'})
    assert code == 200
    # 已归集的需求不能重复归集
    code, body = api(client, 'POST', '/api/admin/collective/create', admin,
                     json_body={'period_type': 'MONTH', 'period': '2026-01'})
    assert code == 400


def test_export_excel(client):
    r1, _ = make_user(client, '导出厂')
    create_demand(client, r1, quantity=800)
    admin = login(client, 'admin', 'admin123')
    api(client, 'POST', '/api/admin/collective/create', admin,
        json_body={'period_type': 'MONTH', 'period': '2026-01'})
    resp = client.post('/api/admin/collective/export',
                       headers={'Authorization': 'Bearer ' + admin}, json={})
    assert resp.status_code == 200
    assert 'spreadsheetml' in resp.content_type
    wb = load_workbook(io.BytesIO(resp.data))
    assert '汇总' in wb.sheetnames and '企业明细' in wb.sheetnames
    assert wb['汇总'].max_row >= 2 and wb['企业明细'].max_row >= 2


# ============ 边界测试 ============
def test_validation_boundaries(client):
    r1, _ = make_user(client, '边界厂')
    cases = [
        ({'quantity': 0}, '数量'), ({'quantity': -5}, '数量'),
        ({'period': '2026-1'}, '周期'), ({'period': '2026-Q5'}, '周期'),
        ({'period_type': 'WEEK'}, '周期类型'), ({'ore_category': ''}, '品类'),
        ({'grade_req': ''}, '品位'), ({'expected_arrival': ''}, '期望到货'),
        ({'remark': 'x' * 501}, '备注'),
    ]
    for over, kw in cases:
        code, body = create_demand(client, r1, **over)
        assert code == 400, f'应拒绝: {kw}'
    # 数量保留2位小数
    code, body = create_demand(client, r1, quantity=123.456789)
    _, lst = api(client, 'GET', '/api/demand/list', r1)
    assert lst['data']['list'][0]['quantity'] == 123.46


def test_r2_r3_blocked(client):
    """上游/履约方不能访问需求申报功能"""
    r2, _ = make_user(client, '越权供方', 'SUPPLIER')
    code, _ = api(client, 'POST', '/api/demand/create', r2, json_body=valid_body())
    assert code == 403
    r3, _ = make_user(client, '越权物流', 'PARTNER', extra={'partner_type': 'LAND'})
    code, _ = api(client, 'GET', '/api/demand/list', r3)
    assert code == 403


def test_unapproved_company_blocked(client):
    """资质未审核通过的企业不能使用申报功能（PRD-01 硬约束）"""
    username, password, cid = register_company(client, '未审核申报厂')
    token = login(client, username, password)
    code, body = create_demand(client, token)
    assert code == 403 and '资质' in body['message']


def test_change_validation(client):
    r1, _ = make_user(client, '变更校验厂')
    _, body = create_demand(client, r1)
    did = body['data']['demand_id']
    # 无效类型
    code, _ = api(client, 'POST', f'/api/demand/{did}/change', r1,
                  json_body={'change_type': 'XXX', 'change_desc': 'a'})
    assert code == 400
    # 缺说明
    code, _ = api(client, 'POST', f'/api/demand/{did}/change', r1,
                  json_body={'change_type': 'QTY', 'change_desc': ''})
    assert code == 400
    # QTY 缺新数量
    code, _ = api(client, 'POST', f'/api/demand/{did}/change', r1,
                  json_body={'change_type': 'QTY', 'change_desc': 'a'})
    assert code == 400
    # 草稿不可变更
    _, body2 = create_demand(client, r1, action='draft')
    code, _ = api(client, 'POST', f"/api/demand/{body2['data']['demand_id']}/change", r1,
                  json_body={'change_type': 'CANCEL', 'change_desc': 'x'})
    assert code == 400


def test_cross_company_write_blocked(client):
    """企业A不能操作企业B的申报"""
    r1a, _ = make_user(client, '越权厂A')
    r1b, _ = make_user(client, '越权厂B')
    _, body = create_demand(client, r1b, action='draft')
    did = body['data']['demand_id']
    code, _ = api(client, 'PUT', f'/api/demand/{did}', r1a, json_body=valid_body())
    assert code == 404
    code, _ = api(client, 'POST', f'/api/demand/{did}/submit', r1a)
    assert code == 404
    code, _ = api(client, 'POST', f'/api/demand/{did}/delete', r1a)
    assert code == 404


def test_operation_log_written(client):
    """关键操作留痕"""
    r1, _ = make_user(client, '日志厂')
    create_demand(client, r1)
    admin = login(client, 'admin', 'admin123')
    _, body = api(client, 'GET', '/api/admin/log/list?action=采购需求', admin)
    assert body['data']['total'] >= 1
