"""大宗矿产集采平台一期 后端服务（Flask 3 + PostgreSQL 14）。

应用工厂：注册 /api/v1 蓝图、统一错误拦截（PRD 6.3 契约）、前端静态托管、
定时任务开关（MINE_DISABLE_JOBS=1 供测试禁用）。
"""
import os
import threading

import psycopg
from psycopg.rows import dict_row
from flask import Flask, g, jsonify, request, send_from_directory
from werkzeug.exceptions import HTTPException

from .common import ApiError
from .db import dsn

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRONTEND_DIR = os.path.join(_ROOT, 'frontend')
UPLOAD_DIR = os.path.join(_ROOT, 'uploads')

# 错误码 → HTTPException 映射（业务失败统一 HTTP 200；鉴权失败 401）
_HTTP_CODE_MAP = {400: 40001, 401: 40101, 403: 40301, 404: 40401, 405: 40001, 409: 40901, 413: 40001}


def create_app():
    app = Flask('mine-platform', static_folder=None)
    app.config['MAX_CONTENT_LENGTH'] = 21 * 1024 * 1024  # 单文件 ≤20MB（PRD 7）
    os.makedirs(UPLOAD_DIR, exist_ok=True)

    # ---- 数据库连接（请求级事务）----
    @app.before_request
    def _open_conn():
        if request.path.startswith('/api/'):
            g.conn = psycopg.connect(dsn(), row_factory=dict_row)

    @app.teardown_request
    def _close_conn(exc):
        conn = g.pop('conn', None)
        if conn is not None:
            try:
                if exc is None:
                    conn.commit()
                else:
                    conn.rollback()
            finally:
                conn.close()

    # ---- 错误拦截（PRD 6.3）----
    @app.errorhandler(ApiError)
    def _on_api_error(e: ApiError):
        return jsonify({'code': e.code, 'message': e.message, 'data': None}), e.http

    @app.errorhandler(HTTPException)
    def _on_http_error(e: HTTPException):
        if request.path.startswith('/api/'):
            code = _HTTP_CODE_MAP.get(e.code, 50001)
            http = 401 if e.code == 401 else (404 if e.code == 404 else 200)
            if e.code in (400, 405, 409, 413):
                http = 200
            return jsonify({'code': code, 'message': e.description, 'data': None}), http
        return e

    @app.errorhandler(Exception)
    def _on_error(e):
        app.logger.exception('服务内部错误: %s', e)
        return jsonify({'code': 50001, 'message': '服务内部错误', 'data': None}), 500

    # ---- 业务蓝图 ----
    from .api import bp
    app.register_blueprint(bp)

    # ---- 前端静态托管（原生 SPA，无构建）----
    @app.route('/')
    def _index():
        return send_from_directory(FRONTEND_DIR, 'index.html')

    @app.route('/<path:filename>')
    def _static(filename):
        if filename.startswith(('api/', 'uploads/')):
            raise ApiError(40401, '资源不存在', http=404)
        full = os.path.normpath(os.path.join(FRONTEND_DIR, filename))
        if not full.startswith(FRONTEND_DIR) or not os.path.isfile(full):
            return send_from_directory(FRONTEND_DIR, 'index.html')  # SPA 回退
        return send_from_directory(FRONTEND_DIR, filename)

    @app.route('/uploads/<path:filename>')
    def _uploads(filename):
        return send_from_directory(UPLOAD_DIR, filename)

    # ---- 定时任务 ----
    if os.environ.get('MINE_DISABLE_JOBS') != '1':
        from . import jobs
        t = threading.Thread(target=jobs.run_loop, daemon=True, name='mine-jobs')
        t.start()

    return app
