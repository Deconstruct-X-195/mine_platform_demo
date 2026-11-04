# -*- coding: utf-8 -*-
"""通用工具：响应封装、操作日志、分页、Excel 导出、文件上传"""
import io
import os
import uuid
from functools import wraps
from flask import request, jsonify, current_app, send_file
from werkzeug.utils import secure_filename
from .db import get_db, UPLOAD_DIR, _now

ALLOWED_EXT = {'pdf', 'png', 'jpg', 'jpeg', 'gif', 'webp', 'xlsx', 'xls', 'doc', 'docx'}


def ok(data=None, **extra):
    body = {'code': 0, 'message': 'success', 'data': data}
    if extra:
        body.update(extra)
    return jsonify(body)


def err(message, code=1, http=400):
    return jsonify({'code': code, 'message': message}), http


def log_action(action, detail=None, before=None, after=None, ref_type=None, ref_id=None):
    """写操作日志（PRD-01 硬约束：全部关键业务操作留痕）"""
    from flask import g as _g
    db = get_db()
    user = getattr(_g, 'current_user', None)
    db.execute(
        "INSERT INTO sys_log(operator_id, operator_name, role_code, action, detail,"
        " before_status, after_status, ref_type, ref_id, create_time) VALUES(?,?,?,?,?,?,?,?,?,?)",
        (user['user_id'] if user else None,
         user['real_name'] or user['username'] if user else 'system',
         user['role_code'] if user else None,
         action, detail, before, after, ref_type, str(ref_id) if ref_id is not None else None,
         _now()))
    db.commit()


def paginate(db, sql, args, page, page_size, count_sql=None):
    total = db.execute(count_sql or f"SELECT COUNT(*) FROM ({sql})", args).fetchone()[0]
    rows = db.execute(sql + " LIMIT ? OFFSET ?", list(args) + [page_size, (page - 1) * page_size]).fetchall()
    return [dict(r) for r in rows], total


def round2(x):
    return round(float(x) + 0.0, 2)


def gen_no(prefix, row_id):
    return f"{prefix}{datetime_suffix()}{row_id:04d}"


def datetime_suffix():
    return _now().replace('-', '').replace(':', '').replace(' ', '')


def save_upload(file):
    """保存上传附件，返回 (file_url, file_name)"""
    if not file or not file.filename:
        return None, None
    ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else ''
    if ext not in ALLOWED_EXT:
        raise ValueError(f"不支持的文件类型: .{ext}（仅支持 {', '.join(sorted(ALLOWED_EXT))}）")
    fname = f"{uuid.uuid4().hex}.{ext}"
    path = os.path.join(UPLOAD_DIR, fname)
    file.save(path)
    return f"/api/files/{fname}", secure_filename(file.filename)


def export_excel(headers, sheets, filename):
    """sheets: [(sheet_name, rows), ...] rows 为二维列表"""
    from openpyxl import Workbook
    wb = Workbook()
    wb.remove(wb.active)
    for sheet_name, rows in sheets:
        ws = wb.create_sheet(sheet_name[:31])
        ws.append(headers)
        for r in rows:
            ws.append(list(r))
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return send_file(buf, as_attachment=True, download_name=filename,
                     mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
