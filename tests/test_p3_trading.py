# -*- coding: utf-8 -*-
"""PRD-04 集采交易模块测试：任务创建/报价-修改-拒绝/比价/锁货生成订单/订单明细/导出/权限隔离"""
from conftest import api, login, make_user
import io
from openpyxl import load_workbook

DEADLINE = '2026-12-31 18:00'


def setup_env(client, suffix=''):
    """搭建基础数据：1家下游(需求1000t IRON 2026-01) + 2家供方(货源5000t/3000t) + 归集清单"""
    r1, c1 = make_user(client, f'交易钢厂{suffix}')
    api(client, 'POST', '/api/demand/create', r1, json_body={
        'period_type': 'MONTH', 'period': '2026-01', 'ore_category': 'IRON', 'ore_type': 'PB_FINES',
        'quantity': 1000, 'grade_req': 'TFe>=62%', 'expected_arrival': '2026-03-01',
        'action': 'submit'})
    ra, ca = make_user(client, f'交易矿山A{suffix}', 'SUPPLIER', extra={'supplier_type': 'DOMESTIC'})
    rb, cb = make_user(client, f'交易矿山B{suffix}', 'SUPPLIER', extra={'supplier_type': 'DOMESTIC'})
    _, bodya = api(client, 'POST', '/api/resource/create', ra, json_body={
        'ore_category': 'IRON', 'origin': '河北承德', 'grade': 'TFe 62%', 'max_qty': 5000,
        'supply_period': '2026-01 ~ 2026-12', 'action': 'submit'})
    _, bodyb = api(client, 'POST', '/api/resource/create', rb, json_body={
        'ore_category': 'IRON', 'origin': '内蒙古包头', 'grade': 'TFe 60%', 'max_qty': 3000,
        'supply_period': '2026-01 ~ 2026-12', 'action': 'submit'})
    admin = login(client, 'admin', 'admin123')
    _, body = api(client, 'POST', '/api/admin/collective/create', admin,
                  json_body={'period_type': 'MONTH', 'period': '2026-01'})
    iron = next(x for x in body['data']['lists'] if x['ore_category'] == 'IRON')
    return {'r1': r1, 'c1': c1, 'ra': ra, 'rb': rb, 'admin': admin,
            'res_a': bodya['data']['resource_id'], 'res_b': bodyb['data']['resource_id'],
            'list_id': iron['list_id'], 'cid_a': ca, 'cid_b': cb}


def create_task(client, env, resource_ids=None, **over):
    body = {'list_id': env['list_id'],
            'resource_ids': [env['res_a'], env['res_b']] if resource_ids is None else resource_ids,
            'quote_deadline': DEADLINE, 'indicator_req': 'TFe>=62%', 'supply_time': '2026-03'}
    body.update(over)
    return api(client, 'POST', '/api/admin/task/create', env['admin'], json_body=body)


def quote(client, token, iid, price, qty, **over):
    body = {'quote_price': price, 'quote_qty': qty, 'supply_period': '2026-03 ~ 2026-04'}
    body.update(over)
    return api(client, 'POST', f'/api/supplier/inquiry/{iid}/quote', token, json_body=body)


def get_inquiries(client, token):
    _, body = api(client, 'GET', '/api/supplier/inquiry/list', token)
    return body['data']['list']


# ============ 功能测试 ============
def test_create_task_and_dispatch(client):
    """创建任务 → 批量下发询价，清单转已询价"""
    env = setup_env(client)
    code, body = create_task(client, env)
    assert code == 200, body
    data = body['data']
    assert data['inquiry_count'] == 2
    assert data['task']['status'] == 'WAIT_QUOTE'
    assert data['task']['task_no'].startswith('CT')
    assert data['task']['ore_category'] == 'IRON'
    assert data['task']['total_qty'] == 1000
    # 清单状态 → INQUIRED
    _, lb = api(client, 'GET', '/api/admin/collective/list', env['admin'])
    assert lb['data']['list'][0]['status'] == 'INQUIRED'
    # 两家供方各收到一条询价
    ia = get_inquiries(client, env['ra'])
    ib = get_inquiries(client, env['rb'])
    assert len(ia) == 1 and len(ib) == 1
    assert ia[0]['status'] == 'WAIT_QUOTE' and ib[0]['status'] == 'WAIT_QUOTE'
    assert ia[0]['task_no'] == data['task']['task_no']
    # 询价列表不包含下游企业明细字段
    assert 'company_name' not in ia[0] and 'details' not in ia[0]


def test_quote_flow_and_history(client):
    """报价 → 任务转比价中 → 修改报价保留历史版本"""
    env = setup_env(client)
    _, body = create_task(client, env)
    tid = body['data']['task']['task_id']
    ia = get_inquiries(client, env['ra'])
    iid = ia[0]['inquiry_id']
    # 提交报价
    code, _ = quote(client, env['ra'], iid, 650.5, 1200, indicator_commit='TFe 62 水分<8', remark='含运费')
    assert code == 200
    ia = get_inquiries(client, env['ra'])
    assert ia[0]['status'] == 'QUOTED' and ia[0]['quote_price'] == 650.5
    # 任务转比价中
    _, tb = api(client, 'GET', '/api/admin/task/list', env['admin'])
    assert tb['data']['list'][0]['status'] == 'QUOTING'
    assert tb['data']['list'][0]['quoted_total'] == 1
    # 修改报价 → 价格更新
    code, _ = api(client, 'PUT', f'/api/supplier/inquiry/{iid}/quote', env['ra'], json_body={
        'quote_price': 630, 'quote_qty': 1000, 'supply_period': '2026-03'})
    assert code == 200
    ia = get_inquiries(client, env['ra'])
    assert ia[0]['quote_price'] == 630.0
    # 历史版本保留2条（首次+修改）
    import sqlite3
    from backend.db import DB_PATH
    db = sqlite3.connect(DB_PATH)
    n = db.execute("SELECT COUNT(*) FROM quote_history WHERE inquiry_id=?", (iid,)).fetchone()[0]
    db.close()
    assert n == 2


def test_refuse_inquiry(client):
    """拒绝询价需填写原因"""
    env = setup_env(client)
    create_task(client, env)
    ib = get_inquiries(client, env['rb'])
    iid = ib[0]['inquiry_id']
    code, body = api(client, 'POST', f'/api/supplier/inquiry/{iid}/refuse', env['rb'], json_body={})
    assert code == 400 and '原因' in body['message']
    code, _ = api(client, 'POST', f'/api/supplier/inquiry/{iid}/refuse', env['rb'],
                  json_body={'reason': '产能不足，无法承接本周期供应'})
    assert code == 200
    ib = get_inquiries(client, env['rb'])
    assert ib[0]['status'] == 'REFUSED'
    assert ib[0]['refuse_reason'] == '产能不足，无法承接本周期供应'


def test_compare_view_sorted(client):
    """比价视图按单价升序，汇总全部供方报价"""
    env = setup_env(client)
    _, body = create_task(client, env)
    tid = body['data']['task']['task_id']
    ia = get_inquiries(client, env['ra'])
    ib = get_inquiries(client, env['rb'])
    quote(client, env['ra'], ia[0]['inquiry_id'], 680, 1200)
    quote(client, env['rb'], ib[0]['inquiry_id'], 655, 1000)
    code, body = api(client, 'GET', f'/api/admin/task/{tid}/compare', env['admin'])
    assert code == 200
    cps = body['data']['compares']
    assert len(cps) == 2
    assert [c['quote_price'] for c in cps] == [655.0, 680.0]
    assert cps[0]['company_name'] == '交易矿山B'
    assert all(c.get('origin') for c in cps)


def test_lock_single_supplier(client):
    """单家锁货：生成订单+下游明细，状态全链路联动"""
    env = setup_env(client)
    _, body = create_task(client, env)
    tid = body['data']['task']['task_id']
    ia = get_inquiries(client, env['ra'])
    quote(client, env['ra'], ia[0]['inquiry_id'], 650, 1500)
    code, body = api(client, 'POST', f'/api/admin/task/{tid}/lock', env['admin'], json_body={
        'locks': [{'inquiry_id': ia[0]['inquiry_id'], 'unit_price': 645, 'qty': 1000}]})
    assert code == 200, body
    orders = body['data']['orders']
    assert len(orders) == 1
    o = orders[0]
    assert o['order_no'].startswith('CO')
    assert o['total_qty'] == 1000 and o['unit_price'] == 645
    assert o['total_amount'] == 645000.0
    assert o['status'] == 'LOCKED'
    # 订单详情：下游申报明细保留（仅平台可见）
    code, ob = api(client, 'GET', f"/api/admin/order/{o['order_id']}", env['admin'])
    assert code == 200
    assert ob['data']['supplier_name'] == '交易矿山A'
    assert len(ob['data']['details']) == 1
    dt = ob['data']['details'][0]
    assert dt['company_name'] == '交易钢厂' and dt['qty'] == 1000
    # 询价状态：被锁→LOCKED；未锁（未报价的B）→NOT_SELECTED
    assert get_inquiries(client, env['ra'])[0]['status'] == 'LOCKED'
    assert get_inquiries(client, env['rb'])[0]['status'] == 'NOT_SELECTED'
    # 任务 → LOCKED
    _, tb = api(client, 'GET', '/api/admin/task/list', env['admin'])
    assert tb['data']['list'][0]['status'] == 'LOCKED'
    # 需求 → IN_EXEC
    _, dl = api(client, 'GET', '/api/demand/list', env['r1'])
    assert dl['data']['list'][0]['status'] == 'IN_EXEC'


def test_lock_multiple_suppliers_and_orders(client):
    """多家合计覆盖需求量 → 每家一张订单"""
    env = setup_env(client)
    _, body = create_task(client, env)
    tid = body['data']['task']['task_id']
    ia = get_inquiries(client, env['ra'])
    ib = get_inquiries(client, env['rb'])
    quote(client, env['ra'], ia[0]['inquiry_id'], 650, 600)
    quote(client, env['rb'], ib[0]['inquiry_id'], 640, 500)
    code, body = api(client, 'POST', f'/api/admin/task/{tid}/lock', env['admin'], json_body={
        'locks': [{'inquiry_id': ia[0]['inquiry_id'], 'unit_price': 650, 'qty': 600},
                  {'inquiry_id': ib[0]['inquiry_id'], 'unit_price': 640, 'qty': 400}]})
    assert code == 200
    orders = body['data']['orders']
    assert len(orders) == 2
    assert {o['supplier_id'] for o in orders} == {env['cid_a'], env['cid_b']}
    assert sum(o['total_qty'] for o in orders) == 1000
    # 订单列表
    _, ol = api(client, 'GET', '/api/admin/order/list', env['admin'])
    assert ol['data']['total'] == 2


def test_compare_export(client):
    resp = client.get('/api/admin/task/1/compare/export')
    assert resp.status_code == 401  # 未登录
    env = setup_env(client)
    _, body = create_task(client, env)
    tid = body['data']['task']['task_id']
    ia = get_inquiries(client, env['ra'])
    quote(client, env['ra'], ia[0]['inquiry_id'], 650, 1200)
    resp = client.get(f'/api/admin/task/{tid}/compare/export',
                      headers={'Authorization': 'Bearer ' + env['admin']})
    assert resp.status_code == 200
    assert 'spreadsheetml' in resp.content_type
    wb = load_workbook(io.BytesIO(resp.data))
    ws = wb.active
    assert ws.max_row == 3  # 表头 + 2家供方
    assert ws.cell(2, 2).value == '交易矿山A'


# ============ 边界测试 ============
def test_task_create_boundaries(client):
    env = setup_env(client)
    # 缺少供货方
    code, body = create_task(client, env, resource_ids=[])
    assert code == 400
    # 品类不符（清单为IRON，货源为CHROME）
    _, bodyb = api(client, 'POST', '/api/resource/create', env['rb'], json_body={
        'ore_category': 'CHROME', 'origin': '西藏', 'grade': 'Cr2O3 40%', 'max_qty': 800,
        'supply_period': '2026-01 ~ 2026-06', 'action': 'submit'})
    code, body = create_task(client, env, resource_ids=[bodyb['data']['resource_id']])
    assert code == 400 and '品类' in body['message']
    # 截止时间格式错误
    code, _ = create_task(client, env, quote_deadline='2026/12/31')
    assert code == 400
    # 截止时间早于当前
    code, body = create_task(client, env, quote_deadline='2026-01-01 00:00')
    assert code == 400 and '晚于' in body['message']
    # 重复创建（清单已INQUIRED）
    create_task(client, env)
    code, body = create_task(client, env)
    assert code == 400 and '不可重复' in body['message']


def test_quote_boundaries(client):
    env = setup_env(client)
    create_task(client, env)
    ia = get_inquiries(client, env['ra'])
    iid = ia[0]['inquiry_id']
    # 数量超货源可供应量（5000）
    code, body = quote(client, env['ra'], iid, 650, 6000)
    assert code == 400 and '可供应量' in body['message']
    # 单价/数量非正数
    code, _ = quote(client, env['ra'], iid, 0, 1000)
    assert code == 400
    code, _ = quote(client, env['ra'], iid, 650, -1)
    assert code == 400
    # 供货周期必填
    code, body = quote(client, env['ra'], iid, 650, 1000, supply_period='')
    assert code == 400 and '供货周期' in body['message']
    # 未报价状态不能走修改接口
    code, body = api(client, 'PUT', f'/api/supplier/inquiry/{iid}/quote', env['ra'],
                     json_body={'quote_price': 650, 'quote_qty': 1000, 'supply_period': '2026-03'})
    assert code == 400
    # 已报价不能再走首次提交接口
    quote(client, env['ra'], iid, 650, 1000)
    code, body = quote(client, env['ra'], iid, 660, 1000)
    assert code == 400 and '提交' in body['message']


def test_quote_deadline_expired(client):
    """过截止时间不可报价"""
    import sqlite3
    from backend.db import DB_PATH
    env = setup_env(client)
    create_task(client, env)
    # 将任务截止时间回拨至过去，模拟过期
    db = sqlite3.connect(DB_PATH)
    db.execute("UPDATE collective_task SET quote_deadline='2026-01-01 00:00'")
    db.commit()
    db.close()
    ia = get_inquiries(client, env['ra'])
    code, body = quote(client, env['ra'], ia[0]['inquiry_id'], 650, 1000)
    assert code == 400 and '截止' in body['message']


def test_lock_boundaries(client):
    env = setup_env(client)
    _, body = create_task(client, env)
    tid = body['data']['task']['task_id']
    ia = get_inquiries(client, env['ra'])
    iid = ia[0]['inquiry_id']
    # 未报价不可锁
    code, body = api(client, 'POST', f'/api/admin/task/{tid}/lock', env['admin'],
                     json_body={'locks': [{'inquiry_id': iid, 'unit_price': 650, 'qty': 1000}]})
    assert code == 400 and '状态' in body['message']
    quote(client, env['ra'], iid, 650, 1500)
    # 锁货量超过报价量
    code, body = api(client, 'POST', f'/api/admin/task/{tid}/lock', env['admin'],
                     json_body={'locks': [{'inquiry_id': iid, 'unit_price': 650, 'qty': 1600}]})
    assert code == 400 and '报价量' in body['message']
    # 合计未覆盖需求量
    code, body = api(client, 'POST', f'/api/admin/task/{tid}/lock', env['admin'],
                     json_body={'locks': [{'inquiry_id': iid, 'unit_price': 650, 'qty': 900}]})
    assert code == 400 and '覆盖' in body['message']
    # 正常锁货
    code, _ = api(client, 'POST', f'/api/admin/task/{tid}/lock', env['admin'],
                  json_body={'locks': [{'inquiry_id': iid, 'unit_price': 650, 'qty': 1000}]})
    assert code == 200
    # 锁货后不可重复锁货
    code, body = api(client, 'POST', f'/api/admin/task/{tid}/lock', env['admin'],
                     json_body={'locks': [{'inquiry_id': iid, 'unit_price': 650, 'qty': 1000}]})
    assert code == 400 and '不可锁货' in body['message']
    # 锁货后供方不可再改价/拒绝
    code, _ = api(client, 'PUT', f'/api/supplier/inquiry/{iid}/quote', env['ra'],
                  json_body={'quote_price': 600, 'quote_qty': 1000, 'supply_period': '2026-03'})
    assert code == 400
    code, _ = api(client, 'POST', f'/api/supplier/inquiry/{iid}/refuse', env['ra'],
                  json_body={'reason': '反悔'})
    assert code == 400


# ============ 权限隔离 ============
def test_permission_isolation(client):
    env = setup_env(client)
    # 下游R1不可访问集采交易管理端
    code, _ = api(client, 'POST', '/api/admin/task/create', env['r1'], json_body={})
    assert code == 403
    code, _ = api(client, 'GET', '/api/admin/task/list', env['r1'])
    assert code == 403
    # 供方不可访问管理端比价/锁货
    code, _ = api(client, 'GET', '/api/admin/task/1/compare', env['ra'])
    assert code == 403
    code, _ = api(client, 'POST', '/api/admin/task/1/lock', env['ra'], json_body={'locks': []})
    assert code == 403
    # 供方不可见下游明细订单详情
    code, _ = api(client, 'GET', '/api/admin/order/1', env['ra'])
    assert code == 403
    # 供方A不能操作供方B的询价
    create_task(client, env)
    ib = get_inquiries(client, env['rb'])
    code, _ = quote(client, env['ra'], ib[0]['inquiry_id'], 650, 100)
    assert code == 403
    code, _ = api(client, 'POST', f"/api/supplier/inquiry/{ib[0]['inquiry_id']}/refuse", env['ra'],
                  json_body={'reason': '越权'})
    assert code == 403
    # 未登录 → 401
    code, _ = api(client, 'GET', '/api/supplier/inquiry/list')
    assert code == 401
    code, _ = api(client, 'GET', '/api/admin/task/list')
    assert code == 401
