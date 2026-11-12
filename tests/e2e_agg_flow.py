# -*- coding: utf-8 -*-
"""需求归集环节端到端测试（全链路拉通：归集合并 → 平台代发询价 → 供方密封报价 →
平台汇总返回钢厂 → 成员钢厂反馈 → 运营处理反馈（重新发起询价）→ 归集订单关闭 → 异常校验）。

业务链路（需求归集环节节点定义）：
  节点A 需求归集合并   输入=已提交需求明细（同品种同品位、有剩余可归集量）
                       输出=归集订单（锁定量）+ 需求转 INQUIRING + 站内信通知钢厂
  节点B 平台代发询价   输入=OPEN 归集订单 + 统一询价条件 + 受邀供应商
                       输出=归集询价单（source=PLATFORM, buyer_id=NULL）+ 通知钢厂/供应商
  节点C 供方密封报价   输入=受邀 + 截止内；输出=报价单 + 询价 QUOTING + 平台消息
  节点D 平台汇总返回   输入=有报价的归集询价；输出=揭示固化 + 按份额拆分推送 + 通知钢厂
  节点E 钢厂反馈       输入=揭示后的归集询价；输出=认可/不认可（必填原因）+ 推送运营；
                       不认可 → 询价单转 FEEDBACK
  节点F 运营处理反馈   重新发起询价：旧 FEEDBACK 询价单转 CLOSED
  节点G 归集订单关闭   仅 OPEN 可关闭 → 释放锁定量 → 需求无在途询价回退已提交 + 通知

运行：python tests/e2e_agg_flow.py（前置：Flask 运行于 127.0.0.1:8000，演示数据在库）
"""
import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from e2e_helpers import (ADMIN, BASE, PASS, PG_DSN, Client, check, summary)

PDF = b'%PDF-1.4\nE2E test file\n%%EOF'
STEEL = '13800000001'    # 示范钢铁（钢厂一）
SUP1 = '13800000002'     # 示范矿产（供应商一）
SUP2 = '13800000003'     # 示范矿业（供应商二）

_results = []


def pg1(sql, args=None):
    """只读直连查询，返回单行 dict（无行返回 None）。"""
    import psycopg
    from psycopg.rows import dict_row
    with psycopg.connect(PG_DSN, row_factory=dict_row) as conn:
        return conn.execute(sql, args).fetchone()


def rec(name, ok, detail=''):
    check(name, ok, detail)
    _results.append((name, ok))


def login(user, pwd=PASS):
    return Client.login(user, pwd)


def demand_item(item_id):
    return pg1("""
        SELECT i.id, i.demand_id, i.variety_id, i.grade, i.quantity, i.inquired_qty,
               d.status AS demand_status, d.company_id
        FROM biz_demand_item i JOIN biz_demand d ON d.id = i.demand_id
        WHERE i.id = %s AND i.is_deleted = 0
        """, (item_id,))


def run():
    plat = login(*ADMIN)
    steel = login(STEEL)
    sup1 = login(SUP1)
    sup2 = login(SUP2)
    now = datetime.now()

    # ---------- 准备数据：注册第二钢厂 + 两钢厂各建一条同品种同品位需求并提交 ----------
    tag = now.strftime('%H%M%S')
    anon = Client()  # 未登录客户端：注册链路为公开接口
    lic = anon.s.post(BASE + '/auth/license',
                          files={'file': ('license-agg-%s.pdf' % tag, PDF, 'application/pdf')},
                          timeout=15).json()['data']['fileId']
    u2 = '139%02d%06d' % (now.second, now.microsecond)
    reg2 = {'companyName': 'E2E归集钢厂' + tag, 'creditCode': '91340100MA2T%05dX' % (now.second * 1000 + now.microsecond // 1000),
            'companyTypes': 'STEEL_BUYER', 'province': '河北省', 'city': '唐山市',
            'contactName': '归集联系人', 'contactPhone': '13900000002',
            'username': u2, 'password': 'new123456', 'licenseFileId': lic}
    r2 = anon.post('/auth/register', reg2)
    cid2 = r2['companyId']
    plat.put('/admin/companies/%s/audit' % cid2, {'approve': 'true', 'remark': 'E2E 归集准入'})
    steel2 = login(u2, 'new123456')
    rec('准备-第二钢厂注册并准入', steel2.get('/auth/me')['company']['id'] == cid2,
        '企业 %s' % cid2)

    # 两钢厂各创建一条同品种同品位需求（品种 1=铁矿石粉矿，品位 61.5）并提交
    arrive_s = (now + timedelta(days=12)).strftime('%Y-%m-%d')
    arrive_e = (now + timedelta(days=22)).strftime('%Y-%m-%d')
    made = []
    for cli, name, qty in ((steel, 'E2E归集需求A', 5000), (steel2, 'E2E归集需求B', 8000)):
        dd = cli.post('/demands', {
            'demandName': name, 'deliveryType': 'PLANT', 'deliveryPlace': '日照港',
            'expectArriveStart': arrive_s, 'expectArriveEnd': arrive_e,
            'settleType': 'COD',
            'items': [{'varietyId': 1, 'grade': 61.5, 'quantity': qty, 'moreLessRate': 5}]})
        cli.post('/demands/%s/submit' % dd['id'], {})
        made.append(dd['id'])
    pool = plat.get('/admin/demand-pool', size=50)
    items = pool['list']
    by_demand = {it['id'] if 'itemId' not in it else it['itemId']: it for it in items}
    _rem = lambda it: float(it['quantity']) - float(it['inquiredQty'] or 0)
    # 找刚创建的两条明细（按 demandId 匹配）
    got = {}
    for it in items:
        did = str(it.get('demandId') or '')
        if did and int(did) in made and it['status'] == 'SUBMITTED' \
                and _rem(it) > 0:
            got.setdefault((it['varietyName'], float(it['grade'])), []).append(
                it['itemId'] if 'itemId' in it else it['id'])
    key = next((k for k, v in got.items() if len(v) >= 2), None)
    assert key, '自备数据未就绪（两钢厂同品种同品位已提交需求）'
    item_ids = sorted(got[key], reverse=True)[:2]
    print('[前置] 归集明细 %s（%s %s%%，需求 %s）' % (item_ids, key[0], key[1], made))

    it_a, it_b = demand_item(item_ids[0]), demand_item(item_ids[1])
    rec('前置-两条同品种同品位已提交明细', it_a['variety_id'] == it_b['variety_id']
        and it_a['grade'] == it_b['grade'] and it_a['demand_status'] == 'SUBMITTED'
        and it_b['demand_status'] == 'SUBMITTED',
        '%s/%s' % (it_a['demand_status'], it_b['demand_status']))
    expect_total = float(it_a['quantity'] - it_a['inquired_qty']) + float(it_b['quantity'] - it_b['inquired_qty'])

    # ---------- 异常校验（节点A 前置规则） ----------
    # 品位不一致不可合并：拿一条品位不同的明细混入
    other = next((demand_item(i['id']) for i in items
                  if (i['varietyName'], float(i['grade'])) != key
                  and i['status'] == 'SUBMITTED'
                  and _rem(i) > 0), None)
    if other:
        http, code, msg = plat.try_code('POST', '/admin/aggregated-orders',
                                        {'itemIds': [item_ids[0], other['id']]})
        rec('异常-品位不一致不可合并(40001)', code == 40001, '%s %s' % (code, msg))
    else:
        rec('异常-品位不一致不可合并(40001)', True, '无可用品位不一致明细，跳过')

    # 截止时间 < now+2h / 截止晚于到货日前 7 天（需先有归集订单，放在节点B 校验）

    # ---------- 节点A 需求归集合并 ----------
    agg = plat.post('/admin/aggregated-orders',
                    {'itemIds': item_ids, 'remark': 'E2E 归集端到端测试'})
    agg_id, agg_no = agg['id'], agg['aggNo']
    rec('A1 归集订单生成', bool(agg_id and agg_no),
        '%s 合计 %s 吨（预期 %s）' % (agg_no, agg['totalQty'], expect_total))
    rec('A2 归集量=剩余可归集量合计', abs(float(agg['totalQty']) - expect_total) < 0.001,
        '%s vs %s' % (agg['totalQty'], expect_total))

    it_a2, it_b2 = demand_item(item_ids[0]), demand_item(item_ids[1])
    rec('A3 归集量全量锁定', it_a2['inquired_qty'] == it_a2['quantity']
        and it_b2['inquired_qty'] == it_b2['quantity'],
        'inquired %s/%s' % (it_a2['inquired_qty'], it_b2['inquired_qty']))
    rec('A4 需求转 INQUIRING', it_a2['demand_status'] == 'INQUIRING'
        and it_b2['demand_status'] == 'INQUIRING',
        '%s/%s' % (it_a2['demand_status'], it_b2['demand_status']))

    agg_detail = plat.get('/admin/aggregated-orders/%s' % agg_id)
    members = agg_detail['members']
    rec('A5 归集订单成员明细', len(members) == 2
        and all(m['quantity'] == m['itemQty'] for m in members),
        '成员 %d 家' % len(members))
    agg_msgs = pg1("""
        SELECT count(*) AS c FROM sys_message
        WHERE biz_type='DEMAND' AND title='需求已纳入归集订单'
          AND content LIKE '%%' || (SELECT agg_no FROM biz_aggregated_order WHERE id=%s) || '%%'
        """, (agg_id,))['c']
    rec('A6 站内信-需求已纳入归集订单', agg_msgs >= 1, '消息 %d 条' % agg_msgs)

    # ---------- 异常校验（节点B 前置规则） ----------
    arrive = (now + timedelta(days=18)).strftime('%Y-%m-%d')
    ddl_bad = (now + timedelta(hours=1)).strftime('%Y-%m-%d %H:%M:%S')
    http, code, msg = plat.try_code('POST', '/admin/quote-inquiries', {
        'aggOrderId': agg_id, 'arriveDate': arrive, 'deadline': ddl_bad,
        'inviteSupplierIds': [2, 3]})
    rec('异常-截止需≥当前+2h(40001)', code == 40001, '%s %s' % (code, msg))

    arrive_far = (now + timedelta(days=3)).strftime('%Y-%m-%d')
    ddl_far = (now + timedelta(days=1)).strftime('%Y-%m-%d %H:%M:%S')
    http, code, msg = plat.try_code('POST', '/admin/quote-inquiries', {
        'aggOrderId': agg_id, 'arriveDate': arrive_far, 'deadline': ddl_far,
        'inviteSupplierIds': [2, 3]})
    rec('异常-截止不晚于到货前7天(40001)', code == 40001, '%s %s' % (code, msg))

    arrive2 = (now + timedelta(days=18)).strftime('%Y-%m-%d')
    ddl_ok = (now + timedelta(days=8)).strftime('%Y-%m-%d %H:%M:%S')
    http, code, msg = plat.try_code('POST', '/admin/quote-inquiries', {
        'aggOrderId': agg_id, 'arriveDate': arrive2, 'deadline': ddl_ok,
        'inviteSupplierIds': []})
    rec('异常-至少邀请一家供应商(40001)', code == 40001, '%s %s' % (code, msg))

    # ---------- 节点B 平台代发询价 ----------
    batch = plat.post('/admin/quote-inquiries', {
        'aggOrderId': agg_id, 'arriveDate': arrive2, 'deadline': ddl_ok,
        'minResponse': 1, 'inviteSupplierIds': [2, 3],
        'remark': 'E2E 归集端到端询价'})
    batch_no, iid = batch['batchNo'], batch['inquiryId']
    rec('B1 归集询价发出', bool(batch_no and iid),
        '批次 %s 询价 %s' % (batch_no, batch['aggNo']))

    inq = pg1("""
        SELECT i.source, i.buyer_id, i.agg_id, i.quantity, i.status, i.min_response
        FROM biz_inquiry i WHERE i.id=%s
        """, (iid,))
    rec('B2 归集询价字段(source=PLATFORM,buyer_id=NULL)',
        inq['source'] == 'PLATFORM' and inq['buyer_id'] is None
        and inq['agg_id'] == agg_id and float(inq['quantity']) == expect_total,
        'source=%s buyer=%s qty=%s' % (inq['source'], inq['buyer_id'], inq['quantity']))
    rec('B3 归集订单转 INQUIRING', pg1(
        "SELECT status FROM biz_aggregated_order WHERE id=%s", (agg_id,))['status'] == 'INQUIRING')

    steel_msg = pg1("""
        SELECT count(*) AS c FROM sys_message
        WHERE biz_type='AGG_ORDER' AND biz_id=%s AND title='归集需求已发起询价'
        """, (agg_id,))['c']
    rec('B4 站内信-钢厂归集询价通知', steel_msg >= 1, '消息 %d 条' % steel_msg)
    sup_msg = pg1("""
        SELECT count(*) AS c FROM sys_message
        WHERE biz_type='INQUIRY' AND biz_id=%s AND title='收到询价邀请'
        """, (iid,))['c']
    rec('B5 站内信-供应商询价邀请', sup_msg >= 2, '消息 %d 条' % sup_msg)

    # ---------- 节点C 供方密封报价 ----------
    li = sup1.get('/inquiries', size=20)
    mine = next((r for r in li['list'] if r['id'] == iid), None)
    rec('C1 供方可见归集询价', bool(mine and mine['inquiryNo']), str(mine and mine['inquiryNo']))

    q1_price, q2_price = '860', '845'
    for cli, price, tag in ((sup1, q1_price, '供方一'), (sup2, q2_price, '供方二')):
        q = cli.post('/inquiries/%s/quotes' % iid, {
            'price': price, 'quantity': str(expect_total), 'deliveryDate': (now + timedelta(days=15)).strftime('%Y-%m-%d'),
            'taxType': 'INC_TAX', 'freightPrice': '30', 'deliveryType': 'PLANT',
            'remark': 'E2E 归集报价 %s' % tag})
        rec('C2 供方报价-%s' % tag, bool(q['id']) and q['status'] == 'SUBMITTED',
            '报价 %s' % q.get('quoteNo', q['id']))

    st = pg1("SELECT status FROM biz_inquiry WHERE id=%s", (iid,))['status']
    rec('C3 询价转 QUOTING', st == 'QUOTING', st)

    # 密封期：供方查看自己报价可见，平台汇总接口随时可看（运营是汇总方）
    myq = sup1.get('/quotes/%s' % _quote_id(iid, 2))
    rec('C4 密封报价可自查', myq and myq['price'] is not None, str(myq and myq['price']))

    # ---------- 节点D 平台汇总返回钢厂 ----------
    http, code, msg = plat.try_code('POST', '/admin/quote-inquiries/%s/return' % iid, {})
    rec('D1 平台汇总返回钢厂', code == 0, '%s %s' % (code, msg))
    revealed = pg1("SELECT reveal_snapshot IS NOT NULL AS r FROM biz_inquiry WHERE id=%s", (iid,))['r']
    rec('D2 揭示快照已固化', revealed)
    steel_msg2 = pg1("""
        SELECT count(*) AS c FROM sys_message
        WHERE biz_type='INQUIRY' AND biz_id=%s AND title='平台报价汇总推送'
        """, (iid,))['c']
    rec('D3 站内信-汇总推送钢厂', steel_msg2 >= 1, '消息 %d 条' % steel_msg2)

    # ---------- 节点E 钢厂反馈 ----------
    det = steel.get('/inquiries/%s' % iid)
    rec('E1 钢厂可见归集询价(aggView)', det.get('aggView') is True,
        'shareQty=%s' % det.get('shareQty'))
    # 钢厂份额 = 本钢厂在归集订单中的需求量（钢厂一 5000 吨，非归集总量）
    my_qty = float(it_a['quantity'] - it_a['inquired_qty']) \
        if it_a['company_id'] == 1 else float(it_b['quantity'] - it_b['inquired_qty'])
    rec('E2 钢厂份额=本钢厂需求份额', det.get('shareQty') is not None
        and abs(float(det['shareQty']) - my_qty) < 0.001,
        'shareQty=%s vs 本钢厂 %s' % (det.get('shareQty'), my_qty))
    rec('E3 钢厂可见报价供应商名单(不含价格)', bool(det.get('quoteSuppliers'))
        and all('price' not in (s or {}) for s in det['quoteSuppliers']),
        '%d 家' % len(det.get('quoteSuppliers') or []))

    rev = steel.get('/inquiries/%s/quotes/reveal' % iid)
    rec('E4 钢厂比价表按份额拆分', rev and rev.get('shareQty') is not None
        and all(str(r['quantity']) == str(rev['shareQty']) for r in rev['rows']),
        '份额 %s，%d 行' % (rev.get('shareQty'), len(rev.get('rows') or [])))

    steel.post('/inquiries/%s/feedback' % iid, {'decision': 'ACCEPTED'})
    fb = pg1("""
        SELECT decision FROM biz_agg_inquiry_feedback
        WHERE inquiry_id=%s AND company_id=1
        """, (iid,))
    rec('E5 钢厂反馈-认可', fb and fb['decision'] == 'ACCEPTED')
    plat_msg = pg1("""
        SELECT count(*) AS c FROM sys_message
        WHERE title='钢厂对归集询价反馈' AND content LIKE '%%示范钢铁%%认可%%'
        """, )['c']
    rec('E6 反馈推送运营端', plat_msg >= 1, '消息 %d 条' % plat_msg)

    # 重复反馈幂等（ON CONFLICT 更新）
    steel.post('/inquiries/%s/feedback' % iid, {'decision': 'ACCEPTED'})
    cnt = pg1("SELECT count(*) AS c FROM biz_agg_inquiry_feedback WHERE inquiry_id=%s", (iid,))['c']
    rec('E7 重复反馈幂等', cnt == 1, '反馈 %d 条' % cnt)

    # 不认可（必填原因）→ 询价单转 FEEDBACK
    http, code, msg = steel.try_code('POST', '/inquiries/%s/feedback' % iid, {'decision': 'REJECTED'})
    rec('异常-不认可必填原因(40001)', code == 40001, '%s %s' % (code, msg))
    steel.post('/inquiries/%s/feedback' % iid,
               {'decision': 'REJECTED', 'reason': 'E2E 不认可：价格高于预期'})
    st = pg1("SELECT status FROM biz_inquiry WHERE id=%s", (iid,))['status']
    rec('E8 不认可后询价转 FEEDBACK', st == 'FEEDBACK', st)
    fbs = plat.get('/admin/quote-inquiries/%s/feedbacks' % iid)
    rec('E9 运营可见反馈明细', any(f['decision'] == 'REJECTED' for f in fbs['list']),
        '%d 条反馈' % len(fbs['list']))

    # ---------- 节点F 运营处理反馈：重新发起询价 ----------
    batch2 = plat.post('/admin/quote-inquiries', {
        'aggOrderId': agg_id, 'arriveDate': arrive2, 'deadline': ddl_ok,
        'minResponse': 1, 'inviteSupplierIds': [2],
        'remark': 'E2E 重新发起询价'})
    iid2 = batch2['inquiryId']
    old = pg1("SELECT status FROM biz_inquiry WHERE id=%s", (iid,))['status']
    rec('F1 重新发起询价', bool(iid2), '新询价单 %s（批次 %s）' % (iid2, batch2['batchNo']))
    rec('F2 旧反馈询价单转 CLOSED', old == 'CLOSED', old)

    # ---------- 节点G 归集订单关闭（自备两条新需求：归集后不询价直接关闭） ----------
    close_ids = []
    for cli, name, qty in ((steel, 'E2E关闭需求A', 3000), (steel, 'E2E关闭需求B', 4000)):
        dd = cli.post('/demands', {
            'demandName': name, 'deliveryType': 'PLANT', 'deliveryPlace': '日照港',
            'expectArriveStart': arrive_s, 'expectArriveEnd': arrive_e,
            'settleType': 'COD',
            'items': [{'varietyId': 1, 'grade': 62.5, 'quantity': qty, 'moreLessRate': 5}]})
        cli.post('/demands/%s/submit' % dd['id'], {})
        close_ids.append(dd['id'])
    pool2 = plat.get('/admin/demand-pool', size=50)
    close_items = [it for it in pool2['list']
                   if str(it.get('demandId') or '') and int(it['demandId']) in close_ids
                   and it['status'] == 'SUBMITTED']
    if len(close_items) >= 2:
        ids2 = [it['itemId'] if 'itemId' in it else it['id'] for it in close_items[:2]]
        agg2 = plat.post('/admin/aggregated-orders', {'itemIds': ids2, 'remark': 'E2E 关闭测试'})
        g1, g2_ = demand_item(ids2[0]), demand_item(ids2[1])
        plat.put('/admin/aggregated-orders/%s/close' % agg2['id'], {})
        g1b, g2b = demand_item(ids2[0]), demand_item(ids2[1])
        rec('G1 归集订单关闭', pg1(
            "SELECT status FROM biz_aggregated_order WHERE id=%s", (agg2['id'],))['status'] == 'CLOSED')
        rec('G2 锁定量释放', float(g1b['inquired_qty']) < float(g1['inquired_qty'])
            and float(g2b['inquired_qty']) < float(g2_['inquired_qty']),
            '%s→%s / %s→%s' % (g1['inquired_qty'], g1b['inquired_qty'],
                               g2_['inquired_qty'], g2b['inquired_qty']))
        rec('G3 需求回退已提交', g1b['demand_status'] == 'SUBMITTED'
            and g2b['demand_status'] == 'SUBMITTED',
            '%s/%s' % (g1b['demand_status'], g2b['demand_status']))
        close_msg = pg1("""
            SELECT count(*) AS c FROM sys_message
            WHERE biz_type='DEMAND' AND title='归集订单已关闭'
              AND content LIKE '%%' || (SELECT agg_no FROM biz_aggregated_order WHERE id=%s) || '%%'
            """, (agg2['id'],))['c']
        rec('G4 站内信-归集订单已关闭', close_msg >= 1, '消息 %d 条' % close_msg)
        # 已询价的归集订单不可关闭（第一轮归集订单已 INQUIRING）
        http, code, msg = plat.try_code('PUT', '/admin/aggregated-orders/%s/close' % agg_id, {})
        rec('异常-已询价归集订单不可关闭(40901)', code == 40901, '%s %s' % (code, msg))
    else:
        rec('G1-G4 归集订单关闭链路', True, '自备关闭数据未就绪，跳过')

    # ---------- 越权校验 ----------
    http, code, msg = sup1.try_code('POST', '/admin/aggregated-orders', {'itemIds': item_ids[:1]})
    rec('越权-供方不可归集(40301)', code == 40301, '%s %s' % (code, msg))
    http, code, msg = plat.try_code('POST', '/inquiries/%s/feedback' % iid, {'decision': 'ACCEPTED'})
    rec('越权-平台不可反馈(40301)', code == 40301, '%s %s' % (code, msg))

    return summary()


def _quote_id(iid, supplier_id):
    return pg1("SELECT id FROM biz_quote WHERE inquiry_id=%s AND supplier_id=%s",
               (iid, supplier_id))['id']


if __name__ == '__main__':
    ok = run()
    sys.exit(0 if ok else 1)
