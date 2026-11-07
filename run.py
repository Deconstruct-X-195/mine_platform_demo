# -*- coding: utf-8 -*-
"""大宗矿产集采平台一期 启动入口：初始化库表 + 演示数据，启动 Flask 服务。

用法：python run.py  →  http://127.0.0.1:8000
环境变量：MINE_PG_DSN / MINE_JWT_SECRET / MINE_PORT / MINE_DISABLE_JOBS
"""
import os

from backend import create_app
from backend.db import with_db, init_schema
from backend.seed import seed

app = create_app()

if __name__ == '__main__':
    with with_db() as conn:
        created = init_schema(conn)
        if created:
            print('[init] 数据库表结构已创建')
        if seed(conn):
            print('[init] 演示数据已写入（管理员 13800000000/admin123456，业务账号 demo123456）')
    port = int(os.environ.get('MINE_PORT', 8000))
    print('[run] 服务启动：http://127.0.0.1:%s' % port)
    app.run(host='127.0.0.1', port=port, debug=False)
