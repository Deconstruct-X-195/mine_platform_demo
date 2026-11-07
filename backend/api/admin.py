"""运营后台（PRD 4.10）：企业审核、品种与基准价维护、单据总览、数据字典、操作日志。"""
from decimal import Decimal

from flask import g, request

from ..common import (ApiError, get_params, json_payload, ok, op_log,
                      page_args, page_data, require_fields)
from ..db import execute, qall, q1
from ..security import plat_required
from ..state_machine import transition
from . import bp


def grade_value(raw):
    """默认牌号落库前校验：品位百分数，业务域 0～100；空值存 NULL，非法输入报业务错误而非 500。"""
    if raw is None or str(raw).strip() == '':
        return None
    try:
        d = Decimal(str(raw))
    except Exception:
        raise ApiError(40001, '默认牌号必须为数字（如 61.5，品位百分数）')
    if not (Decimal('0') <= d <= Decimal('100')):
        raise ApiError(40001, '默认牌号需在 0～100 之间（品位百分数）')
    return d


# ---------- 企业审核台 ----------

@bp.get('/admin/companies')
@plat_required
def pending_companies():
    params = get_params()
    page, size = page_args(params)
    where = 'WHERE is_deleted=0'
    args = []
    audit = params.get('auditStatus')
    if audit:
        where += ' AND audit_status=%s'
        args.append(audit)
    total = q1(g.conn, 'SELECT count(*) AS c FROM ent_company ' + where, args)['c']
    rows = qall(g.conn, """
        SELECT id, company_name AS "companyName", credit_code AS "creditCode",
               company_types AS "companyTypes", contact_name AS "contactName",
               contact_phone AS "contactPhone", audit_status AS "auditStatus",
               audit_remark AS "auditRemark", status, created_at AS "createdAt"
        FROM ent_company %s ORDER BY id DESC LIMIT %%s OFFSET %%s
        """ % where, args + [size, (page - 1) * size])
    return ok(page_data(rows, total, page, size))


@bp.put('/admin/companies/<int:cid>/audit')
@plat_required
def audit_company(cid):
    p = get_params()
    require_fields(p, 'approve')
    row = q1(g.conn, "SELECT * FROM ent_company WHERE id=%s AND is_deleted=0", (cid,))
    if not row:
        raise ApiError(40401, '企业不存在')
    approve = str(p['approve']).lower() in ('true', '1')
    remark = p.get('remark')
    if not approve and not (remark and str(remark).strip()):
        raise ApiError(40001, '驳回必须填写原因')
    to = 'APPROVED' if approve else 'REJECTED'
    transition(g.conn, g.ctx, 'ent_company', '企业', 'ent_company', cid, to)
    execute(g.conn, "UPDATE ent_company SET audit_remark=%s, updated_by=%s WHERE id=%s",
            (remark or '审核通过', g.ctx.user['id'], cid))
    from ..common import send_msg
    send_msg(g.conn, cid, '准入审核%s' % ('通过' if approve else '驳回'),
             remark or '恭喜，您的企业已通过平台准入审核，可开始使用业务功能。', 'COMPANY', cid)
    return ok({'auditStatus': to})


@bp.put('/admin/companies/<int:cid>/status')
@plat_required
def toggle_company(cid):
    """账号启停（FR-01-07 P1）：ENABLED/DISABLED。"""
    p = get_params()
    require_fields(p, 'status')
    if p['status'] not in ('ENABLED', 'DISABLED'):
        raise ApiError(40001, 'status 仅支持 ENABLED/DISABLED')
    row = q1(g.conn, "SELECT id FROM ent_company WHERE id=%s AND is_deleted=0", (cid,))
    if not row:
        raise ApiError(40401, '企业不存在')
    execute(g.conn, "UPDATE ent_company SET status=%s, updated_by=%s WHERE id=%s",
            (p['status'], g.ctx.user['id'], cid))
    op_log(g.conn, g.ctx, 'ent_company', cid, 'SET STATUS', None, {'status': p['status']})
    return ok({'status': p['status']})


# ---------- 品种与基准价维护 ----------

@bp.post('/admin/varieties')
@plat_required
def create_variety():
    p = get_params()
    require_fields(p, 'varietyCode', 'varietyName')
    grade = grade_value(p.get('defaultGrade'))
    if q1(g.conn, "SELECT id FROM base_variety WHERE variety_code=%s", (p['varietyCode'],)):
        raise ApiError(40902, '品种代码已存在')
    vid = execute(g.conn, """
        INSERT INTO base_variety (variety_code, variety_name, default_grade, unit, sort_no, created_by, updated_by)
        VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id
        """, (p['varietyCode'], p['varietyName'], grade, p.get('unit') or '吨',
              p.get('sortNo') or 0, g.ctx.user['id'], g.ctx.user['id']), returning_id=True)
    op_log(g.conn, g.ctx, 'base_variety', vid, 'CREATE', None, p)
    return ok({'id': vid})


@bp.put('/admin/varieties/<int:vid>')
@plat_required
def update_variety(vid):
    p = get_params()
    row = q1(g.conn, "SELECT * FROM base_variety WHERE id=%s AND is_deleted=0", (vid,))
    if not row:
        raise ApiError(40401, '品种不存在')
    fields = {'varietyName': 'variety_name', 'defaultGrade': 'default_grade',
              'unit': 'unit', 'sortNo': 'sort_no', 'status': 'status'}
    updates = {fields[k]: p[k] for k in fields if p.get(k) is not None}
    if 'default_grade' in updates:
        updates['default_grade'] = grade_value(updates['default_grade'])
    if not updates:
        raise ApiError(40001, '无有效变更字段')
    sets = ', '.join('%s=%%s' % c for c in updates)
    execute(g.conn, 'UPDATE base_variety SET %s, updated_by=%%s, updated_at=now() WHERE id=%%s' % sets,
            list(updates.values()) + [g.ctx.user['id'], vid])
    op_log(g.conn, g.ctx, 'base_variety', vid, 'UPDATE', json_payload(row), updates)
    return ok({'id': vid})


@bp.post('/admin/base-prices')
@plat_required
def save_base_price():
    """基准价录入：同品种同日仅一条有效（重复录入视为修改，留痕）。"""
    p = get_params()
    require_fields(p, 'varietyId', 'priceDate', 'price')
    v = q1(g.conn, "SELECT * FROM base_variety WHERE id=%s AND is_deleted=0", (p['varietyId'],))
    if not v:
        raise ApiError(40401, '品种不存在')
    old = q1(g.conn, "SELECT * FROM base_price WHERE variety_id=%s AND price_date=%s AND is_deleted=0",
             (p['varietyId'], p['priceDate']))
    if old:
        execute(g.conn, """
            UPDATE base_price SET price=%s, price_basis=%s, source_desc=%s, remark=%s,
                   updated_by=%s, updated_at=now() WHERE id=%s
            """, (p['price'], p.get('priceBasis') or 'WET', p.get('sourceDesc'), p.get('remark'),
                  g.ctx.user['id'], old['id']))
        op_log(g.conn, g.ctx, 'base_price', old['id'], 'UPDATE',
               json_payload(old), {'price': p['price'], 'priceBasis': p.get('priceBasis')})
        return ok({'id': old['id'], 'updated': True})
    pid = execute(g.conn, """
        INSERT INTO base_price (variety_id, price_date, price, price_basis, source_desc, remark, created_by, updated_by)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id
        """, (p['varietyId'], p['priceDate'], p['price'], p.get('priceBasis') or 'WET',
              p.get('sourceDesc'), p.get('remark'), g.ctx.user['id'], g.ctx.user['id']), returning_id=True)
    op_log(g.conn, g.ctx, 'base_price', pid, 'CREATE', None, p)
    return ok({'id': pid, 'updated': False})


# ---------- 单据总览 / 字典 / 日志 ----------

@bp.get('/admin/dashboard')
@plat_required
def dashboard():
    def count(sql, args=None):
        return q1(g.conn, sql, args)['c']

    return ok({
        'companyTotal': count("SELECT count(*) AS c FROM ent_company WHERE is_deleted=0"),
        'companyPending': count("SELECT count(*) AS c FROM ent_company WHERE is_deleted=0 AND audit_status='PENDING'"),
        'orderActive': count("SELECT count(*) AS c FROM biz_order WHERE is_deleted=0 AND status NOT IN ('CANCELLED','COMPLETED')"),
        'orderTotal': count("SELECT count(*) AS c FROM biz_order WHERE is_deleted=0"),
        'alertPending': count("SELECT count(*) AS c FROM biz_alert WHERE is_deleted=0 AND status<>'CLOSED'"),
        'inquiryQuoting': count("SELECT count(*) AS c FROM biz_inquiry WHERE is_deleted=0 AND status IN ('SENT','QUOTING')"),
    })


@bp.get('/admin/doc-overview')
@plat_required
def doc_overview():
    """单据总览（FR-10-03）：各单据状态分布。"""
    tables = [('biz_demand', '需求单'), ('biz_inquiry', '询价单'), ('biz_quote', '报价单'),
              ('biz_order', '订单'), ('biz_contract', '合同'), ('biz_waybill', '运单'),
              ('biz_settlement', '结算单'), ('biz_alert', '预警')]
    out = {}
    for t, label in tables:
        rows = qall(g.conn, "SELECT status, count(*) AS c FROM %s WHERE is_deleted=0 GROUP BY status" % t)
        out[t] = {'label': label, 'byStatus': {r['status']: r['c'] for r in rows},
                  'total': sum(r['c'] for r in rows)}
    return ok(out)


@bp.get('/admin/dicts')
@plat_required
def dicts():
    """数据字典（FR-10-05）：枚举常量集中输出。"""
    from ..state_machine import TRANSITIONS
    return ok({'transitions': TRANSITIONS})


@bp.get('/logs')
@plat_required
def logs():
    params = get_params()
    page, size = page_args(params)
    where, args = 'WHERE 1=1', []
    if params.get('bizType'):
        where += ' AND biz_type=%s'
        args.append(params['bizType'])
    if params.get('bizId'):
        where += ' AND biz_id=%s'
        args.append(params['bizId'])
    total = q1(g.conn, 'SELECT count(*) AS c FROM sys_operation_log ' + where, args)['c']
    rows = qall(g.conn, """
        SELECT id, user_id AS "userId", company_id AS "companyId", biz_type AS "bizType",
               biz_id AS "bizId", action, before_value AS "before", after_value AS "after",
               ip, created_at AS "createdAt"
        FROM sys_operation_log %s ORDER BY id DESC LIMIT %%s OFFSET %%s
        """ % where, args + [size, (page - 1) * size])
    return ok(page_data(rows, total, page, size))
