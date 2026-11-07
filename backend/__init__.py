# -*- coding: utf-8 -*-
"""应用工厂"""
import os
from flask import Flask, send_from_directory, request
from .db import init_db, close_db, get_db, BASE_DIR, UPLOAD_DIR, _now
from .utils import ok, err, log_action
from .auth import current_user

FRONTEND_DIR = os.path.join(BASE_DIR, 'frontend')


def create_app():
    app = Flask(__name__, static_folder=None)
    app.config['MAX_CONTENT_LENGTH'] = 20 * 1024 * 1024  # 20MB

    init_db(app)
    app.teardown_appcontext(close_db)

    from . import auth as auth_mod
    auth_bp = auth_mod.create_auth_bp()
    app.register_blueprint(auth_bp, url_prefix='/api')

    register_common_routes(app)
    register_module_bps(app)

    @app.errorhandler(404)
    def not_found(_):
        if request.path.startswith('/api/'):
            return err('接口不存在', code=404, http=404)
        return send_from_directory(FRONTEND_DIR, 'index.html')

    @app.errorhandler(500)
    def server_error(e):
        return err(f'服务器内部错误: {e}', code=500, http=500)

    @app.get('/')
    def index():
        resp = send_from_directory(FRONTEND_DIR, 'index.html')
        resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        return resp

    @app.get('/assets/<path:filename>')
    def assets(filename):
        # 防目录穿越
        if '..' in filename:
            return err('非法路径', http=400)
        return send_from_directory(os.path.join(FRONTEND_DIR, 'assets'), filename)

    return app


def register_common_routes(app):
    """通用路由：文件服务、字典查询、附件上传"""

    @app.get('/api/files/<name>')
    def serve_file(name):
        # 防目录穿越
        if '/' in name or '\\' in name or '..' in name:
            return err('非法文件名', http=400)
        return send_from_directory(UPLOAD_DIR, name)

    @app.post('/api/upload')
    def upload_file():
        from .auth import current_user
        from .utils import save_upload
        if not current_user():
            return err('未登录或登录已过期', code=401, http=401)
        f = request.files.get('file')
        if not f:
            return err('未选择文件')
        try:
            url, name = save_upload(f)
        except ValueError as e:
            return err(str(e))
        return ok({'file_url': url, 'file_name': name})

    @app.get('/api/dict/<category>')
    def get_dict(category):
        rows = get_db().execute(
            "SELECT item_code, item_name FROM dict_item WHERE category=? AND status=1 ORDER BY sort",
            (category,)).fetchall()
        return ok([dict(r) for r in rows])


def register_module_bps(app):
    from .api import admin as admin_mod
    app.register_blueprint(admin_mod.bp, url_prefix='/api')
    try:
        from .api import demand
        app.register_blueprint(demand.bp, url_prefix='/api')
        from .api import resource
        app.register_blueprint(resource.bp, url_prefix='/api')
        from .api import trading
        app.register_blueprint(trading.bp, url_prefix='/api')
        from .api import logistics
        app.register_blueprint(logistics.bp, url_prefix='/api')
        from .api import price
        app.register_blueprint(price.bp, url_prefix='/api')
        from .api import settlement
        app.register_blueprint(settlement.bp, url_prefix='/api')
    except ImportError:
        pass  # 模块随开发阶段逐步启用

    # 扩展模块（PRD-09 ~ PRD-15）
    for mod_name in ('inspect', 'contract', 'expense', 'message', 'report', 'bizchange'):
        from importlib import import_module
        mod = import_module(f'.api.{mod_name}', package=__package__)
        app.register_blueprint(mod.bp, url_prefix='/api')

    # 采购商城（现货直购）
    from .api import mall
    app.register_blueprint(mall.bp, url_prefix='/api')
