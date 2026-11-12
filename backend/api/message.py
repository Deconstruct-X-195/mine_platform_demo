"""站内消息接口（PRD 4.10/一期简化项）：消息列表与已读标记。"""
from flask import g

from ..common import ApiError, get_params, ok, page_args, page_data
from ..db import execute, q1, qall
from ..security import auth_required
from . import bp


@bp.get('/messages')
@auth_required
def list_messages():
    if not g.ctx.company and not g.ctx.is_plat:
        return ok({'list': [], 'total': 0, 'page': 1, 'size': 10, 'unread': 0})
    p = get_params()
    page, size = page_args(p)
    # 平台管理员收平台消息（receiver_company_id 为空）；企业收本企业消息
    if g.ctx.is_plat:
        where = 'receiver_company_id IS NULL'
        args = []
    else:
        where = 'receiver_company_id=%s'
        args = [g.ctx.company['id']]
    if p.get('isRead') in ('0', '1'):
        where += ' AND is_read=%s'
        args.append(int(p['isRead']))
    total = q1(g.conn, "SELECT count(*) AS c FROM sys_message WHERE " + where, args)['c']
    unread = q1(g.conn,
                "SELECT count(*) AS c FROM sys_message WHERE " + where + ("" if p.get('isRead') in ('0', '1') else " AND is_read=0"),
                args)['c']
    rows = qall(g.conn, """
        SELECT id, receiver_company_id AS "receiverCompanyId", title, content,
               biz_type AS "bizType", biz_id AS "bizId", is_read AS "isRead",
               created_at AS "createdAt"
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
    if not g.ctx.is_plat and (not g.ctx.company or g.ctx.company['id'] != row['receiver_company_id']):
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
                "UPDATE sys_message SET is_read=1 WHERE receiver_company_id=%s AND is_read=0",
                (g.ctx.company['id'],))
    return ok({'updated': n})
