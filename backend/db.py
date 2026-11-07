"""数据库访问层：基于 psycopg 3 的轻量封装（PostgreSQL 14）。"""
import os
from contextlib import contextmanager

import psycopg
from psycopg.rows import dict_row

# TODO(PRD待确认): 一期演示环境将 DSN 写为默认值，生产环境必须通过环境变量注入。
DEFAULT_DSN = 'postgresql://postgres:Langchain2026@127.0.0.1:5432/mine_platform'

_SCHEMA_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'docs', 'schema_postgresql.sql')


def dsn() -> str:
    return os.environ.get('MINE_PG_DSN', DEFAULT_DSN)


@contextmanager
def with_db():
    """请求级连接：进入开启事务，正常退出提交，异常回滚。"""
    conn = psycopg.connect(dsn(), row_factory=dict_row)
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
