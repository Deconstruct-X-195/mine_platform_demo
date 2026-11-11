"""演示数据种子（幂等）：平台管理员、演示企业与账号、品种档案与当日基准价。

账号约定：
  平台管理员  13800000000 / admin123456
  钢厂        13800000001 / demo123456
  供应商×3    13800000002-04 / demo123456
  承运商      13800000005 / demo123456
"""
from .db import execute, q1
from .security import hash_password

VARIETIES = [
    ('PB_FINES', 'PB粉', '61.50', 760.00),
    ('CHINA_BLEND_FINES', '中华混一号', '61.50', 745.00),
]

COMPANIES = [
    # (company_name, credit_code, company_types, phone, real_name)
    ('示范钢铁集团有限公司', '91310000MA1FL45X2K', 'STEEL', '13800000001', '钢厂采购员'),
    ('示范矿产贸易有限公司', '91310000MA1FL45X3L', 'SUPPLIER', '13800000002', '供应商销售甲'),
    ('示范矿业有限公司', '91310000MA1FL45X4M', 'SUPPLIER', '13800000003', '供应商销售乙'),
    ('示范国际供应链有限公司', '91310000MA1FL45X5N', 'SUPPLIER', '13800000004', '供应商销售丙'),
    ('示范物流运输有限公司', '91310000MA1FL45X6P', 'LOGISTICS', '13800000005', '物流操作员'),
]


def seed(conn):
    """幂等：已存在平台管理员则跳过。"""
    if q1(conn, "SELECT id FROM sys_user WHERE username=%s AND is_deleted=0", ('13800000000',)):
        return False
    # 平台管理员（无企业归属）
    execute(conn, """
        INSERT INTO sys_user (company_id, username, password_hash, real_name, roles, created_by)
        VALUES (NULL, %s, %s, %s, 'PLAT_ADMIN', NULL)
    """, ('13800000000', hash_password('admin123456'), '平台管理员'))
    # 演示企业 + 首个账号（已准入，直接可用）
    for name, credit, types, phone, real_name in COMPANIES:
        cid = execute(conn, """
            INSERT INTO ent_company (company_name, credit_code, company_types, province, city,
                                     address, contact_name, contact_phone, audit_status, status)
            VALUES (%s, %s, %s, '上海市', '上海市', '示范路 1 号', %s, %s, 'APPROVED', 'ENABLED')
            RETURNING id
        """, (name, credit, types, real_name, phone), returning_id=True)
        execute(conn, """
            INSERT INTO sys_user (company_id, username, password_hash, real_name, roles)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id
        """, (cid, phone, hash_password('demo123456'), real_name,
              {'STEEL': 'STEEL_BUYER', 'SUPPLIER': 'SUPPLIER', 'LOGISTICS': 'LOGISTICS_CARRIER'}[types]))
    # 品种档案 + 当日基准价
    for code, vname, grade, price in VARIETIES:
        vid = execute(conn, """
            INSERT INTO base_variety (variety_code, variety_name, default_grade, unit, sort_no)
            VALUES (%s, %s, %s, '吨', %s)
            RETURNING id
        """, (code, vname, grade, len(code)), returning_id=True)
        execute(conn, """
            INSERT INTO base_price (variety_id, price_date, price, price_basis, source_desc)
            VALUES (%s, current_date, %s, 'WET', '运营手工维护（演示数据）')
        """, (vid, price))
        # 港口+品位维度：PB粉维护 61.5%/60.8% 两档基准价
        # （锚点：兰格钢铁网 2026-11-09 天津港 60.8% 657 元；61.5% 按品位价差 +10 推算 667）
        pb_id = q1(conn, "SELECT id FROM base_variety WHERE variety_code='PB_FINES'")['id']
        for grade, tj in (('61.50', 667.00), ('60.80', 657.00)):
            for port, p in (('天津港', tj), ('黄骅港', round(tj - 2, 2))):
                execute(conn, """
                    INSERT INTO base_price (variety_id, price_date, price, price_basis, port, grade, source_desc)
                    VALUES (%s, current_date, %s, 'WET', %s, %s, '兰格钢铁网公开报价锚点·锚点间线性内插（演示）')
                """, (pb_id, p, port, grade))
    return True
