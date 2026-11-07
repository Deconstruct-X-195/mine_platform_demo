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
    if not row:
        raise ApiError(40401, '文件不存在')
    return send_from_directory(UPLOAD_DIR, os.path.basename(row['path']),
                               download_name=row['file_name'])


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
