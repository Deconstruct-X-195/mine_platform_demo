# -*- coding: utf-8 -*-
"""履约跟踪页回归测试（BUG-08 fmtDateTime 回归）。

根因回顾：ui.js 的 timeline() 内裸调用 fmtDateTime()，而该函数此前仅挂在
window.UI 上、未在 IIFE 内定义局部绑定，导致履约跟踪页渲染时间轴时抛
“fmtDateTime is not defined”，页面整体显示“页面加载失败”。

回归断言（三层）：
- T1 单元级：浏览器内直接执行 UI.timeline(...)，断言时间项 .t-time 正确格式化
  （直接回归 BUG 根因，不依赖业务数据）。
- T2 页面级：钢厂（普阳）进入履约跟踪页，断言无“页面加载失败”，
  有订单时时间轴正常渲染且节点时间已格式化。
- T3 页面级：承运商进入履约跟踪页（复现截图账号场景），同样断言。
- T4 console：无 fmtDateTime 相关 SEVERE 错误。

运行前置：Flask 运行于 127.0.0.1:8000。
运行：python tests/ui_track_regression.py
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ui_e2e import (  # noqa: E402  复用 UI 检测封装
    BUYER, RESULTS, SHOTS, drv, goto, login, logout, q_css, q_text, rec, step,
    _vis,
)
from selenium.webdriver.common.by import By  # noqa: E402

CARRIER = ('13900000003', 'demo123456')  # 承运商（截图账号场景）


def _page_broken(d):
    """页面是否处于“页面加载失败”状态。"""
    return bool([e for e in d.find_elements(By.CSS_SELECTOR, '#page .empty')
                 if '页面加载失败' in (e.text or '')])


def _wait_track_content(d, timeout=10):
    """等待履约跟踪页内容：订单选择器 或 暂无订单 空态。返回 'sel'/'empty'/None。"""
    end = time.time() + timeout
    while time.time() < end:
        sel = [e for e in d.find_elements(By.CSS_SELECTOR, '#page select') if _vis(e)]
        empty = [e for e in d.find_elements(By.XPATH, "//div[contains(@class,'empty')][contains(.,'暂无订单')]") if _vis(e)]
        if sel or empty:
            return 'sel' if sel else 'empty'
        time.sleep(0.3)
    return None


def _goto_track(d, tries=4):
    """进入履约跟踪页：直接改 hash 并等待内容渲染（规避登录后跳转竞态）。"""
    for _ in range(tries):
        d.execute_script("location.hash = '#/track';")
        time.sleep(0.8)
        if _wait_track_content(d, timeout=2):
            return True
    return False


def _assert_track_page(d):
    """履约跟踪页通用断言：无加载失败；有订单时时间轴渲染且时间已格式化。"""
    assert _goto_track(d), '未能进入履约跟踪页'
    assert not _page_broken(d), '页面加载失败仍出现'
    kind = _wait_track_content(d, timeout=10)
    assert kind, '时间轴未渲染（既无选择器也无空态）'
    if kind == 'empty':
        return '无订单（空态正常）'
    assert wait_timeline(d), '时间轴未渲染'
    times = [t.text for t in d.find_elements(By.CSS_SELECTOR, '.timeline .t-time') if _vis(t)]
    if times:
        # fmtDateTime 正常输出应为 “YYYY-MM-DD HH:MM” 或 '-'
        bad = [t for t in times if t not in ('-',) and len(t) < 10]
        assert not bad, '时间未格式化: %s' % bad[:3]
    return '时间轴节点时间 %d 项' % len(times)


def wait_timeline(d, timeout=10):
    end = time.time() + timeout
    while time.time() < end:
        if d.find_elements(By.CSS_SELECTOR, '.timeline') or \
           [e for e in d.find_elements(By.XPATH, "//div[contains(@class,'empty')][contains(.,'暂无节点记录')]") if _vis(e)]:
            return True
        time.sleep(0.3)
    return False


def run(d):
    # T0 单元级：浏览器内直接回归 UI.timeline（不依赖业务数据）
    def t0():
        login(d, *BUYER)
        js = ("const el = UI.timeline([{occurTime:'2026-11-08T10:30:00', nodeName:'装车完成'}]);"
              "const t = el.querySelector('.t-time');"
              "return t ? t.textContent : null;")
        val = d.execute_script(js)
        assert val == '2026-11-08 10:30', 'UI.timeline 时间格式化异常: %r' % val
    step(d, 'T0 UI.timeline 单元回归（fmtDateTime 格式化）', t0, 'track-01-单元回归')

    # T1 页面级：钢厂履约跟踪
    def t1():
        goto(d, 'track')
        detail = _assert_track_page(d)
        print('    钢厂视角:', detail)
    step(d, 'T1 钢厂履约跟踪页渲染', t1, 'track-02-钢厂履约跟踪')

    logout(d)

    # T2 页面级：承运商履约跟踪（截图账号场景）
    def t2():
        login(d, *CARRIER)
        detail = _assert_track_page(d)
        print('    承运商视角:', detail)
    step(d, 'T2 承运商履约跟踪页渲染', t2, 'track-03-承运商履约跟踪')

    # T3 console 无 fmtDateTime 相关 SEVERE
    def t3():
        logs = []
        try:
            logs = [e for e in d.get_log('browser') if e['level'] == 'SEVERE']
        except Exception:
            pass
        bad = [e for e in logs if 'fmtDateTime' in e.get('message', '')]
        assert not bad, 'console 仍有 fmtDateTime 错误: %s' % '; '.join(e['message'][:120] for e in bad[:3])
    step(d, 'T3 console 无 fmtDateTime 错误', t3, 'track-04-console检查')


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
    print('\n===== 履约跟踪回归 %d/%d PASS =====' % (n_ok, len(RESULTS)))
    for r in RESULTS:
        if not r['ok']:
            print('FAIL', r['step'], '-', r['detail'][:160])
    out = os.path.join(SHOTS, 'track_regression.json')
    with open(out, 'w', encoding='utf-8') as f:
        json.dump(RESULTS, f, ensure_ascii=False, indent=2)
    print('结果已写入', out)
    return n_ok == len(RESULTS)


if __name__ == '__main__':
    ok = main()
    sys.exit(0 if ok else 1)
