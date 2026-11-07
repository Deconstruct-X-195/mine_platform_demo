# -*- coding: utf-8 -*-
"""E2E 全链路测试（PRD 10.2 + AC 验收清单）：注册→准入→基准价→需求→询价→密封报价→揭示→
议价→定标→订单确认→合同（作废重签）→物流→质检预警→结算→付款→归档→导出→越权隔离。

前置：Flask 运行于 127.0.0.1:8000（init_schema + seed 已执行，PostgreSQL 14 可达）。
运行：python tests/e2e_full_chain.py
"""
import hashlib
import io
import os
import sys
import zipfile
from datetime import datetime, timedelta

from e2e_helpers import (ADMIN, BASE, CARRIER, PASS, SUP1, SUP2, SUP3, STEEL,
                         Client, check, dl_bytes, summary)

# E2E 直连库必须与被测服务一致：默认本机演示库，多环境验证时用 MINE_PG_DSN 覆盖
PG_DSN = os.environ.get('MINE_PG_DSN', 'postgresql://postgres:Langchain2026@127.0.0.1:5432/mine_platform')
PDF = b'%PDF-1.4\nE2E test file\n%%EOF'
PNG = b'\x89PNG\r\n\x1a\nE2E-FAKE-STAMP-IMAGE'


def pg_exec(sql, args=()):
    """测试专用直连：仅用于把报价截止时间拨到过去以触发揭示（业务接口禁止该操作）。"""
    import psycopg
    with psycopg.connect(PG_DSN) as conn:
        conn.execute(sql, args)


def upload(client, filename, data, ctype):
    r = client.s.post(BASE + '/files', files={'file': (filename, data, ctype)}, timeout=15)
    b = r.json()
    assert r.status_code == 200 and b.get('code') == 0, \
        '上传 %s 失败：HTTP %s %s' % (filename, r.status_code, b)
    return b['data']['fileId']


def run():
    plat = Client.login(*ADMIN)
    steel = Client.login(STEEL, PASS)
    sup1 = Client.login(SUP1, PASS)
    sup2 = Client.login(SUP2, PASS)
    sup3 = Client.login(SUP3, PASS)
    carrier = Client.login(CARRIER, PASS)
    now = datetime.now()
    tag = now.strftime('%m%d%H%M%S')
    today = now.strftime('%Y-%m-%d')

    sup1_cid = sup1.user['company']['id']
    sup2_cid = sup2.user['company']['id']
    sup3_cid = sup3.user['company']['id']
    carrier_cid = carrier.user['company']['id']

    # ---- AC-01 企业注册 ----
    print('\n[AC-01] 企业注册')
    lic = upload(plat, 'license-%s.pdf' % tag, PDF, 'application/pdf')
    credit1 = '91340100MA1T%05dX' % (now.second * 1000 + now.microsecond // 1000)
    u1 = '139%02d%06d' % (now.second, now.microsecond)
    reg1 = {'companyName': 'E2E钢厂二' + tag, 'creditCode': credit1,
            'companyTypes': 'STEEL', 'province': '河北省', 'city': '唐山市',
            'contactName': 'E2E 联系人一', 'contactPhone': '13900000001',
            'username': u1, 'password': 'new123456', 'licenseFileId': lic}
    r1 = plat.post('/auth/register', reg1)
    check('AC-01 注册成功待准入', r1['auditStatus'] == 'PENDING', r1)
    bad = dict(reg1)
    bad.pop('licenseFileId')
    bad['username'] = '138%02d%06d' % (now.minute, now.microsecond)
    s, c, m = plat.try_code('POST', '/auth/register', bad)
    check('AC-01 缺营业执照附件被拦截(40001)', c == 40001, m)
    lic2 = upload(plat, 'license-dup-%s.pdf' % tag, PDF, 'application/pdf')
    dup = dict(reg1)
    dup['username'] = '137%02d%06d' % (now.minute, now.microsecond)
    dup['contactPhone'] = '13700000000'
    dup['licenseFileId'] = lic2
    s, c, m = plat.try_code('POST', '/auth/register', dup)
    check('AC-01 重复信用代码被拦截(40902)', c == 40902, m)

    # ---- AC-02 平台准入审批 ----
    print('\n[AC-02] 平台准入审批')
    s, c, m = plat.try_code('PUT', '/admin/companies/0/audit', {'approve': 'true'})
    check('AC-02 不存在企业返回 40401', c == 40401, m)
    s, c, m = plat.try_code('PUT', '/admin/companies/0/audit', {})
    check('AC-02 审批参数缺失返回 40001', c == 40001, m)
    pend = plat.get('/admin/companies', size=100)['list']
    cid2 = next(x['id'] for x in pend if x['companyName'] == reg1['companyName'])
    s, c, m = plat.try_code('PUT', '/admin/companies/%d/audit' % cid2, {'approve': 'false'})
    check('AC-02 驳回缺原因返回 40001', c == 40001, m)
    plat.put('/admin/companies/%d/audit' % cid2, {'approve': 'true', 'remark': 'E2E 准入'})
    steel2 = Client.login(u1, 'new123456')
    me = steel2.get('/auth/me')
    check('AC-02 审批后 APPROVED 且开放菜单',
          me['company']['auditStatus'] == 'APPROVED' and len(me['menus']) > 0,
          me.get('company'))

    # ---- AC-05 品种与基准价 ----
    print('\n[AC-05] 品种与基准价')
    vs = steel.get('/base/varieties')['list']
    check('AC-05 品种列表非空', len(vs) >= 4, vs)
    pb = next(v for v in vs if v['varietyCode'] == 'IRON_ORE_POWDER')
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
    cur = steel.get('/base-prices/current', varietyId=pb['id'])
    trow = next((x for x in cur['today'] if x['varietyId'] == pb['id']), None)
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
    check('AC-03 提交后关键字段锁定(40901)', c == 40901, m)
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

    # ---- AC-07 询价创建与发出 ----
    print('\n[AC-07] 询价创建与发出')
    deadline = (now + timedelta(hours=2, minutes=10)).strftime('%Y-%m-%d %H:%M:%S')
    arrive = (now + timedelta(days=9)).strftime('%Y-%m-%d')
    inq_body = {'demandId': dem_id, 'demandItemId': item_id, 'quantity': 20000,
                'arriveDate': arrive, 'deadline': deadline, 'minResponse': 3,
                'inviteSupplierIds': [sup1_cid, sup2_cid, sup3_cid], 'remark': 'E2E 询价'}
    bad = dict(inq_body)
    bad['deadline'] = now.strftime('%Y-%m-%d %H:%M:%S')
    s, c, m = steel.try_code('POST', '/inquiries', bad)
    check('AC-07 截止须至少当前+2h(40001)', c == 40001, m)
    q = steel.post('/inquiries', inq_body)
    inq_id = q['id']
    check('AC-07 创建询价 DRAFT', q['status'] == 'DRAFT', q)
    r = steel.post('/inquiries/%d/send' % inq_id)
    check('AC-07 发出后 SENT', r['status'] == 'SENT', r)
    det = steel.get('/inquiries/%d' % inq_id)
    check('AC-07 已邀请 3 家供应商', len(det.get('invites', [])) == 3, det.get('invites'))

    # ---- AC-08 密封报价与揭示 ----
    print('\n[AC-08] 密封报价与揭示')
    s, c, m = sup1.try_code('POST', '/inquiries/%d/reveal' % inq_id, {})
    check('AC-08 供应商不可揭示(40301)', c == 40301, m)
    deliver = (now + timedelta(days=8)).strftime('%Y-%m-%d')
    for cli, price in ((sup1, 818.00), (sup2, 815.00), (sup3, 812.00)):
        cli.post('/inquiries/%d/quotes' % inq_id,
                 {'price': price, 'quantity': 20000, 'deliveryDate': deliver, 'payTerms': 'T/T'})
        det = cli.get('/inquiries/%d' % inq_id)
        check('AC-08 供应商可见自己报价',
              det.get('myQuote', {}).get('status') == 'SUBMITTED', det.get('myQuote'))
    s, c, m = sup1.try_code('POST', '/inquiries/%d/quotes' % inq_id,
                            {'price': 810, 'quantity': 20000, 'deliveryDate': deliver})
    check('AC-08 重复报价被拦截(40902)', c == 40902, m)
    det = steel.get('/inquiries/%d' % inq_id)
    leak = [i for i in det.get('invites', []) if 'price' in i or 'quantity' in i]
    check('AC-08 截止前需方不可见任何报价', not leak, leak)
    s, c, m = steel.try_code('POST', '/inquiries/%d/reveal' % inq_id, {})
    check('AC-08 未截止不可揭示(40901)', c == 40901, m)
    pg_exec("UPDATE biz_inquiry SET deadline=now()-interval '5 minutes' WHERE id=%s", (inq_id,))
    snap = steel.post('/inquiries/%d/reveal' % inq_id)
    rows = snap.get('rows', [])
    check('AC-08 揭示生成 3 条比价快照', len(rows) == 3, snap)
    check('AC-08 快照按价格升序',
          [float(x['unitPrice']) for x in rows] == [812.0, 815.0, 818.0], rows)
    q3_id = rows[0]['quoteId']  # sup3 最低价

    # ---- T11 议价多轮 ----
    print('\n[T11] 议价多轮')
    b1 = steel.post('/bargains', {'quoteId': q3_id, 'price': 810.00, 'quantity': 20000,
                                  'extraTerms': '第 1 轮还价'})
    check('T11 发起还价 PENDING', b1.get('status') == 'PENDING' and b1.get('roundNo') == 1, b1)
    s, c, m = steel.try_code('PUT', '/bargains/%d/accept' % b1['id'], {})
    check('T11 发起方不可自答(40301)', c == 40301, m)
    sup3.put('/bargains/%d/accept' % b1['id'], {})
    for price in (808.00, 806.00):
        b = steel.post('/bargains', {'quoteId': q3_id, 'price': price, 'quantity': 20000,
                                     'extraTerms': '还价 %.2f' % price})
        sup3.put('/bargains/%d/accept' % b['id'], {})
    bl = steel.get('/bargains', quoteId=q3_id)['list']
    check('T11 三轮全部 ACCEPTED',
          [x['roundNo'] for x in bl] == [3, 2, 1] and all(x['status'] == 'ACCEPTED' for x in bl), bl)

    # ---- AC-12 定标生成订单 ----
    print('\n[AC-12] 定标生成订单')
    aw = steel.post('/inquiries/%d/award' % inq_id, {'quoteId': q3_id})
    oid = aw['orderId']
    check('AC-12 返回订单与确认期限', oid and bool(aw.get('confirmDeadline')), aw)
    od = steel.get('/orders/%d' % oid)
    check('AC-12 以议价接受价定标', float(od['unit_price']) == 806.0
          and float(od['quantity']) == 20000, od)
    check('AC-12 订单待供应商确认', od['status'] == 'PENDING_CONFIRM', od)
    det3 = sup3.get('/inquiries/%d' % inq_id)
    check('AC-12 中标报价 WIN', det3['myQuote']['status'] == 'WIN', det3.get('myQuote'))
    det2 = sup2.get('/inquiries/%d' % inq_id)
    check('AC-12 未中标报价 LOSE', det2['myQuote']['status'] == 'LOSE', det2.get('myQuote'))
    s, c, m = steel.try_code('POST', '/inquiries/%d/award' % inq_id, {'quoteId': q3_id})
    check('AC-12 重复定标被拦截(40901)', c == 40901, m)

    # ---- T12 供应商确认 ----
    print('\n[T12] 供应商订单确认')
    s, c, m = steel.try_code('PUT', '/orders/%d/confirm' % oid, {})
    check('T12 需方无确认权(40301)', c == 40301, m)
    sup3.put('/orders/%d/confirm' % oid, {})
    od2 = sup3.get('/orders/%d' % oid)
    check('T12 确认后待合同', od2['status'] == 'PENDING_CONTRACT', od2)

    # ---- AC-14 合同顺序签署 + AC-15 作废重签 ----
    print('\n[AC-14/15] 合同签署与作废重签')
    cg = steel.post('/orders/%d/contract/generate' % oid)
    c1 = cg['contractId']
    check('AC-14 生成合同 v1 待需方签', cg['version'] == 1 and cg['status'] == 'PENDING_BUYER', cg)
    cd = steel.get('/contracts/%d' % c1)
    check('AC-14 合同详情含订单', cd['order']['id'] == oid, cd.get('order'))
    s, c, m = steel.try_code('POST', '/contracts/%d/sign' % c1,
                             {'signerName': '需方经办', 'confirm': 'true'})
    check('AC-14 签署必须附盖章件(40001)', c == 40001, m)
    s, c, m = sup3.try_code('POST', '/contracts/%d/sign' % c1,
                            {'signerName': '供方经办', 'confirm': 'true', 'fileId': 'x'})
    check('AC-14 供方先签被拒(40901)', c == 40901, m)
    stamp1 = upload(steel, 'stamp-buyer-%s.pdf' % tag, PDF, 'application/pdf')
    r1 = steel.post('/contracts/%d/sign' % c1,
                    {'signerName': '需方经办', 'confirm': 'true', 'fileId': stamp1})
    check('AC-14 需方签署后待供方', r1['status'] == 'PENDING_SUPPLIER', r1)
    check('AC-14 记录盖章件 SHA-256',
          r1.get('fileSha256') == hashlib.sha256(PDF).hexdigest(), r1)
    vd = steel.post('/contracts/%d/void' % c1, {'reason': 'E2E：条款调整，作废重签'})
    check('AC-15 未完整签署合同可作废', vd['status'] == 'VOID', vd)
    odv = steel.get('/orders/%d' % oid)
    check('AC-15 作废后订单回到待生成合同', odv['status'] == 'PENDING_CONTRACT', odv)
    cg2 = steel.post('/orders/%d/contract/generate' % oid)
    c2 = cg2['contractId']
    check('AC-15 作废重签生成新版本', cg2['version'] == 2, cg2)
    s, c, m = sup3.try_code('POST', '/contracts/%d/sign' % c2,
                            {'signerName': '供方经办', 'confirm': 'true', 'fileId': stamp1})
    check('AC-15 v2 仍需需方先签(40901)', c == 40901, m)
    steel.post('/contracts/%d/sign' % c2,
               {'signerName': '需方经办', 'confirm': 'true', 'fileId': stamp1})
    stamp2 = upload(sup3, 'stamp-supplier-%s.png' % tag, PNG, 'image/png')
    r2 = sup3.post('/contracts/%d/sign' % c2,
                   {'signerName': '供方经办', 'confirm': 'true', 'fileId': stamp2})
    check('AC-14 双签后 EFFECTIVE', r2['status'] == 'EFFECTIVE', r2)
    cd2 = steel.get('/contracts/%d' % c2)
    check('AC-14 生效合同哈希为供方盖章件',
          cd2['file_hash'] == hashlib.sha256(PNG).hexdigest(), cd2.get('file_hash'))
    od3 = steel.get('/orders/%d' % oid)
    check('AC-14 双签后订单履约中', od3['status'] == 'PERFORMING', od3)
    s, c, m = steel.try_code('POST', '/contracts/%d/void' % c2, {'reason': '尝试作废已生效合同'})
    check('AC-15 已生效合同不可作废(40901)', c == 40901, m)

    # ---- T14 物流方案与运单 ----
    print('\n[T14] 物流方案与运单调度')
    plan = steel.post('/orders/%d/logistics-plan' % oid, {'orgMode': 'PLATFORM', 'remark': 'E2E 物流'})
    pid = plan['planId']
    check('T14 创建物流方案', bool(pid), plan)
    s, c, m = steel.try_code('POST', '/orders/%d/logistics-plan' % oid, {'orgMode': 'SELF'})
    check('T14 重复方案被拦截(40902)', c == 40902, m)
    wd = (now + timedelta(days=6)).strftime('%Y-%m-%d')
    seg = {'segmentNo': 'SEG-1', 'transportMode': 'ROAD', 'planQty': 10000,
           'planDepartDate': today, 'planArriveDate': wd,
           'departPlace': '曹妃甸港', 'arrivePlace': '青岛港'}
    s, c, m = steel.try_code('POST', '/logistics-plans/%d/waybills' % pid, dict(seg))
    check('T14 偏差超5%须填说明(40001)', c == 40001, m)
    w1 = steel.post('/logistics-plans/%d/waybills' % pid,
                    dict(seg, deviationReason='首段运力有限，剩余量由第二段补齐'))
    wid1 = w1['id']
    check('T14 分段1待指派', w1['status'] == 'PENDING_ASSIGN', w1)
    r = steel.put('/waybills/%d/assign' % wid1, {'carrierId': carrier_cid})
    check('T14 指派承运商', r['status'] == 'PENDING_ACCEPT', r)
    carrier.put('/waybills/%d/accept' % wid1, {})
    carrier.put('/waybills/%d/node' % wid1, {'node': 'DEPART', 'actualQty': 10000})
    carrier.put('/waybills/%d/node' % wid1, {'node': 'ARRIVE'})
    s, c, m = carrier.try_code('PUT', '/waybills/%d/node' % wid1, {'node': 'SIGN'})
    check('T14 承运商仅可回填发运/到达(40001)', c == 40001, m)
    steel.post('/waybills/%d/sign' % wid1, {})
    wl = steel.get('/waybills', orderId=oid)['list']
    st1 = next(x for x in wl if x['id'] == wid1)
    check('T14 需方签收后 SIGNED', st1['status'] == 'SIGNED', st1)
    w2 = steel.post('/logistics-plans/%d/waybills' % pid,
                    {'segmentNo': 'SEG-2', 'transportMode': 'SEA', 'planQty': 10000,
                     'planDepartDate': today, 'planArriveDate': wd,
                     'departPlace': '青岛港', 'arrivePlace': '湛江港', 'carrierId': carrier_cid})
    wid2 = w2['id']
    check('T14 创建即指派', w2['status'] == 'PENDING_ACCEPT', w2)
    carrier.put('/waybills/%d/accept' % wid2, {})
    carrier.put('/waybills/%d/node' % wid2, {'node': 'DEPART'})
    carrier.put('/waybills/%d/node' % wid2, {'node': 'ARRIVE'})
    steel.post('/waybills/%d/sign' % wid2, {})
    wl = steel.get('/waybills', orderId=oid)['list']
    check('T14 全部运单 SIGNED',
          len(wl) == 2 and all(x['status'] == 'SIGNED' for x in wl),
          [(x['id'], x['status']) for x in wl])

    # ---- T16 履约时间轴 ----
    print('\n[T16] 履约时间轴')
    tl = steel.get('/orders/%d/timeline' % oid)['list']
    check('T16 时间轴节点完整', len(tl) >= 10, '共 %d 个节点' % len(tl))
    codes = {x.get('nodeCode') or x.get('node_code') for x in tl}
    check('T16 含订单/合同/运单节点',
          {'ORDER_CREATED', 'CONTRACT_EFFECTIVE', 'WAYBILL_SIGNED'} <= codes, codes)

    # ---- T17 质检 + AC-19 预警 ----
    print('\n[T17/AC-19] 质检与预警')
    steel.post('/orders/%d/quality-check' % oid,
               {'arrivedQty': 25000, 'conclusion': 'ACCEPT', 'indicators': 'Fe 62.1%',
                'checkDesc': 'E2E 质检-超差触发预警'})
    als = steel.get('/alerts', bizType='ORDER', bizId=oid)['list']
    al = next((a for a in als if a.get('alertType') == 'QTY_DIFF'), None)
    check('AC-19 超差自动触发预警', al is not None, als)
    aid = al['id']
    r = steel.put('/alerts/%d/handle' % aid, {'action': 'PROCESSING', 'handlerRemark': 'E2E 处理中'})
    check('AC-19 预警转处理中', r['status'] == 'PROCESSING', r)
    s, c, m = steel.try_code('PUT', '/alerts/%d/handle' % aid, {'action': 'CLOSE'})
    check('AC-19 关闭须填处理意见(40001)', c == 40001, m)
    steel.put('/alerts/%d/handle' % aid, {'action': 'CLOSE', 'handlerRemark': '双方确认按实收结算'})
    steel.post('/orders/%d/quality-check' % oid,
               {'arrivedQty': 26000, 'conclusion': 'ACCEPT', 'checkDesc': 'E2E 重复超差'})
    als2 = steel.get('/alerts', bizType='ORDER', bizId=oid, alertType='QTY_DIFF')['list']
    # PRD AC-19"不重复"= 同对象同类型未关闭去重：已关闭的留痕保留，未关闭仅 1 条
    open2 = [a for a in als2 if a['status'] in ('PENDING', 'PROCESSING')]
    check('AC-19 未关闭同类预警去重', len(open2) == 1 and len(als2) == 2,
          [(a['id'], a['status']) for a in als2])
    steel.put('/alerts/%d/handle' % open2[0]['id'],
              {'action': 'CLOSE', 'handlerRemark': '双方确认按实收结算'})
    steel.post('/orders/%d/quality-check' % oid,
               {'arrivedQty': 20500, 'conclusion': 'ACCEPT', 'indicators': 'Fe 62.0%',
                'checkDesc': 'E2E 复检'})
    qcs = steel.get('/orders/%d/quality-checks' % oid)['list']
    check('T17 质检记录 3 条', len(qcs) == 3, [x['checkNo'] for x in qcs])

    # ---- T18 结算双向确认 ----
    print('\n[T18] 结算与双向确认')
    total = 806.00 * 20500
    st = steel.post('/orders/%d/settlements' % oid, {'settleDesc': 'E2E 结算'})
    sid_ = st['id']
    check('T18 结算数量默认最近质检实收', float(st['settle_qty']) == 20500, st)
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
    steel.post('/orders/%d/archive' % oid, {})
    od4 = steel.get('/orders/%d' % oid)
    check('T19 归档后订单 COMPLETED', od4['status'] == 'COMPLETED', od4)
    blob = dl_bytes(steel, '/orders/%d/archive/export' % oid)
    zf = zipfile.ZipFile(io.BytesIO(blob))
    check('T19 档案 zip 含 manifest.json',
          blob[:2] == b'PK' and 'manifest.json' in zf.namelist(), zf.namelist()[:5])

    # ---- AC-24 越权隔离与消息 ----
    print('\n[AC-24] 越权隔离与消息')
    s, c, m = sup2.try_code('GET', '/orders/%d' % oid)
    check('AC-24 无关方不可见订单(40301)', c == 40301, m)
    s, c, m = sup2.try_code('GET', '/settlements/%d' % sid_)
    check('AC-24 无关方不可见结算(40301)', c == 40301, m)
    s, c, m = sup2.try_code('GET', '/contracts/%d' % c2)
    check('AC-24 无关方不可见合同(40301)', c == 40301, m)
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
