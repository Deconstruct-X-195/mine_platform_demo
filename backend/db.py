"""数据库访问层：基于 psycopg 3 的轻量封装（PostgreSQL 14）。"""
import os
from contextlib import contextmanager

import psycopg
from psycopg.rows import dict_row

# TODO(PRD待确认): 一期演示环境将 DSN 写为默认值，生产环境必须通过环境变量注入。
DEFAULT_DSN = 'postgresql://postgres:Langchain2026@127.0.0.1:5432/mine_platform'

# 业务时区（BUG-06 修复）：平台业务时间（报价截止/校验基准/页面展示）统一按
# Asia/Shanghai 语义。PG 容器默认时区为 Etc/UTC，若不设定会话时区，
# now()/current_date 等服务端时间函数生成的时间戳将落后本地时间 8 小时，
# 导致页面显示与"+2h/前7天"校验基准混乱。可用环境变量 MINE_PG_TZ 覆盖。
BUSINESS_TZ = os.environ.get('MINE_PG_TZ', 'Asia/Shanghai')

_SCHEMA_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'docs', 'schema_postgresql.sql')


def dsn() -> str:
    return os.environ.get('MINE_PG_DSN', DEFAULT_DSN)


@contextmanager
def with_db():
    """请求级连接：进入开启事务，正常退出提交，异常回滚。

    会话时区固定为业务时区（BUG-06 修复）：保证 now()/current_date 与
    应用侧 datetime.now()、用户本地输入使用同一时间语义。
    """
    conn = psycopg.connect(dsn(), row_factory=dict_row, options='-c timezone=' + BUSINESS_TZ)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


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
            ALTER TABLE biz_demand ADD COLUMN IF NOT EXISTS submitted_at TIMESTAMP;
            ALTER TABLE biz_inquiry ADD COLUMN IF NOT EXISTS source VARCHAR(16) NOT NULL DEFAULT 'STEEL';
            ALTER TABLE biz_inquiry ADD COLUMN IF NOT EXISTS batch_no VARCHAR(32);
            ALTER TABLE biz_contract ADD COLUMN IF NOT EXISTS plat_status VARCHAR(20);
            ALTER TABLE biz_contract ADD COLUMN IF NOT EXISTS plat_remark VARCHAR(500);
            ALTER TABLE biz_contract ADD COLUMN IF NOT EXISTS plat_confirm_by BIGINT;
            ALTER TABLE biz_contract ADD COLUMN IF NOT EXISTS plat_confirm_at TIMESTAMP;
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
            ALTER TABLE sys_message ALTER COLUMN receiver_company_id DROP NOT NULL;
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
        """)
    return created
