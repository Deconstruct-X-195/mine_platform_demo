# -*- coding: utf-8 -*-
"""钢厂端履约跟踪页改版回归（§97）：
全链信息表 + 五阶段进度（提货计划状态修复）三单验证，输出 docs/shots/ui_track_*.png
  1) DD-20261115-0009（id=18，PENDING_CONFIRM）→ 双方确认进行中、提货计划待进行/待提交
  2) DD-20261115-0007（id=16，PERFORMING）→ 运输交付进行中、提货计划已提交
  3) DD-20261108-9001（id=5，普通订单 PERFORMING）→ 提货计划行「不适用」
"""
import os
import time

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.edge.options import Options
from selenium.webdriver.edge.service import Service
from selenium.webdriver.support.ui import Select, WebDriverWait

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHOTS = os.path.join(BASE, 'docs', 'shots')
os.makedirs(SHOTS, exist_ok=True)
URL = 'http://127.0.0.1:8000'


def drv():
    o = Options()
    o.add_argument('--headless=new')
    o.add_argument('--window-size=1440,1000')
    o.add_argument('--disable-gpu')
    o.add_argument('--log-level=3')
    s = Service()
    s.creation_flags = 0x08000000
    d = webdriver.Edge(options=o, service=s)
    d.set_page_load_timeout(40)
    return d


def main():
    d = drv()
    try:
        d.get(URL + '/#/login')
        d.find_element(By.CSS_SELECTOR, 'input[placeholder*="手机号"],input[type="text"]').send_keys('13800000001')
        d.find_element(By.CSS_SELECTOR, 'input[type="password"]').send_keys('demo123456')
        d.find_element(By.XPATH, "//button[contains(.,'登')]").click()
        import time
        time.sleep(1.5)
        d.get(URL + '/#/track')
        time.sleep(2.0)

        def pick(order_no):
            sel_el = WebDriverWait(d, 15).until(
                lambda dd: next((e for e in dd.find_elements(By.CSS_SELECTOR, '.toolbar select, .card select')
                                 if e.is_displayed()), None))
            sel = Select(sel_el)
            for opt in sel.options:
                if order_no in opt.text:
                    sel.select_by_visible_text(opt.text)
                    break
            time.sleep(1.5)

        def dump():
            stages = [e.text.replace('\n', ' ') for e in d.find_elements(By.CSS_SELECTOR, '.flow-step')]
            rows = [e.text.replace('\n', ' | ') for e in d.find_elements(By.CSS_SELECTOR, '.card table tbody tr')]
            return stages, rows

        for no, name in [('DD-20261115-0009', 'ui_track_steel_dd0009_fix'),
                         ('DD-20261115-0007', 'ui_track_steel_dd0007_fix'),
                         ('DD-20261108-9001', 'ui_track_steel_regular_fix')]:
            pick(no)
            d.save_screenshot(os.path.join(SHOTS, name + '.png'))
            stages, rows = dump()
            print('=====', no, '=====')
            print('STAGES:', ' || '.join(stages))
            for r in rows:
                print('ROW:', r)

        # 签收按钮全流程：DD-20261109-9002 的已到达运单 YD-20261109-9001 → 签收 → SIGNED
        pick('DD-20261109-9002')
        btns = [e for e in d.find_elements(By.XPATH, "//button[normalize-space()='签收']") if e.is_displayed()]
        print('===== DD-20261109-9002 签收按钮:', len(btns))
        if btns:
            btns[0].click()
            time.sleep(0.6)
            d.find_element(By.XPATH, "//button[contains(.,'确')]").click()
            time.sleep(1.5)
            d.save_screenshot(os.path.join(SHOTS, 'ui_track_steel_sign_done.png'))
            _, rows = dump()
            for r in rows:
                print('ROW:', r)
    finally:
        d.quit()


if __name__ == '__main__':
    main()
