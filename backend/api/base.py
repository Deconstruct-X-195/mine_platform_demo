"""品种与基准价查询（PRD T05）：品种列表、当日报价与近 30 日走势。"""
from datetime import date, timedelta

from flask import g, request

from ..common import json_payload, ok
from ..db import qall, q1
from ..security import auth_required
from . import bp


@bp.get('/base/varieties')
@auth_required
def varieties():
    rows = qall(g.conn, """
        SELECT id, variety_code AS "varietyCode", variety_name AS "varietyName",
               default_grade AS "defaultGrade", unit, status
        FROM base_variety WHERE is_deleted=0 ORDER BY sort_no, id
        """)
    return ok({'list': json_payload(rows)})


@bp.get('/base-prices/current')
@auth_required
def current_prices():
    """当日报价与近 30 日（PRD FR-03-03 P1）：?varietyId= 可选，缺省返回全部品种当日价。"""
    vid = request.args.get('varietyId')
    today = date.today()
    sql = """
        SELECT p.variety_id AS "varietyId", v.variety_name AS "varietyName",
               p.price, p.price_basis AS "priceBasis", p.price_date AS "priceDate",
               p.source_desc AS "sourceDesc"
        FROM base_price p JOIN base_variety v ON v.id=p.variety_id
        WHERE p.is_deleted=0 AND p.price_date=%s
    """
    args = [today]
    if vid:
        sql += ' AND p.variety_id=%s'
        args.append(vid)
    rows = qall(g.conn, sql + ' ORDER BY v.sort_no, v.id', args)
    trend_sql = """
        SELECT variety_id AS "varietyId", price_date AS "priceDate", price
        FROM base_price WHERE is_deleted=0 AND price_date >= %s
    """
    trend_args = [today - timedelta(days=30)]
    if vid:
        trend_sql += ' AND variety_id=%s'
        trend_args.append(vid)
    trend = qall(g.conn, trend_sql + ' ORDER BY variety_id, price_date', trend_args)
    return ok({'today': json_payload(rows), 'trend': json_payload(trend)})
