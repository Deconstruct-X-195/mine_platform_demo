# -*- coding: utf-8 -*-
"""前端全流程可视化专项检测（Selenium Edge headless）
链路：需求→询价→报价→揭示→议价→定标→订单→合同双签→质检→结算→付款
每步截图 + toast/DOM 断言 + console 错误收集 → docs/shots/results.json
"""
import json, os, subprocess, time, traceback
from datetime import date, timedelta
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.edge.options import Options
from selenium.webdriver.edge.service import Service
from selenium.webdriver.support.ui import WebDriverWait, Select

BASE = r'e:\TRAE\mine_platform_demo'
SHOTS = os.path.join(BASE, 'docs', 'shots')
os.makedirs(SHOTS, exist_ok=True)
RESULT = os.path.join(SHOTS, 'results.json')
SEAL = os.path.join(BASE, 'uploads', '8a2d75e891cf46d89a6624a1285ddc9b.pdf')  # 盖章件（pdf）

BUYER = ('13800000001', 'demo123456')     # 示范钢铁集团（钢厂/需方）
SUPPLIER = ('13800000002', 'demo123456')  # 示范矿产贸易（供应商/供方）
ADMIN = ('13800000000', 'admin123456')    # 平台管理员

D = date.today()
DS = lambda n: (D + timedelta(days=n)).isoformat()
DT = lambda n, hm: (D + timedelta(days=n)).isoformat() + 'T' + hm

RESULTS = []


def drv():
    o = Options()
    o.add_argument('--headless=new')
    o.add_argument('--window-size=1440,900')
    o.add_argument('--disable-gpu')
    o.add_argument('--log-level=3')
    o.set_capability('ms:loggingPrefs', {'browser': 'ALL'})
    s = Service()
    s.creation_flags = 0x08000000  # 隐藏 msedgedriver 控制台窗
    d = webdriver.Edge(options=o, service=s)
    d.set_page_load_timeout(40)
    return d


def shot(name):
    try:
        _shot(name)
    except Exception:
        pass


def _shot(name):
    _D.save_screenshot(os.path.join(SHOTS, name + '.png'))


_D = None


def rec(step, ok, detail='', shot_name=None):
    if shot_name:
        shot(shot_name)
    RESULTS.append({'step': step, 'ok': bool(ok), 'detail': str(detail)[:600]})
    print(('PASS' if ok else 'FAIL'), step, '-', str(detail)[:200])


def _vis(e):
    try:
        return e.is_displayed()
    except Exception:
        return False


def q_text(d, txt, tag='button', timeout=8, scope=None):
    root = scope or d
    def f(dd):
        for e in root.find_elements(By.XPATH, "//%s[contains(normalize-space(),'%s')]" % (tag, txt)):
            if _vis(e):
                return e
        return None
    return WebDriverWait(d, timeout).until(lambda dd: f(dd))


def q_text_in(d, scope, txt, tag='button', timeout=8):
    return q_text(d, txt, tag, timeout, scope=scope)


def q_ph(d, ph, tag='input', timeout=8, scope=None):
    root = scope or d
    def f(dd):
        for e in root.find_elements(By.XPATH, "//%s[contains(@placeholder,'%s')]" % (tag, ph)):
            if _vis(e):
                return e
        return None
    return WebDriverWait(d, timeout).until(lambda dd: f(dd))


def q_ph_in(d, scope, ph, tag='input', timeout=8):
    return q_ph(d, ph, tag, timeout, scope=scope)


def q_css(d, sel, timeout=8):
    def f(dd):
        for e in dd.find_elements(By.CSS_SELECTOR, sel):
            if _vis(e):
                return e
        return None
    return WebDriverWait(d, timeout).until(f)


def modal(d, timeout=8):
    return q_css(d, '.modal-mask', timeout)


def top_modal(d):
    ms = [m for m in d.find_elements(By.CSS_SELECTOR, '.modal-mask') if _vis(m)]
    return ms[-1] if ms else None


def set_val(d, el, val):
    """JS 赋值并派发 input/change（兼容 .value 直读与 onchange 同步模型两种写法）"""
    d.execute_script(
        "arguments[0].value=arguments[1];"
        "arguments[0].dispatchEvent(new Event('input',{bubbles:true}));"
        "arguments[0].dispatchEvent(new Event('change',{bubbles:true}));", el, val)


def pick_option(d, sel_el, txt):
    s = Select(sel_el)
    for o in s.options:
        if txt in o.text:
            s.select_by_value(o.get_attribute('value'))
            return True
    s.select_by_index(0)
    return False


def wait_js(d, js, timeout=10):
    end = time.time() + timeout
    while time.time() < end:
        try:
            if d.execute_script('return Boolean(%s);' % js):
                return True
        except Exception:
            pass
        time.sleep(0.2)
    return False


def poll_toast(d, kw, timeout=8):
    """轮询 toast：返回 (匹配文本, 期间见过的全部 toast 文本)——便于诊断关键词不匹配。
    页面刷新可能导致 toast/列表元素 stale，逐元素容错跳过。"""
    seen, end = [], time.time() + timeout
    while time.time() < end:
        for t in d.find_elements(By.CSS_SELECTOR, '.toast'):
            try:
                if not _vis(t):
                    continue
                txt = t.text
            except Exception:
                continue  # stale element，下一轮再取
            if not txt:
                continue
            if txt not in seen:
                seen.append(txt)
            if kw in txt:
                return txt, seen
        time.sleep(0.2)
    return None, seen


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


def confirm(d, timeout=8):
    q_text(d, '确 定', 'button', timeout).click()


def login(d, user, pwd):
    d.get('http://127.0.0.1:8000/#/login')
    time.sleep(1.2)
    if d.find_elements(By.CSS_SELECTOR, '.layout'):
        # 已登录态会被重定向，先退出再回登录页
        try:
            q_text(d, '退 出', timeout=3).click()
            time.sleep(0.8)
            d.get('http://127.0.0.1:8000/#/login')
            time.sleep(1.0)
        except Exception:
            pass
    u = q_ph(d, '手机号'); u.clear(); u.send_keys(user)
    p = q_ph(d, '密码'); p.clear(); p.send_keys(pwd)
    q_text(d, '登 录').click()
    time.sleep(1.2)


def logout(d):
    close_modals(d)
    # 等待列表重渲染的在途请求完成，避免登出清 token 后在途请求以 401 记入控制台（S24 误报）
    time.sleep(1.5)
    try:
        q_text(d, '退 出').click()
    except Exception:
        pass
    time.sleep(0.8)


def step(d, name, fn, shot_name=None):
    global _D
    _D = d
    try:
        fn()
        rec(name, True, 'OK', shot_name)
    except Exception as e:
        rec(name, False, traceback.format_exc(limit=2) or e, shot_name)

def run(d):
    # S01 登录页渲染
    def s01():
        d.get('http://127.0.0.1:8000/#/login'); time.sleep(1.2)
        assert q_ph(d, '手机号') and q_ph(d, '密码') and q_text(d, '登 录'), '登录表单缺失'
    step(d, 'S01 登录页渲染', s01, '01-登录页')

    # S02 普阳登录
    def s02():
        login(d, *BUYER)
        assert q_css(d, '.layout'), '未进入主布局'
        assert q_css(d, "nav a[data-menu='demand']"), '缺需求菜单'
    step(d, 'S02 需方登录+首页', s02, '02-需方首页')

    # S03 新建需求（精简表单：品种/品位/数量/交货地点/到货日期）→保存→提交
    def s03():
        goto(d, 'demand')
        q_text(d, '新建需求').click(); time.sleep(0.6)
        m = modal(d)
        sel = m.find_elements(By.CSS_SELECTOR, 'select')[0]
        pick_option(d, sel, '中华混一号')
        q_ph_in(d, m, '品位%').send_keys('62.1')
        qty = q_ph_in(d, m, '数量'); qty.clear(); qty.send_keys('3000')
        q_ph_in(d, m, '交货地点').send_keys('日照港')
        dates = [e for e in m.find_elements(By.CSS_SELECTOR, 'input[type=date]') if _vis(e)]
        assert len(dates) >= 2, '缺期望到货日期输入'
        set_val(d, dates[0], DS(12)); set_val(d, dates[1], DS(22))
        q_text_in(d, m, '保 存').click()
        t, seen = poll_toast(d, '已创建草稿')
        assert t, '保存toast未出现 | seen=%s' % seen
        time.sleep(0.6)
        q_text(d, '提交', 'button', 10).click(); time.sleep(0.4)
        confirm(d)
        t2, seen2 = poll_toast(d, '已提交')
        assert t2, '提交toast未出现 | seen=%s' % seen2
    step(d, 'S03 新建需求+提交', s03, '03-需求已提交')

    # S04 新建询价→保存草稿→详情→发出
    def s04():
        goto(d, 'inquiry')
        q_text(d, '引入需求管理').click(); time.sleep(0.6)
        m = modal(d)
        assert '新建询价' in m.text, '新建询价弹窗未出现'
        assert wait_js(d, "[...document.querySelectorAll('.modal option')]"
                           ".some(o=>o.textContent.includes('（数量'))", 10), '需求明细选项未加载'
        dtl = [e for e in m.find_elements(By.CSS_SELECTOR, "input[type='datetime-local']") if _vis(e)]
        assert dtl, '缺报价截止输入'
        set_val(d, dtl[0], DT(2, '18:00'))
        q_text_in(d, m, '保存草稿').click()
        t, seen = poll_toast(d, '询价草稿已创建')
        assert t, '保存toast未出现 | seen=%s' % seen
        time.sleep(0.6)
        q_text(d, '详情').click(); time.sleep(0.6)
        q_text(d, '发出询价', 'button', 10).click()
        t2, seen2 = poll_toast(d, '询价已发出')
        assert t2, '发出toast未出现 | seen=%s' % seen2
    step(d, 'S04 新建询价并发出', s04, '04-询价已发出')

    # S05 询价列表渲染
    def s05():
        close_modals(d); time.sleep(0.6)
        rows = [r for r in d.find_elements(By.CSS_SELECTOR, 'table tbody tr') if _vis(r)]
        assert rows, '询价列表无行'
    step(d, 'S05 询价列表渲染', s05, '05-询价列表')

    # S06 询价详情渲染
    def s06():
        q_text(d, '详情').click(); time.sleep(0.7)
        m = top_modal(d)
        assert m and '询价详情' in m.text, '询价详情未渲染'
        close_modals(d)
    step(d, 'S06 询价详情渲染', s06, '06-询价详情')

    logout(d)

    # S07 中矿登录+收到的询价
    def s07():
        login(d, *SUPPLIER)
        goto(d, 'inquiry')
        assert q_text(d, '报价', 'button', 10), '无报价入口'
    step(d, 'S07 供方登录+询价列表', s07, '07-供方询价')

    # S08 密封报价（PR #9 必填：含税口径/运价/交货方式，缺一返回 40001）
    def s08():
        q_text(d, '报价').click(); time.sleep(0.6)
        m = modal(d)
        q_ph_in(d, m, '单价').send_keys('860')
        q_ph_in(d, m, '运价').send_keys('30')
        qty = q_ph_in(d, m, '数量'); qty.clear(); qty.send_keys('3000')
        dates = [e for e in m.find_elements(By.CSS_SELECTOR, 'input[type=date]') if _vis(e)]
        assert dates, '缺到货日输入'
        set_val(d, dates[0], DS(22))  # 不得晚于询价期望到货日（S03 到货止=DS(22)，自动引入）
        sels = [s for s in m.find_elements(By.CSS_SELECTOR, 'select') if _vis(s)]
        dt = next(s for s in sels
                  if any('港口离岸' in o.text for o in s.find_elements(By.CSS_SELECTOR, 'option')))
        pick_option(d, dt, '港口离岸')
        shot('08-报价表单')
        q_text_in(d, m, '提交报价').click()
        t, seen = poll_toast(d, '报价已提交')
        assert t, 'toast未出现 | seen=%s' % seen
    step(d, 'S08 密封报价提交', s08, '08-已报价')

    logout(d)

    # S09 截止揭示+比价快照
    def s09():
        # 模拟自然到期：将未截止询价的 deadline 提前（后端规定截止后方可揭示）
        subprocess.run(['docker', 'exec', 'mine-platform-pg', 'psql', '-U', 'postgres', '-d',
                        'mine_platform', '-c',
                        "UPDATE biz_inquiry SET deadline=now()-interval '5 minutes' "
                        "WHERE status IN ('SENT','QUOTING') AND deadline>now();"],
                       capture_output=True, timeout=60)
        login(d, *BUYER); goto(d, 'inquiry')
        q_text(d, '详情').click(); time.sleep(0.6)
        q_text(d, '截止揭示', 'button', 10).click()
        q_text(d, '比价快照', 'div', 12)  # 等待揭示弹窗异步打开
        m = top_modal(d)
        assert m and '比价快照' in m.text, '比价快照未渲染'
    step(d, 'S09 截止揭示+比价快照', s09, '09-比价快照')

    # S10 发出还价
    def s10():
        q_text(d, '议价').click(); time.sleep(0.6)
        m = top_modal(d)
        q_ph_in(d, m, '还价').send_keys('850')
        q_text_in(d, m, '发出还价').click()
        t, seen = poll_toast(d, '还价已发出')
        assert t, 'toast未出现 | seen=%s' % seen
        close_modals(d); close_modals(d)
    step(d, 'S10 发出还价', s10, '10-还价已发出')

    logout(d)

    # S11 中矿接受还价
    def s11():
        login(d, *SUPPLIER); goto(d, 'bargain')
        q_text(d, '接受', 'button', 12).click(); time.sleep(0.4)
        confirm(d)
        t, seen = poll_toast(d, '已接受')
        assert t, 'toast未出现 | seen=%s' % seen
    step(d, 'S11 供方接受还价', s11, '11-还价已接受')

    logout(d)

    # S12 需方定标
    def s12():
        login(d, *BUYER); goto(d, 'bargain')
        q_text(d, '比价/议价', 'button', 12).click(); time.sleep(0.6)
        q_text(d, '定标', 'button', 10).click(); time.sleep(0.4)
        confirm(d)
        t, seen = poll_toast(d, '定标成功')
        assert t, 'toast未出现 | seen=%s' % seen
    step(d, 'S12 需方定标', s12, '12-已定标')

def _sign(d, btn_text):
    """合同签署公共流程：勾选已核对条款 + 上传盖章件 + 签 署"""
    q_text(d, btn_text, 'button', 12).click(); time.sleep(0.6)
    m = modal(d)
    cbs = [c for c in m.find_elements(By.CSS_SELECTOR, 'input[type=checkbox]') if _vis(c)]
    assert cbs, '缺"已核对条款"勾选'
    cbs[0].click()
    f = [x for x in m.find_elements(By.CSS_SELECTOR, 'input[type=file]') if _vis(x)]
    assert f, '缺盖章件上传控件'
    f[0].send_keys(SEAL)
    q_text_in(d, m, '签 署').click()
    t, seen = poll_toast(d, '签署成功')
    assert t, 'toast未出现 | seen=%s' % seen


def _part3(d):
    # S13 中矿确认订单
    def s13():
        login(d, *SUPPLIER); goto(d, 'order')
        q_text(d, '确认订单', 'button', 12).click(); time.sleep(0.4)
        confirm(d)
        t, seen = poll_toast(d, '订单已确认')
        assert t, 'toast未出现 | seen=%s' % seen
    step(d, 'S13 供方确认订单', s13, '13-订单已确认')

    # S14 需方生成合同
    def s14():
        login(d, *BUYER); goto(d, 'order')
        q_text(d, '生成合同', 'button', 12).click()
        t, seen = poll_toast(d, '合同已生成')
        assert t, 'toast未出现 | seen=%s' % seen
    step(d, 'S14 需方生成合同', s14, '14-合同已生成')

    # S15 订单详情渲染
    def s15():
        q_text(d, '详情').click(); time.sleep(0.7)
        m = top_modal(d)
        assert m and '订单详情' in m.text, '订单详情未渲染'
        close_modals(d)
    step(d, 'S15 订单详情渲染', s15, '15-订单详情')

    # S16 需方签署
    def s16():
        goto(d, 'contract')
        # 等待列表异步加载完成（有行或出现"暂无合同"空态）
        WebDriverWait(d, 12).until(lambda dd: [
            r for r in dd.find_elements(By.CSS_SELECTOR, 'table tbody tr') if _vis(r)]
            or [e for e in dd.find_elements(By.XPATH, "//div[contains(@class,'empty')][contains(.,'暂无合同')]") if _vis(e)])
        rows = [r for r in d.find_elements(By.CSS_SELECTOR, 'table tbody tr') if _vis(r)]
        assert rows, '合同列表无行'
        _sign(d, '需方签署')
    step(d, 'S16 需方签署合同', s16, '16-需方已签')

    logout(d)

    # S17 供方签署
    def s17():
        login(d, *SUPPLIER); goto(d, 'contract')
        _sign(d, '供方签署')
    step(d, 'S17 供方签署合同', s17, '17-供方已签')

    logout(d)

    # S18 平台核验合同（PR #9：双签后合同待平台核验，核验通过方生效并转履约）
    def s18():
        login(d, *ADMIN)
        goto(d, 'contract_admin')
        WebDriverWait(d, 12).until(lambda dd: [
            r for r in dd.find_elements(By.CSS_SELECTOR, 'table tbody tr') if _vis(r)])
        rows = [r for r in d.find_elements(By.CSS_SELECTOR, 'table tbody tr') if _vis(r)]
        btns = [b for r in rows for b in r.find_elements(
            By.XPATH, ".//button[contains(normalize-space(),'核验')]") if _vis(b)]
        assert btns, '无待核验合同（列表无核验按钮）'
        btns[0].click(); time.sleep(0.6)
        m = top_modal(d)
        assert m and '合同核验' in m.text, '核验弹窗未渲染'
        shot('18-合同核验弹窗')
        q_text_in(d, m, '提 交').click()
        t, seen = poll_toast(d, '合同已生效并纳入台账')
        assert t, 'toast未出现 | seen=%s' % seen
        close_modals(d)
        shot('18-合同已生效')
    step(d, 'S18 平台核验合同', s18, None)

    # S19 结算工作台渲染（合同生效后订单转履约，方可进入结算）
    def s19():
        login(d, *BUYER); goto(d, 'settlement')
        assert q_text(d, '结算工作台', 'h3', 10), '结算工作台未渲染'
        assert q_css(d, 'select', 8), '缺订单选择器'
    step(d, 'S19 结算工作台渲染', s19, '19-结算工作台')

    # S20 质检录入
    def s20():
        q_text(d, '质检录入').click(); time.sleep(0.6)
        m = modal(d)
        q_ph_in(d, m, '实收数量').send_keys('2980')
        ta = q_ph_in(d, m, '检验指标', tag='textarea')
        ta.send_keys('Fe 62.1%，水分 7.8%')
        q_text_in(d, m, '保 存').click()
        t, seen = poll_toast(d, '质检记录已保存')
        assert t, 'toast未出现 | seen=%s' % seen
    step(d, 'S20 质检录入', s20, '20-质检已录')

    # S21 生成结算
    def s21():
        q_text(d, '生成结算').click(); time.sleep(0.6)
        m = modal(d)
        qty = q_ph_in(d, m, '结算数量'); qty.clear(); qty.send_keys('2980')
        q_text_in(d, m, '生 成').click()
        t, seen = poll_toast(d, '结算单已生成')
        assert t, 'toast未出现 | seen=%s' % seen
    step(d, 'S21 生成结算', s21, '21-结算已生成')

    logout(d)

    # S22 供应商确认结算
    def s22():
        login(d, *SUPPLIER); goto(d, 'settlement')
        q_text(d, '供应商确认', 'button', 12).click(); time.sleep(0.4)
        confirm(d)
        t, seen = poll_toast(d, '已确认')
        assert t, 'toast未出现 | seen=%s' % seen
    step(d, 'S22 供应商确认结算', s22, '22-结算已确认')

    logout(d)

    # S23 需方确认+付款登记（供应商确认后状态为待需方确认，需方确认后方可付款登记）
    def s23():
        login(d, *BUYER); goto(d, 'settlement')
        q_text(d, '需方确认', 'button', 12).click(); time.sleep(0.4)
        confirm(d)
        t, seen = poll_toast(d, '需方已确认')
        assert t, '需方确认toast未出现 | seen=%s' % seen
        time.sleep(0.6)
        q_text(d, '付款登记', 'button', 12).click(); time.sleep(0.6)
        m = modal(d)
        q_text_in(d, m, '登 记').click()
        t2, seen2 = poll_toast(d, '付款已登记')
        assert t2, 'toast未出现 | seen=%s' % seen2
    step(d, 'S23 需方确认+付款登记', s23, '23-付款已登记')

    # S24 console 错误收集
    def s24():
        logs = []
        try:
            logs = [e for e in d.get_log('browser') if e['level'] == 'SEVERE']
        except Exception:
            pass
        assert not logs, 'console SEVERE: %s' % '; '.join(e['message'][:120] for e in logs[:3])
    step(d, 'S24 console错误收集', s24, '24-console检查')


def main():
    d = drv()
    try:
        run(d)
        _part3(d)
    finally:
        try:
            d.quit()
        except Exception:
            pass
    n_ok = sum(1 for r in RESULTS if r['ok'])
    print('\n===== 汇总 %d/%d PASS =====' % (n_ok, len(RESULTS)))
    for r in RESULTS:
        if not r['ok']:
            print('FAIL', r['step'], '-', r['detail'][:160])
    with open(RESULT, 'w', encoding='utf-8') as f:
        json.dump(RESULTS, f, ensure_ascii=False, indent=2)
    print('结果已写入', RESULT)


if __name__ == '__main__':
    main()
