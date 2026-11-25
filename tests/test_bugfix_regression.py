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
  （回归断言完整 提交→撤回→重提 链路，以及撤回态可编辑、重提生成新版本）。
- BUG-05 企业信息页误显"平台管理员无企业档案"：/companies/me 平铺返回
  企业字段（回归断言企业用户平铺+qualifications、管理员 company=null）。
- BUG-06 业务时区 UTC/本地 8 小时偏差：DB now() 生成时间戳须等于本地时间
  （回归断言 created_at 与本机时钟差 < 10 分钟）。
- BUG-07 询价保存"静默失败"：校验拒绝须返回明确 message
  （回归断言邀请供应商为空 / 最少响应家数越界的 40001 message，供弹窗内持久展示）。

部署前安全回归（部署前全面评估报告-20261121 P1/P1-1/P2-1）：
- P1-1 登录限流真实 IP：限流键取 X-Real-IP（反代注入），不同来源互不影响锁定；
  锁定窗口内正确密码亦被拒；无反代头直连回退 remote_addr。
- P2-1 附件下载归属校验：非归属企业/无业务关联者下载被拒（40401 不泄露存在性）；
  归属企业本人与平台管理员可下载；注册执照（无归属）仅平台管理员可下载；
  合同扫描件经单据引用对订单参与方开放（seed 环境存在演示合同件时断言）。

运行前置：Flask 运行于 127.0.0.1:8000（POSTGRES 可达，已应用
docs/migrations/20261108_bug06_timezone_fix.sql 并重启服务）。
运行：python tests/test_bugfix_regression.py
"""
import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import requests

from e2e_helpers import ADMIN, BASE, PG_DSN, Client, check, discover_accounts, pg_one, summary

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
    check('BUG-04 撤回态可编辑(无需更改理由)', c == 0, m)
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

    # ---- BUG-06/07 询价校验（平台归集代发询价；截止由平台自动设定，另验自发询价必填拦截） ----
    print('\n[BUG-06/07] 询价校验')
    pool = plat.get('/admin/demand-pool', size=50)
    pool_item = next((it for it in pool.get('list') or []
                      if str(it.get('demandId') or '') == str(d['id'])
                      and it.get('status') == 'SUBMITTED'
                      and float(it['quantity']) - float(it.get('inquiredQty') or 0) > 0), None)
    assert pool_item, '需求池未找到 BUG-02/03 创建的已提交明细'
    item_id = pool_item['itemId'] if 'itemId' in pool_item else pool_item['id']
    agg = plat.post('/admin/aggregated-orders', {'itemIds': [item_id]})
    agg_id = agg['id']
    base = {'aggOrderId': agg_id, 'arriveDate': (now + timedelta(days=10)).strftime('%Y-%m-%d'),
            'minResponse': 1, 'inviteSupplierIds': [sup.user['company']['id']]}
    q = plat.post('/admin/quote-inquiries', base)
    check('BUG-06 本地时间语义下归集询价可创建', bool(q.get('inquiryId')), q)
    dl = str(pg_one("SELECT deadline FROM biz_inquiry WHERE id=%s", (q['inquiryId'],))[0])
    check('BUG-07 截止由平台自动设定(到货前7天18:00)',
          dl.startswith((now + timedelta(days=3)).strftime('%Y-%m-%d')) and dl.endswith('18:00:00'), dl)
    s, c, m = plat.try_code('POST', '/admin/quote-inquiries',
                            dict(base, inviteSupplierIds=[]))
    check('BUG-07 邀请供应商为空被拦且message明确(40001)', c == 40001 and '供应商' in (m or ''), m)
    s, c, m = plat.try_code('POST', '/admin/quote-inquiries',
                            dict(base, minResponse=11))
    check('BUG-07 最少响应家数越界被拦且message明确(40001)', c == 40001 and '1~10' in (m or ''), m)
    s, c, m = steel.try_code('POST', '/inquiries', {'demandId': d['id'], 'demandItemId': item_id,
                                                    'arriveDate': (now + timedelta(days=10)).strftime('%Y-%m-%d')})
    check('BUG-07 自发询价缺quantity被拦且message明确(40001)', c == 40001, m)

    # ---- P1-1 登录限流真实 IP（反代部署语义） ----
    # 反代场景：全体客户端 remote_addr 均为 127.0.0.1，限流键必须取反代注入的 X-Real-IP。
    # 使用不存在的账号名，避免影响真实账号的锁定状态。
    print('\n[P1-1] 登录限流真实 IP 隔离')
    ghost = 'locktest-nouser-' + tag

    def _login_probe(ip, username, password):
        headers = {'X-Real-IP': ip} if ip else {}
        r = requests.post(BASE + '/auth/login', json={'username': username, 'password': password},
                          headers=headers, timeout=10)
        b = r.json() if 'json' in r.headers.get('Content-Type', '') else {}
        return r.status_code, b.get('code'), b.get('message')

    for i in range(5):
        s, c, m = _login_probe('10.99.0.1', ghost, 'wrong-%d' % i)
        check('P1-1 第%d次错误密码正常拒绝' % (i + 1),
              s == 200 and c == 40001 and '密码' in (m or ''), 'http=%s code=%s msg=%s' % (s, c, m))
    s, c, m = _login_probe('10.99.0.1', ghost, PASS)
    check('P1-1 同IP第6次(含正确密码)被锁定', s == 200 and c == 40001 and '频繁' in (m or ''),
          'http=%s code=%s msg=%s' % (s, c, m))
    s, c, m = _login_probe('10.99.0.2', ghost, 'wrong-x')
    check('P1-1 不同X-Real-IP不受影响', s == 200 and c == 40001 and '密码' in (m or ''),
          'http=%s code=%s msg=%s' % (s, c, m))
    s, c, m = _login_probe(None, ghost, 'wrong-x')
    check('P1-1 无反代头直连回退remote_addr不受影响', s == 200 and c == 40001 and '密码' in (m or ''),
          'http=%s code=%s msg=%s' % (s, c, m))

    # ---- P2-1 附件下载归属校验 ----
    print('\n[P2-1] 附件下载归属校验')

    def _dl(client_or_token_session, fid):
        r = client_or_token_session.get(BASE + '/files/%s' % fid, timeout=15)
        return r

    # 供应商上传私有附件 → 归属企业本人可下载
    r = sup.s.post(BASE + '/files',
                   files={'file': ('acl-test-%s.pdf' % tag, b'%PDF-1.4 acl-test', 'application/pdf')},
                   timeout=15)
    up = (r.json() or {}).get('data') or {}
    fid = up.get('fileId')
    check('P2-1 供应商上传文件成功', bool(fid), r.text[:200])
    rd = _dl(sup.s, fid)
    check('P2-1 归属企业本人可下载', rd.status_code == 200 and rd.content.startswith(b'%PDF'),
          'http=%s ct=%s' % (rd.status_code, rd.headers.get('Content-Type')))
    # 钢厂（无业务关联）直接下载他人附件 → 40401 不泄露存在性
    rd2 = _dl(steel.s, fid)
    try:
        b2 = rd2.json()
    except ValueError:
        b2 = {}
    check('P2-1 非归属企业下载被拒(40401)', b2.get('code') == 40401,
          'http=%s body=%s' % (rd2.status_code, b2))
    # 平台管理员可下载任意附件
    rda = _dl(plat.s, fid)
    check('P2-1 平台管理员可下载', rda.status_code == 200 and rda.content.startswith(b'%PDF'),
          'http=%s' % rda.status_code)
    # 注册执照（无归属 sys_file，company_id=NULL）：匿名上传后任何企业不可下载，仅平台管理员可
    r = requests.post(BASE + '/auth/license',
                      files={'file': ('license-%s.pdf' % tag, b'%PDF-1.4 lic', 'application/pdf')},
                      timeout=15)
    lic = (r.json() or {}).get('data') or {}
    lid = lic.get('fileId')
    check('P2-1 匿名执照上传成功', bool(lid), r.text[:200])
    rd3 = _dl(steel.s, lid)
    try:
        b3 = rd3.json()
    except ValueError:
        b3 = {}
    check('P2-1 无归属执照企业端不可下载(40401)', b3.get('code') == 40401,
          'http=%s body=%s' % (rd3.status_code, b3))
    rda2 = _dl(plat.s, lid)
    check('P2-1 平台管理员可下载执照', rda2.status_code == 200 and rda2.content.startswith(b'%PDF'),
          'http=%s' % rda2.status_code)
    # 合同扫描件经 biz_contract 单据引用对订单参与方开放（仅 seed 环境存在演示合同件）
    demo_f = pg_one("SELECT file_id FROM sys_file WHERE file_id='democontractscan0000000000000001'")
    if demo_f:
        rdc = _dl(steel.s, 'democontractscan0000000000000001')
        check('P2-1 合同件对订单参与方开放', rdc.status_code == 200 and rdc.content.startswith(b'%PDF'),
              'http=%s' % rdc.status_code)
    else:
        print('  SKIP 演示合同文件不存在（清理后基线），跳过合同引用开放断言')

    return summary()


if __name__ == '__main__':
    ok = run()
    sys.exit(0 if ok else 1)
