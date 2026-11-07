"""议价（PRD 4.5/T11）：多轮还价（上限10轮）、接受/拒绝、轮次冻结。

规则：一方接受即议价结束，对方再提交还价返回"议价已结束"；
定标仅在 ACCEPTED 时允许；同报价轮次序号自1递增，上限10轮。
"""
from flask import g

from ..common import (ApiError, get_params, json_payload, ok, op_log,
                      parse_date, require_fields)
from ..db import execute, qall, q1
from ..security import ROLE_STEEL, ROLE_SUPPLIER, auth_required, roles_required
from ..state_machine import transition
from . import bp


def _bargain_target_role(initiator):
    """发起轮次方为 ctx 角色；响应方为另一角色。"""
    return 'SUPPLIER' if initiator == 'BUYER' else 'BUYER'


@bp.post('/bargains')
@auth_required
def create_bargain():
    p = get_params()
    require_fields(p, 'quoteId')
    quote = q1(g.conn, """
        SELECT q.*, i.buyer_id, i.status AS inquiry_status
        FROM biz_quote q JOIN biz_inquiry i ON i.id=q.inquiry_id
        WHERE q.id=%s AND q.is_deleted=0
        """, (p['quoteId'],))
    if not quote:
        raise ApiError(40401, '报价不存在')
    if quote['status'] not in ('REVEALED', 'BARGAINING'):
        raise ApiError(40901, '报价状态为 %s，不可发起议价' % quote['status'])
    is_buyer = g.ctx.company and quote['buyer_id'] == g.ctx.company['id']
    is_supplier = g.ctx.company and quote['supplier_id'] == g.ctx.company['id']
    if not (is_buyer or is_supplier):
        raise ApiError(40301, '只有报价双方可发起议价')

    rounds = qall(g.conn, "SELECT * FROM biz_bargain WHERE quote_id=%s AND is_deleted=0 ORDER BY round_no",
                  (p['quoteId'],))
    for r in rounds:
        if r['status'] == 'PENDING':
            target = _bargain_target_role(r['initiator'])
            me = 'BUYER' if is_buyer else 'SUPPLIER'
            if me != target:
                raise ApiError(40901, '第 %d 轮待响应，先处理在途议价轮次' % r['round_no'])
            # 对方已在途轮次，我方再发还价即"还回"（新一轮）
            break
    round_no = (rounds[-1]['round_no'] + 1) if rounds else 1
    if round_no > 10:
        raise ApiError(40901, '议价轮次已达上限 10 轮')
    initiator = 'BUYER' if is_buyer else 'SUPPLIER'

    bid = execute(g.conn, """
        INSERT INTO biz_bargain (quote_id, inquiry_id, round_no, initiator, price, quantity,
            delivery_date, settle_type, extra_terms, status, created_by)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,'PENDING',%s) RETURNING id
        """, (p['quoteId'], quote['inquiry_id'], round_no, initiator, p.get('price'),
              p.get('quantity'), parse_date(p, 'deliveryDate', required=False),
              p.get('settleType'), p.get('extraTerms'), g.ctx.user['id']), returning_id=True)
    if quote['status'] == 'REVEALED':
        execute(g.conn, "UPDATE biz_quote SET status='BARGAINING', updated_at=now() WHERE id=%s", (p['quoteId'],))
    if quote['inquiry_status'] == 'CLOSED':
        transition(g.conn, g.ctx, 'biz_inquiry', '询价单', 'biz_inquiry', quote['inquiry_id'], 'BARGAINING')
    op_log(g.conn, g.ctx, 'biz_bargain', bid, 'CREATE',
           None, {'quoteId': p['quoteId'], 'roundNo': round_no, 'initiator': initiator})
    return ok({'id': bid, 'roundNo': round_no, 'status': 'PENDING', 'targetRole': _bargain_target_role(initiator)})


@bp.get('/bargains')
@auth_required
def list_bargains():
    """按报价列轮次（双方可见）。?quoteId= 必填。"""
    from flask import request
    p = request.args.to_dict()
    require_fields(p, 'quoteId')
    quote = q1(g.conn, """
        SELECT q.id, q.supplier_id, i.buyer_id FROM biz_quote q
        JOIN biz_inquiry i ON i.id=q.inquiry_id WHERE q.id=%s AND q.is_deleted=0
        """, (p['quoteId'],))
    if not quote:
        raise ApiError(40401, '报价不存在')
    if not (g.ctx.is_plat or (g.ctx.company and quote['supplier_id'] == g.ctx.company['id'])
            or (g.ctx.company and quote['buyer_id'] == g.ctx.company['id'])):
        raise ApiError(40301, '只有报价双方可查看议价记录')
    rows = qall(g.conn, """
        SELECT id, quote_id AS "quoteId", round_no AS "roundNo", initiator, price, quantity,
               delivery_date AS "deliveryDate", settle_type AS "settleType",
               extra_terms AS "extraTerms", status, created_at AS "createdAt"
        FROM biz_bargain WHERE quote_id=%s AND is_deleted=0 ORDER BY round_no DESC
        """, (p['quoteId'],))
    return ok({'list': json_payload(rows)})


def _respond_check(bid):
    """校验响应方：仅报价双方可响应，且不能响应自己发起的轮次。返回 (row, is_buyer)。"""
    row = q1(g.conn, "SELECT * FROM biz_bargain WHERE id=%s AND is_deleted=0", (bid,))
    if not row:
        raise ApiError(40401, '议价轮次不存在')
    if row['status'] != 'PENDING':
        raise ApiError(40901, '议价已结束（%s）' % row['status'])
    quote = q1(g.conn, """
        SELECT q.supplier_id, i.buyer_id FROM biz_quote q
        JOIN biz_inquiry i ON i.id=q.inquiry_id WHERE q.id=%s
        """, (row['quote_id'],))
    is_buyer = g.ctx.company and quote['buyer_id'] == g.ctx.company['id']
    is_supplier = g.ctx.company and quote['supplier_id'] == g.ctx.company['id']
    if not (is_buyer or is_supplier):
        raise ApiError(40301, '只有报价双方可响应议价')
    me = 'BUYER' if is_buyer else 'SUPPLIER'
    if me == row['initiator']:
        raise ApiError(40301, '发起方不能自答，请等待对方响应')
    return row


@bp.put('/bargains/<int:bid>/accept')
@auth_required
def accept_bargain(bid):
    row = _respond_check(bid)
    transition(g.conn, g.ctx, 'biz_bargain', '议价轮次', 'biz_bargain', bid, 'ACCEPTED')
    # 一方接受即议价结束：同报价其余 PENDING 轮次置 EXPIRED
    execute(g.conn, "UPDATE biz_bargain SET status='EXPIRED', updated_at=now() WHERE quote_id=%s AND status='PENDING'", (row['quote_id'],))
    return ok({'id': bid, 'status': 'ACCEPTED'})


@bp.put('/bargains/<int:bid>/reject')
@auth_required
def reject_bargain(bid):
    row = _respond_check(bid)
    transition(g.conn, g.ctx, 'biz_bargain', '议价轮次', 'biz_bargain', bid, 'REJECTED')
    return ok({'id': bid, 'status': 'REJECTED'})
