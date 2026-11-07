# 大宗矿产集采平台（一期）

面向大宗矿产（铁矿石等）集采交易的一体化平台：覆盖 **需求申报 → 脱敏需求池 → 远期预报 → 询价/密封报价 → 揭示比价 → 多轮议价 → 定标生成订单 → 合同签署 → 物流运单 → 履约跟踪 → 质检预警 → 结算付款 → 归档导出** 的完整业务闭环，提供钢厂、供应商、承运商、平台运营四类角色的权限隔离与统一状态机管控。

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
| `MINE_DISABLE_JOBS` | 未设置 | 设为 `1` 时禁用后台定时预警扫描（测试用） |

## 演示账号

| 角色 | 账号 | 密码 |
|---|---|---|
| 平台运营 | 13800000000 | admin123456 |
| 钢厂 | 13800000001 | demo123456 |
| 供应商 ×3 | 13800000002 ~ 13800000004 | demo123456 |
| 承运商 | 13800000005 | demo123456 |

## 测试

```bash
# 服务运行中执行 E2E 全链路回归（94 项检查）
python tests/e2e_full_chain.py
```

## 目录结构

```
mine_platform_demo/
├── run.py                    # 启动入口（自动建表 + 演示数据）
├── docker-compose.yml        # PostgreSQL 14 容器编排
├── requirements.txt
├── backend/                  # Flask 3 后端（16 个 API 模块 + 公共件）
├── frontend/                 # 原生 JS SPA（index.html / css / js）
├── tests/                    # E2E 全链路测试
└── docs/                     # 数据库 DDL 与项目说明文档
```

## 文档

- [数据库表结构](docs/schema_postgresql.sql)（PostgreSQL 方言全量 DDL）
- [项目说明文档](docs/PROJECT_GUIDE.md)（架构设计 / 模块与接口 / 表结构与初始化 / 部署指南）

## 说明

- Flask 内置 WSGI 服务器仅适用于演示/开发，生产部署请更换（如 waitress/gunicorn）。
- 数据可整体重置：清空数据库后重跑 `python run.py`（建表与演示数据均幂等）。
