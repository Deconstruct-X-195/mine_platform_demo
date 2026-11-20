# -*- coding: utf-8 -*-
"""钢厂端「物流服务·物流节点跟踪」显示回归（§96 口径）。

断言（对齐交付报告 §96）：
- A1 时间单行：首个 .trace-time innerText 为「YYYY-MM-DD HH:MM」单行文本、无子元素节点。
- A2 信息条间距：wb-head（组织方式/创建时间信息条）底边到首行 trace-item 顶边间距 16px。
- A3 竖线通到底：末行 trace-item 仍带 trace-seg，且 trace-line 底部与 trace-panel 底部齐平。
- A4 截图 docs/shots/ui_logistics_steel_20261117.png。

运行前置：Flask 运行于 127.0.0.1:8000。
运行：python tests/ui_logistics_steel_check.py
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import ui_e2e  # noqa: E402
from ui_e2e import BUYER, RESULTS, drv, goto, login, rec, step, _vis  # noqa: E402
from selenium.webdriver.common.by import By  # noqa: E402

# 截图统一落在当前工作区 docs/shots（ui_e2e 的 BASE 指向旧目录）
SHOTS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'docs', 'shots')
os.makedirs(SHOTS, exist_ok=True)
ui_e2e.SHOTS = SHOTS

SHOT_NAME = 'ui_logistics_steel_20261117'
TARGET_ORDER = 'DD-20261115-0007'


def _wait_items(d, timeout=12):
    import time
    end = time.time() + timeout
    while time.time() < end:
        items = [e for e in d.find_elements(By.CSS_SELECTOR, '.trace-line .trace-item') if _vis(e)]
        if items:
            return items
        time.sleep(0.3)
    return []


def run(d):
    # S1 登录钢厂端并进入物流服务页
    def s1():
        login(d, *BUYER)
        goto(d, 'logistics')
        items = _wait_items(d)
        assert items, '物流节点跟踪时间线未渲染'
    step(d, 'S1 钢厂登录并进入物流服务页', s1)

    # S2 选定目标订单 DD-20261115-0007（若默认非该单）
    def s2():
        from selenium.webdriver.support.ui import Select
        sel = [e for e in d.find_elements(By.CSS_SELECTOR, '#page select') if _vis(e)][0]
        s = Select(sel)
        if TARGET_ORDER not in s.first_selected_option.text:
            for o in s.options:
                if TARGET_ORDER in o.text:
                    s.select_by_value(o.get_attribute('value'))
                    break
        import time
        time.sleep(1.0)
        items = _wait_items(d)
        assert items, '切换订单后时间线未渲染'
    step(d, 'S2 选择订单 %s' % TARGET_ORDER, s2)

    # A1 时间单行（无子节点）
    def a1():
        t = d.find_elements(By.CSS_SELECTOR, '.trace-line .trace-item .trace-time')[0]
        txt = (t.text or '').strip()
        assert t.find_elements(By.CSS_SELECTOR, '*') == [], '时间元素仍含子节点'
        assert '\n' not in txt, '时间文本换行: %r' % txt
        assert len(txt) == 16 and txt[4] == '-' and txt[10] == ' ', '时间格式异常: %r' % txt
        return '首行时间=%s（单行,无子节点）' % txt
    step(d, 'A1 时间元素单行', a1)

    # A2 信息条到首行间距 16px
    def a2():
        head = [e for e in d.find_elements(By.CSS_SELECTOR, '#page .wb-head') if _vis(e)]
        assert head, '信息条 wb-head 未找到'
        first_item = d.find_elements(By.CSS_SELECTOR, '.trace-line .trace-item')[0]
        gap = d.execute_script(
            'const h=arguments[0].getBoundingClientRect(),'
            'i=arguments[1].getBoundingClientRect();'
            'return Math.round(i.top - h.bottom);', head[-1], first_item)
        assert gap == 16, '信息条到首行节点间距=%s（期望16）' % gap
        return '信息条→首行间距 %dpx' % gap
    step(d, 'A2 信息条到首行间距16px', a2)

    # A3 竖线通到底
    def a3():
        items = [e for e in d.find_elements(By.CSS_SELECTOR, '.trace-line .trace-item') if _vis(e)]
        assert len(items) >= 2, '时间线行数不足'
        last_seg = items[-1].find_elements(By.CSS_SELECTOR, '.trace-seg')
        assert last_seg, '末行无 trace-seg（竖线未通到底）'
        line_bottom = d.execute_script(
            'const l=arguments[0].getBoundingClientRect();return Math.round(l.bottom);',
            d.find_element(By.CSS_SELECTOR, '.trace-line'))
        item_bottom = d.execute_script(
            'const i=arguments[0].getBoundingClientRect();return Math.round(i.bottom);', items[-1])
        assert abs(line_bottom - item_bottom) <= 2, 'trace-line 底部与末行底部相差 %dpx' % abs(line_bottom - item_bottom)
        return '末行含竖线段, 时间线底部与末行齐平(%d/%d)' % (line_bottom, item_bottom)
    step(d, 'A3 时间线竖线通到底', a3)

    # A4 截图
    rec('A4 截图', True, SHOT_NAME + '.png', SHOT_NAME)


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
    print('\n===== 物流节点跟踪显示回归 %d/%d PASS =====' % (n_ok, len(RESULTS)))
    for r in RESULTS:
        print(('PASS' if r['ok'] else 'FAIL'), r['step'], '-', r['detail'][:120])
    out = os.path.join(SHOTS, 'logistics_steel_check.json')
    with open(out, 'w', encoding='utf-8') as f:
        json.dump(RESULTS, f, ensure_ascii=False, indent=2)
    return n_ok == len(RESULTS)


if __name__ == '__main__':
    ok = main()
    sys.exit(0 if ok else 1)
