"""需求申报（PRD 4.2/T06）：草稿增改、明细维护、提交、撤回、关闭、脱敏需求池。

规则：提交后品种/数量/交货条件/到货时间锁定；被询价引用的需求不可撤回只能关闭；
供应商只见脱敏概要（品种、数量区间、交货区域、期望月份），看不到钢厂名称与价格意向。
"""
import json

from flask import g, request

from ..common import (ApiError, doc_no, get_params, json_payload, ok, op_log,
                      page_args, page_data, parse_date, require_fields)
from ..db import execute, qall, q1
from ..security import ROLE_CARRIER, ROLE_STEEL, ROLE_SUPPLIER, auth_required, roles_required
from ..state_machine import assert_status, transition
from . import bp


def _save_items(conn, demand_id, items, user_id):
    execute(conn, "DELETE FROM biz_demand_item WHERE demand_id=%s", (demand_id,))
    for it in items:
        require_fields(it, 'varietyId', 'grade', 'quantity')
        v = q1(conn, "SELECT id FROM base_variety WHERE id=%s AND is_deleted=0", (it['varietyId'],))
        if not v:
            raise ApiError(40401, '品种不存在：%s' % it['varietyId'])
        qty = _num(it['quantity'], 'quantity')
        if qty <= 0:
            raise ApiError(40001, '数量必须大于0')
        rate = _num(it.get('moreLessRate') or 5, 'moreLessRate')
        ct, cy, cv = _cycle(it)
        execute(conn, """
            INSERT INTO biz_demand_item (demand_id, variety_id, grade, quantity, more_less_rate,
                                         cycle_type, cycle_year, cycle_value, created_by)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """, (demand_id, it['varietyId'], _num(it['grade'], 'grade'), qty, rate,
                  ct, cy, cv, user_id))


def _cycle(it):
    """采购周期：MONTH(月度)/QUARTER(季度)/ONE_TIME(一次性订单) + 年 + 月(1~12)/季度(1~4)；未传则存 NULL。

    一次性订单与月度一致：同样选择年 + 月（值存 1~12）。
    """
    ct = it.get('cycleType')
    if not ct:
        return None, None, None
    if ct not in ('MONTH', 'QUARTER', 'ONE_TIME'):
        raise ApiError(40001, '周期类型不合法（MONTH/QUARTER/ONE_TIME）')
    try:
        cy = int(it.get('cycleYear'))
        cv = int(it.get('cycleValue'))
    except (TypeError, ValueError):
        raise ApiError(40001, '周期年份/月份数值格式错误')
    if not 2000 <= cy <= 2100:
        raise ApiError(40001, '周期年份不合法')
    if ct == 'QUARTER' and not 1 <= cv <= 4:
        raise ApiError(40001, '季度周期季度不合法（1~4）')
    if ct in ('MONTH', 'ONE_TIME') and not 1 <= cv <= 12:
        raise ApiError(40001, '月度周期月份不合法（1~12）')
    return ct, cy, cv


def _num(v, name):
    from decimal import Decimal, InvalidOperation
    try:
        return Decimal(str(v))
    except (InvalidOperation, TypeError, ValueError):
        raise ApiError(40001, '数值格式错误：%s' % name)


@bp.post('/demands')
@auth_required
def create_demand():
    if not g.ctx.has_role(ROLE_STEEL):
        raise ApiError(40301, '仅钢厂可创建需求')
    p = get_params()
    place = _validate_demand(g.conn, p)
    did = execute(g.conn, """
        INSERT INTO biz_demand (demand_no, company_id, demand_name, delivery_type, delivery_place,
                                expect_arrive_start, expect_arrive_end, price_intent, settle_type,
                                settle_days, quality_req, remark, status, created_by, updated_by)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'DRAFT',%s,%s) RETURNING id
        """, (doc_no(g.conn, 'XQ'), g.ctx.company['id'], p['demandName'], p.get('deliveryType'),
              place or None, parse_date(p, 'expectArriveStart', required=False),
              parse_date(p, 'expectArriveEnd', required=False),
              p.get('priceIntent'), p.get('settleType'), p.get('settleDays'), p.get('qualityReq'),
              p.get('remark'), g.ctx.user['id'], g.ctx.user['id']), returning_id=True)
    _save_items(g.conn, did, p.get('items') or [], g.ctx.user['id'])
    op_log(g.conn, g.ctx, 'biz_demand', did, 'CREATE', None, {'demandName': p['demandName']})
    return ok({'id': did, 'status': 'DRAFT'})


def _is_other_demand(conn, p):
    """「其它」品种需求：所有明细均为 OTHER 品种 → 仅做需求归集，交货/到货/结算信息选填。"""
    items = p.get('items') or []
    if not items:
        return False
    other = q1(conn, "SELECT id FROM base_variety WHERE variety_code='OTHER' AND is_deleted=0")
    if not other:
        return False
    return all(str(it.get('varietyId')) == str(other['id']) for it in items)


def _validate_demand(conn, p):
    require_fields(p, 'demandName')
    if len(str(p['demandName'])) > 50:
        raise ApiError(40001, '需求名称不超过50字')
    other = _is_other_demand(conn, p)
    if not other:
        require_fields(p, 'deliveryType', 'expectArriveStart', 'expectArriveEnd', 'settleType')
    delivery_type = p.get('deliveryType')
    if delivery_type is not None and delivery_type not in ('PLANT', 'STATION_SELF', 'PORT_FOB', 'PORT_TRUCK'):
        raise ApiError(40001, '交货方式不合法（PLANT/STATION_SELF）')
    # 交货地点：到场/到站自提必选；港口自提由供应商报价确定，可为空；「其它」品种选填
    place = (str(p['deliveryPlace']).strip() if p.get('deliveryPlace') is not None else '')
    if delivery_type in ('PLANT', 'STATION_SELF') and not place and not other:
        raise ApiError(40001, '到场/到站自提必须选择交货地点')
    start = parse_date(p, 'expectArriveStart', required=not other)
    end = parse_date(p, 'expectArriveEnd', required=not other)
    if start and end and end < start:
        raise ApiError(40001, '期望到货结束日期不能早于开始日期')
    settle_type = p.get('settleType')
    if settle_type is not None and settle_type not in ('PREPAY', 'COD', 'CREDIT', 'INSTALLMENT'):
        raise ApiError(40001, '结算方式不合法（PREPAY/COD/CREDIT/INSTALLMENT）')
    if settle_type == 'CREDIT' and not p.get('settleDays'):
        raise ApiError(40001, '选择账期结算必须填写账期天数')
    if p.get('remark') and len(str(p['remark'])) > 500:
        raise ApiError(40001, '备注不超过500字')
    return place


@bp.put('/demands/<int:did>')
@auth_required
def update_demand(did):
    row = _own_demand(did)
    p = get_params()
    st = row['status']
    if st not in ('DRAFT', 'WITHDRAWN', 'SUBMITTED', 'PENDING_DELETE'):
        raise ApiError(40901, '需求单当前状态为 %s，不可更改' % st)
    reason = None
    if st in ('SUBMITTED', 'PENDING_DELETE'):
        # 已提交内容需填写更改理由：保存后转"待提交"，重新提交后推送运营端
        reason = (p.get('changeReason') or '').strip()
        if not reason:
            raise ApiError(40001, '已提交需求单更改必须填写更改理由')
    if st == 'SUBMITTED':
        pend = q1(g.conn, """
            SELECT id FROM biz_demand_change WHERE demand_id=%s AND status='PENDING' AND is_deleted=0
            """, (did,))
        if pend:
            raise ApiError(40901, '该需求单已有待审核的变更申请，请等待运营端处理')
    place = _validate_demand(g.conn, p)
    new_status = 'WITHDRAWN' if st in ('SUBMITTED', 'PENDING_DELETE') else st
    before = _demand_raw_snapshot(g.conn, did) if st in ('SUBMITTED', 'PENDING_DELETE') else None
    execute(g.conn, """
        UPDATE biz_demand SET demand_name=%s, delivery_type=%s, delivery_place=%s,
            expect_arrive_start=%s, expect_arrive_end=%s, price_intent=%s, settle_type=%s,
            settle_days=%s, quality_req=%s, remark=%s, status=%s, updated_by=%s, updated_at=now()
        WHERE id=%s
        """, (p['demandName'], p.get('deliveryType'), place or None,
              parse_date(p, 'expectArriveStart', required=False),
              parse_date(p, 'expectArriveEnd', required=False),
              p.get('priceIntent'), p.get('settleType'), p.get('settleDays'), p.get('qualityReq'),
              ('更改理由：' + reason) if reason else p.get('remark'),
              new_status, g.ctx.user['id'], did))
    _save_items(g.conn, did, p.get('items') or [], g.ctx.user['id'])
    if st in ('SUBMITTED', 'PENDING_DELETE'):
        # 两步变更：保存仅本地暂存为「待提交」，变更申请暂存（DRAFT，不推送运营端）；
        # 钢厂点提交时 DRAFT→PENDING 才进入运营端审核。
        # 「删除待提交」下点更改视为放弃删除申请：作废删除暂存，改存内容变更暂存
        execute(g.conn, "UPDATE biz_demand_change SET is_deleted=1 WHERE demand_id=%s AND status='DRAFT'", (did,))
        execute(g.conn, """
            INSERT INTO biz_demand_change (change_no, demand_id, company_id, before_data, after_data,
                                           reason, status, created_by, updated_by)
            VALUES (%s,%s,%s,%s,%s,%s,'DRAFT',%s,%s)
            """, (doc_no(g.conn, 'BG'), did, g.ctx.company['id'],
                  json.dumps(before, ensure_ascii=False),
                  json.dumps(_demand_raw_snapshot(g.conn, did), ensure_ascii=False),
                  reason, g.ctx.user['id'], g.ctx.user['id']))
    elif st == 'WITHDRAWN':
        draft = q1(g.conn, """
            SELECT id FROM biz_demand_change WHERE demand_id=%s AND status='DRAFT' AND is_deleted=0
            ORDER BY id DESC LIMIT 1""", (did,))
        if draft:
            # 待提交状态下再次编辑：刷新暂存变更的「变更后」数据（变更前快照与理由保持首次保存内容）
            execute(g.conn, """
                UPDATE biz_demand_change SET after_data=%s, updated_by=%s, updated_at=now() WHERE id=%s
                """, (json.dumps(_demand_raw_snapshot(g.conn, did), ensure_ascii=False),
                      g.ctx.user['id'], draft['id']))
    op_log(g.conn, g.ctx, 'biz_demand', did, 'UPDATE', None,
           {'demandName': p['demandName'], 'changeReason': reason, 'status': new_status})
    return ok({'id': did, 'status': new_status})


@bp.post('/demands/<int:did>/submit')
@auth_required
def submit_demand(did):
    row = _own_demand(did)
    if row['status'] not in ('DRAFT', 'WITHDRAWN', 'PENDING_DELETE'):
        raise ApiError(40901, '需求单当前状态为 %s，禁止提交' % row['status'])
    items = qall(g.conn, "SELECT * FROM biz_demand_item WHERE demand_id=%s AND is_deleted=0", (did,))
    if not items:
        raise ApiError(40001, '需求至少需要一条明细')
    frm = row['status']
    if frm == 'PENDING_DELETE':
        # 删除申请两步走：随本次提交推送运营端审核（DRAFT→PENDING），需求转「删除待审核」；
        # 审核通过后才关闭并移出归集单，驳回则回退删除前状态
        raw = (row.get('remark') or '').replace('删除理由：', '').strip()
        reason = raw or '钢厂申请删除'
        draft = q1(g.conn, """
            SELECT id FROM biz_demand_change WHERE demand_id=%s AND status='DRAFT' AND is_deleted=0
            ORDER BY id DESC LIMIT 1""", (did,))
        if draft:
            transition(g.conn, g.ctx, 'biz_demand_change', '变更申请', 'biz_demand_change',
                       draft['id'], 'PENDING')
        else:
            # 兜底：无暂存记录（历史数据）时直接生成待审核删除申请
            execute(g.conn, """
                INSERT INTO biz_demand_change (change_no, demand_id, company_id, before_data, after_data,
                                               reason, status, created_by, updated_by)
                VALUES (%s,%s,%s,%s,%s,%s,'PENDING',%s,%s)
                """, (doc_no(g.conn, 'BG'), did, g.ctx.company['id'],
                      json.dumps(_demand_raw_snapshot(g.conn, did), ensure_ascii=False),
                      json.dumps({'deleteRequest': True, 'fromStatus': 'SUBMITTED'}, ensure_ascii=False),
                      reason, g.ctx.user['id'], g.ctx.user['id']))
        transition(g.conn, g.ctx, 'biz_demand', '需求单', 'biz_demand', did, 'DELETE_AUDIT')
        return ok({'id': did, 'status': 'DELETE_AUDIT'})
    to_version = row['version'] + 1 if frm == 'WITHDRAWN' else row['version']
    # 两步变更：随本次提交将暂存的变更申请（DRAFT）推送运营端审核（DRAFT→PENDING）
    draft = q1(g.conn, """
        SELECT id FROM biz_demand_change WHERE demand_id=%s AND status='DRAFT' AND is_deleted=0
        ORDER BY id DESC LIMIT 1""", (did,))
    if draft:
        transition(g.conn, g.ctx, 'biz_demand_change', '变更申请', 'biz_demand_change',
                   draft['id'], 'PENDING')
    execute(g.conn, """
        UPDATE biz_demand SET status='SUBMITTED', version=%s, submitted_at=now(),
               updated_by=%s, updated_at=now() WHERE id=%s
        """, (to_version, g.ctx.user['id'], did))
    op_log(g.conn, g.ctx, 'biz_demand', did, 'STATUS %s->SUBMITTED' % frm,
           {'status': frm, 'version': row['version']}, {'status': 'SUBMITTED', 'version': to_version})
    return ok({'id': did, 'status': 'SUBMITTED', 'version': to_version})


@bp.post('/demands/<int:did>/withdraw')
@auth_required
def withdraw_demand(did):
    row = _own_demand(did)
    assert_status(row, 'SUBMITTED', '需求单')
    ref = q1(g.conn, "SELECT id FROM biz_inquiry WHERE demand_id=%s AND is_deleted=0 LIMIT 1", (did,))
    if ref:
        raise ApiError(40901, '需求已被询价引用，不可撤回，只能关闭')
    transition(g.conn, g.ctx, 'biz_demand', '需求单', 'biz_demand', did, 'WITHDRAWN')
    return ok({'id': did, 'status': 'WITHDRAWN'})


@bp.post('/demands/<int:did>/close')
@auth_required
def close_demand(did):
    row = _own_demand(did)
    p = get_params()
    require_fields(p, 'reason')
    frm = row['status']
    if frm not in ('SUBMITTED', 'INQUIRING', 'DEALT'):
        raise ApiError(40901, '需求单当前状态为 %s，禁止关闭' % frm)
    execute(g.conn, """
        UPDATE biz_demand SET status='CLOSED', remark=concat_ws(' | ', remark, %s::VARCHAR),
               updated_by=%s, updated_at=now() WHERE id=%s
        """, ('关闭原因：' + p['reason'], g.ctx.user['id'], did))
    op_log(g.conn, g.ctx, 'biz_demand', did, 'STATUS %s->CLOSED' % frm,
           {'status': frm}, {'status': 'CLOSED', 'reason': p['reason']})
    return ok({'id': did, 'status': 'CLOSED'})


@bp.delete('/demands/<int:did>')
@auth_required
def delete_demand(did):
    """草稿直接删除；已提交需求须填删除理由 → 转"删除待提交"，提交后生效关闭推送运营端。"""
    row = _own_demand(did)
    st = row['status']
    if st == 'DRAFT':
        execute(g.conn, "UPDATE biz_demand SET is_deleted=1, updated_by=%s, updated_at=now() WHERE id=%s",
                (g.ctx.user['id'], did))
        execute(g.conn, "UPDATE biz_demand_item SET is_deleted=1 WHERE demand_id=%s", (did,))
        op_log(g.conn, g.ctx, 'biz_demand', did, 'DELETE', None, None)
        return ok({'id': did, 'status': 'DELETED'})
    if st == 'CLOSED':
        # 已关闭需求钢厂可自行删除（不走删除审核流程）
        execute(g.conn, "UPDATE biz_demand SET is_deleted=1, updated_by=%s, updated_at=now() WHERE id=%s",
                (g.ctx.user['id'], did))
        execute(g.conn, "UPDATE biz_demand_item SET is_deleted=1 WHERE demand_id=%s", (did,))
        op_log(g.conn, g.ctx, 'biz_demand', did, 'DELETE', None, {'fromStatus': 'CLOSED'})
        return ok({'id': did, 'status': 'DELETED'})
    if st == 'PENDING_DELETE':
        raise ApiError(40901, '需求单已是删除待提交状态')
    if st not in ('SUBMITTED', 'WITHDRAWN', 'TO_INQUIRY', 'AGGREGATED'):
        raise ApiError(40901, '需求单当前状态为 %s，不可删除' % st)
    pend = q1(g.conn, """
        SELECT id FROM biz_demand_change WHERE demand_id=%s AND status='PENDING' AND is_deleted=0
        """, (did,))
    if pend:
        raise ApiError(40901, '该需求单已有待审核的变更申请，请等待运营端处理')
    p = get_params()
    reason = (p.get('reason') or '').strip()
    if not reason:
        raise ApiError(40001, '已提交需求单删除必须填写删除理由')
    execute(g.conn, """
        UPDATE biz_demand SET status='PENDING_DELETE', remark=%s,
               updated_by=%s, updated_at=now() WHERE id=%s
        """, ('删除理由：' + reason, g.ctx.user['id'], did))
    # 删除申请暂存（DRAFT，不推送运营端）：钢厂点「提交」后转 PENDING 进入运营端审核，通过后才关闭
    execute(g.conn, "UPDATE biz_demand_change SET is_deleted=1 WHERE demand_id=%s AND status='DRAFT'", (did,))
    execute(g.conn, """
        INSERT INTO biz_demand_change (change_no, demand_id, company_id, before_data, after_data,
                                       reason, status, created_by, updated_by)
        VALUES (%s,%s,%s,%s,%s,%s,'DRAFT',%s,%s)
        """, (doc_no(g.conn, 'BG'), did, g.ctx.company['id'],
              json.dumps(_demand_raw_snapshot(g.conn, did), ensure_ascii=False),
              json.dumps({'deleteRequest': True, 'fromStatus': st}, ensure_ascii=False),
              reason, g.ctx.user['id'], g.ctx.user['id']))
    op_log(g.conn, g.ctx, 'biz_demand', did, 'STATUS %s->PENDING_DELETE' % st,
           {'status': st}, {'status': 'PENDING_DELETE', 'reason': reason})
    return ok({'id': did, 'status': 'PENDING_DELETE'})


def _own_demand(did):
    row = q1(g.conn, "SELECT * FROM biz_demand WHERE id=%s AND is_deleted=0", (did,))
    if not row:
        raise ApiError(40401, '需求单不存在')
    if not g.ctx.is_plat and row['company_id'] != g.ctx.company['id']:
        raise ApiError(40301, '无权限操作该需求单')
    return row


# ---------- 变更申请：钢厂已提交需求在平台询价前可申请变更，运营端审核通过后自动同步 ----------
def _demand_raw_snapshot(conn, did):
    """变更前数据（与前端编辑表单同构的原始字段，供前端差异展示与审核通过后回放应用）。"""
    d = q1(conn, "SELECT * FROM biz_demand WHERE id=%s", (did,))
    items = qall(conn, """
        SELECT i.variety_id AS "varietyId", v.variety_name AS "varietyName", i.grade, i.quantity,
               i.more_less_rate AS "moreLessRate", i.cycle_type AS "cycleType",
               i.cycle_year AS "cycleYear", i.cycle_value AS "cycleValue"
        FROM biz_demand_item i JOIN base_variety v ON v.id=i.variety_id
        WHERE i.demand_id=%s AND i.is_deleted=0 ORDER BY i.id
        """, (did,))
    return {
        'demandName': d['demand_name'],
        'deliveryType': d['delivery_type'],
        'deliveryPlace': d['delivery_place'],
        'expectArriveStart': d['expect_arrive_start'].strftime('%Y-%m-%d') if d['expect_arrive_start'] else '',
        'expectArriveEnd': d['expect_arrive_end'].strftime('%Y-%m-%d') if d['expect_arrive_end'] else '',
        'settleType': d['settle_type'],
        'settleDays': d['settle_days'],
        'qualityReq': d['quality_req'],
        'items': json_payload(items),
    }


@bp.post('/demands/<int:did>/change-request')
@auth_required
def create_change_request(did):
    """已提交需求（平台询价开始前）提交变更申请：留痕变更前后数据，运营端审核。

    可申请范围：未归集的已提交需求；已归集但归集单尚未询价（OPEN）的需求也可申请，
    但已归集需求仅允许数量/交货信息变更（品类/品位变更会破坏归集口径，须先关闭归集单）。
    """
    row = _own_demand(did)
    pend = q1(g.conn, """
        SELECT id FROM biz_demand_change WHERE demand_id=%s AND status='PENDING' AND is_deleted=0
        """, (did,))
    if pend:
        raise ApiError(40901, '该需求单已有待审核的变更申请，请等待运营端处理')
    agg = q1(g.conn, """
        SELECT a.id, a.status FROM biz_aggregated_order_item m
        JOIN biz_aggregated_order a ON a.id=m.agg_id AND a.is_deleted=0
        WHERE m.demand_id=%s AND m.is_deleted=0 ORDER BY m.id DESC LIMIT 1
        """, (did,))
    agg_locked = bool(agg)   # 已归集（含归集单 OPEN 未询价 → 需求状态为 INQUIRING）
    if agg_locked:
        if agg['status'] != 'OPEN':
            raise ApiError(40901, '该需求已进入询价流程，不可提交变更申请')
    elif row['status'] not in ('SUBMITTED', 'TO_INQUIRY', 'AGGREGATED'):
        raise ApiError(40901, '仅已提交/待询价/已归集（未进入询价）的需求单可提交变更申请')
    p = get_params()
    reason = (p.get('changeReason') or '').strip()
    if not reason:
        raise ApiError(40001, '变更申请必须填写变更理由')
    _validate_demand(g.conn, p)   # 校验变更后的内容合法性
    before = _demand_raw_snapshot(g.conn, did)
    if agg_locked:
        from decimal import Decimal, InvalidOperation

        def same_num(x, y):
            try:
                return Decimal(str(x)) == Decimal(str(y))
            except (InvalidOperation, TypeError, ValueError):
                return str(x) == str(y)
        old_it = (before.get('items') or [{}])[0]
        new_it = (p.get('items') or [{}])[0]
        if (str(new_it.get('varietyId')) != str(old_it.get('varietyId'))
                or not same_num(new_it.get('grade'), old_it.get('grade'))):
            raise ApiError(40001, '已归集需求仅可变更数量与交货信息，品类/品位变更请先联系平台关闭归集单')
    after = {
        'demandName': p['demandName'], 'deliveryType': p['deliveryType'],
        'deliveryPlace': p.get('deliveryPlace'),
        'expectArriveStart': p.get('expectArriveStart'), 'expectArriveEnd': p.get('expectArriveEnd'),
        'settleType': p['settleType'], 'settleDays': p.get('settleDays'),
        'qualityReq': p.get('qualityReq'),
        'items': p.get('items') or [],
    }
    # 品类名注入（变更后数据用于差异展示，前端需要品类名）
    vmap = {}
    for it in after['items']:
        vid = it.get('varietyId')
        if vid and vid not in vmap:
            vr = q1(g.conn, "SELECT variety_name FROM base_variety WHERE id=%s", (vid,))
            vmap[vid] = vr['variety_name'] if vr else None
        it.setdefault('varietyName', vmap.get(vid))
    cno = doc_no(g.conn, 'BG')
    cid = execute(g.conn, """
        INSERT INTO biz_demand_change (change_no, demand_id, company_id, before_data, after_data,
                                       reason, status, created_by, updated_by)
        VALUES (%s,%s,%s,%s,%s,%s,'PENDING',%s,%s) RETURNING id
        """, (cno, did, g.ctx.company['id'],
              json.dumps(before, ensure_ascii=False), json.dumps(after, ensure_ascii=False),
              reason, g.ctx.user['id'], g.ctx.user['id']), returning_id=True)
    op_log(g.conn, g.ctx, 'biz_demand_change', cid, 'CREATE', None,
           {'changeNo': cno, 'demandNo': row['demand_no'], 'reason': reason, 'aggLocked': agg_locked})
    return ok({'id': cid, 'changeNo': cno, 'status': 'PENDING'})


def _mask_demand(row):
    """脱敏概要：品种、数量区间、交货区域、期望月份（PRD 4.2）。"""
    items = qall(g.conn, """
        SELECT i.id, v.variety_name AS "varietyName", i.grade, i.quantity, i.more_less_rate AS "moreLessRate",
               i.quantity - i.inquired_qty - COALESCE(i.deal_qty, 0) AS "remainQty"
        FROM biz_demand_item i JOIN base_variety v ON v.id=i.variety_id
        WHERE i.demand_id=%s AND i.is_deleted=0 ORDER BY i.id
        """, (row['id'],))
    total = sum(i['quantity'] for i in items) if items else 0
    return {
        'id': row['id'], 'demandNo': row['demand_no'],
        'items': json_payload(items),
        'totalQty': str(total),
        'deliveryType': row['delivery_type'],
        'deliveryRegion': row['delivery_place'],
        'expectMonth': (row['expect_arrive_start'].strftime('%Y-%m') if row['expect_arrive_start'] else None),
        'createdAt': row['created_at'],
    }


@bp.get('/demands')
@auth_required
def demand_list():
    params = request.args.to_dict()
    page, size = page_args(params)
    if g.ctx.has_role(ROLE_STEEL):
        return _own_demand_list(params, page, size)
    # 供应商/物流/其他：只看已提交需求池的脱敏概要
    where = "WHERE d.status='SUBMITTED' AND d.is_deleted=0"
    args = []
    if params.get('varietyId'):
        where += (' AND EXISTS (SELECT 1 FROM biz_demand_item i '
                  'WHERE i.demand_id=d.id AND i.variety_id=%s AND i.is_deleted=0)')
        args.append(params['varietyId'])
    total = q1(g.conn, 'SELECT count(*) AS c FROM biz_demand d ' + where, args)['c']
    rows = qall(g.conn, 'SELECT d.* FROM biz_demand d ' + where +
                ' ORDER BY d.id DESC LIMIT %s OFFSET %s', args + [size, (page - 1) * size])
    return ok(page_data([_mask_demand(r) for r in rows], total, page, size))


def _own_demand_list(params, page, size):
    where = 'WHERE company_id=%s AND is_deleted=0'
    args = [g.ctx.company['id']]
    if params.get('status'):
        if params['status'] == 'UNPUSHED':
            # 展示口径「待提交」：草稿/待提交/删除待提交 统一筛选
            where += " AND status IN ('DRAFT','WITHDRAWN','PENDING_DELETE')"
        else:
            where += ' AND status=%s'
            args.append(params['status'])
    total = q1(g.conn, 'SELECT count(*) AS c FROM biz_demand ' + where, args)['c']
    rows = qall(g.conn, """
        SELECT * FROM biz_demand %s ORDER BY id DESC LIMIT %%s OFFSET %%s
        """ % where, args + [size, (page - 1) * size])
    out = []
    for r in rows:
        d = json_payload(dict(r))
        d['items'] = json_payload(qall(g.conn, """
            SELECT i.id, i.variety_id AS "varietyId", v.variety_name AS "varietyName", i.grade,
                   i.quantity, i.more_less_rate AS "moreLessRate",
                   i.cycle_type AS "cycleType", i.cycle_year AS "cycleYear", i.cycle_value AS "cycleValue",
                   i.inquired_qty AS "inquiredQty",
                   i.quantity - i.inquired_qty - COALESCE(i.deal_qty, 0) AS "remainQty", i.deal_qty AS "dealQty"
            FROM biz_demand_item i JOIN base_variety v ON v.id=i.variety_id
            WHERE i.demand_id=%s AND i.is_deleted=0 ORDER BY i.id
            """, (r['id'],)))
        d['changePending'] = bool(q1(g.conn, """
            SELECT id FROM biz_demand_change
            WHERE demand_id=%s AND status='PENDING' AND is_deleted=0 LIMIT 1
            """, (r['id'],)))
        # 最近一次变更/删除申请审核结果：已驳回时钢厂端状态栏展示「已驳回」标签与原因
        last_ch = q1(g.conn, """
            SELECT status, COALESCE(audit_remark, '') AS remark FROM biz_demand_change
            WHERE demand_id=%s AND is_deleted=0 AND status IN ('PENDING','APPROVED','REJECTED')
            ORDER BY id DESC LIMIT 1""", (r['id'],))
        d['lastChangeStatus'] = last_ch['status'] if last_ch else None
        d['lastChangeRemark'] = last_ch['remark'] if last_ch else ''
        d['aggOpen'] = bool(q1(g.conn, """
            SELECT m.id FROM biz_aggregated_order_item m
            JOIN biz_aggregated_order a ON a.id=m.agg_id AND a.is_deleted=0
            WHERE m.demand_id=%s AND m.is_deleted=0 AND a.status='OPEN' LIMIT 1
            """, (r['id'],)))
        out.append(d)
    return ok(page_data(out, total, page, size))


@bp.get('/demands/<int:did>')
@auth_required
def demand_detail(did):
    row = q1(g.conn, "SELECT * FROM biz_demand WHERE id=%s AND is_deleted=0", (did,))
    if not row:
        raise ApiError(40401, '需求单不存在')
    if g.ctx.is_plat or (g.ctx.company and row['company_id'] == g.ctx.company['id']):
        d = json_payload(dict(row))
        d['items'] = json_payload(qall(g.conn, """
            SELECT i.id, i.variety_id AS "varietyId", v.variety_name AS "varietyName", i.grade,
                   i.quantity, i.more_less_rate AS "moreLessRate",
                   i.cycle_type AS "cycleType", i.cycle_year AS "cycleYear", i.cycle_value AS "cycleValue",
                   i.inquired_qty AS "inquiredQty",
                   i.quantity - i.inquired_qty - COALESCE(i.deal_qty, 0) AS "remainQty", i.deal_qty AS "dealQty"
            FROM biz_demand_item i JOIN base_variety v ON v.id=i.variety_id
            WHERE i.demand_id=%s AND i.is_deleted=0 ORDER BY i.id
            """, (did,)))
        d['changePending'] = bool(q1(g.conn, """
            SELECT id FROM biz_demand_change
            WHERE demand_id=%s AND status='PENDING' AND is_deleted=0 LIMIT 1
            """, (did,)))
        d['aggOpen'] = bool(q1(g.conn, """
            SELECT m.id FROM biz_aggregated_order_item m
            JOIN biz_aggregated_order a ON a.id=m.agg_id AND a.is_deleted=0
            WHERE m.demand_id=%s AND m.is_deleted=0 AND a.status='OPEN' LIMIT 1
            """, (did,)))
        return ok(d)
    if row['status'] == 'SUBMITTED':
        return ok(_mask_demand(row))
    raise ApiError(40301, '无权限查看该需求单')


# ---------------- 供应商端：运营推送的需求归集（采购参考，非询价） ----------------

@bp.get('/demand-groups')
@roles_required(ROLE_SUPPLIER)
def demand_groups():
    """运营平台已推送的月度/季度需求归集列表（供应商采购参考）。"""
    params = get_params()
    page, size = page_args(params)
    where = "WHERE a.is_deleted=0 AND a.agg_kind='DEMAND' AND a.pushed_at IS NOT NULL"
    total = q1(g.conn, 'SELECT count(*) AS c FROM biz_aggregated_order a ' + where, [])['c']
    rows = qall(g.conn, """
        SELECT a.id, a.agg_no AS "aggNo", v.variety_name AS "varietyName", v.category,
               a.grade, a.total_qty AS "totalQty",
               a.cycle_type AS "cycleType", a.cycle_year AS "cycleYear", a.cycle_value AS "cycleValue",
               a.created_at AS "createdAt", a.pushed_at AS "pushedAt",
               (SELECT count(*) FROM biz_aggregated_order_item m
                 WHERE m.agg_id=a.id AND m.is_deleted=0) AS "memberCount",
               (SELECT string_agg(DISTINCT c.company_name, '、')
                 FROM biz_aggregated_order_item m JOIN ent_company c ON c.id=m.company_id
                 WHERE m.agg_id=a.id AND m.is_deleted=0) AS "companyNames"
        FROM biz_aggregated_order a
        JOIN base_variety v ON v.id=a.variety_id
        %s ORDER BY a.pushed_at DESC, a.id DESC LIMIT %%s OFFSET %%s
        """ % where, [size, (page - 1) * size])
    return ok(page_data(rows, total, page, size))


@bp.get('/demand-groups/<int:aid>')
@roles_required(ROLE_SUPPLIER)
def demand_group_detail(aid):
    """供应商查看运营推送的需求归集详情：基本信息 + 参与明细（钢厂/矿种/品位/数量/预期到货时间）。"""
    a = q1(g.conn, """
        SELECT a.id, a.agg_no AS "aggNo", a.grade, a.total_qty AS "totalQty",
               a.cycle_type AS "cycleType", a.cycle_year AS "cycleYear", a.cycle_value AS "cycleValue",
               a.created_at AS "createdAt", a.pushed_at AS "pushedAt",
               v.variety_name AS "varietyName"
        FROM biz_aggregated_order a JOIN base_variety v ON v.id=a.variety_id
        WHERE a.id=%s AND a.is_deleted=0 AND a.agg_kind='DEMAND' AND a.pushed_at IS NOT NULL
        """, (aid,))
    if not a:
        raise ApiError(40401, '需求归集不存在或尚未推送')
    members = qall(g.conn, """
        SELECT m.id, c.company_name AS "companyName",
               v.variety_name AS "varietyName", di.grade, m.quantity,
               d.expect_arrive_start AS "expectArriveStart", d.expect_arrive_end AS "expectArriveEnd"
        FROM biz_aggregated_order_item m
        JOIN ent_company c ON c.id=m.company_id
        JOIN biz_demand d ON d.id=m.demand_id
        JOIN biz_demand_item di ON di.id=m.demand_item_id
        JOIN base_variety v ON v.id=di.variety_id
        WHERE m.agg_id=%s AND m.is_deleted=0 ORDER BY m.id
        """, (aid,))
    return ok({'order': json_payload(a), 'members': json_payload(members)})
