# -*- coding: utf-8 -*-
"""运营端运输调度页回归：物流调度 Tab / 订单行点击保税分析表 / 在途监控 Tab。"""
import os
import sys
import time

from selenium import webdriver
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.edge.options import Options
from selenium.webdriver.edge.service import Service

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHOTS = os.path.join(BASE, 'docs', 'shots')
FAILS = []


def check(name, cond, extra=''):
    print(('PASS ' if cond else 'FAIL ') + name + (('  ' + str(extra)) if extra else ''))
    if not cond:
        FAILS.append(name)


def main():
    o = Options()
    o.add_argument('--headless=new')
    o.add_argument('--window-size=1440,1100')
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
        d.get('http://127.0.0.1:8000/#/logistics-dispatch')
        time.sleep(2.2)
        body = d.find_element(By.CSS_SELECTOR, '.card').text
        check('物流调度 Tab 打开', '订单号' in body and '制定方案' in body or '新增分段运单' in body, body[:150])
        check('多钢厂订单需方列出全部钢厂', '多钢厂集采' not in body and '示范钢铁集团有限公司' in body, body[:300])
        d.get_screenshot_as_file(os.path.join(SHOTS, 'ui_logistics_dispatch_admin_20261118.png'))
        # 点击订单行 → 保税进出库存分析表（Excel 式：编辑 + 合并居中）
        rows = d.find_elements(By.CSS_SELECTOR, '.card table tbody tr')
        if rows:
            rows[0].click()
            time.sleep(1.0)
            body2 = d.find_element(By.CSS_SELECTOR, '.card').text
            check('保税进出库存分析表展示', '保税进出库存分析表' in body2 and '添加行' in body2)
            check('合并居中/取消合并按钮存在', '合并居中' in body2 and '取消合并' in body2)
            cells = d.find_elements(By.CSS_SELECTOR, '.analysis-grid td.cell .cell-text')
            ActionChains(d).click(cells[0]).perform()
            time.sleep(0.3)
            ActionChains(d).key_down(Keys.SHIFT).click(cells[4]).key_up(Keys.SHIFT).perform()
            time.sleep(0.3)
            check('选区高亮', len(d.find_elements(By.CSS_SELECTOR, '.cell-text.selm')) == 5)
            d.find_element(By.XPATH, "//button[contains(.,'合并居中')]").click()
            time.sleep(0.8)
            merged = d.find_elements(By.CSS_SELECTOR, '.analysis-grid td.merged')
            check('合并单元格生成( colspan )', len(merged) == 1
                  and merged[0].get_attribute('colspan') == '5', len(merged))
            d.get_screenshot_as_file(os.path.join(SHOTS, 'ui_logistics_grid_admin_20261118.png'))
            d.find_element(By.XPATH, "//button[contains(.,'取消合并')]").click()
            time.sleep(0.8)
            check('取消合并恢复', len(d.find_elements(By.CSS_SELECTOR, '.analysis-grid td.merged')) == 0)
            d.find_element(By.XPATH, "//button[contains(.,'关闭分析')]").click()
            time.sleep(0.8)
        # 在途监控 Tab
        d.find_element(By.XPATH, "//button[@data-tab='monitor']").click()
        time.sleep(1.6)
        body3 = d.find_element(By.CSS_SELECTOR, '.card').text
        check('在途监控 Tab 打开', '运单号' in body3 or 'WB-' in body3 or '暂无' in body3, body3[:150])
        d.get_screenshot_as_file(os.path.join(SHOTS, 'ui_logistics_monitor_admin_20261118.png'))
    finally:
        d.quit()
    print('\n%s' % ('ALL PASS' if not FAILS else 'FAILED: ' + ', '.join(FAILS)))
    if FAILS:
        sys.exit(1)


if __name__ == '__main__':
    main()
