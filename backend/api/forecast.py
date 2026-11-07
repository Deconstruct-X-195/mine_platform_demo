"""远期预报报价（PRD 4.3/T07）：供应商预判价，非平台成交价，不构成要约。

规则：预报在周期开始前可改，开始后锁定；展示必须标注"供应商预判价，非平台成交价"。
"""
from datetime import date

from flask import g, request

from ..common import (ApiError, doc_no, get_params, json_payload, ok, op_log,
                      page_args, page_data, parse_date, require_fields)
from ..db import execute, qall, q1
from ..security import ROLE_SUPPLIER, auth_required, roles_required
from . import bp

FORECAST_NOTICE = '供应商预判价，非平台成交价'


def _validate(p):
    require_fields(p, 'varietyId', 'periodType', 'periodStart', 'periodEnd',
                   'availableQty', 'forecastPrice')
    if p['periodType'] not in ('TEN_DAY', 'MONTHLY'):
        raise ApiError(40001, '周期类型仅支持 TEN_DAY/MONTHLY')
    start = parse_date(p, 'periodStart')
    end = parse_date(p, 'periodEnd')
    if end < start:
        raise ApiError(40001, '周期结束不能早于开始')
    if p.get('priceBasis') and p['priceBasis'] not in ('DRY', 'WET'):
        raise ApiError(40001, '计价口径仅支持 DRY/WET')


@bp.post('/forecast-quotes')
@roles_required(ROLE_SUPPLIER)
def create_forecast():
    p = get_params()
    _validate(p)
    v = q1(g.conn, "SELECT id FROM base_variety WHERE id=%s AND is_deleted=0", (p['varietyId'],))
    if not v:
        raise ApiError(40401, '品种不存在')
    fid = execute(g.conn, """
        INSERT INTO biz_forecast_quote (forecast_no, supplier_id, variety_id, period_type,
            period_start, period_end, available_qty, forecast_price, price_basis,
            delivery_port, valid_until, remark, created_by, updated_by)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id
        """, (doc_no(g.conn, 'YB'), g.ctx.company['id'], p['varietyId'], p['periodType'],
              parse_date(p, 'periodStart'), parse_date(p, 'periodEnd'),
              p['availableQty'], p['forecastPrice'], p.get('priceBasis') or 'WET',
              p.get('deliveryPort'), parse_date(p, 'validUntil', required=False),
              p.get('remark'), g.ctx.user['id'], g.ctx.user['id']), returning_id=True)
    op_log(g.conn, g.ctx, 'biz_forecast_quote', fid, 'CREATE', None, p)
    return ok({'id': fid, 'forecastNo': None, 'notice': FORECAST_NOTICE})


@bp.put('/forecast-quotes/<int:fid>')
@roles_required(ROLE_SUPPLIER)
def update_forecast(fid):
    row = q1(g.conn, "SELECT * FROM biz_forecast_quote WHERE id=%s AND is_deleted=0", (fid,))
    if not row:
        raise ApiError(40401, '预报不存在')
    if row['supplier_id'] != g.ctx.company['id']:
        raise ApiError(40301, '无权限修改该预报')
    if date.today() >= row['period_start']:
        raise ApiError(40901, '预报周期已开始，锁定不可修改')
    p = get_params()
    _validate(p)
    execute(g.conn, """
        UPDATE biz_forecast_quote SET variety_id=%s, period_type=%s, period_start=%s,
            period_end=%s, available_qty=%s, forecast_price=%s, price_basis=%s,
            delivery_port=%s, valid_until=%s, remark=%s, updated_by=%s, updated_at=now()
        WHERE id=%s
        """, (p['varietyId'], p['periodType'], parse_date(p, 'periodStart'), parse_date(p, 'periodEnd'),
              p['availableQty'], p['forecastPrice'], p.get('priceBasis') or 'WET',
              p.get('deliveryPort'), parse_date(p, 'validUntil', required=False), p.get('remark'),
              g.ctx.user['id'], fid))
    op_log(g.conn, g.ctx, 'biz_forecast_quote', fid, 'UPDATE', json_payload(row), p)
    return ok({'id': fid, 'notice': FORECAST_NOTICE})


@bp.get('/forecast-quotes')
@auth_required
def list_forecasts():
    """预报池（全部已生效预报，标注预判价）。供应商可见自己全部。"""
    params = request.args.to_dict()
    page, size = page_args(params)
    where = "WHERE f.is_deleted=0"
    args = []
    if params.get('varietyId'):
        where += ' AND f.variety_id=%s'
        args.append(params['varietyId'])
    if params.get('mine') == '1':
        where += ' AND f.supplier_id=%s'
        args.append(g.ctx.company['id'] if g.ctx.company else -1)
    else:
        where += " AND f.status='EFFECTIVE'"
    total = q1(g.conn, 'SELECT count(*) AS c FROM biz_forecast_quote f ' + where, args)['c']
    rows = qall(g.conn, """
        SELECT f.id, f.forecast_no AS "forecastNo", f.supplier_id AS "supplierId",
               c.company_name AS "supplierName", f.variety_id AS "varietyId",
               v.variety_name AS "varietyName", f.period_type AS "periodType",
               f.period_start AS "periodStart", f.period_end AS "periodEnd",
               f.available_qty AS "availableQty", f.forecast_price AS "forecastPrice",
               f.price_basis AS "priceBasis", f.delivery_port AS "deliveryPort",
               f.valid_until AS "validUntil", f.status, f.remark, f.created_at AS "createdAt"
        FROM biz_forecast_quote f
        JOIN base_variety v ON v.id=f.variety_id
        LEFT JOIN ent_company c ON c.id=f.supplier_id
        %s ORDER BY f.id DESC LIMIT %%s OFFSET %%s
        """ % where, args + [size, (page - 1) * size])
    data = page_data(rows, total, page, size)
    data['notice'] = FORECAST_NOTICE
    return ok(data)


@bp.post('/forecast-quotes/<int:fid>/expire')
@roles_required(ROLE_SUPPLIER)
def expire_forecast(fid):
    """失效管理：预报置 EXPIRED（失效管理 FR-03-06 最小实现）。"""
    row = q1(g.conn, "SELECT * FROM biz_forecast_quote WHERE id=%s AND is_deleted=0", (fid,))
    if not row:
        raise ApiError(40401, '预报不存在')
    if row['supplier_id'] != g.ctx.company['id']:
        raise ApiError(40301, '无权限操作该预报')
    execute(g.conn, "UPDATE biz_forecast_quote SET status='EXPIRED', updated_by=%s, updated_at=now() WHERE id=%s",
            (g.ctx.user['id'], fid))
    op_log(g.conn, g.ctx, 'biz_forecast_quote', fid, 'STATUS %s->EXPIRED' % row['status'],
           {'status': row['status']}, {'status': 'EXPIRED'})
    return ok({'id': fid, 'status': 'EXPIRED'})
