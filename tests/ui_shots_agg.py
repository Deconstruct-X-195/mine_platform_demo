# -*- coding: utf-8 -*-
"""需求归集环节高清截图（供《系统使用说明》§4.6 配图）
输出 docs/shots/：
  D1-钢厂归集询价列表  D2-钢厂归集询价详情  D3-平台报价询价页  D4-发起归集询价弹窗
"""
import os
import time
from datetime import datetime, timedelta

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.edge.options import Options
from selenium.webdriver.edge.service import Service
from selenium.webdriver.support.ui import Select

BASE = r'e:\TRAE\mine_platform_demo'
SHOTS = os.path.join(BASE, 'docs', 'shots')
os.makedirs(SHOTS, exist_ok=True)

ADMIN = ('13800000000', 'admin123456')
BUYER = ('13800000001', 'demo123456')


def drv():
    o = Options()
    o.add_argument('--headless=new')
    o.add_argument('--window-size=1440,900')
    o.add_argument('--disable-gpu')
    o.add_argument('--log-level=3')
    s = Service()
    s.creation_flags = 0x08000000
    d = webdriver.Edge(options=o, service=s)
    d.set_page_load_timeout(40)
    return d


def _vis(e):
    try:
        return e.is_displayed()
    except Exception:
        return False


def shot(d, name):
    d.save_screenshot(os.path.join(SHOTS, name + '.png'))
    print('SHOT', name)


def q_text(d, txt, tag='button', timeout=8, scope=None):
    root = scope or d
    def f(dd):
        for e in root.find_elements(By.XPATH, "//%s[contains(normalize-space(),'%s')]" % (tag, txt)):
            if _vis(e):
                return e
        return None
    from selenium.webdriver.support.ui import WebDriverWait
    return WebDriverWait(d, timeout).until(lambda dd: f(dd))


def q_css(d, sel, timeout=8):
    from selenium.webdriver.support.ui import WebDriverWait
    def f(dd):
        for e in dd.find_elements(By.CSS_SELECTOR, sel):
            if _vis(e):
                return e
        return None
    return WebDriverWait(d, timeout).until(f)


def close_modals(d):
    for _ in range(5):
        ms = [m for m in d.find_elements(By.CSS_SELECTOR, '.modal-mask') if _vis(m)]
        if not ms:
            return
        try:
            btns = [b for b in ms[-1].find_elements(
                By.XPATH, ".//button[normalize-space()='关 闭' or normalize-space()='取 消' or normalize-space()='关 闭弹窗']") if _vis(b)]
            if btns:
                btns[-1].click()
            else:
                d.execute_script("arguments[0].remove();", ms[-1])
        except Exception:
            try:
                d.execute_script("arguments[0].remove();", ms[-1])
            except Exception:
                pass
        time.sleep(0.4)


def goto(d, menu):
    close_modals(d)
    q_css(d, "nav a[data-menu='%s']" % menu).click()
    time.sleep(0.9)


def login(d, user, pwd):
    d.get('http://127.0.0.1:8000/#/login')
    time.sleep(1.2)
    if d.find_elements(By.CSS_SELECTOR, '.layout'):
        try:
            q_text(d, '退 出', timeout=3).click()
            time.sleep(0.8)
            d.get('http://127.0.0.1:8000/#/login')
            time.sleep(1.0)
        except Exception:
            pass
    u = q_css(d, "input[placeholder*='手机号']"); u.clear(); u.send_keys(user)
    p = q_css(d, "input[placeholder*='密码']"); p.clear(); p.send_keys(pwd)
    q_text(d, '登 录').click()
    time.sleep(1.2)


def logout(d):
    close_modals(d)
    try:
        q_text(d, '退 出').click()
    except Exception:
        pass
    time.sleep(0.8)


def buyer_shots(d):
    """D1/D2：钢厂端归集询价列表与详情（库内已有已揭示的归集询价）。"""
    login(d, *BUYER)
    goto(d, 'inquiry')
    time.sleep(1.0)
    shot(d, 'D1-钢厂归集询价列表')
    # 点开带「归集」标记且已揭示的行详情（已截止/反馈待处理=已揭示，有按份额拆分的比价表）
    agg_rows = [r for r in d.find_elements(By.CSS_SELECTOR, 'table tbody tr')
                if _vis(r) and '归集' in r.text
                and ('已截止' in r.text or '反馈待处理' in r.text)]
    if not agg_rows:  # 兜底：取任意带归集标记的行
        agg_rows = [r for r in d.find_elements(By.CSS_SELECTOR, 'table tbody tr')
                    if _vis(r) and '归集' in r.text]
    if agg_rows:
        agg_rows[0].find_elements(By.XPATH, ".//button[contains(normalize-space(),'详情')]")[0].click()
        time.sleep(1.0)
        shot(d, 'D2-钢厂归集询价详情')
        # 已揭示单继续点「查看比价」：拍按份额拆分的比价表（含本钢厂份额）
        try:
            q_text(d, '查看比价', 'button', 5).click()
            time.sleep(1.0)
            shot(d, 'D2b-钢厂归集比价份额')
        except Exception as e:
            print('SKIP D2b', e)
    close_modals(d)
    logout(d)


def admin_shots(d):
    """D3/D4：平台报价询价页与发起归集询价弹窗（自备 OPEN 归集订单）。"""
    # 数据准备：钢厂一建两条同品种同品位需求并提交 → 管理员归集（OPEN）
    import requests
    API = 'http://127.0.0.1:8000/api/v1'
    tok = requests.post(API + '/auth/login',
                        json={'username': BUYER[0], 'password': BUYER[1]}, timeout=10).json()['data']['token']
    h = {'Authorization': 'Bearer ' + tok}
    now = datetime.now()
    made = []
    for name, qty in (('E2E归集演示A', 3200), ('E2E归集演示B', 2600)):
        dd = requests.post(API + '/demands', headers=h, json={
            'demandName': name, 'deliveryType': 'PLANT', 'deliveryPlace': '日照港',
            'expectArriveStart': (now + timedelta(days=14)).strftime('%Y-%m-%d'),
            'expectArriveEnd': (now + timedelta(days=24)).strftime('%Y-%m-%d'),
            'settleType': 'COD',
            'items': [{'varietyId': 1, 'grade': 61.8, 'quantity': qty, 'moreLessRate': 5}]},
            timeout=10).json()['data']
        requests.post(API + '/demands/%s/submit' % dd['id'], headers=h, timeout=10)
        made.append(dd['id'])
    atok = requests.post(API + '/auth/login',
                         json={'username': ADMIN[0], 'password': ADMIN[1]}, timeout=10).json()['data']['token']
    ah = {'Authorization': 'Bearer ' + atok}
    pool = requests.get(API + '/admin/demand-pool', headers=ah, params={'size': 50}, timeout=10).json()['data']
    ids = [it['id'] for it in pool['list']
           if str(it.get('demandId') or '') and int(it['demandId']) in made
           and it['status'] == 'SUBMITTED'][:2]
    agg = requests.post(API + '/admin/aggregated-orders', headers=ah,
                        json={'itemIds': ids, 'remark': '归集演示截图'}, timeout=10).json()['data']
    print('PREPARE agg', agg['aggNo'])

    login(d, *ADMIN)
    goto(d, 'quote_inquiry')
    time.sleep(1.0)
    shot(d, 'D3-平台报价询价页')
    q_text(d, '发起询价', 'button', 10).click()
    time.sleep(1.0)
    shot(d, 'D4-发起归集询价弹窗')
    close_modals(d)
    # 拍摄后关闭演示归集订单，释放数据
    requests.put(API + '/admin/aggregated-orders/%s/close' % agg['id'], headers=ah, timeout=10)
    logout(d)


if __name__ == '__main__':
    d = drv()
    try:
        buyer_shots(d)
        admin_shots(d)
    finally:
        d.quit()
    print('DONE')
