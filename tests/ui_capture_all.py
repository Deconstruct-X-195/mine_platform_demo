# -*- coding: utf-8 -*-
"""UI 重构视觉巡检截图（Selenium Edge headless）
三角色（普阳/中矿/承运商）+ 平台管理员，遍历全部菜单页截图 → docs/shots/ui_*.png
并收集每页 console 错误，汇总写入 docs/shots/ui_capture.json
"""
import json, os, time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.edge.options import Options
from selenium.webdriver.edge.service import Service

BASE = r'e:\TRAE\mine_platform_demo'
SHOTS = os.path.join(BASE, 'docs', 'shots')
os.makedirs(SHOTS, exist_ok=True)

BUYER = ('13900000002', 'demo123456')
SUPPLIER = ('13900000001', 'demo123456')
CARRIER = ('13900000003', 'demo123456')
ADMIN = ('13800000000', 'admin123456')


def drv():
    o = Options()
    o.add_argument('--headless=new')
    o.add_argument('--window-size=1440,900')
    o.add_argument('--disable-gpu')
    o.add_argument('--log-level=3')
    o.set_capability('ms:loggingPrefs', {'browser': 'ALL'})
    s = Service()
    s.creation_flags = 0x08000000
    d = webdriver.Edge(options=o, service=s)
    d.set_page_load_timeout(40)
    return d


def vis(e):
    try:
        return e.is_displayed()
    except Exception:
        return False


def q_text(d, txt, tag='button', timeout=8):
    end = time.time() + timeout
    while time.time() < end:
        for e in d.find_elements(By.XPATH, "//%s[contains(normalize-space(),'%s')]" % (tag, txt)):
            if vis(e):
                return e
        time.sleep(0.2)
    return None


def q_ph(d, ph, timeout=8):
    end = time.time() + timeout
    while time.time() < end:
        for e in d.find_elements(By.XPATH, "//input[contains(@placeholder,'%s')]" % ph):
            if vis(e):
                return e
        time.sleep(0.2)
    return None


def login(d, user, pwd):
    d.get('http://127.0.0.1:8000/#/login')
    time.sleep(1.2)
    if d.find_elements(By.CSS_SELECTOR, '.layout'):
        try:
            q_text(d, '退 出').click()
            time.sleep(0.8)
            d.get('http://127.0.0.1:8000/#/login')
            time.sleep(1.0)
        except Exception:
            pass
    u = q_ph(d, '手机号'); u.clear(); u.send_keys(user)
    p = q_ph(d, '密码'); p.clear(); p.send_keys(pwd)
    q_text(d, '登 录').click()
    time.sleep(1.2)


def goto(d, menu):
    for a in d.find_elements(By.CSS_SELECTOR, "nav a[data-menu='%s']" % menu):
        if vis(a):
            a.click()
            break
    time.sleep(1.0)


def console_errs(d):
    out = []
    try:
        for e in d.get_log('browser'):
            if e.get('level') == 'SEVERE':
                out.append(e.get('message', '')[:160])
    except Exception:
        pass
    return out


RESULTS = []


def capture(d, role, menu):
    goto(d, menu)
    d.save_screenshot(os.path.join(SHOTS, 'ui_%s_%s.png' % (role, menu)))
    title = ''
    for t in d.find_elements(By.CSS_SELECTOR, '.page-title'):
        if vis(t):
            title = t.text.strip()
            break
    errs = console_errs(d)
    RESULTS.append({'role': role, 'menu': menu, 'title': title, 'console_errs': errs})
    print(('OK ' if title else 'EMPTY '), role, menu, '→', title, ('ERRS:%d' % len(errs)) if errs else '')


def capture_modal_new_demand(d):
    """普阳：打开新建需求弹窗截图（表单控件视觉）"""
    goto(d, 'demand')
    q_text(d, '新建需求').click()
    time.sleep(0.8)
    d.save_screenshot(os.path.join(SHOTS, 'ui_buyer_modal_demand.png'))
    print('OK  buyer modal_demand')
    # 防御性关闭
    for m in d.find_elements(By.CSS_SELECTOR, '.modal-mask'):
        if vis(m):
            d.execute_script("arguments[0].remove();", m)
    time.sleep(0.3)


def main():
    d = drv()
    try:
        # 登录页 / 注册页
        d.get('http://127.0.0.1:8000/#/login'); time.sleep(1.2)
        d.save_screenshot(os.path.join(SHOTS, 'ui_login.png'))
        print('OK  login')
        d.get('http://127.0.0.1:8000/#/register'); time.sleep(1.2)
        d.save_screenshot(os.path.join(SHOTS, 'ui_register.png'))
        print('OK  register')
        RESULTS.append({'role': 'guest', 'menu': 'login', 'title': '登录', 'console_errs': console_errs(d)})
        RESULTS.append({'role': 'guest', 'menu': 'register', 'title': '注册', 'console_errs': console_errs(d)})

        # 普阳（需方）
        login(d, *BUYER)
        for m in ['demand', 'price', 'inquiry', 'bargain', 'order', 'contract',
                  'logistics', 'track', 'settlement', 'profile']:
            capture(d, 'buyer', m)
        capture_modal_new_demand(d)

        # 中矿（供方）
        login(d, *SUPPLIER)
        for m in ['demand', 'inquiry', 'bargain', 'order', 'contract', 'settlement']:
            capture(d, 'supplier', m)

        # 承运商
        login(d, *CARRIER)
        for m in ['logistics', 'waybill', 'track']:
            capture(d, 'carrier', m)

        # 平台管理员
        login(d, *ADMIN)
        for m in ['dashboard', 'admin_companies', 'base_data', 'dict', 'logs', 'alerts']:
            capture(d, 'admin', m)
    finally:
        d.quit()
    with open(os.path.join(SHOTS, 'ui_capture.json'), 'w', encoding='utf-8') as f:
        json.dump(RESULTS, f, ensure_ascii=False, indent=2)
    errs = [r for r in RESULTS if r['console_errs']]
    print('===== 视觉巡检完成：%d 页，console 错误页 %d =====' % (len(RESULTS), len(errs)))


if __name__ == '__main__':
    main()
