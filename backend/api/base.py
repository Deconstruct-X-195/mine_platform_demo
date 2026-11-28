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
    """当日基准价与近 30 日走势（PRD FR-03-03）。

    钢厂端"今日基准价"与运营端"今日港口价"同源：均取 base_port_price
    （品种×港口最新一条），运营端改价后钢厂端刷新即联动。?varietyId= 可选。
    """
    vid = request.args.get('varietyId')
    today = date.today()
    today_sql = """
        SELECT DISTINCT ON (p.variety_id, p.port_name, COALESCE(p.grade, 61.5))
               p.variety_id AS "varietyId", v.variety_name AS "varietyName",
               p.price, p.price_date AS "priceDate", p.port_name AS "port",
               COALESCE(p.grade, 61.5) AS "grade",
               'WET' AS "priceBasis", 'Mysteel' AS "sourceDesc"
        FROM base_port_price p JOIN base_variety v ON v.id=p.variety_id
        WHERE p.is_deleted=0
    """
    port_args = []
    if vid:
        today_sql += ' AND p.variety_id=%s'
        port_args.append(vid)
    rows = qall(g.conn, today_sql + ' ORDER BY p.variety_id, p.port_name, COALESCE(p.grade, 61.5), p.price_date DESC, p.id DESC',
                port_args)
    trend_sql = """
        SELECT p.variety_id AS "varietyId", v.variety_name AS "varietyName",
               p.price_date AS "priceDate", p.price, p.port_name AS "port",
               COALESCE(p.grade, 61.5) AS "grade"
        FROM base_port_price p JOIN base_variety v ON v.id=p.variety_id
        WHERE p.is_deleted=0 AND p.price_date >= %s
    """
    trend_args = [today - timedelta(days=30)]
    if vid:
        trend_sql += ' AND p.variety_id=%s'
        trend_args.append(vid)
    # 不做 DISTINCT ON 去重：与运营端图表同口径——同日同品位多条记录（录入不覆盖只新增）全部返回，
    # 前端趋势图对同日多点并排展现；today 表仍取每键最新一条
    trend = qall(g.conn, trend_sql + ' ORDER BY p.variety_id, p.port_name, COALESCE(p.grade, 61.5), p.price_date, p.id DESC', trend_args)
    if not rows:
        # 港口价尚未维护时兜底：沿用兰格锚点基准价（base_price），日期如实显示
        anchor_today = """
            SELECT p.variety_id AS "varietyId", v.variety_name AS "varietyName",
                   p.price, p.price_basis AS "priceBasis", p.price_date AS "priceDate",
                   p.port, p.grade, p.source_desc AS "sourceDesc"
            FROM base_price p JOIN base_variety v ON v.id=p.variety_id
            WHERE p.is_deleted=0
        """
        anchor_args = []
        latest = q1(g.conn, 'SELECT MAX(price_date) AS d FROM base_price WHERE is_deleted=0')
        if latest and latest['d']:
            anchor_today += ' AND p.price_date=%s'
            anchor_args.append(latest['d'])
        if vid:
            anchor_today += ' AND p.variety_id=%s'
            anchor_args.append(vid)
        rows = qall(g.conn, anchor_today + ' ORDER BY v.sort_no, v.id', anchor_args)
        anchor_trend = """
            SELECT p.variety_id AS "varietyId", v.variety_name AS "varietyName",
                   p.price_date AS "priceDate", p.price, p.port, p.grade
            FROM base_price p JOIN base_variety v ON v.id=p.variety_id
            WHERE p.is_deleted=0 AND p.price_date >= %s
        """
        anchor_targs = [today - timedelta(days=30)]
        if vid:
            anchor_trend += ' AND p.variety_id=%s'
            anchor_targs.append(vid)
        trend = qall(g.conn, anchor_trend + ' ORDER BY variety_id, price_date', anchor_targs)
    return ok({'today': json_payload(rows), 'trend': json_payload(trend)})


# ---------------- 港口现货价（运营看板"行业数据趋势"数据源） ----------------

@bp.get('/base-prices/deal-trend')
@auth_required
def deal_trend():
    """平台成交价走势：?varietyId= 必选，按日×品位聚合订单均价（biz_order），行含 grade。"""
    vid = request.args.get('varietyId')
    if not vid:
        raise ApiError(40001, 'varietyId 必填')
    rows = qall(g.conn, """
        SELECT DATE(o.created_at) AS "priceDate", COALESCE(o.grade, '61.50') AS grade,
               AVG(o.unit_price) AS price, COUNT(*) AS deals
        FROM biz_order o
        WHERE o.is_deleted=0 AND o.variety_id=%s
        GROUP BY DATE(o.created_at), COALESCE(o.grade, '61.50') ORDER BY 1
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
               p.port_name AS "portName", p.price_date AS "priceDate", p.price,
               p.deal_price AS "dealPrice",
               COALESCE(p.grade, 61.5) AS "grade",
               'WET' AS "priceBasis"
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
    """设置港口现货价（平台运营专用；同键已有记录时不覆盖，仅提醒并新增一条）。"""
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
    try:
        grade = float(str(p.get('grade') or '').replace('%', '').strip() or 61.5)
    except (TypeError, ValueError):
        raise ApiError(40001, '品位必须是数字')
    if not 0 < grade <= 100:
        raise ApiError(40001, '品位需在 0-100 之间')
    d = parse_date(p, 'priceDate')
    port_name = str(p['portName']).strip()
    if not port_name or len(port_name) > 50:
        raise ApiError(40001, '港口名称必填且不超过50字')
    deal_price = p.get('dealPrice')
    if deal_price in (None, ''):
        deal_price = None
    else:
        try:
            deal_price = float(deal_price)
        except (TypeError, ValueError):
            raise ApiError(40001, '交易价格必须是数字')
        if deal_price <= 0:
            raise ApiError(40001, '交易价格必须大于0')
    # 同键（品种×港口×日期×品位）已有记录：不覆盖原记录，直接新增一条（前端按 duplicated 提醒）。
    # P3-9 说明：检查与插入非原子——并发同键录入极端下 duplicated 标记可能漏报，
    # 但业务上同键多条记录本就允许并存（2026-11-24 设计变更），标记仅为提示，风险受控。
    dup = q1(g.conn, """
        SELECT price FROM base_port_price
        WHERE variety_id=%s AND port_name=%s AND price_date=%s AND grade=%s AND is_deleted=0
        ORDER BY id DESC LIMIT 1
    """, (p['varietyId'], port_name, d, grade))
    row = q1(g.conn, """
        INSERT INTO base_port_price (variety_id, port_name, price_date, price, grade, deal_price, created_by)
        VALUES (%s,%s,%s,%s,%s,%s,%s)
        RETURNING id
    """, (p['varietyId'], port_name, d, price, grade, deal_price, g.ctx.user['id']), )
    op_log(g.conn, g.ctx, 'base_port_price', row['id'], 'CREATE', None,
           {'portName': port_name, 'priceDate': str(d), 'price': price, 'grade': grade,
            'dealPrice': deal_price})
    return ok({'id': row['id'], 'duplicated': dup is not None,
               'existingPrice': str(dup['price']) if dup is not None else None})


@bp.put('/base-prices/ports/<int:pid>')
@auth_required
def update_port_price(pid):
    """修改港口现货价（平台运营专用；按记录 id 原地更新，不新增）。"""
    if not g.ctx.is_plat:
        raise ApiError(40301, '仅平台运营可维护港口价格')
    old = q1(g.conn, "SELECT id FROM base_port_price WHERE id=%s AND is_deleted=0", (pid,))
    if not old:
        raise ApiError(40401, '记录不存在')
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
    try:
        grade = float(str(p.get('grade') or '').replace('%', '').strip() or 61.5)
    except (TypeError, ValueError):
        raise ApiError(40001, '品位必须是数字')
    if not 0 < grade <= 100:
        raise ApiError(40001, '品位需在 0-100 之间')
    d = parse_date(p, 'priceDate')
    port_name = str(p['portName']).strip()
    if not port_name or len(port_name) > 50:
        raise ApiError(40001, '港口名称必填且不超过50字')
    deal_price = p.get('dealPrice')
    if deal_price in (None, ''):
        deal_price = None  # 置空表示清除该条记录的交易价格
    else:
        try:
            deal_price = float(deal_price)
        except (TypeError, ValueError):
            raise ApiError(40001, '交易价格必须是数字')
        if deal_price <= 0:
            raise ApiError(40001, '交易价格必须大于0')
    execute(g.conn, """
        UPDATE base_port_price
        SET variety_id=%s, port_name=%s, price_date=%s, price=%s, grade=%s, deal_price=%s
        WHERE id=%s AND is_deleted=0
    """, (p['varietyId'], port_name, d, price, grade, deal_price, pid))
    op_log(g.conn, g.ctx, 'base_port_price', pid, 'UPDATE', None,
           {'portName': port_name, 'priceDate': str(d), 'price': price, 'grade': grade,
            'dealPrice': deal_price})
    return ok({'id': pid})


@bp.post('/base-prices/ports/batch-delete')
@auth_required
def batch_remove_port_prices():
    """批量删除港口现货价（平台运营专用，软删除）。JSON 体：{ids: [记录id, ...]}。"""
    if not g.ctx.is_plat:
        raise ApiError(40301, '仅平台运营可维护港口价格')
    p = get_params()
    ids = p.get('ids')
    if not isinstance(ids, list) or not ids:
        raise ApiError(40001, 'ids 必填且为非空数组')
    try:
        ids = [int(x) for x in ids]
    except (TypeError, ValueError):
        raise ApiError(40001, 'ids 必须为整数数组')
    n = 0
    deleted = []
    for pid in ids:
        if execute(g.conn, "UPDATE base_port_price SET is_deleted=1 WHERE id=%s AND is_deleted=0", (pid,)):
            n += 1
            deleted.append(pid)
    # P3-9 修复：逐条留痕（原 biz_id=0 无法定位具体记录）；被删除的 id 才写审计
    for pid in deleted:
        op_log(g.conn, g.ctx, 'base_port_price', pid, 'BATCH_DELETE', None, {'batch': ids})
    return ok({'deleted': n})


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
