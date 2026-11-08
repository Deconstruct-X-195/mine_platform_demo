# 大宗矿产集采平台（一期）

面向大宗矿产（铁矿石等）集采交易的一体化平台：覆盖 **需求申报 → 脱敏需求池 → 远期预报 → 询价/密封报价 → 揭示比价 → 多轮议价 → 定标生成订单 → 合同签署 → 物流运单 → 履约跟踪 → 质检预警 → 结算付款 → 归档导出** 的完整业务闭环，提供钢厂、供应商、承运商、平台运营四类角色的权限隔离与统一状态机管控。

## 最新更新（2026-11-08）

完成 E2E 全链路测试暴露的 7 个已知问题（BUG-01~07）的定位与修复，并全部通过回归验证（BUG 回归 17/17 PASS、E2E 全链路 97/97 PASS）：

| BUG | 问题 | 修复 |
|---|---|---|
| BUG-01 | 管理后台状态字典页空白 | 前端按嵌套 dict 形状展开渲染（`frontend/js/pages/admin.js`） |
| BUG-02 | 新建需求明细：下拉已显示品种但保存仍报"不完整" | 默认选中项回写数据模型（`demand.js`） |
| BUG-03 | 编辑需求弹窗不回显已有明细 | 从 existing.items 回填并原样回存 |
| BUG-04 | 需求撤回后无"重新提交"入口 | 补充重提按钮（后端状态机本支持 WITHDRAWN→SUBMITTED） |
| BUG-05 | 企业用户个人资料页误判"无企业档案" | 兼容 /companies/me 平铺返回形状（`misc.js`） |
| BUG-06 | 页面时间与本地差 8 小时、询价截止被误拦 | 会话时区统一 Asia/Shanghai（代码+容器环境变量+存量数据迁移，见 FAQ Q7） |
| BUG-07 | 询价弹窗保存失败仅 3 秒 toast，"静默失败" | 弹窗内持久错误提示区 + 客户端预校验（`trade.js`） |

详见 [系统使用说明](系统使用说明.md) 与 [测试证据归档](test-evidence-20261108/)。

## 技术架构

| 层 | 技术 |
|---|---|
| 后端 | Python 3.12+（开发环境 3.14）+ Flask 3 + psycopg 3 |
| 数据库 | PostgreSQL 14（Docker 容器） |
| 前端 | 原生 JS SPA（hash 路由，无构建，Flask 静态托管） |
| 认证 | JWT Bearer + bcrypt 密码散列 |
| 后台任务 | 进程内定时扫描（五类预警：报价截止/订单超时/运单超时/质检超差/结算超时） |

## 快速启动

前提：已安装 **Docker** 与 **Python 3.12+**。

```bash
# 1. 启动 PostgreSQL 14 数据库容器（首次自动创建 mine_platform 库）
docker compose up -d

# 2. 安装 Python 依赖
pip install -r requirements.txt

# 3. 启动服务（首次运行自动建表 + 写入演示数据）
python run.py        # → http://127.0.0.1:8000
```

打开 http://127.0.0.1:8000 即可使用演示账号登录。

## 默认数据库配置

| 配置项 | 值 |
|---|---|
| 数据库类型 | PostgreSQL 14 |
| 主机 / 端口 | 127.0.0.1 / 5432 |
| 数据库名 | mine_platform |
| 用户名 | postgres |
| 密码 | Langchain2026 |
| 连接串 | `postgresql://postgres:Langchain2026@127.0.0.1:5432/mine_platform` |

> 一期演示项目将连接串作为代码默认值（见 `backend/db.py`），生产环境请通过环境变量 `MINE_PG_DSN` 注入真实连接信息。

### 环境变量

| 变量 | 默认值 | 说明 |
|---|---|---|
| `MINE_PG_DSN` | `postgresql://postgres:Langchain2026@127.0.0.1:5432/mine_platform` | 数据库连接串 |
| `MINE_JWT_SECRET` | 内置演示密钥 | JWT 签名密钥 |
| `MINE_PORT` | `8000` | 服务端口 |
| `MINE_DISABLE_JOBS` | 未设置 | 设为 `1` 时禁用后台定时任务（五类预警扫描 / 到期询价自动揭示 / 超时订单自动失效，测试用） |
| `MINE_JOBS_INTERVAL` | `3600` | 后台定时任务扫描间隔（秒） |
| `MINE_PG_TZ` | `Asia/Shanghai` | 数据库会话业务时区（每次连接以 `options='-c timezone=…'` 生效），保证 `now()` 生成的时间与页面展示、用户输入同一语义 |

## 演示账号

| 角色 | 账号 | 密码 |
|---|---|---|
| 平台运营 | 13800000000 | admin123456 |
| 供应商（中矿） | 13900000001 | demo123456 |
| 钢厂（普阳） | 13900000002 | demo123456 |
| 承运商 | 13900000003 | demo123456 |

## 测试

```bash
# 服务运行中执行 E2E 全链路回归（检查项随基线环境自适应，全 PASS 为通过）
python tests/e2e_full_chain.py

# BUG-01~07 修复回归测试（API 级，覆盖 7 个已知问题的修复验证）
python tests/test_bugfix_regression.py
```

## 目录结构

```
mine_platform_demo/
├── run.py                    # 启动入口（自动建表 + 演示数据）
├── docker-compose.yml        # PostgreSQL 14 容器编排（含业务时区 TZ/PGTZ）
├── requirements.txt
├── backend/                  # Flask 3 后端（16 个 API 模块 + 公共件）
├── frontend/                 # 原生 JS SPA（index.html / css / js）
├── tests/                    # E2E 全链路测试 + BUG 回归测试
├── docs/                     # 数据库 DDL、项目说明与一次性迁移脚本（migrations/）
├── 系统使用说明.md            # 面向使用者的完整操作手册
└── test-evidence-20261108/   # 本轮 E2E 测试与 BUG 修复证据归档
```

## 文档

- [数据库表结构](docs/schema_postgresql.sql)（PostgreSQL 方言全量 DDL）
- [项目说明文档](docs/PROJECT_GUIDE.md)（架构设计 / 模块与接口 / 表结构与初始化 / 部署指南）
- [系统使用说明](系统使用说明.md)（功能模块 / 环境配置 / 操作流程 / 常见问题排查，含 BUG-01~07 修复记录）
- [交付报告](交付报告.md)（交付范围 / 关键设计 / 验收结果 / 后续修复记录）

## 常见问题（FAQ）

**Q1：启动时报数据库连接失败？**
先确认数据库容器在运行：`docker compose up -d`（或 `docker start mine-platform-pg`），再核对 `MINE_PG_DSN` 与容器端口 5432；可用 `docker logs mine-platform-pg` 排查容器状态。

**Q2：8000 端口被占用？**
通过环境变量 `MINE_PORT` 换端口启动，如 `MINE_PORT=8010 python run.py`。

**Q3：如何重置演示数据？**
清空数据库后重跑 `python run.py` 即可（建表与演示数据均幂等）；彻底重置可 `docker compose down -v` 后重新 `up -d` 并启动服务。

**Q4：注册企业后什么时候能开展业务？**
注册成功即可登录，但询价、报价、物流等业务操作需平台在「企业准入」中审核通过（APPROVED）后才可用。

**Q5：后台定时任务多久执行一次？**
默认 3600 秒（`MINE_JOBS_INTERVAL`），覆盖五类预警扫描、到期询价自动揭示、超时订单自动失效；测试时可设 `MINE_DISABLE_JOBS=1` 关闭。

**Q6：上传的附件存放在哪里？**
本地 `uploads/` 目录（按 file_id 命名），多实例部署需改为对象存储。

**Q7：页面显示的时间与本地时间差 8 小时？**
平台业务时区统一为 Asia/Shanghai：后端对每个数据库连接设置会话时区（`backend/db.py` 的 `BUSINESS_TZ`，可用 `MINE_PG_TZ` 覆盖），容器侧已配置 `TZ/PGTZ`。若为 2026-11-08 之前初始化的存量数据库，需执行一次性迁移：`Get-Content docs\migrations\20261108_bug06_timezone_fix.sql -Raw | docker exec -i mine-platform-pg psql -U postgres -d mine_platform`；全新环境无需处理。

**Q8：生产部署有哪些注意？**
Flask 内置 WSGI 服务器仅适用于演示/开发，生产请更换（如 waitress/gunicorn）；通过环境变量注入 `MINE_PG_DSN` 与 `MINE_JWT_SECRET`，勿使用代码默认值；建议配置独立数据库账号与定期备份。
