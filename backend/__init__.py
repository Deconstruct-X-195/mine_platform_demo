"""大宗矿产集采平台一期 后端服务（Flask 3 + PostgreSQL 14）。

应用工厂：注册 /api/v1 蓝图、统一错误拦截（PRD 6.3 契约）、前端静态托管、
定时任务开关（MINE_DISABLE_JOBS=1 供测试禁用）。
"""
import os
import threading
from datetime import date, datetime

from flask import Flask, g, jsonify, redirect, request, send_from_directory
from flask.json.provider import DefaultJSONProvider
from werkzeug.exceptions import HTTPException

from .common import ApiError
from .db import pool

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRONTEND_DIR = os.path.join(_ROOT, 'frontend')
# 政务大屏静态目录（21:9 index.html / 4:3 index43.html，独立于 SPA）
BIGSCREEN_DIR = os.path.join(_ROOT, 'bigscreen')
# C11（部署适配方案 §5）：上传目录支持 MINE_UPLOAD_DIR 环境变量覆盖
# （服务器侧分离挂载盘 /data/mine/uploads，默认保持本地仓库相对路径不变）
UPLOAD_DIR = os.environ.get('MINE_UPLOAD_DIR') or os.path.join(_ROOT, 'uploads')

# 错误码 → HTTPException 映射（业务失败统一 HTTP 200；鉴权失败 401）
_HTTP_CODE_MAP = {400: 40001, 401: 40101, 403: 40301, 404: 40401, 405: 40001, 409: 40901, 413: 40001}


class _JSONProvider(DefaultJSONProvider):
    """日期时间序列化为阿拉伯数字格式（2026-11-12 09:30:00），不用英文 RFC 格式。"""

    def default(self, o):
        if isinstance(o, datetime):
            return o.strftime('%Y-%m-%d %H:%M:%S')
        if isinstance(o, date):
            return o.strftime('%Y-%m-%d')
        return super().default(o)


def create_app():
    app = Flask('mine-platform', static_folder=None)
    app.json = _JSONProvider(app)  # 日期时间统一序列化为阿拉伯数字格式
    app.config['MAX_CONTENT_LENGTH'] = 21 * 1024 * 1024  # 单文件 ≤20MB（PRD 7）
    os.makedirs(UPLOAD_DIR, exist_ok=True)

    # ---- 数据库连接（请求级事务，会话时区=业务时区，BUG-06 修复）----
    # C5（部署适配方案 §5）：物理连接改由进程级连接池获取/归还，
    # 事务边界（请求成功 commit、异常 rollback）与全部 SQL 零改动
    @app.before_request
    def _open_conn():
        if request.path.startswith('/api/'):
            g.conn = pool().getconn()

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
                pool().putconn(conn)

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
    # 政务大屏（先于 /<path:filename> 通配注册，专路优先）
    # /bigscreen/ 默认进 4:3 版（index43.html）；21:9 版保留在 /bigscreen/index.html
    @app.route('/bigscreen/')
    def _bigscreen_index():
        return redirect('/bigscreen/index43.html')

    @app.route('/bigscreen/<path:filename>')
    def _bigscreen_static(filename):
        return send_from_directory(BIGSCREEN_DIR, filename)

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

    # C6（部署适配方案 §5）：匿名 /uploads/<filename> 直链已删除——
    # 附件统一走鉴权接口 /api/v1/files/<file_id>（auth_required）下载，
    # 该路径经 _static 的 uploads/ 前缀拦截返回 404，避免未登录枚举/爬取落盘文件。

    # ---- 定时任务 ----
    if os.environ.get('MINE_DISABLE_JOBS') != '1':
        from . import jobs
        t = threading.Thread(target=jobs.run_loop, daemon=True, name='mine-jobs')
        t.start()

    return app
