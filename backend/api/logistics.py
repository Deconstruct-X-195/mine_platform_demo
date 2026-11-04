# -*- coding: utf-8 -*-
"""物流跟踪模块 (PRD-05)：物流任务创建/7节点顺序推进/配套方操作与单据/总看板/回退授权/下游只读视图"""
import re
from flask import Blueprint, request, g
from ..db import get_db, _now
from ..utils import ok, err, log_action, paginate
from ..auth import roles_required, company_approved_required

bp = Blueprint('logistics', __name__)

NODE_NAMES = {1: '待启运', 2: '海运在途', 3: '船舶到港', 4: '港口接卸完成',
              5: '入仓储', 6: '启动陆运配送', 7: '完成送达'}
TIME_RE = re.compile(r'^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$')


def _phase(node):
    if node <= 0:
        return 'NOT_STARTED'
    if node <= 4:
        return 'IN_TRANSIT'
    if node <= 6:
        return 'WAREHOUSED'
    return 'DELIVERED'


def _get_task(db, lid):
    return db.execute("SELECT * FROM logistics_task WHERE logi_id=?", (lid,)).fetchone()


def _task_vo(db, t):
    """任务视图对象：订单/供方/四方名称/当前节点"""
    o = db.execute(
        "SELECT o.*, c.company_name AS supplier_name FROM collective_order o"
        " JOIN company c ON c.company_id=o.supplier_id WHERE o.order_id=?", (t['order_id'],)).fetchone()
    names = {}
    for col in ('sea_partner_id', 'port_partner_id', 'warehouse_partner_id', 'land_partner_id'):
        if t[col]:
            r = db.execute("SELECT company_name FROM company WHERE company_id=?", (t[col],)).fetchone()
            names[col] = r['company_name'] if r else None
    cur = db.execute(
        "SELECT node_code,node_name,status,actual_time FROM logistics_node"
        " WHERE logi_id=? AND node_code=? ", (t['logi_id'], min(t['current_node'] + 1, 7))).fetchone()
    return {**dict(t), **names,
            'order_no': o['order_no'] if o else None,
            'ore_category': o['ore_category'] if o else None,
            'total_qty': o['total_qty'] if o else None,
            'supplier_name': o['supplier_name'] if o else None,
            'phase': _phase(t['current_node']),
            'next_node': dict(cur) if cur else None}


# ================= 平台端 (R4) =================

@bp.post('/admin/logistics/create')
@roles_required('R4')
def logistics_create():
    """为已锁货订单创建物流任务并分配配套方"""
    d = request.get_json(force=True)
    db = get_db()
    if not d.get('order_id'):
        return err('缺少集采订单')
    o = db.execute("SELECT * FROM collective_order WHERE order_id=?", (d['order_id'],)).fetchone()
    if not o:
        return err('集采订单不存在', http=404)
    if o['status'] != 'LOCKED':
        return err('仅已锁货状态的订单可创建物流任务')
    dup = db.execute("SELECT logi_id FROM logistics_task WHERE order_id=?", (d['order_id'],)).fetchone()
    if dup:
        return err('该订单已存在物流任务')

    partners = {}
    for field in ('sea_partner_id', 'port_partner_id', 'warehouse_partner_id', 'land_partner_id'):
        pid = d.get(field)
        if pid in ('', None):
            partners[field] = None
            continue
        try:
            pid = int(pid)
        except (TypeError, ValueError):
            return err(f'{field} 无效')
        c = db.execute("SELECT * FROM company WHERE company_id=?", (pid,)).fetchone()
        if not c or c['company_type'] != 'PARTNER':
            return err(f'{field} 不是履约配套方')
        if c['audit_status'] != 'APPROVED':
            return err(f'配套方 {c["company_name"]} 资质未审核通过')
        partners[field] = pid
    if not any(partners.values()):
        return err('请至少分配一家履约配套方')

    now = _now()
    cur = db.execute(
        "INSERT INTO logistics_task(order_id,sea_partner_id,port_partner_id,warehouse_partner_id,"
        "land_partner_id,from_place,dest_port,plan_arrival,warehouse,dest_place,current_node,create_time)"
        " VALUES(?,?,?,?,?,?,?,?,?,?,0,?)",
        (d['order_id'], partners['sea_partner_id'], partners['port_partner_id'],
         partners['warehouse_partner_id'], partners['land_partner_id'],
         (d.get('from_place') or '').strip() or None, (d.get('dest_port') or '').strip() or None,
         (d.get('plan_arrival') or '').strip() or None, (d.get('warehouse') or '').strip() or None,
         (d.get('dest_place') or '').strip() or None, now))
    lid = cur.lastrowid
    db.execute("UPDATE logistics_task SET logi_no=? WHERE logi_id=?", (f"LG{now.replace('-', '').replace(':', '').replace(' ', '')}{lid:04d}", lid))
    for code in range(1, 8):
        db.execute(
            "INSERT INTO logistics_node(logi_id,node_code,node_name,status) VALUES(?,?,?,'PENDING')",
            (lid, code, NODE_NAMES[code]))
    db.commit()
    log_action('创建物流任务', f"订单{o['order_no']} 分配海运/港口/仓储/陆运配套方",
               ref_type='logistics_task', ref_id=lid)
    return ok(_task_vo(db, _get_task(db, lid)))


@bp.get('/admin/logistics/board')
@roles_required('R4')
def logistics_board():
    """物流总看板：全量进度 + 在途/到港分布统计"""
    db = get_db()
    page = int(request.args.get('page', 1)); size = int(request.args.get('page_size', 10))
    sql = ("SELECT lt.*, o.order_no, o.supplier_id, o.ore_category, o.total_qty,"
           " c.company_name AS supplier_name FROM logistics_task lt"
           " JOIN collective_order o ON o.order_id=lt.order_id"
           " JOIN company c ON c.company_id=o.supplier_id WHERE 1=1")
    args = []
    phase = request.args.get('phase')
    if phase == 'NOT_STARTED':
        sql += " AND lt.current_node=0"
    elif phase == 'IN_TRANSIT':
        sql += " AND lt.current_node BETWEEN 1 AND 4"
    elif phase == 'WAREHOUSED':
        sql += " AND lt.current_node BETWEEN 5 AND 6"
    elif phase == 'DELIVERED':
        sql += " AND lt.current_node=7"
    elif phase:
        return err('无效的阶段筛选')
    if request.args.get('supplier'):
        sql += " AND c.company_name LIKE ?"; args.append(f"%{request.args['supplier']}%")
    if request.args.get('dest_port'):
        sql += " AND lt.dest_port LIKE ?"; args.append(f"%{request.args['dest_port']}%")
    if request.args.get('order_no'):
        sql += " AND o.order_no LIKE ?"; args.append(f"%{request.args['order_no']}%")
    sql += " ORDER BY lt.create_time DESC"
    rows, total = paginate(db, sql, args, page, size)
    for r in rows:
        r['phase'] = _phase(r['current_node'])
        r['current_name'] = NODE_NAMES[r['current_node']] if r['current_node'] else '未启运'
        r['partners'] = {}
        for col in ('sea_partner_id', 'port_partner_id', 'warehouse_partner_id', 'land_partner_id'):
            if r[col]:
                x = db.execute("SELECT company_name FROM company WHERE company_id=?", (r[col],)).fetchone()
                r['partners'][col] = x['company_name'] if x else None
    # 分布统计
    stats = {'total': 0, 'NOT_STARTED': 0, 'IN_TRANSIT': 0, 'WAREHOUSED': 0, 'DELIVERED': 0}
    for r in db.execute("SELECT current_node FROM logistics_task"):
        stats['total'] += 1
        stats[_phase(r['current_node'])] += 1
    return ok({'list': rows, 'total': total, 'page': page, 'page_size': size, 'stats': stats})


@bp.get('/admin/logistics/<int:lid>')
@roles_required('R4')
def logistics_detail(lid):
    """任务详情：7节点状态 + 单据附件"""
    db = get_db()
    t = _get_task(db, lid)
    if not t:
        return err('物流任务不存在', http=404)
    nodes = []
    for n in db.execute("SELECT * FROM logistics_node WHERE logi_id=? ORDER BY node_code", (lid,)):
        node = dict(n)
        node['attachments'] = [dict(a) for a in db.execute(
            "SELECT id,doc_type,file_url,file_name,upload_time FROM logistics_attachment WHERE node_id=?",
            (n['id'],))]
        nodes.append(node)
    return ok({**_task_vo(db, t), 'nodes': nodes})


@bp.post('/admin/logistics/<int:lid>/rollback')
@roles_required('R4')
def logistics_rollback(lid):
    """管理员授权回退：重置 node_code 之后的节点"""
    d = request.get_json(force=True)
    reason = (d.get('reason') or '').strip()
    if not reason:
        return err('回退原因必填')
    db = get_db()
    t = _get_task(db, lid)
    if not t:
        return err('物流任务不存在', http=404)
    try:
        node_code = int(d.get('node_code'))
    except (TypeError, ValueError):
        return err('node_code 无效')
    if node_code < 0 or node_code > 7:
        return err('node_code 取值 0~7')
    if node_code >= t['current_node']:
        return err('回退目标节点须小于当前已完成节点')
    now = _now()
    db.execute(
        "UPDATE logistics_node SET status='PENDING',actual_time=NULL,operator_id=NULL,done_time=NULL"
        " WHERE logi_id=? AND node_code>? AND status='DONE'", (lid, node_code))
    db.execute("UPDATE logistics_task SET current_node=? WHERE logi_id=?", (node_code, lid))
    db.commit()
    log_action('物流节点回退授权', f"任务回退至N{node_code}，原因: {reason}",
               before=f'N{t["current_node"]}', after=f'N{node_code}', ref_type='logistics_task', ref_id=lid)
    return ok(_task_vo(db, _get_task(db, lid)))


# ================= 配套方端 (R3) =================

@bp.get('/partner/logistics/list')
@roles_required('R3')
@company_approved_required
def partner_task_list():
    """我的物流任务：含本人负责的节点与可推进节点"""
    db = get_db()
    cid = g.current_user['company_id']
    page = int(request.args.get('page', 1)); size = int(request.args.get('page_size', 10))
    sql = ("SELECT lt.*, o.order_no, o.ore_category, o.total_qty, c.company_name AS supplier_name"
           " FROM logistics_task lt"
           " JOIN collective_order o ON o.order_id=lt.order_id"
           " JOIN company c ON c.company_id=o.supplier_id"
           " WHERE (lt.sea_partner_id=? OR lt.port_partner_id=? OR lt.warehouse_partner_id=? OR lt.land_partner_id=?)")
    args = [cid, cid, cid, cid]
    sql += " ORDER BY lt.create_time DESC"
    rows, total = paginate(db, sql, args, page, size)
    owner_col_of = {1: 'sea_partner_id', 2: 'sea_partner_id', 3: 'port_partner_id',
                    4: 'port_partner_id', 5: 'warehouse_partner_id',
                    6: 'land_partner_id', 7: 'land_partner_id'}
    for r in rows:
        r['my_roles'] = []
        for col, role in (('sea_partner_id', '海运方'), ('port_partner_id', '港口方'),
                          ('warehouse_partner_id', '仓储方'), ('land_partner_id', '陆运方')):
            if r[col] == cid:
                r['my_roles'].append(role)
        next_code = min(r['current_node'] + 1, 7)
        r['next_node'] = {'node_code': next_code, 'node_name': NODE_NAMES[next_code]} if r['current_node'] < 7 else None
        r['mine_to_do'] = bool(r['next_node']) and r[owner_col_of[next_code]] == cid
        r['current_name'] = NODE_NAMES[r['current_node']] if r['current_node'] else '未启运'
        r['phase'] = _phase(r['current_node'])
    return ok({'list': rows, 'total': total, 'page': page, 'page_size': size})


@bp.post('/partner/logistics/<int:lid>/advance')
@roles_required('R3')
@company_approved_required
def partner_advance(lid):
    """推进节点：顺序推进不可跳级倒退，可上传单据"""
    d = request.get_json(force=True)
    db = get_db()
    t = _get_task(db, lid)
    if not t:
        return err('物流任务不存在', http=404)
    try:
        code = int(d.get('node_code'))
    except (TypeError, ValueError):
        return err('node_code 无效')
    if code not in NODE_NAMES:
        return err('node_code 取值 1~7')
    expect = t['current_node'] + 1
    if code > expect:
        return err(f'不可跳级推进，下一节点为 N{expect} {NODE_NAMES[expect]}')
    if code <= t['current_node']:
        return err('节点已完成，不可重复推进或倒退')
    owner_col = {1: 'sea_partner_id', 2: 'sea_partner_id', 3: 'port_partner_id',
                 4: 'port_partner_id', 5: 'warehouse_partner_id',
                 6: 'land_partner_id', 7: 'land_partner_id'}[code]
    if not t[owner_col]:
        return err(f'N{code} 未分配负责配套方，请联系平台管理员')
    if t[owner_col] != g.current_user['company_id']:
        return err('该节点不由您负责，无法推进', code=403, http=403)
    actual = (d.get('actual_time') or '').strip() or _now()[:16]
    if not TIME_RE.match(actual):
        return err('实际时间格式应为 YYYY-MM-DD HH:MM')
    if actual > _now()[:16]:
        return err('实际时间不可晚于当前时间')
    atts = d.get('attachments') or []
    if not isinstance(atts, list):
        return err('附件格式错误')
    now = _now()
    node = db.execute("SELECT * FROM logistics_node WHERE logi_id=? AND node_code=?", (lid, code)).fetchone()
    db.execute(
        "UPDATE logistics_node SET status='DONE',actual_time=?,operator_id=?,done_time=? WHERE id=?",
        (actual, g.current_user['user_id'], now, node['id']))
    for a in atts:
        if not a.get('file_url'):
            continue
        db.execute(
            "INSERT INTO logistics_attachment(node_id,doc_type,file_url,file_name,uploader_id,upload_time)"
            " VALUES(?,?,?,?,?,?)",
            (node['id'], (a.get('doc_type') or 'DOC').strip() or 'DOC', a['file_url'],
             a.get('file_name'), g.current_user['user_id'], now))
    db.execute("UPDATE logistics_task SET current_node=? WHERE logi_id=?", (code, lid))
    db.commit()
    # N7 完成送达 → 该订单全部「配送在途」分拨单转为待企业确认（PRD-05/07 联动）
    if code == 7:
        o = db.execute("SELECT order_id FROM logistics_task WHERE logi_id=?", (lid,)).fetchone()
        if o:
            db.execute(
                "UPDATE allocation_order SET status='WAIT_CONFIRM' WHERE order_id=? AND status='TRANSIT'",
                (o['order_id'],))
            db.commit()
    log_action('推进物流节点', f"任务推进至 N{code} {NODE_NAMES[code]}，单据{len([a for a in atts if a.get('file_url')])}份",
               before=f'N{t["current_node"]}', after=f'N{code}', ref_type='logistics_task', ref_id=lid)
    return ok({'logi_id': lid, 'current_node': code, 'node_name': NODE_NAMES[code]})


@bp.get('/partner/logistics/<int:lid>/nodes')
@roles_required('R3')
@company_approved_required
def partner_nodes(lid):
    """配套方查看任务节点明细（限被分配方）"""
    db = get_db()
    t = _get_task(db, lid)
    if not t:
        return err('物流任务不存在', http=404)
    cid = g.current_user['company_id']
    if cid not in (t['sea_partner_id'], t['port_partner_id'], t['warehouse_partner_id'], t['land_partner_id']):
        return err('未分配该任务，无权查看', code=403, http=403)
    nodes = []
    for n in db.execute("SELECT * FROM logistics_node WHERE logi_id=? ORDER BY node_code", (lid,)):
        node = dict(n)
        if n['status'] == 'DONE':
            node['attachments'] = [dict(a) for a in db.execute(
                "SELECT id,doc_type,file_url,file_name,upload_time FROM logistics_attachment WHERE node_id=?",
                (n['id'],))]
        nodes.append(node)
    return ok({**_task_vo(db, t), 'nodes': nodes})


# ================= 时间线与下游只读 =================

@bp.get('/logistics/order/<int:oid>/timeline')
@roles_required('R4', 'R3')
def order_timeline(oid):
    """订单物流时间线：R4 全量；R3 仅被分配任务"""
    db = get_db()
    t = db.execute("SELECT * FROM logistics_task WHERE order_id=?", (oid,)).fetchone()
    if not t:
        return err('该订单暂无物流任务', http=404)
    if g.current_user['role_code'] == 'R3' and g.current_user['company_id'] not in (
            t['sea_partner_id'], t['port_partner_id'], t['warehouse_partner_id'], t['land_partner_id']):
        return err('未分配该任务，无权查看', code=403, http=403)
    nodes = [dict(n) for n in db.execute(
        "SELECT node_code,node_name,status,actual_time,done_time FROM logistics_node"
        " WHERE logi_id=? ORDER BY node_code", (t['logi_id'],))]
    return ok({**_task_vo(db, t), 'nodes': nodes})


@bp.get('/company/logistics/list')
@roles_required('R1')
@company_approved_required
def company_logistics():
    """下游企业只读：归属自己分拨单的物流进度（仅陆运配送节点，隐藏上游海运细节）"""
    db = get_db()
    cid = g.current_user['company_id']
    rows = []
    for a in db.execute("SELECT * FROM allocation_order WHERE company_id=? ORDER BY create_time DESC", (cid,)):
        t = db.execute("SELECT * FROM logistics_task WHERE order_id=?", (a['order_id'],)).fetchone()
        item = {'alloc_no': a['alloc_no'], 'ore_category': a['ore_category'], 'qty': a['qty'],
                'destination': a['destination'], 'status': a['status'],
                'logistics': None}
        if t:
            land_nodes = [dict(n) for n in db.execute(
                "SELECT node_code,node_name,status,actual_time FROM logistics_node"
                " WHERE logi_id=? AND node_code IN (6,7) ORDER BY node_code", (t['logi_id'],))]
            item['logistics'] = {
                'logi_no': t['logi_no'],
                'dest_place': t['dest_place'],
                'nodes': land_nodes,
                'phase': _phase(t['current_node'])
            }
        rows.append(item)
    return ok({'list': rows})
