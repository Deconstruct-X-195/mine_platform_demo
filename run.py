# -*- coding: utf-8 -*-
"""大宗矿产集采平台一期 启动入口：初始化库表 + 演示数据，启动 Flask 服务。

用法：python run.py            →  Web 服务 http://127.0.0.1:8000（waitress）
      python run.py --jobs    →  独立任务进程：建表后执行单轮定时任务并退出
环境变量：MINE_PG_DSN / MINE_JWT_SECRET / MINE_PORT / MINE_DISABLE_JOBS / MINE_SEED_DEMO / MINE_SEED_BASE
"""
import os
import sys

from backend import create_app
from backend.db import with_db, init_schema
from backend.seed import seed, seed_base_data

app = create_app()

if __name__ == '__main__':
    with with_db() as conn:
        created = init_schema(conn)
        if created:
            print('[init] 数据库表结构已创建')
        # C10（部署适配方案 §5）：演示数据种子开关——生产部署不注入演示数据，
        # 仅本地开发/回归测试显式设 MINE_SEED_DEMO=1 时写入
        if os.environ.get('MINE_SEED_DEMO') == '1':
            print('[warn] MINE_SEED_DEMO=1：将写入演示种子数据（演示企业/账号），'
                  '生产环境严禁开启！如为生产部署请立即停止并移除该变量')
            if seed(conn):
                print('[init] 演示数据已写入（管理员 13800000000/admin123456，业务账号 demo123456）')
        elif os.environ.get('MINE_SEED_BASE') == '1':
            # 生产基础数据开关：仅写入品种档案/当日基准价/港口现货价，
            # 不含任何账号与企业（管理员经 manage.py create-admin 创建，账号走注册流程）
            print('[init] MINE_SEED_BASE=1：写入生产基础数据（品种/当日基准价/港口现货价，不含账号与企业）')
            seed_base_data(conn)
            print('[init] 生产基础数据已写入')
    port = int(os.environ.get('MINE_PORT', 8000))
    if '--jobs' in sys.argv[1:]:
        # C4（部署适配方案 §5）：独立任务进程单轮执行（systemd timer 调度），不启动 Web
        from backend import jobs
        print('[jobs] 独立任务进程：单轮执行开始')
        jobs.run_once()
        print('[jobs] 独立任务进程：单轮执行完成')
    else:
        from waitress import serve  # C1（部署适配方案 §5）：生产级 WSGI 容器替换 werkzeug 开发服务器
        # D2-4（部署前全面评估报告）：线程数环境变量化，默认 8 不变；
        # 内存受限服务器可设 MINE_WORKERS=4 降低常驻内存
        workers = int(os.environ.get('MINE_WORKERS', '8'))
        print('[run] 服务启动：http://127.0.0.1:%s (waitress, threads=%d)' % (port, workers))
        serve(app, host='127.0.0.1', port=port, threads=workers)
