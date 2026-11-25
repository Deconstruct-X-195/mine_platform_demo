# -*- coding: utf-8 -*-
"""E2E 全链路测试（PRD 10.2 + AC 验收清单）：注册→准入→基准价→需求→需求归集→平台代发询价→
密封报价→平台汇总揭示→钢厂反馈（全员认可自动成单）→订单确认→提货计划→平台物流方案与
分段运单→物流节点→签收→质检预警→结算→付款→归档→导出→越权隔离。

前置：Flask 运行于 127.0.0.1:8000（PostgreSQL 14 可达），库内存在已审批的
钢厂/供应商/承运商基线账号（清理后基线或 seed 演示数据均可，账号动态发现）。
运行：python tests/e2e_full_chain.py
"""
import io
import os
import sys
import zipfile
from datetime import datetime, timedelta

from e2e_helpers import (ADMIN, BASE, PASS, Client, check, discover_accounts,
                         dl_bytes, pg_one, summary)

# E2E 直连库必须与被测服务一致：默认本机演示库，多环境验证时用 MINE_PG_DSN 覆盖
PG_DSN = os.environ.get('MINE_PG_DSN', 'postgresql://postgres:Langchain2026@127.0.0.1:5432/mine_platform')
PDF = b'%PDF-1.4\nE2E test file\n%%EOF'

MIN_SUPPLIERS = 3  # 密封报价/揭示比价的最少供应商数


def pg_exec(sql, args=()):
    """测试专用直连：仅用于把报价截止时间拨到过去以触发揭示（业务接口禁止该操作）。"""
    import psycopg
    with psycopg.connect(PG_DSN) as conn:
        conn.execute(sql, args)


def upload_license(anon, tag, suffix='pdf'):
    """免登录执照上传（POST /auth/license）：注册流程专用公开接口。"""
    r = anon.s.post(BASE + '/auth/license',
                    files={'file': ('license-%s.%s' % (tag, suffix), PDF, 'application/pdf')},
                    timeout=15)
    b = r.json()
    assert r.status_code == 200 and b.get('code') == 0, '免登录执照上传失败：%s %s' % (r.status_code, b)
    return b['data']['fileId']


def login_user(username):
    """自适应登录：基线/seed 账号用 demo123456，E2E 历史注册账号用 new123456。"""
    last = None
    for pw in (PASS, 'new123456'):
        try:
            return Client.login(username, pw)
        except Exception as e:  # noqa: BLE001 - 记录最后一次失败
            last = e
    raise last


def run():
    plat = Client.login(*ADMIN)
    now = datetime.now()
    tag = now.strftime('%m%d%H%M%S')
    today = now.strftime('%Y-%m-%d')
    anon = Client()  # 未登录客户端：验证注册链路为公开接口

    # 自适应发现基线账号（兼容"清理后基线"与"seed 演示数据"两种环境）
    # 承运商端已下线（2026-11-13 起）：承运商账号仅作运单归属展示，不再登录
    acc = discover_accounts()
    assert acc['steel'] and acc['suppliers'], \
        '基线账号缺失：钢厂 %s / 供应商 %s / 承运商 %s' % acc
    print('[基线] 钢厂 %s | 供应商 %d 家 | 承运商 %s（承运商端已下线，不登录）'
          % (acc['steel'][0], len(acc['suppliers']), acc['carrier'][0] if acc['carrier'] else '-'))
    steel = login_user(acc['steel'][0])
    sup1 = login_user(acc['suppliers'][0])
    sup1_cid = sup1.user['company']['id']

    # ---- AC-01 企业注册（免登录执照上传 + 类型别名归一）----
    print('\n[AC-01] 企业注册')
    lic = upload_license(anon, tag)
    credit1 = '91340100MA1T%05dX' % (now.second * 1000 + now.microsecond // 1000)
    u1 = '139%02d%06d' % (now.second, now.microsecond)
    reg1 = {'companyName': 'E2E钢厂二' + tag, 'creditCode': credit1,
            'companyTypes': 'STEEL_BUYER', 'province': '河北省', 'city': '唐山市',
            'contactName': 'E2E 联系人一', 'contactPhone': '13900000001',
            'username': u1, 'password': 'new123456', 'legalPerson': 'E2E 法定代表人',
            'licenseFileId': lic}
    r1 = anon.post('/auth/register', reg1)
    check('AC-01 注册成功待准入', r1['auditStatus'] == 'PENDING', r1)
    t1 = pg_one("SELECT company_types FROM ent_company WHERE id=%s", (r1['companyId'],))[0]
    check('AC-01 企业类型别名归一(STEEL_BUYER→STEEL)', t1 == 'STEEL', t1)
    bad = dict(reg1)
    bad.pop('licenseFileId')
    bad['username'] = '138%02d%06d' % (now.minute, now.microsecond)
    s, c, m = anon.try_code('POST', '/auth/register', bad)
    check('AC-01 缺营业执照附件被拦截(40001)', c == 40001, m)
    lic2 = upload_license(anon, tag + '-dup')
    dup = dict(reg1)
    dup['username'] = '137%02d%06d' % (now.minute, now.microsecond)
    dup['contactPhone'] = '13700000000'
    dup['licenseFileId'] = lic2
    s, c, m = anon.try_code('POST', '/auth/register', dup)
    check('AC-01 重复信用代码被拦截(40902)', c == 40902, m)

    # 供应商不足 3 家时，随注册流程补齐（密封报价/揭示比价需要）
    new_regs = []
    for i in range(max(0, MIN_SUPPLIERS - len(acc['suppliers']))):
        lic_i = upload_license(anon, '%s-sup%d' % (tag, i))
        credit_i = '91340100MA2T%05dX' % (now.second * 1000 + now.microsecond // 1000 + i + 1)
        ui = '138%02d%06d' % (now.second + i + 1, now.microsecond)
        regi = {'companyName': 'E2E补位供应商%s%s' % (i + 1, tag), 'creditCode': credit_i,
                'companyTypes': 'SUPPLIER', 'province': '山东省', 'city': '青岛市',
                'contactName': 'E2E 供应商联系人', 'contactPhone': '1390000%04d' % (i + 1),
                'username': ui, 'password': 'new123456', 'legalPerson': 'E2E 供应商法人%s' % (i + 1),
                'licenseFileId': lic_i}
        ri = anon.post('/auth/register', regi)
        ti = pg_one("SELECT company_types FROM ent_company WHERE id=%s", (ri['companyId'],))[0]
        check('AC-01 补位供应商注册并归一(SUPPLIER)', ti == 'SUPPLIER', ti)
        new_regs.append(regi)
    if new_regs:
        print('[AC-01] 基线供应商 %d 家，已补位注册 %d 家'
              % (len(acc['suppliers']), len(new_regs)))

    # ---- AC-02 平台准入审批 ----
    print('\n[AC-02] 平台准入审批')
    s, c, m = plat.try_code('PUT', '/admin/companies/0/audit', {'approve': 'true'})
    check('AC-02 不存在企业返回 40401', c == 40401, m)
    s, c, m = plat.try_code('PUT', '/admin/companies/0/audit', {})
    check('AC-02 审批参数缺失返回 40001', c == 40001, m)
    pend = plat.get('/admin/companies', size=100)['list']
    to_approve = [reg1] + new_regs
    cid2 = next(x['id'] for x in pend if x['companyName'] == reg1['companyName'])
    s, c, m = plat.try_code('PUT', '/admin/companies/%d/audit' % cid2, {'approve': 'false'})
    check('AC-02 驳回缺原因返回 40001', c == 40001, m)
    for regx in to_approve:
        cx = next(x['id'] for x in pend if x['companyName'] == regx['companyName'])
        plat.put('/admin/companies/%d/audit' % cx, {'approve': 'true', 'remark': 'E2E 准入'})
    steel2 = Client.login(u1, 'new123456')
    me = steel2.get('/auth/me')
    check('AC-02 审批后 APPROVED 且开放菜单',
          me['company']['auditStatus'] == 'APPROVED' and len(me['menus']) > 0,
          me.get('company'))

    # 审批完成后装配供应商池（sup2/sup3 可能为本次新注册账号，统一走双密码回退登录）
    sup_pool = list(acc['suppliers']) + [r['username'] for r in new_regs]
    sup2 = login_user(sup_pool[1])
    sup3 = login_user(sup_pool[2])
    sup2_cid = sup2.user['company']['id']
    sup3_cid = sup3.user['company']['id']

    # ---- AC-05 品种与基准价 ----
    print('\n[AC-05] 品种与基准价')
    vs = steel.get('/base/varieties')['list']
    check('AC-05 品种列表非空', len(vs) >= 1, [v['varietyName'] for v in vs])
    # 优先选取基线品种（PB粉），seed 环境回退到 IRON_ORE_POWDER，再回退首品种
    pb = next((v for v in vs if 'PB' in (v.get('varietyName') or '').upper()
               or v.get('varietyCode') == 'IRON_ORE_POWDER'), vs[0])
    # 默认牌号数值校验（回归：非法值返回 40001 业务错误而非 500）
    s, c, m = plat.try_code('POST', '/admin/varieties',
                            {'varietyCode': 'E2EGRD%s' % tag, 'varietyName': 'E2E 牌号校验品种',
                             'defaultGrade': 'abc'})
    check('AC-05 默认牌号非数值被拦截(40001)', c == 40001, m)
    s, c, m = plat.try_code('PUT', '/admin/varieties/%d' % pb['id'], {'defaultGrade': 999})
    check('AC-05 默认牌号超范围被拦截(40001)', c == 40001, m)
    # 新建无港口价的校验品种：/base-prices/current 对无港口价品种回退展示锚点基准价
    v2 = plat.post('/admin/varieties', {'varietyCode': 'E2EGRD%s' % tag,
                                        'varietyName': 'E2E 基准价校验品种',
                                        'defaultGrade': 61.5})
    check('AC-05 新建品种成功', bool(v2.get('id')), v2)
    # 幂等：清掉上次运行当日基准价残留（验收要求"首次录入为新增"）
    pg_exec("DELETE FROM base_price WHERE variety_id=%s AND price_date=%s", (pb['id'], today))
    b1 = plat.post('/admin/base-prices', {'varietyId': pb['id'], 'priceDate': today,
                                          'price': 820.5, 'priceBasis': 'WET',
                                          'sourceDesc': 'E2E 录入'})
    check('AC-05 首次录入为新增', not b1.get('updated'), b1)
    b2 = plat.post('/admin/base-prices', {'varietyId': pb['id'], 'priceDate': today,
                                          'price': 830.5, 'priceBasis': 'WET',
                                          'sourceDesc': 'E2E 当日更新'})
    check('AC-05 同品种同日更新留痕', b2.get('updated') is True and b2['id'] == b1['id'], b2)
    s, c, m = steel.try_code('POST', '/admin/base-prices',
                             {'varietyId': pb['id'], 'priceDate': today, 'price': 1})
    check('AC-05 非平台无权录入(40301)', c == 40301, m)
    pg_exec("DELETE FROM base_price WHERE variety_id=%s AND price_date=%s", (v2['id'], today))
    plat.post('/admin/base-prices', {'varietyId': v2['id'], 'priceDate': today,
                                     'price': 830.5, 'priceBasis': 'WET',
                                     'sourceDesc': 'E2E 锚点价校验'})
    cur = steel.get('/base-prices/current', varietyId=v2['id'])
    trow = next((x for x in cur['today'] if x['varietyId'] == v2['id']), None)
    check('AC-05 当日报价已生效', trow is not None and trow['price'] == '830.50', cur['today'])
    check('AC-05 近30日走势非空', len(cur['trend']) >= 1, cur['trend'])

    # ---- AC-03 需求申报 ----
    print('\n[AC-03] 需求申报')
    d1 = (now + timedelta(days=5)).strftime('%Y-%m-%d')
    d2 = (now + timedelta(days=20)).strftime('%Y-%m-%d')
    base_body = {'demandName': 'E2E 全链路需求' + tag, 'deliveryType': 'PORT_TRUCK',
                 'deliveryPlace': '青岛港', 'expectArriveStart': d1, 'expectArriveEnd': d2,
                 'settleType': 'COD', 'priceIntent': '随行就市',
                 'items': [{'varietyId': pb['id'], 'grade': 62.0, 'quantity': 30000,
                            'moreLessRate': 5}]}
    bad = dict(base_body)
    bad['settleType'] = '月结'
    s, c, m = steel.try_code('POST', '/demands', bad)
    check('AC-03 结算方式不合法(40001)', c == 40001, m)
    bad = dict(base_body)
    bad['items'] = [dict(base_body['items'][0], grade='PB 粉')]
    s, c, m = steel.try_code('POST', '/demands', bad)
    check('AC-03 品位必须为数值(40001)', c == 40001, m)
    d = steel.post('/demands', base_body)
    dem_id = d['id']
    check('AC-03 创建为草稿', d['status'] == 'DRAFT', d)
    steel.put('/demands/%d' % dem_id, base_body)
    dv = steel.get('/demands/%d' % dem_id)
    item_id = dv['items'][0]['id']
    check('AC-03 草稿明细已保存',
          len(dv['items']) == 1 and float(dv['items'][0]['quantity']) == 30000, dv['items'])
    r = steel.post('/demands/%d/submit' % dem_id)
    check('AC-03 提交后 SUBMITTED', r['status'] == 'SUBMITTED', r)
    bad2 = dict(base_body)
    bad2['demandName'] = '提交后改名尝试'
    s, c, m = steel.try_code('PUT', '/demands/%d' % dem_id, bad2)
    check('AC-03 提交后更改须填更改理由(40001)', c == 40001, m)
    w = steel.post('/demands/%d/withdraw' % dem_id)
    check('AC-03 撤回 WITHDRAWN', w['status'] == 'WITHDRAWN', w)
    r = steel.post('/demands/%d/submit' % dem_id)
    check('AC-03 重提版本+1', r.get('version') == 2, r)

    # ---- AC-04 需求池脱敏 ----
    print('\n[AC-04] 需求池脱敏')
    pool = sup1.get('/demands')['list']
    row = next((x for x in pool if x['id'] == dem_id), None)
    check('AC-04 供应商可见需求池条目', row is not None, '共 %d 条' % len(pool))
    check('AC-04 不泄露企业名称与价格意向',
          row is not None and 'companyName' not in row and 'unitPrice' not in row, row)
    check('AC-04 脱敏概要字段齐全',
          row is not None and float(row['totalQty']) == 30000
          and row['deliveryRegion'] == '青岛港', row)

    # ---- AC-07 需求归集与平台代发询价 ----
    print('\n[AC-07] 需求归集与平台代发询价')
    deadline = (now + timedelta(hours=2, minutes=10)).strftime('%Y-%m-%d %H:%M:%S')
    arrive = (now + timedelta(days=9)).strftime('%Y-%m-%d')
    # 钢厂自发询价恢复为完整端点（对齐 2026-11-24 迭代）：缺 quantity/arriveDate 被参数校验拦截
    s, c, m = steel.try_code('POST', '/inquiries', {'demandId': dem_id, 'demandItemId': item_id})
    check('AC-07 自发询价必填参数拦截(40001)', c == 40001, m)
    # 钢厂二创建同品种同品位需求并提交，供平台归集
    d2body = dict(base_body, demandName='E2E 归集需求-钢厂二' + tag,
                  items=[dict(base_body['items'][0], quantity=15000)])
    d2 = steel2.post('/demands', d2body)
    steel2.post('/demands/%d/submit' % d2['id'])
    # 平台需求池按本次两条需求匹配可归集明细（agg_flow 口径：itemId 优先）
    pool = plat.get('/admin/demand-pool', size=50)['list']
    match = [it for it in pool
             if it.get('demandId') in (dem_id, d2['id']) and it.get('status') == 'SUBMITTED'
             and float(it['quantity']) - float(it.get('inquiredQty') or 0) > 0]
    item_ids = [it['itemId'] if 'itemId' in it else it['id'] for it in match]
    check('AC-07 需求池匹配两条可归集明细', len(item_ids) == 2, match)
    agg = plat.post('/admin/aggregated-orders', {'itemIds': item_ids})
    check('AC-07 归集订单生成 45000 吨',
          bool(agg.get('aggNo')) and float(agg['totalQty']) == 45000.0, agg)
    # 报价截止由平台自动设定（到货日前 7 天 18:00，下限当前 +2h），调用方不再传 deadline
    bad = {'aggOrderId': agg['id'], 'arriveDate': arrive, 'minResponse': 3,
           'inviteSupplierIds': []}
    s, c, m = plat.try_code('POST', '/admin/quote-inquiries', bad)
    check('AC-07 至少邀请一家供应商(40001)', c == 40001, m)
    qi = plat.post('/admin/quote-inquiries',
                   {'aggOrderId': agg['id'], 'arriveDate': arrive,
                    'minResponse': 3, 'inviteSupplierIds': [sup1_cid, sup2_cid, sup3_cid],
                    'remark': 'E2E 平台代发询价'})
    inq_id = qi['inquiryId']
    check('AC-07 平台代发询价 batchNo/aggNo',
          str(qi.get('batchNo', '')).startswith('PC') and qi.get('aggNo') == agg['aggNo'], qi)
    det = steel.get('/inquiries/%d' % inq_id)
    check('AC-07 成员钢厂归集视图与份额',
          det.get('aggView') is True and float(det.get('shareQty')) == 30000.0, det)

    # ---- AC-08 密封报价与平台汇总揭示 ----
    print('\n[AC-08] 密封报价与平台汇总揭示')
    s, c, m = sup1.try_code('POST', '/inquiries/%d/reveal' % inq_id, {})
    check('AC-08 供应商不可揭示(40301)', c == 40301, m)
    s, c, m = plat.try_code('POST', '/admin/quote-inquiries/%d/return' % inq_id, {})
    check('AC-08 无报价不可汇总揭示(40001)', c == 40001, m)
    deliver = (now + timedelta(days=8)).strftime('%Y-%m-%d')
    # 报价新契约（2026-11-24 迭代）：产品申报必填矿种 varietyId
    var_id = pg_one("SELECT variety_id FROM biz_inquiry WHERE id=%s", (inq_id,))[0]
    for cli, price in ((sup1, 818.00), (sup2, 815.00), (sup3, 812.00)):
        cli.post('/inquiries/%d/quotes' % inq_id,
                 {'price': price, 'quantity': 45000, 'deliveryDate': deliver, 'payTerms': 'T/T',
                  'taxType': 'INC_TAX', 'freightPrice': 30.0, 'deliveryType': 'PORT_FOB',
                  'varietyId': var_id, 'origin': '澳大利亚', 'grade': 61.5})
        det = cli.get('/inquiries/%d' % inq_id)
        check('AC-08 供应商可见自己报价',
              det.get('myQuote', {}).get('status') == 'SUBMITTED', det.get('myQuote'))
    s, c, m = sup1.try_code('POST', '/inquiries/%d/quotes' % inq_id,
                            {'price': 810, 'quantity': 45000, 'deliveryDate': deliver,
                             'taxType': 'INC_TAX', 'freightPrice': 30.0, 'deliveryType': 'PORT_FOB',
                             'varietyId': var_id, 'origin': '澳大利亚', 'grade': 61.5})
    check('AC-08 重复报价被拦截(40902)', c == 40902, m)
    det = steel.get('/inquiries/%d' % inq_id)
    leak = [i for i in det.get('quoteSuppliers', []) if 'price' in i or 'unitPrice' in i]
    check('AC-08 截止前需方不可见任何报价', not leak, leak)
    s, c, m = steel.try_code('POST', '/inquiries/%d/reveal' % inq_id, {})
    check('AC-08 未截止不可揭示(40901)', c == 40901, m)
    pg_exec("UPDATE biz_inquiry SET deadline=now()-interval '5 minutes' WHERE id=%s", (inq_id,))
    rv = plat.post('/admin/quote-inquiries/%d/return' % inq_id)
    check('AC-08 平台汇总揭示', rv.get('revealed') is True and rv.get('quoteCount') == 3, rv)
    rv2 = steel.get('/inquiries/%d/quotes/reveal' % inq_id)
    rows = rv2['rows']
    check('AC-08 揭示快照 3 条且量为本厂份额',
          len(rows) == 3 and float(rv2.get('shareQty')) == 30000.0
          and all(float(x['quantity']) == 30000.0 for x in rows), rows)
    check('AC-08 快照按价格升序',
          [float(x['unitPrice']) for x in rows] == [812.0, 815.0, 818.0], rows)
    q3_id = rows[0]['quoteId']  # sup3 最低价

    # ---- T11 钢厂反馈与自动成单 ----
    print('\n[T11] 钢厂反馈与自动成单')
    s, c, m = sup1.try_code('POST', '/inquiries/%d/feedback' % inq_id, {'decision': 'ACCEPTED'})
    check('T11 供应商不可反馈(40301)', c == 40301, m)
    s, c, m = steel.try_code('POST', '/inquiries/%d/feedback' % inq_id, {'decision': 'REJECTED'})
    check('T11 拒单必填原因(40001)', c == 40001, m)
    steel.post('/inquiries/%d/feedback' % inq_id, {'decision': 'ACCEPTED'})
    fb = plat.get('/admin/quote-inquiries/%d/feedbacks' % inq_id)['list']
    check('T11 钢厂一反馈可查', len(fb) == 1 and fb[0]['decision'] == 'ACCEPTED', fb)
    r2 = steel2.post('/inquiries/%d/feedback' % inq_id, {'decision': 'ACCEPTED'})
    check('T11 全员认可自动成单',
          bool(r2.get('autoAward', {}).get('orderId')) and r2['autoAward'].get('memberCount') == 2,
          r2.get('autoAward'))
    aw = r2['autoAward']

    # ---- AC-12 自动成单结果校验 ----
    print('\n[AC-12] 自动成单结果校验')
    oid = aw['orderId']
    check('AC-12 返回订单与确认期限', oid and bool(aw.get('confirmDeadline')), aw)
    od = steel.get('/orders/%d' % oid)
    check('AC-12 以最低价按归集总量成单', float(od['unit_price']) == 812.0
          and float(od['quantity']) == 45000.0, od)
    check('AC-12 订单待供应商确认', od['status'] == 'PENDING_CONFIRM', od)
    det3 = sup3.get('/inquiries/%d' % inq_id)
    check('AC-12 中标报价 WIN', det3['myQuote']['status'] == 'WIN', det3.get('myQuote'))
    det2 = sup2.get('/inquiries/%d' % inq_id)
    check('AC-12 未中标报价 LOSE', det2['myQuote']['status'] == 'LOSE', det2.get('myQuote'))
    s, c, m = plat.try_code('POST', '/admin/quote-inquiries/%d/award' % inq_id,
                            {'quoteId': q3_id})
    check('AC-12 重复定标被拦截(40901)', c == 40901, m)

    # ---- T12 供应商确认 ----
    print('\n[T12] 供应商订单确认')
    s, c, m = steel.try_code('PUT', '/orders/%d/confirm' % oid, {})
    check('T12 需方无确认权(40301)', c == 40301, m)
    sup3.put('/orders/%d/confirm' % oid, {})
    od2 = sup3.get('/orders/%d' % oid)
    check('T12 确认后待提货计划', od2['status'] == 'PENDING_PICKUP', od2)

    # ---- T13 提货计划全员提交 ----
    print('\n[T13] 提货计划全员提交')
    s, c, m = sup1.try_code('POST', '/orders/%d/pickup-plan' % oid, {'dailyQty': 1000, 'startDate': today})
    check('T13 非成员不可提交(40301)', c == 40301, m)
    s, c, m = steel.try_code('POST', '/orders/%d/pickup-plan' % oid, {'dailyQty': 0, 'startDate': today})
    check('T13 日提货量必须大于 0(40001)', c == 40001, m)
    steel.post('/orders/%d/pickup-plan' % oid, {'dailyQty': 3000, 'startDate': today})
    od3 = steel.get('/orders/%d' % oid)
    check('T13 单成员提交不转态', od3['status'] == 'PENDING_PICKUP', od3)
    steel2.post('/orders/%d/pickup-plan' % oid, {'dailyQty': 1500, 'startDate': today})
    od3 = steel.get('/orders/%d' % oid)
    check('T13 全员提交后待运输', od3['status'] == 'PENDING_TRANSPORT', od3)

    # ---- T14 平台物流方案与分段运单 ----
    print('\n[T14] 平台物流方案与分段运单')
    plan = plat.post('/admin/logistics-plans', {'orderId': oid, 'orgMode': 'PLATFORM'})
    pid = plan['planId']
    check('T14 平台创建物流方案', bool(pid), plan)
    s, c, m = plat.try_code('POST', '/admin/logistics-plans',
                            {'orderId': oid, 'orgMode': 'PLATFORM'})
    check('T14 重复方案被拦截(40902)', c == 40902, m)
    wd = (now + timedelta(days=6)).strftime('%Y-%m-%d')
    s, c, m = plat.try_code('POST', '/admin/logistics-plans/%d/waybills' % pid,
                            {'segmentNo': 'SEG-1', 'transportMode': 'SEA', 'planQty': 20000,
                             'planDepartDate': today, 'planArriveDate': wd,
                             'departPlace': '黄骅港', 'arrivePlace': '青岛港', 'freight': 60.0})
    check('T14 运输方式仅铁路/多式联运/公路(40001)', c == 40001, m)
    s, c, m = plat.try_code('POST', '/admin/logistics-plans/%d/waybills' % pid,
                            {'segmentNo': 'SEG-1', 'transportMode': 'ROAD', 'planQty': 20000,
                             'planDepartDate': today, 'planArriveDate': wd,
                             'departPlace': '黄骅港', 'arrivePlace': '青岛港'})
    check('T14 运费必填(40001)', c == 40001, m)
    s, c, m = plat.try_code('POST', '/admin/logistics-plans/%d/waybills' % pid,
                            {'segmentNo': 'SEG-1', 'transportMode': 'ROAD', 'planQty': 20000,
                             'planDepartDate': today, 'planArriveDate': wd,
                             'departPlace': '曹妃甸港', 'arrivePlace': '青岛港', 'freight': 60.0})
    check('T14 装货港口仅黄骅港/天津港(40001)', c == 40001, m)
    s, c, m = plat.try_code('POST', '/admin/logistics-plans/%d/waybills' % pid,
                            {'segmentNo': 'SEG-1', 'transportMode': 'ROAD', 'planQty': 20000,
                             'planDepartDate': today, 'planArriveDate': wd,
                             'departPlace': '黄骅港', 'arrivePlace': '青岛港', 'freight': 60.0})
    check('T14 计划量偏差超5%须填说明(40001)', c == 40001, m)
    w1 = plat.post('/admin/logistics-plans/%d/waybills' % pid,
                   {'segmentNo': 'SEG-1', 'transportMode': 'ROAD', 'planQty': 20000,
                    'planDepartDate': today, 'planArriveDate': wd,
                    'departPlace': '黄骅港', 'arrivePlace': '青岛港', 'freight': 60.0,
                    'deviationReason': '首段运力有限，剩余量由第二段补齐'})
    wid1 = w1['id']
    check('T14 分段1创建即待发运', w1['status'] == 'PENDING_DEPART', w1)
    r = plat.put('/admin/waybills/%d/advance' % wid1, {'action': 'ETA'})
    check('T14 平台登记船到港', r.get('action') == 'ETA', r)
    s, c, m = plat.try_code('PUT', '/admin/waybills/%d/advance' % wid1, {'action': 'ARRIVE'})
    check('T14 未发运不可到达(40901)', c == 40901, m)
    plat.put('/admin/waybills/%d/advance' % wid1, {'action': 'DEPART', 'actualQty': 20000})
    plat.put('/admin/waybills/%d/advance' % wid1, {'action': 'ARRIVE'})
    steel.post('/waybills/%d/sign' % wid1, {})
    wl = steel.get('/waybills', orderId=oid)['list']
    st1 = next(x for x in wl if x['id'] == wid1)
    check('T14 需方签收后 SIGNED', st1['status'] == 'SIGNED', st1)
    w2 = plat.post('/admin/logistics-plans/%d/waybills' % pid,
                   {'segmentNo': 'SEG-2', 'transportMode': 'RAIL', 'planQty': 25000,
                    'planDepartDate': today, 'planArriveDate': wd,
                    'departPlace': '天津港', 'arrivePlace': '青岛港', 'freight': 80.0})
    wid2 = w2['id']
    check('T14 分段2创建即待发运', w2['status'] == 'PENDING_DEPART', w2)
    plat.put('/admin/waybills/%d/advance' % wid2, {'action': 'DEPART'})
    plat.put('/admin/waybills/%d/advance' % wid2, {'action': 'ARRIVE'})
    steel.post('/waybills/%d/sign' % wid2, {})
    wl = steel.get('/waybills', orderId=oid)['list']
    check('T14 全部运单 SIGNED',
          len(wl) == 2 and all(x['status'] == 'SIGNED' for x in wl),
          [(x['id'], x['status']) for x in wl])

    # ---- T16 履约时间轴 ----
    print('\n[T16] 履约时间轴')
    tl = steel.get('/orders/%d/timeline' % oid)['list']
    check('T16 时间轴节点完整', len(tl) >= 8, '共 %d 个节点' % len(tl))
    codes = {x.get('nodeCode') or x.get('node_code') for x in tl}
    check('T16 含订单/运单节点',
          {'ORDER_CREATED', 'WAYBILL_SIGNED'} <= codes, codes)

    # ---- T17 质检 + AC-19 预警 ----
    print('\n[T17/AC-19] 质检与预警')
    steel.post('/orders/%d/quality-check' % oid,
               {'arrivedQty': 50000, 'conclusion': 'ACCEPT', 'indicators': 'Fe 62.1%',
                'checkDesc': 'E2E 质检-超差触发预警'})
    als = steel.get('/alerts', bizType='ORDER', bizId=oid)['list']
    al = next((a for a in als if a.get('alertType') == 'QTY_DIFF'), None)
    check('AC-19 超差自动触发预警', al is not None, als)
    aid = al['id']
    r = steel.put('/alerts/%d/handle' % aid, {'action': 'PROCESSING', 'handlerRemark': 'E2E 处理中'})
    check('AC-19 预警转处理中', r['status'] == 'PROCESSING', r)
    # 再次超差：同对象同类型仅一条未关闭预警（24h 节流不重复新建）
    steel.post('/orders/%d/quality-check' % oid,
               {'arrivedQty': 51000, 'conclusion': 'ACCEPT', 'checkDesc': 'E2E 重复超差'})
    als2 = steel.get('/alerts', bizType='ORDER', bizId=oid, alertType='QTY_DIFF')['list']
    open2 = [a for a in als2 if a['status'] in ('PENDING', 'PROCESSING')]
    check('AC-19 未关闭同类预警去重',
          len(open2) == 1 and len(als2) == 1 and open2[0]['id'] == aid,
          [(a['id'], a['status']) for a in als2])
    s, c, m = steel.try_code('PUT', '/alerts/%d/handle' % aid, {'action': 'CLOSE'})
    check('AC-19 关闭须填处理意见(40001)', c == 40001, m)
    steel.put('/alerts/%d/handle' % aid, {'action': 'CLOSE', 'handlerRemark': '双方确认按实收结算'})
    steel.post('/orders/%d/quality-check' % oid,
               {'arrivedQty': 46000, 'conclusion': 'ACCEPT', 'indicators': 'Fe 62.0%',
                'checkDesc': 'E2E 复检'})
    qcs = steel.get('/orders/%d/quality-checks' % oid)['list']
    check('T17 质检记录 3 条', len(qcs) == 3, [x['checkNo'] for x in qcs])

    # ---- T18 结算双向确认 ----
    print('\n[T18] 结算与双向确认')
    total = 812.00 * 46000
    st = steel.post('/orders/%d/settlements' % oid, {'settleDesc': 'E2E 结算'})
    sid_ = st['id']
    check('T18 结算数量默认最近质检实收', float(st['settle_qty']) == 46000, st)
    check('T18 金额系统计算', float(st['total_amount']) == total, st['total_amount'])
    check('T18 初始待供应商确认', st['status'] == 'PENDING_CONFIRM_SUPPLIER', st)
    s, c, m = sup3.try_code('POST', '/orders/%d/settlements' % oid, {})
    check('T18 供应商无权生成结算(40301)', c == 40301, m)
    r = sup3.put('/settlements/%d/confirm' % sid_, {})
    check('T18 供方确认后待需方', r['status'] == 'PENDING_CONFIRM_BUYER', r)
    s, c, m = sup3.try_code('PUT', '/settlements/%d/confirm' % sid_, {})
    check('T18 冻结后不可重复确认(40901)', c == 40901, m)
    r = steel.put('/settlements/%d/confirm' % sid_, {})
    check('T18 双向确认后 CONFIRMED', r['status'] == 'CONFIRMED', r)

    # ---- T19 付款登记与归档导出 ----
    print('\n[T19] 付款登记与归档导出')
    pay = steel.post('/settlements/%d/payments' % sid_,
                     {'amount': total, 'payDate': today, 'payDesc': 'E2E 付款登记'})
    check('T19 生成付款单', str(pay.get('paymentNo', '')).startswith('FK'), pay)
    std = steel.get('/settlements/%d' % sid_)
    check('T19 付款后结算 COMPLETED', std['status'] == 'COMPLETED', std)
    check('T19 付款记录可查', len(std.get('payments', [])) == 1, std.get('payments'))
    # 完成确认（2026-11-24 迭代）：全部钢厂成员与供应商 finish-confirm 齐备后订单自动完成并归档
    steel.post('/orders/%d/finish-confirm' % oid, {})
    steel2.post('/orders/%d/finish-confirm' % oid, {})
    r1 = sup3.post('/orders/%d/finish-confirm' % oid, {})
    check('T19 双方确认后订单自动完成', r1.get('completed') is True, r1)
    od4 = steel.get('/orders/%d' % oid)
    check('T19 归档后订单 COMPLETED', od4['status'] == 'COMPLETED', od4)
    blob = dl_bytes(plat, '/orders/%d/archive/export' % oid)
    zf = zipfile.ZipFile(io.BytesIO(blob))
    check('T19 档案 zip 含 manifest.json',
          blob[:2] == b'PK' and 'manifest.json' in zf.namelist(), zf.namelist()[:5])

    # ---- AC-24 越权隔离与消息 ----
    print('\n[AC-24] 越权隔离与消息')
    s, c, m = sup2.try_code('GET', '/orders/%d' % oid)
    check('AC-24 无关方不可见订单(40301)', c == 40301, m)
    s, c, m = sup2.try_code('GET', '/settlements/%d' % sid_)
    check('AC-24 无关方不可见结算(40301)', c == 40301, m)
    ms = sup3.get('/messages', isRead='0')['list']
    check('消息通知已送达', len(ms) > 0, '未读 %d 条' % len(ms))

    return summary()


def main():
    try:
        ok_all = run()
    except AssertionError as exc:
        print('\nE2E 中断：%s' % exc)
        ok_all = False
    sys.exit(0 if ok_all else 1)


if __name__ == '__main__':
    main()
