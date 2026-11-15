"""站内消息接口（PRD 4.10/一期简化项）：消息列表、分类筛选、已读标记与待办任务。"""
from flask import g

from ..common import ApiError, get_params, ok, page_args, page_data
from ..db import execute, q1, qall
from ..security import auth_required
from . import bp

MSG_CATEGORIES = ('NOTICE', 'WARN', 'ANNOUNCE', 'ACTIVITY')


@bp.get('/messages')
@auth_required
def list_messages():
    if not g.ctx.company and not g.ctx.is_plat:
        return ok({'list': [], 'total': 0, 'page': 1, 'size': 10, 'unread': 0})
    p = get_params()
    page, size = page_args(p)
    # 平台管理员收平台消息（receiver_company_id 为空）；企业收本企业消息 + 平台广播（公告/活动/预警等）
    if g.ctx.is_plat:
        where = 'receiver_company_id IS NULL'
        args = []
    else:
        where = '(receiver_company_id=%s OR receiver_company_id IS NULL)'
        args = [g.ctx.company['id']]
    if p.get('isRead') in ('0', '1'):
        where += ' AND is_read=%s'
        args.append(int(p['isRead']))
    if p.get('category') in MSG_CATEGORIES:
        where += ' AND msg_category=%s'
        args.append(p['category'])
    total = q1(g.conn, "SELECT count(*) AS c FROM sys_message WHERE " + where, args)['c']
    unread = q1(g.conn,
                "SELECT count(*) AS c FROM sys_message WHERE " + where + ("" if p.get('isRead') in ('0', '1') else " AND is_read=0"),
                args)['c']
    rows = qall(g.conn, """
        SELECT id, receiver_company_id AS "receiverCompanyId", title, content,
               biz_type AS "bizType", biz_id AS "bizId", is_read AS "isRead",
               msg_category AS "msgCategory", created_at AS "createdAt"
        FROM sys_message WHERE """ + where + " ORDER BY id DESC LIMIT %s OFFSET %s",
        args + [size, (page - 1) * size])
    data = page_data(rows, total, page, size)
    data['unread'] = unread
    return ok(data)


@bp.put('/messages/<int:mid>/read')
@auth_required
def mark_read(mid):
    row = q1(g.conn, "SELECT receiver_company_id FROM sys_message WHERE id=%s", (mid,))
    if not row:
        raise ApiError(40401, '消息不存在')
    # 平台广播消息（receiver_company_id 为空）所有端均可标记已读；企业消息仅本企业可操作
    if (not g.ctx.is_plat and row['receiver_company_id'] is not None
            and (not g.ctx.company or g.ctx.company['id'] != row['receiver_company_id'])):
        raise ApiError(40301, '无权限操作该消息')
    execute(g.conn, "UPDATE sys_message SET is_read=1 WHERE id=%s", (mid,))
    return ok({'id': mid, 'isRead': 1})


@bp.put('/messages/read-all')
@auth_required
def mark_all_read():
    """一键全读：平台读全部平台消息，企业读本企业全部未读消息。"""
    if g.ctx.is_plat:
        n = execute(g.conn,
                    "UPDATE sys_message SET is_read=1 WHERE receiver_company_id IS NULL AND is_read=0")
        return ok({'updated': n})
    if not g.ctx.company:
        return ok({'updated': 0})
    n = execute(g.conn,
                "UPDATE sys_message SET is_read=1 WHERE (receiver_company_id=%s OR receiver_company_id IS NULL) AND is_read=0",
                (g.ctx.company['id'],))
    return ok({'updated': n})


@bp.get('/tasks/todos')
@auth_required
def list_todos():
    """任务中心（box=todo 待办任务 / done 已办任务 / doing 在办申请 / applied 已办申请）。

    返回扁平列表：[{bizType, bizId, title, createdAt, hash}]，前端点击后跳转 hash。
    """
    box = get_params().get('box')
    if box not in ('todo', 'done', 'doing', 'applied'):
        box = 'todo'
    cid = g.ctx.company['id'] if g.ctx.company else None
    roles = g.ctx.roles or []
    tasks = []

    def add(biz_type, biz_id, title, created_at, hash_url):
        tasks.append({'bizType': biz_type, 'bizId': biz_id, 'title': title,
                      'createdAt': created_at, 'hash': hash_url})

    BIZ_LABEL = {'CONTRACT': '合同', 'COMPANY': '企业准入', 'WAYBILL': '运单',
                 'ORDER': '订单', 'SETTLEMENT': '结算单', 'INQUIRY': '询价单',
                 'DEMAND': '需求', 'ALERT': '预警'}
    # 操作日志 biz_type 存的是表名，统一映射为标准业务类型
    TYPE_OF_TABLE = {'biz_order': 'ORDER', 'biz_contract': 'CONTRACT', 'biz_waybill': 'WAYBILL',
                     'biz_settlement': 'SETTLEMENT', 'biz_inquiry': 'INQUIRY', 'biz_quote': 'INQUIRY',
                     'biz_bargain': 'INQUIRY', 'biz_demand': 'DEMAND', 'ent_company': 'COMPANY',
                     'biz_alert': 'ALERT', 'biz_aggregated_order': 'ORDER', 'biz_aggregated_demand': 'DEMAND'}

    def hash_of(biz_type):
        """按业务类型 + 当前角色返回跳转页。"""
        if g.ctx.is_plat:
            return {'CONTRACT': '#/contract-admin', 'COMPANY': '#/admin-companies',
                    'WAYBILL': '#/logistics-dispatch', 'ORDER': '#/logistics-dispatch',
                    'SETTLEMENT': '#/settlement-stats', 'INQUIRY': '#/quote-inquiry',
                    'DEMAND': '#/demand-pool'}.get(biz_type, '')
        if 'LOGISTICS_CARRIER' in roles:
            return '#/waybill'
        if 'SUPPLIER' in roles:
            return {'CONTRACT': '#/contract', 'ORDER': '#/order', 'SETTLEMENT': '#/settlement',
                    'INQUIRY': '#/inquiry', 'DEMAND': '#/inquiry'}.get(biz_type, '')
        return {'CONTRACT': '#/contract', 'ORDER': '#/order', 'SETTLEMENT': '#/settlement',
                'WAYBILL': '#/track', 'DEMAND': '#/demand'}.get(biz_type, '')

    if box == 'done':
        # 已办任务：我的操作留痕（最近 50 条）
        rows = qall(g.conn, """
            SELECT id, biz_type, biz_id, action, created_at FROM sys_operation_log
            WHERE user_id=%s ORDER BY id DESC LIMIT 50""", (g.ctx.user['id'],))
        for r in rows:
            act = str(r['action'] or '')
            if act.startswith('STATUS '):
                act = '状态 ' + act[7:]
            std = TYPE_OF_TABLE.get(r['biz_type'] or '', r['biz_type'] or '')
            label = BIZ_LABEL.get(std, std or '操作')
            add(std, r['biz_id'], '%s办理：%s' % (label, act), r['created_at'], hash_of(std))
        tasks.sort(key=lambda x: str(x['createdAt'] or ''), reverse=True)
        return ok({'list': tasks, 'total': len(tasks)})

    if box in ('doing', 'applied'):
        # 在办申请 / 已办申请：与我相关的单据按状态归类（平台可见全部）
        doing = box == 'doing'
        cond = {
            'CONTRACT': ("c.status IN ('PENDING_GENERATE','PENDING_BUYER','PENDING_SUPPLIER')"
                         if doing else "c.status IN ('EFFECTIVE','VOID')"),
            'ORDER': ("o.status IN ('PENDING_CONFIRM','PENDING_CONTRACT','PENDING_EFFECT','PERFORMING')"
                      if doing else "o.status IN ('COMPLETED','CANCELLED')"),
        }
        scope = '' if g.ctx.is_plat else ' AND (o.buyer_id=%s OR o.supplier_id=%s)'
        sargs = [] if g.ctx.is_plat else [cid, cid]
        for r in qall(g.conn, """
                SELECT c.id, c.contract_no AS t, c.created_at FROM biz_contract c
                JOIN biz_order o ON o.id=c.order_id
                WHERE c.is_deleted=0 AND """ + cond['CONTRACT'] + scope +
                " ORDER BY c.id DESC LIMIT 20", sargs):
            add('CONTRACT', r['id'], BIZ_LABEL['CONTRACT'] + '：' + r['t'], r['created_at'], hash_of('CONTRACT'))
        for r in qall(g.conn, """
                SELECT id, order_no AS t, created_at FROM biz_order o
                WHERE is_deleted=0 AND """ + cond['ORDER'] + scope +
                " ORDER BY id DESC LIMIT 20", sargs):
            add('ORDER', r['id'], BIZ_LABEL['ORDER'] + '：' + r['t'], r['created_at'], hash_of('ORDER'))
        wscope = '' if g.ctx.is_plat else \
            ' AND (w.carrier_id=%s OR EXISTS (SELECT 1 FROM biz_order o WHERE o.id=w.order_id AND (o.buyer_id=%s OR o.supplier_id=%s)))'
        wargs = [] if g.ctx.is_plat else [cid, cid, cid]
        # 运单（in 子句需要按 doing/applied 拼接）
        wstat = ("IN ('PENDING_ASSIGN','PENDING_ACCEPT','PENDING_DEPART','IN_TRANSIT','ARRIVED')"
                 if doing else "IN ('SIGNED','CANCELLED')")
        for r in qall(g.conn, """
                SELECT w.id, w.waybill_no AS t, w.created_at FROM biz_waybill w
                WHERE w.is_deleted=0 AND w.status """ + wstat + wscope +
                " ORDER BY w.id DESC LIMIT 20", wargs):
            add('WAYBILL', r['id'], BIZ_LABEL['WAYBILL'] + '：' + r['t'], r['created_at'], hash_of('WAYBILL'))
        for r in qall(g.conn, """
                SELECT s.id, s.settle_no AS t, s.created_at FROM biz_settlement s
                JOIN biz_order o ON o.id=s.order_id
                WHERE s.is_deleted=0 AND s.status """ +
                ("IN ('PENDING_CONFIRM_SUPPLIER','PENDING_CONFIRM_BUYER')" if doing
                 else "IN ('CONFIRMED','COMPLETED')") + scope +
                " ORDER BY s.id DESC LIMIT 20", sargs):
            add('SETTLEMENT', r['id'], BIZ_LABEL['SETTLEMENT'] + '：' + r['t'], r['created_at'], hash_of('SETTLEMENT'))
        if g.ctx.is_plat:
            for r in qall(g.conn, """
                    SELECT id, company_name AS t, created_at FROM ent_company
                    WHERE is_deleted=0 AND audit_status """ +
                    ("='PENDING'" if doing else "IN ('APPROVED','REJECTED')") +
                    " ORDER BY id DESC LIMIT 20"):
                add('COMPANY', r['id'], BIZ_LABEL['COMPANY'] + '：' + r['t'], r['created_at'], hash_of('COMPANY'))
        tasks.sort(key=lambda x: str(x['createdAt'] or ''), reverse=True)
        return ok({'list': tasks, 'total': len(tasks)})

    # box=todo：按角色聚合待处理项
    if g.ctx.is_plat:
        # 运营端：待核验合同 / 待审核企业准入 / 待指派运单
        for r in qall(g.conn, """
                SELECT id, contract_no AS t, created_at FROM biz_contract
                WHERE plat_status='PENDING' AND is_deleted=0 ORDER BY id DESC LIMIT 20"""):
            add('CONTRACT', r['id'], '合同待核验：' + r['t'], r['created_at'], '#/contract-admin')
        for r in qall(g.conn, """
                SELECT id, company_name AS t, created_at FROM ent_company
                WHERE audit_status='PENDING' AND is_deleted=0 ORDER BY id DESC LIMIT 20"""):
            add('COMPANY', r['id'], '企业准入待审核：' + r['t'], r['created_at'], '#/admin-companies')
        for r in qall(g.conn, """
                SELECT id, waybill_no AS t, created_at FROM biz_waybill
                WHERE status='PENDING_ASSIGN' AND is_deleted=0 ORDER BY id DESC LIMIT 20"""):
            add('WAYBILL', r['id'], '运单待指派承运商：' + r['t'], r['created_at'], '#/logistics-dispatch')
    elif cid:
        if 'STEEL_BUYER' in roles:
            for r in qall(g.conn, """
                    SELECT id, order_no AS t, created_at FROM biz_order
                    WHERE buyer_id=%s AND status='PENDING_CONFIRM' AND is_deleted=0
                    ORDER BY id DESC LIMIT 20""", (cid,)):
                add('ORDER', r['id'], '订单待确认：' + r['t'], r['created_at'], '#/order')
            for r in qall(g.conn, """
                    SELECT c.id, c.contract_no AS t, c.created_at FROM biz_contract c
                    JOIN biz_order o ON o.id=c.order_id
                    WHERE o.buyer_id=%s AND c.status='PENDING_BUYER' AND c.is_deleted=0
                    ORDER BY c.id DESC LIMIT 20""", (cid,)):
                add('CONTRACT', r['id'], '合同待签署（需方）：' + r['t'], r['created_at'], '#/contract')
            for r in qall(g.conn, """
                    SELECT s.id, s.settle_no AS t, s.created_at FROM biz_settlement s
                    JOIN biz_order o ON o.id=s.order_id
                    WHERE o.buyer_id=%s AND s.status='PENDING_CONFIRM_BUYER' AND s.is_deleted=0
                    ORDER BY s.id DESC LIMIT 20""", (cid,)):
                add('SETTLEMENT', r['id'], '结算单待确认：' + r['t'], r['created_at'], '#/settlement')
        if 'SUPPLIER' in roles:
            for r in qall(g.conn, """
                    SELECT i.id, i.inquiry_no AS t, i.created_at FROM biz_inquiry_invite inv
                    JOIN biz_inquiry i ON i.id=inv.inquiry_id
                    WHERE inv.supplier_id=%s AND inv.status='INVITED' AND inv.is_deleted=0
                    ORDER BY inv.id DESC LIMIT 20""", (cid,)):
                add('INQUIRY', r['id'], '询价待报价：' + r['t'], r['created_at'], '#/inquiry')
            for r in qall(g.conn, """
                    SELECT c.id, c.contract_no AS t, c.created_at FROM biz_contract c
                    JOIN biz_order o ON o.id=c.order_id
                    WHERE o.supplier_id=%s AND c.status='PENDING_SUPPLIER' AND c.is_deleted=0
                    ORDER BY c.id DESC LIMIT 20""", (cid,)):
                add('CONTRACT', r['id'], '合同待签署（供方）：' + r['t'], r['created_at'], '#/contract')
            for r in qall(g.conn, """
                    SELECT s.id, s.settle_no AS t, s.created_at FROM biz_settlement s
                    JOIN biz_order o ON o.id=s.order_id
                    WHERE o.supplier_id=%s AND s.status='PENDING_CONFIRM_SUPPLIER' AND s.is_deleted=0
                    ORDER BY s.id DESC LIMIT 20""", (cid,)):
                add('SETTLEMENT', r['id'], '结算单待确认：' + r['t'], r['created_at'], '#/settlement')
        if 'LOGISTICS_CARRIER' in roles:
            for r in qall(g.conn, """
                    SELECT id, waybill_no AS t, created_at FROM biz_waybill
                    WHERE carrier_id=%s AND status='PENDING_ACCEPT' AND is_deleted=0
                    ORDER BY id DESC LIMIT 20""", (cid,)):
                add('WAYBILL', r['id'], '运单待接单：' + r['t'], r['created_at'], '#/waybill')
            for r in qall(g.conn, """
                    SELECT id, waybill_no AS t, created_at FROM biz_waybill
                    WHERE carrier_id=%s AND status='PENDING_DEPART' AND is_deleted=0
                    ORDER BY id DESC LIMIT 20""", (cid,)):
                add('WAYBILL', r['id'], '运单待发运：' + r['t'], r['created_at'], '#/waybill')
    tasks.sort(key=lambda x: str(x['createdAt'] or ''), reverse=True)
    return ok({'list': tasks, 'total': len(tasks)})
