# -*- coding: utf-8 -*-
"""前端全流程可视化专项检测（Selenium Edge headless）
链路（平台归集版）：需求提交→平台需求归集→平台代发询价→供应商密封报价→
平台汇总揭示→钢厂比价认可自动成单→供方确认→钢厂提货计划→平台物流方案与分段运单→
平台发运/到达→钢厂签收→订单/履约跟踪渲染
每步截图 + toast/DOM 断言 + console 错误收集 → docs/shots/results.json
说明：结算工作台/合同面板 UI 已下线，质检→结算→归档由 API 侧
tests/e2e_full_chain.py（T17-T19）覆盖，本脚本不再重复。
"""
import json, os, re, subprocess, time, traceback
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

BUYER = ('13800000001', 'demo123456')     # 示范钢铁集团（钢厂/需方）
SUPPLIER = ('13800000002', 'demo123456')  # 示范矿产贸易（供应商/供方）
ADMIN = ('13800000000', 'admin123456')    # 平台管理员

PG = ['docker', 'exec', 'mine-platform-pg', 'psql', '-U', 'postgres', '-d', 'mine_platform', '-c']

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


def q_exact(d, txt, tag='button', timeout=8, scope=None):
    """按钮文本精确匹配（避免「认可」误命中「不认可」）"""
    root = scope or d
    def f(dd):
        for e in root.find_elements(By.XPATH, "//%s[normalize-space()='%s']" % (tag, txt)):
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

    # S02 需方登录
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

    logout(d)

    # S04 平台需求归集：清理历史残留 → 勾选目标明细 → 合并归集
    def s04():
        # 幂等清理：本企业历史 3000t 残留明细软删、仅保留最新一条（本次 S03 创建）。
        # 不论是否已归集都要清：归集单软删后行内不再显示 GJ- 号，已归集旧行会混入候选。
        subprocess.run(PG + [
            "UPDATE biz_demand_item i SET is_deleted=1 FROM biz_demand d "
            "WHERE i.demand_id=d.id AND i.is_deleted=0 AND d.is_deleted=0 AND d.status='SUBMITTED' "
            "AND i.quantity=3000 "
            "AND d.company_id=(SELECT id FROM ent_company WHERE company_name LIKE '示范钢铁集团%') "
            "AND i.id < (SELECT max(i2.id) FROM biz_demand_item i2 "
            "JOIN biz_demand d2 ON d2.id=i2.demand_id "
            "WHERE i2.is_deleted=0 AND i2.quantity=3000 AND d2.is_deleted=0 "
            "AND d2.status='SUBMITTED' "
            "AND d2.company_id=(SELECT id FROM ent_company WHERE company_name LIKE '示范钢铁集团%'));"],
            capture_output=True, timeout=60)
        login(d, *ADMIN)
        goto(d, 'demand_pool')
        # 以本次 S03 创建的最新需求单号精确定位目标行（池中旧行状态/归集显示各异，文本匹配易误命中）
        out = subprocess.run(PG + [
            "SELECT d.demand_no FROM biz_demand d WHERE d.is_deleted=0 ORDER BY d.id DESC LIMIT 1;"],
            capture_output=True, text=True, timeout=60)
        mno = re.search(r'XQ-\d{8}-\d{4}', out.stdout)
        assert mno, '未取到最新需求单号 | %s' % (out.stderr or out.stdout)
        target = [r for r in (x for x in d.find_elements(By.CSS_SELECTOR, 'table tbody tr') if _vis(x))
                  if mno.group(0) in r.text]
        assert len(target) == 1, '按单号 %s 定位目标行应唯一，实际 %d 行' % (mno.group(0), len(target))
        assert '3000' in target[0].text.replace(',', ''), '目标行吨数非3000：%s' % target[0].text
        cbs = [c for c in target[0].find_elements(By.CSS_SELECTOR, 'input[type=checkbox]') if _vis(c)]
        assert cbs, '目标行缺勾选框（勾选参与归集）'
        cbs[0].click(); time.sleep(0.3)
        q_text(d, '合并归集').click(); time.sleep(0.5)
        confirm(d)
        t, seen = poll_toast(d, '已生成')
        assert t, '归集toast未出现 | seen=%s' % seen
        assert '3000' in t.replace(',', ''), '归集数量非3000：%s' % t
    step(d, 'S04 平台需求归集', s04, '04-需求已归集')

    # S05 平台代发询价（归集订单统一询价，钢厂自发询价已下线）
    def s05():
        # 清理历史重跑残留的 3000 吨候选归集单（软删），仅保留最新一张，保证选项唯一
        subprocess.run(PG + [
            "UPDATE biz_aggregated_order SET is_deleted=1 "
            "WHERE total_qty=3000 AND status IN ('OPEN','INQUIRING') AND is_deleted=0 "
            "AND id <> (SELECT max(id) FROM biz_aggregated_order "
            "WHERE total_qty=3000 AND status IN ('OPEN','INQUIRING') AND is_deleted=0);"],
            capture_output=True, timeout=60)
        goto(d, 'quote_inquiry')
        q_text(d, '发起询价').click(); time.sleep(0.6)
        m = modal(d)
        assert '归集订单' in m.text, '发起询价弹窗未出现'
        # 明确选中本次 3000 吨归集单（库中可能有历史 INQUIRING 归集单干扰默认选中；
        # totalQty 为后端序列化字符串，形如 '3000.000'，用正则兼容小数尾零）
        ok = wait_js(d, "[...document.querySelectorAll('.modal select option')]"
                        ".some(o=>/·\\s*3000(\\.0+)?吨\\s*·/.test(o.textContent))", 10)
        assert ok, '归集订单选项未加载（未找到3000吨归集单）'
        d.execute_script("var re=/·\\s*3000(\\.0+)?吨\\s*·/;"
                         "var o=[...document.querySelectorAll('.modal select option')]"
                         ".find(x=>re.test(x.textContent));"
                         "o.selected=true;o.closest('select')"
                         ".dispatchEvent(new Event('change',{bubbles:true}));")
        # 期望到货日默认 now+18 天，早于供方报价到货日 DS(22)，须显式置后（供方到货日 ≤ 期望到货日）
        dds = [e for e in m.find_elements(By.CSS_SELECTOR, "input[type='date']") if _vis(e)]
        assert dds, '缺期望到货日输入'
        set_val(d, dds[0], DS(25))
        dtl = [e for e in m.find_elements(By.CSS_SELECTOR, "input[type='datetime-local']") if _vis(e)]
        assert dtl, '缺报价截止输入'
        set_val(d, dtl[0], DT(2, '18:00'))
        nums = [e for e in m.find_elements(By.CSS_SELECTOR, 'input[type=number]') if _vis(e)]
        assert nums, '缺最少响应家数输入'
        set_val(d, nums[0], '1')  # 单供应商场景：最少响应家数置 1，否则平台揭示被拦截
        cbs = [c for c in m.find_elements(By.CSS_SELECTOR, 'input[type=checkbox]') if _vis(c)]
        assert cbs, '缺邀请供应商勾选'
        for c in cbs:
            c.click(); time.sleep(0.1)
        q_text_in(d, m, '保存并发出').click()
        t, seen = poll_toast(d, '询价已发出')
        assert t, '发出toast未出现 | seen=%s' % seen
    step(d, 'S05 平台代发询价', s05, '05-询价已发出')

    # S06 平台询价列表渲染
    def s06():
        close_modals(d); time.sleep(0.6)
        rows = [r for r in d.find_elements(By.CSS_SELECTOR, 'table tbody tr') if _vis(r)]
        assert rows, '询价列表无行'
    step(d, 'S06 平台询价列表渲染', s06, '06-询价列表')

    logout(d)

    # S07 供方登录+收到的询价
    def s07():
        login(d, *SUPPLIER)
        goto(d, 'inquiry')
        assert q_text(d, '报价', 'button', 10), '无报价入口'
    step(d, 'S07 供方登录+询价列表', s07, '07-供方询价')

    # S08 密封报价（单价/运价/可供数量/交货时间，交货日不得晚于期望到货止日）
    def s08():
        q_text(d, '报价').click(); time.sleep(0.6)
        m = modal(d)
        q_ph_in(d, m, '单价').send_keys('820')
        q_ph_in(d, m, '运价').send_keys('30')
        qty = q_ph_in(d, m, '数量'); qty.clear(); qty.send_keys('3000')
        dates = [e for e in m.find_elements(By.CSS_SELECTOR, 'input[type=date]') if _vis(e)]
        assert dates, '缺到货日输入'
        set_val(d, dates[0], DS(22))  # 不得晚于归集需求期望到货止（DS(22)）
        sels = [s for s in m.find_elements(By.CSS_SELECTOR, 'select') if _vis(s)]
        dt = next(s for s in sels
                  if any('港口离岸' in o.text for o in s.find_elements(By.CSS_SELECTOR, 'option')))
        pick_option(d, dt, '港口离岸')
        shot('08-报价表单')
        q_text_in(d, m, '提交报价').click()
        t, seen = poll_toast(d, '报价已提交')
        assert t, 'toast未出现 | seen=%s' % seen
    step(d, 'S08 供方密封报价', s08, '08-已报价')

    logout(d)

    # S09 平台汇总揭示：模拟截止到期 → 汇总报价返回钢厂
    def s09():
        # 模拟自然到期：将未截止询价的 deadline 提前（平台揭示须在截止后）
        subprocess.run(PG + [
            "UPDATE biz_inquiry SET deadline=now()-interval '5 minutes' "
            "WHERE status IN ('SENT','QUOTING') AND deadline>now();"],
            capture_output=True, timeout=60)
        login(d, *ADMIN)
        goto(d, 'quote_inquiry')
        q_text(d, '汇总报价返回钢厂', 'button', 12).click()
        q_text(d, '确认汇总并返回钢厂', 'button', 12).click()  # 等待汇总弹窗异步打开并确认
        t, seen = poll_toast(d, '已汇总')
        assert t, '揭示toast未出现 | seen=%s' % seen
        assert '1 家' in t, '报价家数非1：%s' % t
    step(d, 'S09 平台汇总揭示', s09, '09-已揭示汇总')

    logout(d)

    # S10 钢厂查看比价并认可（全员认可 → 自动锁货锁价成单）
    def s10():
        login(d, *BUYER)
        goto(d, 'inquiry')
        q_text(d, '详情').click(); time.sleep(0.6)
        q_text(d, '查看比价', 'button', 12).click()
        q_text(d, '比价快照', 'div', 12)  # 等待快照弹窗异步打开
        m = top_modal(d)
        assert m and '比价快照' in m.text, '比价快照未渲染'
        q_exact(d, '确认报价', 'button', 10).click()  # 比价快照弹窗按钮文案为「确认报价」
        time.sleep(0.4)
        confirm(d)
        t, seen = poll_toast(d, '全员认可')
        assert t, '认可toast未出现（应自动成单）| seen=%s' % seen
    step(d, 'S10 钢厂比价认可自动成单', s10, '10-比价认可')

    logout(d)

    # S11 供方确认订单（48h 期限）
    def s11():
        login(d, *SUPPLIER)
        goto(d, 'order')
        q_text(d, '确认订单', 'button', 12).click(); time.sleep(0.4)
        confirm(d)
        t, seen = poll_toast(d, '订单已确认')
        assert t, 'toast未出现 | seen=%s' % seen
    step(d, 'S11 供方确认订单', s11, '11-订单已确认')

    logout(d)

    # S12 钢厂提交提货计划（单成员全员提交后订单转待运输方案）
    def s12():
        login(d, *BUYER)
        goto(d, 'order')
        q_exact(d, '提货计划', 'button', 12).click(); time.sleep(0.6)
        m = modal(d)
        assert '提货计划' in m.text, '提货计划弹窗未出现'
        dates = [e for e in m.find_elements(By.CSS_SELECTOR, 'input[type=date]') if _vis(e)]
        assert dates, '缺开始提货日期'
        set_val(d, dates[0], DS(0))
        q_ph_in(d, m, '吨/天').send_keys('1000')
        q_text_in(d, m, '保 存').click()
        t, seen = poll_toast(d, '提货计划已提交')
        assert t, 'toast未出现 | seen=%s' % seen
    step(d, 'S12 钢厂提交提货计划', s12, '12-提货计划已提交')

    logout(d)

    # S13 平台制定物流方案 + 新增分段运单（按 3000 吨订单行定位按钮，避免命中旧订单）
    def s13():
        login(d, *ADMIN)
        goto(d, 'logistics_dispatch')
        q_text(d, '物流调度', 'button', 10).click()

        def row_btn(txt, timeout=12):
            """在订单表中定位「3000 吨订单」所在行的按钮（列表 id 倒序，首个匹配即本次订单）"""
            end = time.time() + timeout
            while True:
                for b in d.find_elements(By.XPATH, "//button[normalize-space()='%s']" % txt):
                    if not _vis(b):
                        continue
                    try:
                        row = b.find_element(By.XPATH, 'ancestor::tr[1]')
                    except Exception:
                        continue
                    if re.search(r'(?<!\d)3000(?!\d)', row.text.replace(',', '')):
                        return b
                if time.time() >= end:
                    raise AssertionError('未找到 3000 吨订单行的「%s」按钮' % txt)
                time.sleep(0.3)

        row_btn('制定方案').click(); time.sleep(0.6)
        m = modal(d)
        assert '制定物流方案' in m.text, '方案弹窗未出现'
        q_text_in(d, m, '提 交').click()
        t, seen = poll_toast(d, '方案已制定')
        assert t, 'toast未出现 | seen=%s' % seen
        row_btn('新增分段运单').click(); time.sleep(0.6)
        m2 = modal(d)
        assert '新增分段运单' in m2.text, '分段运单弹窗未出现'
        q_ph_in(d, m2, '如：钢厂厂区').send_keys('日照港')
        eta = [e for e in m2.find_elements(By.CSS_SELECTOR, "input[type='datetime-local']") if _vis(e)]
        assert eta, '缺预计船到港时间'
        set_val(d, eta[0], DT(1, '09:00'))
        dates = [e for e in m2.find_elements(By.CSS_SELECTOR, 'input[type=date]') if _vis(e)]
        assert len(dates) >= 2, '缺计划发运/到达日'
        set_val(d, dates[0], DS(1)); set_val(d, dates[1], DS(3))
        q_ph_in(d, m2, '运费总额').send_keys('100')
        pqs = [e for e in m2.find_elements(
            By.XPATH, ".//div[contains(@class,'form-row')][label[contains(text(),'计划量')]]/input") if _vis(e)]
        if pqs and not (pqs[0].get_attribute('value') or '').strip():
            set_val(d, pqs[0], '3000')
        shot('13-分段运单表单')
        q_text_in(d, m2, '提 交').click()
        t2, seen2 = poll_toast(d, '运单已创建')
        assert t2, 'toast未出现 | seen=%s' % seen2
    step(d, 'S13 平台方案+分段运单', s13, '13-方案与运单')

    # S14 平台确认发运/到达（在途监控）
    def s14():
        close_modals(d)
        q_text(d, '在途监控', 'button', 10).click()
        q_text(d, '确认发运', 'button', 12).click(); time.sleep(0.6)
        q_text(d, '提 交').click()
        t, seen = poll_toast(d, '已发运')
        assert t, '发运toast未出现 | seen=%s' % seen
        q_text(d, '确认到达', 'button', 12).click(); time.sleep(0.6)
        q_text(d, '提 交').click()
        t2, seen2 = poll_toast(d, '已到达')
        assert t2, '到达toast未出现 | seen=%s' % seen2
    step(d, 'S14 平台确认发运/到达', s14, '14-发运到达')

    logout(d)

    # S15 钢厂签收（履约跟踪-运单）
    def s15():
        login(d, *BUYER)
        goto(d, 'track')
        q_text(d, '签收', 'button', 12).click(); time.sleep(0.4)
        confirm(d)
        t, seen = poll_toast(d, '已签收')
        assert t, 'toast未出现 | seen=%s' % seen
    step(d, 'S15 钢厂签收', s15, '15-已签收')

    # S16 钢厂订单详情渲染
    def s16():
        goto(d, 'order')
        q_text(d, '详情').click(); time.sleep(0.7)
        m = top_modal(d)
        assert m and '订单详情' in m.text, '订单详情未渲染'
        close_modals(d)
    step(d, 'S16 钢厂订单详情渲染', s16, '16-订单详情')

    # S17 履约跟踪渲染（五阶段进度 + 节点台账）
    def s17():
        goto(d, 'track')
        assert q_css(d, '.flow-steps', 8), '履约五阶段未渲染'
        assert q_css(d, '.trace-line', 8), '节点台账未渲染'
        assert q_text(d, '运单', 'button', 6), '缺运单节点筛选'
    step(d, 'S17 履约跟踪渲染', s17, '17-履约跟踪')

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
