# -*- coding: utf-8 -*-
"""PRD-07 对账结算模块测试：分拨/到货确认/异常反馈/企业供方对账单/结清/归档/台账/权限隔离"""
from conftest import api, make_user
from test_p3_trading import setup_env, create_task, quote, get_inquiries
from test_p4_logistics import _mk as mk_partner, create_logi, advance


def setup_to_n5(client):
    """搭建到「货物入仓完成(N5)」的全链路：锁货订单 + 物流任务推进至 N5"""
    env = setup_env(client)
    _, body = create_task(client, env)
    tid = body['data']['task']['task_id']
    ia = get_inquiries(client, env['ra'])
    quote(client, env['ra'], ia[0]['inquiry_id'], 650, 1500)
    _, body = api(client, 'POST', f'/api/admin/task/{tid}/lock', env['admin'],
                  json_body={'locks': [{'inquiry_id': ia[0]['inquiry_id'], 'unit_price': 650, 'qty': 1000}]})
    env['order_id'] = body['data']['orders'][0]['order_id']
    env['order'] = body['data']['orders'][0]
    ptok, pcid = mk_partner(client, '结算物流')
    _, body = create_logi(client, env, [pcid])
    lid = body['data']['logi_id']
    for i in range(1, 6):
        code, _ = advance(client, ptok, lid, i)
        assert code == 200, (i, body)
    env['lid'] = lid
    env['ptok'] = ptok
    return env


def allocate(client, env, allocs=None, **over):
    body = {'order_id': env['order_id'],
            'allocs': allocs or [{'company_id': env['c1'], 'qty': 1000, 'unit_price': 655,
                                  'destination': '交易钢厂料场'}]}
    body.update(over)
    return api(client, 'POST', '/api/admin/allocation/create', env['admin'], json_body=body)


def get_alloc_id(client, env):
    _, body = api(client, 'GET', '/api/company/allocation/list', env['r1'])
    return body['data']['list'][0]['alloc_id']


# ============ 功能测试 ============
def test_allocation_create_and_states(client):
    """N5前不可分拨；N5后生成TRANSIT分拨单；N7送达转待确认"""
    env = setup_env(client)
    _, body = create_task(client, env)
    tid = body['data']['task']['task_id']
    ia = get_inquiries(client, env['ra'])
    quote(client, env['ra'], ia[0]['inquiry_id'], 650, 1500)
    _, body = api(client, 'POST', f'/api/admin/task/{tid}/lock', env['admin'],
                  json_body={'locks': [{'inquiry_id': ia[0]['inquiry_id'], 'unit_price': 650, 'qty': 1000}]})
    env['order_id'] = body['data']['orders'][0]['order_id']
    ptok, pcid = mk_partner(client, '分拨物流')
    _, body = create_logi(client, env, [pcid])
    lid = body['data']['logi_id']
    # 未入仓储不可分拨
    code, body = allocate(client, env)
    assert code == 400 and '入仓储' in body['message']
    for i in (1, 2, 3, 4):
        advance(client, ptok, lid, i)
    code, body = allocate(client, env)
    assert code == 400 and '入仓储' in body['message']
    advance(client, ptok, lid, 5)
    code, body = allocate(client, env)
    assert code == 200, body
    row = body['data']['list'][0]
    assert row['alloc_no'].startswith('AL')
    assert row['status'] == 'TRANSIT'
    assert row['amount'] == 1000 * 655
    # 重复分拨拦截
    code, body = allocate(client, env)
    assert code == 400 and '不可重复' in body['message']
    # N6 不改变状态；N7 完成送达 → WAIT_CONFIRM
    advance(client, ptok, lid, 6)
    _, body = api(client, 'GET', '/api/company/allocation/list', env['r1'])
    assert body['data']['list'][0]['status'] == 'TRANSIT'
    advance(client, ptok, lid, 7)
    _, body = api(client, 'GET', '/api/company/allocation/list', env['r1'])
    assert body['data']['list'][0]['status'] == 'WAIT_CONFIRM'


def test_confirm_and_feedback(client):
    """企业确认到货 → DONE；异常反馈与平台处理"""
    env = setup_to_n5(client)
    code, body = allocate(client, env)
    assert code == 200
    aid = get_alloc_id(client, env)
    # 异常反馈
    code, body = api(client, 'POST', f'/api/company/allocation/{aid}/feedback', env['r1'],
                     json_body={'description': '到货数量短缺约2吨，磅单已拍照'})
    assert code == 200
    fid = body['data']['feedback_id']
    # 平台处理
    code, body = api(client, 'POST', f'/api/admin/feedback/{fid}/resolve', env['admin'], json_body={})
    assert code == 400 and '说明' in body['message']
    code, body = api(client, 'POST', f'/api/admin/feedback/{fid}/resolve', env['admin'],
                     json_body={'resolve_remark': '已复核磅单，短缺在误差范围内，双方确认'})
    assert code == 200
    # 确认到货
    code, body = api(client, 'POST', f'/api/company/allocation/{aid}/confirm', env['r1'])
    assert code == 200
    assert body['data']['status'] == 'DONE'
    # 重复确认拦截
    code, body = api(client, 'POST', f'/api/company/allocation/{aid}/confirm', env['r1'])
    assert code == 400
    # 已处理反馈不可重复处理
    code, _ = api(client, 'POST', f'/api/admin/feedback/{fid}/resolve', env['admin'],
                  json_body={'resolve_remark': '再次处理'})
    assert code == 400
    # 企业列表可见反馈与状态
    _, body = api(client, 'GET', '/api/company/allocation/list', env['r1'])
    row = body['data']['list'][0]
    assert row['status'] == 'DONE'
    assert row['feedback']['status'] == 'RESOLVED'


def test_company_bill_flow(client):
    """企业对账单：生成(按企业聚合) → 确认 → 异议 → 结清 → 导出"""
    env = setup_to_n5(client)
    code, _ = allocate(client, env)
    assert code == 200
    aid = get_alloc_id(client, env)
    # 未生成分拨单的订单不能生成对账单
    code, body = api(client, 'POST', '/api/admin/bill/company/create', env['admin'], json_body={'order_id': 9999})
    assert code == 404
    # 生成
    code, body = api(client, 'POST', '/api/admin/bill/company/create', env['admin'], json_body={'order_id': env['order_id']})
    assert code == 200 and body['data']['created'] == 1
    _, body = api(client, 'GET', '/api/company/bill/list', env['r1'])
    assert len(body['data']['list']) == 1
    bill = body['data']['list'][0]
    assert bill['bill_no'].startswith('CB') and bill['status'] == 'PENDING'
    assert bill['total_amount'] == 1000 * 655
    assert len(bill['details']) == 1 and bill['details'][0]['alloc_no'].startswith('AL')
    # 重复生成 → 跳过
    code, body = api(client, 'POST', '/api/admin/bill/company/create', env['admin'], json_body={'order_id': env['order_id']})
    assert code == 200 and body['data']['created'] == 0
    # 企业确认
    code, body = api(client, 'POST', f"/api/company/bill/{bill['bill_id']}/confirm", env['r1'])
    assert code == 200 and body['data']['status'] == 'CONFIRMED'
    # 异议（可从已确认转回异议）
    code, body = api(client, 'POST', f"/api/company/bill/{bill['bill_id']}/dispute", env['r1'], json_body={})
    assert code == 400 and '原因' in body['message']
    code, body = api(client, 'POST', f"/api/company/bill/{bill['bill_id']}/dispute", env['r1'],
                     json_body={'reason': '单价与锁货单存在差异，请核对'})
    assert code == 200 and body['data']['status'] == 'DISPUTE'
    _, body = api(client, 'GET', '/api/company/bill/list', env['r1'])
    assert body['data']['list'][0]['dispute_reason'] == '单价与锁货单存在差异，请核对'
    # 平台结清
    code, body = api(client, 'POST', f"/api/admin/bill/company/{bill['bill_id']}/settle", env['admin'],
                     json_body={'remark': '已双方线下核对一致'})
    assert code == 200 and body['data']['status'] == 'SETTLED'
    # 结清后不可再操作
    code, _ = api(client, 'POST', f"/api/company/bill/{bill['bill_id']}/confirm", env['r1'])
    assert code == 400
    # 导出
    resp = client.get(f"/api/company/bill/{bill['bill_id']}/export",
                      headers={'Authorization': 'Bearer ' + env['r1']})
    assert resp.status_code == 200 and 'spreadsheetml' in resp.content_type


def test_supplier_bill_flow(client):
    """供方对账单：按订单生成 → 供方确认 → 异议 → 结清；防重复"""
    env = setup_to_n5(client)
    code, _ = allocate(client, env)
    assert code == 200
    code, body = api(client, 'POST', '/api/admin/bill/supplier/create', env['admin'], json_body={'order_id': env['order_id']})
    assert code == 200
    bid = body['data']['bill_id']
    # 防重复
    code, body = api(client, 'POST', '/api/admin/bill/supplier/create', env['admin'], json_body={'order_id': env['order_id']})
    assert code == 400 and '已生成' in body['message']
    # 供方查看
    _, body = api(client, 'GET', '/api/supplier/bill/list', env['ra'])
    assert len(body['data']['list']) == 1
    sb = body['data']['list'][0]
    assert sb['bill_no'].startswith('SB')
    assert sb['total_amount'] == env['order']['total_amount']
    assert sb['order_no'].startswith('CO')
    # 供方确认 → 异议 → 平台结清
    code, body = api(client, 'POST', f'/api/supplier/bill/{bid}/confirm', env['ra'])
    assert code == 200
    code, body = api(client, 'POST', f'/api/supplier/bill/{bid}/dispute', env['ra'],
                     json_body={'reason': '运费承担方式需再确认'})
    assert code == 200
    code, body = api(client, 'POST', f'/api/admin/bill/supplier/{bid}/settle', env['admin'], json_body={})
    assert code == 200 and body['data']['status'] == 'SETTLED'


def test_archive_full_loop(client):
    """归档：前置校验 → 归档联动订单/任务/需求状态 → 只读保护"""
    env = setup_to_n5(client)
    code, _ = allocate(client, env)
    assert code == 200
    aid = get_alloc_id(client, env)
    # 未确认到货不可归档
    code, body = api(client, 'POST', '/api/admin/archive', env['admin'], json_body={'order_id': env['order_id']})
    assert code == 400 and '未确认到货' in body['message']
    api(client, 'POST', f'/api/company/allocation/{aid}/confirm', env['r1'])
    # 未生成企业对账单不可归档
    code, body = api(client, 'POST', '/api/admin/archive', env['admin'], json_body={'order_id': env['order_id']})
    assert code == 400 and '企业对账单' in body['message']
    code, _ = api(client, 'POST', '/api/admin/bill/company/create', env['admin'], json_body={'order_id': env['order_id']})
    _, bl = api(client, 'GET', '/api/company/bill/list', env['r1'])
    cbid = bl['data']['list'][0]['bill_id']
    # 企业单未结清不可归档
    code, body = api(client, 'POST', '/api/admin/archive', env['admin'], json_body={'order_id': env['order_id']})
    assert code == 400 and '未结清' in body['message']
    api(client, 'POST', f'/api/company/bill/{cbid}/confirm', env['r1'])
    api(client, 'POST', f'/api/admin/bill/company/{cbid}/settle', env['admin'], json_body={})
    # 供方单缺失不可归档
    code, body = api(client, 'POST', '/api/admin/archive', env['admin'], json_body={'order_id': env['order_id']})
    assert code == 400 and '供方对账单' in body['message']
    code, _ = api(client, 'POST', '/api/admin/bill/supplier/create', env['admin'], json_body={'order_id': env['order_id']})
    _, sl = api(client, 'GET', '/api/supplier/bill/list', env['ra'])
    sbid = sl['data']['list'][0]['bill_id']
    api(client, 'POST', f'/api/supplier/bill/{sbid}/confirm', env['ra'])
    # 供方单未结清不可归档
    code, body = api(client, 'POST', '/api/admin/archive', env['admin'], json_body={'order_id': env['order_id']})
    assert code == 400 and '供方' in body['message']
    api(client, 'POST', f'/api/admin/bill/supplier/{sbid}/settle', env['admin'], json_body={})
    # 正式归档
    code, body = api(client, 'POST', '/api/admin/archive', env['admin'], json_body={'order_id': env['order_id']})
    assert code == 200, body
    assert body['data']['status'] == 'ARCHIVED'
    # 重复归档
    code, body = api(client, 'POST', '/api/admin/archive', env['admin'], json_body={'order_id': env['order_id']})
    assert code == 400 and '已归档' in body['message']
    # 联动状态：任务→ARCHIVED，需求→DISTRIBUTED，企业单据只读
    _, bl = api(client, 'GET', '/api/company/allocation/list', env['r1'])
    assert bl['data']['list'][0]['order_archived'] is True
    code, body = api(client, 'POST', f'/api/company/allocation/{aid}/feedback', env['r1'],
                     json_body={'description': '归档后反馈'})
    assert code == 400 and '只读' in body['message']
    # 需求变更只读
    # demand_id=1 不一定是本企业的，遍历需求列表取实际ID
    _, dl = api(client, 'GET', '/api/demand/list', env['r1'])
    did = dl['data']['list'][0]['demand_id']
    assert dl['data']['list'][0]['status'] == 'DISTRIBUTED'
    code, body = api(client, 'POST', f'/api/demand/{did}/change', env['r1'],
                     json_body={'change_type': 'QTY', 'change_desc': '调整为900吨', 'new_quantity': 900})
    assert code == 400 and '只读' in body['message']
    # 归档记录
    _, body = api(client, 'GET', '/api/admin/archive/list', env['admin'])
    assert body['data']['list'][0]['order_no'].startswith('CO')


def test_ledger(client):
    """履约台账：列表 + 筛选 + 导出"""
    env = setup_to_n5(client)
    code, _ = allocate(client, env)
    assert code == 200
    _, body = api(client, 'GET', '/api/admin/ledger', env['admin'])
    assert body['data']['total'] == 1
    row = body['data']['list'][0]
    assert row['company_name'] == '交易钢厂'
    assert row['period'] == '2026-01'
    assert row['bill_status'] is None  # 未生成对账单
    assert row['archived'] == 0
    # 筛选
    _, body = api(client, 'GET', '/api/admin/ledger?company=钢厂', env['admin'])
    assert body['data']['total'] == 1
    _, body = api(client, 'GET', '/api/admin/ledger?ore_category=CHROME', env['admin'])
    assert body['data']['total'] == 0
    _, body = api(client, 'GET', '/api/admin/ledger?period=2026-01', env['admin'])
    assert body['data']['total'] == 1
    # 导出
    resp = client.get('/api/admin/ledger/export', headers={'Authorization': 'Bearer ' + env['admin']})
    assert resp.status_code == 200 and 'spreadsheetml' in resp.content_type


def test_allocation_boundaries(client):
    """分拨边界：合计超量/非法企业/资质未审"""
    env = setup_to_n5(client)
    # 合计超过集采量
    code, body = allocate(client, env, allocs=[
        {'company_id': env['c1'], 'qty': 800, 'unit_price': 655},
        {'company_id': env['c1'], 'qty': 300, 'unit_price': 655}])
    assert code == 400 and '不可超过' in body['message']
    # 分拨对象非下游企业
    code, body = allocate(client, env, allocs=[{'company_id': env['cid_a'], 'qty': 500, 'unit_price': 655}])
    assert code == 400 and '下游' in body['message']
    # 明细非法数值
    code, body = allocate(client, env, allocs=[{'company_id': env['c1'], 'qty': 0, 'unit_price': 655}])
    assert code == 400
    # 允许：合计正好等于集采量
    code, body = allocate(client, env, allocs=[
        {'company_id': env['c1'], 'qty': 700, 'unit_price': 655, 'destination': '一号料场'},
        {'company_id': env['c1'], 'qty': 300, 'unit_price': 660, 'destination': '二号料场'}])
    assert code == 200
    _, body = api(client, 'GET', '/api/company/allocation/list', env['r1'])
    assert len(body['data']['list']) == 2
    assert sum(x['amount'] for x in body['data']['list']) == 700 * 655 + 300 * 660


# ============ 权限隔离 ============
def test_permission_isolation(client):
    env = setup_to_n5(client)
    code, _ = allocate(client, env)
    assert code == 200
    aid = get_alloc_id(client, env)
    code, _ = api(client, 'POST', '/api/admin/bill/company/create', env['admin'], json_body={'order_id': env['order_id']})
    _, bl = api(client, 'GET', '/api/company/bill/list', env['r1'])
    cbid = bl['data']['list'][0]['bill_id']
    code, _ = api(client, 'POST', '/api/admin/bill/supplier/create', env['admin'], json_body={'order_id': env['order_id']})
    # R2 不可访问企业端点
    code, _ = api(client, 'GET', '/api/company/allocation/list', env['ra'])
    assert code == 403
    code, _ = api(client, 'POST', f'/api/company/allocation/{aid}/confirm', env['ra'])
    assert code == 403
    code, _ = api(client, 'GET', '/api/company/bill/list', env['ra'])
    assert code == 403
    code, _ = api(client, 'POST', f'/api/company/bill/{cbid}/confirm', env['ra'])
    assert code == 403
    # R1 不可操作供方对账单端点
    code, _ = api(client, 'GET', '/api/supplier/bill/list', env['r1'])
    assert code == 403
    # R2 不可访问平台管理端点
    code, _ = api(client, 'POST', '/api/admin/archive', env['ra'], json_body={})
    assert code == 403
    code, _ = api(client, 'GET', '/api/admin/ledger', env['ra'])
    assert code == 403
    code, _ = api(client, 'GET', '/api/admin/feedback/list', env['ra'])
    assert code == 403
    # 越权：供方B确认供方A的对账单
    env2 = setup_env(client, suffix='乙')
    _, body = create_task(client, env2)
    tid2 = body['data']['task']['task_id']
    ia2 = get_inquiries(client, env2['rb'])
    quote(client, env2['rb'], ia2[0]['inquiry_id'], 640, 1200)
    _, body = api(client, 'POST', f'/api/admin/task/{tid2}/lock', env2['admin'],
                  json_body={'locks': [{'inquiry_id': ia2[0]['inquiry_id'], 'unit_price': 640, 'qty': 1000}]})
    code, body = api(client, 'POST', '/api/admin/bill/supplier/create', env['admin'],
                  json_body={'order_id': body['data']['orders'][0]['order_id']})
    assert code == 200, body
    sbid2 = body['data']['bill_id']
    # 供方A（env['ra']）确认乙链路供方B的账单 → 403
    code, body = api(client, 'POST', f'/api/supplier/bill/{sbid2}/confirm', env['ra'])
    assert code == 403
    # 未登录 → 401
    code, _ = api(client, 'GET', '/api/company/allocation/list')
    assert code == 401
    code, _ = api(client, 'GET', '/api/admin/ledger')
    assert code == 401
