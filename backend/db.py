"""数据库访问层：基于 psycopg 3 的轻量封装（PostgreSQL 14）。"""
import os
import threading
from contextlib import contextmanager

import psycopg
from psycopg.rows import dict_row

# C2（部署适配方案 §5）：生产/本地凭据一律经环境变量 MINE_PG_DSN 注入，
# 不再提供代码默认值（原演示默认串含明文密码，已随 C2 移除；生产库须使用全新强密码）。

# 业务时区（BUG-06 修复）：平台业务时间（报价截止/校验基准/页面展示）统一按
# Asia/Shanghai 语义。PG 容器默认时区为 Etc/UTC，若不设定会话时区，
# now()/current_date 等服务端时间函数生成的时间戳将落后本地时间 8 小时，
# 导致页面显示与"+2h/前7天"校验基准混乱。可用环境变量 MINE_PG_TZ 覆盖。
BUSINESS_TZ = os.environ.get('MINE_PG_TZ', 'Asia/Shanghai')

_SCHEMA_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'docs', 'schema_postgresql.sql')


def dsn() -> str:
    value = os.environ.get('MINE_PG_DSN', '')
    if not value:
        raise RuntimeError(
            '环境变量 MINE_PG_DSN 未设置：请注入 PostgreSQL 连接串'
            '（示例 postgresql://postgres:PASSWORD@127.0.0.1:5432/mine_platform，'
            '本地开发参见 .env.example）')
    return value


# C5（部署适配方案 §5）：进程级连接池（懒初始化）。仅替换物理连接的获取/归还方式，
# 事务边界（commit/rollback 时机）与 q1/qall/execute 及全部 SQL 零改动。
_pool = None
_pool_lock = threading.Lock()


def pool():
    """进程级 psycopg 连接池：min 2 / max 10，连接携带会话时区（BUG-06 语义不变）。"""
    global _pool
    if _pool is None:
        with _pool_lock:
            if _pool is None:
                from psycopg_pool import ConnectionPool
                _pool = ConnectionPool(
                    conninfo=dsn(), min_size=2, max_size=10, timeout=30, open=True,
                    name='mine-pool',
                    kwargs={'row_factory': dict_row,
                            'options': '-c timezone=' + BUSINESS_TZ})
    return _pool


@contextmanager
def with_db():
    """请求级连接：进入开启事务，正常退出提交，异常回滚（连接自池获取/归还）。

    会话时区固定为业务时区（BUG-06 修复）：保证 now()/current_date 与
    应用侧 datetime.now()、用户本地输入使用同一时间语义。
    """
    conn = pool().getconn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        pool().putconn(conn)


def q1(conn, sql, args=None):
    with conn.cursor() as cur:
        cur.execute(sql, args)
        return cur.fetchone()


def qall(conn, sql, args=None):
    with conn.cursor() as cur:
        cur.execute(sql, args)
        return cur.fetchall()


def execute(conn, sql, args=None, returning_id=False):
    with conn.cursor() as cur:
        cur.execute(sql, args)
        if returning_id:
            row = cur.fetchone()
            return row['id'] if row else None
        return cur.rowcount


def schema_ready(conn) -> bool:
    row = q1(conn, "SELECT to_regclass('public.ent_company') AS t")
    return row is not None and row['t'] is not None


def init_schema(conn):
    """执行建表脚本（幂等：仅当核心表不存在时执行）。"""
    created = False
    if not schema_ready(conn):
        sql = open(_SCHEMA_FILE, encoding='utf-8').read()
        with conn.cursor() as cur:
            cur.execute(sql)
        created = True
    # 增量表补建（老库启动时自动补齐，IF NOT EXISTS 幂等）
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS base_port_price (
              id BIGSERIAL PRIMARY KEY,
              variety_id BIGINT NOT NULL, port_name VARCHAR(50) NOT NULL, price_date DATE NOT NULL,
              price NUMERIC(18,2) NOT NULL,
              created_at TIMESTAMP NOT NULL DEFAULT now(), created_by BIGINT,
              is_deleted SMALLINT DEFAULT 0,
              CONSTRAINT uk_port_variety_date UNIQUE (variety_id, port_name, price_date)
            );
            CREATE INDEX IF NOT EXISTS idx_port_price_query ON base_port_price (variety_id, port_name, price_date);
        """)
        cur.execute("""
            ALTER TABLE base_variety ADD COLUMN IF NOT EXISTS category VARCHAR(50);
            ALTER TABLE base_price ADD COLUMN IF NOT EXISTS port VARCHAR(32);
            ALTER TABLE base_price ADD COLUMN IF NOT EXISTS grade VARCHAR(16);
            ALTER TABLE biz_demand ADD COLUMN IF NOT EXISTS submitted_at TIMESTAMP;
            ALTER TABLE biz_demand ADD COLUMN IF NOT EXISTS settle_days INT;
            -- 需求明细采购周期：MONTH(月度)/QUARTER(季度) + 年 + 月/季度值
            ALTER TABLE biz_demand_item ADD COLUMN IF NOT EXISTS cycle_type VARCHAR(10);
            ALTER TABLE biz_demand_item ADD COLUMN IF NOT EXISTS cycle_year INT;
            ALTER TABLE biz_demand_item ADD COLUMN IF NOT EXISTS cycle_value INT;
            -- 港口自提交货地点可为空（港口由供应商报价确定）
            ALTER TABLE biz_demand ALTER COLUMN delivery_place DROP NOT NULL;
            -- 「其它」品种需求（仅需求归集，不形成实际订单）：期望到货时间可空
            ALTER TABLE biz_demand ALTER COLUMN expect_arrive_start DROP NOT NULL;
            ALTER TABLE biz_demand ALTER COLUMN expect_arrive_end DROP NOT NULL;
            ALTER TABLE biz_inquiry ADD COLUMN IF NOT EXISTS source VARCHAR(16) NOT NULL DEFAULT 'STEEL';
            ALTER TABLE biz_inquiry ADD COLUMN IF NOT EXISTS batch_no VARCHAR(32);
            -- 按钢厂询价单归集：归集成员明细回链来源询价单
            ALTER TABLE biz_aggregated_order_item ADD COLUMN IF NOT EXISTS inquiry_id BIGINT;
            ALTER TABLE biz_demand ADD COLUMN IF NOT EXISTS settle_days INT;
            ALTER TABLE biz_contract ADD COLUMN IF NOT EXISTS plat_status VARCHAR(20);
            ALTER TABLE biz_contract ADD COLUMN IF NOT EXISTS plat_remark VARCHAR(500);
            ALTER TABLE biz_contract ADD COLUMN IF NOT EXISTS plat_confirm_by BIGINT;
            ALTER TABLE biz_contract ADD COLUMN IF NOT EXISTS plat_confirm_at TIMESTAMP;
            ALTER TABLE biz_contract ADD COLUMN IF NOT EXISTS buyer_file_url VARCHAR(500);
            ALTER TABLE biz_contract ADD COLUMN IF NOT EXISTS buyer_file_hash VARCHAR(64);
            ALTER TABLE biz_contract ADD COLUMN IF NOT EXISTS supplier_file_url VARCHAR(500);
            ALTER TABLE biz_contract ADD COLUMN IF NOT EXISTS supplier_file_hash VARCHAR(64);
            -- 存量合同：旧版单文件字段按已上传方回填到双方独立扫描件字段
            UPDATE biz_contract SET buyer_file_url=file_url, buyer_file_hash=file_hash
                WHERE file_url IS NOT NULL AND buyer_file_url IS NULL AND buyer_sign_at IS NOT NULL;
            UPDATE biz_contract SET supplier_file_url=file_url, supplier_file_hash=file_hash
                WHERE file_url IS NOT NULL AND supplier_file_url IS NULL AND supplier_sign_at IS NOT NULL;
            -- 港口价品位维度（PB粉 61.5/60.8 双品位，不同品位价格不同）
            ALTER TABLE base_port_price ADD COLUMN IF NOT EXISTS grade NUMERIC(5,2) NOT NULL DEFAULT 61.5;
            -- 同键（品种×港口×日期×品位）允许多条：重复录入不覆盖原记录、仅新增（唯一约束改普通索引）
            ALTER TABLE base_port_price DROP CONSTRAINT IF EXISTS uk_port_variety_date;
            CREATE INDEX IF NOT EXISTS idx_port_price_key ON base_port_price (variety_id, port_name, price_date, grade);
            -- 归集分组：ORDER=一次性订单归集（「订单归集」页）；DEMAND=月度/季度计划归集（「需求归集」页）
            ALTER TABLE biz_aggregated_order ADD COLUMN IF NOT EXISTS agg_kind VARCHAR(10) NOT NULL DEFAULT 'ORDER';
            ALTER TABLE biz_aggregated_order ADD COLUMN IF NOT EXISTS cycle_type VARCHAR(10);
            ALTER TABLE biz_aggregated_order ADD COLUMN IF NOT EXISTS cycle_year INT;
            ALTER TABLE biz_aggregated_order ADD COLUMN IF NOT EXISTS cycle_value INT;
            -- 需求归集推送供应商（采购参考）：推送时间与操作人（NULL=未推送）
            ALTER TABLE biz_aggregated_order ADD COLUMN IF NOT EXISTS pushed_at TIMESTAMP;
            ALTER TABLE biz_aggregated_order ADD COLUMN IF NOT EXISTS pushed_by BIGINT;
            CREATE TABLE IF NOT EXISTS biz_demand_change (
              id BIGSERIAL PRIMARY KEY,
              change_no VARCHAR(32) NOT NULL, demand_id BIGINT NOT NULL, company_id BIGINT NOT NULL,
              before_data TEXT, after_data TEXT, reason VARCHAR(500),
              status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
              audit_remark VARCHAR(500),
              audit_by BIGINT, audit_at TIMESTAMP,
              created_at TIMESTAMP NOT NULL DEFAULT now(), updated_at TIMESTAMP NOT NULL DEFAULT now(),
              created_by BIGINT, updated_by BIGINT, is_deleted SMALLINT DEFAULT 0,
              CONSTRAINT uk_change_no UNIQUE (change_no)
            );
            CREATE INDEX IF NOT EXISTS idx_change_demand ON biz_demand_change (demand_id);
            CREATE INDEX IF NOT EXISTS idx_change_status ON biz_demand_change (status);
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS biz_aggregated_order (
              id BIGSERIAL PRIMARY KEY,
              agg_no VARCHAR(32) NOT NULL,
              variety_id BIGINT NOT NULL,
              grade NUMERIC(5,2),
              total_qty NUMERIC(18,3) NOT NULL,
              status VARCHAR(20) NOT NULL DEFAULT 'OPEN',
              remark VARCHAR(200),
              created_at TIMESTAMP NOT NULL DEFAULT now(), updated_at TIMESTAMP NOT NULL DEFAULT now(),
              created_by BIGINT, updated_by BIGINT, is_deleted SMALLINT DEFAULT 0,
              CONSTRAINT uk_agg_no UNIQUE (agg_no)
            );
            CREATE TABLE IF NOT EXISTS biz_aggregated_order_item (
              id BIGSERIAL PRIMARY KEY,
              agg_id BIGINT NOT NULL,
              demand_id BIGINT NOT NULL,
              demand_item_id BIGINT NOT NULL,
              company_id BIGINT NOT NULL,
              quantity NUMERIC(18,3) NOT NULL,
              created_at TIMESTAMP NOT NULL DEFAULT now(),
              is_deleted SMALLINT DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS idx_agg_item_agg ON biz_aggregated_order_item (agg_id);
            CREATE INDEX IF NOT EXISTS idx_agg_item_demand ON biz_aggregated_order_item (demand_id);
            ALTER TABLE biz_inquiry ADD COLUMN IF NOT EXISTS agg_id BIGINT;
            ALTER TABLE biz_inquiry ALTER COLUMN buyer_id DROP NOT NULL;
            ALTER TABLE biz_quote ADD COLUMN IF NOT EXISTS tax_type VARCHAR(10);
            ALTER TABLE biz_quote ADD COLUMN IF NOT EXISTS freight_price NUMERIC(18,2);
            ALTER TABLE biz_quote ADD COLUMN IF NOT EXISTS delivery_type VARCHAR(20);
            -- 报价产品申报：矿种/产地/品位（供应商申报实际所报货物，均必填）
            ALTER TABLE biz_quote ADD COLUMN IF NOT EXISTS variety_id BIGINT;
            ALTER TABLE biz_quote ADD COLUMN IF NOT EXISTS origin VARCHAR(100);
            ALTER TABLE biz_quote ADD COLUMN IF NOT EXISTS grade NUMERIC(5,2);
            -- 供应商申报的上下浮方向与金额（「港口现货价格」仅固定字样，不关联当日港口价格数据）
            ALTER TABLE biz_quote ADD COLUMN IF NOT EXISTS price_sign VARCHAR(2);
            ALTER TABLE biz_quote ADD COLUMN IF NOT EXISTS price_float NUMERIC(18,2);
            ALTER TABLE sys_message ALTER COLUMN receiver_company_id DROP NOT NULL;
            ALTER TABLE sys_message ADD COLUMN IF NOT EXISTS msg_category VARCHAR(20) NOT NULL DEFAULT 'NOTICE';
            -- 消息提醒板块：need_action=需要接收端后续操作（任务）；sender_company_id=发布企业（空=运营端发布）
            ALTER TABLE sys_message ADD COLUMN IF NOT EXISTS need_action BOOLEAN NOT NULL DEFAULT FALSE;
            ALTER TABLE sys_message ADD COLUMN IF NOT EXISTS sender_company_id INTEGER;
            -- 小铃铛消息列表清除标记：=1 不再出现在铃铛列表；「全部消息」页不受影响
            ALTER TABLE sys_message ADD COLUMN IF NOT EXISTS bell_cleared SMALLINT NOT NULL DEFAULT 0;
            CREATE TABLE IF NOT EXISTS biz_agg_inquiry_feedback (
              id BIGSERIAL PRIMARY KEY,
              inquiry_id BIGINT NOT NULL,
              agg_id BIGINT NOT NULL,
              company_id BIGINT NOT NULL,
              decision VARCHAR(10) NOT NULL,
              reason VARCHAR(200),
              created_at TIMESTAMP NOT NULL DEFAULT now(),
              created_by BIGINT,
              is_deleted SMALLINT DEFAULT 0,
              CONSTRAINT uk_agg_feedback UNIQUE (inquiry_id, company_id)
            );
            -- 集采聚合订单：整单锁货锁价，buyer_id 为空，参与钢厂以成员明细记录
            ALTER TABLE biz_order ALTER COLUMN buyer_id DROP NOT NULL;
            CREATE TABLE IF NOT EXISTS biz_order_member (              id BIGSERIAL PRIMARY KEY,
              order_id BIGINT NOT NULL,
              company_id BIGINT NOT NULL,
              demand_id BIGINT,
              demand_item_id BIGINT,
              quantity NUMERIC(18,3) NOT NULL,
              pickup_start_date DATE,
              daily_qty NUMERIC(18,3),
              pickup_remark VARCHAR(200),
              pickup_status VARCHAR(20) DEFAULT 'PENDING',
              submitted_at TIMESTAMP,
              created_at TIMESTAMP NOT NULL DEFAULT now(),
              is_deleted SMALLINT DEFAULT 0,
              CONSTRAINT uk_order_member UNIQUE (order_id, company_id)
            );
            CREATE INDEX IF NOT EXISTS idx_order_member_order ON biz_order_member (order_id);
            -- 成员钢厂货物信息：运营端按钢厂录入（货物总量/出港/在途/到站/可提货）→ 钢厂端物流服务自动更新；
            -- 物流轨迹各钢厂一致（挂整单运单），货物信息各厂独立（一单一厂一行）
            CREATE TABLE IF NOT EXISTS biz_member_cargo (
              id BIGSERIAL PRIMARY KEY,
              order_id BIGINT NOT NULL,
              company_id BIGINT NOT NULL,
              total_qty NUMERIC(18,3),
              shipped_qty NUMERIC(18,3),
              transit_qty NUMERIC(18,3),
              arrived_qty NUMERIC(18,3),
              pickup_qty NUMERIC(18,3),
              updated_at TIMESTAMP NOT NULL DEFAULT now(),
              updated_by BIGINT,
              is_deleted SMALLINT DEFAULT 0,
              CONSTRAINT uk_member_cargo UNIQUE (order_id, company_id)
            );
            CREATE INDEX IF NOT EXISTS idx_member_cargo_order ON biz_member_cargo (order_id);
            -- 分段运单：预计船到港时间（ETA）、中转站（公铁联运）
            ALTER TABLE biz_waybill ADD COLUMN IF NOT EXISTS eta_at TIMESTAMP;
            ALTER TABLE biz_waybill ADD COLUMN IF NOT EXISTS transit_station VARCHAR(100);
            -- 订单完成新路径（付款结算线下完成，平台不登记）：钢厂提完货后供需双方确认验收，
            -- 双方确认齐备且无未关闭预警 → 订单自动完成并归档
            ALTER TABLE biz_order ADD COLUMN IF NOT EXISTS supplier_confirm_at TIMESTAMP;
            ALTER TABLE biz_order ADD COLUMN IF NOT EXISTS demand_confirm_at TIMESTAMP;
            -- 订单完成确认（新流程）：供应商/传统单需方确认时间；归集单成员确认在 biz_order_member.finish_confirm_at
            ALTER TABLE biz_order ADD COLUMN IF NOT EXISTS supplier_finish_confirm_at TIMESTAMP;
            ALTER TABLE biz_order ADD COLUMN IF NOT EXISTS buyer_finish_confirm_at TIMESTAMP;
            ALTER TABLE biz_order_member ADD COLUMN IF NOT EXISTS finish_confirm_at TIMESTAMP;
            ALTER TABLE biz_order_member ADD COLUMN IF NOT EXISTS confirm_at TIMESTAMP;
            ALTER TABLE biz_order_member ADD COLUMN IF NOT EXISTS buyer_confirm_at TIMESTAMP; -- 钢厂确认中标订单时间
            -- 物流节点跟踪：实际船到港时间、实际到达中转站时间
            ALTER TABLE biz_waybill ADD COLUMN IF NOT EXISTS actual_eta_at TIMESTAMP;
            ALTER TABLE biz_waybill ADD COLUMN IF NOT EXISTS actual_transit_at TIMESTAMP;
            -- 运营端节点草稿（保存后统一提交）：JSON 文本 {ETA/DEPART/TRANSIT/ARRIVE: 'YYYY-MM-DD HH:MM:SS'}
            ALTER TABLE biz_waybill ADD COLUMN IF NOT EXISTS node_draft TEXT;
            -- 节点录入追加物流轨迹日志（只增不改，每录一次新增一条）：JSON 数组 [{loc, desc, occurTime}]
            ALTER TABLE biz_waybill ADD COLUMN IF NOT EXISTS node_log TEXT;
            -- 运输方案按运输方式分框：铁路直达/公铁联运/汽运直达
            ALTER TABLE biz_logistics_plan ADD COLUMN IF NOT EXISTS rail_remark VARCHAR(500);
            ALTER TABLE biz_logistics_plan ADD COLUMN IF NOT EXISTS multimodal_remark VARCHAR(500);
            ALTER TABLE biz_logistics_plan ADD COLUMN IF NOT EXISTS truck_remark VARCHAR(500);
            -- 供应商货物信息（运营端录入，供应商端随录随更新）
            ALTER TABLE biz_logistics_plan ADD COLUMN IF NOT EXISTS supp_total_qty NUMERIC(18,3);
            ALTER TABLE biz_logistics_plan ADD COLUMN IF NOT EXISTS supp_shipped_qty NUMERIC(18,3);
            ALTER TABLE biz_logistics_plan ADD COLUMN IF NOT EXISTS supp_transit_qty NUMERIC(18,3);
            ALTER TABLE biz_logistics_plan ADD COLUMN IF NOT EXISTS supp_arrived_qty NUMERIC(18,3);
            ALTER TABLE biz_logistics_plan ADD COLUMN IF NOT EXISTS supp_pickup_qty NUMERIC(18,3);
            ALTER TABLE biz_logistics_plan ADD COLUMN IF NOT EXISTS supp_cargo_at TIMESTAMP;
            -- 物流信息发布快照（推送门控）：运营端显式推送后钢厂/供应商端才可见，未推送前节点录入/货物信息不外露
            -- target：MILL（推送至钢厂：轨迹 + 各厂货物信息）/ SUPPLIER（推送供应商：轨迹 + 货物汇总 + 运输方案）
            CREATE TABLE IF NOT EXISTS biz_logistics_publish (
              order_id BIGINT NOT NULL,
              target VARCHAR(10) NOT NULL,
              trace_json TEXT,
              cargo_json TEXT,
              plan_json TEXT,
              published_at TIMESTAMP,
              updated_at TIMESTAMP NOT NULL DEFAULT now(),
              PRIMARY KEY (order_id, target)
            );
            -- 运单详情：运行时间节点（铁路/公铁联运按列车）+ 装车信息（汽运直达为全程持续运输，列车类字段留空）
            ALTER TABLE biz_waybill ADD COLUMN IF NOT EXISTS request_at TIMESTAMP;         -- 请车时间
            ALTER TABLE biz_waybill ADD COLUMN IF NOT EXISTS approve_at TIMESTAMP;        -- 批复时间
            ALTER TABLE biz_waybill ADD COLUMN IF NOT EXISTS load_at TIMESTAMP;           -- 装车时间
            ALTER TABLE biz_waybill ADD COLUMN IF NOT EXISTS load_done_at TIMESTAMP;      -- 装完时间
            ALTER TABLE biz_waybill ADD COLUMN IF NOT EXISTS unload_start_at TIMESTAMP;   -- 开始卸车时间
            ALTER TABLE biz_waybill ADD COLUMN IF NOT EXISTS unload_done_at TIMESTAMP;    -- 卸完时间
            ALTER TABLE biz_waybill ADD COLUMN IF NOT EXISTS return_window VARCHAR(100);  -- 返倒时间（可为时间区间文本）
            ALTER TABLE biz_waybill ADD COLUMN IF NOT EXISTS storage_at TIMESTAMP;        -- 入库时间
            ALTER TABLE biz_waybill ADD COLUMN IF NOT EXISTS load_place VARCHAR(50);      -- 装车地点
            ALTER TABLE biz_waybill ADD COLUMN IF NOT EXISTS car_count_desc VARCHAR(100); -- 车节数（含实装/移车/空板车说明）
            ALTER TABLE biz_waybill ADD COLUMN IF NOT EXISTS open_car_count INT;          -- 敞车集装箱节数
            ALTER TABLE biz_waybill ADD COLUMN IF NOT EXISTS flat_car_count INT;          -- 板车集装箱节数
            ALTER TABLE biz_waybill ADD COLUMN IF NOT EXISTS first_car_no VARCHAR(50);    -- 首节车号
            ALTER TABLE biz_waybill ADD COLUMN IF NOT EXISTS last_car_no VARCHAR(50);     -- 尾节车号
            ALTER TABLE biz_waybill ADD COLUMN IF NOT EXISTS ticket_no VARCHAR(100);      -- 票号
            ALTER TABLE biz_waybill ADD COLUMN IF NOT EXISTS voyage_no VARCHAR(50);       -- 航次号
            ALTER TABLE biz_waybill ADD COLUMN IF NOT EXISTS track_weight NUMERIC(12,2);  -- 轨道衡净重吨数
            -- 报价附件（供应商报价时上传的资质/承诺等文件，经通用 /files 落盘后关联）
            CREATE TABLE IF NOT EXISTS biz_quote_file (
              id BIGSERIAL PRIMARY KEY,
              quote_id BIGINT NOT NULL,
              file_id VARCHAR(64) NOT NULL,
              file_name VARCHAR(200),
              created_at TIMESTAMP NOT NULL DEFAULT now(),
              created_by BIGINT,
              is_deleted SMALLINT DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS idx_quote_file_quote ON biz_quote_file (quote_id);
            -- 企业信息变更待审核：已准入企业改信息 → 暂存 JSON → 运营端审核通过后自动更新
            ALTER TABLE ent_company ADD COLUMN IF NOT EXISTS pending_changes TEXT;
        """)
        cur.execute("""
            -- 基准价唯一约束升级（PR #8）：品种+日期 → 品种+日期+港口+品位 四列。
            -- 新库已含新约束则跳过；存量库从旧约束 uk_variety_date 平滑升级。
            DO $$
            BEGIN
              IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='uk_variety_date_port_grade') THEN
                ALTER TABLE base_price DROP CONSTRAINT IF EXISTS uk_variety_date;
                ALTER TABLE base_price ADD CONSTRAINT uk_variety_date_port_grade
                  UNIQUE (variety_id, price_date, port, grade);
              END IF;
            END $$;
        """)
    return created
