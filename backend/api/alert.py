"""预警接口（PRD 4.8/T16）：预警列表检索与人工处理。

可见范围：平台看全部；业务方只能看到 company_ids 包含本企业的预警。
处理：运营登记处理中（PROCESSING）/ 填原因关闭（CLOSED）；
在途超时等自动关闭场景由定时任务与业务动作触发（alerts.py）。
"""
from flask import g

from ..common import ApiError, get_params, ok, page_args, page_data, require_fields
from ..db import execute, q1, qall
from ..security import auth_required
from ..state_machine import transition
from . import bp

_ALERT_LIST_SQL = """
SELECT a.id, a.alert_no AS "alertNo", a.alert_type AS "alertType",
       a.biz_type AS "bizType", a.biz_id AS "bizId",
       a.company_ids AS "companyIds", a.content,
       a.handler_remark AS "handlerRemark", a.handler_id AS "handlerId",
       a.handled_at AS "handledAt", a.status, a.created_at AS "createdAt"
FROM biz_alert a
"""


@bp.get('/alerts')
@auth_required
def list_alerts():
    p = get_params()
    page, size = page_args(p)
    where = ['a.is_deleted=0']
    args = []
    if not g.ctx.is_plat:
        if not g.ctx.company:
            return ok(page_data([], 0, page, size))
        # company_ids 为逗号分隔文本，用位置匹配避免前缀误命中
        where.append("position(',' || %s || ',' in ',' || coalesce(a.company_ids,'') || ',') > 0")
        args.append(str(g.ctx.company['id']))
    if p.get('alertType'):
        where.append('a.alert_type=%s')
        args.append(p['alertType'])
    if p.get('status'):
        where.append('a.status=%s')
        args.append(p['status'])
    if p.get('bizType'):
        where.append('a.biz_type=%s')
        args.append(p['bizType'])
    if p.get('bizId'):
        where.append('a.biz_id=%s')
        args.append(p['bizId'])
    w = ' AND '.join(where)
    total = q1(g.conn, "SELECT count(*) AS c FROM biz_alert a WHERE " + w, args)['c']
    rows = qall(
        g.conn,
        _ALERT_LIST_SQL + "WHERE " + w + " ORDER BY a.created_at DESC, a.id DESC LIMIT %s OFFSET %s",
        args + [size, (page - 1) * size],
    )
    return ok(page_data(rows, total, page, size))


@bp.get('/alerts/<int:aid>')
@auth_required
def alert_detail(aid):
    row = q1(g.conn, _ALERT_LIST_SQL + "WHERE a.id=%s AND a.is_deleted=0", (aid,))
    if not row:
        raise ApiError(40401, '预警不存在')
    if not g.ctx.is_plat:
        ids = (row['companyIds'] or '').split(',')
        if not g.ctx.company or str(g.ctx.company['id']) not in ids:
            raise ApiError(40301, '无权限查看该预警')
    return ok(row)


@bp.put('/alerts/<int:aid>/handle')
@auth_required
def handle_alert(aid):
    """人工处理：action=PROCESSING 登记处理中 / action=CLOSE 关闭（须填 handlerRemark）。

    平台运营可处理任意预警；预警通知企业（QTY_DIFF 双方确认等场景）也可填写处理意见。
    """
    row = q1(g.conn, "SELECT * FROM biz_alert WHERE id=%s AND is_deleted=0", (aid,))
    if not row:
        raise ApiError(40401, '预警不存在')
    ids = (row['company_ids'] or '').split(',')
    is_related = g.ctx.company and str(g.ctx.company['id']) in ids
    if not g.ctx.is_plat and not is_related:
        raise ApiError(40301, '无权限处理该预警')
    p = get_params()
    action = p.get('action')
    if action not in ('PROCESSING', 'CLOSE'):
        raise ApiError(40001, 'action 须为 PROCESSING 或 CLOSE')
    to_status = 'PROCESSING' if action == 'PROCESSING' else 'CLOSED'
    remark = p.get('handlerRemark') or p.get('remark') or ''
    if to_status == 'CLOSED' and not remark.strip():
        raise ApiError(40001, '关闭预警必须填写处理意见')
    transition(g.conn, g.ctx, 'biz_alert', '预警', 'biz_alert', aid, to_status)
    execute(
        g.conn,
        """
        UPDATE biz_alert SET handler_remark=%s, handler_id=%s,
               handled_at=COALESCE(handled_at, now()), updated_at=now()
        WHERE id=%s
        """,
        (remark or None, g.ctx.user['id'], aid),
    )
    return ok({'id': aid, 'status': to_status})
