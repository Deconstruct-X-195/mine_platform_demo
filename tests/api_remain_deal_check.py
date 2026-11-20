# -*- coding: utf-8 -*-
"""剩余可询量随成交自动更新 回归：
口径 剩余可询 = 明细数量 - 在途询价锁定量(inquired_qty) - 已成交吨数(deal_qty)
  D1) 发出询价锁量 → 剩余减少；超量创建被拒；流标归还 → 剩余恢复
  D2) 归集整单询价 → 供应商报价 → 揭示 → 钢厂认可自动定标成单 →
      deal_qty 回填、锁定量释放、剩余可询归零、需求转已成交、再创建询价被拒
"""
import os
import sys
from datetime import datetime, timedelta

import psycopg
import requests

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)
from backend.db import DEFAULT_DSN  # noqa: E402

API = 'http://127.0.0.1:8000/api/v1'
FAILS = []


def check(name, cond, extra=''):
    print(('PASS ' if cond else 'FAIL ') + name + (('  ' + str(extra)) if extra else ''))
    if not cond:
        FAILS.append(name)


def login(s, user, pwd):
    r = s.post(API + '/auth/login', json={'username': user, 'password': pwd}, timeout=10)
    tok = r.json()['data']['token']
    s.headers['Authorization'] = 'Bearer ' + tok
    return r.json()['data']


def api(s, method, path, **kw):
    r = s.request(method, API + path, timeout=15, **kw)
    body = {}
    try:
        body = r.json()
    except Exception:
        pass
    return r.status_code, body


def item_of(s, did):
    st, d = api(s, 'GET', '/demands/%d' % did)
    it = d['data']['items'][0]
    return it, d['data']['status']


def main():
    steel = requests.Session()
    login(steel, '13800000001', 'demo123456')
    _, vs = api(steel, 'GET', '/base/varieties')
    vid = {v['varietyName']: v['id'] for v in vs['data']['list']}['PB粉']
    d0 = datetime.now()
    start = (d0 + timedelta(days=12)).strftime('%Y-%m-%d')
    end = (d0 + timedelta(days=40)).strftime('%Y-%m-%d')

    def mk_demand(qty, name):
        p = {'demandName': name, 'deliveryType': 'PLANT', 'deliveryPlace': '河北陆港保税',
             'expectArriveStart': start, 'expectArriveEnd': end, 'settleType': 'PREPAY',
             'items': [{'varietyId': vid, 'grade': '62', 'quantity': qty,
                        'cycleType': 'MONTH', 'cycleYear': d0.year, 'cycleValue': d0.month}]}
        _, r = api(steel, 'POST', '/demands', json=p)
        did = r['data']['id']
        api(steel, 'POST', '/demands/%d/submit' % did)
        return did

    deadline = (d0 + timedelta(hours=3)).strftime('%Y-%m-%dT%H:%M')

    # ---- D1：锁量 / 超量校验 / 流标归还 ----
    d1 = mk_demand(12000, '回归-锁量')
    it1, _ = item_of(steel, d1)
    check('D1 初始剩余=12000', float(it1['remainQty']) == 12000, it1['remainQty'])
    _, r = api(steel, 'POST', '/inquiries', json={
        'demandId': d1, 'demandItemId': it1['id'], 'quantity': 3000,
        'arriveDate': start, 'deadline': deadline.replace('T', ' ') + ':00'})
    iid1 = r['data']['id']
    api(steel, 'POST', '/inquiries/%d/send' % iid1)
    it1, _ = item_of(steel, d1)
    check('D1 发出询价后剩余=9000', float(it1['remainQty']) == 9000, it1['remainQty'])
    st, r = api(steel, 'POST', '/inquiries', json={
        'demandId': d1, 'demandItemId': it1['id'], 'quantity': 10000,
        'arriveDate': start, 'deadline': deadline.replace('T', ' ') + ':00'})
    check('D1 超剩余可询创建被拒', r.get('code') == 40001, (st, r.get('message')))
    _, r = api(steel, 'POST', '/inquiries/%d/fail' % iid1, json={'reason': '回归-流标归还'})
    check('D1 流标成功', r.get('code') == 0, r.get('message'))
    it1, _ = item_of(steel, d1)
    check('D1 流标后剩余恢复=12000', float(it1['remainQty']) == 12000, it1['remainQty'])

    # ---- D2：钢厂询价单 → 运营端按单归集 → 总询价单 → 供应商报价 → 认可自动成单 ----
    d2 = mk_demand(12000, '回归-成交')
    it2, _ = item_of(steel, d2)
    _, r = api(steel, 'POST', '/inquiries', json={
        'demandId': d2, 'demandItemId': it2['id'], 'quantity': 12000,
        'arriveDate': start, 'deadline': deadline.replace('T', ' ') + ':00'})
    iid_x = r['data']['id']
    api(steel, 'POST', '/inquiries/%d/send' % iid_x)
    it2, _ = item_of(steel, d2)
    check('D2 发单后剩余=0（全量锁定）', float(it2['remainQty']) == 0, it2['remainQty'])
    plat = requests.Session()
    login(plat, '13800000000', 'admin123456')
    _, r = api(plat, 'GET', '/admin/inquiry-pool')
    check('D2 询价单进入归集池', r.get('code') == 0
          and any(x['inquiryId'] == iid_x for x in r['data']['list']), r.get('message'))
    _, r = api(plat, 'POST', '/admin/aggregated-orders', json={'inquiryIds': [iid_x]})
    check('D2 按询价单归集成功(量=12000)', r.get('code') == 0 and float(r['data']['totalQty']) == 12000, r)
    aid = r['data']['id']
    _, r = api(steel, 'GET', '/inquiries/%d' % iid_x)
    check('D2 钢厂询价单转已归集', r['data']['status'] == 'AGGREGATED', r['data']['status'])
    sup = requests.Session()
    sup_user = login(sup, '13800000002', 'demo123456')['user']
    sup_cid = sup_user['company']['id']
    _, r = api(plat, 'POST', '/admin/quote-inquiries', json={
        'aggOrderId': aid, 'arriveDate': start,
        'deadline': deadline.replace('T', ' ') + ':00', 'inviteSupplierIds': [sup_cid]})
    check('D2 总询价单发出', r.get('code') == 0, r)
    iid2 = r['data']['inquiryId']
    _, r = api(sup, 'POST', '/inquiries/%d/quotes' % iid2, json={
        'price': '855', 'quantity': '12000', 'deliveryDate': (d0 + timedelta(days=10)).strftime('%Y-%m-%d'),
        'taxType': 'INC_TAX', 'freightPrice': '30', 'deliveryType': 'PORT_TRUCK'})
    check('D2 供应商报价成功', r.get('code') == 0, r)
    with psycopg.connect(DEFAULT_DSN) as conn:
        conn.execute("UPDATE biz_inquiry SET deadline=now()-interval '2 hours' WHERE id=%s", (iid2,))
        conn.commit()
    _, r = api(steel, 'POST', '/inquiries/%d/reveal' % iid2)
    check('D2 截止揭示', r.get('code') == 0, r)
    _, r = api(steel, 'POST', '/inquiries/%d/feedback' % iid2, json={'decision': 'ACCEPTED'})
    check('D2 全员认可自动定标', r.get('code') == 0 and r['data'].get('autoAward'), r)
    it2, st2 = item_of(steel, d2)
    check('D2 成交后剩余可询=0', float(it2['remainQty']) == 0, it2['remainQty'])
    check('D2 已成交吨数=12000', float(it2['dealQty']) == 12000, it2['dealQty'])
    check('D2 需求转已成交', st2 == 'DEALT', st2)
    _, r = api(steel, 'GET', '/inquiries/%d' % iid_x)
    check('D2 钢厂询价单随总单定标', r['data']['status'] == 'AWARDED', r['data']['status'])
    st, r = api(steel, 'POST', '/inquiries', json={
        'demandId': d2, 'demandItemId': it2['id'], 'quantity': 100,
        'arriveDate': start, 'deadline': deadline.replace('T', ' ') + ':00'})
    check('D2 已成交需求再询价被拒', r.get('code') == 40901, (st, r.get('message')))

    print('\n%s' % ('ALL PASS' if not FAILS else 'FAILED: ' + ', '.join(FAILS)))
    if FAILS:
        sys.exit(1)


if __name__ == '__main__':
    main()
