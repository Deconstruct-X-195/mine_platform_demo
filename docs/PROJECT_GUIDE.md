# 大宗矿产集采平台一期 · 项目说明文档

> 本文档基于开发过程记录与现行代码库整理，覆盖：整体架构设计、前后端模块划分与接口说明、数据库表结构与初始化规则、环境部署与运行操作指南。

---

## 1. 项目定位与业务流程

### 1.1 功能定位

面向大宗矿产（铁矿石等）集采交易的一体化平台一期，实现从需求到归档的完整采购交易闭环，四类角色（钢厂 R1 / 供应商 R2 / 承运商 R3 / 平台运营 R0）权限隔离，所有单据流转经统一状态机管控并留痕。

### 1.2 核心业务流程（端到端 18 步）

```
需求申报(草稿/提交/撤回) → 脱敏需求池 → 远期预报挂价
→ 发起询价 → 邀请供应商 → 密封报价(截止前不可揭示/版本留痕)
→ 揭示并生成比价快照 → (可流标) → 多轮议价 → 接受/拒绝
→ 定标生成订单(落选报价置 LOSE) → 订单确认(48h 超时自动关闭)
→ 合同生成(版本留痕/SHA-256) → 双方顺序签署 → (可作废重签)
→ 物流方案 → 运单创建 → 承运商接单/派车/节点上报 → 签收
→ 履约时间轴 → 质检(超差触发预警) → 结算(双向确认冻结) → 付款登记
→ 归档(三条件校验) → 资料包导出(zip)
```

全程伴随五类定时预警扫描：报价截止、订单超时、运单超时、质检超差、结算超时（同对象同类型未关闭预警唯一，AC-19 去重）。后台定时任务（`backend/jobs.py`，默认间隔 3600 秒）除五类预警扫描外，还包含到期询价自动揭示与超时订单自动失效；`MINE_DISABLE_JOBS=1` 可整体禁用，`MINE_JOBS_INTERVAL` 可调整间隔。

---

## 2. 整体架构设计

### 2.1 技术栈与分层

```
┌─────────────────────────────────────────────┐
│ 前端 SPA（原生 JS，无构建）                    │
│   index.html + css/app.css                   │
│   js/app.js（外壳/路由/菜单/徽标）             │
│   js/api.js（fetch 封装） js/ui.js（组件库）    │
│   js/pages/*（23 个页面函数）                  │
├─────────────────────────────────────────────┤
│ Flask 3 后端（/api/v1 蓝图）                  │
│   应用工厂 backend/__init__.py                │
│   16 个业务模块 backend/api/*.py              │
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

- **状态机集中管控**（backend/state_machine.py）：所有单据流转经 `transition` 校验，非法流转抛 40901，每次流转写操作日志（前后值快照）。
- **脱敏需求池**：供应商仅见品种/数量/交货区域/期望月份，接口层不返回钢厂名称与价格意向。
- **密封报价**：截止前不可揭示；揭示生成比价快照；改价版本留痕。
- **归档三条件**：运单全部签收 + 结算完成 + 无未关闭预警；导出 zip 资料包。
- **AC-19 预警去重**：同对象同类型未关闭预警唯一（部分唯一索引），已关闭留痕后可再次产生。

---

## 3. 后端模块划分与 API 接口说明

所有接口前缀 `/api/v1`，鉴权方式 `Authorization: Bearer <JWT>`（公开接口除外：注册/登录）。

### 3.1 模块清单（backend/api/，16 个）

| 模块 | 职责 | | 模块 | 职责 |
|---|---|---|---|---|
| auth | 注册执照上传/注册/登录/当前用户 | | order | 定标/订单确认/订单查询 |
| company | 企业档案与准入 | | contract | 合同生成/签署/作废 |
| files | 附件上传下载 | | logistics | 物流方案/运单作业 |
| base | 品种与基准价查询 | | track | 履约时间轴/签收 |
| admin | 运营后台 | | settlement | 质检/结算/付款/归档 |
| demand | 需求申报与需求池 | | alert | 预警查询与处理 |
| forecast | 远期预报挂价 | | message | 站内消息 |
| inquiry | 询价/报价/揭示比价 | | bargain | 议价 |

### 3.2 接口明细（共 83 个端点）

**认证与用户（auth）**

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | /auth/license | 注册专用营业执照上传（免登录，≤20MB，返回 file_id） |
| POST | /auth/register | 企业注册（携带 licenseFileId） |
| POST | /auth/login | 登录签发 JWT |
| GET | /auth/me | 当前用户与企业信息 |

**企业（company）**

| 方法 | 路径 | 说明 |
|---|---|---|
| GET/PUT | /companies/me | 本企业档案查看/关键信息变更（触发重审） |
| GET | /companies /companies/&lt;cid&gt; | 企业列表/详情（运营） |

**附件（files）**

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | /files | 上传附件（≤20MB，返回 file_id） |
| GET | /files/&lt;file_id&gt; /admin/files | 下载 / 附件总览 |

**基础数据（base + admin）**

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | /base/varieties /base-prices/current | 品种列表 / 今日基准价 |
| POST/PUT | /admin/varieties | 品种新增/编辑 |
| POST | /admin/base-prices | 基准价录入 |
| GET | /admin/dicts /logs | 字典 / 操作日志 |

**需求申报（demand）**

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | /demands | 创建需求（草稿，含明细行） |
| PUT | /demands/&lt;did&gt; | 编辑（仅草稿） |
| POST | /demands/&lt;did&gt;/submit /withdraw /close | 提交/撤回/关闭 |
| GET | /demands /demands/&lt;did&gt; | 列表（R1 我的 / R2 脱敏池）/ 详情 |

**远期预报（forecast）**

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | /forecast-quotes | 供应商挂价 |
| PUT | /forecast-quotes/&lt;fid&gt; | 改价（版本留痕） |
| GET | /forecast-quotes | 列表（按角色视角） |
| POST | /forecast-quotes/&lt;fid&gt;/expire | 手动过期 |

**询价与报价（inquiry）**

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | /inquiries | 创建询价单（选需求/品种/数量/截止） |
| POST | /inquiries/&lt;iid&gt;/send | 邀请供应商并发出 |
| GET | /inquiries /inquiries/&lt;iid&gt; | 列表/详情 |
| POST | /inquiries/&lt;iid&gt;/quotes | 供应商密封报价 |
| PUT | /quotes/&lt;qid&gt; | 改价（版本留痕，截止前） |
| GET | /quotes/&lt;qid&gt; | 我的报价 |
| POST | /inquiries/&lt;iid&gt;/reveal | 揭示并生成比价快照 |
| GET | /inquiries/&lt;iid&gt;/quotes/reveal | 比价快照 |
| POST | /inquiries/&lt;iid&gt;/fail | 流标 |
| GET | /inquiries/&lt;iid&gt;/bargain-context | 议价上下文 |

**议价（bargain）**

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | /bargains | 发起议价轮次 |
| GET | /bargains | 议价列表 |
| PUT | /bargains/&lt;bid&gt;/accept /reject | 接受/拒绝 |

**订单与定标（order）**

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | /inquiries/&lt;iid&gt;/award | 定标生成订单（其余报价置 LOSE） |
| PUT | /orders/&lt;oid&gt;/confirm | 供应商确认（48h 超时自动关闭） |
| GET | /orders /orders/&lt;oid&gt; | 列表/详情 |

**合同（contract）**

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | /orders/&lt;oid&gt;/contract/generate | 生成合同（版本留痕/SHA-256） |
| POST | /contracts/&lt;cid&gt;/sign | 顺序签署 |
| POST | /contracts/&lt;cid&gt;/void | 作废重签 |
| GET | /contracts /contracts/&lt;cid&gt; | 列表/详情 |

**物流与运单（logistics）**

| 方法 | 路径 | 说明 |
|---|---|---|
| POST/GET | /orders/&lt;oid&gt;/logistics-plan | 物流方案创建/查看 |
| POST | /logistics-plans/&lt;pid&gt;/waybills | 创建运单 |
| PUT | /waybills/&lt;wid&gt;/assign /accept /node | 派车/接单/节点上报 |
| GET | /waybills /waybills/&lt;wid&gt; | 运单列表/详情 |

**履约跟踪（track）**

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | /orders/&lt;oid&gt;/timeline | 履约时间轴 |
| POST | /orders/&lt;oid&gt;/nodes | 里程碑节点上报 |
| POST | /waybills/&lt;wid&gt;/sign | 运单签收 |

**结算与归档（settlement）**

| 方法 | 路径 | 说明 |
|---|---|---|
| POST/GET | /orders/&lt;oid&gt;/quality-check(s) | 质检登记/列表（超差触发预警） |
| POST | /orders/&lt;oid&gt;/settlements | 发起结算（双向确认冻结） |
| PUT | /settlements/&lt;sid&gt;/confirm | 双方确认 |
| POST | /settlements/&lt;sid&gt;/payments | 付款登记 |
| POST | /orders/&lt;oid&gt;/archive | 归档（三条件校验） |
| GET | /orders/&lt;oid&gt;/archive/export | 资料包 zip 导出 |
| GET | /settlements /settlements/&lt;sid&gt; | 结算列表/详情 |

**预警与消息（alert / message）**

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | /alerts /alerts/&lt;aid&gt; | 预警列表/详情 |
| PUT | /alerts/&lt;aid&gt;/handle | 处理预警 |
| GET | /messages | 我的消息 |
| PUT | /messages/&lt;mid&gt;/read | 标记已读 |

**运营后台（admin）**

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | /admin/companies | 企业列表（审核状态筛选） |
| PUT | /admin/companies/&lt;cid&gt;/audit /status | 审核/启用停用 |
| GET | /admin/dashboard | 运营仪表盘 |
| GET | /admin/doc-overview | 单据总览 |

### 3.3 前端模块划分（frontend/js/，23 个页面）

| 文件 | 页面 |
|---|---|
| app.js | 应用外壳：hash 路由、角色菜单、消息徽标、登录态 |
| api.js | fetch 封装（契约解析/错误 toast/qs 拼接） |
| ui.js | 组件库：表格/弹窗/表单/状态标签/SVG 趋势图 |
| pages/auth.js | login、register |
| pages/demand.js | demand（需求申报）、pool（脱敏需求池） |
| pages/price.js | price（基准价行情）、forecast（远期预报） |
| pages/trade.js | inquiry（询价/报价）、bargain（议价工作台） |
| pages/order.js | order、contract、logistics、waybill、track |
| pages/settle.js | settlement（结算工作台） |
| pages/admin.js | dashboard、admin_companies、base_data、doc_overview、alerts、dict、logs |
| pages/misc.js | profile、messages |

路由规则：URL 用连字符（`#/admin-companies`），页面键用下划线（`admin_companies`），app.js 自动归一化。

---

## 4. 数据库表结构与初始化规则

### 4.1 表清单（docs/schema_postgresql.sql，共 25 张）

| 分组 | 表 | 说明 |
|---|---|---|
| 系统支撑 | sys_seq | 单据编号序列（前缀+日期发号，见 4.2） |
| | sys_user | 用户（手机号登录，bcrypt 散列，角色 PLAT_ADMIN/STEEL_BUYER/SUPPLIER/LOGISTICS_CARRIER） |
| | sys_operation_log | 操作日志（状态机流转前后值快照） |
| | sys_message | 站内消息 |
| | sys_file | 附件元数据 |
| 企业域 | ent_company | 企业档案（audit_status: PENDING/APPROVED/REJECTED） |
| | ent_qualification | 企业资质（证照有效期预警依据） |
| 基础数据 | base_variety | 品种档案（粉矿/块矿/精粉/球团等） |
| | base_price | 品种基准价（按日，湿基/干基） |
| 需求域 | biz_demand | 需求单（DRAFT→SUBMITTED→INQUIRING/DEALT/CLOSED，含 WITHDRAWN，脱敏字段） |
| | biz_demand_item | 需求明细行（品种/牌号 grade NUMERIC(5,2)/数量/交期） |
| 询价域 | biz_inquiry | 询价单（需求关联/截止时间；DRAFT→SENT→QUOTING→CLOSED→BARGAINING→AWARDED/FAILED，订单超时失效可回退重开定标） |
| | biz_inquiry_invite | 邀请记录（INVITED） |
| | biz_quote | 密封报价（版本留痕；SUBMITTED→REVEALED→BARGAINING→WIN/LOSE，REJECTED） |
| | biz_bargain | 议价轮次（PENDING/ACCEPTED/REJECTED/EXPIRED） |
| | biz_forecast_quote | 远期预报挂价 |
| 交易域 | biz_order | 订单（PENDING_CONFIRM→PENDING_CONTRACT→PENDING_EFFECT→PERFORMING→COMPLETED，含 CANCELLED 分支与超时失效） |
| | biz_contract | 合同（版本 + SHA-256 留痕；PENDING_GENERATE→PENDING_BUYER→PENDING_SUPPLIER→EFFECTIVE，可 VOID 作废重签） |
| 物流域 | biz_logistics_plan | 物流方案 |
| | biz_waybill | 运单（派车/接单/节点/签收） |
| | biz_track_node | 履约节点 |
| 结算域 | biz_quality_check | 质检记录（超差触发预警） |
| | biz_settlement | 结算单（PENDING_CONFIRM_SUPPLIER→PENDING_CONFIRM_BUYER→CONFIRMED→COMPLETED，双向确认） |
| | biz_payment | 付款登记 |
| 预警 | biz_alert | 五类预警（部分唯一索引实现 AC-19 去重） |

### 4.2 初始化规则

- **建表**：`run.py` 启动时调用 `backend/db.init_schema(conn)`，读取 `docs/schema_postgresql.sql` **幂等执行**（CREATE TABLE IF NOT EXISTS / CREATE INDEX IF NOT EXISTS / DROP trigger 守护），重复启动无副作用。
- **演示数据**：`backend/seed.py` 幂等写入——平台管理员、5 家演示企业与 6 个账号、4 个品种档案、当日基准价 8 行、字典项。
- **序列编号**：`sys_seq` 按「单据类型前缀 + 日期」发号，格式 `前缀-YYYYMMDD-4位流水`（如 `XJ-20261107-0001`），流水按日重置、作废不复用，保证编号连续唯一。
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
2. 全链路回归：服务运行中执行 `python tests/e2e_full_chain.py`（94 项检查，应全部 PASS）。

### 5.4 配置项

| 变量 | 默认值 | 说明 |
|---|---|---|
| `MINE_PG_DSN` | `postgresql://postgres:Langchain2026@127.0.0.1:5432/mine_platform` | 数据库连接串（生产必改） |
| `MINE_JWT_SECRET` | 内置演示密钥 | JWT 签名密钥（生产必改） |
| `MINE_PORT` | 8000 | 服务端口 |
| `MINE_DISABLE_JOBS` | 未设置 | `1` = 禁用后台定时任务（预警扫描/到期揭示/订单超时失效） |
| `MINE_JOBS_INTERVAL` | 3600 | 后台定时任务扫描间隔（秒） |

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
