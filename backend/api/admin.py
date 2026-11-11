"""运营后台（PRD 4.10）：企业审核、品种与基准价维护、单据总览、数据字典、操作日志。"""
import json
from datetime import datetime, timedelta
from decimal import Decimal

from flask import g, request

from ..common import (ApiError, doc_no, get_params, json_payload, ok, op_log,
                      page_args, page_data, parse_date, parse_datetime,
                      require_fields, send_msg)
from ..db import execute, qall, q1
from ..security import plat_required
from ..state_machine import transition
from . import bp
from .inquiry import _check_invites, create_and_send_agg_inquiry, reveal_inquiry
from .logistics import _check_carrier


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


# ---------- 需求归集（需求列表 + 变更申请审核） ----------

@bp.get('/admin/demand-pool')
@plat_required
def demand_pool():
    """归集各钢厂需求单（按明细行展开：一行 = 需求单 × 品种明细）。"""
    params = get_params()
    page, size = page_args(params)
    where = 'WHERE d.is_deleted=0 AND i.is_deleted=0'
    args = []
    status = params.get('status')
    if status:
        where += ' AND d.status=%s'
        args.append(status)
    total = q1(g.conn, """
        SELECT count(*) AS c
        FROM biz_demand_item i
        JOIN biz_demand d ON d.id=i.demand_id
        %s
        """ % where, args)['c']
    rows = qall(g.conn, """
        SELECT i.id, d.id AS "demandId", d.demand_no AS "demandNo", d.demand_name AS "demandName",
               c.company_name AS "companyName", v.category, v.variety_name AS "varietyName",
               i.quantity, i.grade, i.inquired_qty AS "inquiredQty",
               d.delivery_type AS "deliveryType", d.delivery_place AS "deliveryPlace",
               d.expect_arrive_start AS "expectArriveStart", d.expect_arrive_end AS "expectArriveEnd",
               d.status, d.version AS "version",
               COALESCE(d.submitted_at, d.updated_at) AS "submittedAt"
        FROM biz_demand_item i
        JOIN biz_demand d ON d.id=i.demand_id
        JOIN ent_company c ON c.id=d.company_id
        JOIN base_variety v ON v.id=i.variety_id
        %s
        ORDER BY COALESCE(d.submitted_at, d.updated_at) DESC, d.id DESC, i.id
        LIMIT %%s OFFSET %%s
        """ % where, args + [size, (page - 1) * size])
    return ok(page_data(rows, total, page, size))


@bp.get('/admin/demand-changes')
@plat_required
def demand_changes():
    """需求变更申请列表（分页 + 状态筛选）。"""
    params = get_params()
    page, size = page_args(params)
    where = 'WHERE ch.is_deleted=0'
    args = []
    status = params.get('status')
    if status:
        where += ' AND ch.status=%s'
        args.append(status)
    total = q1(g.conn, 'SELECT count(*) AS c FROM biz_demand_change ch ' + where, args)['c']
    rows = qall(g.conn, """
        SELECT ch.id, ch.change_no AS "changeNo", ch.demand_id AS "demandId",
               d.demand_no AS "demandNo", ch.company_id AS "companyId",
               c.company_name AS "companyName", ch.before_data AS "beforeData",
               ch.after_data AS "afterData", ch.reason,
               ch.status, ch.audit_remark AS "auditRemark",
               ch.audit_at AS "auditAt", ch.created_at AS "createdAt"
        FROM biz_demand_change ch
        JOIN ent_company c ON c.id=ch.company_id
        LEFT JOIN biz_demand d ON d.id=ch.demand_id
        %s ORDER BY ch.id DESC LIMIT %%s OFFSET %%s
        """ % where, args + [size, (page - 1) * size])
    for r in rows:
        r['beforeData'] = _change_payload(r.pop('beforeData'))
        r['afterData'] = _change_payload(r.pop('afterData'))
    return ok(page_data(rows, total, page, size))


def _change_payload(raw):
    """变更前后数据落库为 JSON 字符串，返回时还原为对象（容错：非法/空 → {}）。"""
    if not raw:
        return {}
    if isinstance(raw, (dict, list)):
        return json_payload(raw)
    try:
        return json_payload(json.loads(raw))
    except Exception:
        return {}


@bp.put('/admin/demand-changes/<int:cid>/audit')
@plat_required
def audit_demand_change(cid):
    """变更申请审核：通过/驳回（驳回必填原因），结论站内通知申请企业。"""
    p = get_params()
    require_fields(p, 'approve')
    row = q1(g.conn, "SELECT * FROM biz_demand_change WHERE id=%s AND is_deleted=0", (cid,))
    if not row:
        raise ApiError(40401, '变更申请不存在')
    if row['status'] != 'PENDING':
        raise ApiError(40901, '变更申请当前状态为 %s，禁止审核' % row['status'])
    approve = str(p['approve']).lower() in ('true', '1')
    remark = p.get('remark')
    if not approve and not (remark and str(remark).strip()):
        raise ApiError(40001, '驳回必须填写原因')
    to = 'APPROVED' if approve else 'REJECTED'
    transition(g.conn, g.ctx, 'biz_demand_change', '变更申请', 'biz_demand_change', cid, to)
    execute(g.conn, """
        UPDATE biz_demand_change SET audit_remark=%s, audit_by=%s, audit_at=now(),
               updated_by=%s, updated_at=now() WHERE id=%s
        """, (remark, g.ctx.user['id'], g.ctx.user['id'], cid))
    send_msg(g.conn, row['company_id'],
             '需求变更申请%s' % ('通过' if approve else '驳回'),
             remark or '您提交的需求变更申请已审核通过。', 'DEMAND', row['demand_id'])
    return ok({'status': to})


# ---------- 归集订单：多钢厂同品种同品位需求合并 ----------
@bp.get('/admin/aggregated-orders')
@plat_required
def aggregated_orders():
    """归集订单列表（含参与钢厂、关联询价状态）。"""
    params = get_params()
    page, size = page_args(params)
    where = 'WHERE a.is_deleted=0'
    args = []
    if params.get('status'):
        where += ' AND a.status=%s'
        args.append(params['status'])
    total = q1(g.conn, 'SELECT count(*) AS c FROM biz_aggregated_order a ' + where, args)['c']
    rows = qall(g.conn, """
        SELECT a.id, a.agg_no AS "aggNo", a.variety_id AS "varietyId",
               v.variety_name AS "varietyName", v.category,
               a.grade, a.total_qty AS "totalQty", a.status, a.remark,
               a.created_at AS "createdAt",
               (SELECT count(*) FROM biz_aggregated_order_item m
                 WHERE m.agg_id=a.id AND m.is_deleted=0) AS "memberCount",
               (SELECT string_agg(DISTINCT c.company_name, '、')
                 FROM biz_aggregated_order_item m JOIN ent_company c ON c.id=m.company_id
                 WHERE m.agg_id=a.id AND m.is_deleted=0) AS "companyNames",
               (SELECT i.id FROM biz_inquiry i
                 WHERE i.agg_id=a.id AND i.is_deleted=0 ORDER BY i.id DESC LIMIT 1) AS "inquiryId",
               (SELECT i.inquiry_no FROM biz_inquiry i
                 WHERE i.agg_id=a.id AND i.is_deleted=0 ORDER BY i.id DESC LIMIT 1) AS "inquiryNo",
               (SELECT i.status FROM biz_inquiry i
                 WHERE i.agg_id=a.id AND i.is_deleted=0 ORDER BY i.id DESC LIMIT 1) AS "inquiryStatus"
        FROM biz_aggregated_order a
        JOIN base_variety v ON v.id=a.variety_id
        %s ORDER BY a.id DESC LIMIT %%s OFFSET %%s
        """ % where, args + [size, (page - 1) * size])
    return ok(page_data(rows, total, page, size))


@bp.get('/admin/aggregated-orders/<int:aid>')
@plat_required
def aggregated_order_detail(aid):
    """归集订单详情：成员明细（钢厂 × 需求 × 份额）。"""
    a = q1(g.conn, """
        SELECT a.*, v.variety_name AS "varietyName", v.category
        FROM biz_aggregated_order a JOIN base_variety v ON v.id=a.variety_id
        WHERE a.id=%s AND a.is_deleted=0
        """, (aid,))
    if not a:
        raise ApiError(40401, '归集订单不存在')
    members = qall(g.conn, """
        SELECT m.id, m.company_id AS "companyId", c.company_name AS "companyName",
               d.demand_no AS "demandNo", d.demand_name AS "demandName",
               v.variety_name AS "varietyName", di.grade, m.quantity,
               di.quantity AS "itemQty", di.inquired_qty AS "inquiredQty"
        FROM biz_aggregated_order_item m
        JOIN ent_company c ON c.id=m.company_id
        JOIN biz_demand d ON d.id=m.demand_id
        JOIN biz_demand_item di ON di.id=m.demand_item_id
        JOIN base_variety v ON v.id=di.variety_id
        WHERE m.agg_id=%s AND m.is_deleted=0 ORDER BY m.id
        """, (aid,))
    return ok({'order': json_payload(a), 'members': json_payload(members)})


@bp.post('/admin/aggregated-orders')
@plat_required
def create_aggregated_order():
    """合并归集：勾选多份已提交需求中同品种同品位的明细 → 生成归集订单并锁定量。"""
    p = get_params()
    require_fields(p, 'itemIds')
    item_ids = p['itemIds']
    if not isinstance(item_ids, list) or not item_ids:
        raise ApiError(40001, '请至少选择一条需求明细')
    items = qall(g.conn, """
        SELECT i.id, i.demand_id, i.variety_id, i.grade, i.quantity, i.inquired_qty,
               d.company_id, d.status AS demand_status, v.variety_name
        FROM biz_demand_item i
        JOIN biz_demand d ON d.id=i.demand_id
        JOIN base_variety v ON v.id=i.variety_id
        WHERE i.id = ANY(%s) AND i.is_deleted=0 AND d.is_deleted=0
        """, (item_ids,))
    if len(items) != len(set(item_ids)):
        raise ApiError(40401, '部分需求明细不存在')
    base = items[0]
    for it in items:
        if it['variety_id'] != base['variety_id'] or it['grade'] != base['grade']:
            raise ApiError(40001, '仅同品种且同品位的明细可合并归集（%s 品位不一致）' % it['variety_name'])
        if it['demand_status'] != 'SUBMITTED':
            raise ApiError(40901, '需求单状态为 %s，不可归集（仅已提交状态可归集）' % it['demand_status'])
        if it['quantity'] - it['inquired_qty'] <= 0:
            raise ApiError(40901, '明细 %s 已无可归集量' % it['id'])
    total = sum(it['quantity'] - it['inquired_qty'] for it in items)
    aid = execute(g.conn, """
        INSERT INTO biz_aggregated_order (agg_no, variety_id, grade, total_qty, status, remark,
            created_by, updated_by)
        VALUES (%s, %s, %s, %s, 'OPEN', %s, %s, %s) RETURNING id
        """, (doc_no(g.conn, 'GJ'), base['variety_id'], base['grade'], total, p.get('remark'),
              g.ctx.user['id'], g.ctx.user['id']), returning_id=True)
    mills = {}
    for it in items:
        lock = it['quantity'] - it['inquired_qty']
        execute(g.conn, """
            INSERT INTO biz_aggregated_order_item (agg_id, demand_id, demand_item_id, company_id, quantity)
            VALUES (%s, %s, %s, %s, %s)
            """, (aid, it['demand_id'], it['id'], it['company_id'], lock))
        execute(g.conn, """
            UPDATE biz_demand_item SET inquired_qty=%s, updated_at=now() WHERE id=%s
            """, (it['quantity'], it['id']))  # 归集全量锁定
        mills[it['company_id']] = it['variety_name']
    # 需求状态：SUBMITTED → INQUIRING（同一需求多明细合并只流转一次）
    for did in {it['demand_id'] for it in items}:
        transition(g.conn, g.ctx, 'biz_demand', '需求单', 'biz_demand', did, 'INQUIRING')
    agg_no = q1(g.conn, "SELECT agg_no FROM biz_aggregated_order WHERE id=%s", (aid,))['agg_no']
    for cid, vname in mills.items():
        send_msg(g.conn, cid, '需求已纳入归集订单',
                 '贵司 %s 需求已由平台归集（归集订单 %s，合计 %.3f 吨），将统一向供应商询价，报价汇总后推送贵司。'
                 % (vname, agg_no, float(total)), 'DEMAND', items[0]['demand_id'])
    op_log(g.conn, g.ctx, 'biz_aggregated_order', aid, 'CREATE', None,
           {'itemIds': item_ids, 'totalQty': str(total)})
    return ok({'id': aid, 'aggNo': agg_no, 'totalQty': float(total)})


@bp.put('/admin/aggregated-orders/<int:aid>/close')
@plat_required
def close_aggregated_order(aid):
    """关闭归集订单（仅未询价 OPEN 状态）：释放锁定量，需求无其他在途询价时回退已提交。"""
    a = q1(g.conn, "SELECT * FROM biz_aggregated_order WHERE id=%s AND is_deleted=0", (aid,))
    if not a:
        raise ApiError(40401, '归集订单不存在')
    if a['status'] != 'OPEN':
        raise ApiError(40901, '归集订单已发起询价（%s），不可直接关闭' % a['status'])
    members = qall(g.conn, """
        SELECT * FROM biz_aggregated_order_item WHERE agg_id=%s AND is_deleted=0
        """, (aid,))
    for m in members:
        execute(g.conn, """
            UPDATE biz_demand_item SET inquired_qty = inquired_qty - %s, updated_at=now()
            WHERE id=%s
            """, (m['quantity'], m['demand_item_id']))
        active = q1(g.conn, """
            SELECT count(*) AS c FROM biz_inquiry
            WHERE is_deleted=0 AND status IN ('DRAFT','SENT','QUOTING')
              AND (demand_id=%s OR (agg_id IS NOT NULL AND agg_id <> %s AND id IN (
                    SELECT DISTINCT agg_id FROM biz_aggregated_order_item
                    WHERE demand_id=%s AND is_deleted=0)))
            """, (m['demand_id'], aid, m['demand_id']))['c']
        drow = q1(g.conn, "SELECT id, status FROM biz_demand WHERE id=%s", (m['demand_id'],))
        if not active and drow and drow['status'] == 'INQUIRING':
            transition(g.conn, g.ctx, 'biz_demand', '需求单', 'biz_demand', m['demand_id'], 'SUBMITTED')
    transition(g.conn, g.ctx, 'biz_aggregated_order', '归集订单', 'biz_aggregated_order', aid, 'CLOSED')
    for m in members:
        send_msg(g.conn, m['company_id'], '归集订单已关闭',
                 '归集订单 %s 已关闭，贵司需求份额量已释放，可继续等待归集或被单独询价。' % a['agg_no'],
                 'DEMAND', m['demand_id'])
    op_log(g.conn, g.ctx, 'biz_aggregated_order', aid, 'CLOSE', None,
           {'members': len(members)})
    return ok({'id': aid, 'status': 'CLOSED'})


# ---------- 报价询价（平台代发：归集订单 → 统一向供应商询价 → 汇总返回钢厂） ----------

@bp.get('/admin/quote-inquiries')
@plat_required
def platform_quote_list():
    """平台代发询价列表（source='PLATFORM'，分页 + 状态筛选）。"""
    params = get_params()
    page, size = page_args(params)
    where = "WHERE i.is_deleted=0 AND i.source='PLATFORM'"
    args = []
    status = params.get('status')
    if status:
        where += ' AND i.status=%s'
        args.append(status)
    total = q1(g.conn, 'SELECT count(*) AS c FROM biz_inquiry i ' + where, args)['c']
    rows = qall(g.conn, """
        SELECT i.id, i.inquiry_no AS "inquiryNo", i.batch_no AS "batchNo",
               d.demand_no AS "demandNo", c.company_name AS "companyName",
               v.variety_name AS "varietyName", i.grade, i.quantity,
               i.agg_id AS "aggId", a.agg_no AS "aggNo",
               i.delivery_place AS "deliveryPlace", i.deadline, i.expect_arrive_date AS "expectArriveDate",
               i.min_response AS "minResponse", i.status,
               (SELECT count(*) FROM biz_inquiry_invite inv
                 WHERE inv.inquiry_id=i.id AND inv.is_deleted=0) AS invited,
               (SELECT count(*) FROM biz_quote q
                 WHERE q.inquiry_id=i.id AND q.is_deleted=0 AND q.status != 'REJECTED') AS responded,
               (SELECT count(*) FROM biz_agg_inquiry_feedback f
                 WHERE f.inquiry_id=i.id AND f.is_deleted=0 AND f.decision='ACCEPTED') AS "feedbackAccept",
               (SELECT count(*) FROM biz_agg_inquiry_feedback f
                 WHERE f.inquiry_id=i.id AND f.is_deleted=0 AND f.decision='REJECTED') AS "feedbackReject",
               (i.reveal_snapshot IS NOT NULL) AS revealed,
               i.sent_at AS "sentAt", i.created_at AS "createdAt"
        FROM biz_inquiry i
        LEFT JOIN biz_demand d ON d.id=i.demand_id
        LEFT JOIN ent_company c ON c.id=i.buyer_id
        LEFT JOIN base_variety v ON v.id=i.variety_id
        LEFT JOIN biz_aggregated_order a ON a.id=i.agg_id
        %s ORDER BY i.id DESC LIMIT %%s OFFSET %%s
        """ % where, args + [size, (page - 1) * size])
    return ok(page_data(rows, total, page, size))


@bp.post('/admin/quote-inquiries')
@plat_required
def create_platform_inquiries():
    """归集订单整单询价：引用 OPEN 状态归集订单，统一条件邀请供应商（仅归集询价）。"""
    p = get_params()
    require_fields(p, 'aggOrderId', 'arriveDate', 'deadline', 'inviteSupplierIds')
    supplier_ids = p['inviteSupplierIds']
    if not supplier_ids:
        raise ApiError(40001, '至少邀请一家供应商')
    _check_invites(supplier_ids)
    arrive = parse_date(p, 'arriveDate')
    deadline = parse_datetime(p, 'deadline')
    if deadline < datetime.now() + timedelta(hours=2):
        raise ApiError(40001, '报价截止时间必须至少为当前时间 +2 小时')
    if deadline.date() > arrive - timedelta(days=7):
        raise ApiError(40001, '报价截止时间不能晚于到货日期前 7 天')
    min_response = p.get('minResponse') or 2
    if not (1 <= int(min_response) <= 10):
        raise ApiError(40001, '最少响应家数取值 1~10')
    agg = q1(g.conn, "SELECT * FROM biz_aggregated_order WHERE id=%s AND is_deleted=0",
             (p['aggOrderId'],))
    if not agg:
        raise ApiError(40401, '归集订单不存在')
    if agg['status'] not in ('OPEN', 'INQUIRING'):
        raise ApiError(40901, '归集订单状态为 %s，不可发起询价' % agg['status'])
    if agg['status'] == 'INQUIRING':
        active = q1(g.conn, """
            SELECT id FROM biz_inquiry
            WHERE agg_id=%s AND status IN ('SENT','QUOTING') AND is_deleted=0
            """, (agg['id'],))
        if active:
            raise ApiError(40901, '该归集订单存在进行中的询价，请等待报价截止/汇总后再发起')
    batch_no = doc_no(g.conn, 'PC')
    iid = create_and_send_agg_inquiry(g.conn, agg, g.ctx.user['id'], arrive, deadline,
                                      min_response, supplier_ids, batch_no, p.get('remark'))
    if agg['status'] == 'OPEN':
        transition(g.conn, g.ctx, 'biz_aggregated_order', '归集订单', 'biz_aggregated_order',
                   agg['id'], 'INQUIRING')
    # 重新发起询价：该归集单下「反馈待处理」的旧询价单标记已处理（回退已截止）
    for r in qall(g.conn, """
            SELECT id FROM biz_inquiry WHERE agg_id=%s AND status='FEEDBACK' AND is_deleted=0
            """, (agg['id'],)):
        transition(g.conn, g.ctx, 'biz_inquiry', '询价单', 'biz_inquiry', r['id'], 'CLOSED')
    op_log(g.conn, g.ctx, 'biz_inquiry', iid, 'PLATFORM CREATE', None,
           {'batchNo': batch_no, 'aggId': agg['id'], 'aggNo': agg['agg_no'],
            'totalQty': str(agg['total_qty'])})
    return ok({'batchNo': batch_no, 'inquiryId': iid, 'aggNo': agg['agg_no']})


@bp.get('/admin/quote-inquiries/<int:iid>/feedbacks')
@plat_required
def platform_quote_feedbacks(iid):
    """归集询价的钢厂反馈明细（认可/不认可 + 原因）。"""
    rows = qall(g.conn, """
        SELECT f.decision, f.reason, to_char(f.created_at, 'YYYY-MM-DD HH24:MI') AS "createdAt",
               c.company_name AS "companyName"
        FROM biz_agg_inquiry_feedback f
        JOIN ent_company c ON c.id=f.company_id
        WHERE f.inquiry_id=%s AND f.is_deleted=0 ORDER BY f.id
        """, (iid,))
    return ok({'list': rows})


@bp.get('/admin/quote-inquiries/<int:iid>/summary')
@plat_required
def platform_quote_summary(iid):
    """供应商报价汇总（价格升序）：运营作为汇总方可见，不受密封期限制。"""
    row = q1(g.conn, """
        SELECT i.*, d.demand_no AS "demandNo", c.company_name AS "companyName",
               v.variety_name AS "varietyName", a.agg_no AS "aggNo"
        FROM biz_inquiry i
        LEFT JOIN biz_demand d ON d.id=i.demand_id
        LEFT JOIN ent_company c ON c.id=i.buyer_id
        LEFT JOIN base_variety v ON v.id=i.variety_id
        LEFT JOIN biz_aggregated_order a ON a.id=i.agg_id
        WHERE i.id=%s AND i.is_deleted=0 AND i.source='PLATFORM'
        """, (iid,))
    if not row:
        raise ApiError(40401, '询价单不存在')
    quotes = qall(g.conn, """
        SELECT q.id, q.quote_no AS "quoteNo", c.company_name AS "companyName",
               q.price, q.quantity, q.delivery_date AS "deliveryDate",
               q.delivery_place AS "deliveryPlace", q.pay_terms AS "payTerms",
               q.status, q.version
        FROM biz_quote q JOIN ent_company c ON c.id=q.supplier_id
        WHERE q.inquiry_id=%s AND q.is_deleted=0 AND q.status != 'REJECTED'
        ORDER BY q.price ASC
        """, (iid,))
    return ok({'inquiry': json_payload(row), 'quotes': json_payload(quotes)})


@bp.post('/admin/quote-inquiries/<int:iid>/return')
@plat_required
def platform_quote_return(iid):
    """汇总报价返回钢厂：执行揭示（钢厂端现有页面即见比价快照）+ 站内明确通知。已揭示则仅补发通知（幂等）。"""
    row = q1(g.conn, "SELECT * FROM biz_inquiry WHERE id=%s AND is_deleted=0 AND source='PLATFORM'", (iid,))
    if not row:
        raise ApiError(40401, '询价单不存在')
    if row['status'] not in ('SENT', 'QUOTING', 'CLOSED'):
        raise ApiError(40901, '询价单状态为 %s，不可汇总返回' % row['status'])
    n_quotes = q1(g.conn, """
        SELECT count(*) AS c FROM biz_quote
        WHERE inquiry_id=%s AND is_deleted=0 AND status != 'REJECTED'
        """, (iid,))['c']
    if row['status'] != 'CLOSED' and n_quotes == 0:
        raise ApiError(40001, '暂无供应商报价，无法汇总返回')
    revealed_now = False
    if row['status'] in ('SENT', 'QUOTING') and not row['reveal_snapshot']:
        reveal_inquiry(g.conn, iid, g.ctx)
        revealed_now = True
    if row['agg_id']:
        mills = qall(g.conn, """
            SELECT DISTINCT m.company_id AS company_id,
                   (SELECT COALESCE(SUM(m2.quantity), 0) FROM biz_aggregated_order_item m2
                     JOIN biz_demand d2 ON d2.id=m2.demand_id
                     WHERE m2.agg_id=%s AND m2.is_deleted=0 AND d2.is_deleted=0
                       AND d2.company_id=m.company_id) AS share_qty
            FROM biz_aggregated_order_item m
            WHERE m.agg_id=%s AND m.is_deleted=0
            """, (row['agg_id'], row['agg_id']))
        for m in mills:
            send_msg(g.conn, m['company_id'], '平台报价汇总推送',
                     '归集订单询价 %s 已汇总 %s 家供应商报价，并按贵司需求份额（%s 吨）拆分推送，请前往「询价报价」查看比价。'
                     % (row['inquiry_no'], n_quotes, m['share_qty']), 'INQUIRY', iid)
    else:
        send_msg(g.conn, row['buyer_id'], '平台报价汇总推送',
                 '询价单 %s 已汇总 %s 家供应商报价并推送至贵司，请前往「询价报价」查看比价。'
                 % (row['inquiry_no'], n_quotes), 'INQUIRY', iid)
    op_log(g.conn, g.ctx, 'biz_inquiry', iid, 'PLATFORM RETURN', None,
           {'quotes': n_quotes, 'revealed': revealed_now})
    return ok({'revealed': revealed_now, 'quoteCount': n_quotes})


# ---------- 合同管理：扫描件核验与台账 ----------
@bp.get('/admin/contracts')
@plat_required
def platform_contract_list():
    """合同列表（汇集各端上传的扫描件，含平台核验状态与关联运单数）。"""
    params = get_params()
    page, size = page_args(params)
    where = "WHERE c.is_deleted=0"
    args = []
    ps = params.get('platStatus')
    if ps == 'NONE':
        where += " AND c.plat_status IS NULL"
    elif ps:
        where += " AND c.plat_status=%s"
        args.append(ps)
    if params.get('status'):
        where += " AND c.status=%s"
        args.append(params['status'])
    total = q1(g.conn, 'SELECT count(*) AS c FROM biz_contract c ' + where, args)['c']
    rows = qall(g.conn, """
        SELECT c.id, c.contract_no AS "contractNo", c.order_id AS "orderId", o.order_no AS "orderNo",
               b.company_name AS "buyerName", s.company_name AS "supplierName",
               c.version, c.signature_type AS "signatureType",
               c.buyer_sign_at AS "buyerSignAt", c.supplier_sign_at AS "supplierSignAt",
               c.file_url AS "fileUrl", c.file_hash AS "fileHash",
               c.status, c.plat_status AS "platStatus", c.plat_remark AS "platRemark",
               c.plat_confirm_at AS "platConfirmAt", c.created_at AS "createdAt",
               (SELECT count(*) FROM biz_waybill w WHERE w.order_id=c.order_id AND w.is_deleted=0) AS "waybillCount"
        FROM biz_contract c
        JOIN biz_order o ON o.id=c.order_id
        JOIN ent_company b ON b.id=o.buyer_id
        JOIN ent_company s ON s.id=o.supplier_id
        %s ORDER BY c.id DESC LIMIT %%s OFFSET %%s
        """ % where, args + [size, (page - 1) * size])
    return ok(page_data(rows, total, page, size))


@bp.put('/admin/contracts/<int:cid>/verify')
@plat_required
def platform_contract_verify(cid):
    """核验合同：approve → 生效并入台账；否则退回上传方（附原因）。"""
    p = get_params()
    require_fields(p, 'approve')
    row = q1(g.conn, """
        SELECT c.*, o.order_no, o.buyer_id, o.supplier_id
        FROM biz_contract c JOIN biz_order o ON o.id=c.order_id
        WHERE c.id=%s AND c.is_deleted=0
        """, (cid,))
    if not row:
        raise ApiError(40401, '合同不存在')
    if row['plat_status'] != 'PENDING':
        raise ApiError(40901, '合同平台核验状态为 %s，不可核验' % (row['plat_status'] or '无'))
    if row['status'] != 'PENDING_SUPPLIER':
        raise ApiError(40901, '合同状态为 %s，不可核验' % row['status'])
    approve = str(p['approve']).lower() in ('true', '1')
    if approve:
        transition(g.conn, g.ctx, 'biz_contract', '合同', 'biz_contract', cid, 'EFFECTIVE',
                   node_biz_type='ORDER', node_code='CONTRACT_EFFECTIVE', node_biz_id=row['order_id'])
        ostatus = q1(g.conn, "SELECT status FROM biz_order WHERE id=%s", (row['order_id'],))['status']
        if ostatus == 'PENDING_EFFECT':
            transition(g.conn, g.ctx, 'biz_order', '订单', 'biz_order', row['order_id'], 'PERFORMING',
                       node_biz_type='ORDER', node_code='CONTRACT_EFFECTIVE')
        execute(g.conn, """
            UPDATE biz_contract SET plat_status='CONFIRMED', plat_confirm_by=%s, plat_confirm_at=now(),
                updated_by=%s, updated_at=now() WHERE id=%s
            """, (g.ctx.user['id'], g.ctx.user['id'], cid))
        text = '订单 %s 合同 %s 已通过平台核验并生效。' % (row['order_no'], row['contract_no'])
        send_msg(g.conn, row['buyer_id'], '合同已核验生效', text, 'CONTRACT', cid)
        send_msg(g.conn, row['supplier_id'], '合同已核验生效', text, 'CONTRACT', cid)
        op_log(g.conn, g.ctx, 'biz_contract', cid, 'VERIFY', None, {'result': 'CONFIRMED'})
        return ok({'id': cid, 'platStatus': 'CONFIRMED', 'status': 'EFFECTIVE'})
    remark = (p.get('remark') or '').strip()
    if not remark:
        raise ApiError(40001, '退回必须填写原因')
    if row['supplier_sign_at'] and row['buyer_sign_at']:
        to_company = row['supplier_id'] if row['supplier_sign_at'] >= row['buyer_sign_at'] else row['buyer_id']
    else:
        to_company = row['buyer_id']
    execute(g.conn, """
        UPDATE biz_contract SET plat_status='RETURNED', plat_remark=%s, updated_by=%s, updated_at=now()
        WHERE id=%s
        """, (remark, g.ctx.user['id'], cid))
    send_msg(g.conn, to_company, '合同扫描件被退回',
             '合同 %s 扫描件未通过平台核验，原因：%s，请重新上传。' % (row['contract_no'], remark), 'CONTRACT', cid)
    op_log(g.conn, g.ctx, 'biz_contract', cid, 'RETURN', None, {'remark': remark})
    return ok({'id': cid, 'platStatus': 'RETURNED'})


# ---------- 运输调度：数据统计分析 ----------
@bp.get('/admin/logistics-stats')
@plat_required
def platform_logistics_stats():
    """调度统计分析：出港口数 / 在途数 / 到站数 / 分拨数，按汽运(ROAD)、火运(RAIL)及总计分列。

    口径：出港=已实际发运；在途=当前 IN_TRANSIT；到站=已实际到达（含已签收）；分拨=分段序号>1 的转运段。
    """
    t = q1(g.conn, """
        SELECT
          count(*) FILTER (WHERE actual_depart_at IS NOT NULL AND transport_mode='ROAD') AS depart_road,
          count(*) FILTER (WHERE actual_depart_at IS NOT NULL AND transport_mode='RAIL') AS depart_rail,
          count(*) FILTER (WHERE actual_depart_at IS NOT NULL) AS depart_total,
          count(*) FILTER (WHERE status='IN_TRANSIT' AND transport_mode='ROAD') AS transit_road,
          count(*) FILTER (WHERE status='IN_TRANSIT' AND transport_mode='RAIL') AS transit_rail,
          count(*) FILTER (WHERE status='IN_TRANSIT') AS transit_total,
          count(*) FILTER (WHERE actual_arrive_at IS NOT NULL AND transport_mode='ROAD') AS arrive_road,
          count(*) FILTER (WHERE actual_arrive_at IS NOT NULL AND transport_mode='RAIL') AS arrive_rail,
          count(*) FILTER (WHERE actual_arrive_at IS NOT NULL) AS arrive_total,
          count(*) FILTER (WHERE segment_no<>'1' AND transport_mode='ROAD') AS transship_road,
          count(*) FILTER (WHERE segment_no<>'1' AND transport_mode='RAIL') AS transship_rail,
          count(*) FILTER (WHERE segment_no<>'1') AS transship_total
        FROM biz_waybill WHERE is_deleted=0 AND status<>'CANCELLED'
        """)
    return ok({
        'depart': {'road': t['depart_road'], 'rail': t['depart_rail'], 'total': t['depart_total']},
        'inTransit': {'road': t['transit_road'], 'rail': t['transit_rail'], 'total': t['transit_total']},
        'arrived': {'road': t['arrive_road'], 'rail': t['arrive_rail'], 'total': t['arrive_total']},
        'transship': {'road': t['transship_road'], 'rail': t['transship_rail'], 'total': t['transship_total']},
    })


# ---------- 运输调度：物流调度 + 在途监控 ----------
@bp.get('/admin/logistics-orders')
@plat_required
def platform_logistics_orders():
    """可调度订单（履约中），带方案与运单概况。"""
    params = get_params()
    page, size = page_args(params)
    where = "WHERE o.is_deleted=0 AND o.status='PERFORMING'"
    total = q1(g.conn, 'SELECT count(*) AS c FROM biz_order o ' + where)['c']
    rows = qall(g.conn, """
        SELECT o.id, o.order_no AS "orderNo", b.company_name AS "buyerName",
               s.company_name AS "supplierName", o.quantity,
               c.contract_no AS "contractNo",
               p.id AS "planId", p.plan_no AS "planNo", p.org_mode AS "orgMode",
               (SELECT count(*) FROM biz_waybill w WHERE w.plan_id=p.id AND w.is_deleted=0 AND w.status<>'CANCELLED') AS "waybillCount",
               (SELECT coalesce(sum(w.plan_qty),0) FROM biz_waybill w WHERE w.plan_id=p.id AND w.is_deleted=0 AND w.status<>'CANCELLED') AS "plannedQty"
        FROM biz_order o
        JOIN ent_company b ON b.id=o.buyer_id
        JOIN ent_company s ON s.id=o.supplier_id
        LEFT JOIN biz_contract c ON c.order_id=o.id AND c.is_deleted=0 AND c.status='EFFECTIVE'
        LEFT JOIN biz_logistics_plan p ON p.order_id=o.id AND p.is_deleted=0
        %s ORDER BY o.id DESC LIMIT %%s OFFSET %%s
        """ % where, [size, (page - 1) * size])
    return ok(page_data(rows, total, page, size))


@bp.post('/admin/logistics-plans')
@plat_required
def platform_create_plan():
    """运营代钢厂制定物流方案（订单履约中），方案自动给到钢厂（站内消息 + 现有页面可见）。"""
    p = get_params()
    require_fields(p, 'orderId', 'orgMode')
    order = q1(g.conn, "SELECT * FROM biz_order WHERE id=%s AND is_deleted=0", (p['orderId'],))
    if not order:
        raise ApiError(40401, '订单不存在')
    if order['status'] != 'PERFORMING':
        raise ApiError(40901, '仅履约中订单可制定物流方案（当前 %s）' % order['status'])
    if q1(g.conn, "SELECT id FROM biz_logistics_plan WHERE order_id=%s AND is_deleted=0", (p['orderId'],)):
        raise ApiError(40902, '该订单已存在物流方案')
    if p['orgMode'] not in ('SELF', 'PLATFORM'):
        raise ApiError(40001, '组织方式仅支持 SELF/PLATFORM')
    pid = execute(g.conn, """
        INSERT INTO biz_logistics_plan (plan_no, order_id, org_mode, remark, created_by, updated_by)
        VALUES (%s,%s,%s,%s,%s,%s) RETURNING id
        """, (doc_no(g.conn, 'WL'), p['orderId'], p['orgMode'], p.get('remark'),
              g.ctx.user['id'], g.ctx.user['id']), returning_id=True)
    execute(g.conn, """
        INSERT INTO biz_track_node (biz_type, biz_id, node_code, node_name, occur_time, source, remark, created_by)
        VALUES ('ORDER', %s, 'LOGISTICS_PLAN_CREATED', '平台制定物流方案', now(), 'MANUAL', %s, %s)
        """, (p['orderId'], p.get('remark') or ('组织方式 %s' % p['orgMode']), g.ctx.user['id']))
    send_msg(g.conn, order['buyer_id'], '物流方案已制定',
             '订单 %s 平台已制定物流方案，贵司无需操作，可在履约跟踪查看进度。' % order['order_no'],
             'ORDER', p['orderId'])
    op_log(g.conn, g.ctx, 'biz_logistics_plan', pid, 'PLATFORM_CREATE', None, p)
    return ok({'planId': pid})


@bp.post('/admin/logistics-plans/<int:pid>/waybills')
@plat_required
def platform_create_waybill(pid):
    """运营代钢厂创建分段运单并匹配承运商（带 carrierId → 待接单；不带 → 待指派）。"""
    plan = q1(g.conn, """
        SELECT p.*, o.quantity AS order_qty, o.buyer_id, o.order_no
        FROM biz_logistics_plan p JOIN biz_order o ON o.id=p.order_id
        WHERE p.id=%s AND p.is_deleted=0 AND o.is_deleted=0
        """, (pid,))
    if not plan:
        raise ApiError(40401, '物流方案不存在')
    p = get_params()
    require_fields(p, 'segmentNo', 'transportMode', 'planQty', 'planDepartDate', 'planArriveDate')
    if p['transportMode'] not in ('SEA', 'RAIL', 'ROAD', 'MULTIMODAL'):
        raise ApiError(40001, '运输方式仅支持 SEA/RAIL/ROAD/MULTIMODAL')
    if parse_date(p, 'planArriveDate') < parse_date(p, 'planDepartDate'):
        raise ApiError(40001, '计划到达日不能早于计划发运日')
    plan_qty = p['planQty']
    if plan_qty <= 0:
        raise ApiError(40001, '计划量必须大于0')
    seg_no = str(p['segmentNo'])
    if q1(g.conn, "SELECT id FROM biz_waybill WHERE plan_id=%s AND segment_no=%s AND is_deleted=0",
          (pid, seg_no)):
        raise ApiError(40902, '分段序号 %s 已存在' % seg_no)
    used = q1(g.conn, """
        SELECT coalesce(sum(plan_qty),0) AS t FROM biz_waybill
        WHERE order_id=%s AND is_deleted=0 AND status<>'CANCELLED'
        """, (plan['order_id'],))['t']
    new_total = used + plan_qty
    deviation = abs(new_total - plan['order_qty']) / plan['order_qty'] * 100
    if deviation > 5 and not (p.get('deviationReason') or '').strip():
        raise ApiError(40001, '分段计划量合计与订单数量偏差 %.2f%% 超过 5%%，必须填写偏差说明' % deviation)
    carrier_id = p.get('carrierId')
    if carrier_id:
        _check_carrier(carrier_id)
        status = 'PENDING_ACCEPT'
    else:
        status = 'PENDING_ASSIGN'
    wid = execute(g.conn, """
        INSERT INTO biz_waybill (waybill_no, order_id, plan_id, segment_no, carrier_id, transport_mode,
            depart_place, arrive_place, plan_depart_date, plan_arrive_date, plan_qty, freight,
            vehicle_no, status, created_by, updated_by)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id
        """, (doc_no(g.conn, 'YD'), plan['order_id'], pid, seg_no, carrier_id,
              p['transportMode'], p.get('departPlace'), p.get('arrivePlace'),
              parse_date(p, 'planDepartDate'), parse_date(p, 'planArriveDate'), plan_qty,
              p.get('freight'), p.get('vehicleNo'), status, g.ctx.user['id'], g.ctx.user['id']),
        returning_id=True)
    if deviation > 5:
        op_log(g.conn, g.ctx, 'biz_waybill', wid, 'DEVIATION', None,
               {'deviationRate': '%.2f%%' % deviation, 'reason': p.get('deviationReason')})
    if status == 'PENDING_ACCEPT' and carrier_id:
        send_msg(g.conn, carrier_id, '运单待接单',
                 '订单 %s 分段运单已指派，请接单确认。' % plan['order_no'], 'WAYBILL', wid)
    send_msg(g.conn, plan['buyer_id'], '运单已安排',
             '订单 %s 分段 %s 运单已创建，贵司无需操作，可在履约跟踪查看进度。' % (plan['order_no'], p['segmentNo']),
             'ORDER', plan['order_id'])
    op_log(g.conn, g.ctx, 'biz_waybill', wid, 'PLATFORM_CREATE', None,
           {'planQty': str(plan_qty), 'status': status})
    return ok({'id': wid, 'status': status, 'planTotalDeviation': '%.2f%%' % deviation})


@bp.put('/admin/waybills/<int:wid>/assign')
@plat_required
def platform_assign_waybill(wid):
    """运营为待指派运单匹配承运商（PENDING_ASSIGN → PENDING_ACCEPT）。"""
    p = get_params()
    require_fields(p, 'carrierId')
    _check_carrier(p['carrierId'])
    row = q1(g.conn, "SELECT * FROM biz_waybill WHERE id=%s AND is_deleted=0", (wid,))
    if not row:
        raise ApiError(40401, '运单不存在')
    if row['status'] != 'PENDING_ASSIGN':
        raise ApiError(40901, '运单状态为 %s，不可指派' % row['status'])
    execute(g.conn, """
        UPDATE biz_waybill SET carrier_id=%s, status='PENDING_ACCEPT', updated_by=%s, updated_at=now()
        WHERE id=%s
        """, (p['carrierId'], g.ctx.user['id'], wid))
    send_msg(g.conn, p['carrierId'], '运单待接单',
             '运单 %s 已指派给贵司，请接单确认。' % row['waybill_no'], 'WAYBILL', wid)
    op_log(g.conn, g.ctx, 'biz_waybill', wid, 'PLATFORM_ASSIGN', None, {'carrierId': p['carrierId']})
    return ok({'id': wid, 'status': 'PENDING_ACCEPT'})


@bp.put('/admin/waybills/<int:wid>/advance')
@plat_required
def platform_waybill_advance(wid):
    """运营代推进运单节点：DEPART 发运 / ARRIVE 到达 / SIGN 签收（与各端现有动作同语义）。"""
    row = q1(g.conn, "SELECT * FROM biz_waybill WHERE id=%s AND is_deleted=0", (wid,))
    if not row:
        raise ApiError(40401, '运单不存在')
    order = q1(g.conn, "SELECT id, buyer_id, supplier_id, order_no FROM biz_order WHERE id=%s AND is_deleted=0",
               (row['order_id'],))
    p = get_params()
    require_fields(p, 'action')
    action = p['action']
    occur = parse_datetime(p, 'occurTime', required=False)
    if action == 'DEPART':
        if row['status'] != 'PENDING_DEPART':
            raise ApiError(40901, '运单状态为 %s，不可发运' % row['status'])
        transition(g.conn, g.ctx, 'biz_waybill', '运单', 'biz_waybill', wid, 'IN_TRANSIT',
                   node_biz_type='WAYBILL', node_code='WAYBILL_DEPARTED')
        execute(g.conn, """
            UPDATE biz_waybill SET actual_depart_at=%s, actual_qty=%s, updated_by=%s, updated_at=now()
            WHERE id=%s
            """, (occur or datetime.now(), p.get('actualQty') or row['plan_qty'], g.ctx.user['id'], wid))
        send_msg(g.conn, order['buyer_id'], '运单已发运',
                 '订单 %s 运单 %s 已发运，可在履约跟踪查看在途节点。' % (order['order_no'], row['waybill_no']),
                 'WAYBILL', wid)
    elif action == 'ARRIVE':
        if row['status'] != 'IN_TRANSIT':
            raise ApiError(40901, '运单状态为 %s，不可到达' % row['status'])
        transition(g.conn, g.ctx, 'biz_waybill', '运单', 'biz_waybill', wid, 'ARRIVED',
                   node_biz_type='WAYBILL', node_code='WAYBILL_ARRIVED')
        execute(g.conn, """
            UPDATE biz_waybill SET actual_arrive_at=%s, updated_by=%s, updated_at=now() WHERE id=%s
            """, (occur, g.ctx.user['id'], wid))
        send_msg(g.conn, order['buyer_id'], '运单已到达',
                 '订单 %s 运单 %s 已到达，待签收。' % (order['order_no'], row['waybill_no']), 'WAYBILL', wid)
    elif action == 'SIGN':
        if row['status'] != 'ARRIVED':
            raise ApiError(40901, '运单状态为 %s，不可签收' % row['status'])
        transition(g.conn, g.ctx, 'biz_waybill', '运单', 'biz_waybill', wid, 'SIGNED',
                   node_biz_type='WAYBILL', node_code='WAYBILL_SIGNED')
        execute(g.conn, """
            UPDATE biz_waybill SET actual_arrive_at=coalesce(actual_arrive_at, %s), updated_by=%s,
                updated_at=now() WHERE id=%s
            """, (occur or datetime.now(), g.ctx.user['id'], wid))
        send_msg(g.conn, order['buyer_id'], '运单已签收',
                 '订单 %s 运单 %s 已签收。' % (order['order_no'], row['waybill_no']), 'WAYBILL', wid)
        send_msg(g.conn, order['supplier_id'], '运单已签收',
                 '订单 %s 运单 %s 已签收。' % (order['order_no'], row['waybill_no']), 'WAYBILL', wid)
    else:
        raise ApiError(40001, 'action 仅支持 DEPART/ARRIVE/SIGN')
    op_log(g.conn, g.ctx, 'biz_waybill', wid, 'PLATFORM_ADVANCE %s' % action, None, p)
    return ok({'id': wid, 'action': action})


@bp.get('/admin/waybills-ops')
@plat_required
def platform_waybill_ops():
    """调度视角运单列表（在途监控），含订单/合同/承运商信息。"""
    params = get_params()
    page, size = page_args(params)
    where = "WHERE w.is_deleted=0"
    args = []
    if params.get('status'):
        where += " AND w.status=%s"
        args.append(params['status'])
    if params.get('planId'):
        where += " AND w.plan_id=%s"
        args.append(params['planId'])
    if params.get('orderId'):
        where += " AND w.order_id=%s"
        args.append(params['orderId'])
    total = q1(g.conn, 'SELECT count(*) AS c FROM biz_waybill w ' + where, args)['c']
    rows = qall(g.conn, """
        SELECT w.id, w.waybill_no AS "waybillNo", w.order_id AS "orderId", o.order_no AS "orderNo",
               c.contract_no AS "contractNo", b.company_name AS "buyerName",
               s.company_name AS "supplierName", w.segment_no AS "segmentNo",
               w.transport_mode AS "transportMode", w.depart_place AS "departPlace",
               w.arrive_place AS "arrivePlace", w.plan_depart_date AS "planDepartDate",
               w.plan_arrive_date AS "planArriveDate", w.plan_qty AS "planQty",
               w.freight, w.vehicle_no AS "vehicleNo",
               cr.company_name AS "carrierName", w.actual_depart_at AS "actualDepartAt",
               w.actual_arrive_at AS "actualArriveAt", w.status, w.created_at AS "createdAt"
        FROM biz_waybill w
        JOIN biz_order o ON o.id=w.order_id
        JOIN ent_company b ON b.id=o.buyer_id
        JOIN ent_company s ON s.id=o.supplier_id
        LEFT JOIN ent_company cr ON cr.id=w.carrier_id
        LEFT JOIN biz_contract c ON c.order_id=o.id AND c.is_deleted=0 AND c.status='EFFECTIVE'
        %s ORDER BY w.id DESC LIMIT %%s OFFSET %%s
        """ % where, args + [size, (page - 1) * size])
    return ok(page_data(rows, total, page, size))


# ---------- 对账结算：只读统计 ----------
@bp.get('/admin/settlement-stats')
@plat_required
def platform_settlement_stats():
    """结算统计看板数据（只读聚合）。"""
    t = q1(g.conn, """
        SELECT count(*) AS total,
               coalesce(sum(CASE WHEN status IN ('CONFIRMED','COMPLETED') THEN total_amount END),0) AS confirmed_amount,
               count(*) FILTER (WHERE status LIKE 'PENDING%%') AS pending_count,
               coalesce(sum(total_amount),0) AS settle_amount
        FROM biz_settlement WHERE is_deleted=0
        """)
    paid = q1(g.conn, """
        SELECT coalesce(sum(p.amount),0) AS paid FROM biz_payment p
        JOIN biz_settlement s ON s.id=p.settlement_id
        WHERE p.is_deleted=0 AND s.is_deleted=0
        """)
    return ok({
        'total': t['total'],
        'confirmedAmount': t['confirmed_amount'],
        'pendingCount': t['pending_count'],
        'settleAmount': t['settle_amount'],
        'paidAmount': paid['paid'],
    })


@bp.get('/admin/settlements')
@plat_required
def platform_settlement_list():
    """结算单列表（只读）：含双方企业、金额、确认进度与付款进度。"""
    params = get_params()
    page, size = page_args(params)
    where = "WHERE st.is_deleted=0"
    args = []
    if params.get('status'):
        where += " AND st.status=%s"
        args.append(params['status'])
    total = q1(g.conn, 'SELECT count(*) AS c FROM biz_settlement st ' + where, args)['c']
    rows = qall(g.conn, """
        SELECT st.id, st.settle_no AS "settleNo", st.order_id AS "orderId", o.order_no AS "orderNo",
               b.company_name AS "buyerName", s.company_name AS "supplierName",
               st.settle_qty AS "settleQty", st.unit_price AS "unitPrice",
               st.adjust_amount AS "adjustAmount", st.deduct_amount AS "deductAmount",
               st.total_amount AS "totalAmount", st.status,
               st.supplier_confirm_at AS "supplierConfirmAt", st.buyer_confirm_at AS "buyerConfirmAt",
               (SELECT coalesce(sum(p.amount),0) FROM biz_payment p
                WHERE p.settlement_id=st.id AND p.is_deleted=0) AS "paidAmount",
               st.created_at AS "createdAt"
        FROM biz_settlement st
        JOIN biz_order o ON o.id=st.order_id
        JOIN ent_company b ON b.id=o.buyer_id
        JOIN ent_company s ON s.id=o.supplier_id
        %s ORDER BY st.id DESC LIMIT %%s OFFSET %%s
        """ % where, args + [size, (page - 1) * size])
    return ok(page_data(rows, total, page, size))


@bp.get('/admin/settlements/<int:sid>/payments')
@plat_required
def platform_settlement_payments(sid):
    """结算单付款记录（只读）。"""
    rows = qall(g.conn, """
        SELECT p.id, p.payment_no AS "paymentNo", p.amount, p.pay_date AS "payDate",
               p.pay_desc AS "payDesc", p.file_url AS "fileUrl"
        FROM biz_payment p WHERE p.settlement_id=%s AND p.is_deleted=0 ORDER BY p.id DESC
        """, (sid,))
    return ok({'list': rows})


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
        INSERT INTO base_variety (variety_code, variety_name, category, default_grade, unit, sort_no, created_by, updated_by)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id
        """, (p['varietyCode'], p['varietyName'], p.get('category'), grade, p.get('unit') or '吨',
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
    fields = {'varietyName': 'variety_name', 'category': 'category', 'defaultGrade': 'default_grade',
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
        'companyApproved': count("SELECT count(*) AS c FROM ent_company WHERE is_deleted=0 AND audit_status='APPROVED'"),
        'procureQty': q1(g.conn, "SELECT COALESCE(SUM(quantity),0) AS c FROM biz_order WHERE is_deleted=0")['c'],
        'waybillTotal': count("SELECT count(*) AS c FROM biz_waybill WHERE is_deleted=0"),
        'totalAmount': q1(g.conn, "SELECT COALESCE(SUM(amount),0) AS c FROM biz_order WHERE is_deleted=0")['c'],
        'companyPending': count("SELECT count(*) AS c FROM ent_company WHERE is_deleted=0 AND audit_status='PENDING'"),
        'orderActive': count("SELECT count(*) AS c FROM biz_order WHERE is_deleted=0 AND status NOT IN ('CANCELLED','COMPLETED')"),
        'orderTotal': count("SELECT count(*) AS c FROM biz_order WHERE is_deleted=0"),
        'alertPending': count("SELECT count(*) AS c FROM biz_alert WHERE is_deleted=0 AND status<>'CLOSED'"),
        'inquiryQuoting': count("SELECT count(*) AS c FROM biz_inquiry WHERE is_deleted=0 AND status IN ('SENT','QUOTING')"),
    })


@bp.get('/admin/dashboard/charts')
@plat_required
def dashboard_charts():
    """运营看板图表：货运趋势 / 矿种分布 / 运输方式运量对比。"""
    freight = qall(g.conn, """
        SELECT DATE(created_at) AS "trendDate", SUM(plan_qty) AS qty, count(*) AS cnt
        FROM biz_waybill
        WHERE is_deleted=0 AND created_at >= current_date - interval '13 days'
        GROUP BY DATE(created_at) ORDER BY 1
    """)
    variety = qall(g.conn, """
        SELECT v.variety_name AS "name", COALESCE(SUM(o.quantity),0) AS qty
        FROM biz_order o JOIN base_variety v ON v.id = o.variety_id
        WHERE o.is_deleted=0
        GROUP BY v.variety_name ORDER BY qty DESC
    """)
    mode = qall(g.conn, """
        SELECT transport_mode AS "mode", COALESCE(SUM(plan_qty),0) AS qty, count(*) AS cnt
        FROM biz_waybill WHERE is_deleted=0
        GROUP BY transport_mode ORDER BY qty DESC
    """)
    return ok({'freightTrend': json_payload(freight), 'varietyDist': json_payload(variety),
               'modeDist': json_payload(mode)})


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
