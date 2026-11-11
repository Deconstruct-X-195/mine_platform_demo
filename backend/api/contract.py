"""电子合同（PRD 4.6/T13）：生成、需方先签/供方后签、SHA-256 留痕、作废重签。

平台内实名确认（signature_type 固定 PLATFORM_CONFIRM，预留 CA）；
签署需签署人姓名 + 勾选已核对 + 盖章件上传；生效后条款不可修改，只能作废重签。
"""
import hashlib
import os

from flask import g

from ..common import (ApiError, doc_no, get_params, json_payload, ok, op_log,
                      require_fields, send_msg)
from ..db import execute, qall, q1
from ..security import ROLE_STEEL, ROLE_SUPPLIER, auth_required, roles_required
from .. import UPLOAD_DIR
from ..state_machine import transition
from . import bp


def _get(oid):
    row = q1(g.conn, "SELECT * FROM biz_order WHERE id=%s AND is_deleted=0", (oid,))
    if not row:
        raise ApiError(40401, '订单不存在')
    if not g.ctx.is_plat and (not g.ctx.company or g.ctx.company['id'] not in (row['buyer_id'], row['supplier_id'])):
        raise ApiError(40301, '无权限访问该订单')
    return row


@bp.post('/orders/<int:oid>/contract/generate')
@roles_required(ROLE_STEEL)
def generate(oid):
    row = _get(oid)
    if row['status'] != 'PENDING_CONTRACT':
        raise ApiError(40901, '订单状态为 %s，不可生成合同' % row['status'])
    max_v = q1(g.conn, "SELECT coalesce(max(version),0) AS v FROM biz_contract WHERE order_id=%s AND is_deleted=0", (oid,))['v']
    version = max_v + 1
    cid = execute(g.conn, """
        INSERT INTO biz_contract (contract_no, order_id, version, signature_type, status, created_by, updated_by)
        VALUES (%s,%s,%s,'PLATFORM_CONFIRM','PENDING_GENERATE',%s,%s) RETURNING id
        """, (doc_no(g.conn, 'HT'), oid, version, g.ctx.user['id'], g.ctx.user['id']), returning_id=True)
    transition(g.conn, g.ctx, 'biz_contract', '合同', 'biz_contract', cid, 'PENDING_BUYER',
               node_biz_type='ORDER', node_code='CONTRACT_GENERATED', node_biz_id=row['id'])
    transition(g.conn, g.ctx, 'biz_order', '订单', 'biz_order', oid, 'PENDING_EFFECT')
    send_msg(g.conn, row['buyer_id'], '合同待签署（需方）',
             '订单 %s 合同 v%d 已生成，请需求方首先签署。' % (row['order_no'], version), 'CONTRACT', cid)
    op_log(g.conn, g.ctx, 'biz_contract', cid, 'GENERATE', None, {'version': version})
    return ok({'contractId': cid, 'version': version, 'status': 'PENDING_BUYER'})


def _contract(cid):
    row = q1(g.conn, "SELECT * FROM biz_contract WHERE id=%s AND is_deleted=0", (cid,))
    if not row:
        raise ApiError(40401, '合同不存在')
    order = q1(g.conn, "SELECT * FROM biz_order WHERE id=%s AND is_deleted=0", (row['order_id'],))
    if not g.ctx.is_plat and (not g.ctx.company or g.ctx.company['id'] not in (order['buyer_id'], order['supplier_id'])):
        raise ApiError(40301, '无权限访问该合同')
    return row, order


@bp.post('/contracts/<int:cid>/sign')
@auth_required
def sign(cid):
    p = get_params()
    require_fields(p, 'signerName', 'confirm', 'fileId')
    if str(p['confirm']).lower() not in ('true', '1'):
        raise ApiError(40001, '必须勾选"已核对条款"')
    row, order = _contract(cid)
    is_buyer = g.ctx.company and order['buyer_id'] == g.ctx.company['id']
    is_supplier = g.ctx.company and order['supplier_id'] == g.ctx.company['id']
    if row['status'] == 'PENDING_BUYER' and is_buyer:
        col, user_col = 'buyer_sign_at', 'buyer_sign_user'
        to = 'PENDING_SUPPLIER'
        role_label = '需方'
    elif row['status'] == 'PENDING_SUPPLIER' and is_supplier:
        col, user_col = 'supplier_sign_at', 'supplier_sign_user'
        to = None  # 双方签齐后不自动生效：进入"待运营确认"，由运营端核验生效
        role_label = '供方'
    elif row['status'] == 'PENDING_SUPPLIER' and is_buyer and row['plat_status'] == 'RETURNED':
        col, user_col = 'buyer_sign_at', 'buyer_sign_user'
        to = None  # 扫描件被运营退回，需方重传（重新进入待核验）
        role_label = '需方(重传)'
    else:
        raise ApiError(40901, '当前不可签署（合同 %s / 本方角色不符，需方先签、供方后签）' % row['status'])

    f = q1(g.conn, "SELECT * FROM sys_file WHERE file_id=%s AND is_deleted=0", (p['fileId'],))
    if not f:
        raise ApiError(40401, '盖章件不存在，请先上传')
    if f['content_type'] and not (f['content_type'].startswith('application/pdf')
                                  or f['content_type'].startswith('image/')):
        raise ApiError(40001, '盖章件仅支持 pdf/jpg/png')
    sha = _file_sha256(f['path'])
    execute(g.conn, """
        UPDATE biz_contract SET file_url=%s, file_hash=%s, {col}=now(), {ucol}=%s, updated_by=%s
        WHERE id=%s
        """.format(col=col, ucol=user_col),
        (f['file_id'], sha, g.ctx.user['id'], g.ctx.user['id'], cid))
    if to is None:
        # 双方签齐（或退回重传）→ 待运营确认，合同状态保持 PENDING_SUPPLIER
        execute(g.conn, "UPDATE biz_contract SET plat_status='PENDING', updated_by=%s WHERE id=%s",
                (g.ctx.user['id'], cid))
        text = '订单 %s 合同 %s 双方已签署，待平台核验后生效。' % (order['order_no'], row['contract_no'])
        send_msg(g.conn, order['supplier_id'], '合同签署完成', text, 'CONTRACT', cid)
        send_msg(g.conn, order['buyer_id'], '合同签署完成', text, 'CONTRACT', cid)
    else:
        transition(g.conn, g.ctx, 'biz_contract', '合同', 'biz_contract', cid, to,
                   node_biz_type='ORDER', node_code='CONTRACT_BUYER_SIGNED',
                   node_biz_id=order['id'])
        send_msg(g.conn, order['supplier_id'], '合同待签署（供方）',
                 '订单 %s 合同 %s 需方已签署，请供方签署。' % (order['order_no'], row['contract_no']), 'CONTRACT', cid)
    op_log(g.conn, g.ctx, 'biz_contract', cid, 'SIGN(%s)' % role_label,
           None, {'signerName': p['signerName'], 'fileSha256': sha})
    return ok({'id': cid, 'status': to or 'PENDING_SUPPLIER', 'platStatus': 'PENDING' if to is None else None, 'fileSha256': sha})


def _file_sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(65536), b''):
            h.update(chunk)
    return h.hexdigest()


@bp.post('/contracts/<int:cid>/void')
@auth_required
def void_contract(cid):
    p = get_params()
    require_fields(p, 'reason')
    row, order = _contract(cid)
    if row['status'] not in ('PENDING_GENERATE', 'PENDING_BUYER', 'PENDING_SUPPLIER'):
        raise ApiError(40901, '已生效合同不可作废')
    transition(g.conn, g.ctx, 'biz_contract', '合同', 'biz_contract', cid, 'VOID',
               node_biz_type='ORDER', node_code='CONTRACT_VOIDED', node_biz_id=order['id'])
    # 订单回到待生成合同
    if order['status'] in ('PENDING_EFFECT', 'PENDING_CONTRACT'):
        transition(g.conn, g.ctx, 'biz_order', '订单', 'biz_order', order['id'], 'PENDING_CONTRACT')
    send_msg(g.conn, order['buyer_id'], '合同已作废',
             '订单 %s 合同 %s 已作废：%s（可重新生成新版本）' % (order['order_no'], row['contract_no'], p['reason']),
             'CONTRACT', cid)
    send_msg(g.conn, order['supplier_id'], '合同已作废',
             '订单 %s 合同 %s 已作废：%s（可重新生成新版本）' % (order['order_no'], row['contract_no'], p['reason']),
             'CONTRACT', cid)
    op_log(g.conn, g.ctx, 'biz_contract', cid, 'VOID', None, {'reason': p['reason']})
    return ok({'id': cid, 'status': 'VOID'})


@bp.get('/contracts/<int:cid>')
@auth_required
def detail(cid):
    row, order = _contract(cid)
    data = json_payload(dict(row))
    data['order'] = json_payload(dict(order))
    return ok(data)


@bp.get('/contracts')
@auth_required
def list_mine():
    from flask import request
    params = request.args.to_dict()
    from ..common import page_args, page_data
    page, size = page_args(params)
    where, args = 'WHERE 1=1', []
    if not g.ctx.is_plat:
        where += ' AND (o.buyer_id=%s OR o.supplier_id=%s)'
        args += [g.ctx.company['id'] or -1, g.ctx.company['id'] or -1]
    if params.get('status'):
        where += ' AND c.status=%s'
        args.append(params['status'])
    total = q1(g.conn, 'SELECT count(*) AS c FROM biz_contract c JOIN biz_order o ON o.id=c.order_id ' + where, args)['c']
    rows = qall(g.conn, """
        SELECT c.id, c.contract_no AS "contractNo", c.order_id AS "orderId", o.order_no AS "orderNo",
               c.version, c.status, c.file_url AS "fileUrl", c.file_hash AS "fileHash",
               c.buyer_sign_at AS "buyerSignAt", c.supplier_sign_at AS "supplierSignAt",
               c.void_reason AS "voidReason", c.created_at AS "createdAt"
        FROM biz_contract c JOIN biz_order o ON o.id=c.order_id
        %s ORDER BY c.id DESC LIMIT %%s OFFSET %%s
        """ % where, args + [size, (page - 1) * size])
    return ok(page_data(rows, total, page, size))
