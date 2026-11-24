"""演示基础数据种子（幂等）：平台管理员、演示企业与账号、品种档案与港口现货价。

业务单据（订单/合同/物流/消息等）由实际操作产生，不预置演示数据；重启不再重建历史演示单据。

账号约定：
  平台管理员  13800000000 / admin123456
  钢厂        13800000001 / demo123456
  供应商×3    13800000002-04 / demo123456
  承运商      13800000005 / demo123456
"""
from .db import execute, q1, qall
from .security import hash_password

VARIETIES = [
    # (variety_code, variety_name, default_grade, 当日基准价；None=不维护行情价)
    ('PB_FINES', 'PB粉', '61.50', 760.00),
    ('CHINA_BLEND_FINES', '中华混一号', '61.50', 745.00),
    # 「其它」：暂只做需求归集，不形成实际订单，无行情基准价
    ('OTHER', '其它', '62.00', None),
]

COMPANIES = [
    # (company_name, credit_code, company_types, phone, real_name)
    ('示范钢铁集团有限公司', '91310000MA1FL45X2K', 'STEEL', '13800000001', '钢厂采购员'),
    ('示范矿产贸易有限公司', '91310000MA1FL45X3L', 'SUPPLIER', '13800000002', '供应商销售甲'),
    ('示范矿业有限公司', '91310000MA1FL45X4M', 'SUPPLIER', '13800000003', '供应商销售乙'),
    ('示范国际供应链有限公司', '91310000MA1FL45X5N', 'SUPPLIER', '13800000004', '供应商销售丙'),
    ('示范物流运输有限公司', '91310000MA1FL45X6P', 'LOGISTICS', '13800000005', '物流操作员'),
]


def _ensure_varieties(conn):
    """品种档案幂等补齐：按 variety_code 或同名品种判定已存在（兼容旧编码库，避免同名重复）。"""
    for code, vname, grade, price in VARIETIES:
        if q1(conn, "SELECT id FROM base_variety WHERE variety_code=%s OR variety_name=%s",
              (code, vname)):
            continue
        vid = execute(conn, """
            INSERT INTO base_variety (variety_code, variety_name, default_grade, unit, sort_no)
            VALUES (%s, %s, %s, '湿吨', %s)
            RETURNING id
        """, (code, vname, grade, 99 if code == 'OTHER' else len(code)), returning_id=True)
        if price is not None:
            execute(conn, """
                INSERT INTO base_price (variety_id, price_date, price, price_basis, source_desc)
                VALUES (%s, current_date, %s, 'WET', '运营手工维护（演示数据）')
            """, (vid, price))


def _pb_variety(conn):
    """取品种 id（按名称查找）。"""
    return q1(conn, "SELECT id FROM base_variety WHERE variety_name=%s ORDER BY id LIMIT 1", ('PB粉',))


def _ensure_port_prices(conn):
    """港口现货价演示数据（幂等：表为空时写入近 14 日 黄骅港/日照港 PB粉、黄骅港 中华混一号 价格）。
    PB粉 双品位：61.5%（主）与 60.8%（低品位，价格约低 5 元/湿吨）。"""
    if q1(conn, "SELECT id FROM base_port_price LIMIT 1"):
        return
    v = _pb_variety(conn)
    if not v:
        return
    vid = v['id']
    for offset in range(13, -1, -1):
        step = (13 - offset) % 5 - 2
        hi = 780 + step * 3
        execute(conn, """
            INSERT INTO base_port_price (variety_id, port_name, price_date, price, grade)
            VALUES (%s, '黄骅港', current_date - %s, %s, 61.5)
        """, (vid, offset, hi))
        execute(conn, """
            INSERT INTO base_port_price (variety_id, port_name, price_date, price, grade)
            VALUES (%s, '黄骅港', current_date - %s, %s, 60.8)
        """, (vid, offset, hi - 5))
        step2 = (13 - offset) % 4
        lo = 775 + step2 * 2
        execute(conn, """
            INSERT INTO base_port_price (variety_id, port_name, price_date, price, grade)
            VALUES (%s, '日照港', current_date - %s, %s, 61.5)
        """, (vid, offset, lo))
        execute(conn, """
            INSERT INTO base_port_price (variety_id, port_name, price_date, price, grade)
            VALUES (%s, '日照港', current_date - %s, %s, 60.8)
        """, (vid, offset, lo - 5))


def _ensure_grade_608(conn):
    """品位补齐（幂等）：为已有 PB粉 61.5% 港口价补写 60.8% 品位行（价格约低 5 元/湿吨）。
    适用于升级前已存在港口价数据的老库，保证双品位完整。"""
    v = _pb_variety(conn)
    if not v:
        return
    execute(conn, """
        INSERT INTO base_port_price (variety_id, port_name, price_date, price, grade)
        SELECT p.variety_id, p.port_name, p.price_date, p.price - 5, 60.8
        FROM base_port_price p
        WHERE p.variety_id=%s AND p.grade=61.5 AND p.is_deleted=0
          AND NOT EXISTS (
            SELECT 1 FROM base_port_price q
            WHERE q.variety_id=p.variety_id AND q.port_name=p.port_name
              AND q.price_date=p.price_date AND q.grade=60.8 AND q.is_deleted=0)
    """, (v['id'],))


def seed(conn):
    """幂等：品种档案/港口价格按幂等补齐；已存在平台管理员则跳过账号/企业。业务单据由实际操作产生。"""
    _ensure_varieties(conn)
    # 数量单位全系统统一为湿吨：存量品种单位幂等升级
    execute(conn, "UPDATE base_variety SET unit='湿吨' WHERE unit IS NULL OR unit='' OR unit='吨'")
    _ensure_port_prices(conn)
    _ensure_grade_608(conn)
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
    # 品种档案已由 _ensure_varieties 幂等补齐
    # PB粉 港口+品位维度基准价分档：61.5%/60.8% 两档
    # （锚点：兰格钢铁网 2026-11-09 天津港 60.8% 657 元；61.5% 按品位价差 +10 推算 667）
    pb = _pb_variety(conn)
    if pb:
        for grade, tj in (('61.50', 667.00), ('60.80', 657.00)):
            for port, p in (('天津港', tj), ('黄骅港', round(tj - 2, 2))):
                execute(conn, """
                    INSERT INTO base_price (variety_id, price_date, price, price_basis, port, grade, source_desc)
                    VALUES (%s, current_date, %s, 'WET', %s, %s, '兰格钢铁网公开报价锚点·锚点间线性内插（演示）')
                """, (pb['id'], p, port, grade))
    return True
