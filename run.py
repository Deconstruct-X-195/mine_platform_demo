# -*- coding: utf-8 -*-
"""矿石集中集采平台 启动入口"""
from backend import create_app

app = create_app()

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5000, debug=False)
