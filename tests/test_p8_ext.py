# -*- coding: utf-8 -*-
"""PRD-09~15 扩展模块测试：质检化验(PRD-09)/合同管理(PRD-10)/费用分摊(PRD-11)/
消息预警(PRD-12)/报表大屏(PRD-13)/字典指标(PRD-14)/变更红冲(PRD-15)"""
import sqlite3
from datetime import datetime, timedelta
from urllib.parse import quote

from conftest import api, login, make_user
from test_p3_trading import setup_env
from test_p6_settlement import setup_to_n5, allocate, get_alloc_id
from test_p4_logistics import _mk as mk_partner


def dstr(days):
    """距今天数后的日期字符串 YYYY-MM-DD"""
    return (datetime.now() + timedelta(days=days)).strftime('%Y-%m-%d')


def db_conn():
    from backend import db
    return sqlite3.connect(db.DB_PATH)


def mk_rule(client, token, **over):
    """创建扣水扣杂规则，返回 rule_id"""
    body = {'rule_name': '水分扣减', 'ore_category': 'IRON', 'index_name': '水分',
            'threshold': 8, 'deduct_rate': 5}
    body.update(over)
    code, resp = api(client, 'POST', '/api/inspect/rule/save', token, json_body=body)
    assert code == 200, resp
    return resp['data']['rule_id']


def mk_inspect(client, token, submit=True, **over):
    """创建化验单（可提交），返回详情 data"""
    body = {'indexes': [{'index_name': '水分', 'index_value': '8', 'index_unit': '%'}]}
    body.update(over)
    body['submit'] = submit
    code, resp = api(client, 'POST', '/api/inspect/report/save', token, json_body=body)
    assert code == 200, resp
    return resp['data']


# ================= PRD-09 质检化验 =================

def test_deduct_rule_crud_and_permission(client):
    """扣水扣杂规则：参数校验/R4专属保存/启停切换"""
    env = setup_env(client)
    r4 = env['admin']
    # R2 无权保存规则
    code, _ = api(client, 'POST', '/api/inspect/rule/save', env['ra'], json_body={
        'rule_name': 'x', 'ore_category': 'IRON', 'index_name': '水分', 'threshold': 8, 'deduct_rate': 5})
    assert code == 403
    # 缺必填
    code, body = api(client, 'POST', '/api/inspect/rule/save', r4, json_body={'rule_name': '缺品类'})
    assert code == 400 and '必填' in body['message']
    # 非数字阈值
    code, body = api(client, 'POST', '/api/inspect/rule/save', r4, json_body={
        'rule_name': '水分扣减', 'ore_category': 'IRON', 'index_name': '水分',
        'threshold': 'abc', 'deduct_rate': 5})
    assert code == 400 and '必须为数字' in body['message']
    # 负数
    code, body = api(client, 'POST', '/api/inspect/rule/save', r4, json_body={
        'rule_name': '水分扣减', 'ore_category': 'IRON', 'index_name': '水分',
        'threshold': -1, 'deduct_rate': 5})
    assert code == 400 and '必须大于0' in body['message']
    # 扣减比例超100%
    code, body = api(client, 'POST', '/api/inspect/rule/save', r4, json_body={
        'rule_name': '水分扣减', 'ore_category': 'IRON', 'index_name': '水分',
        'threshold': 8, 'deduct_rate': 150})
    assert code == 400 and '不可超过100%' in body['message']
    # 正常创建
    rid = mk_rule(client, r4)
    assert isinstance(rid, int)
    # 列表：R2/R3/R4 可见，R1 无权
    _, body = api(client, 'GET', '/api/inspect/rule/list', env['ra'])
    assert body['data']['total'] == 1
    code, _ = api(client, 'GET', '/api/inspect/rule/list', env['r1'])
    assert code == 403
    # toggle 启停（返回键为 status）
    code, body = api(client, 'POST', f'/api/inspect/rule/{rid}/toggle', r4)
    assert code == 200 and body['data']['status'] == 0
    code, body = api(client, 'POST', f'/api/inspect/rule/{rid}/toggle', r4)
    assert code == 200 and body['data']['status'] == 1


def test_inspect_lifecycle_and_deduct_calc(client):
    """化验单全生命周期：草稿→扣减计算→提交→驳回→重报→通过→待办办结→导出"""
    env = setup_env(client)
    r4 = env['admin']
    mk_rule(client, r4)  # IRON 水分≥8 扣5%
    rtok, _ = mk_partner(client, '化验机构甲')
    # R3 不能创建货源预检单
    code, body = api(client, 'POST', '/api/inspect/report/save', rtok, json_body={
        'report_type': 1, 'source_id': env['res_a']})
    assert code == 400 and '仅限供方或平台' in body['message']
    # R2 只能为自有货源创建
    code, body = api(client, 'POST', '/api/inspect/report/save', env['rb'], json_body={
        'report_type': 1, 'source_id': env['res_a']})
    assert code == 403 and '只能为自有货源' in body['message']
    # R2 缺货源关联
    code, body = api(client, 'POST', '/api/inspect/report/save', env['ra'], json_body={'report_type': 1})
    assert code == 400 and '必须关联货源' in body['message']
    code, body = api(client, 'POST', '/api/inspect/report/save', env['ra'], json_body={
        'report_type': 1, 'source_id': 99999})
    assert code == 404 and '不存在' in body['message']
    # 创建草稿（不带湿基吨数）
    data = mk_inspect(client, env['ra'], submit=False, report_type=1, source_id=env['res_a'],
                      inspect_org='矿山化验室',
                      indexes=[{'index_name': 'TFe', 'index_value': '63.2', 'index_unit': '%'}])
    rid = data['report_id']
    assert data['report_no'].startswith('IR') and data['status'] == 'DRAFT'
    assert len(data['indexes']) == 1
    # 编辑带湿基吨数 → 自动扣减（水分10 ≥ 阈值8 → 扣 1000×5% = 50，结算 950）
    data = mk_inspect(client, env['ra'], submit=False, report_id=rid, report_type=1,
                      source_id=env['res_a'], wet_ton=1000,
                      indexes=[{'index_name': '水分', 'index_value': '10', 'index_unit': '%'}])
    assert data['deduct_ton'] == 50.0 and data['settle_ton'] == 950.0
    # 再次编辑不带湿基吨数 → 保留上次扣减/结算结果
    data = mk_inspect(client, env['ra'], submit=False, report_id=rid, report_type=1,
                      source_id=env['res_a'], conclusion='初检合格')
    assert data['deduct_ton'] == 50.0 and data['settle_ton'] == 950.0
    # R1 看不到货源预检单
    _, body = api(client, 'GET', '/api/inspect/report/list', env['r1'])
    assert body['data']['total'] == 0
    # 提交 → R4 待办
    data = mk_inspect(client, env['ra'], submit=True, report_id=rid, report_type=1,
                      source_id=env['res_a'], wet_ton=1000)
    assert data['status'] == 'PENDING'
    # 待审核状态禁止编辑
    code, body = api(client, 'POST', '/api/inspect/report/save', env['ra'], json_body={
        'report_id': rid, 'report_type': 1, 'source_id': env['res_a']})
    assert code == 400 and '禁止修改' in body['message']
    _, body = api(client, 'GET', '/api/message/unread-count', r4)
    assert body['data']['count'] >= 1
    # R1 无权审核
    code, _ = api(client, 'POST', '/api/inspect/report/audit', env['r1'], json_body={
        'report_id': rid, 'result': 'APPROVED'})
    assert code == 403
    # 驳回必须填原因（字段为 reject_reason）
    code, body = api(client, 'POST', '/api/inspect/report/audit', r4, json_body={
        'report_id': rid, 'result': 'REJECTED'})
    assert code == 400 and '驳回必须填写原因' in body['message']
    code, body = api(client, 'POST', '/api/inspect/report/audit', r4, json_body={
        'report_id': rid, 'result': 'REJECTED', 'reject_reason': '水分指标数据存疑，请复核'})
    assert code == 200 and body['data']['status'] == 'REJECTED'
    # 创建人收到驳回通知
    _, body = api(client, 'GET', '/api/message/list?msg_type=2', env['ra'])
    assert any('驳回' in m['title'] for m in body['data']['list'])
    # 驳回后可编辑重报
    data = mk_inspect(client, env['ra'], submit=True, report_id=rid, report_type=1,
                      source_id=env['res_a'], wet_ton=1000,
                      indexes=[{'index_name': '水分', 'index_value': '9.2', 'index_unit': '%'}])
    assert data['status'] == 'PENDING'
    code, body = api(client, 'POST', '/api/inspect/report/audit', r4, json_body={
        'report_id': rid, 'result': 'APPROVED'})
    assert code == 200
    # 详情可查，待办自动办结
    _, body = api(client, 'GET', f'/api/inspect/report/detail?report_id={rid}', r4)
    assert body['data']['status'] == 'APPROVED'
    _, body = api(client, 'GET', '/api/message/list?msg_type=1', r4)
    assert all(m['is_finish'] == 1 for m in body['data']['list'])
    # 台账导出 xlsx
    code, data = api(client, 'GET', '/api/inspect/report/export', r4)
    assert code == 200 and data[:2] == b'PK'


def test_inspect_types_links_and_isolation(client):
    """四类化验单关联校验 + 四角色数据隔离与越权拦截"""
    env = setup_to_n5(client)
    r4 = env['admin']
    code, _ = allocate(client, env)
    assert code == 200
    aid = get_alloc_id(client, env)
    rtok, _ = mk_partner(client, '化验机构乙')
    rtok2, _ = mk_partner(client, '化验机构丙')
    # R2 不能录船检/仓检/出库检
    code, body = api(client, 'POST', '/api/inspect/report/save', env['ra'], json_body={
        'report_type': 2, 'order_id': env['order_id']})
    assert code == 400 and '仅限化验机构或平台' in body['message']
    # 船检必须关联总订单
    code, body = api(client, 'POST', '/api/inspect/report/save', rtok, json_body={'report_type': 2})
    assert code == 400 and '必须关联集采总订单' in body['message']
    code, body = api(client, 'POST', '/api/inspect/report/save', rtok, json_body={
        'report_type': 2, 'order_id': 99999})
    assert code == 404 and '不存在' in body['message']
    # 船检创建+提交+通过
    data = mk_inspect(client, rtok, report_type=2, order_id=env['order_id'],
                      wet_ton=1000, vessel_no='SEA001')
    ship_rid = data['report_id']
    code, body = api(client, 'POST', '/api/inspect/report/audit', r4, json_body={
        'report_id': ship_rid, 'result': 'APPROVED'})
    assert code == 200
    # 出库检必须关联分拨单
    code, body = api(client, 'POST', '/api/inspect/report/save', rtok, json_body={'report_type': 4})
    assert code == 400 and '必须关联分拨单' in body['message']
    code, body = api(client, 'POST', '/api/inspect/report/save', rtok, json_body={
        'report_type': 4, 'alloc_id': 99999})
    assert code == 404 and '不存在' in body['message']
    # 出库检创建+提交+通过
    data = mk_inspect(client, rtok, report_type=4, alloc_id=aid, wet_ton=990)
    out_rid = data['report_id']
    code, body = api(client, 'POST', '/api/inspect/report/audit', r4, json_body={
        'report_id': out_rid, 'result': 'APPROVED'})
    assert code == 200
    # 列表隔离：R1 仅见自己分拨单的化验单（出库检），不见船检
    _, body = api(client, 'GET', '/api/inspect/report/list', env['r1'])
    ids = [r['report_id'] for r in body['data']['list']]
    assert out_rid in ids and ship_rid not in ids
    # R2（供方）见自己订单的船检，不见下游出库检
    _, body = api(client, 'GET', '/api/inspect/report/list', env['ra'])
    ids = [r['report_id'] for r in body['data']['list']]
    assert ship_rid in ids and out_rid not in ids
    # R3 见自己录入的
    _, body = api(client, 'GET', '/api/inspect/report/list', rtok)
    ids = [r['report_id'] for r in body['data']['list']]
    assert ship_rid in ids and out_rid in ids
    # 详情越权：无关供方 403
    code, body = api(client, 'GET', f'/api/inspect/report/detail?report_id={ship_rid}', env['rb'])
    assert code == 403 and '无权查看' in body['message']
    # 详情越权：无关配套方 403
    code, body = api(client, 'GET', f'/api/inspect/report/detail?report_id={out_rid}', rtok2)
    assert code == 403
    # 属主可看：R3 创建者 + R1 分拨属主
    code, _ = api(client, 'GET', f'/api/inspect/report/detail?report_id={out_rid}', rtok)
    assert code == 200
    code, _ = api(client, 'GET', f'/api/inspect/report/detail?report_id={out_rid}', env['r1'])
    assert code == 200


# ================= PRD-10 合同管理 =================

def test_contract_lifecycle(client):
    """合同生命周期：校验/状态机全链/编辑锁/盖章生效/终止原因/相对方通知/导出"""
    env = setup_to_n5(client)
    r4 = env['admin']
    code, _ = allocate(client, env)
    assert code == 200
    aid = get_alloc_id(client, env)
    # 校验：类型关联缺失/不存在/金额非法/日期格式
    code, body = api(client, 'POST', '/api/contract/save', r4, json_body={'contract_type': 1})
    assert code == 400 and '必须关联集采总订单' in body['message']
    code, body = api(client, 'POST', '/api/contract/save', r4, json_body={
        'contract_type': 2, 'alloc_id': 99999})
    assert code == 404 and '不存在' in body['message']
    code, body = api(client, 'POST', '/api/contract/save', r4, json_body={
        'contract_type': 1, 'order_id': env['order_id'], 'plan_ton': 'x'})
    assert code == 400 and '必须为数字' in body['message']
    code, body = api(client, 'POST', '/api/contract/save', r4, json_body={
        'contract_type': 1, 'order_id': env['order_id'], 'plan_ton': -5})
    assert code == 400 and '必须大于0' in body['message']
    code, body = api(client, 'POST', '/api/contract/save', r4, json_body={
        'contract_type': 1, 'order_id': env['order_id'], 'sign_date': '2026/01/01'})
    assert code == 400 and 'YYYY-MM-DD' in body['message']
    # 上游供货合同：enterprise 自动取订单供方矿山A
    code, body = api(client, 'POST', '/api/contract/save', r4, json_body={
        'contract_type': 1, 'order_id': env['order_id'], 'plan_ton': 1000, 'unit_price': 650,
        'contract_amount': 650000, 'sign_date': dstr(-1), 'effective_date': dstr(0),
        'expire_date': dstr(30),
        'attachments': [{'file_url': '/api/files/ht.pdf', 'file_name': '合同扫描件.pdf'}]})
    assert code == 200, body
    up = body['data']
    assert up['contract_no'].startswith('HT') and up['status'] == 'DRAFT'
    assert up['enterprise_id'] == env['cid_a'] and up['enterprise_name'] == '交易矿山A'
    assert len(up['attachments']) == 1
    # 下游分拨合同：enterprise 自动取分拨单企业
    code, body = api(client, 'POST', '/api/contract/save', r4, json_body={
        'contract_type': 2, 'alloc_id': aid, 'plan_ton': 1000, 'unit_price': 655,
        'contract_amount': 655000, 'expire_date': dstr(60)})
    assert code == 200, body
    down = body['data']
    assert down['enterprise_id'] == env['c1'] and down['contract_type_name'] == '下游分拨合同'
    # 可见性：R1 仅 type2 / R2 仅 type1 / 无关供方空 / R3 无权
    _, body = api(client, 'GET', '/api/contract/list', env['r1'])
    assert [c['contract_type'] for c in body['data']['list']] == [2]
    _, body = api(client, 'GET', '/api/contract/list', env['ra'])
    assert [c['contract_type'] for c in body['data']['list']] == [1]
    _, body = api(client, 'GET', '/api/contract/list', env['rb'])
    assert body['data']['total'] == 0
    code, _ = api(client, 'GET', '/api/contract/list', env['ptok'])
    assert code == 403
    # 非法流转：草稿直跳生效
    code, body = api(client, 'POST', '/api/contract/status/update', r4, json_body={
        'contract_id': down['contract_id'], 'status': 'EFFECTIVE'})
    assert code == 400 and '不允许从 草稿 变更为' in body['message']
    # R1 无权推进状态
    code, _ = api(client, 'POST', '/api/contract/status/update', env['r1'], json_body={
        'contract_id': down['contract_id'], 'status': 'PENDING_STAMP'})
    assert code == 403
    # 草稿 → 待盖章 → 生效（缺盖章编号被拦）
    code, body = api(client, 'POST', '/api/contract/status/update', r4, json_body={
        'contract_id': down['contract_id'], 'status': 'PENDING_STAMP'})
    assert code == 200
    code, body = api(client, 'POST', '/api/contract/status/update', r4, json_body={
        'contract_id': down['contract_id'], 'status': 'EFFECTIVE'})
    assert code == 400 and '盖章编号' in body['message']
    code, body = api(client, 'POST', '/api/contract/status/update', r4, json_body={
        'contract_id': down['contract_id'], 'status': 'EFFECTIVE',
        'stamp_no': 'STAMP-001', 'effective_date': dstr(0)})
    assert code == 200 and body['data']['status'] == 'EFFECTIVE'
    # 已生效合同禁止直接编辑
    code, body = api(client, 'POST', '/api/contract/save', r4, json_body={
        'contract_id': down['contract_id'], 'contract_type': 2, 'alloc_id': aid, 'plan_ton': 1})
    assert code == 400 and '仅草稿状态合同可编辑' in body['message']
    # 相对方（下游企业）收到状态更新通知
    _, body = api(client, 'GET', '/api/message/list', env['r1'])
    assert any('合同状态更新' in m['title'] for m in body['data']['list'])
    # 履约中 → 终止必须填原因
    code, body = api(client, 'POST', '/api/contract/status/update', r4, json_body={
        'contract_id': down['contract_id'], 'status': 'EXECUTING'})
    assert code == 200
    code, body = api(client, 'POST', '/api/contract/status/update', r4, json_body={
        'contract_id': down['contract_id'], 'status': 'TERMINATED'})
    assert code == 400 and '终止必须填写终止原因' in body['message']
    code, body = api(client, 'POST', '/api/contract/status/update', r4, json_body={
        'contract_id': down['contract_id'], 'status': 'TERMINATED',
        'terminate_reason': '需方产能调整，双方协商一致终止'})
    assert code == 200
    # 详情状态名 + R1 越权查看上游合同被拦
    _, body = api(client, 'GET', f"/api/contract/detail?contract_id={down['contract_id']}", env['r1'])
    assert body['data']['status_name'] == '已终止'
    code, body = api(client, 'GET', f"/api/contract/detail?contract_id={up['contract_id']}", env['r1'])
    assert code == 403
    # 草稿可编辑（up 仍为 DRAFT）
    code, body = api(client, 'POST', '/api/contract/save', r4, json_body={
        'contract_id': up['contract_id'], 'contract_type': 1, 'order_id': env['order_id'],
        'plan_ton': 1100, 'unit_price': 650, 'contract_amount': 715000})
    assert code == 200 and body['data']['plan_ton'] == 1100.0
    # 台账导出
    code, data = api(client, 'GET', '/api/contract/export', r4)
    assert code == 200 and data[:2] == b'PK'


def test_contract_change_and_visibility(client):
    """合同变更记录：R2/R4 发起权限/越权拦截/补充协议附件同步/通知"""
    env = setup_to_n5(client)
    r4 = env['admin']
    code, _ = allocate(client, env)
    assert code == 200
    aid = get_alloc_id(client, env)
    _, body = api(client, 'POST', '/api/contract/save', r4, json_body={
        'contract_type': 2, 'alloc_id': aid, 'plan_ton': 1000, 'unit_price': 655,
        'contract_amount': 655000})
    down = body['data']
    _, body = api(client, 'POST', '/api/contract/save', r4, json_body={
        'contract_type': 1, 'order_id': env['order_id']})
    up = body['data']
    # R1 无权发起变更
    code, _ = api(client, 'POST', '/api/contract/change/add', env['r1'], json_body={
        'contract_id': down['contract_id'], 'change_content': '单价上调'})
    assert code == 403
    # R2 对下游合同越权（R2 仅可见 type1）
    code, body = api(client, 'POST', '/api/contract/change/add', env['ra'], json_body={
        'contract_id': down['contract_id'], 'change_content': '单价上调'})
    assert code == 403 and '无权操作该合同' in body['message']
    # 内容必填
    code, body = api(client, 'POST', '/api/contract/change/add', r4, json_body={
        'contract_id': down['contract_id']})
    assert code == 400 and '变更内容必填' in body['message']
    # R4 变更 + 补充协议附件同步附件表
    code, body = api(client, 'POST', '/api/contract/change/add', r4, json_body={
        'contract_id': down['contract_id'], 'change_content': '单价由655调整为660',
        'reason': '市场行情上涨', 'attachment_url': '/api/files/supp.pdf', 'file_name': '补充协议.pdf'})
    assert code == 200, body
    # R2 以订单供方身份变更上游合同
    code, body = api(client, 'POST', '/api/contract/change/add', env['ra'], json_body={
        'contract_id': up['contract_id'], 'change_content': '吨数由1000调整为1100'})
    assert code == 200, body
    # 详情：changes 记录 + CHANGE 类型附件
    _, body = api(client, 'GET', f"/api/contract/detail?contract_id={down['contract_id']}", env['r1'])
    assert len(body['data']['changes']) == 1
    assert any(a['attach_type'] == 'CHANGE' for a in body['data']['attachments'])
    # R4 收到变更待关注待办
    _, body = api(client, 'GET', '/api/message/list', r4)
    assert any('合同变更' in m['title'] for m in body['data']['list'])
    # 导出
    code, data = api(client, 'GET', '/api/contract/export', env['r1'])
    assert code == 200 and data[:2] == b'PK'


# ================= PRD-11 费用分摊 =================

def mk_bill(client, r4, order_id, etype='SEA', amount=10000, **over):
    body = {'order_id': order_id, 'expense_type': etype, 'expense_amount': amount,
            'payee': '测试收款方', 'happen_date': dstr(0)}
    body.update(over)
    code, resp = api(client, 'POST', '/api/expense/bill/save', r4, json_body=body)
    assert code == 200, resp
    return resp['data']


def approve_ship_report(client, r4, order_id, wet_ton=1000):
    """创建并审核通过到港船检化验单，返回 report_id"""
    rtok, _ = mk_partner(client, '船检机构')
    data = mk_inspect(client, rtok, report_type=2, order_id=order_id, wet_ton=wet_ton)
    code, body = api(client, 'POST', '/api/inspect/report/audit', r4, json_body={
        'report_id': data['report_id'], 'result': 'APPROVED'})
    assert code == 200, body
    return data['report_id']


def test_expense_bill_crud(client):
    """费用单：R4专属/校验/单号/列表筛选/删除"""
    env = setup_to_n5(client)
    r4 = env['admin']
    # R1 无权
    code, _ = api(client, 'POST', '/api/expense/bill/save', env['r1'], json_body={
        'order_id': env['order_id'], 'expense_type': 'SEA', 'expense_amount': 100})
    assert code == 403
    # 校验链
    code, body = api(client, 'POST', '/api/expense/bill/save', r4, json_body={'expense_type': 'SEA'})
    assert code == 400 and '必须关联集采总订单' in body['message']
    code, body = api(client, 'POST', '/api/expense/bill/save', r4, json_body={'order_id': env['order_id']})
    assert code == 400 and '费用类型必填' in body['message']
    code, body = api(client, 'POST', '/api/expense/bill/save', r4, json_body={
        'order_id': env['order_id'], 'expense_type': 'SEA', 'expense_amount': 'abc'})
    assert code == 400 and '必须为数字' in body['message']
    code, body = api(client, 'POST', '/api/expense/bill/save', r4, json_body={
        'order_id': env['order_id'], 'expense_type': 'SEA', 'expense_amount': 0})
    assert code == 400 and '必须大于0' in body['message']
    # 正常创建
    bill = mk_bill(client, r4, env['order_id'])
    assert bill['expense_no'].startswith('EX') and bill['allocated_count'] == 0
    # 列表筛选
    _, body = api(client, 'GET', f"/api/expense/bill/list?order_id={env['order_id']}", r4)
    assert body['data']['total'] == 1
    _, body = api(client, 'GET', f"/api/expense/bill/list?order_id={env['order_id']}"
                                f"&expense_type={quote('港杂费')}", r4)
    assert body['data']['total'] == 0
    # 删除 + 重复删除 404
    code, _ = api(client, 'POST', f"/api/expense/bill/{bill['expense_id']}/delete", r4)
    assert code == 200
    code, body = api(client, 'POST', f"/api/expense/bill/{bill['expense_id']}/delete", r4)
    assert code == 404 and '不存在' in body['message']


def test_expense_share_run_revoke_and_detail(client):
    """费用分摊：船检前置/执行/明细核算/越权403/重复分摊拦截/撤销重跑/通知"""
    env = setup_to_n5(client)
    r4 = env['admin']
    code, _ = allocate(client, env)
    assert code == 200
    aid = get_alloc_id(client, env)
    # 无审核通过船检 → 拦截
    code, body = api(client, 'POST', '/api/expense/share/run', r4, json_body={'order_id': env['order_id']})
    assert code == 400 and '尚无审核通过的到港船检化验单' in body['message']
    approve_ship_report(client, r4, env['order_id'])
    # 无待分摊费用 → 拦截
    code, body = api(client, 'POST', '/api/expense/share/run', r4, json_body={'order_id': env['order_id']})
    assert code == 400 and '没有待分摊的费用单' in body['message']
    # 创建费用单并执行分摊（权重 1000t → 全额归一张分拨单）
    bill = mk_bill(client, r4, env['order_id'], 'SEA', 10000)
    code, body = api(client, 'POST', '/api/expense/share/run', r4, json_body={'order_id': env['order_id']})
    assert code == 200, body
    assert body['data'] == {'allocated_rows': 1, 'bills': 1, 'alloc_orders': 1}
    # 下游企业收到分摊通知
    _, body = api(client, 'GET', '/api/message/list', env['r1'])
    assert any('分项结算明细' in m['title'] for m in body['data']['list'])
    # R4 订单视图明细：杂费汇总 10000（订单视图无单一分拨上下文，alloc 为空）
    _, body = api(client, 'GET', f'/api/expense/share/detail?order_id={env["order_id"]}', r4)
    d = body['data']
    assert d['alloc'] is None and d['expense_total'] == 10000.0
    assert d['details'][0]['share_amount'] == 10000.0
    assert d['details'][0]['share_ton'] == 1000.0
    # R1 明细（分拨视图）：货款 655×1000=655000 + 杂费 10000 = 665000
    _, body = api(client, 'GET', f'/api/expense/share/detail?alloc_id={aid}', env['r1'])
    assert body['data']['alloc']['ore_amount'] == 655000.0
    assert body['data']['total_payable'] == 665000.0
    # R1 明细：不带 alloc_id → 提示
    code, body = api(client, 'GET', '/api/expense/share/detail', env['r1'])
    assert code == 400 and '请选择分拨单' in body['message']
    _, body = api(client, 'GET', f'/api/expense/share/detail?alloc_id={aid}', env['r1'])
    assert body['data']['total_payable'] == 665000.0
    # R1 越权查看他人分拨单 → 403
    r1b, _ = make_user(client, '越权钢厂')
    code, body = api(client, 'GET', f'/api/expense/share/detail?alloc_id={aid}', r1b)
    assert code == 403 and '无权查看该分拨单' in body['message']
    # 已分摊费用单不可删除
    code, body = api(client, 'POST', f"/api/expense/bill/{bill['expense_id']}/delete", r4)
    assert code == 400 and '已执行分摊' in body['message']
    # 已分摊费用重复分摊 → 无待分摊
    code, body = api(client, 'POST', '/api/expense/share/run', r4, json_body={'order_id': env['order_id']})
    assert code == 400 and '没有待分摊的费用单' in body['message']
    # 追加费用后可再次分摊
    mk_bill(client, r4, env['order_id'], 'PORT', 2000)
    code, body = api(client, 'POST', '/api/expense/share/run', r4, json_body={'order_id': env['order_id']})
    assert code == 200 and body['data']['bills'] == 1
    # 撤销 → 再撤销无记录
    code, body = api(client, 'POST', '/api/expense/share/revoke', r4, json_body={'order_id': env['order_id']})
    assert code == 200 and body['data']['revoked'] == 2
    code, body = api(client, 'POST', '/api/expense/share/revoke', r4, json_body={'order_id': env['order_id']})
    assert code == 400 and '没有可撤销的分摊记录' in body['message']
    # 撤销后明细为空
    _, body = api(client, 'GET', f'/api/expense/share/detail?alloc_id={aid}', env['r1'])
    assert body['data']['details'] == [] and body['data']['expense_total'] == 0.0
    # 撤销后费用单可删除
    code, _ = api(client, 'POST', f"/api/expense/bill/{bill['expense_id']}/delete", r4)
    assert code == 200
    # 台账导出
    code, data = api(client, 'GET', '/api/expense/bill/export', r4)
    assert code == 200 and data[:2] == b'PK'


def test_expense_weight_priority_and_tail(client):
    """分摊权重：出库检结算吨数优先于分拨吨数；最后一单兜尾差保证金额守恒"""
    env = setup_to_n5(client)
    r4 = env['admin']
    # 两张分拨单：700 + 300
    code, body = allocate(client, env, allocs=[
        {'company_id': env['c1'], 'qty': 700, 'unit_price': 655, 'destination': '交易钢厂料场'},
        {'company_id': env['c1'], 'qty': 300, 'unit_price': 655, 'destination': '交易钢厂料场'}])
    assert code == 200, body
    aid1, aid2 = [r['alloc_id'] for r in body['data']['list']]
    approve_ship_report(client, r4, env['order_id'])
    # 第一张分拨单的出库检结算吨数 600（低于分拨吨数700 → 优先采用 600）
    rtok, _ = mk_partner(client, '出库检机构')
    data = mk_inspect(client, rtok, report_type=4, alloc_id=aid1, wet_ton=600)
    code, body = api(client, 'POST', '/api/inspect/report/audit', r4, json_body={
        'report_id': data['report_id'], 'result': 'APPROVED'})
    assert code == 200
    mk_bill(client, r4, env['order_id'], 'SEA', 10000)
    code, body = api(client, 'POST', '/api/expense/share/run', r4, json_body={'order_id': env['order_id']})
    assert code == 200, body
    assert body['data']['alloc_orders'] == 2
    # 权重 600/300，总 900：600/900×10000=6666.67，尾差归最后一单 3333.33
    _, body = api(client, 'GET', f'/api/expense/share/detail?alloc_id={aid1}', env['r1'])
    assert body['data']['details'][0]['share_amount'] == 6666.67
    _, body = api(client, 'GET', f'/api/expense/share/detail?alloc_id={aid2}', env['r1'])
    assert body['data']['details'][0]['share_amount'] == 3333.33
    # 两单合计 = 10000 金额守恒
    total = round(6666.67 + 3333.33, 2)
    assert total == 10000.0


# ================= PRD-12 消息中心 & 预警 =================

def test_message_center(client):
    """消息中心：角标/筛选/已读/待办办结/全部已读"""
    env = setup_env(client)
    r4 = env['admin']
    ra = env['ra']
    # 提交一张预检单 → R4 待办
    data = mk_inspect(client, ra, submit=True, report_type=1, source_id=env['res_a'], wet_ton=1000)
    rid = data['report_id']
    _, body = api(client, 'GET', '/api/message/unread-count', r4)
    assert body['data']['count'] >= 1
    # 筛选待办
    _, body = api(client, 'GET', '/api/message/list?msg_type=1&is_read=0', r4)
    todos = body['data']['list']
    assert len(todos) >= 1 and todos[0]['msg_type_name'] == '待办'
    mid = todos[0]['msg_id']
    # 标记单条已读 → 角标减少
    code, _ = api(client, 'POST', f'/api/message/{mid}/read', r4)
    assert code == 200
    _, body = api(client, 'GET', '/api/message/unread-count', r4)
    assert body['data']['count'] == 0
    # 缺业务标识 → 拦截
    code, body = api(client, 'POST', '/api/message/finish', r4, json_body={})
    assert code == 400 and '缺少业务单据标识' in body['message']
    # 待办办结：按 link_biz_type + biz_id（INSPECT + report_id）
    code, body = api(client, 'POST', '/api/message/finish', r4, json_body={
        'link_biz_type': 'INSPECT', 'biz_id': rid})
    assert code == 200 and body['data']['finished'] == 1
    # 已办结不重复计数
    code, body = api(client, 'POST', '/api/message/finish', r4, json_body={
        'link_biz_type': 'INSPECT', 'biz_id': rid})
    assert code == 200 and body['data']['finished'] == 0
    # 再造一条通知 → 查看详情即已读
    code, _ = api(client, 'POST', '/api/inspect/report/audit', r4, json_body={
        'report_id': rid, 'result': 'APPROVED'})
    assert code == 200
    _, body = api(client, 'GET', '/api/message/list?is_read=0', ra)
    nid = body['data']['list'][0]['msg_id']
    code, body = api(client, 'GET', f'/api/message/{nid}', ra)
    assert code == 200 and body['data']['is_read'] == 1
    # 不存在的消息 404
    code, body = api(client, 'GET', '/api/message/999999', ra)
    assert code == 404
    # read-all
    code, _ = api(client, 'POST', '/api/message/read-all', ra)
    assert code == 200
    _, body = api(client, 'GET', '/api/message/unread-count', ra)
    assert body['data']['count'] == 0


def test_warn_rules_and_scan(client):
    """预警规则配置 + 四类预警扫描触发 + 当日去重 + 停用拦截"""
    env = setup_to_n5(client)
    r4 = env['admin']
    ra = env['ra']
    # R2 无权访问预警规则
    code, _ = api(client, 'GET', '/api/warn/rule/list', ra)
    assert code == 403
    # 校验链
    code, body = api(client, 'POST', '/api/warn/rule/save', r4, json_body={})
    assert code == 400 and '规则名称必填' in body['message']
    code, body = api(client, 'POST', '/api/warn/rule/save', r4, json_body={
        'rule_name': 'x', 'warn_type': 'BAD'})
    assert code == 400 and '无效的预警类型' in body['message']
    code, body = api(client, 'POST', '/api/warn/rule/save', r4, json_body={
        'rule_name': 'x', 'warn_type': 'CONTRACT_EXPIRE', 'threshold': 'abc'})
    assert code == 400 and '必须为数字' in body['message']
    code, body = api(client, 'POST', '/api/warn/rule/save', r4, json_body={
        'rule_name': 'x', 'warn_type': 'CONTRACT_EXPIRE', 'threshold': 0})
    assert code == 400 and '必须大于0' in body['message']
    # 四条规则：合同15天/价格5%/物流10天/货源10天
    for wtype, th in [('CONTRACT_EXPIRE', 15), ('PRICE_CHANGE', 5),
                      ('LOGI_STALE', 10), ('RESOURCE_EXPIRE', 10)]:
        code, body = api(client, 'POST', '/api/warn/rule/save', r4, json_body={
            'rule_name': wtype, 'warn_type': wtype, 'threshold': th})
        assert code == 200, body
    _, body = api(client, 'GET', '/api/warn/rule/list', r4)
    assert body['data']['total'] == 4
    rule_id = body['data']['list'][0]['rule_id']
    # 初始扫描无预警
    code, body = api(client, 'POST', '/api/warn/scan', r4)
    assert code == 200 and body['data']['total'] == 0
    # —— 1. 合同到期：生效合同 10 天后到期 → 触发
    code, _ = allocate(client, env)
    assert code == 200
    aid = get_alloc_id(client, env)
    _, body = api(client, 'POST', '/api/contract/save', r4, json_body={
        'contract_type': 2, 'alloc_id': aid, 'plan_ton': 1000, 'unit_price': 655,
        'contract_amount': 655000, 'expire_date': dstr(10)})
    cid = body['data']['contract_id']
    api(client, 'POST', '/api/contract/status/update', r4, json_body={
        'contract_id': cid, 'status': 'PENDING_STAMP'})
    api(client, 'POST', '/api/contract/status/update', r4, json_body={
        'contract_id': cid, 'status': 'EFFECTIVE', 'stamp_no': 'STAMP-9', 'effective_date': dstr(0)})
    code, body = api(client, 'POST', '/api/warn/scan', r4)
    assert body['data']['generated']['CONTRACT_EXPIRE'] == 1
    # 当日去重：再次扫描不重复
    code, body = api(client, 'POST', '/api/warn/scan', r4)
    assert body['data']['generated']['CONTRACT_EXPIRE'] == 0
    # —— 2. 价格异动：最新两条 640 → 700（+9.4% ≥ 5%）→ 触发
    api(client, 'POST', '/api/admin/price/create', r4, json_body={
        'ore_category': 'IRON', 'spec': 'TFe 62%', 'quote_date': dstr(-1), 'market_price': 640})
    api(client, 'POST', '/api/admin/price/create', r4, json_body={
        'ore_category': 'IRON', 'spec': 'TFe 62%', 'quote_date': dstr(0), 'market_price': 700})
    code, body = api(client, 'POST', '/api/warn/scan', r4)
    assert body['data']['generated']['PRICE_CHANGE'] == 1
    # —— 3. 物流超时：任务停在 N5，回填最后完成节点为 11 天前 → 触发
    conn = db_conn()
    conn.execute("UPDATE logistics_node SET done_time=? WHERE logi_id=? AND status='DONE'",
                 ((datetime.now() - timedelta(days=11)).strftime('%Y-%m-%d %H:%M:%S'), env['lid']))
    conn.commit()
    conn.close()
    code, body = api(client, 'POST', '/api/warn/scan', r4)
    assert body['data']['generated']['LOGI_STALE'] == 1
    # —— 4. 货源周期：上架货源 8 天后到期 → 触发
    _, body = api(client, 'POST', '/api/resource/create', ra, json_body={
        'ore_category': 'IRON', 'origin': '河北承德', 'grade': 'TFe 63%', 'max_qty': 500,
        'supply_period': f'{dstr(0)} ~ {dstr(8)}', 'action': 'submit'})
    assert code == 200, body
    code, body = api(client, 'POST', '/api/warn/scan', r4)
    assert body['data']['generated']['RESOURCE_EXPIRE'] == 1
    # R4 收到预警消息（msg_type=3）
    _, body = api(client, 'GET', '/api/message/list?msg_type=3', r4)
    titles = [m['title'] for m in body['data']['list']]
    assert any('合同到期' in t for t in titles)
    assert any('价格异动' in t for t in titles)
    assert any('物流超时' in t for t in titles)
    assert any('货源周期' in t for t in titles)
    # 停用合同规则 → 新合同不再触发
    code, body = api(client, 'POST', f'/api/warn/rule/{rule_id}/toggle', r4)
    assert code == 200 and body['data']['enable_status'] == 0
    code, body = api(client, 'POST', '/api/warn/scan', r4)
    assert body['data']['generated']['CONTRACT_EXPIRE'] == 0


# ================= PRD-13 报表 & 大屏 =================

def test_reports_and_dashboard(client):
    """报表角色矩阵 + 响应结构 + 大屏聚合"""
    env = setup_to_n5(client)
    r4 = env['admin']
    code, _ = allocate(client, env)
    assert code == 200
    approve_ship_report(client, r4, env['order_id'])
    mk_bill(client, r4, env['order_id'], 'SEA', 10000)
    code, _ = api(client, 'POST', '/api/expense/share/run', r4, json_body={'order_id': env['order_id']})
    assert code == 200
    api(client, 'POST', '/api/admin/price/create', r4, json_body={
        'ore_category': 'IRON', 'spec': 'TFe 62%', 'quote_date': dstr(0), 'market_price': 650})
    # R4 全报表 200
    for url in ['/api/report/summary', '/api/report/trade', '/api/report/logistics',
                '/api/report/settlement', '/api/report/price-trend', '/api/dashboard/overview']:
        code, body = api(client, 'GET', url, r4)
        assert code == 200, (url, body)
    # 响应结构
    _, body = api(client, 'GET', '/api/report/summary', r4)
    assert set(body['data'].keys()) == {'by_category', 'by_period', 'by_company', 'by_status'}
    assert body['data']['by_category'][0]['ore_category'] == 'IRON'
    _, body = api(client, 'GET', '/api/report/trade', r4)
    assert set(body['data'].keys()) == {'by_month', 'by_category', 'by_supplier'}
    _, body = api(client, 'GET', '/api/report/logistics', r4)
    assert {'stats', 'avg_days', 'finish_rate', 'total'} <= set(body['data'].keys())
    _, body = api(client, 'GET', '/api/report/settlement', r4)
    assert 'by_company' in body['data']
    _, body = api(client, 'GET', '/api/dashboard/overview', r4)
    assert {'cards', 'order_trend', 'alloc_map', 'node_map'} <= set(body['data'].keys())
    # R1：summary/settlement/logistics 可用；trade/price-trend 403
    _, body = api(client, 'GET', '/api/report/summary', env['r1'])
    assert body['data']['by_company'][0]['company_name'] == '交易钢厂'
    code, _ = api(client, 'GET', '/api/report/trade', env['r1'])
    assert code == 403
    code, _ = api(client, 'GET', '/api/report/price-trend', env['r1'])
    assert code == 403
    code, _ = api(client, 'GET', '/api/dashboard/overview', env['r1'])
    assert code == 403
    code, _ = api(client, 'GET', '/api/report/settlement', env['r1'])
    assert code == 200
    # R2：trade 可用；summary 403
    _, body = api(client, 'GET', '/api/report/trade', env['ra'])
    assert body['data']['by_supplier'][0]['total_amount'] == 650000.0
    code, _ = api(client, 'GET', '/api/report/summary', env['ra'])
    assert code == 403
    # R3：仅 logistics 可用
    code, body = api(client, 'GET', '/api/report/logistics', env['ptok'])
    assert code == 200 and body['data']['total'] >= 1
    code, _ = api(client, 'GET', '/api/report/settlement', env['ptok'])
    assert code == 403
    # 时间筛选：未来区间返回空
    _, body = api(client, 'GET', '/api/report/summary?start_date=2099-01-01&end_date=2099-12-31', r4)
    assert body['data']['by_category'] == []


# ================= PRD-14 字典 & 指标模板 =================

def test_dict_guard_and_indicator_unit(client):
    """字典：R4专属/重复拦截/被引用禁删/正常删除/指标模板 unit 字段"""
    env = setup_env(client)
    r4 = env['admin']
    # R2 无权
    code, _ = api(client, 'GET', '/api/admin/dict/list?category=X', env['ra'])
    assert code == 403
    # 缺字段
    code, body = api(client, 'POST', '/api/admin/dict', r4, json_body={'category': 'X'})
    assert code == 400 and '缺少必填字段' in body['message']
    # 创建 + 重复拦截
    code, body = api(client, 'POST', '/api/admin/dict', r4, json_body={
        'category': 'GRADE_LEVEL', 'item_code': 'HIGH', 'item_name': '高品位'})
    assert code == 200, body
    code, body = api(client, 'POST', '/api/admin/dict', r4, json_body={
        'category': 'GRADE_LEVEL', 'item_code': 'HIGH', 'item_name': '高品位2'})
    assert code == 400 and '该字典项已存在' in body['message']
    # 列表
    _, body = api(client, 'GET', '/api/admin/dict/list?category=GRADE_LEVEL', r4)
    assert body['data']['total'] == 1
    did = body['data']['list'][0]['id']
    # 未引用可删除，再删 404
    code, _ = api(client, 'POST', f'/api/admin/dict/{did}/delete', r4)
    assert code == 200
    code, body = api(client, 'POST', f'/api/admin/dict/{did}/delete', r4)
    assert code == 404 and '字典项不存在' in body['message']
    # 被业务引用禁删：品类字典 TESTCAT + 使用该品类的货源
    code, body = api(client, 'POST', '/api/admin/dict', r4, json_body={
        'category': 'ORE_CATEGORY', 'item_code': 'TESTCAT', 'item_name': '测试矿种'})
    assert code == 200
    _, body = api(client, 'GET', '/api/admin/dict/list?category=ORE_CATEGORY', r4)
    did = next(x['id'] for x in body['data']['list'] if x['item_code'] == 'TESTCAT')
    code, body = api(client, 'POST', '/api/resource/create', env['ra'], json_body={
        'ore_category': 'TESTCAT', 'origin': '河北承德', 'grade': 'TFe 60%', 'max_qty': 100,
        'supply_period': '2026-01 ~ 2026-12', 'action': 'submit'})
    assert code == 200, body
    code, body = api(client, 'POST', f'/api/admin/dict/{did}/delete', r4)
    assert code == 400 and '已被业务单据引用' in body['message']
    # 指标模板：校验 + unit 字段
    code, body = api(client, 'POST', '/api/admin/indicator/template', r4, json_body={
        'ore_category': 'TESTCAT'})
    assert code == 400 and '必填' in body['message']
    code, body = api(client, 'POST', '/api/admin/indicator/template', r4, json_body={
        'ore_category': 'TESTCAT', 'field_name': 'moisture', 'field_label': '水分',
        'field_type': 'number', 'required': 1, 'unit': '%', 'sort': 1})
    assert code == 200, body
    # 按品类查询（无鉴权端点，供业务表单驱动）
    code, body = api(client, 'GET', '/api/indicator/template/TESTCAT')
    assert code == 200 and body['data'][0]['unit'] == '%'


# ================= PRD-15 变更 & 红冲 =================

def test_biz_change_flow(client):
    """变更申请：校验/越权/驳回需备注/通过/重复审核/历史轨迹"""
    env = setup_to_n5(client)
    r4 = env['admin']
    code, _ = allocate(client, env)
    assert code == 200
    aid = get_alloc_id(client, env)
    # R4 无权发起（仅 R1/R2）
    code, _ = api(client, 'POST', '/api/biz/change/apply', r4, json_body={
        'biz_type': 'ALLOC', 'biz_id': aid, 'before_content': 'a', 'after_content': 'b'})
    assert code == 403
    # 无效类型 / 单据不存在
    code, body = api(client, 'POST', '/api/biz/change/apply', env['r1'], json_body={
        'biz_type': 'BAD', 'biz_id': 1, 'before_content': 'a', 'after_content': 'b'})
    assert code == 400 and '无效的单据类型' in body['message']
    code, body = api(client, 'POST', '/api/biz/change/apply', env['r1'], json_body={
        'biz_type': 'ALLOC', 'biz_id': 99999, 'before_content': 'a', 'after_content': 'b'})
    assert code == 404 and '不存在' in body['message']
    # 越权：无关企业对分拨单发起变更
    r1b, _ = make_user(client, '越权变更钢厂')
    code, body = api(client, 'POST', '/api/biz/change/apply', r1b, json_body={
        'biz_type': 'ALLOC', 'biz_id': aid, 'before_content': 'a', 'after_content': 'b'})
    assert code == 403 and '无权对该单据发起变更' in body['message']
    # 内容校验
    code, body = api(client, 'POST', '/api/biz/change/apply', env['r1'], json_body={
        'biz_type': 'ALLOC', 'biz_id': aid})
    assert code == 400 and '均必填' in body['message']
    code, body = api(client, 'POST', '/api/biz/change/apply', env['r1'], json_body={
        'biz_type': 'ALLOC', 'biz_id': aid, 'before_content': '数量1000吨',
        'after_content': '数量1000吨'})
    assert code == 400 and '变更前后内容相同' in body['message']
    # R1 对自有分拨单发起变更
    code, body = api(client, 'POST', '/api/biz/change/apply', env['r1'], json_body={
        'biz_type': 'ALLOC', 'biz_id': aid, 'before_content': '数量1000吨',
        'after_content': '数量980吨', 'reason': '到货实测短缺'})
    assert code == 200, body
    change_id = body['data']['change_id']
    # R4 审核列表：enrich 字段
    _, body = api(client, 'GET', '/api/biz/apply/list?kind=change', r4)
    row = body['data']['list'][0]
    assert row['biz_type_name'] == '分拨单' and row['biz_no'].startswith('AL')
    assert row['apply_user'] and row['status'] == 'PENDING'
    # 驳回必须填备注
    code, body = api(client, 'POST', '/api/biz/change/audit', r4, json_body={
        'change_id': change_id, 'result': 'REJECTED'})
    assert code == 400 and '驳回必须填写审核备注' in body['message']
    code, body = api(client, 'POST', '/api/biz/change/audit', r4, json_body={
        'change_id': change_id, 'result': 'REJECTED', 'review_remark': '证据不足'})
    assert code == 200 and body['data']['status'] == 'REJECTED'
    # 重复审核拦截
    code, body = api(client, 'POST', '/api/biz/change/audit', r4, json_body={
        'change_id': change_id, 'result': 'APPROVED'})
    assert code == 400 and '已审核' in body['message']
    # 再发一张 → 通过 → R1 收到审核结果通知
    code, body = api(client, 'POST', '/api/biz/change/apply', env['r1'], json_body={
        'biz_type': 'ALLOC', 'biz_id': aid, 'before_content': '单价655元',
        'after_content': '单价650元'})
    change_id2 = body['data']['change_id']
    code, body = api(client, 'POST', '/api/biz/change/audit', r4, json_body={
        'change_id': change_id2, 'result': 'APPROVED'})
    assert code == 200 and body['data']['status'] == 'APPROVED'
    _, body = api(client, 'GET', '/api/message/list', env['r1'])
    assert any('变更申请审核' in m['title'] for m in body['data']['list'])
    # 历史轨迹
    _, body = api(client, 'GET', f'/api/biz/history?biz_type=ALLOC&biz_id={aid}', env['r1'])
    assert len(body['data']['changes']) == 2
    # R3 无权访问历史
    code, _ = api(client, 'GET', f'/api/biz/history?biz_type=ALLOC&biz_id={aid}', env['ptok'])
    assert code == 403


def test_biz_redback_flow(client):
    """红冲：原因校验/审核作废/防重复/ALLOC 红冲后分摊拦截/历史轨迹"""
    env = setup_to_n5(client)
    r4 = env['admin']
    code, _ = allocate(client, env)
    assert code == 200
    aid = get_alloc_id(client, env)
    # 完整分摊链路：船检通过 + 费用 + 分摊
    approve_ship_report(client, r4, env['order_id'])
    mk_bill(client, r4, env['order_id'], 'SEA', 10000)
    code, body = api(client, 'POST', '/api/expense/share/run', r4, json_body={'order_id': env['order_id']})
    assert code == 200
    # 原因不足 5 字
    code, body = api(client, 'POST', '/api/biz/redback/apply', env['r1'], json_body={
        'biz_type': 'ALLOC', 'biz_id': aid, 'reason': '错单'})
    assert code == 400 and '红冲原因必填且不少于5个字' in body['message']
    # R3 无权发起
    code, _ = api(client, 'POST', '/api/biz/redback/apply', env['ptok'], json_body={
        'biz_type': 'ALLOC', 'biz_id': aid, 'reason': '分拨数量录错需要红冲'})
    assert code == 403
    # R1 申请红冲分拨单（带红冲吨数）
    code, body = api(client, 'POST', '/api/biz/redback/apply', env['r1'], json_body={
        'biz_type': 'ALLOC', 'biz_id': aid, 'reason': '分拨数量录错需要红冲', 'redback_ton': 1000})
    assert code == 200, body
    redback_id = body['data']['redback_id']
    # 审核列表 kind=redback：source_biz_id 指向原单
    _, body = api(client, 'GET', '/api/biz/apply/list?kind=redback', r4)
    row = body['data']['list'][0]
    assert row['source_biz_id'] == aid and row['redback_no'].startswith('HC')
    # 驳回第一张
    code, body = api(client, 'POST', '/api/biz/redback/audit', r4, json_body={
        'redback_id': redback_id, 'result': 'REJECTED', 'review_remark': '请补充磅单证据'})
    assert code == 200 and body['data']['status'] == 'REJECTED'
    # 单据未被作废，可再次申请
    code, body = api(client, 'POST', '/api/biz/redback/apply', env['r1'], json_body={
        'biz_type': 'ALLOC', 'biz_id': aid, 'reason': '分拨数量录错需要红冲第二次'})
    redback_id2 = body['data']['redback_id']
    # 通过 → 原单作废
    code, body = api(client, 'POST', '/api/biz/redback/audit', r4, json_body={
        'redback_id': redback_id2, 'result': 'APPROVED'})
    assert code == 200 and body['data']['status'] == 'APPROVED'
    # 重复申请被拦（原单已作废）
    code, body = api(client, 'POST', '/api/biz/redback/apply', env['r1'], json_body={
        'biz_type': 'ALLOC', 'biz_id': aid, 'reason': '分拨数量录错需要红冲第三次'})
    assert code == 400 and '已被红冲作废，不可重复红冲' in body['message']
    # 重复审核拦截
    code, body = api(client, 'POST', '/api/biz/redback/audit', r4, json_body={
        'redback_id': redback_id2, 'result': 'APPROVED'})
    assert code == 400 and '已审核' in body['message']
    # 红冲后分拨单不再参与分摊：撤销旧分摊后重跑 → 无可分摊分拨单
    code, body = api(client, 'POST', '/api/expense/share/revoke', r4, json_body={'order_id': env['order_id']})
    assert code == 200
    code, body = api(client, 'POST', '/api/expense/share/run', r4, json_body={'order_id': env['order_id']})
    assert code == 400 and '没有可分摊的分拨单' in body['message']
    # R1 收到红冲审核通知
    _, body = api(client, 'GET', '/api/message/list', env['r1'])
    assert any('红冲申请审核' in m['title'] for m in body['data']['list'])
    # 历史轨迹：redbacks 2 条（一驳一过）
    _, body = api(client, 'GET', f'/api/biz/history?biz_type=ALLOC&biz_id={aid}', env['r1'])
    assert len(body['data']['redbacks']) == 2
    # 补充：化验单红冲 → 状态置 REDBACKED，列表过滤
    rtok, _ = mk_partner(client, '红冲船检机构')
    data = mk_inspect(client, rtok, report_type=2, order_id=env['order_id'], wet_ton=900)
    ship_rid = data['report_id']
    code, body = api(client, 'POST', '/api/inspect/report/audit', r4, json_body={
        'report_id': ship_rid, 'result': 'APPROVED'})
    assert code == 200
    code, body = api(client, 'POST', '/api/biz/redback/apply', rtok, json_body={
        'biz_type': 'INSPECT', 'biz_id': ship_rid, 'reason': '船检数据录入有误需作废'})
    assert code == 200, body
    code, body = api(client, 'POST', '/api/biz/redback/audit', r4, json_body={
        'redback_id': body['data']['redback_id'], 'result': 'APPROVED'})
    assert code == 200
    # 化验单列表（含 R4）不再显示该红冲单；详情状态 REDBACKED
    _, body = api(client, 'GET', '/api/inspect/report/list', r4)
    assert ship_rid not in [r['report_id'] for r in body['data']['list']]
    _, body = api(client, 'GET', f'/api/inspect/report/detail?report_id={ship_rid}', r4)
    assert body['data']['status'] == 'REDBACKED'
