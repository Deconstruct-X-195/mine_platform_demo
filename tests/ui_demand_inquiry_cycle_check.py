# -*- coding: utf-8 -*-
"""需求申报周期 + 采购询价改版回归：
1) 需求单列表列「申报周期」（替代期望到货时间）与详情弹窗申报周期行；
2) 采购询价页批量按钮（新增询价/更改/删除/提交/导出）；
3) 新增询价关联需求单：月度需求直接填报（信息不改）、季度需求出现「本月采购计划」框。
输出 docs/shots/ui_{demand,inquiry}_*_20261117.png
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
from selenium.webdriver.support.ui import Select

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHOTS = os.path.join(BASE, 'docs', 'shots')
os.makedirs(SHOTS, exist_ok=True)
URL = 'http://127.0.0.1:8000'
API = URL + '/api/v1'
FAILS = []


def check(name, cond, extra=''):
    print(('PASS ' if cond else 'FAIL ') + name + ('  ' + extra if extra and not cond else ''))
    if not cond:
        FAILS.append(name)


def api_seed():
    """API 造数：月度需求（PB粉 2026-12）+ 季度需求（中华混一号 2027Q1）并提交。"""
    s = requests.Session()
    r = s.post(API + '/auth/login', json={'username': '13800000001', 'password': 'demo123456'}, timeout=10)
    tok = r.json()['data']['token']
    h = {'Authorization': 'Bearer ' + tok}
    vs = s.get(API + '/base/varieties', headers=h, timeout=10).json()['data']['list']
    vid = {v['varietyName']: v['id'] for v in vs}
    d0 = datetime.now()
    start = (d0 + timedelta(days=12)).strftime('%Y-%m-%d')
    end = (d0 + timedelta(days=40)).strftime('%Y-%m-%d')
    ids = {}
    for name, item in (
        ('月度', {'varietyId': vid['PB粉'], 'grade': '62', 'quantity': 5000,
                  'cycleType': 'MONTH', 'cycleYear': d0.year, 'cycleValue': d0.month}),
        ('季度', {'varietyId': vid['中华混一号'], 'grade': '61.5', 'quantity': 9000,
                  'cycleType': 'QUARTER', 'cycleYear': d0.year + (1 if d0.month >= 10 else 0),
                  'cycleValue': 1}),
    ):
        payload = {
            'demandName': '验证-' + name, 'deliveryType': 'PLANT', 'deliveryPlace': '河北陆港保税',
            'expectArriveStart': start, 'expectArriveEnd': end,
            'settleType': 'PREPAY', 'qualityReq': '', 'items': [item],
        }
        rid = s.post(API + '/demands', json=payload, headers=h, timeout=10).json()['data']['id']
        s.post(API + '/demands/%d/submit' % rid, headers=h, timeout=10)
        ids[name] = rid
        print('seeded 验证-' + name + ' demand id=' + str(rid))
    return ids


def drv():
    o = Options()
    o.add_argument('--headless=new')
    o.add_argument('--window-size=1440,1000')
    o.add_argument('--disable-gpu')
    o.add_argument('--log-level=3')
    d = webdriver.Edge(options=o, service=Service())
    d.set_page_load_timeout(40)
    return d


def login_ui(d):
    d.get(URL + '/#/login')
    d.find_element(By.CSS_SELECTOR, 'input[placeholder*="手机号"],input[type="text"]').send_keys('13800000001')
    d.find_element(By.CSS_SELECTOR, 'input[type="password"]').send_keys('demo123456')
    d.find_element(By.XPATH, "//button[contains(.,'登')]").click()
    time.sleep(1.8)


def headers_of(d):
    return [e.text.strip() for e in d.find_elements(By.CSS_SELECTOR, '.card thead th')]


def close_modal(d):
    for x in d.find_elements(By.CSS_SELECTOR, '.modal-head .close'):
        if x.is_displayed():
            x.click()
            time.sleep(0.4)
            return


def pick_demand_option(d, key):
    """key: '季度' 选季度需求，否则选月度需求（按下拉选项文案判断）。"""
    sel_el = d.find_element(By.CSS_SELECTOR, '.modal .form-grid select')
    sel = Select(sel_el)
    target = None
    for opt in sel.options:
        t = opt.text
        is_q = '季度' in t
        if (key == '季度') == is_q:
            target = t
            break
    if not target:
        return False
    sel.select_by_visible_text(target)
    time.sleep(0.6)
    return True


def main():
    api_seed()
    d = drv()
    try:
        login_ui(d)

        # ---- 需求管理：列表申报周期列 ----
        d.get(URL + '/#/demand')
        time.sleep(2.0)
        ths = headers_of(d)
        check('需求列表列含[申报周期]', any('申报周期' in t for t in ths), str(ths))
        check('需求列表列不含[期望到货时间]', not any('期望到货时间' in t for t in ths), str(ths))
        d.save_shots = None
        d.find_elements(By.CSS_SELECTOR, '.card')[0].screenshot(os.path.join(SHOTS, 'ui_demand_cycle_list_20261117.png')) \
            if False else d.get_screenshot_as_file(os.path.join(SHOTS, 'ui_demand_cycle_list_20261117.png'))

        # ---- 需求详情：申报周期行 ----
        d.find_elements(By.CSS_SELECTOR, '.card table button.sm')[0].click()
        time.sleep(1.0)
        modal_txt = d.find_element(By.CSS_SELECTOR, '.modal-mask').text
        check('需求详情含[申报周期]', '申报周期' in modal_txt)
        d.get_screenshot_as_file(os.path.join(SHOTS, 'ui_demand_cycle_detail_20261117.png'))
        close_modal(d)

        # ---- 采购询价：批量按钮栏 ----
        d.get(URL + '/#/inquiry')
        time.sleep(2.0)
        bar = d.find_element(By.CSS_SELECTOR, '.batch-bar').text.replace('\n', ' ')
        for b in ['新增询价', '更改', '删除', '提交', '导出']:
            check('询价按钮栏含[%s]' % b, b.replace(' ', '') in bar.replace(' ', ''), bar)
        d.get_screenshot_as_file(os.path.join(SHOTS, 'ui_inquiry_batch_20261117.png'))

        # ---- 新增询价：关联需求单（月度/季度分支） ----
        d.find_element(By.XPATH, "//button[contains(.,'新增询价')]").click()
        time.sleep(0.8)
        mtxt = d.find_element(By.CSS_SELECTOR, '.modal-mask').text
        check('新增询价弹窗标题(按月填报)', '按月填报' in mtxt)

        check('月度需求可选', pick_demand_option(d, '月度'))
        mtxt = d.find_element(By.CSS_SELECTOR, '.modal-mask').text
        check('月度分支显示申报周期', '申报周期' in mtxt)
        check('月度分支无本月采购计划', '本月采购计划' not in mtxt)
        d.get_screenshot_as_file(os.path.join(SHOTS, 'ui_inquiry_month_20261117.png'))

        check('季度需求可选', pick_demand_option(d, '季度'))
        mtxt = d.find_element(By.CSS_SELECTOR, '.modal-mask').text
        check('季度分支出现本月采购计划', '本月采购计划' in mtxt)
        d.get_screenshot_as_file(os.path.join(SHOTS, 'ui_inquiry_quarter_20261117.png'))
        close_modal(d)
    finally:
        d.quit()
    print('\n%d checks, %d failed' % (len(FAILS) + sum(1 for _ in []), len(FAILS)))
    if FAILS:
        print('FAILED: ' + ', '.join(FAILS))
        sys.exit(1)


if __name__ == '__main__':
    main()
