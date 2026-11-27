"""运营后台（PRD 4.10）：企业审核、品种与基准价维护、单据总览、数据字典、操作日志。"""
import json
from datetime import datetime, timedelta
from decimal import Decimal

from flask import g, request

from ..common import (ApiError, doc_no, get_params, json_payload, ok, op_log,
                      page_args, page_data, parse_date, parse_datetime,
                      require_fields, send_msg, validate_credit_code,
                      validate_password, validate_phone)
from ..db import execute, qall, q1
from ..security import hash_password, plat_required, roles_from_company_types
from ..state_machine import transition, add_node
from . import bp
from .inquiry import _auto_deadline, _check_invites, create_and_send_agg_inquiry, reveal_inquiry
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
    keyword = (params.get('keyword') or '').strip()
    if keyword:
        # 关键字检索：企业名称/信用代码/联系人/联系电话/登录账号
        where += """ AND (company_name ILIKE %s OR credit_code ILIKE %s OR contact_name ILIKE %s
            OR contact_phone ILIKE %s OR EXISTS (
                SELECT 1 FROM sys_user u2 WHERE u2.company_id = ent_company.id
                  AND u2.is_deleted = 0 AND u2.username ILIKE %s))"""
        args.extend(['%' + keyword + '%'] * 5)
    total = q1(g.conn, 'SELECT count(*) AS c FROM ent_company ' + where, args)['c']
    rows = qall(g.conn, """
        SELECT id, company_name AS "companyName", credit_code AS "creditCode",
               company_types AS "companyTypes", contact_name AS "contactName",
               contact_phone AS "contactPhone", audit_status AS "auditStatus",
               audit_remark AS "auditRemark", status, created_at AS "createdAt",
               (SELECT u.username FROM sys_user u WHERE u.company_id = ent_company.id
                  AND u.is_deleted = 0 ORDER BY u.id LIMIT 1) AS "account"
        FROM ent_company %s ORDER BY id DESC LIMIT %%s OFFSET %%s
        """ % where, args + [size, (page - 1) * size])
    return ok(page_data(rows, total, page, size))


@bp.post('/admin/companies/register')
@plat_required
def platform_company_register():
    """运营端代注册：表单字段与企业注册页一致，但全部为选填。

    缺失字段处理：企业名称/信用代码自动生成占位值（信用代码 18 位、以 AD 开头标识代注册）；
    登录账号填写且企业角色已选时才创建账号（密码缺省自动生成并在响应中返回，运营转告企业）；
    营业执照选传（licenseFileId），缺省不写资质。企业落库为 PENDING，走正常准入审核流程。
    """
    p = get_params()
    name = (p.get('companyName') or '').strip()
    if not name:
        name = '待完善企业 ' + datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    credit = (p.get('creditCode') or '').strip()
    if credit:
        validate_credit_code(credit)
        if q1(g.conn, "SELECT id FROM ent_company WHERE credit_code=%s AND is_deleted=0", (credit,)):
            raise ApiError(40902, '统一社会信用代码已存在')
    else:
        # 占位信用代码：AD + 时间戳（微秒截断至 16 位），满足 15~18 位大写字母数字且唯一
        credit = ('AD' + datetime.now().strftime('%y%m%d%H%M%S%f'))[:18]
        if q1(g.conn, "SELECT id FROM ent_company WHERE credit_code=%s", (credit,)):
            raise ApiError(40902, '占位信用代码冲突，请重试')
    # 企业类型：选填；填写登录账号时必须已选（角色由企业类型推导）
    types = []
    raw_types = (p.get('companyTypes') or '').strip()
    if raw_types:
        type_alias = {'STEEL': 'STEEL', 'STEEL_BUYER': 'STEEL', 'SUPPLIER': 'SUPPLIER'}
        for t in (s.strip() for s in raw_types.split(',')):
            if not t:
                continue
            t = type_alias.get(t, t)
            if t not in ('STEEL', 'SUPPLIER') or t in types:
                raise ApiError(40001, '企业类型不合法（STEEL/SUPPLIER 逗号分隔）')
            types.append(t)
    roles = ','.join(roles_from_company_types(','.join(types))) if types else ''

    contact_phone = (p.get('contactPhone') or '').strip()
    if contact_phone:
        validate_phone(contact_phone)
    contact_email = (p.get('contactEmail') or '').strip()
    if contact_email and '@' not in contact_email:
        raise ApiError(40001, '联系邮箱格式不正确')
    legal_person = (p.get('legalPerson') or '').strip()
    if len(legal_person) > 30:
        raise ApiError(40001, '法定代表人不超过 30 字')

    # 账号：选填——仅当登录账号 + 企业角色齐备时创建；密码缺省自动生成（响应返回，运营转告企业）
    username = (p.get('username') or '').strip()
    generated_pwd = None
    if username:
        if not types:
            raise ApiError(40001, '填写登录账号时须选择企业角色')
        validate_phone(username)
        if q1(g.conn, "SELECT id FROM sys_user WHERE username=%s AND is_deleted=0", (username,)):
            raise ApiError(40902, '手机号已被注册')
        password = p.get('password')
        if password:
            validate_password(password)
        else:
            import secrets
            # 自动生成 8 位口令：字母 4 + 大写 1 + 数字 3（满足"字母+数字且≥8位"强度规则）
            alphabet = 'abcdefghjkmnpqrstuvwxyz'
            generated_pwd = ''.join(secrets.choice(alphabet) for _ in range(4)) \
                + secrets.choice('ABCDEFGHJKLMNPQRSTUVWXYZ') \
                + ''.join(secrets.choice('0123456789') for _ in range(3))
            password = generated_pwd

    license_file_id = (p.get('licenseFileId') or '').strip() or None
    lic = None
    if license_file_id:
        lic = q1(g.conn, "SELECT * FROM sys_file WHERE file_id=%s AND is_deleted=0", (license_file_id,))
        if not lic:
            raise ApiError(40401, '营业执照附件不存在，请先上传')

    admin_id = g.ctx.user['id']
    cid = execute(g.conn, """
        INSERT INTO ent_company (company_name, credit_code, company_types, province, city,
                                 address, legal_person, contact_name, contact_phone,
                                 contact_email, business_scope, bank_name, bank_account,
                                 audit_status, created_by, updated_by)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'PENDING',%s,%s) RETURNING id
        """, (name, credit, ','.join(types) if types else '', p.get('province'),
              p.get('city'), (p.get('address') or '').strip(), legal_person,
              (p.get('contactName') or '').strip(), contact_phone, contact_email,
              (p.get('businessScope') or '').strip(), p.get('bankName'), p.get('bankAccount'),
              admin_id, admin_id), returning_id=True)
    uid = None
    if username:
        uid = execute(g.conn, """
            INSERT INTO sys_user (company_id, username, password_hash, real_name, roles, created_by)
            VALUES (%s,%s,%s,%s,%s,%s) RETURNING id
            """, (cid, username, hash_password(password),
                  (p.get('contactName') or '').strip() or name, roles, admin_id), returning_id=True)
        op_log(g.conn, g.ctx, 'sys_user', uid, 'ADMIN_REGISTER_USER', None,
               {'username': username, 'companyTypes': ','.join(types)})
    if lic:
        execute(g.conn, """
            INSERT INTO ent_qualification (company_id, file_id, file_name, file_type, created_by)
            VALUES (%s,%s,%s,'BUSINESS_LICENSE',%s)
            """, (cid, license_file_id, lic['file_name'], admin_id))
    op_log(g.conn, g.ctx, 'ent_company', cid, 'ADMIN_REGISTER', None,
           {'companyName': name, 'creditCode': credit,
            'placeholderCredit': not bool((p.get('creditCode') or '').strip())})
    return ok({'companyId': cid, 'userId': uid, 'username': username or None,
               'generatedPassword': generated_pwd, 'auditStatus': 'PENDING'})


@bp.put('/admin/companies/<int:cid>/reset-password')
@plat_required
def reset_company_password(cid):
    """运营端重置企业账号密码：由运营端传入新口令（强度校验 + bcrypt 散列落库），不再使用固定演示口令。"""
    p = get_params()
    require_fields(p, 'password')
    validate_password(p['password'])
    row = q1(g.conn, "SELECT id, company_name FROM ent_company WHERE id=%s AND is_deleted=0", (cid,))
    if not row:
        raise ApiError(40401, '企业不存在')
    users = qall(g.conn, "SELECT id FROM sys_user WHERE company_id=%s AND is_deleted=0", (cid,))
    if not users:
        raise ApiError(40401, '该企业暂无账号')
    execute(g.conn, "UPDATE sys_user SET password_hash=%s WHERE company_id=%s AND is_deleted=0",
            (hash_password(p['password']), cid))
    op_log(g.conn, g.ctx, 'sys_user', cid, 'RESET_PASSWORD', None,
           {'company': row['company_name'], 'accounts': len(users)})
    return ok({'reset': len(users)})


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
    from ..common import send_msg
    import json as _json
    pending = None
    if row.get('pending_changes'):
        try:
            pending = _json.loads(row['pending_changes'])
        except Exception:
            pending = None
    change_review = bool(pending)
    # 变更字段 → 数据库列映射（与 company.py 信息维护一致）
    FIELD_COL = {'companyName': 'company_name', 'creditCode': 'credit_code', 'province': 'province',
                 'city': 'city', 'address': 'address', 'legalPerson': 'legal_person',
                 'contactName': 'contact_name', 'contactPhone': 'contact_phone',
                 'contactEmail': 'contact_email', 'businessScope': 'business_scope',
                 'bankName': 'bank_name', 'bankAccount': 'bank_account'}
    if approve:
        to = 'APPROVED'
        transition(g.conn, g.ctx, 'ent_company', '企业', 'ent_company', cid, to)
        if change_review:
            cols = {FIELD_COL[k]: str(v) for k, v in pending.items() if k in FIELD_COL}
            if cols:
                sets = ', '.join('%s=%%s' % c for c in cols)
                execute(g.conn, "UPDATE ent_company SET " + sets + ", audit_remark=%s, "
                        "pending_changes=NULL, updated_by=%s WHERE id=%s",
                        list(cols.values()) + ['信息变更审核通过', g.ctx.user['id'], cid])
            else:
                execute(g.conn, "UPDATE ent_company SET audit_remark=%s, pending_changes=NULL, "
                        "updated_by=%s WHERE id=%s", ('信息变更审核通过', g.ctx.user['id'], cid))
            op_log(g.conn, g.ctx, 'ent_company', cid, 'CHANGE APPROVED', None, pending)
            send_msg(g.conn, cid, '信息变更审核通过',
                     '您提交的企业信息变更已审核通过，企业信息已自动更新。', 'COMPANY', cid)
        else:
            execute(g.conn, "UPDATE ent_company SET audit_remark=%s, pending_changes=NULL, "
                    "updated_by=%s WHERE id=%s", (remark or '审核通过', g.ctx.user['id'], cid))
            send_msg(g.conn, cid, '准入审核%s' % ('通过' if approve else '驳回'),
                     remark or '恭喜，您的企业已通过平台准入审核，可开始使用业务功能。', 'COMPANY', cid)
    elif change_review:
        # 信息变更驳回：恢复准入状态（企业信息保持不变），丢弃变更
        to = 'APPROVED'
        transition(g.conn, g.ctx, 'ent_company', '企业', 'ent_company', cid, to)
        execute(g.conn, "UPDATE ent_company SET audit_status='APPROVED', audit_remark=%s, "
                "pending_changes=NULL, updated_by=%s WHERE id=%s",
                ('信息变更未通过：' + str(remark).strip(), g.ctx.user['id'], cid))
        op_log(g.conn, g.ctx, 'ent_company', cid, 'CHANGE REJECTED', None, pending)
        send_msg(g.conn, cid, '企业信息变更未通过',
                 '您提交的企业信息变更未通过审核：' + str(remark).strip() + '。企业信息保持不变。', 'COMPANY', cid,
                 need_action=True)
    else:
        to = 'REJECTED'
        transition(g.conn, g.ctx, 'ent_company', '企业', 'ent_company', cid, to)
        execute(g.conn, "UPDATE ent_company SET audit_remark=%s, pending_changes=NULL, "
                "updated_by=%s WHERE id=%s", (remark or '审核通过', g.ctx.user['id'], cid))
        send_msg(g.conn, cid, '准入审核%s' % ('通过' if approve else '驳回'),
                 remark or '恭喜，您的企业已通过平台准入审核，可开始使用业务功能。', 'COMPANY', cid,
                 need_action=not approve)
    return ok({'auditStatus': to, 'changeReview': change_review})


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
    """归集各钢厂需求单（按明细行展开：一行 = 需求单 × 品种明细）。
    钢厂端询价提交（非草稿）后，行内展示关联询价（单号/状态）——
    运营端据此在「报价询价」模块平台代发，钢厂端不直接联系供应商端。"""
    params = get_params()
    page, size = page_args(params)
    # 草稿不推送运营端：钢厂提交（SUBMITTED/WITHDRAWN/INQUIRING/DEALT/CLOSED）后才进入归集池
    where = "WHERE d.is_deleted=0 AND i.is_deleted=0 AND d.status <> 'DRAFT'"
    args = []
    status = params.get('status')
    if status:
        where += ' AND d.status=%s'
        args.append(status)
    inq_sub = """(SELECT x.{col} FROM biz_inquiry x
                  WHERE x.demand_item_id=i.id AND x.is_deleted=0 AND x.status <> 'DRAFT'
                  ORDER BY x.id DESC LIMIT 1)"""
    total = q1(g.conn, """
        SELECT count(*) AS c
        FROM biz_demand_item i
        JOIN biz_demand d ON d.id=i.demand_id
        %s
        """ % where, args)['c']
    rows = qall(g.conn, """
        SELECT i.id, d.id AS "demandId", d.demand_no AS "demandNo", d.demand_name AS "demandName",
               c.company_name AS "companyName", v.category, v.variety_name AS "varietyName",
               i.quantity, i.grade,
               i.cycle_type AS "cycleType", i.cycle_year AS "cycleYear", i.cycle_value AS "cycleValue",
               i.inquired_qty AS "inquiredQty",
               d.delivery_type AS "deliveryType", d.delivery_place AS "deliveryPlace",
               d.expect_arrive_start AS "expectArriveStart", d.expect_arrive_end AS "expectArriveEnd",
               d.status, d.version AS "version",
               COALESCE(d.submitted_at, d.updated_at) AS "submittedAt",
               (SELECT a.agg_no FROM biz_aggregated_order_item m
                 JOIN biz_aggregated_order a ON a.id=m.agg_id AND a.is_deleted=0
                 WHERE m.demand_item_id=i.id AND m.is_deleted=0
                 ORDER BY m.id DESC LIMIT 1) AS "aggNo",
               (SELECT a.id FROM biz_aggregated_order_item m
                 JOIN biz_aggregated_order a ON a.id=m.agg_id AND a.is_deleted=0
                 WHERE m.demand_item_id=i.id AND m.is_deleted=0
                 ORDER BY m.id DESC LIMIT 1) AS "aggId",
               %s AS "inquiryNo",
               %s AS "inquiryStatus",
               %s AS "inquiryDeadline",
               %s AS "inquiryId"
        FROM biz_demand_item i
        JOIN biz_demand d ON d.id=i.demand_id
        JOIN ent_company c ON c.id=d.company_id
        JOIN base_variety v ON v.id=i.variety_id
        %s
        ORDER BY COALESCE(d.submitted_at, d.updated_at) DESC, d.id DESC, i.id
        LIMIT %%s OFFSET %%s
        """ % (inq_sub.format(col='inquiry_no'), inq_sub.format(col='status'),
               inq_sub.format(col='deadline'), inq_sub.format(col='id'), where), args + [size, (page - 1) * size])
    return ok(page_data(rows, total, page, size))


@bp.get('/admin/inquiry-pool')
@plat_required
def inquiry_pool():
    """钢厂询价单归集池：钢厂已提交（SENT）的询价单，按单归集生成总询价单。

    与需求归集池并存：需求列表按需求明细归集，询价单列表按钢厂询价单归集，
    归集后统一走「报价询价」向供应商发出总询价单。
    """
    params = get_params()
    page, size = page_args(params)
    where = """WHERE x.is_deleted=0 AND x.source='STEEL' AND x.status='SENT'
               AND d.is_deleted=0 AND i.is_deleted=0"""
    total = q1(g.conn, """
        SELECT count(*) AS c
        FROM biz_inquiry x
        JOIN biz_demand_item i ON i.id=x.demand_item_id
        JOIN biz_demand d ON d.id=i.demand_id
        %s
        """ % where, ())['c']
    rows = qall(g.conn, """
        SELECT x.id AS "inquiryId", x.inquiry_no AS "inquiryNo",
               c.company_name AS "companyName", v.category, v.variety_name AS "varietyName",
               x.grade, x.quantity,
               i.cycle_type AS "cycleType", i.cycle_year AS "cycleYear", i.cycle_value AS "cycleValue",
               d.demand_no AS "demandNo", d.id AS "demandId",
               d.delivery_type AS "deliveryType", d.delivery_place AS "deliveryPlace",
               x.expect_arrive_date AS "arriveDate", x.deadline,
               COALESCE(x.sent_at, x.created_at) AS "sentAt"
        FROM biz_inquiry x
        JOIN biz_demand_item i ON i.id=x.demand_item_id
        JOIN biz_demand d ON d.id=i.demand_id
        JOIN ent_company c ON c.id=x.buyer_id
        JOIN base_variety v ON v.id=x.variety_id
        %s
        ORDER BY COALESCE(x.sent_at, x.created_at) DESC, x.id DESC
        LIMIT %%s OFFSET %%s
        """ % where, [size, (page - 1) * size])
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
    else:
        # 默认不含钢厂本地暂存（DRAFT）的变更申请——钢厂点提交后才对运营端可见
        where += " AND ch.status<>'DRAFT'"
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
    """变更申请审核：通过/驳回（驳回必填原因），结论站内通知申请企业。

    通过后自动同步：按变更后数据回放更新需求单（含明细），并同步归集订单——
    数量类变更更新成员份额与总吨数；品类/品位变更将需求移出原归集单（可重新归集）。
    """
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
    ad = row['after_data']
    if isinstance(ad, str):
        try:
            ad = json.loads(ad or '{}')
        except ValueError:
            ad = {}
    is_delete_req = isinstance(ad, dict) and bool(ad.get('deleteRequest'))
    transition(g.conn, g.ctx, 'biz_demand_change', '变更申请', 'biz_demand_change', cid, to)
    execute(g.conn, """
        UPDATE biz_demand_change SET audit_remark=%s, audit_by=%s, audit_at=now(),
               updated_by=%s, updated_at=now() WHERE id=%s
        """, (remark, g.ctx.user['id'], g.ctx.user['id'], cid))
    if is_delete_req:
        # 删除申请审核：通过→关闭需求（移出未询价归集单并释放份额）；驳回→回退删除前状态
        if approve:
            for m in qall(g.conn, """
                    SELECT m.id, m.agg_id, m.quantity, m.demand_item_id
                    FROM biz_aggregated_order_item m
                    JOIN biz_aggregated_order a ON a.id=m.agg_id AND a.is_deleted=0 AND a.status='OPEN'
                    WHERE m.demand_id=%s AND m.is_deleted=0 AND m.inquiry_id IS NULL
                    """, (row['demand_id'],)):
                _release_agg_member(g.conn, g.ctx, m['id'], m['agg_id'], m['quantity'], m['demand_item_id'])
            transition(g.conn, g.ctx, 'biz_demand', '需求单', 'biz_demand', row['demand_id'], 'CLOSED')
            op_log(g.conn, g.ctx, 'biz_demand', row['demand_id'], 'DELETE APPROVED',
                   None, {'changeNo': row['change_no'], 'reason': row['reason']})
        else:
            transition(g.conn, g.ctx, 'biz_demand', '需求单', 'biz_demand',
                       row['demand_id'], ad.get('fromStatus') or 'SUBMITTED')
        send_msg(g.conn, row['company_id'], '删除申请' + ('通过' if approve else '驳回'),
                 remark or ('您提交的需求删除申请已审核通过，需求单已关闭。' if approve
                            else '您提交的需求删除申请已驳回，需求单已回退原状态。'),
                 'DEMAND', row['demand_id'])
        return ok({'status': to, 'deleteRequest': True})
    synced = None
    if approve:
        synced = _apply_demand_change(g.conn, g.ctx, row['demand_id'], row['after_data'])
        op_log(g.conn, g.ctx, 'biz_demand', row['demand_id'], 'CHANGE SYNC',
               None, {'changeNo': row['change_no'], 'aggResync': synced})
    else:
        # 两步变更（钢厂保存时已将需求内容更新为变更后数据）：驳回时回放变更前数据，需求回到原内容
        drow = q1(g.conn, "SELECT status FROM biz_demand WHERE id=%s", (row['demand_id'],))
        if drow and drow['status'] == 'SUBMITTED':
            try:
                _apply_demand_change(g.conn, g.ctx, row['demand_id'], row['before_data'])
            except ApiError:
                pass  # 需求已进入其他流程（如已重新归集）时跳过回放
    send_msg(g.conn, row['company_id'],
             '需求变更申请%s' % ('通过' if approve else '驳回'),
             (remark or '您提交的需求变更申请已审核通过。') +
             ('变更已同步至需求单及关联归集订单。' if approve and synced else ''), 'DEMAND', row['demand_id'])
    return ok({'status': to, 'synced': synced})


def _apply_demand_change(conn, ctx, did, after_raw):
    """回放变更后数据：更新需求单与明细；如已归集（归集单未询价）同步归集订单数据。"""
    from .demand import _save_items
    try:
        after = json.loads(after_raw) if isinstance(after_raw, str) else (after_raw or {})
    except Exception:
        raise ApiError(40001, '变更后数据格式错误')
    d = q1(conn, "SELECT * FROM biz_demand WHERE id=%s AND is_deleted=0", (did,))
    if not d:
        raise ApiError(40401, '需求单不存在')
    if d['status'] not in ('SUBMITTED', 'TO_INQUIRY', 'AGGREGATED', 'INQUIRING'):
        raise ApiError(40901, '需求单当前状态为 %s，无法应用变更' % d['status'])
    place = (str(after.get('deliveryPlace')).strip() if after.get('deliveryPlace') is not None else '')
    execute(conn, """
        UPDATE biz_demand SET demand_name=%s, delivery_type=%s, delivery_place=%s,
            expect_arrive_start=%s, expect_arrive_end=%s, settle_type=%s, settle_days=%s,
            quality_req=%s, updated_by=%s, updated_at=now() WHERE id=%s
        """, (after.get('demandName') or d['demand_name'], after.get('deliveryType') or d['delivery_type'],
              place or None,
              _chg_date(after.get('expectArriveStart')) or d['expect_arrive_start'],
              _chg_date(after.get('expectArriveEnd')) or d['expect_arrive_end'],
              after.get('settleType') or d['settle_type'], after.get('settleDays') or d['settle_days'],
              after.get('qualityReq'), ctx.user['id'], did))
    items = after.get('items') or []
    if items:
        # 先取变更前明细（用于判断归集口径是否被破坏），再回放新明细
        old_item = q1(conn, """
            SELECT variety_id, grade FROM biz_demand_item WHERE demand_id=%s AND is_deleted=0 ORDER BY id LIMIT 1
            """, (did,))
        _save_items(conn, did, items, ctx.user['id'])
        # 明细为删除重建，取新明细 id 回填归集成员，避免成员明细 JOIN 失配
        new_item = q1(conn, """
            SELECT id, variety_id, grade FROM biz_demand_item WHERE demand_id=%s AND is_deleted=0 ORDER BY id LIMIT 1
            """, (did,))
        first = items[0] or {}
        new_qty = first.get('quantity')
        new_var = first.get('varietyId')
        new_grade = first.get('grade')
        m = q1(conn, """
            SELECT m.id AS mid, m.agg_id, a.status, a.variety_id, a.grade
            FROM biz_aggregated_order_item m
            JOIN biz_aggregated_order a ON a.id=m.agg_id AND a.is_deleted=0
            WHERE m.demand_id=%s AND m.is_deleted=0 LIMIT 1
            """, (did,))
        if m:
            if m['status'] != 'OPEN':
                raise ApiError(40901, '归集订单已进入询价流程，无法应用变更')
            str_new_var = str(new_var) if new_var is not None else None
            # 比较归集口径（同品种同品位）是否被破坏
            from decimal import Decimal
            grade_changed = (old_item and new_grade is not None and
                             Decimal(str(new_grade)) != Decimal(str(old_item['grade'])))
            var_changed = (old_item and str_new_var and str_new_var != str(old_item['variety_id']))
            if var_changed or grade_changed:
                # 品类/品位变更：移出原归集单（可重新归集），总吨数重算
                execute(conn, "UPDATE biz_aggregated_order_item SET is_deleted=1 WHERE id=%s", (m['mid'],))
                execute(conn, """
                    UPDATE biz_aggregated_order a SET
                        total_qty=(SELECT COALESCE(SUM(quantity),0) FROM biz_aggregated_order_item
                                   WHERE agg_id=a.id AND is_deleted=0),
                        updated_at=now() WHERE id=%s
                    """, (m['agg_id'],))
                return 'MOVED_OUT_OF_AGG'
            if new_qty is not None:
                # 同步成员份额与归集总吨数；成员明细指向新重建的明细行，归集锁定量随新数量重算
                execute(conn, """
                    UPDATE biz_aggregated_order_item SET demand_item_id=%s, quantity=%s WHERE id=%s
                    """, (new_item['id'], new_qty, m['mid']))
                execute(conn, """
                    UPDATE biz_demand_item SET inquired_qty=%s, updated_at=now()
                    WHERE demand_id=%s AND is_deleted=0
                    """, (new_qty, did))
                execute(conn, """
                    UPDATE biz_aggregated_order a SET
                        total_qty=(SELECT COALESCE(SUM(quantity),0) FROM biz_aggregated_order_item
                                   WHERE agg_id=a.id AND is_deleted=0),
                        updated_at=now() WHERE id=%s
                    """, (m['agg_id'],))
                return 'AGG_RESYNCED'
        return 'DEMAND_UPDATED'
    return 'DEMAND_UPDATED'


def _chg_date(v):
    from ..common import parse_date as _pd
    if not v:
        return None
    try:
        return _pd({'expectArriveStart': v}, 'expectArriveStart')
    except Exception:
        return None


# ---------- 归集订单：多钢厂同品种同品位需求合并 ----------
@bp.get('/admin/aggregated-orders')
@plat_required
def aggregated_orders():
    """归集列表（含参与钢厂、关联询价状态）。?kind=ORDER 仅一次性订单归集（订单归集页）；kind=DEMAND 仅月度/季度计划归集（需求归集页）。"""
    params = get_params()
    page, size = page_args(params)
    where = 'WHERE a.is_deleted=0'
    args = []
    if params.get('status'):
        where += ' AND a.status=%s'
        args.append(params['status'])
    if params.get('kind') in ('ORDER', 'DEMAND'):
        where += ' AND a.agg_kind=%s'
        args.append(params['kind'])
    total = q1(g.conn, 'SELECT count(*) AS c FROM biz_aggregated_order a ' + where, args)['c']
    rows = qall(g.conn, """
        SELECT a.id, a.agg_no AS "aggNo", a.variety_id AS "varietyId",
               v.variety_name AS "varietyName", v.category,
               a.grade, a.total_qty AS "totalQty", a.status, a.remark,
               a.agg_kind AS "aggKind", a.cycle_type AS "cycleType",
               a.cycle_year AS "cycleYear", a.cycle_value AS "cycleValue",
               a.created_at AS "createdAt", a.pushed_at AS "pushedAt",
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
                 WHERE i.agg_id=a.id AND i.is_deleted=0 ORDER BY i.id DESC LIMIT 1) AS "inquiryStatus",
               (SELECT i.sent_at FROM biz_inquiry i
                 WHERE i.agg_id=a.id AND i.is_deleted=0 ORDER BY i.id DESC LIMIT 1) AS "inquirySentAt"
        FROM biz_aggregated_order a
        JOIN base_variety v ON v.id=a.variety_id
        %s ORDER BY a.id DESC LIMIT %%s OFFSET %%s
        """ % where, args + [size, (page - 1) * size])
    return ok(page_data(rows, total, page, size))


@bp.get('/admin/supplier-options')
@plat_required
def supplier_options():
    """推送供应商选择列表：全部准入且启用的供应商（id + 名称）。"""
    rows = qall(g.conn, """
        SELECT id, company_name AS "companyName" FROM ent_company
        WHERE position('SUPPLIER' in company_types) > 0
          AND audit_status='APPROVED' AND status='ENABLED' AND is_deleted=0
        ORDER BY company_name
    """)
    return ok({'list': rows})


@bp.post('/admin/aggregated-orders/push')
@plat_required
def push_aggregated_orders():
    """推送需求归集：勾选的月度/季度归集单推送给所选供应商（不选=全部准入供应商），采购参考非询价。"""
    p = get_params()
    ids = p.get('ids') or []
    if not isinstance(ids, list) or not ids:
        raise ApiError(40001, '请先勾选要推送的需求归集单')
    rows = qall(g.conn, """
        SELECT a.id, a.agg_no, a.agg_kind, a.pushed_at, a.total_qty,
               v.variety_name, a.grade
        FROM biz_aggregated_order a JOIN base_variety v ON v.id=a.variety_id
        WHERE a.id = ANY(%s) AND a.is_deleted=0
        """, ([int(i) for i in ids],))
    if len(rows) != len(set(int(i) for i in ids)):
        raise ApiError(40401, '部分需求归集单不存在')
    for r in rows:
        if r['agg_kind'] != 'DEMAND':
            raise ApiError(40001, '仅月度/季度需求归集（%s）可推送，一次性订单归集走询价流程' % r['agg_no'])
    sup_all = qall(g.conn, """
        SELECT id FROM ent_company
        WHERE position('SUPPLIER' in company_types) > 0
          AND audit_status='APPROVED' AND status='ENABLED' AND is_deleted=0
    """)
    req_ids = [int(i) for i in (p.get('supplierIds') or [])]
    if req_ids:
        allowed = {r['id'] for r in sup_all}
        bad = set(req_ids) - allowed
        if bad:
            raise ApiError(40001, '所选供应商中有 %d 家不存在或未准入启用' % len(bad))
        sups = [r for r in sup_all if r['id'] in set(req_ids)]
    else:
        sups = sup_all
    if not sups:
        raise ApiError(40901, '请选择要推送的供应商')
    for r in rows:
        execute(g.conn, """
            UPDATE biz_aggregated_order SET pushed_at=now(), pushed_by=%s, updated_by=%s,
                   updated_at=now() WHERE id=%s
            """, (g.ctx.user['id'], g.ctx.user['id'], r['id']))
        for s in sups:
            send_msg(g.conn, s['id'], '需求归集推送',
                     '运营平台推送需求归集 %s（%s，品位 %s%%，%s 湿吨），'
                     '详情请至「需求归集」菜单查看，可作为采购参考。'
                     % (r['agg_no'], r['variety_name'], r['grade'],
                        r['total_qty'].quantize(Decimal('0.01'))),
                     'NOTICE', r['id'])
        op_log(g.conn, g.ctx, 'biz_aggregated_order', r['id'], 'PUSH', None,
               {'suppliers': [s['id'] for s in sups]})
    return ok({'pushed': len(rows), 'suppliers': len(sups)})


@bp.get('/admin/aggregated-orders/<int:aid>')
@plat_required
def aggregated_order_detail(aid):
    """归集详情：成员明细（钢厂 × 需求 × 份额）。"""
    a = q1(g.conn, """
        SELECT a.id, a.agg_no AS "aggNo", a.variety_id AS "varietyId", a.grade,
               a.total_qty AS "totalQty", a.status, a.remark,
               a.agg_kind AS "aggKind", a.cycle_type AS "cycleType",
               a.cycle_year AS "cycleYear", a.cycle_value AS "cycleValue",
               a.created_at AS "createdAt", a.created_by AS "createdBy",
               v.variety_name AS "varietyName", v.category
        FROM biz_aggregated_order a JOIN base_variety v ON v.id=a.variety_id
        WHERE a.id=%s AND a.is_deleted=0
        """, (aid,))
    if not a:
        raise ApiError(40401, '归集订单不存在')
    members = qall(g.conn, """
        SELECT m.id, m.company_id AS "companyId", c.company_name AS "companyName",
               d.demand_no AS "demandNo", d.demand_name AS "demandName",
               d.expect_arrive_start AS "expectArriveStart", d.expect_arrive_end AS "expectArriveEnd",
               v.variety_name AS "varietyName", di.grade, m.quantity,
               di.cycle_type AS "cycleType", di.cycle_year AS "cycleYear", di.cycle_value AS "cycleValue",
               di.quantity AS "itemQty", di.inquired_qty AS "inquiredQty",
               x.inquiry_no AS "inquiryNo", x.status AS "inquiryStatus", x.id AS "inquiryId"
        FROM biz_aggregated_order_item m
        JOIN ent_company c ON c.id=m.company_id
        JOIN biz_demand d ON d.id=m.demand_id
        JOIN biz_demand_item di ON di.id=m.demand_item_id
        JOIN base_variety v ON v.id=di.variety_id
        LEFT JOIN biz_inquiry x ON x.id=m.inquiry_id AND x.is_deleted=0
        WHERE m.agg_id=%s AND m.is_deleted=0 ORDER BY m.id
        """, (aid,))
    return ok({'order': json_payload(a), 'members': json_payload(members)})


def _agg_from_inquiries(p, inquiry_ids):
    """按钢厂询价单归集：勾选同品种同品位、已提交（SENT）的询价单 → 生成归集订单。

    成员明细 quantity = 询价单数量（量已在钢厂发单时锁减，此处不再重复锁量），
    并回链 inquiry_id；询价单转入「已归集」，总询价单定标后随之成单。
    """
    if not isinstance(inquiry_ids, list) or not inquiry_ids:
        raise ApiError(40001, '请至少选择一份询价单')
    xs = qall(g.conn, """
        SELECT x.id, x.inquiry_no, x.demand_id, x.demand_item_id, x.buyer_id,
               x.variety_id, x.grade, x.quantity, v.variety_name
        FROM biz_inquiry x JOIN base_variety v ON v.id=x.variety_id
        WHERE x.id = ANY(%s) AND x.is_deleted=0 AND x.source='STEEL' AND x.status='SENT'
        """, (inquiry_ids,))
    if len(xs) != len(set(inquiry_ids)):
        raise ApiError(40401, '部分询价单不存在或不可归集（仅「已发出」状态可归集）')
    base = xs[0]
    for x in xs:
        if x['variety_id'] != base['variety_id'] or x['grade'] != base['grade']:
            raise ApiError(40001, '仅同品种且同品位的询价单可合并归集（%s 品位不一致）' % x['variety_name'])
    total = sum(x['quantity'] for x in xs)
    aid = execute(g.conn, """
        INSERT INTO biz_aggregated_order (agg_no, variety_id, grade, total_qty, status, remark,
            created_by, updated_by)
        VALUES (%s, %s, %s, %s, 'OPEN', %s, %s, %s) RETURNING id
        """, (doc_no(g.conn, 'GJ'), base['variety_id'], base['grade'], total, p.get('remark'),
              g.ctx.user['id'], g.ctx.user['id']), returning_id=True)
    mills = {}
    for x in xs:
        execute(g.conn, """
            INSERT INTO biz_aggregated_order_item (agg_id, demand_id, demand_item_id, company_id,
                quantity, inquiry_id)
            VALUES (%s, %s, %s, %s, %s, %s)
            """, (aid, x['demand_id'], x['demand_item_id'], x['buyer_id'], x['quantity'], x['id']))
        transition(g.conn, g.ctx, 'biz_inquiry', '询价单', 'biz_inquiry', x['id'], 'AGGREGATED')
        mills[x['buyer_id']] = x['variety_name']
    # 需求状态：仅在仍为「已提交」时转入询价中（询价单发出时通常已转）
    for did in {x['demand_id'] for x in xs}:
        drow = q1(g.conn, "SELECT status FROM biz_demand WHERE id=%s AND is_deleted=0", (did,))
        if drow and drow['status'] == 'SUBMITTED':
            transition(g.conn, g.ctx, 'biz_demand', '需求单', 'biz_demand', did, 'INQUIRING')
    agg_no = q1(g.conn, "SELECT agg_no FROM biz_aggregated_order WHERE id=%s", (aid,))['agg_no']
    for cid in mills:
        send_msg(g.conn, cid, '询价单已纳入归集订单',
                 '贵司询价单已由平台归集（归集订单 %s，合计 %.3f 湿吨），将统一向供应商发出总询价，报价汇总后推送贵司。'
                 % (agg_no, float(total)), 'DEMAND', xs[0]['demand_id'])
    op_log(g.conn, g.ctx, 'biz_aggregated_order', aid, 'CREATE', None,
           {'inquiryIds': inquiry_ids, 'totalQty': str(total)})
    return ok({'id': aid, 'aggNo': agg_no, 'totalQty': float(total)})


@bp.post('/admin/aggregated-orders')
@plat_required
def create_aggregated_order():
    """合并归集：勾选多份已提交需求中同品种同品位的明细 → 生成归集订单并锁定量。

    一次性订单明细归集为「订单归集」（agg_kind=ORDER）；月度/季度计划归集为「需求归集」
    （agg_kind=DEMAND，须申报周期一致），两类不可混合。明细数据带 agg_kind 返回，前端据此分流展示。
    传 aggId 时并入指定未询价（OPEN）归集单（品种品位/周期分组须一致），否则生成新归集单。
    """
    p = get_params()
    inquiry_ids = p.get('inquiryIds')
    if inquiry_ids:
        return _agg_from_inquiries(p, inquiry_ids)
    require_fields(p, 'itemIds')
    item_ids = p['itemIds']
    if not isinstance(item_ids, list) or not item_ids:
        raise ApiError(40001, '请至少选择一条需求明细')
    target = None
    if p.get('aggId'):
        try:
            target_id = int(p['aggId'])
        except (TypeError, ValueError):
            raise ApiError(40001, 'aggId 数值格式错误')
        target = q1(g.conn, "SELECT * FROM biz_aggregated_order WHERE id=%s AND is_deleted=0", (target_id,))
        if not target:
            raise ApiError(40401, '目标归集订单不存在')
        if target['status'] != 'OPEN':
            raise ApiError(40901, '目标归集订单已发起询价（%s），不可并入' % target['status'])
    items = qall(g.conn, """
        SELECT i.id, i.demand_id, i.variety_id, i.grade, i.quantity, i.inquired_qty,
               COALESCE(i.deal_qty, 0) AS deal_qty,
               i.cycle_type, i.cycle_year, i.cycle_value,
               d.company_id, d.status AS demand_status, v.variety_name
        FROM biz_demand_item i
        JOIN biz_demand d ON d.id=i.demand_id
        JOIN base_variety v ON v.id=i.variety_id
        WHERE i.id = ANY(%s) AND i.is_deleted=0 AND d.is_deleted=0
        """, (item_ids,))
    if len(items) != len(set(item_ids)):
        raise ApiError(40401, '部分需求明细不存在')
    base = items[0]
    # 周期分组：一次性订单归集 →「订单归集」；月度/季度计划归集 →「需求归集」，两类不可混合
    # 注意：落库 agg_kind 必须是 ORDER（与列默认值/文档/订单归集列表过滤一致），ONE_TIME 是需求周期类型，不可直接落库
    kinds = {'ORDER' if it['cycle_type'] == 'ONE_TIME' or not it['cycle_type'] else 'DEMAND'
             for it in items}
    if len(kinds) > 1:
        raise ApiError(40001, '一次性订单与月度/季度计划不可混合归集，请分开勾选分别归集')
    kind = kinds.pop()  # ORDER=一次性订单归集；DEMAND=月度/季度计划归集
    cycles = {(it['cycle_type'], it['cycle_year'], it['cycle_value']) for it in items}
    if kind == 'DEMAND' and len(cycles) > 1:
        raise ApiError(40001, '月度/季度计划归集要求申报周期一致（同类型同年同月/季度），请分开勾选分别归集')
    cyc = cycles.pop() if kind == 'DEMAND' else (None, None, None)
    for it in items:
        if target and (it['variety_id'] != target['variety_id'] or it['grade'] != target['grade']):
            raise ApiError(40001, '明细与目标归集订单品种/品位不一致，不可并入')
        if target and target['agg_kind'] != kind:
            raise ApiError(40001, '明细与目标归集单周期分组不一致，不可并入')
        if target and kind == 'DEMAND' and (
                target['cycle_type'], target['cycle_year'], target['cycle_value']) != cyc:
            raise ApiError(40001, '明细与目标归集单申报周期不一致，不可并入')
        if it['variety_id'] != base['variety_id'] or it['grade'] != base['grade']:
            raise ApiError(40001, '仅同品种且同品位的明细可合并归集（%s 品位不一致）' % it['variety_name'])
        if it['demand_status'] != 'SUBMITTED':
            raise ApiError(40901, '需求单状态为 %s，不可归集（仅已提交状态可归集）' % it['demand_status'])
        if it['quantity'] - it['inquired_qty'] - it['deal_qty'] <= 0:
            raise ApiError(40901, '明细 %s 已无可归集量' % it['id'])
    # 可归集量 = 明细数量 - 在途询价锁定量 - 已成交吨数
    total = sum(it['quantity'] - it['inquired_qty'] - it['deal_qty'] for it in items)
    if target:
        aid = target['id']
    else:
        aid = execute(g.conn, """
            INSERT INTO biz_aggregated_order (agg_no, variety_id, grade, total_qty, status, remark,
                agg_kind, cycle_type, cycle_year, cycle_value, created_by, updated_by)
            VALUES (%s, %s, %s, %s, 'OPEN', %s, %s, %s, %s, %s, %s, %s) RETURNING id
            """, (doc_no(g.conn, 'GJ'), base['variety_id'], base['grade'], total, p.get('remark'),
                  kind, cyc[0], cyc[1], cyc[2],
                  g.ctx.user['id'], g.ctx.user['id']), returning_id=True)
    mills = {}
    for it in items:
        lock = it['quantity'] - it['inquired_qty'] - it['deal_qty']
        execute(g.conn, """
            INSERT INTO biz_aggregated_order_item (agg_id, demand_id, demand_item_id, company_id, quantity)
            VALUES (%s, %s, %s, %s, %s)
            """, (aid, it['demand_id'], it['id'], it['company_id'], lock))
        execute(g.conn, """
            UPDATE biz_demand_item SET inquired_qty=%s, updated_at=now() WHERE id=%s
            """, (it['inquired_qty'] + lock, it['id']))  # 归集锁定剩余全部可询量
        mills[it['company_id']] = it['variety_name']
    # 需求状态：一次性订单归集 → TO_INQUIRY（待询价：运营端向供应商推送询价后才转询价中）；
    # 月度/季度计划归集 → AGGREGATED（已归集：仅推送采购参考，不走询价）
    new_status = 'TO_INQUIRY' if kind == 'ORDER' else 'AGGREGATED'
    for did in {it['demand_id'] for it in items}:
        transition(g.conn, g.ctx, 'biz_demand', '需求单', 'biz_demand', did, new_status)
    agg_no = q1(g.conn, "SELECT agg_no FROM biz_aggregated_order WHERE id=%s", (aid,))['agg_no']
    for cid, vname in mills.items():
        send_msg(g.conn, cid, '需求已纳入归集订单',
                 '贵司 %s 需求已由平台归集（归集订单 %s，合计 %.3f 湿吨），将统一向供应商询价，报价汇总后推送贵司。'
                 % (vname, agg_no, float(total)), 'DEMAND', items[0]['demand_id'])
    if target:
        # 并入已有归集单：总吨数重算为全部有效成员之和
        execute(g.conn, """
            UPDATE biz_aggregated_order a SET
                total_qty=(SELECT COALESCE(SUM(quantity),0) FROM biz_aggregated_order_item
                           WHERE agg_id=a.id AND is_deleted=0),
                updated_by=%s, updated_at=now() WHERE id=%s
            """, (g.ctx.user['id'], aid))
    total_after = q1(g.conn, "SELECT total_qty FROM biz_aggregated_order WHERE id=%s", (aid,))['total_qty']
    op_log(g.conn, g.ctx, 'biz_aggregated_order', aid, 'MERGE_INTO' if target else 'CREATE', None,
           {'itemIds': item_ids, 'totalQty': str(total_after)})
    return ok({'id': aid, 'aggNo': agg_no, 'totalQty': float(total_after), 'merged': bool(target),
               'kind': kind})


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
        if m.get('inquiry_id'):
            # 按询价单归集的成员：退回询价单至「已发出」（锁定量仍由询价单持有，不重复释放）
            transition(g.conn, g.ctx, 'biz_inquiry', '询价单', 'biz_inquiry', m['inquiry_id'], 'SENT')
        else:
            execute(g.conn, """
                UPDATE biz_demand_item SET inquired_qty = inquired_qty - %s, updated_at=now()
                WHERE id=%s
                """, (m['quantity'], m['demand_item_id']))
        active = q1(g.conn, """
            SELECT count(*) AS c FROM biz_inquiry
            WHERE is_deleted=0 AND status IN ('DRAFT','SENT','QUOTING')
              AND (demand_id=%s OR (agg_id IS NOT NULL AND agg_id <> %s AND agg_id IN (
                    SELECT DISTINCT agg_id FROM biz_aggregated_order_item
                    WHERE demand_id=%s AND is_deleted=0)))
            """, (m['demand_id'], aid, m['demand_id']))['c']
        drow = q1(g.conn, "SELECT id, status FROM biz_demand WHERE id=%s", (m['demand_id'],))
        if not active and drow and drow['status'] in ('INQUIRING', 'TO_INQUIRY', 'AGGREGATED'):
            transition(g.conn, g.ctx, 'biz_demand', '需求单', 'biz_demand', m['demand_id'], 'SUBMITTED')
    transition(g.conn, g.ctx, 'biz_aggregated_order', '归集订单', 'biz_aggregated_order', aid, 'CLOSED')
    for m in members:
        send_msg(g.conn, m['company_id'], '归集订单已关闭',
                 '归集订单 %s 已关闭，贵司需求份额量已释放，可继续等待归集或被单独询价。' % a['agg_no'],
                 'DEMAND', m['demand_id'])
    op_log(g.conn, g.ctx, 'biz_aggregated_order', aid, 'CLOSE', None,
           {'members': len(members)})
    return ok({'id': aid, 'status': 'CLOSED'})


def _release_agg_member(conn, ctx, mid, agg_id, quantity, demand_item_id):
    """移出单条归集成员：删成员行、释放明细锁定量、重算归集总吨数（成员清空则关闭归集单）。"""
    execute(conn, "UPDATE biz_aggregated_order_item SET is_deleted=1 WHERE id=%s", (mid,))
    execute(conn, """
        UPDATE biz_demand_item SET inquired_qty = GREATEST(inquired_qty - %s, 0), updated_at=now()
        WHERE id=%s
        """, (quantity, demand_item_id))
    remain = q1(conn, """
        SELECT count(*) AS c, COALESCE(SUM(quantity), 0) AS t
        FROM biz_aggregated_order_item WHERE agg_id=%s AND is_deleted=0
        """, (agg_id,))
    if remain['c']:
        execute(conn, "UPDATE biz_aggregated_order SET total_qty=%s, updated_at=now() WHERE id=%s",
                (remain['t'], agg_id))
    else:
        transition(conn, ctx, 'biz_aggregated_order', '归集订单', 'biz_aggregated_order', agg_id, 'CLOSED')
    return remain


@bp.put('/admin/aggregated-orders/<int:aid>/items/<int:mid>/cancel')
@plat_required
def cancel_aggregated_item(aid, mid):
    """取消归集（仅未询价 OPEN 归集单、非按询价单归集的成员）：单条需求份额移出归集。

    释放该明细锁定量，需求无其他在途询价/归集时回退至「已提交」（未归集前状态，
    可重新合并归集）；归集单成员清空后自动关闭。
    """
    a = q1(g.conn, "SELECT * FROM biz_aggregated_order WHERE id=%s AND is_deleted=0", (aid,))
    if not a:
        raise ApiError(40401, '归集订单不存在')
    if a['status'] != 'OPEN':
        raise ApiError(40901, '归集订单已发起询价（%s），不可取消成员' % a['status'])
    m = q1(g.conn, """
        SELECT * FROM biz_aggregated_order_item WHERE id=%s AND agg_id=%s AND is_deleted=0
        """, (mid, aid))
    if not m:
        raise ApiError(40401, '参与明细不存在')
    if m.get('inquiry_id'):
        raise ApiError(40901, '该份额由钢厂询价单归集而来，不可单独移出（请关闭归集订单）')
    remain = _release_agg_member(g.conn, g.ctx, mid, aid, m['quantity'], m['demand_item_id'])
    agg_closed = remain['c'] == 0
    # 需求回退：无其他 OPEN 归集成员、无在途询价时 待询价/询价中 → SUBMITTED（未归集前状态）
    other = q1(g.conn, """
        SELECT count(*) AS c FROM biz_aggregated_order_item m2
        JOIN biz_aggregated_order a2 ON a2.id=m2.agg_id AND a2.is_deleted=0 AND a2.status='OPEN'
        WHERE m2.demand_id=%s AND m2.id<>%s AND m2.is_deleted=0
        """, (m['demand_id'], mid))['c']
    active_inq = q1(g.conn, """
        SELECT count(*) AS c FROM biz_inquiry
        WHERE is_deleted=0 AND status IN ('DRAFT','SENT','QUOTING') AND demand_id=%s
        """, (m['demand_id'],))['c']
    drow = q1(g.conn, "SELECT id, status FROM biz_demand WHERE id=%s", (m['demand_id'],))
    if not other and not active_inq and drow and drow['status'] in ('INQUIRING', 'TO_INQUIRY', 'AGGREGATED'):
        transition(g.conn, g.ctx, 'biz_demand', '需求单', 'biz_demand', m['demand_id'], 'SUBMITTED')
    send_msg(g.conn, m['company_id'], '需求已移出归集订单',
             '贵司需求已由平台移出归集订单 %s（份额 %.3f 湿吨已释放），需求回到已提交状态，可等待重新归集。'
             % (a['agg_no'], float(m['quantity'])), 'DEMAND', m['demand_id'])
    op_log(g.conn, g.ctx, 'biz_aggregated_order', aid, 'CANCEL_MEMBER', None,
           {'itemId': mid, 'demandId': m['demand_id'], 'qty': str(m['quantity']),
            'remainQty': str(remain['t']), 'aggClosed': agg_closed})
    return ok({'id': mid, 'remainQty': float(remain['t']), 'aggClosed': agg_closed})


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
    require_fields(p, 'aggOrderId', 'arriveDate', 'inviteSupplierIds')
    supplier_ids = p['inviteSupplierIds']
    if not supplier_ids:
        raise ApiError(40001, '至少邀请一家供应商')
    _check_invites(supplier_ids)
    arrive = parse_date(p, 'arriveDate')
    # 报价截止由平台自动设定：期望到货日前 7 天 18:00，下限当前 +2 小时
    deadline = _auto_deadline(arrive)
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
            raise ApiError(40901, '该归集订单存在进行中的询价，请等待询价汇总/截止后再发起')
    batch_no = doc_no(g.conn, 'PC')
    iid = create_and_send_agg_inquiry(g.conn, agg, g.ctx.user['id'], arrive, deadline,
                                      min_response, supplier_ids, batch_no, p.get('remark'))
    if agg['status'] == 'OPEN':
        transition(g.conn, g.ctx, 'biz_aggregated_order', '归集订单', 'biz_aggregated_order',
                   agg['id'], 'INQUIRING')
    # 向供应商推送询价：归集单内「待询价」需求转「询价中」
    for r in qall(g.conn, """
            SELECT DISTINCT m.demand_id AS did FROM biz_aggregated_order_item m
            WHERE m.agg_id=%s AND m.is_deleted=0
            """, (agg['id'],)):
        drow = q1(g.conn, "SELECT status FROM biz_demand WHERE id=%s AND is_deleted=0", (r['did'],))
        if drow and drow['status'] == 'TO_INQUIRY':
            transition(g.conn, g.ctx, 'biz_demand', '需求单', 'biz_demand', r['did'], 'INQUIRING')
    # 重新发起询价：该归集单下「反馈待处理」的旧询价单标记已处理（回退已截止）
    for r in qall(g.conn, """
            SELECT id FROM biz_inquiry WHERE agg_id=%s AND status='FEEDBACK' AND is_deleted=0
            """, (agg['id'],)):
        transition(g.conn, g.ctx, 'biz_inquiry', '询价单', 'biz_inquiry', r['id'], 'CLOSED')
    op_log(g.conn, g.ctx, 'biz_inquiry', iid, 'PLATFORM CREATE', None,
           {'batchNo': batch_no, 'aggId': agg['id'], 'aggNo': agg['agg_no'],
            'totalQty': str(agg['total_qty'])})
    return ok({'batchNo': batch_no, 'inquiryId': iid, 'aggNo': agg['agg_no']})


@bp.get('/admin/quote-history')
@plat_required
def quote_history_list():
    """询价历史（按轮次）：每轮询价单及其报价家数、钢厂反馈家数，用于追溯历史报价与反馈。"""
    params = get_params()
    page, size = page_args(params)
    where = "WHERE i.is_deleted=0 AND i.source='PLATFORM' AND i.agg_id IS NOT NULL"
    args = []
    total = q1(g.conn, 'SELECT count(*) AS c FROM biz_inquiry i ' + where, args)['c']
    rows = qall(g.conn, """
        SELECT i.id, i.inquiry_no AS "inquiryNo", i.batch_no AS "batchNo",
               a.agg_no AS "aggNo", v.variety_name AS "varietyName", i.grade, i.quantity,
               i.deadline, i.status, i.expect_arrive_date AS "expectArriveDate",
               i.inquiry_desc AS "inquiryDesc",
               to_char(i.sent_at, 'YYYY-MM-DD HH24:MI') AS "sentAt",
               (SELECT count(*) FROM biz_quote q
                 WHERE q.inquiry_id=i.id AND q.is_deleted=0 AND q.status <> 'REJECTED') AS "quoteCount",
               (SELECT count(*) FROM biz_agg_inquiry_feedback f
                 WHERE f.inquiry_id=i.id AND f.is_deleted=0) AS "feedbackCount"
        FROM biz_inquiry i
        LEFT JOIN biz_aggregated_order a ON a.id=i.agg_id
        LEFT JOIN base_variety v ON v.id=i.variety_id
        %s ORDER BY i.id DESC LIMIT %%s OFFSET %%s
        """ % where, args + [size, (page - 1) * size])
    return ok(page_data(rows, total, page, size))


@bp.get('/admin/quote-history/<int:iid>')
@plat_required
def quote_history_detail(iid):
    """单轮询价历史明细：本轮全部报价（含时间/状态）+ 本轮钢厂反馈。"""
    inq = q1(g.conn, """
        SELECT i.id, i.inquiry_no AS "inquiryNo", i.batch_no AS "batchNo",
               a.agg_no AS "aggNo", v.variety_name AS "varietyName", i.grade, i.quantity,
               i.delivery_place AS "deliveryPlace", i.deadline, i.status,
               i.inquiry_desc AS "inquiryDesc",
               to_char(i.sent_at, 'YYYY-MM-DD HH24:MI') AS "sentAt"
        FROM biz_inquiry i
        LEFT JOIN biz_aggregated_order a ON a.id=i.agg_id
        LEFT JOIN base_variety v ON v.id=i.variety_id
        WHERE i.id=%s AND i.is_deleted=0
        """, (iid,))
    if not inq:
        raise ApiError(40401, '询价单不存在')
    quotes = qall(g.conn, """
        SELECT q.id, q.quote_no AS "quoteNo", c.company_name AS "companyName",
               q.price, q.quantity, q.delivery_date AS "deliveryDate",
               q.pay_terms AS "payTerms", q.status, q.version,
               to_char(q.created_at, 'YYYY-MM-DD HH24:MI') AS "quotedAt"
        FROM biz_quote q JOIN ent_company c ON c.id=q.supplier_id
        WHERE q.inquiry_id=%s AND q.is_deleted=0 AND q.status <> 'REJECTED'
        ORDER BY q.price ASC
        """, (iid,))
    feedbacks = qall(g.conn, """
        SELECT f.decision, f.reason, c.company_name AS "companyName",
               to_char(f.created_at, 'YYYY-MM-DD HH24:MI') AS "createdAt"
        FROM biz_agg_inquiry_feedback f JOIN ent_company c ON c.id=f.company_id
        WHERE f.inquiry_id=%s AND f.is_deleted=0 ORDER BY f.id
        """, (iid,))
    return ok({'inquiry': inq, 'quotes': quotes, 'feedbacks': feedbacks})


def _do_platform_award(conn, ctx, iid, quote):
    """按份额定标核心（运营端手动定标与全员认可自动成单共用）。

    前置：PLATFORM 归集询价且状态 CLOSED、报价可定标、可供量覆盖成员份额总量。
    整张询价单锁货锁价生成 1 张聚合订单（buyer_id 为空），各钢厂份额写入
    biz_order_member，随后通知各钢厂提交提货计划、通知供应商已定标。
    """
    inq = q1(conn, """
        SELECT * FROM biz_inquiry
        WHERE id=%s AND is_deleted=0 AND source='PLATFORM' AND agg_id IS NOT NULL
        """, (iid,))
    if not inq:
        raise ApiError(40401, '归集询价单不存在')
    if inq['status'] != 'CLOSED':
        raise ApiError(40901, '询价单状态为 %s，需截止揭示后方可定标' % inq['status'])
    if not quote or quote['inquiry_id'] != iid:
        raise ApiError(40401, '报价不存在')
    if quote['status'] not in ('REVEALED', 'BARGAINING'):
        raise ApiError(40901, '报价状态为 %s，不可定标' % quote['status'])

    members = qall(conn, """
        SELECT d.company_id AS "companyId", MIN(d.id) AS "demandId",
               MIN(m.demand_item_id) AS "demandItemId",
               COALESCE(SUM(m.quantity), 0) AS share
        FROM biz_aggregated_order_item m
        JOIN biz_demand d ON d.id=m.demand_id AND d.is_deleted=0
        WHERE m.agg_id=%s AND m.is_deleted=0
        GROUP BY d.company_id ORDER BY d.company_id
        """, (inq['agg_id'],))
    if not members:
        raise ApiError(40001, '归集订单无成员钢厂，无法定标')
    total = sum((m['share'] for m in members), Decimal('0'))
    if total > quote['quantity']:
        raise ApiError(40001, '报价可供量 %.2f 湿吨不足定标总量 %.2f 湿吨' % (quote['quantity'], total))

    price = quote['price']
    deadline = datetime.now() + timedelta(hours=48)
    amount = (price * total).quantize(Decimal('0.01'))
    ono = doc_no(conn, 'DD')
    uid = ctx.user['id'] if ctx and ctx.user else None
    # 整单锁货锁价：只生成 1 张聚合订单（buyer_id 为空），参与钢厂写入成员明细
    oid = execute(conn, """
        INSERT INTO biz_order (order_no, inquiry_id, quote_id, demand_id, buyer_id, supplier_id,
            variety_id, grade, quantity, more_less_rate, unit_price, amount, price_basis,
            delivery_type, delivery_place, delivery_date, settle_type, quality_terms,
            confirm_deadline, status, created_by, updated_by)
        VALUES (%s,%s,%s,NULL,NULL,%s,%s,%s,%s,5,%s,%s,'WET',%s,%s,%s,%s,%s,%s,
                'PENDING_CONFIRM',%s,%s) RETURNING id
        """, (ono, iid, quote['id'], quote['supplier_id'],
              inq['variety_id'], inq['grade'], total, price, amount,
              inq['delivery_type'], inq['delivery_place'], quote['delivery_date'],
              inq['settle_type'], quote['quality_commit'], deadline,
              uid, uid), returning_id=True)
    for m in members:
        execute(conn, """
            INSERT INTO biz_order_member (order_id, company_id, demand_id, demand_item_id, quantity)
            VALUES (%s,%s,%s,%s,%s)
            """, (oid, m['companyId'], m['demandId'], m['demandItemId'], m['share']))

    transition(conn, ctx, 'biz_quote', '报价', 'biz_quote', quote['id'], 'WIN',
               node_biz_type='ORDER', node_code='AWARDED', node_biz_id=oid)
    for q in qall(conn, """
            SELECT id FROM biz_quote
            WHERE inquiry_id=%s AND id<>%s AND status IN ('REVEALED','BARGAINING') AND is_deleted=0
            """, (iid, quote['id'])):
        transition(conn, ctx, 'biz_quote', '报价', 'biz_quote', q['id'], 'LOSE')
    execute(conn, "UPDATE biz_bargain SET status='EXPIRED', updated_at=now() WHERE inquiry_id=%s AND status='PENDING'", (iid,))
    transition(conn, ctx, 'biz_inquiry', '询价单', 'biz_inquiry', iid, 'AWARDED',
               node_biz_type='ORDER', node_code='ORDER_CREATED', node_biz_id=oid)
    transition(conn, ctx, 'biz_aggregated_order', '归集订单', 'biz_aggregated_order',
               inq['agg_id'], 'AWARDED')

    # 成交回填：按成员明细累加 deal_qty 并释放归集锁定量（成交即占用）；
    # 需求全部明细成交则转「已成交」
    execute(conn, """
        UPDATE biz_demand_item di
        SET deal_qty = COALESCE(di.deal_qty, 0) + m.quantity,
            inquired_qty = GREATEST(COALESCE(di.inquired_qty, 0) - m.quantity, 0),
            updated_at = now()
        FROM biz_aggregated_order_item m
        WHERE m.agg_id=%s AND m.is_deleted=0 AND m.demand_item_id=di.id
        """, (inq['agg_id'],))
    # 按询价单归集的成员：来源钢厂询价单随总询价单定标成单（已归集 → 已定标）
    for r in qall(conn, """
            SELECT DISTINCT inquiry_id FROM biz_aggregated_order_item
            WHERE agg_id=%s AND is_deleted=0 AND inquiry_id IS NOT NULL
            """, (inq['agg_id'],)):
        transition(conn, ctx, 'biz_inquiry', '询价单', 'biz_inquiry', r['inquiry_id'], 'AWARDED')
    for drow in qall(conn, """
            SELECT d.id, d.status, SUM(di.quantity) AS qty, SUM(COALESCE(di.deal_qty, 0)) AS deal
            FROM biz_demand d
            JOIN biz_demand_item di ON di.demand_id=d.id AND di.is_deleted=0
            WHERE d.id IN (SELECT m.demand_id FROM biz_aggregated_order_item m
                            WHERE m.agg_id=%s AND m.is_deleted=0)
              AND d.is_deleted=0
            GROUP BY d.id, d.status
            """, (inq['agg_id'],)):
        if drow['status'] == 'INQUIRING' and drow['deal'] >= drow['qty']:
            transition(conn, ctx, 'biz_demand', '需求单', 'biz_demand', drow['id'], 'DEALT')

    ino = q1(conn, "SELECT inquiry_no FROM biz_inquiry WHERE id=%s", (iid,))['inquiry_no']
    for m in members:
        send_msg(conn, m['companyId'], '订单已生成',
                 '归集询价 %s 已定标，已生成订单 %s（贵司份额 %s 湿吨），供应商确认订单后请在「订单」页提交提货计划（开始提货日期、日提货吨数）。'
                 % (ino, ono, format(m['share'], '.3f')), 'ORDER', oid)
    send_msg(conn, quote['supplier_id'], '已定标，请确认订单',
             '归集询价 %s 已定标，已生成订单 %s（整单 %s 湿吨），请在 %s 前在「订单管理」完成订单确认，逾期未确认订单将自动取消。'
             % (ino, ono, format(total, '.3f'), deadline.strftime('%Y-%m-%d %H:%M')), 'ORDER', oid,
             need_action=True)
    op_log(conn, ctx, 'biz_order', oid, 'AWARD', None,
           {'quoteId': quote['id'], 'price': str(price), 'quantity': str(total),
            'members': len(members)})
    return {'orderId': oid, 'orderNo': ono, 'totalQty': str(total),
            'memberCount': len(members),
            'confirmDeadline': deadline.strftime('%Y-%m-%d %H:%M:%S')}


@bp.post('/admin/quote-inquiries/<int:iid>/award')
@plat_required
def platform_quote_award(iid):
    """按份额定标（归集询价）：整张询价单锁货锁价，只生成 1 张订单。

    归集询价 buyer_id 为空、份额归多家钢厂，钢厂端只读比价不可定标，
    因此由平台在此定标；钢厂全员认可后系统也会自动触发同一逻辑
    （见 inquiry.agg_inquiry_feedback），本接口用于兜底手动定标。
    """
    p = get_params()
    require_fields(p, 'quoteId')
    quote = q1(g.conn, "SELECT * FROM biz_quote WHERE id=%s AND is_deleted=0", (p['quoteId'],))
    return ok(_do_platform_award(g.conn, g.ctx, iid, quote))


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
               q.tax_type AS "taxType", q.freight_price AS "freightPrice",
               q.delivery_place AS "deliveryPlace", q.pay_terms AS "payTerms",
               q.quality_commit AS "qualityCommit", q.remark, q.valid_until AS "validUntil",
               q.status, q.version,
               q.variety_id AS "varietyId", qv.variety_name AS "varietyName",
               q.origin, q.grade,
               q.price_sign AS "priceSign", q.price_float AS "priceFloat"
        FROM biz_quote q JOIN ent_company c ON c.id=q.supplier_id
        LEFT JOIN base_variety qv ON qv.id=q.variety_id
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
                     '归集订单询价 %s 已汇总 %s 家供应商报价，并按贵司需求份额（%s 湿吨）拆分推送，请前往「询价报价」查看比价。'
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
               c.file_url AS "fileUrl", c.file_hash AS "fileHash",
               c.buyer_file_url AS "buyerFileUrl", c.buyer_sign_at AS "buyerSignAt",
               c.supplier_file_url AS "supplierFileUrl", c.supplier_sign_at AS "supplierSignAt",
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
    """合同归集：双方签署件齐备后，approve → 合同生效并入台账；否则退回上传方（附原因）。"""
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
    if not row.get('buyer_file_url') or not row.get('supplier_file_url'):
        raise ApiError(40901, '需方与供方合同扫描件未齐备，暂不可归集')
    approve = str(p['approve']).strip().upper()
    if approve in ('TRUE', '1'):
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
        text = '订单 %s 合同 %s 签署件已完成平台归集，合同已生效。' % (row['order_no'], row['contract_no'])
        send_msg(g.conn, row['buyer_id'], '合同已归集生效', text, 'CONTRACT', cid)
        send_msg(g.conn, row['supplier_id'], '合同已归集生效', text, 'CONTRACT', cid)
        op_log(g.conn, g.ctx, 'biz_contract', cid, 'CONSOLIDATE', None, {'result': 'CONFIRMED'})
        return ok({'id': cid, 'platStatus': 'CONFIRMED', 'status': 'EFFECTIVE'})
    # 退回：区分退回需方 / 退回供方
    if approve not in ('BUYER', 'SUPPLIER'):
        raise ApiError(40001, '归集结论不合法，请选择归集完成/退回需方/退回供方')
    remark = (p.get('remark') or '').strip()
    if not remark:
        raise ApiError(40001, '退回必须填写原因')
    to_company = row['buyer_id'] if approve == 'BUYER' else row['supplier_id']
    to_label = '需方' if approve == 'BUYER' else '供方'
    execute(g.conn, """
        UPDATE biz_contract SET plat_status='RETURNED', plat_remark=%s, updated_by=%s, updated_at=now()
        WHERE id=%s
        """, (remark, g.ctx.user['id'], cid))
    send_msg(g.conn, to_company, '合同扫描件被退回',
             '合同 %s 扫描件未通过平台核验（退回%s），原因：%s，请重新上传。'
             % (row['contract_no'], to_label, remark), 'CONTRACT', cid,
             need_action=True)
    op_log(g.conn, g.ctx, 'biz_contract', cid, 'RETURN(%s)' % to_label, None,
           {'remark': remark, 'to': approve})
    return ok({'id': cid, 'platStatus': 'RETURNED', 'returnTo': approve})


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
# ---------- 订单管理（集采订单：提货计划汇总 → 运输方案） ----------

def _admin_order_select():
    """订单管理列表/详情公共查询：订单基础字段 + 提货计划进度。"""
    return """
        SELECT o.id, o.order_no AS "orderNo",
               COALESCE((SELECT i2.inquiry_no FROM biz_inquiry i2
                          WHERE i2.agg_id=i.agg_id AND i2.is_deleted=0
                          ORDER BY i2.id LIMIT 1), a.agg_no, '') AS "inquiryNo",
               COALESCE(a.agg_no, '') AS "aggNo",
               v.variety_name AS "varietyName", o.grade,
               o.quantity AS "totalQty", o.more_less_rate AS "moreLessRate",
               o.unit_price AS "unitPrice", o.amount, o.price_basis AS "priceBasis",
               (SELECT q.freight_price FROM biz_quote q
                 WHERE q.id=o.quote_id AND q.is_deleted=0 LIMIT 1) AS "freightPrice",
               (SELECT q.tax_type FROM biz_quote q
                 WHERE q.id=o.quote_id AND q.is_deleted=0 LIMIT 1) AS "taxType",
               (SELECT q.price_sign FROM biz_quote q
                 WHERE q.id=o.quote_id AND q.is_deleted=0 LIMIT 1) AS "priceSign",
               (SELECT q.price_float FROM biz_quote q
                 WHERE q.id=o.quote_id AND q.is_deleted=0 LIMIT 1) AS "priceFloat",
               o.delivery_type AS "deliveryType", o.delivery_place AS "deliveryPlace",
               o.delivery_date AS "deliveryDate", o.settle_type AS "settleType",
               s.company_name AS "supplierName",
               (SELECT count(*) FROM biz_order_member m
                 WHERE m.order_id=o.id AND m.is_deleted=0) AS "millCount",
               (SELECT count(*) FROM biz_order_member m
                 WHERE m.order_id=o.id AND m.is_deleted=0 AND m.pickup_status='SUBMITTED') AS "pickupDoneCount",
               o.status, o.created_at AS "createdAt", o.confirm_deadline AS "confirmDeadline"
        FROM biz_order o
        JOIN base_variety v ON v.id=o.variety_id
        LEFT JOIN ent_company s ON s.id=o.supplier_id
        LEFT JOIN biz_inquiry i ON i.id=o.inquiry_id
        LEFT JOIN biz_aggregated_order a ON a.id=i.agg_id
    """


@bp.get('/admin/orders')
@plat_required
def admin_order_list():
    """订单管理列表（运营端）：支持分页 + 状态 + 订单号模糊查询。"""
    params = get_params()
    page, size = page_args(params)
    where, args = 'WHERE o.is_deleted=0', []
    if params.get('status'):
        where += ' AND o.status=%s'
        args.append(params['status'])
    kw = (params.get('keyword') or '').strip()
    if kw:
        where += ' AND o.order_no ILIKE %s'
        args.append('%' + kw + '%')
    total = q1(g.conn, 'SELECT count(*) AS c FROM biz_order o ' + where, args)['c']
    rows = qall(g.conn, _admin_order_select() + ' %s ORDER BY o.id DESC LIMIT %%s OFFSET %%s' % where,
                args + [size, (page - 1) * size])
    return ok(page_data(rows, total, page, size))


@bp.get('/admin/orders/<int:oid>')
@plat_required
def admin_order_detail(oid):
    """订单详情（运营端）：订单字段 + 参与钢厂提货计划明细与汇总。"""
    row = q1(g.conn, _admin_order_select() + ' WHERE o.id=%s AND o.is_deleted=0', (oid,))
    if not row:
        raise ApiError(40401, '订单不存在')
    members = qall(g.conn, """
        SELECT m.id, m.company_id AS "companyId", c.company_name AS "companyName",
               m.quantity, m.pickup_status AS "pickupStatus",
               m.pickup_start_date AS "pickupStartDate", m.daily_qty AS "dailyQty",
               m.pickup_remark AS "pickupRemark", m.submitted_at AS "submittedAt",
               m.finish_confirm_at AS "finishConfirmAt"
        FROM biz_order_member m JOIN ent_company c ON c.id=m.company_id
        WHERE m.order_id=%s AND m.is_deleted=0 ORDER BY m.id
        """, (oid,))
    data = json_payload(row)
    data['members'] = json_payload(members)
    data['pickupSummary'] = {
        'totalMills': len(members),
        'doneMills': sum(1 for m in members if m['pickupStatus'] == 'SUBMITTED'),
    }
    # 订单完成确认情况：供应商 + 各钢厂成员（传统单看需方行）
    fin = json_payload(q1(g.conn, """
        SELECT supplier_finish_confirm_at AS "supplierFinishConfirmAt",
               buyer_finish_confirm_at AS "buyerFinishConfirmAt",
               (SELECT c2.company_name FROM ent_company c2 WHERE c2.id=o.buyer_id) AS "buyerFinishName"
        FROM biz_order o WHERE o.id=%s
        """, (oid,)))
    data.update(fin or {})
    return ok(data)


@bp.get('/admin/logistics-orders')
@plat_required
def platform_logistics_orders():
    """调度订单列表（全部订单含已完成），带方案与运单概况。"""
    params = get_params()
    page, size = page_args(params)
    where = "WHERE o.is_deleted=0"
    total = q1(g.conn, 'SELECT count(*) AS c FROM biz_order o ' + where)['c']
    rows = qall(g.conn, """
        SELECT o.id, o.order_no AS "orderNo",
               COALESCE(b.company_name, mm.names, '多钢厂集采') AS "buyerName",
               s.company_name AS "supplierName", o.quantity,
               c.contract_no AS "contractNo",
               p.id AS "planId", p.plan_no AS "planNo", p.org_mode AS "orgMode",
               (SELECT q.delivery_place FROM biz_quote q
                 WHERE q.id=o.quote_id AND q.is_deleted=0 LIMIT 1) AS "startPlace",
               COALESCE((SELECT string_agg(DISTINCT d.delivery_place, '、') FROM biz_order_member m
                          JOIN biz_demand d ON d.id=m.demand_id AND d.is_deleted=0
                          WHERE m.order_id=o.id AND m.is_deleted=0 AND d.delivery_place IS NOT NULL),
                        o.delivery_place) AS "destPlace",
               (SELECT count(*) FROM biz_waybill w WHERE w.plan_id=p.id AND w.is_deleted=0 AND w.status<>'CANCELLED') AS "waybillCount",
               (SELECT coalesce(sum(w.plan_qty),0) FROM biz_waybill w WHERE w.plan_id=p.id AND w.is_deleted=0 AND w.status<>'CANCELLED') AS "plannedQty"
        FROM biz_order o
        LEFT JOIN ent_company b ON b.id=o.buyer_id
        LEFT JOIN LATERAL (
            SELECT string_agg(DISTINCT c2.company_name, '、') AS names
            FROM biz_order_member m
            JOIN ent_company c2 ON c2.id=m.company_id
            WHERE m.order_id=o.id
        ) mm ON TRUE
        JOIN ent_company s ON s.id=o.supplier_id
        LEFT JOIN biz_contract c ON c.order_id=o.id AND c.is_deleted=0 AND c.status='EFFECTIVE'
        LEFT JOIN biz_logistics_plan p ON p.order_id=o.id AND p.is_deleted=0
        %s ORDER BY o.id DESC LIMIT %%s OFFSET %%s
        """ % where, [size, (page - 1) * size])
    return ok(page_data(rows, total, page, size))


@bp.get('/admin/logistics-orders/<int:oid>')
@plat_required
def logistics_order_detail(oid):
    """订单物流详情：成员钢厂（含平台录入的货物信息）+ 分段运单轨迹节点（数据源同钢厂端物流服务）。"""
    order = q1(g.conn, """
        SELECT o.id, o.order_no AS "orderNo", o.quantity, o.status, o.grade,
               v.variety_name AS "varietyName",
               (SELECT c.company_name FROM ent_company c WHERE c.id=o.supplier_id) AS "supplierName",
               CASE WHEN (SELECT c.company_name FROM ent_company c WHERE c.id=o.buyer_id) IS NOT NULL
                    THEN (SELECT c.company_name FROM ent_company c WHERE c.id=o.buyer_id)
               ELSE COALESCE((SELECT string_agg(DISTINCT c2.company_name, '、')
                                FROM biz_order_member m JOIN ent_company c2 ON c2.id=m.company_id
                                WHERE m.order_id=o.id AND m.is_deleted=0), '平台集采')
          END AS "buyerName",
               p.id AS "planId", p.plan_no AS "planNo", p.org_mode AS "orgMode",
               p.remark AS "remark", p.rail_remark AS "railRemark",
               p.multimodal_remark AS "multimodalRemark", p.truck_remark AS "truckRemark",
               p.created_at AS "planCreatedAt",
               p.supp_total_qty AS "suppTotalQty", p.supp_shipped_qty AS "suppShippedQty",
               p.supp_transit_qty AS "suppTransitQty", p.supp_arrived_qty AS "suppArrivedQty",
               p.supp_pickup_qty AS "suppPickupQty", p.supp_cargo_at AS "suppCargoAt",
               (SELECT q.delivery_place FROM biz_quote q
                 WHERE q.id=o.quote_id AND q.is_deleted=0 LIMIT 1) AS "startPlace",
               COALESCE((SELECT string_agg(DISTINCT d.delivery_place, '、') FROM biz_order_member m
                          JOIN biz_demand d ON d.id=m.demand_id AND d.is_deleted=0
                          WHERE m.order_id=o.id AND m.is_deleted=0 AND d.delivery_place IS NOT NULL),
                        o.delivery_place) AS "destPlace"
        FROM biz_order o
        LEFT JOIN base_variety v ON v.id=o.variety_id
        LEFT JOIN biz_logistics_plan p ON p.order_id=o.id AND p.is_deleted=0
        WHERE o.id=%s AND o.is_deleted=0
        """, (oid,))
    if not order:
        raise ApiError(40401, '订单不存在')
    members = qall(g.conn, """
        SELECT m.company_id AS "companyId", c.company_name AS "companyName", m.quantity,
               cg.total_qty AS "totalQty", cg.shipped_qty AS "shippedQty",
               cg.transit_qty AS "transitQty", cg.arrived_qty AS "arrivedQty",
               cg.pickup_qty AS "pickupQty", cg.updated_at AS "cargoUpdatedAt"
        FROM biz_order_member m
        JOIN ent_company c ON c.id=m.company_id
        LEFT JOIN biz_member_cargo cg ON cg.order_id=m.order_id AND cg.company_id=m.company_id AND cg.is_deleted=0
        WHERE m.order_id=%s AND m.is_deleted=0
        ORDER BY m.id
        """, (oid,))
    if not members and order.get('buyer_id'):
        # 传统单钢厂订单：按需方合成成员行，货物信息同表存储
        buyer = q1(g.conn, "SELECT id, company_name FROM ent_company WHERE id=%s", (order['buyer_id'],))
        if buyer:
            members = [{'companyId': buyer['id'], 'companyName': buyer['company_name'],
                        'quantity': order['quantity'], 'totalQty': None, 'shippedQty': None,
                        'transitQty': None, 'arrivedQty': None, 'pickupQty': None, 'cargoUpdatedAt': None}]
    waybills = qall(g.conn, """
        SELECT w.id, w.waybill_no AS "waybillNo", w.segment_no AS "segmentNo",
               w.transport_mode AS "transportMode", w.transit_station AS "transitStation",
               w.depart_place AS "departPlace", w.arrive_place AS "arrivePlace",
               w.plan_qty AS "planQty", w.actual_qty AS "actualQty", w.vehicle_no AS "vehicleNo",
               w.plan_depart_date AS "planDepartDate", w.plan_arrive_date AS "planArriveDate",
               w.eta_at AS "etaPlan", w.actual_eta_at AS "etaActual",
               w.actual_depart_at AS "departAt", w.actual_transit_at AS "transitAt",
               w.actual_arrive_at AS "arriveAt", w.status, w.created_at AS "createdAt",
               w.node_draft AS "nodeDraft", w.node_log AS "nodeLog", o.order_no AS "orderNo",
               cr.company_name AS "carrierName"
        FROM biz_waybill w
        LEFT JOIN biz_order o ON o.id=w.order_id
        LEFT JOIN ent_company cr ON cr.id=w.carrier_id
        WHERE w.order_id=%s AND w.is_deleted=0 ORDER BY w.segment_no, w.id
        """, (oid,))
    for wb in waybills:
        try:
            wb['nodeLog'] = json.loads(wb['nodeLog']) if wb.get('nodeLog') else []
        except Exception:
            wb['nodeLog'] = []
    # 供应商货物信息（运营端录入，供应商端随录随更新）
    order['suppCargo'] = {
        'totalQty': order.get('suppTotalQty'), 'shippedQty': order.get('suppShippedQty'),
        'transitQty': order.get('suppTransitQty'), 'arrivedQty': order.get('suppArrivedQty'),
        'pickupQty': order.get('suppPickupQty'), 'updatedAt': order.get('suppCargoAt'),
    } if order.get('planId') else None
    return ok({'order': order, 'members': members, 'waybills': waybills})


@bp.put('/admin/logistics-orders/<int:oid>/members/<int:cid>/cargo')
@plat_required
def set_member_cargo(oid, cid):
    """运营端按钢厂录入货物信息（货物总量/出港/在途/到站/可提货）→ 钢厂端物流服务随 15 秒轮询自动更新。"""
    p = get_params()
    order = q1(g.conn, "SELECT id, order_no, buyer_id FROM biz_order WHERE id=%s AND is_deleted=0", (oid,))
    if not order:
        raise ApiError(40401, '订单不存在')
    member = q1(g.conn, """
        SELECT id FROM biz_order_member WHERE order_id=%s AND company_id=%s AND is_deleted=0
        """, (oid, cid))
    if not member and not (order['buyer_id'] and order['buyer_id'] == cid):
        raise ApiError(40401, '该订单下未找到此钢厂成员')
    company = q1(g.conn, "SELECT company_name FROM ent_company WHERE id=%s", (cid,))

    def _qty(key):
        v = p.get(key)
        if v in (None, ''):
            return None
        try:
            d = Decimal(str(v))
        except Exception:
            raise ApiError(40001, '货物信息项 %s 必须为数字' % key)
        if d < 0:
            raise ApiError(40001, '货物信息项 %s 不能为负数' % key)
        return d

    vals = [_qty(k) for k in ('totalQty', 'shippedQty', 'transitQty', 'arrivedQty', 'pickupQty')]
    execute(g.conn, """
        INSERT INTO biz_member_cargo (order_id, company_id, total_qty, shipped_qty, transit_qty, arrived_qty, pickup_qty, updated_by, updated_at)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,now())
        ON CONFLICT (order_id, company_id) DO UPDATE SET
          total_qty=EXCLUDED.total_qty, shipped_qty=EXCLUDED.shipped_qty, transit_qty=EXCLUDED.transit_qty,
          arrived_qty=EXCLUDED.arrived_qty, pickup_qty=EXCLUDED.pickup_qty,
          updated_by=EXCLUDED.updated_by, updated_at=now(), is_deleted=0
        """, [oid, cid] + vals + [g.ctx.user['id']])
    op_log(g.conn, g.ctx, 'biz_member_cargo', oid, 'SET_CARGO', None,
           {'company': company['company_name'] if company else cid, 'payload': p})
    # 保存不推送（推送门控）：运营端点「推送」后并入 MILL 发布快照，钢厂端才可见
    return ok({'saved': True})


@bp.put('/admin/logistics-orders/<int:oid>/supplier-cargo')
@plat_required
def set_supplier_cargo(oid):
    """运营端录入供应商货物信息（货物总量/出港/在途/到站/可提货）：每录入一次供应商端物流服务即自动更新。"""
    p = get_params()
    order = q1(g.conn, "SELECT id, order_no FROM biz_order WHERE id=%s AND is_deleted=0", (oid,))
    if not order:
        raise ApiError(40401, '订单不存在')
    plan = q1(g.conn, "SELECT id FROM biz_logistics_plan WHERE order_id=%s AND is_deleted=0", (oid,))
    if not plan:
        raise ApiError(40401, '该订单尚未制定物流方案，请先制定方案')

    def _qty(key):
        v = p.get(key)
        if v in (None, ''):
            return None
        try:
            dv = Decimal(str(v))
        except Exception:
            raise ApiError(40001, '货物信息项 %s 必须为数字' % key)
        if dv < 0:
            raise ApiError(40001, '货物信息项 %s 不能为负数' % key)
        return dv

    vals = [_qty(k) for k in ('totalQty', 'shippedQty', 'transitQty', 'arrivedQty', 'pickupQty')]
    execute(g.conn, """
        UPDATE biz_logistics_plan SET
          supp_total_qty=%s, supp_shipped_qty=%s, supp_transit_qty=%s,
          supp_arrived_qty=%s, supp_pickup_qty=%s, supp_cargo_at=now(), updated_at=now()
        WHERE id=%s
        """, vals + [plan['id']])
    op_log(g.conn, g.ctx, 'biz_logistics_plan', plan['id'], 'SUPPLIER_CARGO', None,
           {'order': oid, 'payload': p})
    return ok({'saved': True})


# ---------- 物流信息发布快照（推送门控） ----------
def _build_trace_snapshot(conn, oid):
    """构建物流轨迹发布快照：与钢厂端 tracking 运单列表同构（含节点录入轨迹日志 nodeLog）。"""
    wbs = qall(conn, """
        SELECT w.id, w.waybill_no AS "waybillNo", w.segment_no AS "segmentNo",
               w.transport_mode AS "transportMode", w.transit_station AS "transitStation",
               w.depart_place AS "departPlace", w.arrive_place AS "arrivePlace",
               w.plan_qty AS "planQty", w.freight, w.vehicle_no AS "vehicleNo",
               w.plan_depart_date AS "planDepartDate", w.plan_arrive_date AS "planArriveDate",
               w.eta_at AS "etaPlan", w.actual_eta_at AS "etaActual",
               w.actual_depart_at AS "departAt", w.actual_transit_at AS "transitAt",
               w.actual_arrive_at AS "arriveAt", w.status, w.created_at AS "createdAt",
               w.node_log AS "nodeLog",
               cr.company_name AS "carrierName"
        FROM biz_waybill w
        LEFT JOIN ent_company cr ON cr.id=w.carrier_id
        WHERE w.order_id=%s AND w.is_deleted=0 ORDER BY w.segment_no, w.id
        """, (oid,))
    items = json_payload(wbs)
    for it in items:
        try:
            it['nodeLog'] = json.loads(it['nodeLog']) if it.get('nodeLog') else []
        except Exception:
            it['nodeLog'] = []
    return items


def _cargo_of(conn, oid, cid=None):
    """读取平台录入的成员货物信息；cid 为空时按全部成员汇总（供应商端快照用）。"""
    if cid:
        return json_payload(q1(conn, """
            SELECT total_qty AS "totalQty", shipped_qty AS "shippedQty", transit_qty AS "transitQty",
                   arrived_qty AS "arrivedQty", pickup_qty AS "pickupQty", updated_at AS "cargoUpdatedAt"
            FROM biz_member_cargo WHERE order_id=%s AND company_id=%s AND is_deleted=0
            """, (oid, cid)))
    rows = qall(conn, """
        SELECT total_qty, shipped_qty, transit_qty, arrived_qty, pickup_qty, updated_at
        FROM biz_member_cargo WHERE order_id=%s AND is_deleted=0
        """, (oid,))

    def _sum(k):
        vals = [r[k] for r in rows if r.get(k) is not None]
        return sum(vals) if vals else None

    upd = [r['updated_at'] for r in rows if r.get('updated_at')]
    return json_payload({
        'totalQty': _sum('total_qty'), 'shippedQty': _sum('shipped_qty'),
        'transitQty': _sum('transit_qty'), 'arrivedQty': _sum('arrived_qty'),
        'pickupQty': _sum('pickup_qty'), 'cargoUpdatedAt': max(upd) if upd else None,
    })


def _publish(oid, target, trace=None, cargo=None, plan=None):
    """写入发布快照（按字段合并）：trace=轨迹列表 / cargo=货物信息对象 / plan=运输方案对象；推送时间取 now()。"""
    row = q1(g.conn, "SELECT trace_json, cargo_json, plan_json FROM biz_logistics_publish WHERE order_id=%s AND target=%s",
             (oid, target))

    def _merge(old, val):
        return json.dumps(val, ensure_ascii=False) if val is not None else old

    execute(g.conn, """
        INSERT INTO biz_logistics_publish (order_id, target, trace_json, cargo_json, plan_json, published_at, updated_at)
        VALUES (%s, %s, %s, %s, %s, now(), now())
        ON CONFLICT (order_id, target) DO UPDATE SET
          trace_json=EXCLUDED.trace_json, cargo_json=EXCLUDED.cargo_json, plan_json=EXCLUDED.plan_json,
          published_at=now(), updated_at=now()
        """, (oid, target,
              _merge(row['trace_json'] if row else None, trace),
              _merge(row['cargo_json'] if row else None, cargo),
              _merge(row['plan_json'] if row else None, plan)))


@bp.post('/admin/logistics-plans')
@plat_required
def platform_create_plan():
    """运营代钢厂制定物流方案（待制定运输方案/履约中），方案自动给到钢厂（站内消息 + 现有页面可见）。"""
    p = get_params()
    require_fields(p, 'orderId', 'orgMode')
    order = q1(g.conn, "SELECT * FROM biz_order WHERE id=%s AND is_deleted=0", (p['orderId'],))
    if not order:
        raise ApiError(40401, '订单不存在')
    if order['status'] not in ('PENDING_TRANSPORT', 'PERFORMING'):
        raise ApiError(40901, '仅待制定运输方案/履约中订单可制定物流方案（当前 %s）' % order['status'])
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
    # 集采聚合订单：方案制定后进入履约中；通知全部参与钢厂
    receivers = [order['buyer_id']] if order['buyer_id'] else [
        m['company_id'] for m in qall(g.conn,
            "SELECT company_id FROM biz_order_member WHERE order_id=%s AND is_deleted=0", (p['orderId'],))]
    for cid in receivers:
        send_msg(g.conn, cid, '物流方案已制定',
                 '订单 %s 平台已制定物流方案，贵司无需操作，可在履约跟踪查看进度。' % order['order_no'],
                 'ORDER', p['orderId'])
    if order['supplier_id']:
        send_msg(g.conn, order['supplier_id'], '物流方案已推送',
                 '订单 %s 平台已推送物流方案，请查看「物流服务」页面。' % order['order_no'], 'ORDER', p['orderId'])
    if order['status'] == 'PENDING_TRANSPORT':
        transition(g.conn, g.ctx, 'biz_order', '订单', 'biz_order', p['orderId'], 'PERFORMING',
                   node_biz_type='ORDER', node_code='PLAN_CONFIGURED')
    op_log(g.conn, g.ctx, 'biz_logistics_plan', pid, 'PLATFORM_CREATE', None, p)
    return ok({'planId': pid})


@bp.post('/admin/logistics-plans/<int:pid>/waybills')
@plat_required
def platform_create_waybill(pid):
    """运营代钢厂创建分段运单并匹配承运商（带 carrierId → 待接单；不带 → 待指派）。"""
    plan = q1(g.conn, """
        SELECT p.*, o.quantity AS order_qty, o.buyer_id, o.supplier_id, o.order_no
        FROM biz_logistics_plan p JOIN biz_order o ON o.id=p.order_id
        WHERE p.id=%s AND p.is_deleted=0 AND o.is_deleted=0
        """, (pid,))
    if not plan:
        raise ApiError(40401, '物流方案不存在')
    p = get_params()
    require_fields(p, 'segmentNo', 'transportMode')
    # 运输方式：铁路直达 / 公铁联运 / 汽运直达（数据库沿用 RAIL/MULTIMODAL/ROAD 编码）
    if p['transportMode'] not in ('RAIL', 'MULTIMODAL', 'ROAD'):
        raise ApiError(40001, '运输方式仅支持 铁路直达/公铁联运/汽运直达')
    depart = (p.get('departPlace') or '').strip() or None
    if depart and len(depart) > 50:
        raise ApiError(40001, '起始地不能超过 50 字')
    if (p.get('arrivePlace') or '').strip() and len(p['arrivePlace'].strip()) > 50:
        raise ApiError(40001, '目的地不能超过 50 字')
    # 计划量：未填写时自动取订单剩余可排量（新增分段运单仅需 分段号/运输方式/起始地/目的地）
    used = q1(g.conn, """
        SELECT coalesce(sum(plan_qty),0) AS t FROM biz_waybill
        WHERE order_id=%s AND is_deleted=0 AND status<>'CANCELLED'
        """, (plan['order_id'],))['t']
    plan_qty = p.get('planQty')
    if plan_qty is None:
        plan_qty = plan['order_qty'] - used
    if plan_qty <= 0:
        raise ApiError(40001, '运输量必须大于 0')
    seg_no = str(p['segmentNo'])
    if q1(g.conn, "SELECT id FROM biz_waybill WHERE plan_id=%s AND segment_no=%s AND is_deleted=0",
          (pid, seg_no)):
        raise ApiError(40902, '分段序号 %s 已存在' % seg_no)
    # 分段运输量不强制与订单量一致：允许多个分段自由排载，合计偏差仅记审计（不再强制填写偏差说明）
    new_total = used + plan_qty
    deviation = abs(new_total - plan['order_qty']) / plan['order_qty'] * 100
    carrier_id = p.get('carrierId')
    if carrier_id:
        _check_carrier(carrier_id)
    # 承运商端已下线：运单创建即确认生效，默认平台承担运输，直接进入待发运
    status = 'PENDING_DEPART'
    wid = execute(g.conn, """
        INSERT INTO biz_waybill (waybill_no, order_id, plan_id, segment_no, carrier_id, transport_mode,
            depart_place, transit_station, arrive_place, plan_depart_date, plan_arrive_date, plan_qty,
            eta_at, freight, vehicle_no, status, created_by, updated_by)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id
        """, (doc_no(g.conn, 'YD'), plan['order_id'], pid, seg_no, carrier_id,
              p['transportMode'], p.get('departPlace'), (p.get('transitStation') or '').strip() or None,
              p.get('arrivePlace'),
              parse_date(p, 'planDepartDate', required=False),
              parse_date(p, 'planArriveDate', required=False), plan_qty,
              parse_datetime(p, 'etaDate', required=False),
              p.get('freight'), p.get('vehicleNo'), status, g.ctx.user['id'], g.ctx.user['id']),
        returning_id=True)
    if deviation > 5:
        op_log(g.conn, g.ctx, 'biz_waybill', wid, 'DEVIATION', None,
               {'deviationRate': '%.2f%%' % deviation, 'reason': p.get('deviationReason')})
    # 集采聚合订单无单一需方，通知全部参与钢厂
    receivers = [plan['buyer_id']] if plan['buyer_id'] else [
        m['company_id'] for m in qall(g.conn,
            "SELECT company_id FROM biz_order_member WHERE order_id=%s AND is_deleted=0", (plan['order_id'],))]
    for cid in receivers:
        send_msg(g.conn, cid, '运单已安排',
                 '订单 %s 分段 %s 运单已创建，贵司无需操作，可在履约跟踪查看进度。' % (plan['order_no'], p['segmentNo']),
                 'ORDER', plan['order_id'])
    if plan['supplier_id']:
        send_msg(g.conn, plan['supplier_id'], '运单已安排',
                 '订单 %s 分段 %s 运单已创建，请查看「物流服务」页面。' % (plan['order_no'], p['segmentNo']),
                 'ORDER', plan['order_id'])
    op_log(g.conn, g.ctx, 'biz_waybill', wid, 'PLATFORM_CREATE', None,
           {'planQty': str(plan_qty), 'status': status})
    return ok({'id': wid, 'status': status, 'planTotalDeviation': '%.2f%%' % deviation})


@bp.post('/admin/logistics-plans/<int:pid>/push')
@plat_required
def push_supplier_plan(pid):
    """运营端「运输方案」板块推送供应商（推送门控）：保存三框运输说明 + 发布方案快照（供应商端自此可见方案内容）。"""
    p = get_params()
    plan = q1(g.conn, """
        SELECT p.id, p.plan_no, p.order_id, p.remark, p.rail_remark, p.multimodal_remark, p.truck_remark,
               o.supplier_id, o.order_no
        FROM biz_logistics_plan p JOIN biz_order o ON o.id=p.order_id
        WHERE p.id=%s AND p.is_deleted=0 AND o.is_deleted=0
        """, (pid,))
    if not plan:
        raise ApiError(40401, '物流方案不存在')
    if not plan['supplier_id']:
        raise ApiError(40001, '该订单无供方企业，无法推送')
    remark = (p.get('remark') or '').strip()
    rail = (p.get('railRemark') or '').strip()
    multi = (p.get('multimodalRemark') or '').strip()
    truck = (p.get('truckRemark') or '').strip()
    for label, v in (('铁路直达', rail), ('公铁联运', multi), ('汽运直达', truck), ('运输说明', remark)):
        if len(v) > 500:
            raise ApiError(40001, '%s不能超过 500 字' % label)
    # railRemark 为空时兼容旧版单框运输说明
    rail_eff = rail or remark
    if (rail_eff, multi, truck, remark) != (plan['rail_remark'] or '', plan['multimodal_remark'] or '',
                                            plan['truck_remark'] or '', plan['remark'] or ''):
        execute(g.conn, """
            UPDATE biz_logistics_plan SET remark=%s, rail_remark=%s, multimodal_remark=%s, truck_remark=%s,
                   updated_by=%s, updated_at=now() WHERE id=%s
            """, (remark or None, rail_eff or None, multi or None, truck or None, g.ctx.user['id'], pid))
        op_log(g.conn, g.ctx, 'biz_logistics_plan', pid, 'SET_REMARK', None,
               {'rail': rail_eff, 'multimodal': multi, 'truck': truck, 'remark': remark})
    # 发布运输方案快照（推送门控）：供应商端物流服务「运输方案」板块自此可见并随每次推送更新
    _publish(plan['order_id'], 'SUPPLIER', plan={
        'planNo': plan['plan_no'], 'rail': rail_eff or '', 'multimodal': multi or '',
        'truck': truck or '', 'remark': remark or '',
    })
    send_msg(g.conn, plan['supplier_id'], '运输方案已推送',
             '订单 %s 平台已推送运输方案（%s），请查看「物流服务」页面。'
             % (plan['order_no'], plan['plan_no']), 'ORDER', plan['order_id'])
    op_log(g.conn, g.ctx, 'biz_logistics_plan', pid, 'PUSH_SUPPLIER', None,
           {'orderNo': plan['order_no'], 'supplierId': plan['supplier_id']})
    return ok({'pushed': True, 'remark': remark or None})


@bp.post('/admin/logistics-orders/<int:oid>/members/<int:cid>/push')
@plat_required
def push_member_mill(oid, cid):
    """运营端向单个钢厂推送本厂货物信息（推送门控）：并入 MILL 发布快照 cargo_json，钢厂端自此可见。"""
    order = q1(g.conn, "SELECT id, order_no, buyer_id FROM biz_order WHERE id=%s AND is_deleted=0", (oid,))
    if not order:
        raise ApiError(40401, '订单不存在')
    member = q1(g.conn, """
        SELECT m.company_id, c.company_name
        FROM biz_order_member m JOIN ent_company c ON c.id=m.company_id
        WHERE m.order_id=%s AND m.company_id=%s AND m.is_deleted=0
        """, (oid, cid))
    if not member and not (order['buyer_id'] and order['buyer_id'] == cid):
        raise ApiError(40401, '该订单下无此钢厂成员')
    name = member['company_name'] if member else (
        q1(g.conn, "SELECT company_name FROM ent_company WHERE id=%s", (cid,)) or {}).get('company_name')
    # 并入 MILL 发布快照：{companyId: 本厂货物信息}（推送门控，钢厂端自此可见本厂货物信息）
    row = q1(g.conn, "SELECT cargo_json FROM biz_logistics_publish WHERE order_id=%s AND target='MILL'", (oid,))
    cargo_map = {}
    if row and row.get('cargo_json'):
        try:
            cargo_map = json.loads(row['cargo_json'])
        except Exception:
            cargo_map = {}
    if not isinstance(cargo_map, dict):
        cargo_map = {}
    cargo_map[str(cid)] = _cargo_of(g.conn, oid, cid)
    _publish(oid, 'MILL', cargo=cargo_map)
    send_msg(g.conn, cid, '货物信息已推送',
             '订单 %s 平台已推送最新货物信息，请查看「物流服务」页面。' % order['order_no'],
             'ORDER', oid)
    op_log(g.conn, g.ctx, 'biz_order_member', cid, 'PUSH_MEMBER', None,
           {'orderNo': order['order_no'], 'companyId': cid})
    return ok({'pushed': True, 'companyName': name})


@bp.post('/admin/logistics-orders/<int:oid>/push-mills')
@plat_required
def push_order_mills(oid):
    """运营端推送物流节点轨迹至钢厂端（推送门控）：生成 MILL 发布快照（轨迹），钢厂端物流服务自此可见；
    未推送前节点录入不对钢厂展示。归集聚合订单推全部成员钢厂，传统单（有明确需方）推需方钢厂；
    货物信息各厂不同，仍走成员行内的单独推送。"""
    order = q1(g.conn, """
        SELECT o.id, o.order_no, o.buyer_id, c.company_name AS "buyerName"
        FROM biz_order o LEFT JOIN ent_company c ON c.id = o.buyer_id
        WHERE o.id=%s AND o.is_deleted=0
        """, (oid,))
    if not order:
        raise ApiError(40401, '订单不存在')
    mills = qall(g.conn, """
        SELECT m.company_id, c.company_name
        FROM biz_order_member m JOIN ent_company c ON c.id=m.company_id
        WHERE m.order_id=%s AND m.is_deleted=0
        """, (oid,))
    if not mills:
        if not order['buyer_id']:
            raise ApiError(40001, '该订单暂无成员钢厂，无法推送')
        mills = [{'company_id': order['buyer_id'], 'company_name': order['buyerName']}]
    # 发布轨迹快照（推送门控）：钢厂端自此可见；之后再次节点录入需重新推送
    _publish(oid, 'MILL', trace=_build_trace_snapshot(g.conn, oid))
    for m in mills:
        send_msg(g.conn, m['company_id'], '物流节点轨迹已推送',
                 '订单 %s 平台已推送最新物流节点轨迹，请查看「物流服务」页面。' % order['order_no'],
                 'ORDER', oid)
    op_log(g.conn, g.ctx, 'biz_order', oid, 'PUSH_MILLS', None,
           {'orderNo': order['order_no'], 'mills': [m['company_name'] for m in mills]})
    return ok({'pushed': len(mills)})


@bp.post('/admin/logistics-orders/<int:oid>/push-supplier')
@plat_required
def push_order_supplier(oid):
    """运营端推送物流服务至供应商端（推送门控）：scope=TRACE 只推物流运输轨迹 / CARGO 只推货物信息 /
    ALL 整包（轨迹+货物汇总+运输方案）。写入 SUPPLIER 发布快照，供应商端物流服务随推送更新。"""
    order = q1(g.conn, "SELECT id, order_no, supplier_id FROM biz_order WHERE id=%s AND is_deleted=0", (oid,))
    if not order:
        raise ApiError(40401, '订单不存在')
    if not order['supplier_id']:
        raise ApiError(40001, '该订单无供方企业，无法推送')
    scope = str(get_params().get('scope') or 'ALL').upper()
    if scope not in ('TRACE', 'CARGO', 'ALL'):
        raise ApiError(40001, 'scope 仅支持 TRACE / CARGO / ALL')
    kwargs = {}
    if scope == 'TRACE':
        kwargs['trace'] = _build_trace_snapshot(g.conn, oid)
    elif scope == 'CARGO':
        kwargs['cargo'] = {'aggregate': _cargo_of(g.conn, oid)}
    else:
        plan = q1(g.conn, """
            SELECT plan_no, remark, rail_remark, multimodal_remark, truck_remark
            FROM biz_logistics_plan WHERE order_id=%s AND is_deleted=0
            """, (oid,))
        kwargs = {
            'trace': _build_trace_snapshot(g.conn, oid),
            'cargo': {'aggregate': _cargo_of(g.conn, oid)},
            'plan': {
                'planNo': plan['plan_no'] if plan else None,
                'rail': ((plan['rail_remark'] or plan['remark'] or '')) if plan else '',
                'multimodal': (plan['multimodal_remark'] or '') if plan else '',
                'truck': (plan['truck_remark'] or '') if plan else '',
                'remark': (plan['remark'] or '') if plan else '',
            },
        }
    msg = {'TRACE': '最新物流节点轨迹', 'CARGO': '最新货物信息',
           'ALL': '最新物流服务信息（轨迹、货物、运输方案）'}[scope]
    _publish(oid, 'SUPPLIER', **kwargs)
    send_msg(g.conn, order['supplier_id'], '物流服务信息已推送',
             '订单 %s 平台已推送%s，请查看「物流服务」页面。' % (order['order_no'], msg),
             'ORDER', oid)
    op_log(g.conn, g.ctx, 'biz_order', oid, 'PUSH_SUPPLIER', None,
           {'orderNo': order['order_no'], 'supplierId': order['supplier_id'], 'scope': scope})
    return ok({'pushed': True, 'scope': scope})


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
             '运单 %s 已指派给贵司，请接单确认。' % row['waybill_no'], 'WAYBILL', wid,
             need_action=True)
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
    # 通知对象：传统订单为需方；集采聚合订单（buyer_id 空）通知全部参与钢厂成员
    receivers = [order['buyer_id']] if order['buyer_id'] else [
        m['company_id'] for m in qall(g.conn,
            "SELECT company_id FROM biz_order_member WHERE order_id=%s AND is_deleted=0", (order['id'],))]
    p = get_params()
    require_fields(p, 'action')
    action = p['action']
    # 起讫编辑（自动填充、可修改）：随节点登记一并保存，或 action=PLACES 单独保存
    dp = (p.get('departPlace') or '').strip() or None
    ap = (p.get('arrivePlace') or '').strip() or None
    if dp is not None or ap is not None:
        if len(dp or '') > 100 or len(ap or '') > 100:
            raise ApiError(40001, '起运地/到达地不能超过 100 字')
        execute(g.conn, """
            UPDATE biz_waybill SET depart_place=COALESCE(%s, depart_place),
                   arrive_place=COALESCE(%s, arrive_place), updated_by=%s, updated_at=now()
            WHERE id=%s
            """, (dp, ap, g.ctx.user['id'], wid))
        op_log(g.conn, g.ctx, 'biz_waybill', wid, 'SET_PLACES', None,
               {'departPlace': dp, 'arrivePlace': ap})
    if action == 'PLACES':
        return ok({'saved': True})

    def _parse_dt(v):
        for f in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M'):
            try:
                return datetime.strptime(str(v).strip(), f)
            except Exception:
                continue
        return None

    cur_status = row['status']

    def _apply(code, occur):
        """登记单个节点（状态机校验 + 履约节点 + 站内通知），供单节点动作与统一提交复用。"""
        nonlocal cur_status
        if code == 'ETA':
            # 船到港登记：不改变运单状态，仅记录实际船到港时间并写履约节点
            if cur_status not in ('PENDING_DEPART', 'IN_TRANSIT'):
                raise ApiError(40901, '运单状态为 %s，不可登记船到港' % cur_status)
            execute(g.conn, """
                UPDATE biz_waybill SET actual_eta_at=%s, updated_by=%s, updated_at=now() WHERE id=%s
                """, (occur or datetime.now(), g.ctx.user['id'], wid))
            add_node(g.conn, g.ctx, 'WAYBILL', wid, 'WB_ETA_ARRIVED', occur=occur)
            for cid in receivers:
                send_msg(g.conn, cid, '船已到港',
                         '订单 %s 运单 %s 船已到港，待发运。' % (order['order_no'], row['waybill_no']),
                         'WAYBILL', wid)
        elif code == 'DEPART':
            if cur_status != 'PENDING_DEPART':
                raise ApiError(40901, '运单状态为 %s，不可发运' % cur_status)
            transition(g.conn, g.ctx, 'biz_waybill', '运单', 'biz_waybill', wid, 'IN_TRANSIT',
                       node_biz_type='WAYBILL', node_code='WB_DEPARTED')
            execute(g.conn, """
                UPDATE biz_waybill SET actual_depart_at=%s, actual_qty=%s, updated_by=%s, updated_at=now()
                WHERE id=%s
                """, (occur or datetime.now(), p.get('actualQty') or row['plan_qty'], g.ctx.user['id'], wid))
            for cid in receivers:
                send_msg(g.conn, cid, '运单已发运',
                         '订单 %s 运单 %s 已发运，可在履约跟踪查看在途节点。' % (order['order_no'], row['waybill_no']),
                         'WAYBILL', wid)
            cur_status = 'IN_TRANSIT'
        elif code == 'TRANSIT':
            # 到达中转站登记：不改变运单状态，仅记录实际到达中转站时间并写履约节点
            if cur_status != 'IN_TRANSIT':
                raise ApiError(40901, '运单状态为 %s，不可登记到达中转站' % cur_status)
            execute(g.conn, """
                UPDATE biz_waybill SET actual_transit_at=%s, updated_by=%s, updated_at=now() WHERE id=%s
                """, (occur or datetime.now(), g.ctx.user['id'], wid))
            add_node(g.conn, g.ctx, 'WAYBILL', wid, 'WB_ARRIVED_TRANSIT', occur=occur)
            for cid in receivers:
                send_msg(g.conn, cid, '已到达中转站',
                         '订单 %s 运单 %s 已到达中转站%s。' % (order['order_no'], row['waybill_no'],
                         ('「%s」' % row['transit_station']) if row['transit_station'] else ''),
                         'WAYBILL', wid)
        elif code == 'ARRIVE':
            if cur_status != 'IN_TRANSIT':
                raise ApiError(40901, '运单状态为 %s，不可到达' % cur_status)
            transition(g.conn, g.ctx, 'biz_waybill', '运单', 'biz_waybill', wid, 'ARRIVED',
                       node_biz_type='WAYBILL', node_code='WB_ARRIVED')
            execute(g.conn, """
                UPDATE biz_waybill SET actual_arrive_at=%s, updated_by=%s, updated_at=now() WHERE id=%s
                """, (occur, g.ctx.user['id'], wid))
            for cid in receivers:
                send_msg(g.conn, cid, '运单已到达',
                         '订单 %s 运单 %s 已到达，待签收。' % (order['order_no'], row['waybill_no']), 'WAYBILL', wid)
            cur_status = 'ARRIVED'
        elif code == 'SIGN':
            if cur_status != 'ARRIVED':
                raise ApiError(40901, '运单状态为 %s，不可签收' % cur_status)
            transition(g.conn, g.ctx, 'biz_waybill', '运单', 'biz_waybill', wid, 'SIGNED',
                       node_biz_type='WAYBILL', node_code='WB_SIGNED')
            execute(g.conn, """
                UPDATE biz_waybill SET actual_arrive_at=coalesce(actual_arrive_at, %s), updated_by=%s,
                    updated_at=now() WHERE id=%s
                """, (occur or datetime.now(), g.ctx.user['id'], wid))
            for cid in receivers:
                send_msg(g.conn, cid, '运单已签收',
                         '订单 %s 运单 %s 已签收。' % (order['order_no'], row['waybill_no']), 'WAYBILL', wid)
            send_msg(g.conn, order['supplier_id'], '运单已签收',
                     '订单 %s 运单 %s 已签收。' % (order['order_no'], row['waybill_no']), 'WAYBILL', wid)
            cur_status = 'SIGNED'
        else:
            raise ApiError(40001, 'action 仅支持 ETA/DEPART/TRANSIT/ARRIVE/SIGN')

    if action == 'DRAFT':
        # 保存节点草稿：仅记录不推进状态/不发通知；「统一提交」时按规范顺序补齐登记
        draft = p.get('draft')
        if not isinstance(draft, dict):
            raise ApiError(40001, '节点草稿格式错误')
        merged = {}
        if row.get('node_draft'):
            try:
                merged = json.loads(row['node_draft'])
            except Exception:
                merged = {}
        for k, v in draft.items():
            if str(k) in ('ETA', 'DEPART', 'TRANSIT', 'ARRIVE') and str(v).strip():
                merged[k] = str(v).strip()
        execute(g.conn, "UPDATE biz_waybill SET node_draft=%s, updated_by=%s, updated_at=now() WHERE id=%s",
                (json.dumps(merged, ensure_ascii=False), g.ctx.user['id'], wid))
        op_log(g.conn, g.ctx, 'biz_waybill', wid, 'WB_NODE_DRAFT', None, merged)
        return ok({'saved': True, 'draft': merged})

    if action == 'SUBMIT_DRAFT':
        # 统一提交：按 ETA→DEPART→TRANSIT→ARRIVE 顺序登记草稿节点；
        # 未填写的前置节点沿用其后第一个已填节点时间补齐（保证状态机顺序通过）
        try:
            draft = json.loads(row.get('node_draft') or '{}')
        except Exception:
            draft = {}
        if not isinstance(draft, dict) or not draft:
            raise ApiError(40001, '暂无已保存的节点信息，请先在节点录入中保存')
        NODE_COL = {'ETA': 'actual_eta_at', 'DEPART': 'actual_depart_at',
                    'TRANSIT': 'actual_transit_at', 'ARRIVE': 'actual_arrive_at'}
        ORDER = ['ETA', 'DEPART', 'TRANSIT', 'ARRIVE']
        pending = [c for c in ORDER if not row.get(NODE_COL[c]) and c in draft]
        if not pending:
            execute(g.conn, "UPDATE biz_waybill SET node_draft=NULL, updated_by=%s, updated_at=now() WHERE id=%s",
                    (g.ctx.user['id'], wid))
            raise ApiError(40001, '草稿节点均已登记，无需提交')
        last_idx = max(ORDER.index(c) for c in pending)
        applied = {}
        for i, code in enumerate(ORDER):
            if row.get(NODE_COL[code]):
                continue  # 已登记跳过
            t = _parse_dt(draft.get(code))
            if t is None and i <= last_idx:
                for c2 in ORDER[i:]:
                    if c2 in draft:
                        t = _parse_dt(draft[c2])
                        break
            if t is None:
                continue
            _apply(code, t)
            applied[code] = t.strftime('%Y-%m-%d %H:%M:%S')
        execute(g.conn, "UPDATE biz_waybill SET node_draft=NULL, updated_by=%s, updated_at=now() WHERE id=%s",
                (g.ctx.user['id'], wid))
        op_log(g.conn, g.ctx, 'biz_waybill', wid, 'PLATFORM_ADVANCE SUBMIT_DRAFT', None, applied)
        return ok({'id': wid, 'action': 'SUBMIT_DRAFT', 'applied': applied})

    occur = parse_datetime(p, 'occurTime', required=False)
    _apply(action, occur)
    op_log(g.conn, g.ctx, 'biz_waybill', wid, 'PLATFORM_ADVANCE %s' % action, None, p)
    return ok({'id': wid, 'action': action})


@bp.post('/admin/waybills/<int:wid>/trace-log')
@plat_required
def waybill_trace_log(wid):
    """节点录入追加物流轨迹（只增不改，每录一次新增一条）：写入 biz_waybill.node_log。"""
    row = q1(g.conn, "SELECT * FROM biz_waybill WHERE id=%s AND is_deleted=0", (wid,))
    if not row:
        raise ApiError(40401, '运单不存在')
    p = get_params()
    require_fields(p, 'desc', 'occurTime')
    occur = parse_datetime(p, 'occurTime', required=True)
    desc = (p.get('desc') or '').strip()
    loc = (p.get('loc') or '').strip() or None
    if len(desc) > 100:
        raise ApiError(40001, '节点描述不能超过 100 字')
    try:
        log = json.loads(row.get('node_log') or '[]')
    except Exception:
        log = []
    if not isinstance(log, list):
        log = []
    # 同一节点再次录入（时间不同）覆盖原记录，其余节点追加新条目
    occur_s = occur.strftime('%Y-%m-%d %H:%M:%S')
    desc_key = desc.replace('。', '')
    hit = next((e for e in log if isinstance(e, dict) and (e.get('desc') or '').replace('。', '') == desc_key), None)
    if hit:
        hit['loc'] = loc
        hit['occurTime'] = occur_s
        op_log(g.conn, g.ctx, 'biz_waybill', wid, 'TRACE_LOG_OVERWRITE', None,
               {'loc': loc, 'desc': desc, 'occurTime': occur_s})
    else:
        log.append({'loc': loc, 'desc': desc, 'occurTime': occur_s})
        op_log(g.conn, g.ctx, 'biz_waybill', wid, 'TRACE_LOG', None,
               {'loc': loc, 'desc': desc, 'occurTime': occur_s})
    execute(g.conn, "UPDATE biz_waybill SET node_log=%s, updated_by=%s, updated_at=now() WHERE id=%s",
            (json.dumps(log, ensure_ascii=False), g.ctx.user['id'], wid))
    return ok({'id': wid, 'traceCount': len(log), 'overwritten': bool(hit)})


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
               c.contract_no AS "contractNo", COALESCE(b.company_name, mm.names, '多钢厂集采') AS "buyerName",
               s.company_name AS "supplierName", w.segment_no AS "segmentNo",
               w.transport_mode AS "transportMode", w.depart_place AS "departPlace",
               w.transit_station AS "transitStation", w.arrive_place AS "arrivePlace",
               w.plan_depart_date AS "planDepartDate",
               w.plan_arrive_date AS "planArriveDate", w.plan_qty AS "planQty",
               w.eta_at AS "etaAt", w.actual_eta_at AS "actualEtaAt",
               w.actual_transit_at AS "actualTransitAt",
               w.freight, w.vehicle_no AS "vehicleNo",
               cr.company_name AS "carrierName", w.actual_depart_at AS "actualDepartAt",
               w.actual_arrive_at AS "actualArriveAt", w.status, w.created_at AS "createdAt",
               w.node_draft AS "nodeDraft"
        FROM biz_waybill w
        JOIN biz_order o ON o.id=w.order_id
        LEFT JOIN ent_company b ON b.id=o.buyer_id
        LEFT JOIN LATERAL (
            SELECT string_agg(DISTINCT c2.company_name, '、') AS names
            FROM biz_order_member m
            JOIN ent_company c2 ON c2.id=m.company_id
            WHERE m.order_id=o.id
        ) mm ON TRUE
        LEFT JOIN ent_company s ON s.id=o.supplier_id
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
        """, (p['varietyCode'], p['varietyName'], p.get('category'), grade, p.get('unit') or '湿吨',
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
        'monthOrders': count("SELECT count(*) AS c FROM biz_order WHERE is_deleted=0"
                             " AND status <> 'CANCELLED' AND created_at >= date_trunc('month', current_date)"),
        'companyPending': count("SELECT count(*) AS c FROM ent_company WHERE is_deleted=0 AND audit_status='PENDING'"),
        'orderActive': count("SELECT count(*) AS c FROM biz_order WHERE is_deleted=0 AND status NOT IN ('CANCELLED','COMPLETED')"),
        'orderTotal': count("SELECT count(*) AS c FROM biz_order WHERE is_deleted=0"),
        'alertPending': count("SELECT count(*) AS c FROM biz_alert WHERE is_deleted=0 AND status<>'CLOSED'"),
        'inquiryQuoting': count("SELECT count(*) AS c FROM biz_inquiry WHERE is_deleted=0 AND status IN ('SENT','QUOTING')"),
    })


@bp.get('/admin/dashboard/charts')
@plat_required
def dashboard_charts():
    """运营看板图表：货运趋势（近30日每日运输总量，无运单日补 0）/ 矿种分布 / 运输方式运量对比。"""
    freight = qall(g.conn, """
        SELECT d::date AS "trendDate", COALESCE(SUM(w.plan_qty), 0) AS qty, count(w.id) AS cnt
        FROM generate_series(current_date - interval '29 days', current_date, interval '1 day') d
        LEFT JOIN biz_waybill w ON w.is_deleted=0 AND DATE(w.created_at) = d::date
        GROUP BY d ORDER BY d
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
