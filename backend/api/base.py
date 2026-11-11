"""品种与基准价查询（PRD T05）：品种列表、当日报价与近 30 日走势、港口现货价。"""
from datetime import date, timedelta

from flask import g, request

from ..common import ApiError, get_params, json_payload, ok, op_log, parse_date, require_fields
from ..db import execute, qall, q1
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


# ---------------- 港口现货价（运营看板"行业数据趋势"数据源） ----------------

@bp.get('/base-prices/deal-trend')
@auth_required
def deal_trend():
    """平台成交价走势：?varietyId= 必选，按日聚合订单均价（biz_order）。"""
    vid = request.args.get('varietyId')
    if not vid:
        raise ApiError(40001, 'varietyId 必填')
    rows = qall(g.conn, """
        SELECT DATE(o.created_at) AS "priceDate", AVG(o.unit_price) AS price, COUNT(*) AS deals
        FROM biz_order o
        WHERE o.is_deleted=0 AND o.variety_id=%s
        GROUP BY DATE(o.created_at) ORDER BY 1
    """, (vid,))
    return ok({'list': json_payload(rows)})


@bp.get('/base-prices/ports')
@auth_required
def port_prices():
    """港口现货价列表：?varietyId=&port= 可选，按港口+日期倒序。"""
    vid = request.args.get('varietyId')
    port = request.args.get('port')
    sql = """
        SELECT p.id, p.variety_id AS "varietyId", v.variety_name AS "varietyName",
               p.port_name AS "portName", p.price_date AS "priceDate", p.price
        FROM base_port_price p JOIN base_variety v ON v.id=p.variety_id
        WHERE p.is_deleted=0
    """
    args = []
    if vid:
        sql += ' AND p.variety_id=%s'
        args.append(vid)
    if port:
        sql += ' AND p.port_name=%s'
        args.append(port)
    rows = qall(g.conn, sql + ' ORDER BY p.port_name, p.price_date DESC, p.id DESC', args)
    return ok({'list': json_payload(rows)})


@bp.post('/base-prices/ports')
@auth_required
def save_port_price():
    """设置港口现货价（平台运营专用；同品种×港口×日期 upsert）。"""
    if not g.ctx.is_plat:
        raise ApiError(40301, '仅平台运营可维护港口价格')
    p = get_params()
    require_fields(p, 'varietyId', 'portName', 'priceDate', 'price')
    v = q1(g.conn, "SELECT id FROM base_variety WHERE id=%s AND is_deleted=0", (p['varietyId'],))
    if not v:
        raise ApiError(40401, '品种不存在')
    try:
        price = float(p['price'])
    except (TypeError, ValueError):
        raise ApiError(40001, '价格必须是数字')
    if price <= 0:
        raise ApiError(40001, '价格必须大于0')
    d = parse_date(p, 'priceDate')
    port_name = str(p['portName']).strip()
    if not port_name or len(port_name) > 50:
        raise ApiError(40001, '港口名称必填且不超过50字')
    row = q1(g.conn, """
        INSERT INTO base_port_price (variety_id, port_name, price_date, price, created_by)
        VALUES (%s,%s,%s,%s,%s)
        ON CONFLICT (variety_id, port_name, price_date)
        DO UPDATE SET price=EXCLUDED.price, is_deleted=0
        RETURNING id
    """, (p['varietyId'], port_name, d, price, g.ctx.user['id']), )
    op_log(g.conn, g.ctx, 'base_port_price', row['id'], 'UPSERT', None,
           {'portName': port_name, 'priceDate': str(d), 'price': price})
    return ok({'id': row['id']})


@bp.delete('/base-prices/ports/<int:pid>')
@auth_required
def remove_port_price(pid):
    """删除港口现货价（平台运营专用，软删除）。"""
    if not g.ctx.is_plat:
        raise ApiError(40301, '仅平台运营可维护港口价格')
    n = execute(g.conn, "UPDATE base_port_price SET is_deleted=1 WHERE id=%s AND is_deleted=0", (pid,))
    if not n:
        raise ApiError(40401, '记录不存在')
    op_log(g.conn, g.ctx, 'base_port_price', pid, 'DELETE', None, None)
    return ok({'deleted': n})
