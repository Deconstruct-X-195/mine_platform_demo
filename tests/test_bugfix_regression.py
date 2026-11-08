# -*- coding: utf-8 -*-
"""BUG-01~07 修复回归测试（API 级）。

覆盖范围与根因对照：
- BUG-01 状态字典页"无流转"：/admin/dicts 返回嵌套 dict {from: [to...]}，
  前端需按该结构展开渲染（回归断言接口形状与关键流转存在）。
- BUG-02 新建需求品种下拉误报：明细行默认选中项须回写数据模型
  （回归断言 varietyId 合同字段可创建、可回读、可原样回存）。
- BUG-03 编辑需求明细不回显：GET /demands/<id> 明细字段须齐全
  （回归断言 varietyId/grade/quantity/moreLessRate 回读）。
- BUG-04 撤回后无重提入口：后端状态机 WITHDRAWN→SUBMITTED（version+1）
  （回归断言完整 提交→撤回→重提 链路，以及撤回态不可编辑）。
- BUG-05 企业信息页误显"平台管理员无企业档案"：/companies/me 平铺返回
  企业字段（回归断言企业用户平铺+qualifications、管理员 company=null）。
- BUG-06 业务时区 UTC/本地 8 小时偏差：DB now() 生成时间戳须等于本地时间
  （回归断言 created_at 与本机时钟差 < 10 分钟）。
- BUG-07 询价保存"静默失败"：校验拒绝须返回明确 message
  （回归断言 +2h / 前 7 天规则的 40001 message，供弹窗内持久展示）。

运行前置：Flask 运行于 127.0.0.1:8000（POSTGRES 可达，已应用
docs/migrations/20261108_bug06_timezone_fix.sql 并重启服务）。
运行：python tests/test_bugfix_regression.py
"""
import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from e2e_helpers import ADMIN, PG_DSN, Client, check, discover_accounts, pg_one, summary

PASS = 'demo123456'


def login_user(username):
    """自适应登录：基线/seed 账号用 demo123456，E2E 历史注册账号用 new123456。"""
    last = None
    for pw in (PASS, 'new123456'):
        try:
            return Client.login(username, pw)
        except Exception as e:  # noqa: BLE001 - 记录最后一次失败
            last = e
    raise last


def run():
    plat = Client.login(*ADMIN)
    now = datetime.now()
    tag = 'RG' + now.strftime('%m%d%H%M%S')

    acc = discover_accounts()
    assert acc['steel'] and acc['suppliers'], '基线账号缺失：钢厂 %s / 供应商 %s' % acc
    steel = login_user(acc['steel'][0])
    sup = login_user(acc['suppliers'][0])
    print('[基线] 钢厂 %s | 供应商 %s' % (acc['steel'][0], acc['suppliers'][0]))

    # ---- BUG-01 状态字典形状 ----
    print('\n[BUG-01] 状态字典')
    dd = plat.get('/admin/dicts')
    trs = dd.get('transitions') or {}
    check('BUG-01 transitions 为非空嵌套dict', isinstance(trs, dict) and len(trs) > 0, dd)
    dm = trs.get('biz_demand') or {}
    check('BUG-01 biz_demand.DRAFT 可展开为行', bool(dm.get('DRAFT')), dm)
    check('BUG-01 biz_demand.WITHDRAWN→SUBMITTED 存在', 'SUBMITTED' in (dm.get('WITHDRAWN') or []),
          dm.get('WITHDRAWN'))

    # ---- BUG-02/03 需求明细字段契约 ----
    print('\n[BUG-02/03] 需求明细契约')
    varieties = steel.get('/base/varieties')['list']
    pb = next((v for v in varieties if 'PB' in (v.get('varietyName') or '').upper()
               or v.get('varietyCode') == 'IRON_ORE_POWDER'), varieties[0])
    body = {'demandName': '回归-BUG0203-' + tag, 'deliveryType': 'PORT_TRUCK',
            'deliveryPlace': '青岛港', 'expectArriveStart': (now + timedelta(days=5)).strftime('%Y-%m-%d'),
            'expectArriveEnd': (now + timedelta(days=20)).strftime('%Y-%m-%d'),
            'settleType': 'COD', 'priceIntent': '随行就市',
            'items': [{'varietyId': pb['id'], 'grade': 62.0, 'quantity': 30000, 'moreLessRate': 5}]}
    d = steel.post('/demands', body)
    dv = steel.get('/demands/%d' % d['id'])
    it0 = (dv.get('items') or [{}])[0]
    check('BUG-03 明细回读 varietyId', it0.get('varietyId') == pb['id'], it0)
    check('BUG-03 明细回读 moreLessRate/grade/quantity',
          it0.get('moreLessRate') is not None and it0.get('grade') is not None
          and it0.get('quantity') is not None, it0)
    # 模拟修复后的编辑表单：回显字段原样回存（此前前端不回显明细，保存即清空）
    steel.put('/demands/%d' % d['id'], body)
    dv2 = steel.get('/demands/%d' % d['id'])
    check('BUG-02/03 回显后原样保存成功且数量一致',
          len(dv2.get('items') or []) == 1 and float(dv2['items'][0]['quantity']) == 30000,
          dv2.get('items'))

    # ---- BUG-04 撤回→重新提交 ----
    print('\n[BUG-04] 撤回后重提')
    r = steel.post('/demands/%d/submit' % d['id'])
    check('BUG-04 提交 SUBMITTED', r.get('status') == 'SUBMITTED', r)
    w = steel.post('/demands/%d/withdraw' % d['id'])
    check('BUG-04 撤回 WITHDRAWN', w.get('status') == 'WITHDRAWN', w)
    s, c, m = steel.try_code('PUT', '/demands/%d' % d['id'], body)
    check('BUG-04 撤回态不可编辑(40901)', c == 40901, m)
    r2 = steel.post('/demands/%d/submit' % d['id'])
    check('BUG-04 重新提交生成新版本', r2.get('status') == 'SUBMITTED' and r2.get('version') == 2, r2)

    # ---- BUG-05 企业档案接口形状 ----
    print('\n[BUG-05] 企业档案接口形状')
    me = steel.get('/companies/me')
    check('BUG-05 企业用户平铺返回企业字段', bool(me.get('companyName') or me.get('company_name')), me)
    check('BUG-05 返回资质列表 qualifications', isinstance(me.get('qualifications'), list),
          me.get('qualifications'))
    pa = plat.get('/companies/me')
    check('BUG-05 平台管理员 company=null',
          pa.get('company') is None and not (pa.get('companyName') or pa.get('company_name')), pa)

    # ---- BUG-06 业务时区一致性 ----
    print('\n[BUG-06] 业务时区一致性')
    row = pg_one("SELECT created_at FROM biz_demand WHERE id=%s", (d['id'],))
    diff = abs((row[0] - now).total_seconds())
    check('BUG-06 DB生成时间戳=本地时间(±10分钟)', diff < 600,
          'created_at=%s 本地=%s diff=%.1fs' % (row[0], now, diff))

    # ---- BUG-06/07 询价时间校验 ----
    print('\n[BUG-06/07] 询价时间校验')
    item_id = dv2['items'][0]['id']
    inq = {'demandId': d['id'], 'demandItemId': item_id, 'quantity': 5000,
           'arriveDate': (now + timedelta(days=10)).strftime('%Y-%m-%d'),
           'deadline': (now + timedelta(hours=2, minutes=10)).strftime('%Y-%m-%d %H:%M:%S'),
           'inviteSupplierIds': [sup.user['company']['id']], 'minResponse': 1}
    q = steel.post('/inquiries', inq)
    check('BUG-06 本地时间语义下 +2h10min 询价可创建', q.get('status') == 'DRAFT', q)
    s, c, m = steel.try_code('POST', '/inquiries', dict(inq, deadline=(now + timedelta(hours=1)).strftime('%Y-%m-%d %H:%M:%S')))
    check('BUG-07 截止+1h被拦且message明确(40001)', c == 40001 and '2 小时' in (m or ''), m)
    s, c, m = steel.try_code('POST', '/inquiries',
                             dict(inq, arriveDate=(now + timedelta(days=1)).strftime('%Y-%m-%d')))
    check('BUG-07 截止晚于到货前7天被拦且message明确(40001)', c == 40001 and '7 天' in (m or ''), m)

    return summary()


if __name__ == '__main__':
    ok = run()
    sys.exit(0 if ok else 1)
