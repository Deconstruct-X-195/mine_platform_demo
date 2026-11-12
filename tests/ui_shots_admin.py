# -*- coding: utf-8 -*-
"""管理端与新增功能页面高清截图（供《系统使用说明》配图）
输出 docs/shots/：
  A1-运营仪表盘  A2-合同管理核验  A3-需求归集  A4-基础数据  A5-状态字典
  A6-价格趋势详情 A7-价格行情详情
  B1-钢厂首页    B2-基准价行情    B3-新建需求表单 B4-新建询价表单
"""
import os
import time

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.edge.options import Options
from selenium.webdriver.edge.service import Service
from selenium.webdriver.support.ui import WebDriverWait

BASE = r'e:\TRAE\mine_platform_demo'
SHOTS = os.path.join(BASE, 'docs', 'shots')
os.makedirs(SHOTS, exist_ok=True)

ADMIN = ('13800000000', 'admin123456')    # 平台管理员
BUYER = ('13800000001', 'demo123456')     # 示范钢铁集团（钢厂/需方）


def drv():
    o = Options()
    o.add_argument('--headless=new')
    o.add_argument('--window-size=1440,900')
    o.add_argument('--disable-gpu')
    o.add_argument('--log-level=3')
    s = Service()
    s.creation_flags = 0x08000000  # 隐藏 msedgedriver 控制台窗
    d = webdriver.Edge(options=o, service=s)
    d.set_page_load_timeout(40)
    return d


def _vis(e):
    try:
        return e.is_displayed()
    except Exception:
        return False


def shot(d, name):
    try:
        d.save_screenshot(os.path.join(SHOTS, name + '.png'))
        print('SHOT', name)
    except Exception as e:
        print('SHOT-FAIL', name, e)


def q_text(d, txt, tag='button', timeout=8, scope=None):
    root = scope or d
    def f(dd):
        for e in root.find_elements(By.XPATH, "//%s[contains(normalize-space(),'%s')]" % (tag, txt)):
            if _vis(e):
                return e
        return None
    return WebDriverWait(d, timeout).until(lambda dd: f(dd))


def q_css(d, sel, timeout=8):
    def f(dd):
        for e in dd.find_elements(By.CSS_SELECTOR, sel):
            if _vis(e):
                return e
        return None
    return WebDriverWait(d, timeout).until(f)


def close_modals(d):
    """防御性关闭残留弹窗（点 关 闭/取 消，无按钮则移除遮罩）"""
    for _ in range(5):
        ms = [m for m in d.find_elements(By.CSS_SELECTOR, '.modal-mask') if _vis(m)]
        if not ms:
            return
        try:
            btns = [b for b in ms[-1].find_elements(
                By.XPATH, ".//button[normalize-space()='关 闭' or normalize-space()='取 消']") if _vis(b)]
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


def admin_shots(d):
    login(d, *ADMIN)
    time.sleep(1.2)
    shot(d, 'A1-运营仪表盘')
    for menu, name, extra in [
            ('contract_admin', 'A2-合同管理核验', 1.0),
            ('demand_pool', 'A3-需求归集', 0.8),
            ('base_data', 'A4-基础数据', 0.8),
            ('dict', 'A5-状态字典', 0.8)]:
        goto(d, menu)
        time.sleep(extra)
        shot(d, name)
    # 价格趋势详情 / 价格行情详情：无导航菜单项，从运营看板「详情」按钮进入
    goto(d, 'dashboard')
    time.sleep(0.8)
    q_text(d, '详情', 'button').click()
    time.sleep(1.4)
    shot(d, 'A6-价格趋势详情')
    d.execute_script("location.hash='#/dashboard'")
    time.sleep(1.0)
    btns = [b for b in d.find_elements(By.XPATH, "//button[normalize-space()='详情']") if _vis(b)]
    if btns:
        btns[-1].click()
        time.sleep(1.4)
    shot(d, 'A7-价格行情详情')
    d.execute_script("location.hash='#/dashboard'")
    time.sleep(0.8)
    # 企业准入（无导航菜单，经哈希路由进入）
    d.execute_script("location.hash='#/admin-companies'")
    time.sleep(1.2)
    shot(d, 'A8-企业准入')
    logout(d)


def buyer_shots(d):
    login(d, *BUYER)
    time.sleep(1.2)
    shot(d, 'B1-钢厂首页')
    goto(d, 'price')
    time.sleep(1.2)
    shot(d, 'B2-基准价行情')
    goto(d, 'demand')
    time.sleep(0.8)
    q_text(d, '新建需求').click()
    time.sleep(0.6)
    shot(d, 'B3-新建需求表单')
    close_modals(d)
    goto(d, 'inquiry')
    time.sleep(0.8)
    q_text(d, '引入需求管理').click()
    time.sleep(1.4)  # 等需求明细选项异步加载
    # 默认选中的需求可能在历史链路中已询尽（明细显示"该需求无剩余可询明细"），
    # 切换到最旧的一条需求（未被询价、仍有剩余可询量）以展示明细选项
    d.execute_script("""
      var ds = document.querySelector('.modal select');
      if (ds && ds.options.length > 1) {
        ds.selectedIndex = ds.options.length - 1;
        ds.dispatchEvent(new Event('change'));
      }
    """)
    time.sleep(1.4)  # 等明细异步加载
    shot(d, 'B4-新建询价表单')
    close_modals(d)
    logout(d)


def main():
    d = drv()
    try:
        admin_shots(d)
        buyer_shots(d)
    finally:
        try:
            d.quit()
        except Exception:
            pass
    print('管理端/新功能截图完成 →', SHOTS)


if __name__ == '__main__':
    main()
