# -*- coding: utf-8 -*-
"""PRD-05 物流跟踪模块测试：任务创建/节点顺序推进/单据/看板/回退授权/下游只读/权限隔离"""
from conftest import api, login
from test_p3_trading import setup_env, create_task, quote, get_inquiries

PARTNER_EXTRA = {'partner_type': 'PORT'}


def setup_locked_order(client, suffix=''):
    """搭建到「已锁货订单」的完整链路，返回 env + order_id"""
    env = setup_env(client, suffix=suffix)
    _, body = create_task(client, env)
    tid = body['data']['task']['task_id']
    ia = get_inquiries(client, env['ra'])
    quote(client, env['ra'], ia[0]['inquiry_id'], 650, 1500)
    _, body = api(client, 'POST', f'/api/admin/task/{tid}/lock', env['admin'],
                  json_body={'locks': [{'inquiry_id': ia[0]['inquiry_id'], 'unit_price': 650, 'qty': 1000}]})
    env['order_id'] = body['data']['orders'][0]['order_id']
    return env


def _mk(client, name):
    from conftest import make_user
    return make_user(client, name, 'PARTNER', extra={'partner_type': 'PORT'})


def create_logi(client, env, partners, **over):
    p = partners[0] if partners else None
    body = {'order_id': env.get('order_id'),
            'sea_partner_id': p, 'port_partner_id': p,
            'warehouse_partner_id': p, 'land_partner_id': p,
            'from_place': '河北承德', 'dest_port': '曹妃甸港', 'plan_arrival': '2026-03-15 10:00',
            'warehouse': '曹妃甸港区一号仓', 'dest_place': '交易钢厂料场'}
    body.update(over)
    return api(client, 'POST', '/api/admin/logistics/create', env['admin'], json_body=body)


def advance(client, token, lid, code, **over):
    body = {'node_code': code, 'actual_time': '2026-03-01 10:00'}
    body.update(over)
    return api(client, 'POST', f'/api/partner/logistics/{lid}/advance', token, json_body=body)


# ============ 功能测试 ============
def test_create_logistics_task(client):
    """已锁货订单创建物流任务 → 7节点待推进"""
    env = setup_locked_order(client)
    ptok, pcid = _mk(client, '承德港务')
    code, body = create_logi(client, env, [pcid])
    assert code == 200, body
    d = body['data']
    assert d['logi_no'].startswith('LG')
    assert d['current_node'] == 0 and d['phase'] == 'NOT_STARTED'
    assert d['order_no'].startswith('CO') and d['supplier_name'] == '交易矿山A'
    # 7 个节点已生成
    _, det = api(client, 'GET', f"/api/admin/logistics/{d['logi_id']}", env['admin'])
    nodes = det['data']['nodes']
    assert [n['node_code'] for n in nodes] == [1, 2, 3, 4, 5, 6, 7]
    assert all(n['status'] == 'PENDING' for n in nodes)
    assert nodes[0]['node_name'] == '待启运' and nodes[6]['node_name'] == '完成送达'


def test_full_node_advance_flow(client):
    """N1→N7 顺序推进 + 单据上传 + 操作人记录"""
    env = setup_locked_order(client)
    ptok, pcid = _mk(client, '全链路物流')
    code, body = create_logi(client, env, [pcid])
    lid = body['data']['logi_id']
    # 依次推进 7 个节点
    for i in range(1, 8):
        atts = [{'doc_type': 'BILL', 'file_url': '/api/files/doc.pdf', 'file_name': f'单据{i}.pdf'}] if i in (4, 5, 7) else []
        code, body = advance(client, ptok, lid, i, attachments=atts)
        assert code == 200, (i, body)
        assert body['data']['current_node'] == i
    _, det = api(client, 'GET', f'/api/admin/logistics/{lid}', env['admin'])
    d = det['data']
    assert d['current_node'] == 7 and d['phase'] == 'DELIVERED'
    assert all(n['status'] == 'DONE' for n in d['nodes'])
    assert d['nodes'][0]['actual_time'] == '2026-03-01 10:00'
    # 附件挂在对应节点
    assert len(d['nodes'][3]['attachments']) == 1
    assert d['nodes'][6]['attachments'][0]['file_name'] == '单据7.pdf'


def test_board_and_stats(client):
    """总看板：列表 + 阶段分布统计 + 筛选"""
    env = setup_locked_order(client)
    ptok, pcid = _mk(client, '看板物流')
    code, body = create_logi(client, env, [pcid])
    lid = body['data']['logi_id']
    advance(client, ptok, lid, 1)
    advance(client, ptok, lid, 2)
    code, body = api(client, 'GET', '/api/admin/logistics/board', env['admin'])
    assert code == 200
    assert body['data']['stats'] == {'total': 1, 'NOT_STARTED': 0, 'IN_TRANSIT': 1, 'WAREHOUSED': 0, 'DELIVERED': 0}
    row = body['data']['list'][0]
    assert row['phase'] == 'IN_TRANSIT' and row['current_name'] == '海运在途'
    # 推进到 N5 → 入仓储（解锁分拨阶段）
    advance(client, ptok, lid, 3)
    advance(client, ptok, lid, 4)
    advance(client, ptok, lid, 5)
    _, body = api(client, 'GET', '/api/admin/logistics/board?phase=WAREHOUSED', env['admin'])
    assert body['data']['total'] == 1
    # 筛选供方/港口
    _, body = api(client, 'GET', '/api/admin/logistics/board?supplier=矿山A', env['admin'])
    assert body['data']['total'] == 1
    _, body = api(client, 'GET', '/api/admin/logistics/board?dest_port=黄骅', env['admin'])
    assert body['data']['total'] == 0
    _, body = api(client, 'GET', '/api/admin/logistics/board?dest_port=曹妃甸', env['admin'])
    assert body['data']['total'] == 1


def test_partner_task_list(client):
    """配套方任务列表：角色标识 + 待办节点"""
    env = setup_locked_order(client)
    ptok, pcid = _mk(client, '任务列表物流')
    create_logi(client, env, [pcid])
    _, body = api(client, 'GET', '/api/partner/logistics/list', ptok)
    assert body['data']['total'] == 1
    row = body['data']['list'][0]
    assert row['my_roles'] == ['海运方', '港口方', '仓储方', '陆运方']
    assert row['mine_to_do'] is True
    assert row['next_node']['node_code'] == 1 and row['next_node']['node_name'] == '待启运'
    advance(client, ptok, row['logi_id'], 1)
    _, body = api(client, 'GET', '/api/partner/logistics/list', ptok)
    assert body['data']['list'][0]['next_node']['node_code'] == 2


def test_rollback_with_authorization(client):
    """管理员授权回退：重置后续节点"""
    env = setup_locked_order(client)
    ptok, pcid = _mk(client, '回退物流')
    code, body = create_logi(client, env, [pcid])
    lid = body['data']['logi_id']
    for i in (1, 2, 3, 4, 5):
        advance(client, ptok, lid, i)
    # 无原因不可回退
    code, body = api(client, 'POST', f'/api/admin/logistics/{lid}/rollback', env['admin'],
                     json_body={'node_code': 3})
    assert code == 400 and '原因' in body['message']
    code, body = api(client, 'POST', f'/api/admin/logistics/{lid}/rollback', env['admin'],
                     json_body={'node_code': 3, 'reason': '卸货数量与单据不符，需复核'})
    assert code == 200
    assert body['data']['current_node'] == 3
    _, det = api(client, 'GET', f'/api/admin/logistics/{lid}', env['admin'])
    st = {n['node_code']: n['status'] for n in det['data']['nodes']}
    assert st[1] == 'DONE' and st[3] == 'DONE' and st[4] == 'PENDING' and st[5] == 'PENDING'
    # 回退后可重新推进
    code, _ = advance(client, ptok, lid, 4)
    assert code == 200


def test_order_timeline(client):
    env = setup_locked_order(client)
    ptok, pcid = _mk(client, '时间线物流')
    code, body = create_logi(client, env, [pcid])
    lid = body['data']['logi_id']
    advance(client, ptok, lid, 1)
    code, body = api(client, 'GET', f"/api/logistics/order/{env['order_id']}/timeline", env['admin'])
    assert code == 200
    assert len(body['data']['nodes']) == 7
    assert body['data']['nodes'][0]['status'] == 'DONE'
    # 配套方可查看被分配任务时间线
    code, _ = api(client, 'GET', f"/api/logistics/order/{env['order_id']}/timeline", ptok)
    assert code == 200


def test_company_logistics_readonly(client):
    """下游只读接口：无分拨单返回空列表（分拨数据由 PRD-07 生成）"""
    env = setup_env(client)
    code, body = api(client, 'GET', '/api/company/logistics/list', env['r1'])
    assert code == 200
    assert body['data']['list'] == []


# ============ 边界测试 ============
def test_create_boundaries(client):
    env = setup_locked_order(client)
    ptok, pcid = _mk(client, '边界物流')
    # 重复创建
    code, _ = create_logi(client, env, [pcid])
    assert code == 200
    code, body = create_logi(client, env, [pcid])
    assert code == 400 and '已存在' in body['message']
    # 订单不存在
    code, body = create_logi(client, env, [pcid], order_id=9999)
    assert code == 404
    # 新链路：未分配任何配套方
    env2 = setup_env(client, suffix='乙')
    _, body = create_task(client, env2)
    tid = body['data']['task']['task_id']
    ia = get_inquiries(client, env2['ra'])
    quote(client, env2['ra'], ia[0]['inquiry_id'], 650, 1500)
    _, body = api(client, 'POST', f'/api/admin/task/{tid}/lock', env2['admin'],
                  json_body={'locks': [{'inquiry_id': ia[0]['inquiry_id'], 'unit_price': 650, 'qty': 1000}]})
    oid2 = body['data']['orders'][0]['order_id']
    code, body = create_logi(client, env2, [], order_id=oid2)
    assert code == 400 and '至少分配' in body['message']
    # 配套方资质未审核 → 不可被分配
    from conftest import register_company
    _, _, raw_cid = register_company(client, '未审配套', 'PARTNER', extra={'partner_type': 'PORT'})
    code, body = create_logi(client, env2, [raw_cid], order_id=oid2)
    assert code == 400 and '资质' in body['message']
    # 非配套方企业类型不可被分配
    code, body = create_logi(client, env2, [env2['cid_a']], order_id=oid2)
    assert code == 400 and '配套方' in body['message']


def test_advance_boundaries(client):
    env = setup_locked_order(client)
    ptok, pcid = _mk(client, '推进边界')
    code, body = create_logi(client, env, [pcid])
    lid = body['data']['logi_id']
    # 跳级：N1 未完成直接推 N2
    code, body = advance(client, ptok, lid, 2)
    assert code == 400 and '跳级' in body['message']
    # 非法 node_code
    code, _ = advance(client, ptok, lid, 8)
    assert code == 400
    # 未来时间不可
    code, body = advance(client, ptok, lid, 1, actual_time='2030-01-01 00:00')
    assert code == 400 and '不可晚于' in body['message']
    # 时间格式错误
    code, _ = advance(client, ptok, lid, 1, actual_time='2030/01/01')
    assert code == 400
    # 正常推进 N1 后重复推进 / 倒退
    advance(client, ptok, lid, 1)
    code, body = advance(client, ptok, lid, 1)
    assert code == 400 and '不可重复' in body['message']
    code, body = advance(client, ptok, lid, 0)
    assert code == 400
    # 未分配节点的负责方（本用例全部分配给 pcid，构造未分配场景：只分配海运）
    code, body = advance(client, ptok, lid, 2)
    assert code == 200  # pcid 同时是海运方
    # 新建一个只分配陆运的任务验证「节点未分配负责方」
    env2 = setup_locked_order(client, suffix='乙')
    from conftest import make_user
    ltok, lcid = make_user(client, '纯陆运配套', 'PARTNER', extra={'partner_type': 'LAND'})
    code, body = create_logi(client, env2, [lcid], sea_partner_id='', port_partner_id='',
                             warehouse_partner_id='')
    assert code == 200
    lid2 = body['data']['logi_id']
    code, body = advance(client, ltok, lid2, 1)
    assert code == 400 and '未分配' in body['message']


def test_advance_not_my_node(client):
    """节点不由本人负责时不可推进"""
    env = setup_locked_order(client)
    from conftest import make_user
    atok, acid = make_user(client, '仅海运配套', 'PARTNER', extra={'partner_type': 'SEA'})
    btok, bcid = make_user(client, '仅陆运配套', 'PARTNER', extra={'partner_type': 'LAND'})
    code, body = create_logi(client, env, [bcid], sea_partner_id=acid, port_partner_id=acid,
                             warehouse_partner_id=acid)
    lid = body['data']['logi_id']
    # 陆运方推海运节点 → 403
    code, body = advance(client, btok, lid, 1)
    assert code == 403 and '不由您负责' in body['message']
    # 海运方正常推进 N1
    code, _ = advance(client, atok, lid, 1)
    assert code == 200
    # 海运方推 N6（陆运节点）→ 403
    code, body = advance(client, atok, lid, 6)
    assert code in (400, 403)


# ============ 权限隔离 ============
def test_permission_isolation(client):
    env = setup_locked_order(client)
    ptok, pcid = _mk(client, '权限物流')
    code, body = create_logi(client, env, [pcid])
    lid = body['data']['logi_id']
    # R1 不可访问看板/创建/推进
    code, _ = api(client, 'GET', '/api/admin/logistics/board', env['r1'])
    assert code == 403
    code, _ = api(client, 'POST', '/api/admin/logistics/create', env['r1'], json_body={})
    assert code == 403
    code, _ = advance(client, env['r1'], lid, 1)
    assert code == 403
    # R1 不可访问订单时间线（R1 走 /api/company/logistics/list）
    code, _ = api(client, 'GET', f"/api/logistics/order/{env['order_id']}/timeline", env['r1'])
    assert code == 403
    # R3 不可访问管理端看板
    code, _ = api(client, 'GET', '/api/admin/logistics/board', ptok)
    assert code == 403
    # 未被分配的配套方不可看任务节点明细与时间线
    from conftest import make_user
    otok, ocid = make_user(client, '无关配套', 'PARTNER', extra={'partner_type': 'WAREHOUSE'})
    code, _ = api(client, 'GET', f'/api/partner/logistics/{lid}/nodes', otok)
    assert code == 403
    code, _ = api(client, 'GET', f"/api/logistics/order/{env['order_id']}/timeline", otok)
    assert code == 403
    # 未登录 → 401
    code, _ = api(client, 'GET', '/api/admin/logistics/board')
    assert code == 401
    code, _ = api(client, 'GET', '/api/partner/logistics/list')
    assert code == 401
