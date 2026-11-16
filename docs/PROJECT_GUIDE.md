# 大宗矿产集采平台一期 · 项目说明文档

> 本文档基于开发过程记录与现行代码库整理，覆盖：整体架构设计、前后端模块划分与接口说明、数据库表结构与初始化规则、环境部署与运行操作指南。
>
> 更新：2026-11-16（同步 process-1 范围调整——三端架构、需求归集/平台代发询价/整单锁货锁价/提货计划链路、95306 式物流轨迹、接口与表结构；承运商端与合同/结算前端入口下线）

---

## 1. 项目定位与业务流程

### 1.1 功能定位

面向大宗矿产（铁矿石等）集采交易的一体化平台一期，三端角色（钢厂需方 R1 / 供应商供方 R2 / 平台运营 R0）权限隔离，所有单据流转经统一状态机管控并留痕。

- **承运商端已下线**（2026-11-13 范围调整，交付报告 §37）：平台采购不再涉及承运商，前端无承运商端入口（承运商账号登录后无可用菜单/首页）；注册仅开放钢厂/供应商。
- **合同与结算板块前端下线**：后端接口与数据层保留（API 级可用），前端无入口；运营端保留合同扫描件核验。

### 1.2 核心业务流程

**主链路（需求归集 → 平台代发 → 整单锁货锁价）：**

```
钢厂需求申报(草稿/提交/撤回) → 运营端需求归集池(合并多钢厂需求 → 聚合订单 OPEN, 按份额写 biz_order_member)
→ 平台代发询价(batch_no, 可多轮) → 邀请供应商 → 密封报价(截止前不可揭示/版本留痕)
→ 汇总比价 → 钢厂反馈全员认可(ACCEPT) 自动成单 / 汇总退回(REJECT→FEEDBACK→CLOSED→重新询价, 历史轮次可参考)
→ 聚合订单 AWARDED → 生成订单 PENDING_PICKUP → 供应商确认(48h 超时失效→聚合订单回退可重新询价)
→ 提货计划收集(钢厂全员提交→待制定运输方案) → 运输方案制定(铁路直达/公铁联运/汽运直达)
→ 创建分段运单(ROAD/RAIL) → 95306 式节点推进 PENDING_DEPART→IN_TRANSIT→ARRIVED→SIGNED
→ 需方签收 → 履约时间轴 → 质检(超差触发预警) → 归档(三条件校验) → 资料包导出(zip)
```

**钢厂单笔采购链路（保留）**：钢厂采购询价（STEEL 来源：创建→邀请→密封报价→揭示→多轮议价→钢厂定标）→ 生成普通订单 → 供应商确认 → 后续物流/履约同上。

**辅助链路**：需求脱敏归集（运营端 `demand_pool`）、远期预报挂价（接口保留）、合同生成/双签/平台核验（接口保留）、质检/结算/付款/归档（接口保留）。

全程伴随五类定时预警扫描：报价截止、订单超时、运单超时、质检超差、结算超时（同对象同类型未关闭预警唯一，AC-19 去重）。后台定时任务（`backend/jobs.py`，默认间隔 3600 秒）包含：到期询价自动揭示、供应商 48h 未确认订单失效（普通订单回退中标报价并重开询价；聚合订单经 `_rollback_agg_order` 回退成员锁定量/需求状态并通知）、五类预警扫描（`MINE_DISABLE_JOBS=1` 整体禁用，`MINE_JOBS_INTERVAL` 调整间隔，`MINE_ALERT_SCAN_INTERVAL` 配置预警扫描节流）。

---

## 2. 整体架构设计

### 2.1 技术栈与分层

```
┌─────────────────────────────────────────────┐
│ 前端 SPA（原生 JS，无构建）                    │
│   index.html + css/app.css                   │
│   js/app.js（外壳/路由/菜单/徽标）             │
│   js/api.js（fetch 封装） js/ui.js（组件库）    │
│   js/pages/*（8 文件，25 个页面函数）          │
├─────────────────────────────────────────────┤
│ Flask 3 后端（/api/v1 蓝图）                  │
│   应用工厂 backend/__init__.py                │
│   16 个业务模块 backend/api/*.py（127 端点）   │
│   公共件 security/state_machine/common        │
│   定时任务 alerts + jobs（进程内线程）          │
├─────────────────────────────────────────────┤
│ 数据访问层 backend/db.py（psycopg 3 封装）     │
├─────────────────────────────────────────────┤
│ PostgreSQL 14（Docker 容器 mine-platform-pg） │
└─────────────────────────────────────────────┘
```

### 2.2 请求生命周期（backend/\_\_init\_\_.py）

1. `before_request`：`/api/` 请求开启一个 psycopg 连接（dict_row）挂到 `g.conn`；
2. 蓝图内模块经 `security.auth_required` / `roles_required` 完成 JWT 与角色鉴权；
3. `teardown_request`：无异常则提交事务，有异常整体回滚并关闭连接（业务校验失败不留脏数据）；
4. 错误拦截：`ApiError`（业务异常）→ `{"code","message","data":null}`；HTTPException 映射业务码；兜底 50001。

### 2.3 统一响应契约

```json
{ "code": 0, "message": "success", "data": { } }
```

| 业务码 | 含义 | | 业务码 | 含义 |
|---|---|---|---|---|
| 40001 | 参数错误 | | 40901 | 状态冲突 |
| 40101 | 未认证 | | 40902 | 重复 |
| 40301 | 越权 | | 50001 | 内部错误 |
| 40401 | 不存在 | | | |

### 2.4 关键设计

- **状态机集中管控**（backend/state_machine.py）：所有单据流转经 `transition` 校验，非法流转抛 40901，每次流转写操作日志（前后值快照）。运单状态机 `PENDING_DEPART→IN_TRANSIT→ARRIVED→SIGNED`，运单创建即确认生效（承运商端下线，接单环节取消）。
- **整单锁货锁价 / 聚合订单**（biz_aggregated_order）：运营端合并多钢厂需求生成聚合订单（`buyer_id` 为空），按钢厂份额写入 `biz_order_member`；归集询价全员认可后整体定标成单。
- **多轮询价与历史轮次**：平台代发询价按 `batch_no` 分轮，汇总退回后重新发起（旧询价 FEEDBACK→CLOSED）；供应商报价界面返回 `roundNo`/`historyRounds`（仅已揭示轮次，含钢厂反馈理由）。
- **提货计划收集**（biz_order_member）：钢厂成员提交提货开始日期/日提货吨数，全员提交后订单转入待制定运输方案。
- **需求脱敏**：需求归集池仅供运营端使用；供应商侧仅见被邀请的询价内容。
- **密封报价**：截止前不可揭示；揭示生成比价快照；改价版本留痕。
- **归档三条件**：运单全部签收 + 结算完成 + 无未关闭预警；导出 zip 资料包。
- **AC-19 预警去重**：同对象同类型未关闭预警唯一（部分唯一索引），已关闭留痕后可再次产生。

---

## 3. 后端模块划分与 API 接口说明

所有接口前缀 `/api/v1`，鉴权方式 `Authorization: Bearer <JWT>`（公开接口除外：注册执照上传/注册/登录）。

### 3.1 模块清单（backend/api/，16 个）

| 模块 | 职责 | | 模块 | 职责 |
|---|---|---|---|---|
| auth | 执照上传/注册/登录/当前用户（返回菜单） | | order | 定标/确认/提货计划/订单查询/端首页总览 |
| company | 企业档案/资质上传/变更重审 | | contract | 合同生成/签署/作废（前端下线，接口保留） |
| files | 附件上传下载 | | logistics | 物流方案/分段运单/节点上报 |
| base | 品种/基准价/港口价/成交趋势 | | track | 履约时间轴/在途跟踪/手工节点/签收 |
| admin | 运营后台（准入/归集/代发询价/聚合订单/运输/核验/看板） | | settlement | 质检/结算/付款/归档（前端下线，接口保留） |
| demand | 需求申报与管理 | | alert | 预警查询与处理 |
| forecast | 远期预报挂价（接口保留） | | message | 站内消息/待办 |
| inquiry | 询价/报价/揭示/归集反馈/历史轮次 | | bargain | 议价轮次 |

### 3.2 接口明细（共 127 个端点）

**认证与用户（auth，4）**

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | /auth/license | 注册专用营业执照上传（免登录，≤20MB，返回 file_id） |
| POST | /auth/register | 企业注册（携带 licenseFileId，待准入） |
| POST | /auth/login | 登录签发 JWT（返回菜单） |
| GET | /auth/me | 当前用户与企业信息（菜单会话静默刷新） |

**企业（company，5）**

| 方法 | 路径 | 说明 |
|---|---|---|
| GET/PUT | /companies/me | 本企业档案查看/关键信息变更（触发重审） |
| POST | /companies/me/qualifications | 资质证照在线上传 |
| GET | /companies /companies/&lt;cid&gt; | 企业名录/详情 |

**附件（files，3）**

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | /files | 上传附件（≤20MB，返回 file_id） |
| GET | /files/&lt;file_id&gt; | 下载附件 |
| GET | /admin/files | 附件总览（运营） |

**基础数据（base，6）**

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | /base/varieties | 品种列表 |
| GET | /base-prices/current | 今日基准价（双品位） |
| GET | /base-prices/deal-trend | 成交价趋势 |
| GET/POST | /base-prices/ports | 港口现货价（双品位）查询/录入 |
| DELETE | /base-prices/ports/&lt;pid&gt; | 删除港口价 |

**需求申报（demand，7）**

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | /demands | 创建需求（草稿，含明细行） |
| PUT | /demands/&lt;did&gt; | 编辑（仅草稿，生成新版本） |
| POST | /demands/&lt;did&gt;/submit /withdraw /close | 提交/撤回/关闭 |
| GET | /demands /demands/&lt;did&gt; | 列表（钢厂我的需求）/ 详情 |

**远期预报（forecast，4，接口保留）**

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | /forecast-quotes | 供应商挂价 |
| PUT | /forecast-quotes/&lt;fid&gt; | 锁定期内修改（版本留痕） |
| GET | /forecast-quotes | 列表（按角色视角） |
| POST | /forecast-quotes/&lt;fid&gt;/expire | 手动过期 |

**询价与报价（inquiry，12）**

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | /inquiries | 钢厂创建采购询价（DRAFT） |
| POST | /inquiries/&lt;iid&gt;/send | 发送并邀请供应商 |
| GET | /inquiries /inquiries/&lt;iid&gt; | 列表（含归集视图 aggView）/ 详情 |
| POST | /inquiries/&lt;iid&gt;/quotes | 供应商密封报价 |
| PUT | /quotes/&lt;qid&gt; | 改价（版本留痕，截止前） |
| GET | /quotes/&lt;qid&gt; | 我的报价 |
| POST | /inquiries/&lt;iid&gt;/reveal | 手动揭示（生成比价快照） |
| GET | /inquiries/&lt;iid&gt;/quotes/reveal | 比价结果（含 roundNo/historyRounds 历史轮次） |
| POST | /inquiries/&lt;iid&gt;/feedback | 归集询价钢厂反馈（ACCEPT/REJECT，附理由） |
| POST | /inquiries/&lt;iid&gt;/fail | 作废询价 |
| GET | /inquiries/&lt;iid&gt;/bargain-context | 议价上下文 |

**议价（bargain，4，钢厂单笔采购链路）**

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | /bargains | 发起议价轮次 |
| GET | /bargains | 议价列表 |
| PUT | /bargains/&lt;bid&gt;/accept /reject | 接受/拒绝 |

**订单与提货（order，7）**

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | /inquiries/&lt;iid&gt;/award | 钢厂定标生成订单（其余报价置 LOSE） |
| PUT | /orders/&lt;oid&gt;/confirm | 供应商确认（48h 超时失效；聚合订单确认后进入提货计划收集） |
| GET | /orders /orders/&lt;oid&gt; | 列表/详情（含成员提货计划状态） |
| POST | /orders/&lt;oid&gt;/pickup-plan | 钢厂提交提货计划（开始日期/日提货吨数/备注） |
| GET | /buyer/overview /supplier/overview | 钢厂/供应商端首页总览 |

**合同（contract，6，前端下线，接口保留）**

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | /orders/&lt;oid&gt;/contract/generate | 生成合同（版本留痕/SHA-256） |
| POST | /contracts/&lt;cid&gt;/sign | 签署（上传盖章件） |
| POST | /contracts/&lt;cid&gt;/void | 作废重签 |
| GET | /contracts /contracts/&lt;cid&gt; /contracts/&lt;cid&gt;/files | 列表/详情/附件 |

**物流与运单（logistics，8）**

| 方法 | 路径 | 说明 |
|---|---|---|
| POST/GET | /orders/&lt;oid&gt;/logistics-plan | 钢厂物流方案创建/查看（SELF/PLATFORM） |
| POST | /logistics-plans/&lt;pid&gt;/waybills | 创建分段运单（创建即生效） |
| PUT | /waybills/&lt;wid&gt;/assign | 指派承运商（端点保留，承运商端已下线） |
| PUT | /waybills/&lt;wid&gt;/accept | 承运商接单（端点保留，已停用） |
| PUT | /waybills/&lt;wid&gt;/node | 节点上报 |
| GET | /waybills /waybills/&lt;wid&gt; | 运单列表/详情 |

**履约跟踪（track，4）**

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | /orders/&lt;oid&gt;/timeline | 履约时间轴 |
| GET | /orders/&lt;oid&gt;/tracking | 在途跟踪 |
| POST | /orders/&lt;oid&gt;/nodes | 手工里程碑节点 |
| POST | /waybills/&lt;wid&gt;/sign | 需方签收 |

**结算与归档（settlement，9，前端下线，接口保留）**

| 方法 | 路径 | 说明 |
|---|---|---|
| POST/GET | /orders/&lt;oid&gt;/quality-check(s) | 质检登记/列表（超差触发预警并通知成员钢厂） |
| POST | /orders/&lt;oid&gt;/settlements | 发起结算（双向确认冻结） |
| PUT | /settlements/&lt;sid&gt;/confirm | 确认（先供后购） |
| POST | /settlements/&lt;sid&gt;/payments | 付款登记 |
| POST | /orders/&lt;oid&gt;/archive | 归档（三条件校验） |
| GET | /orders/&lt;oid&gt;/archive/export | 资料包 zip 导出 |
| GET | /settlements /settlements/&lt;sid&gt; | 结算列表/详情 |

**预警与消息（alert，3 / message，4）**

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | /alerts /alerts/&lt;aid&gt; | 预警列表/详情 |
| PUT | /alerts/&lt;aid&gt;/handle | 处理预警 |
| GET | /messages /tasks/todos | 我的消息 / 待办清单 |
| PUT | /messages/&lt;mid&gt;/read /messages/read-all | 标记已读 / 一键全读 |

**运营后台（admin，41，全部运营权限）**

| 分组 | 端点 | 说明 |
|---|---|---|
| 企业准入 | GET /admin/companies；PUT /admin/companies/&lt;id&gt;/reset-password /audit /status | 企业列表/重置密码/准入审核/启停 |
| 需求归集 | GET /admin/demand-pool；GET /admin/demand-changes；PUT /admin/demand-changes/&lt;id&gt;/audit | 归集池/变更申请/变更审核 |
| 归集订单 | GET/POST /admin/aggregated-orders；GET /admin/aggregated-orders/&lt;id&gt;；PUT /admin/aggregated-orders/&lt;id&gt;/close | 聚合订单列表/创建（合并需求写成员份额）/详情/关闭 |
| 平台代发询价 | GET/POST /admin/quote-inquiries；POST /admin/quote-inquiries/&lt;iid&gt;/award；GET /admin/quote-inquiries/&lt;iid&gt;/feedbacks /summary；POST /admin/quote-inquiries/&lt;iid&gt;/return；GET /admin/quote-history /admin/quote-history/&lt;iid&gt; | 批量代发/定标生成订单/钢厂反馈/汇总比价/汇总退回重新询价/询价历史 |
| 合同核验 | GET /admin/contracts；PUT /admin/contracts/&lt;id&gt;/verify | 合同台账/扫描件核验（CONFIRMED/RETURNED） |
| 运输与提货 | GET /admin/logistics-stats /logistics-orders /orders /orders/&lt;id&gt; /waybills-ops；POST /admin/logistics-plans；POST /admin/logistics-plans/&lt;pid&gt;/waybills；PUT /admin/waybills/&lt;wid&gt;/assign /advance | 调度统计/调度订单/订单管理（提货进度）/运单运营操作/运输方案创建/分段运单创建/指派/节点推进 |
| 结算查询 | GET /admin/settlement-stats /admin/settlements /admin/settlements/&lt;id&gt;/payments | 结算统计/列表/付款记录 |
| 基础与看板 | POST /admin/varieties；PUT /admin/varieties/&lt;id&gt;；POST /admin/base-prices；GET /admin/dashboard /charts /doc-overview /dicts /logs | 品种/基准价录入/仪表盘/单据总览/字典/操作日志 |

### 3.3 前端模块划分（frontend/js/，8 文件 25 个页面）

| 文件 | 页面 |
|---|---|
| app.js | 应用外壳：hash 路由、角色菜单（来自后端 user.menus）、消息徽标、登录态 |
| api.js | fetch 封装（契约解析/错误 toast/qs 拼接） |
| ui.js | 组件库：表格/弹窗/表单/状态标签/SVG 趋势图 |
| pages/auth.js | login、register |
| pages/overview.js | overview（钢厂/供应商端首页总览） |
| pages/demand.js | demand（需求申报） |
| pages/price.js | price（基准价行情） |
| pages/trade.js | inquiry（询价/报价）、bargain（议价工作台） |
| pages/order.js | order（订单管理）、logistics（物流服务）、track（履约跟踪） |
| pages/admin.js | dashboard、port_price、price_records、admin_companies、demand_pool、quote_inquiry、quote_history、base_data、order_admin、alerts、dict、logs、logistics_dispatch |
| pages/misc.js | profile、messages |

角色菜单（backend/security.py，后端下发）：

| 角色 | 菜单 |
|---|---|
| STEEL_BUYER（钢厂需方） | overview, demand, price, inquiry（采购询价）, bargain, order, logistics, track, profile |
| SUPPLIER（供应商供方） | overview, inquiry, order, logistics, track, profile |
| PLAT_ADMIN（平台运营） | dashboard, admin_companies, demand_pool, quote_center（quote_inquiry/quote_history）, order_admin, logistics_dispatch, base_data, alerts, dict, logs |
| LOGISTICS_CARRIER | 无菜单（承运商端已下线） |

非菜单页：port_price/price_records（看板下钻）、messages（消息抽屉入口）。路由规则：URL 用连字符（`#/admin-companies`），页面键用下划线（`admin_companies`），app.js 自动归一化。

---

## 4. 数据库表结构与初始化规则

### 4.1 表清单（docs/schema_postgresql.sql，共 30 张）

| 分组 | 表 | 说明 |
|---|---|---|
| 系统支撑 | sys_seq | 单据编号序列（前缀+日期发号，见 4.2） |
| | sys_user | 用户（手机号登录，bcrypt 散列；角色 PLAT_ADMIN/STEEL_BUYER/SUPPLIER/LOGISTICS_CARRIER） |
| | sys_operation_log | 操作日志（状态机流转前后值快照） |
| | sys_message | 站内消息 |
| | sys_file | 附件元数据 |
| 企业域 | ent_company | 企业档案（audit_status: PENDING/APPROVED/REJECTED） |
| | ent_qualification | 企业资质（证照有效期预警依据） |
| 基础数据 | base_variety | 品种档案（含默认牌号 grade NUMERIC(5,2)） |
| | base_price | 品种基准价（按日，湿基/干基双品位） |
| | base_port_price | 港口现货价（品种×港口×日期，行情联动源） |
| 需求域 | biz_demand | 需求单（DRAFT→SUBMITTED→INQUIRING/DEALT/CLOSED，含 WITHDRAWN；关联聚合 agg_id） |
| | biz_demand_item | 需求明细行（品种/牌号/数量/交期） |
| | biz_demand_change | 需求变更申请（运营审核闭环） |
| 归集域 | biz_aggregated_order | 聚合订单（OPEN→INQUIRING→AWARDED→CLOSED；buyer_id 为空） |
| | biz_aggregated_order_item | 聚合订单明细（按钢厂拆分份额） |
| | biz_agg_inquiry_feedback | 归集询价钢厂反馈（ACCEPT/REJECT + 理由） |
| 询价域 | biz_inquiry | 询价单（source: STEEL/PLATFORM、batch_no、agg_id；DRAFT→SENT→QUOTING→FEEDBACK→CLOSED→BARGAINING→AWARDED/FAILED） |
| | biz_inquiry_invite | 邀请记录（含拒绝/未响应可再邀请） |
| | biz_quote | 密封报价（版本留痕；SUBMITTED→REVEALED→BARGAINING→WIN/LOSE/REJECTED） |
| | biz_bargain | 议价轮次（PENDING/ACCEPTED/REJECTED/EXPIRED） |
| | biz_forecast_quote | 远期预报挂价（接口保留） |
| 交易域 | biz_order | 订单（PENDING_PICKUP→PENDING_TRANSPORT→PENDING_CONFIRM→PENDING_CONTRACT→PENDING_EFFECT→PERFORMING→COMPLETED，含 CANCELLED 与 48h 超时失效） |
| | biz_contract | 合同（版本 + SHA-256 留痕；PENDING_GENERATE→PENDING_BUYER→PENDING_SUPPLIER→EFFECTIVE，可 VOID；plat_status 运营核验态） |
| 物流域 | biz_logistics_plan | 运输方案（SELF/PLATFORM；铁路直达/公铁联运/汽运直达，起运地黄骅港/天津港） |
| | biz_waybill | 分段运单（PENDING_DEPART→IN_TRANSIT→ARRIVED→SIGNED；carrier_id 为下线残留字段） |
| | biz_track_node | 履约节点（source: SYSTEM/CARRIER/MANUAL，95306 式节点码） |
| 结算域 | biz_quality_check | 质检记录（超差触发预警并通知成员钢厂） |
| | biz_settlement | 结算单（先供后购双向确认；接口保留） |
| | biz_payment | 付款登记（接口保留） |
| 预警 | biz_alert | 五类预警（部分唯一索引实现 AC-19 去重） |

> 已知差异：业务代码（admin/order/jobs）使用 **biz_order_member** 表（订单成员钢厂份额与提货计划字段 pickup_status/pickup_start_date/daily_qty/pickup_remark），该表未收录在 schema_postgresql.sql 蓝本中，由应用侧建表逻辑维护。

### 4.2 初始化规则

- **建表**：`run.py` 启动时调用 `backend/db.init_schema(conn)`，读取 `docs/schema_postgresql.sql` **幂等执行**（CREATE TABLE IF NOT EXISTS / CREATE INDEX IF NOT EXISTS / DROP trigger 守护），重复启动无副作用。
- **演示数据**：`backend/seed.py` 幂等写入——平台管理员（13800000000/admin123456）+ 5 家演示企业 6 个账号（示范钢铁 13800000001、示范矿产贸易 13800000002、示范矿业 13800000003、示范国际供应链 13800000004、示范物流 13800000005/承运商已下线无菜单；企业账号密码均 demo123456）、品种 PB粉/中华混一号、当日基准价（双品位）、近 14 日黄骅港/日照港港口价、演示合同 5 张（含核验态）、演示订单 4 张、物流方案与分段运单（ROAD 在途/RAIL 待发运）、演示消息。
- **序列编号**：`sys_seq` 按「单据类型前缀 + 日期」发号，格式 `前缀-YYYYMMDD-4位流水`（如 `XJ-20261107-0001`），流水按日重置、作废不复用。
- **重置**：清空数据库（或删除库重建）后重跑 `python run.py` 即恢复初始演示状态。

---

## 5. 环境部署与运行操作指南

### 5.1 环境要求

| 依赖 | 版本要求 | 用途 |
|---|---|---|
| Docker（含 Compose V2） | 任意近期版本 | 运行 PostgreSQL 14 |
| Python | 3.12+（开发环境 3.14） | 后端与测试 |
| pip | 随 Python | 安装依赖 |

### 5.2 一键部署步骤

```bash
git clone https://github.com/Deconstruct-X-195/mine_platform_demo.git
cd mine_platform_demo

# 1. 启动数据库容器（自动创建 mine_platform 库，数据持久化于 named volume）
docker compose up -d

# 2. 安装依赖
pip install -r requirements.txt

# 3. 启动（首次自动建表 + 写入演示数据，之后每次启动幂等）
python run.py          # → http://127.0.0.1:8000
```

### 5.3 验证部署

1. 浏览器打开 http://127.0.0.1:8000，用演示账号登录（平台运营 `13800000000/admin123456`，其余 `demo123456`）；
2. 全链路回归（服务运行中执行）：
   - `python tests/e2e_full_chain.py`（100 项检查，应全部 PASS）；
   - `python tests/e2e_agg_flow.py`（需求归集环节专项）。

### 5.4 配置项

| 变量 | 默认值 | 说明 |
|---|---|---|
| `MINE_PG_DSN` | `postgresql://postgres:Langchain2026@127.0.0.1:5432/mine_platform` | 数据库连接串（生产必改） |
| `MINE_JWT_SECRET` | 内置演示密钥 | JWT 签名密钥（生产必改） |
| `MINE_PORT` | 8000 | 服务端口 |
| `MINE_DISABLE_JOBS` | 未设置 | `1` = 禁用后台定时任务（预警扫描/到期揭示/订单超时失效） |
| `MINE_JOBS_INTERVAL` | 3600 | 后台定时任务扫描间隔（秒） |
| `MINE_ALERT_SCAN_INTERVAL` | 未设置 | 预警扫描节流间隔（秒），默认 24h 节流 |

### 5.5 常用运维操作

| 操作 | 命令 |
|---|---|
| 启停数据库 | `docker compose up -d` / `docker compose down`（数据保留） |
| 彻底清库 | `docker compose down -v` 后重新 `up -d` + `python run.py` |
| 重置演示数据 | 清空库后重跑 `python run.py`（建表与种子均幂等） |
| 查看数据库 | `docker exec -it mine-platform-pg psql -U postgres -d mine_platform` |

### 5.6 生产部署注意

- 更换 WSGI 服务器（waitress/gunicorn），Flask 内置服务器仅限演示；
- 通过环境变量注入 `MINE_PG_DSN` 与 `MINE_JWT_SECRET`，勿使用代码默认值；
- 建议为 PostgreSQL 配置独立账号（最小权限）与定期备份策略；
- 上传附件存于本地 `uploads/` 目录，多实例部署需改为对象存储。
