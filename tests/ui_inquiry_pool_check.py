# -*- coding: utf-8 -*-
"""运营端「需求归集 → 询价单列表」Tab 回归：
钢厂提交询价单进入归集池 → 勾选合并归集入口存在 → 截图 ui_inquiry_pool_admin_20261118.png
"""
import os
import sys
import time
from datetime import datetime, timedelta

import requests
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.edge.options import Options
from selenium.webdriver.edge.service import Service

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHOTS = os.path.join(BASE, 'docs', 'shots')
API = 'http://127.0.0.1:8000/api/v1'
FAILS = []


def check(name, cond, extra=''):
    print(('PASS ' if cond else 'FAIL ') + name + (('  ' + str(extra)) if extra else ''))
    if not cond:
        FAILS.append(name)


def seed():
    """钢厂：需求 6000 提交 + 询价 6000 提交（进入运营端询价归集池）。"""
    s = requests.Session()
    tok = s.post(API + '/auth/login', json={'username': '13800000001', 'password': 'demo123456'},
                 timeout=10).json()['data']['token']
    s.headers['Authorization'] = 'Bearer ' + tok
    vid = {v['varietyName']: v['id'] for v in
           s.get(API + '/base/varieties', timeout=10).json()['data']['list']}['中华混一号']
    d0 = datetime.now()
    p = {'demandName': '归集池验证', 'deliveryType': 'PLANT', 'deliveryPlace': '河北陆港保税',
         'expectArriveStart': (d0 + timedelta(days=12)).strftime('%Y-%m-%d'),
         'expectArriveEnd': (d0 + timedelta(days=40)).strftime('%Y-%m-%d'),
         'settleType': 'PREPAY',
         'items': [{'varietyId': vid, 'grade': '61.5', 'quantity': 6000,
                    'cycleType': 'MONTH', 'cycleYear': d0.year, 'cycleValue': d0.month}]}
    did = s.post(API + '/demands', json=p, timeout=10).json()['data']['id']
    s.post(API + '/demands/%d/submit' % did, timeout=10)
    it = s.get(API + '/demands/%d' % did, timeout=10).json()['data']['items'][0]
    dl = (d0 + timedelta(hours=3)).strftime('%Y-%m-%d %H:%M:%S')
    r = s.post(API + '/inquiries', json={
        'demandId': did, 'demandItemId': it['id'], 'quantity': 6000,
        'arriveDate': p['expectArriveStart'], 'deadline': dl}, timeout=10).json()['data']
    s.post(API + '/inquiries/%d/send' % r['id'], timeout=10)
    return r['id']


def main():
    seed()
    o = Options()
    o.add_argument('--headless=new')
    o.add_argument('--window-size=1440,1000')
    o.add_argument('--disable-gpu')
    o.add_argument('--log-level=3')
    d = webdriver.Edge(options=o, service=Service())
    d.set_page_load_timeout(40)
    try:
        d.get('http://127.0.0.1:8000/#/login')
        d.find_element(By.CSS_SELECTOR, 'input[placeholder*="手机号"],input[type="text"]').send_keys('13800000000')
        d.find_element(By.CSS_SELECTOR, 'input[type="password"]').send_keys('admin123456')
        d.find_element(By.XPATH, "//button[contains(.,'登')]").click()
        time.sleep(1.8)
        d.get('http://127.0.0.1:8000/#/demand-pool')
        time.sleep(2.0)
        d.find_element(By.XPATH, "//button[@data-tab='inqs']").click()
        time.sleep(1.2)
        body = d.find_element(By.CSS_SELECTOR, '.card').text
        check('询价单列表 Tab 打开', '询价单号' in body, body[:120])
        check('池内出现钢厂询价单', 'XJ-' in body)
        check('合并归集按钮存在', '合并归集' in body)
        check('列含申报周期', '申报周期' in body)
        d.get_screenshot_as_file(os.path.join(SHOTS, 'ui_inquiry_pool_admin_20261118.png'))
    finally:
        d.quit()
    print('\n%s' % ('ALL PASS' if not FAILS else 'FAILED: ' + ', '.join(FAILS)))
    if FAILS:
        sys.exit(1)


if __name__ == '__main__':
    main()
