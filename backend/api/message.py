# -*- coding: utf-8 -*-
"""业务预警&消息通知模块 (PRD-12)：站内消息中心（待办/通知/预警）+ 预警规则配置 + 预警扫描"""
from flask import Blueprint, request, g
from ..db import get_db, _now
from ..utils import ok, err, log_action, paginate
from ..auth import roles_required, login_required

bp = Blueprint('message', __name__)

MSG_TYPE = {1: '待办', 2: '通知', 3: '预警'}


def notify(receiver_user_ids, msg_type, title, content=None, link_biz_type=None, biz_id=None):
    """内部服务接口：业务事件触发消息（供各业务模块调用，不对外）"""
    if not receiver_user_ids:
        return
    db = get_db()
    now = _now()
    for uid in set(int(u) for u in receiver_user_ids if u):
        db.execute(
            "INSERT INTO ore_message(receiver_user_id,msg_type,title,content,link_biz_type,biz_id,create_time)"
            " VALUES(?,?,?,?,?,?,?)",
            (uid, msg_type, title, content, link_biz_type, str(biz_id) if biz_id is not None else None, now))
    db.commit()


def notify_role(role_code, msg_type, title, content=None, link_biz_type=None, biz_id=None, company_id=None):
    """按角色（可限定企业）发消息"""
    db = get_db()
    if company_id:
        rows = db.execute("SELECT user_id FROM sys_user WHERE role_code=? AND company_id=? AND status='ACTIVE'",
                          (role_code, company_id)).fetchall()
    else:
        rows = db.execute("SELECT user_id FROM sys_user WHERE role_code=? AND status='ACTIVE'",
                          (role_code,)).fetchall()
    notify([r['user_id'] for r in rows], msg_type, title, content, link_biz_type, biz_id)


def notify_company(db, company_id, msg_type, title, content=None, link_biz_type=None, biz_id=None):
    """按企业主体发消息（不限定角色，企业下全部启用账号）"""
    rows = db.execute("SELECT user_id FROM sys_user WHERE company_id=? AND status='ACTIVE'",
                      (company_id,)).fetchall()
    notify([r['user_id'] for r in rows], msg_type, title, content, link_biz_type, biz_id)


# ================= 消息中心（所有角色） =================

@bp.get('/message/list')
@login_required
def message_list():
    db = get_db()
    page = int(request.args.get('page', 1)); size = int(request.args.get('page_size', 10))
    sql = "SELECT * FROM ore_message WHERE receiver_user_id=? AND is_deleted=0"
    args = [g.current_user['user_id']]
    if request.args.get('msg_type'):
        sql += " AND msg_type=?"; args.append(int(request.args['msg_type']))
    if request.args.get('is_read'):
        sql += " AND is_read=?"; args.append(int(request.args['is_read']))
    sql += " ORDER BY create_time DESC, msg_id DESC"
    rows, total = paginate(db, sql, args, page, size)
    for r in rows:
        r['msg_type_name'] = MSG_TYPE.get(r['msg_type'], '通知')
    return ok({'list': rows, 'total': total, 'page': page, 'page_size': size})


@bp.get('/message/unread-count')
@login_required
def unread_count():
    n = get_db().execute(
        "SELECT COUNT(*) FROM ore_message WHERE receiver_user_id=? AND is_read=0 AND is_deleted=0",
        (g.current_user['user_id'],)).fetchone()[0]
    return ok({'count': n})


@bp.post('/message/<int:mid>/read')
@login_required
def mark_read(mid):
    db = get_db()
    row = db.execute("SELECT * FROM ore_message WHERE msg_id=? AND receiver_user_id=?",
                     (mid, g.current_user['user_id'])).fetchone()
    if not row:
        return err('消息不存在', http=404)
    db.execute("UPDATE ore_message SET is_read=1 WHERE msg_id=?", (mid,))
    db.commit()
    return ok(message='已标记已读')


@bp.post('/message/read-all')
@login_required
def read_all():
    db = get_db()
    db.execute("UPDATE ore_message SET is_read=1 WHERE receiver_user_id=? AND is_read=0",
               (g.current_user['user_id'],))
    db.commit()
    return ok(message='全部已读')


@bp.get('/message/<int:mid>')
@login_required
def message_detail(mid):
    db = get_db()
    row = db.execute("SELECT * FROM ore_message WHERE msg_id=? AND receiver_user_id=? AND is_deleted=0",
                     (mid, g.current_user['user_id'])).fetchone()
    if not row:
        return err('消息不存在', http=404)
    db.execute("UPDATE ore_message SET is_read=1 WHERE msg_id=?", (mid,))
    db.commit()
    d = dict(row)
    d['is_read'] = 1  # 查看即已读（返回更新后的状态）
    d['msg_type_name'] = MSG_TYPE.get(d['msg_type'], '通知')
    return ok(d)


# ================= 待办办结（内部联动） =================

@bp.post('/message/finish')
@login_required
def finish_todo():
    """业务办结后自动标记对应待办已办结：按 link_biz_type + biz_id 匹配接收人待办"""
    d = request.get_json(force=True, silent=True) or {}
    biz_type, biz_id = d.get('link_biz_type'), d.get('biz_id')
    if not biz_type or biz_id is None:
        return err('缺少业务单据标识')
    db = get_db()
    cur = db.execute(
        "UPDATE ore_message SET is_finish=1, is_read=1 WHERE link_biz_type=? AND biz_id=?"
        " AND msg_type=1 AND is_finish=0 AND is_deleted=0",
        (biz_type, str(biz_id)))
    db.commit()
    return ok({'finished': cur.rowcount})


# ================= 预警规则配置（管理员） =================

WARN_TYPES = [
    ('CONTRACT_EXPIRE', '合同到期预警', '提前天数'),
    ('RESOURCE_EXPIRE', '货源供货周期到期预警', '提前天数'),
    ('PRICE_CHANGE', '价格行情异动预警', '波动幅度(%)'),
    ('LOGI_STALE', '物流节点超时预警', '未更新天数'),
]


@bp.get('/warn/rule/list')
@roles_required('R4')
def warn_rule_list():
    rows = [dict(r) for r in get_db().execute("SELECT * FROM ore_warn_rule ORDER BY rule_id").fetchall()]
    for r in rows:
        t = next((x for x in WARN_TYPES if x[0] == r['warn_type']), None)
        r['warn_type_name'] = t[1] if t else r['warn_type']
        r['threshold_unit'] = t[2] if t else ''
    return ok({'list': rows, 'total': len(rows), 'page': 1, 'page_size': len(rows) or 10})


@bp.post('/warn/rule/save')
@roles_required('R4')
def warn_rule_save():
    d = request.get_json(force=True)
    db = get_db()
    name = (d.get('rule_name') or '').strip()
    wtype = (d.get('warn_type') or '').strip()
    if not name:
        return err('规则名称必填')
    if wtype not in [t[0] for t in WARN_TYPES]:
        return err('无效的预警类型')
    try:
        threshold = round(float(d.get('threshold')), 2)
    except (TypeError, ValueError):
        return err('预警阈值必须为数字')
    if threshold <= 0:
        return err('预警阈值必须大于0')
    now = _now()
    if d.get('rule_id'):
        db.execute("UPDATE ore_warn_rule SET rule_name=?,warn_type=?,threshold=?,enable_status=?,update_time=?"
                   " WHERE rule_id=?",
                   (name, wtype, threshold, 1 if d.get('enable_status', 1) else 0, now, d['rule_id']))
        rid = d['rule_id']
    else:
        cur = db.execute("INSERT INTO ore_warn_rule(rule_name,warn_type,threshold,enable_status,create_time)"
                         " VALUES(?,?,?,?,?)", (name, wtype, threshold, 1 if d.get('enable_status', 1) else 0, now))
        rid = cur.lastrowid
    db.commit()
    log_action('保存预警规则', f"{name}（{wtype}，阈值{threshold}）", ref_type='ore_warn_rule', ref_id=rid)
    return ok({'rule_id': rid})


@bp.post('/warn/rule/<int:rid>/toggle')
@roles_required('R4')
def warn_rule_toggle(rid):
    db = get_db()
    row = db.execute("SELECT * FROM ore_warn_rule WHERE rule_id=?", (rid,)).fetchone()
    if not row:
        return err('规则不存在', http=404)
    new_status = 0 if row['enable_status'] else 1
    db.execute("UPDATE ore_warn_rule SET enable_status=?,update_time=? WHERE rule_id=?",
               (new_status, _now(), rid))
    db.commit()
    log_action('启用/停用预警规则', row['rule_name'], after='启用' if new_status else '停用',
               ref_type='ore_warn_rule', ref_id=rid)
    return ok({'enable_status': new_status})


# ================= 预警扫描（管理员手动触发，模拟定时任务） =================

@bp.post('/warn/scan')
@roles_required('R4')
def warn_scan():
    """扫描已启用的预警规则，生成预警消息（合同到期/价格异动/物流超时/货源周期）"""
    db = get_db()
    now = _now()
    rules = {r['warn_type']: r for r in db.execute(
        "SELECT * FROM ore_warn_rule WHERE enable_status=1").fetchall()}
    generated = {'CONTRACT_EXPIRE': 0, 'PRICE_CHANGE': 0, 'LOGI_STALE': 0, 'RESOURCE_EXPIRE': 0}

    def last_sent(wtype, biz_id):
        return db.execute(
            "SELECT 1 FROM ore_message WHERE msg_type=3 AND link_biz_type=? AND biz_id=? AND create_time>=?",
            (wtype, str(biz_id), now[:10])).fetchone()

    # 1. 合同到期预警
    r = rules.get('CONTRACT_EXPIRE')
    if r:
        days = int(r['threshold'])
        rows = db.execute(
            "SELECT c.*, e.company_name FROM ore_contract c JOIN company e ON e.company_id=c.enterprise_id"
            " WHERE c.expire_date IS NOT NULL AND c.status IN ('EFFECTIVE','EXECUTING')"
            " AND c.is_redbacked=0 AND julianday(c.expire_date)-julianday(?)<=? AND julianday(c.expire_date)>=julianday(?)",
            (now, days, now)).fetchall()
        for c in rows:
            if not last_sent('CONTRACT', c['contract_id']):
                notify_role('R4', 3, f"合同到期预警：{c['contract_no']}",
                            f"与「{c['company_name']}」的合同 {c['contract_no']} 将于 {c['expire_date']} 到期（提前{days}天预警）",
                            'CONTRACT', c['contract_id'])
                generated['CONTRACT_EXPIRE'] += 1

    # 2. 价格行情异动预警
    r = rules.get('PRICE_CHANGE')
    if r:
        pct = r['threshold']
        cats = [x['ore_category'] for x in db.execute(
            "SELECT DISTINCT ore_category FROM ore_price_quote").fetchall()]
        for cat in cats:
            quotes = db.execute(
                "SELECT * FROM ore_price_quote WHERE ore_category=? ORDER BY quote_date DESC LIMIT 2",
                (cat,)).fetchall()
            if len(quotes) < 2 or not quotes[1]['market_price']:
                continue
            change = (quotes[0]['market_price'] - quotes[1]['market_price']) / quotes[1]['market_price'] * 100
            if abs(change) >= pct and not last_sent('PRICE', f"{cat}-{quotes[0]['quote_date']}"):
                notify_role('R4', 3, f"价格异动预警：{cat}",
                            f"{cat} 最新行情 {quotes[0]['market_price']} 元/吨，较前一日变动 {change:+.1f}%（阈值±{pct}%）",
                            'PRICE', f"{cat}-{quotes[0]['quote_date']}")
                generated['PRICE_CHANGE'] += 1

    # 3. 物流节点超时预警
    r = rules.get('LOGI_STALE')
    if r:
        days = int(r['threshold'])
        rows = db.execute(
            "SELECT * FROM logistics_task WHERE current_node < 7").fetchall()
        for t in rows:
            last_node = db.execute(
                "SELECT MAX(done_time) AS last_time FROM logistics_node WHERE logi_id=? AND status='DONE'",
                (t['logi_id'],)).fetchone()['last_time'] or t['create_time']
            stale_days = _days_between(last_node, now)
            if stale_days >= days and not last_sent('LOGI', t['logi_id']):
                notify_role('R4', 3, f"物流超时预警：{t['logi_no']}",
                            f"物流任务 {t['logi_no']} 已 {stale_days} 天未更新节点（阈值{days}天）",
                            'LOGI', t['logi_id'])
                generated['LOGI_STALE'] += 1

    # 4. 货源供货周期到期预警（supply_period 形如 2026-12-31 或 2026-12，仅精确到日时参与扫描）
    r = rules.get('RESOURCE_EXPIRE')
    if r:
        days = int(r['threshold'])
        rows = db.execute(
            "SELECT r.resource_id, r.supply_period, c.company_name FROM ore_resource r"
            " JOIN company c ON c.company_id=r.supplier_id WHERE r.status='ON_SHELF'").fetchall()
        for res in rows:
            sp = (res['supply_period'] or '').strip()
            if len(sp) < 10:
                continue
            end_date = sp[:10]
            if _days_between(now[:10], end_date + ' 00:00:00') is None:
                continue
            remain = _date_diff(now[:10], end_date)
            if remain is not None and 0 <= remain <= days and not last_sent('RESOURCE', res['resource_id']):
                notify_role('R4', 3, f"货源周期预警：#{res['resource_id']}",
                            f"供方「{res['company_name']}」货源 #{res['resource_id']} 供货周期将于 {end_date} 到期（提前{days}天预警）",
                            'RESOURCE', res['resource_id'])
                generated['RESOURCE_EXPIRE'] += 1

    total = sum(generated.values())
    log_action('执行预警扫描', f"生成预警消息 {total} 条：{generated}")
    return ok({'generated': generated, 'total': total})


def _days_between(start, end):
    """end - start 天数（负值归0），支持 'YYYY-MM-DD HH:MM:SS' 与 'YYYY-MM-DD' 两种格式"""
    from datetime import datetime as dt

    def _p(s):
        s = str(s)[:19]
        for f in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d'):
            try:
                return dt.strptime(s, f)
            except ValueError:
                continue
        return None

    s, e = _p(start), _p(end)
    if s is None or e is None:
        return None
    return max(0, (e - s).days)


def _date_diff(start_day, end_day):
    """end - start 天数（可正可负），格式非法返回 None"""
    from datetime import datetime as dt
    try:
        s = dt.strptime(str(start_day)[:10], '%Y-%m-%d')
        e = dt.strptime(str(end_day)[:10], '%Y-%m-%d')
        return (e - s).days
    except (ValueError, TypeError):
        return None
