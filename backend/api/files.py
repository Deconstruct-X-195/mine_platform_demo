"""附件模块（PRD 6.1/T03）：统一上传返回 fileId，业务对象只存 fileId。

安全（PRD 7）：扩展名白名单、20MB 上限、随机文件名路径、Content-Disposition 下载。
"""
import hashlib
import os
import uuid

from flask import current_app, g, request, send_from_directory

from ..common import ApiError, get_params, json_payload, ok, op_log, page_args, page_data
from ..db import qall, q1
from ..security import auth_required, plat_required
from .. import UPLOAD_DIR
from . import bp

ALLOWED_EXT = {'pdf', 'jpg', 'jpeg', 'png'}
MAX_SIZE = 20 * 1024 * 1024


@bp.post('/files')
@auth_required
def upload():
    f = request.files.get('file')
    if not f or not f.filename:
        raise ApiError(40001, '缺少上传文件（字段名 file）')
    ext = os.path.splitext(f.filename)[1].lower().lstrip('.')
    if ext not in ALLOWED_EXT:
        raise ApiError(40001, '仅支持 %s 格式' % '/'.join(sorted(ALLOWED_EXT)))
    data = f.read()
    if len(data) > MAX_SIZE:
        raise ApiError(40001, '文件大小不能超过 20MB')
    file_id = uuid.uuid4().hex
    name = '%s.%s' % (file_id, ext)
    path = os.path.join(UPLOAD_DIR, name)
    with open(path, 'wb') as out:
        out.write(data)
    from ..db import execute
    row_id = execute(g.conn, """
        INSERT INTO sys_file (file_id, file_name, content_type, size_bytes, path, company_id, created_by)
        VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id
        """, (file_id, f.filename, f.content_type, len(data), path,
              g.ctx.company['id'] if g.ctx.company else None, g.ctx.user['id']),
        returning_id=True)
    op_log(g.conn, g.ctx, 'sys_file', row_id, 'UPLOAD', None, {'fileName': f.filename, 'size': len(data)})
    return ok({'fileId': file_id, 'fileName': f.filename, 'sha256': hashlib.sha256(data).hexdigest()})


@bp.get('/files/<file_id>')
@auth_required
def download(file_id):
    row = q1(g.conn, "SELECT * FROM sys_file WHERE file_id=%s AND is_deleted=0", (file_id,))
    if not row or not _file_accessible(row):
        raise ApiError(40401, '文件不存在')
    return send_from_directory(UPLOAD_DIR, os.path.basename(row['path']),
                               download_name=row['file_name'])


def _file_accessible(row):
    """P2-1 下载越权修复：附件可见性跟随业务关系，登录用户不再可下载任意文件。

    规则：
    - 平台管理员全部可见；
    - 企业归属文件仅归属企业可见（含经 ent_qualification 判定归属的注册执照）；
    - 归属他企业或无归属的文件按业务单据引用关系对参与企业开放
      （合同/质检/付款凭证→订单双方，报价附件→报价供应商或询价买方）。
    无权访问统一返回 40401，不泄露文件存在性。
    """
    ctx = g.ctx
    if ctx.is_plat:
        return True
    my_cid = ctx.company['id'] if ctx.company else None
    if not my_cid:
        return False
    owner = row['company_id']
    if owner is None:
        # 注册执照类无归属文件：经 ent_qualification 判定归属企业
        qual = q1(g.conn, """
            SELECT company_id FROM ent_qualification
            WHERE file_id=%s AND is_deleted=0 ORDER BY id LIMIT 1
            """, (row['file_id'],))
        owner = qual['company_id'] if qual else None
    if owner == my_cid:
        return True
    # 归属他企业或无归属：按业务单据引用关系判定（对单据参与企业开放）
    fid = row['file_id']
    return bool(q1(g.conn, """
        SELECT 1 WHERE EXISTS (
            SELECT 1 FROM biz_contract c JOIN biz_order o ON o.id = c.order_id
             WHERE (c.file_url = %s OR c.buyer_file_url = %s OR c.supplier_file_url = %s)
               AND (o.buyer_id = %s OR o.supplier_id = %s)
        ) OR EXISTS (
            SELECT 1 FROM biz_quality_check q JOIN biz_order o ON o.id = q.order_id
             WHERE q.file_url = %s AND (o.buyer_id = %s OR o.supplier_id = %s)
        ) OR EXISTS (
            SELECT 1 FROM biz_payment p
             JOIN biz_settlement s ON s.id = p.settlement_id
             JOIN biz_order o ON o.id = s.order_id
             WHERE p.file_url = %s AND (o.buyer_id = %s OR o.supplier_id = %s)
        ) OR EXISTS (
            SELECT 1 FROM biz_quote_file qf
             JOIN biz_quote q ON q.id = qf.quote_id
             LEFT JOIN biz_inquiry i ON i.id = q.inquiry_id
             WHERE qf.file_id = %s AND (
                   q.supplier_id = %s OR i.buyer_id = %s
                   OR (i.agg_id IS NOT NULL AND EXISTS (
                       SELECT 1 FROM biz_aggregated_order_item m
                       JOIN biz_demand d ON d.id = m.demand_id
                       WHERE m.agg_id = i.agg_id AND m.is_deleted = 0
                         AND d.is_deleted = 0 AND d.company_id = %s))
             )
        )
        """, (fid, fid, fid, my_cid, my_cid,
              fid, my_cid, my_cid,
              fid, my_cid, my_cid,
              fid, my_cid, my_cid, my_cid)))


@bp.get('/admin/files')
@plat_required
def admin_files():
    params = get_params()
    page, size = page_args(params)
    total = q1(g.conn, 'SELECT count(*) AS c FROM sys_file WHERE is_deleted=0')['c']
    rows = qall(g.conn, """
        SELECT file_id AS "fileId", file_name AS "fileName", content_type AS "contentType",
               size_bytes AS "size", company_id AS "companyId", created_at AS "createdAt"
        FROM sys_file WHERE is_deleted=0 ORDER BY id DESC LIMIT %s OFFSET %s
        """, (size, (page - 1) * size))
    return ok(page_data(rows, total, page, size))
