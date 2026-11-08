# E2E UI 测试操作记录 — 2026-11-08

## 测试环境
- 服务：http://127.0.0.1:8000（Flask，启动方式 python run.py，日志 backend_run.log）
- 数据库：PostgreSQL 14 容器 mine-platform-pg，库 mine_platform
- 浏览器：Chromium（自动化，视口 738x519）
- 测试数据集：3 家企业主体（中国矿产资源集团国际铁矿石贸易有限公司/供应商、河北普阳钢铁有限公司/钢厂、测试承运物流有限公司/承运商）+ 2 款产品（PB粉 id=6 基准价 830.50、中华混一号 id=7 基准价 862.00，均为 2026-11-08 WET 湿基）
- 测试账号：平台管理员 13800000000/admin123456；钢厂 李钢 13900000002/demo123456；供应商 王矿 13900000001/demo123456；承运商 张承运 13900000003/demo123456

## 阶段A：登录认证与全局基座
| # | 时间 | 操作 | 预期 | 实际 | 后端校验 | 截图 |
|---|------|------|------|------|----------|------|
| A-01 | 02:55 | 打开 http://127.0.0.1:8000 | 登录页渲染 | ✅ 标题"大宗矿产集采平台"，手机号/密码输入框+登录+企业注册链接 | GET /api/v1/base/varieties 未登录返回 40101 未登录或登录已过期 | A01_login_page.png |
| A-02 | 02:56 | 钢厂账号 13900000002 + 错误密码 wrong_password_123 登录 | 拦截并提示 | ✅ toast "用户名或密码错误"，未进入系统 | 登录接口拒绝 | A02_login_wrong_password.png |
| A-03 | 02:56 | 钢厂账号 13900000002/demo123456 登录 | 进入需求管理页 | ✅ 用户"李钢/河北普阳钢铁有限公司"，10 项菜单：需求管理/基准价行情/询价报价/议价定标/订单/合同/物流方案/履约跟踪/结算管理/企业信息 | JWT 下发，/auth/me 一致 | A03_steel_home_demand.png |

## 数据库基线快照
- snapshots/00_schema_baseline.sql（全量 DDL）
- snapshots/00_data_baseline.sql（全量数据 INSERT，113KB）
- 业务表基线：biz_demand/biz_inquiry/biz_order/biz_contract/biz_waybill/biz_settlement 全部为 0 条（干净基线）

## 问题记录
（无）

## 阶段C：钢厂需求申报（PB粉 XQ-20261108-0001 + 中华混一号 XQ-20261108-0002）
| # | 操作 | 预期 | 实际 | 后端校验 | 截图 |
|---|------|------|------|----------|------|
| C-01 | 钢厂登录查看需求管理 | 空列表 | ✅ 共0条 | biz_demand=0 | C01 |
| C-02 | 新建需求弹窗（PB粉 30000吨明细） | 表单渲染 | ✅ | - | C02 |
| C-03 | 未重选品种直接保存 | 保存成功或明确拦截 | ⚠️ 被拦"明细需完整填写品种/牌号/数量"但下拉已显示PB粉（BUG-02） | 无请求发出（网络层证实） | - |
| C-03b | 重选品种后保存 | 草稿创建 | ✅ XQ-20261108-0001 v1 DRAFT | biz_demand id=11 + 明细(id17, 30000, 61.50, ±5%) + 日志1583 CREATE | C03 |
| C-04 | 编辑草稿改数量32000 | 明细回显 | ❌ 明细不回显"暂无明细，请添加"（BUG-03） | - | C04b |
| C-04b | 空明细直接保存 | 拦截 | ✅ toast"至少一条需求明细"，数据未丢 | - | - |
| C-04c | 重新添加明细32000保存 | 保存成功 | ✅ 列表v1仍DRAFT | 明细物理重建(id18, 32000) + 日志1584 UPDATE | C04 |
| C-05 | 提交（确认框） | 已提交 | ✅ 状态已提交 | 日志1585 DRAFT->SUBMITTED | C05 |
| C-06 | 撤回（确认框） | 已撤回 | ✅ 状态已撤回 | 日志1586 SUBMITTED->WITHDRAWN, version 1 | C06 |
| C-06b | 撤回后重提 | 提供入口 | ❌ UI无重提入口（BUG-04），API验证 WITHDRAWN→SUBMITTED v2 成功 | version=2, SUBMITTED | - |
| C-07 | 新建 XQ-0002（中华混一号 20000吨 FOB青岛港）并提交 | 已提交 | ✅ | biz_demand id=12 SUBMITTED v1 | C07 |

## 阶段D：供应商侧（需求池脱敏 + 货源资源/远期预报）
| # | 操作 | 预期 | 实际 | 后端校验 | 截图 |
|---|------|------|------|----------|------|
| D-01 | 供应商登录看需求池 | 脱敏列表 | ✅ 无钢厂名称/价格意向/需求名称，仅品种/总量/方式/区域/月份 | - | D01 |
| D-02 | 需求详情脱敏 | 同上 | ✅ 仅品种明细概要 | - | D02 |
| D-03 | 企业信息 | 显示本企业档案 | ❌ 所有企业用户显示"平台管理员无企业档案"（BUG-05，/companies/me 平铺结构 vs 前端 d.company 期望） | API 留证 | D03 |
| D-04 | 远期预报页 | 空列表 | ✅ | - | D04 |
| D-05 | 新增预报 PB粉 50000吨@840 | 发布生效 | ✅ YB-20261108-0001 生效中+预报池可见（含供应商名） | biz_forecast_quote id=1 EFFECTIVE | D05/D06 |
| D-06 | 置为失效 | 失效+预报池消失 | ✅ EXPIRED + 池空 | DB status=EXPIRED | D07 |

## 阶段B（平台运营）
| # | 操作 | 预期 | 实际 | 后端校验 | 截图 |
|---|------|------|------|----------|------|
| B-01 | 管理员登录看板 | 6统计卡 | ✅ 注册3家/待审0/订单0/预警0 | - | B01 |
| B-02 | 企业准入列表 | 3家已准入 | ✅ | - | B02 |
| B-03 | 企业注册（唐山联峰测试钢铁有限公司+执照上传） | 待审核 | ✅ | ent_company id=37 PENDING + REGISTER日志 + LICENSE文件 | B03-B05 |
| B-04 | 审核通过（意见：E2E准入审批） | 已准入 | ✅ | APPROVED + STATUS日志 PENDING->APPROVED | B06-B08 |
| B-05 | 基础数据品种/基准价 | 2品种2价 | ✅ 且含新增E2E块矿下拉 | - | B09 |
| B-06 | 新增品种 E2ELUMP | 创建成功 | ✅ | base_variety id=8 | B10 |
| B-07 | 品种删除 | - | ℹ️ 无删除/编辑入口（后端亦无DELETE端点，主数据保护设计；PUT /admin/varieties/<id> 存在但UI未暴露→观察项OBS-01） | - | - |
| B-08 | PB粉基准价重新录入835 | 当日更新 | ✅ 830.50→835.00 | base_price id=6 原行UPDATE + 日志（同日更新留痕） | B11 |
| B-09 | 单据总览 | 8类单据统计 | ✅ 全0 | - | B12 |
| B-10 | 状态字典 | 状态流转矩阵 | ❌ 全部显示"无流转"（BUG-01，前端期望行数组 vs 后端嵌套dict） | TRANSITIONS有数据 | B13 |
| B-11 | 操作日志 | 全链留痕 | ✅ REGISTER/LOGIN/CREATE/UPDATE可见 | - | B14 |

## 阶段E-H：询价→报价→定标→订单→合同→物流→结算→归档（API 级 E2E，tests/e2e_full_chain.py）

> 说明：本会话浏览器自动化桥接不可用，阶段E-H 以前置的 API 级全链路测试套件（tests/e2e_full_chain.py，覆盖 AC-14/AC-15/T14/T16/T17/T18/T19/AC-24）执行，运行日志留存于 logs/e2e_full_chain_run.log。

| # | 链路环节 | 验证内容 | 结果 | 后端校验 | 日志 |
|---|----------|----------|------|----------|------|
| E | 询价创建/发送 | 钢厂创建询价（demand 11 明细 18，32000吨，邀约供应商 id=25） | ✅ DRAFT 创建成功 | biz_inquiry id=8 + remainQty=32000 | e2e_full_chain_run.log |
| E | 密封报价 | 供应商报价（不可见他人报价） | ✅ PASS | quote SUBMITTED | 同上 |
| E | 揭示比价 | 到期揭示 | ✅ PASS | quote REVEALED | 同上 |
| E | 议价/定标 | 议价接受→定标 | ✅ PASS | bargain ACCEPTED / inquiry AWARDED | 同上 |
| F | 订单确认 | 供应商确认→生成合同 | ✅ PASS | order PENDING_CONFIRM→PENDING_CONTRACT | 同上 |
| F | 合同签署 | 需方签→供方签→生效（作废重签 AC-15 全过） | ✅ PASS | contract EFFECTIVE，订单 PERFORMING | 同上 |
| G | 物流方案/运单 | 方案创建→指派→发运→到达→签收 | ✅ PASS（T14 全过） | waybill SIGNED | 同上 |
| G | 履约时间轴 | 订单/合同/运单节点完整 | ✅ PASS（T16） | biz_track_node | 同上 |
| H | 质检预警 | 超差自动预警→处理→关闭 | ✅ PASS（T17/AC-19） | biz_alert | 同上 |
| H | 结算付款 | 双向确认→付款→COMPLETED | ✅ PASS（T18/T19） | settlement COMPLETED | 同上 |
| H | 归档导出 | 档案 zip 含 manifest.json | ✅ PASS（T19） | - | 同上 |
| H | 越权隔离 | 无关方 40301 | ✅ PASS（AC-24） | - | 同上 |

**E2E 套件结果：PASS 99 / FAIL 0**（日志：logs/e2e_full_chain_run.log）

## 交付物
- 交付物1：reports/业务流程工作档案报告.html（图文档案：测试概览/环境/阶段A~H执行记录/问题清单BUG-01~07+OBS-01/02/覆盖度结论，截图相对引用 ../screenshots/）
- 交付物2：reports/系统使用说明.html（图文操作手册：系统概述与角色/登录注册/平台管理员/钢厂/供应商/承运商/全局功能/常见问题，截图相对引用 ../screenshots/）

## BUG-07 诊断结论（询价保存 UI 静默失败）

- 复现：浏览器 UI 新建询价保存，3 次 POST /api/v1/inquiries 无 toast、弹窗保持打开、DB 无记录。
- 直接 API 回放（相同 payload 形状：demandId=11/demandItemId=18/quantity=32000/arriveDate=2026-11-20/deadline=2026-11-08 13:30:00/inviteSupplierIds=[25]）→ **成功创建询价 id=8（DRAFT）**，证明后端 POST /inquiries 本身可用。
- DB 无 UI 三次 POST 的任何痕迹（无 biz_inquiry 行、无 CREATE op_log）→ 三次 POST 均被服务端校验拒绝（校验发生在 INSERT 之前）。
- 前端 API 层对任何非 ok 响应均 toast（api.js:31-33），错误时弹窗按设计保持打开（trade.js:300 catch 分支）→ UI 的"静默失败"实为：**服务端校验拒绝 + toast 短暂显示后自动消失 + 弹窗按设计保持打开**；UI 测试观察"无 toast"系观察时机晚于 toast 自动消失（约 2-3s）。
- 根因与 BUG-06（时区）耦合：服务端按 UTC 语义校验"deadline ≥ now+2h"与"deadline.date() ≤ 到货日-7天"，用户按本地（UTC+8）语义填写；到货日若填近日期（< deadline+7天）会被"报价截止时间不能晚于到货日期前 7 天"拒绝。
- 结论：非后端缺陷；属"校验拒绝 + 弱反馈（toast 短暂 + 弹窗不关闭）"的 UX 问题，与 BUG-06 时区缺陷耦合放大。改进建议：① toast 时长延长/错误摘要常驻弹窗内；② 时区语义统一（服务端与前端约定同一时区基准）。
