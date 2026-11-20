# -*- coding: utf-8 -*-
"""钢厂端「履约跟踪」页显示回归（§97 全链信息表口径）。

三单验证（对齐交付报告 §97 验证口径）：
- DD-20261115-0009（PENDING_CONFIRM）→ 五阶段「双方确认进行中 / 提货计划待进行」，
  全链表提货计划行「待提交」（修复前误显示已完成）。
- DD-20261115-0007（PERFORMING）→ 运输交付进行中，全链 8 行
  （询价/议价反馈/订单/提货计划已提交/物流方案/运单聚合 1 行（多段并单）/交付验收 1/4/结算待生成），
  运单行整体轨迹显示，已到达运单聚合行内含「签收」按钮。
- DD-20261108-9001（普通订单）→ 提货计划行「不适用」。
截图：docs/shots/ui_track_steel_dd0009_20261117.png / ui_track_steel_dd0007_20261117.png /
     ui_track_steel_regular_20261117.png

运行前置：Flask 运行于 127.0.0.1:8000。
运行：python tests/ui_track_steel_check.py
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import ui_e2e  # noqa: E402
from ui_e2e import BUYER, RESULTS, drv, goto, login, rec, step, _vis  # noqa: E402
from selenium.webdriver.common.by import By  # noqa: E402
from selenium.webdriver.support.ui import Select  # noqa: E402

# 截图统一落在当前工作区 docs/shots（ui_e2e 的 BASE 指向旧目录）
SHOTS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'docs', 'shots')
os.makedirs(SHOTS, exist_ok=True)
ui_e2e.SHOTS = SHOTS


def _page_broken(d):
    return bool([e for e in d.find_elements(By.CSS_SELECTOR, '#page .empty')
                 if '页面加载失败' in (e.text or '')])


def _pick(d, order_no):
    sel_el = [e for e in d.find_elements(By.CSS_SELECTOR, '#page select') if _vis(e)][0]
    s = Select(sel_el)
    for o in s.options:
        if order_no in o.text:
            s.select_by_value(o.get_attribute('value'))
            break
    time.sleep(1.2)


def _stages(d):
    return [e.text.replace('\n', ' ') for e in d.find_elements(By.CSS_SELECTOR, '.flow-step') if _vis(e)]


def _rows(d):
    return [(e.text.replace('\n', ' | ')) for e in d.find_elements(By.CSS_SELECTOR, '.card table tbody tr') if _vis(e)]


def _wait_page(d, timeout=12):
    end = time.time() + timeout
    while time.time() < end:
        if _stages(d):
            return True
        time.sleep(0.3)
    return False


def run(d):
    # S1 登录钢厂端进入履约跟踪页
    def s1():
        login(d, *BUYER)
        goto(d, 'track')
        assert _wait_page(d), '履约跟踪页五阶段未渲染'
        assert not _page_broken(d), '页面加载失败'
    step(d, 'S1 钢厂登录并进入履约跟踪页', s1)

    # T1 DD-20261115-0009：双方确认进行中 / 提货计划待提交
    def t1():
        _pick(d, 'DD-20261115-0009')
        st = _stages(d)
        assert len(st) == 5, '五阶段不足: %s' % st
        assert '进行中' in st[1] and '双方确认' in st[1], '阶段2异常: %s' % st[1]
        assert '待进行' in st[2] and '提货计划' in st[2], '阶段3应待进行: %s' % st[2]
        rows = _rows(d)
        pk = [r for r in rows if r.startswith('提货计划')]
        assert pk and '待提交' in pk[0], '提货计划行应待提交: %s' % pk
        rec('T1 概要', True, ' | '.join(rows[:2]))
    step(d, 'T1 DD-20261115-0009 双方确认进行中', t1, 'ui_track_steel_dd0009_20261117')

    # T2 DD-20261115-0007：运输交付进行中 + 全链 8 行（运单聚合单行）+ 签收按钮
    def t2():
        _pick(d, 'DD-20261115-0007')
        st = _stages(d)
        assert '进行中' in st[3] and '运输交付' in st[3], '阶段4应运输交付进行中: %s' % st[3]
        rows = _rows(d)
        heads = [r.split(' ')[0] for r in rows]  # 环节列 = 行首词（环节名无空格）
        assert heads == ['询价', '议价反馈', '订单', '提货计划', '物流方案',
                         '运单', '交付验收', '结算'], '全链行异常: %s' % heads
        assert any('已提交' in r for r in rows if r.startswith('提货计划')), '提货计划应已提交'
        assert any('1/4' in r for r in rows if r.startswith('交付验收')), '交付验收应 1/4'
        wb_rows = [r for r in rows if r.startswith('运单')]
        assert len(wb_rows) == 1 and '等 4 单' in wb_rows[0], '运单应聚合单行(等 4 单): %s' % wb_rows
        assert ' → ' in wb_rows[0], '运单行应显示整体轨迹'
        sign_btns = [b for b in d.find_elements(By.XPATH, "//button[normalize-space()='签收']") if _vis(b)]
        assert len(sign_btns) == 1, '已到达运单应有且仅有 1 个签收按钮: %d' % len(sign_btns)
        rec('T2 概要', True, '全链 %d 行' % len(rows))
    step(d, 'T2 DD-20261115-0007 全链信息表', t2, 'ui_track_steel_dd0007_20261117')

    # T3 DD-20261108-9001：普通订单提货计划「不适用」
    def t3():
        _pick(d, 'DD-20261108-9001')
        rows = _rows(d)
        pk = [r for r in rows if r.startswith('提货计划')]
        assert pk and '不适用' in pk[0], '普通订单提货计划行应不适用: %s' % pk
        rec('T3 概要', True, ' | '.join(rows[:2]))
    step(d, 'T3 DD-20261108-9001 普通订单', t3, 'ui_track_steel_regular_20261117')


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
    print('\n===== 履约跟踪显示回归 %d/%d PASS =====' % (n_ok, len(RESULTS)))
    for r in RESULTS:
        print(('PASS' if r['ok'] else 'FAIL'), r['step'], '-', r['detail'][:160])
    return n_ok == len(RESULTS)


if __name__ == '__main__':
    ok = main()
    sys.exit(0 if ok else 1)
