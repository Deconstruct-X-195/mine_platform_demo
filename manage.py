# -*- coding: utf-8 -*-
"""生产环境管理员账号管理 CLI（服务端本机执行，不经 HTTP、不经公开注册）。

背景：MINE_SEED_DEMO=1 的演示种子（含平台管理员 13800000000）生产环境禁用后，
平台管理员账号由本工具在服务器本机初始化，与 sys_user/PLAT_ADMIN 权限体系完全同构。

用法（需先注入 MINE_PG_DSN；CLI 不签发 JWT，无需 MINE_JWT_SECRET）：
  set -a; . ./.env; set +a          # 或按部署规范注入环境变量
  python manage.py create-admin                     # 交互式：手机号 + getpass 双输密码
  python manage.py create-admin --username 138...   # 非交互用户名，密码仍走 getpass
  python manage.py create-admin --force             # 已存在管理员时增补（需输入 YES 二次确认）
  python manage.py reset-admin-password             # 重置指定/唯一管理员密码
  python manage.py list-admins                      # 审计核对：列出全部 PLAT_ADMIN

安全约定：
  密码一律 getpass 或 --password-stdin 输入，禁止出现在命令行参数/环境变量/shell history；
  校验复用 backend.common（手机号格式、密码强度≥8位含字母数字）；
  每次变更写 sys_operation_log（ip=CLI）留痕，可追溯。
"""
import argparse
import getpass
import json
import sys

from backend.common import ApiError, validate_password, validate_phone
from backend.db import execute, q1, qall, schema_ready, with_db


def _hash_password(plain: str) -> str:
    """BCrypt 散列，与 backend.security.hash_password 完全一致（rounds=10，ascii 存储）。

    不直接 import backend.security：该模块加载即强制校验 MINE_JWT_SECRET（Web 启动约束），
    而 CLI 不签发 token，不应把 JWT 密钥作为运行前置条件。
    """
    import bcrypt
    return bcrypt.hashpw(plain.encode('utf-8'), bcrypt.gensalt(rounds=10)).decode('ascii')


def _audit(conn, uid, action, after):
    """操作留痕：与 backend.common.op_log 同构（CLI 无请求上下文，ip 固定 CLI）。"""
    execute(conn, """
        INSERT INTO sys_operation_log (user_id, company_id, biz_type, biz_id, action,
                                       before_value, after_value, ip)
        VALUES (%s, NULL, 'sys_user', %s, %s, NULL, %s, 'CLI')
    """, (uid, uid, action, json.dumps(after, ensure_ascii=False)))


def _check_schema(conn):
    if not schema_ready(conn):
        sys.exit('[error] 数据库表结构尚未初始化：请先运行 python run.py 完成建表，再执行本命令')


def _read_password(label='新密码', use_stdin=False):
    """密码读取：--password-stdin 或 getpass 双输确认（不回显、不落参数）。"""
    if use_stdin:
        pwd = sys.stdin.readline()
        if not pwd:
            sys.exit('[error] stdin 未提供密码')
        return pwd.rstrip('\r\n')
    p1 = getpass.getpass('请输入%s（至少8位，须同时包含字母和数字）: ' % label)
    p2 = getpass.getpass('请再次输入%s确认: ' % label)
    if p1 != p2:
        sys.exit('[error] 两次输入的密码不一致')
    return p1


def _admins(conn):
    return qall(conn, """SELECT id, username, real_name, status, created_at
                         FROM sys_user WHERE roles='PLAT_ADMIN' AND is_deleted=0 ORDER BY id""")


def cmd_create_admin(args):
    with with_db() as conn:
        _check_schema(conn)
        exist = _admins(conn)
        if exist and not args.force:
            sys.exit('[error] 已存在平台管理员（%s）。如确需增补管理员，请加 --force 并二次确认'
                     % ', '.join(r['username'] for r in exist))
        if exist and args.force:
            if input('已存在平台管理员，确认增补新管理员？请输入 YES 继续: ').strip() != 'YES':
                sys.exit('[info] 已取消')
        username = args.username or input('请输入管理员手机号（登录账号）: ').strip()
        validate_phone(username)
        if q1(conn, "SELECT id FROM sys_user WHERE username=%s AND is_deleted=0", (username,)):
            sys.exit('[error] 该手机号已被注册（含企业账号），请更换')
        pwd = _read_password(use_stdin=args.password_stdin)
        validate_password(pwd)
        real_name = args.real_name or '平台管理员'
        uid = execute(conn, """
            INSERT INTO sys_user (company_id, username, password_hash, real_name, roles, created_by)
            VALUES (NULL, %s, %s, %s, 'PLAT_ADMIN', NULL)
            RETURNING id
        """, (username, _hash_password(pwd), real_name), returning_id=True)
        _audit(conn, uid, 'ADMIN_BOOTSTRAP', {'username': username, 'via': 'manage.py'})
        print('[ok] 平台管理员已创建：%s（id=%s）' % (username, uid))
        print('[tip] 请妥善保管密码；建议定期使用 reset-admin-password 轮换')


def cmd_reset_admin_password(args):
    with with_db() as conn:
        _check_schema(conn)
        admins = _admins(conn)
        if not admins:
            sys.exit('[error] 库中尚无平台管理员，请先执行 create-admin')
        if args.username:
            target = next((r for r in admins if r['username'] == args.username), None)
            if not target:
                sys.exit('[error] 管理员 %s 不存在（现有：%s）'
                         % (args.username, ', '.join(r['username'] for r in admins)))
        elif len(admins) == 1:
            target = admins[0]
        else:
            sys.exit('[error] 存在多个管理员，请用 --username 指定（现有：%s）'
                     % ', '.join(r['username'] for r in admins))
        pwd = _read_password(use_stdin=args.password_stdin)
        validate_password(pwd)
        execute(conn, "UPDATE sys_user SET password_hash=%s WHERE id=%s",
                (_hash_password(pwd), target['id']))
        _audit(conn, target['id'], 'ADMIN_PWD_RESET', {'username': target['username']})
        print('[ok] 管理员 %s 密码已更新' % target['username'])


def cmd_list_admins(args):
    with with_db() as conn:
        _check_schema(conn)
        admins = _admins(conn)
        if not admins:
            print('[info] 库中暂无平台管理员')
            return
        print('%-6s %-14s %-16s %-10s %s' % ('id', '账号', '姓名', '状态', '创建时间'))
        for r in admins:
            print('%-6s %-14s %-16s %-10s %s' % (
                r['id'], r['username'], r['real_name'] or '-', r['status'], r['created_at']))


def main():
    parser = argparse.ArgumentParser(description='平台管理员账号管理 CLI（服务端本机执行）')
    sub = parser.add_subparsers(dest='cmd', required=True)

    p1 = sub.add_parser('create-admin', help='创建平台管理员（已存在时默认拒绝）')
    p1.add_argument('--username', help='管理员手机号（缺省交互输入）')
    p1.add_argument('--real-name', help='姓名（缺省：平台管理员）')
    p1.add_argument('--force', action='store_true', help='已存在管理员时增补（需输入 YES 确认）')
    p1.add_argument('--password-stdin', dest='password_stdin', action='store_true',
                    help='从 stdin 首行读取密码（自动化场景，避免落 shell history）')
    p1.set_defaults(fn=cmd_create_admin)

    p2 = sub.add_parser('reset-admin-password', help='重置管理员密码')
    p2.add_argument('--username', help='目标管理员手机号（仅一个管理员时可缺省）')
    p2.add_argument('--password-stdin', dest='password_stdin', action='store_true',
                    help='从 stdin 首行读取密码（自动化场景，避免落 shell history）')
    p2.set_defaults(fn=cmd_reset_admin_password)

    p3 = sub.add_parser('list-admins', help='列出全部平台管理员')
    p3.set_defaults(fn=cmd_list_admins)

    args = parser.parse_args()
    try:
        args.fn(args)
    except ApiError as e:
        sys.exit('[error] %s' % e.message)


if __name__ == '__main__':
    main()
