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
    if schema_ready(conn):
        return False
    sql = open(_SCHEMA_FILE, encoding='utf-8').read()
    with conn.cursor() as cur:
        cur.execute(sql)
    return True
