# -*- coding: utf-8 -*-
"""PRD-06 价格数据模块测试：行情CRUD/批量导入/成交均价统计/趋势/下游脱敏/权限隔离"""
import io
from conftest import api, login
from openpyxl import Workbook
from test_p3_trading import setup_env, create_task, quote, get_inquiries


def mk_price(client, admin, **over):
    body = {'ore_category': 'IRON', 'spec': 'TFe 62%', 'quote_date': '2026-01-15',
            'market_price': 720.5, 'source': 'Mysteel'}
    body.update(over)
    return api(client, 'POST', '/api/admin/price/create', admin, json_body=body)


def setup_deal_order(client):
    """构建一笔已锁货集采订单，用于成交均价统计"""
    env = setup_env(client)
    _, body = create_task(client, env)
    tid = body['data']['task']['task_id']
    ia = get_inquiries(client, env['ra'])
    quote(client, env['ra'], ia[0]['inquiry_id'], 650, 1500)
    _, body = api(client, 'POST', f'/api/admin/task/{tid}/lock', env['admin'],
                  json_body={'locks': [{'inquiry_id': ia[0]['inquiry_id'], 'unit_price': 645.5, 'qty': 1000}]})
    return env, body['data']['orders'][0]


# ============ 功能测试 ============
def test_price_crud(client):
    admin = login(client, 'admin', 'admin123')
    code, body = mk_price(client, admin)
    assert code == 200
    pid = body['data']['id']
    # 列表可见
    _, body = api(client, 'GET', '/api/admin/price/list', admin)
    assert body['data']['total'] == 1
    row = body['data']['list'][0]
    assert row['ore_category'] == 'IRON' and row['market_price'] == 720.5
    # 编辑
    code, _ = api(client, 'PUT', f'/api/admin/price/{pid}', admin, json_body={
        'ore_category': 'IRON', 'spec': 'TFe 62%', 'quote_date': '2026-01-16',
        'market_price': 725, 'avg_deal_price': 680, 'source': '钢联'})
    assert code == 200
    _, body = api(client, 'GET', '/api/admin/price/list', admin)
    assert body['data']['list'][0]['market_price'] == 725
    assert body['data']['list'][0]['avg_deal_price'] == 680
    # 删除
    code, _ = api(client, 'DELETE', f'/api/admin/price/{pid}', admin)
    assert code == 200
    _, body = api(client, 'GET', '/api/admin/price/list', admin)
    assert body['data']['total'] == 0


def test_price_template(client):
    admin = login(client, 'admin', 'admin123')
    resp = client.get('/api/admin/price/template', headers={'Authorization': 'Bearer ' + admin})
    assert resp.status_code == 200
    assert 'spreadsheetml' in resp.content_type


def _xlsx(rows):
    wb = Workbook()
    ws = wb.active
    ws.append(['矿石品类', '指标规格', '日期', '市场参考价(元/吨)', '平台成交均价(元/吨)', '数据来源', '备注'])
    for r in rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


def test_price_import(client):
    admin = login(client, 'admin', 'admin123')
    buf = _xlsx([
        ['IRON', 'TFe 62%', '2026-01-15', 720.5, None, 'Mysteel', ''],
        ['CHROME', 'Cr2O3 40%', '2026-01-20', 1500, '', '', '南非块矿'],
    ])
    resp = client.post('/api/admin/price/import', data={'file': (buf, 'prices.xlsx')},
                       headers={'Authorization': 'Bearer ' + admin},
                       content_type='multipart/form-data')
    assert resp.status_code == 200
    body = resp.get_json()
    assert body['data']['inserted'] == 2 and body['data']['failed'] == 0
    _, body = api(client, 'GET', '/api/admin/price/list', admin)
    assert body['data']['total'] == 2


def test_price_import_partial_errors(client):
    admin = login(client, 'admin', 'admin123')
    buf = _xlsx([
        ['IRON', 'TFe 62%', '2026-01-15', 720.5, None, 'Mysteel', ''],       # 合法
        ['IRON', '', '2026-01-16', 700, None, '', ''],                       # 缺指标规格
        ['IRON', 'TFe 60%', '2026/01/17', 700, None, '', ''],                # 日期格式错
        ['IRON', 'TFe 58%', '2026-01-18', -5, None, '', ''],                 # 价格非法
        ['CHROME', 'Cr2O3 40%', '2026-01-20', 1500, None, '', ''],           # 合法
    ])
    resp = client.post('/api/admin/price/import', data={'file': (buf, 'prices.xlsx')},
                       headers={'Authorization': 'Bearer ' + admin},
                       content_type='multipart/form-data')
    body = resp.get_json()
    assert body['data']['inserted'] == 2 and body['data']['failed'] == 3
    assert {e['row'] for e in body['data']['errors']} == {3, 4, 5}
    _, body = api(client, 'GET', '/api/admin/price/list', admin)
    assert body['data']['total'] == 2


def test_admin_trend_and_deal_stats(client):
    env, order = setup_deal_order(client)
    admin = env['admin']
    mk_price(client, admin, quote_date='2026-01-15', market_price=720.5, avg_deal_price=680)
    mk_price(client, admin, quote_date='2026-02-15', market_price=715, avg_deal_price=660)
    code, body = api(client, 'GET', '/api/admin/price/trend', admin)
    assert code == 200
    trend = body['data']['trend']
    assert [t['market_price'] for t in trend] == [720.5, 715]  # 按日期升序
    assert [t['avg_deal_price'] for t in trend] == [680, 660]
    # 成交均价统计来自真实锁货订单（单价645.5，1000吨）
    stats = body['data']['deal_stats']
    assert len(stats) == 1
    s = stats[0]
    assert s['order_count'] == 1 and s['total_qty'] == 1000
    assert s['avg_unit_price'] == 645.5
    assert s['month'] == order['create_time'][:7]
    # 品类筛选
    _, body = api(client, 'GET', '/api/admin/price/trend?ore_category=CHROME', admin)
    assert body['data']['trend'] == []


def test_company_trend_masked(client):
    """下游只读行情：脱敏，不可见平台成交均价/成交统计"""
    env, _ = setup_deal_order(client)
    admin = env['admin']
    mk_price(client, admin, quote_date='2026-01-15', market_price=720.5, avg_deal_price=680)
    code, body = api(client, 'GET', '/api/company/price/trend', env['r1'])
    assert code == 200
    assert body['data']['total'] == 1
    row = body['data']['list'][0]
    # 仅公开字段
    assert set(row.keys()) == {'id', 'ore_category', 'spec', 'quote_date', 'market_price', 'source'}
    assert row['market_price'] == 720.5
    # 无成交均价统计
    assert 'deal_stats' not in body['data']


# ============ 边界测试 ============
def test_create_boundaries(client):
    admin = login(client, 'admin', 'admin123')
    # 缺品类/规格
    code, body = mk_price(client, admin, ore_category='')
    assert code == 400 and '品类' in body['message']
    code, body = mk_price(client, admin, spec='')
    assert code == 400 and '规格' in body['message']
    # 日期格式
    code, body = mk_price(client, admin, quote_date='2026/01/15')
    assert code == 400 and 'YYYY-MM-DD' in body['message']
    # 价格非法
    code, body = mk_price(client, admin, market_price=0)
    assert code == 400 and '大于0' in body['message']
    code, body = mk_price(client, admin, market_price='abc')
    assert code == 400
    # 成交均价非法
    code, body = mk_price(client, admin, avg_deal_price=-1)
    assert code == 400 and '成交均价' in body['message']
    # 备注超长
    code, body = mk_price(client, admin, remark='x' * 201)
    assert code == 400 and '备注' in body['message']
    # 编辑/删除不存在的记录
    code, body = api(client, 'PUT', '/api/admin/price/999', admin, json_body={
        'ore_category': 'IRON', 'spec': 'TFe 62%', 'quote_date': '2026-01-15', 'market_price': 700})
    assert code == 404
    code, body = api(client, 'DELETE', '/api/admin/price/999', admin)
    assert code == 404
    # 导入：无文件 / 空数据
    code, body = api(client, 'POST', '/api/admin/price/import', admin, json_body={})
    assert code == 400 and '上传' in body['message']
    buf = _xlsx([])
    resp = client.post('/api/admin/price/import', data={'file': (buf, 'empty.xlsx')},
                       headers={'Authorization': 'Bearer ' + admin},
                       content_type='multipart/form-data')
    assert resp.get_json()['code'] == 1  # 模板无数据行
    # 非Excel文件
    resp = client.post('/api/admin/price/import', data={'file': (io.BytesIO(b'not excel'), 'x.xlsx')},
                       headers={'Authorization': 'Bearer ' + admin},
                       content_type='multipart/form-data')
    assert resp.get_json()['code'] == 1  # 解析失败


def test_list_filters(client):
    admin = login(client, 'admin', 'admin123')
    mk_price(client, admin, ore_category='IRON', quote_date='2026-01-10')
    mk_price(client, admin, ore_category='CHROME', quote_date='2026-02-10')
    _, body = api(client, 'GET', '/api/admin/price/list?ore_category=IRON', admin)
    assert body['data']['total'] == 1
    _, body = api(client, 'GET', '/api/admin/price/list?date_from=2026-02-01&date_to=2026-02-28', admin)
    assert body['data']['total'] == 1
    assert body['data']['list'][0]['ore_category'] == 'CHROME'


# ============ 权限隔离 ============
def test_permission_isolation(client):
    env, _ = setup_deal_order(client)
    # R1 不可访问管理端行情接口
    code, _ = api(client, 'POST', '/api/admin/price/create', env['r1'], json_body={})
    assert code == 403
    code, _ = api(client, 'GET', '/api/admin/price/list', env['r1'])
    assert code == 403
    code, _ = api(client, 'GET', '/api/admin/price/trend', env['r1'])
    assert code == 403
    code, _ = api(client, 'POST', '/api/admin/price/import', env['r1'], json_body={})
    assert code == 403
    code, _ = api(client, 'DELETE', '/api/admin/price/1', env['r1'])
    assert code == 403
    # R2/R3 不可访问下游行情接口
    code, _ = api(client, 'GET', '/api/company/price/trend', env['ra'])
    assert code == 403
    # 未登录 → 401
    code, _ = api(client, 'GET', '/api/admin/price/list')
    assert code == 401
    code, _ = api(client, 'GET', '/api/company/price/trend')
    assert code == 401
