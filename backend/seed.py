"""基础数据种子（幂等）：平台管理员、演示企业与账号、品种档案与当日基准价。

业务单据由实际操作产生；仅合同管理/运输调度预置少量演示单据（_ensure_demo_contracts，幂等）。

账号约定：
  平台管理员  13800000000 / admin123456
  钢厂        13800000001 / demo123456
  供应商×3    13800000002-04 / demo123456
  承运商      13800000005 / demo123456
"""
import os

from . import UPLOAD_DIR
from .db import execute, q1
from .security import hash_password

VARIETIES = [
    # (variety_code, variety_name, 品类 category, default_grade, 当日基准价)
    ('IRON_ORE_POWDER', '铁矿石粉矿', '粉矿', '61.50', 760.00),
    ('IRON_ORE_LUMP', '铁矿石块矿', '块矿', '62.50', 820.00),
    ('IRON_ORE_CONCENTRATE', '铁精粉', '精粉', '65.00', 905.00),
    ('IRON_ORE_PELLET', '球团矿', '球团', '64.00', 960.00),
    ('IRON_ORE_PB_POWDER', 'PB粉', '粉矿', '62.00', 780.00),
    ('IRON_ORE_ZH_MIX_1', '中华混一号', '混矿', '61.50', 770.00),
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


def _ensure_varieties(conn):
    """品种档案按 variety_code 幂等补齐：已有库无需重建即可获得新增品种。
    种子（幂等）：已存在平台管理员则跳过账号/企业。"""
    for code, vname, category, grade, price in VARIETIES:
        if q1(conn, "SELECT id FROM base_variety WHERE variety_code=%s", (code,)):
            continue
        vid = execute(conn, """
            INSERT INTO base_variety (variety_code, variety_name, category, default_grade, unit, sort_no)
            VALUES (%s, %s, %s, %s, '吨', %s)
            RETURNING id
        """, (code, vname, category, grade, len(code)), returning_id=True)
        execute(conn, """
            INSERT INTO base_price (variety_id, price_date, price, price_basis, source_desc)
            VALUES (%s, current_date, %s, 'WET', '运营手工维护（演示数据）')
        """, (vid, price))


def _ensure_categories(conn):
    """存量品种品类补齐（幂等：仅当 category 为空时按种子回填）。"""
    for code, vname, category, grade, price in VARIETIES:
        execute(conn, """
            UPDATE base_variety SET category=%s
            WHERE variety_code=%s AND (category IS NULL OR category='')
        """, (category, code))


def _ensure_port_prices(conn):
    """港口现货价演示数据（幂等：表为空时写入近 14 日 黄骅港/日照港 PB粉 价格）。"""
    if q1(conn, "SELECT id FROM base_port_price LIMIT 1"):
        return
    v = q1(conn, "SELECT id FROM base_variety WHERE variety_code='IRON_ORE_PB_POWDER'")
    if not v:
        return
    vid = v['id']
    for offset in range(13, -1, -1):
        step = (13 - offset) % 5 - 2
        execute(conn, """
            INSERT INTO base_port_price (variety_id, port_name, price_date, price)
            VALUES (%s, '黄骅港', current_date - %s, %s)
            ON CONFLICT (variety_id, port_name, price_date) DO NOTHING
        """, (vid, offset, 780 + step * 3))
        step2 = (13 - offset) % 4
        execute(conn, """
            INSERT INTO base_port_price (variety_id, port_name, price_date, price)
            VALUES (%s, '日照港', current_date - %s, %s)
            ON CONFLICT (variety_id, port_name, price_date) DO NOTHING
        """, (vid, offset, 775 + step2 * 2))


def _demo_pdf():
    """最小可打开的演示 PDF（合同扫描件占位）。"""
    stream = b"BT /F1 12 Tf 20 60 Td (Demo Contract Scan) Tj ET"
    return (b"%PDF-1.4\n"
            b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
            b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
            b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 320 120]/Contents 4 0 R"
            b"/Resources<</Font<</F1 5 0 R>>>>>>endobj\n"
            b"4 0 obj<</Length " + str(len(stream)).encode() + b">>stream\n" + stream +
            b"\nendstream endobj\n"
            b"5 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj\n"
            b"trailer<</Root 1 0 R>>\n%%EOF")


def _ensure_demo_contracts(conn):
    """合同管理/运输调度 演示数据（幂等）：仅当 biz_contract 为空且种子企业齐备时写入，
    覆盖 待核验/已核验入台账/已退回 三类状态，并附物流方案与分段运单用于调度展示。"""
    if q1(conn, "SELECT id FROM biz_contract LIMIT 1"):
        return
    buyer = q1(conn, "SELECT id FROM ent_company WHERE company_types LIKE '%%STEEL%%' AND is_deleted=0 ORDER BY id LIMIT 1")
    sup_a = q1(conn, "SELECT id FROM ent_company WHERE credit_code='91310000MA1FL45X3L' AND is_deleted=0")
    sup_b = q1(conn, "SELECT id FROM ent_company WHERE credit_code='91310000MA1FL45X4M' AND is_deleted=0")
    carrier = q1(conn, "SELECT id FROM ent_company WHERE credit_code='91310000MA1FL45X6P' AND is_deleted=0")
    v1 = q1(conn, "SELECT id FROM base_variety WHERE variety_code='IRON_ORE_POWDER'")
    v2 = q1(conn, "SELECT id FROM base_variety WHERE variety_code='IRON_ORE_PB_POWDER'")
    if not (buyer and sup_a and sup_b and carrier and v1 and v2):
        return
    buyer_id, a_id, b_id, car_id = buyer['id'], sup_a['id'], sup_b['id'], carrier['id']

    def demo_file(file_id, disk_name, file_name):
        path = os.path.join(UPLOAD_DIR, disk_name)
        if not os.path.exists(path):
            with open(path, 'wb') as f:
                f.write(_demo_pdf())
        if not q1(conn, "SELECT id FROM sys_file WHERE file_id=%s", (file_id,)):
            execute(conn, """
                INSERT INTO sys_file (file_id, file_name, content_type, size_bytes, path)
                VALUES (%s, %s, 'application/pdf', %s, %s)
            """, (file_id, file_name, os.path.getsize(path), path))
        return file_id

    def demo_order(order_no, supplier_id, variety_id, grade, qty, price, status, days_ago):
        return execute(conn, """
            INSERT INTO biz_order (order_no, buyer_id, supplier_id, variety_id, grade, quantity,
                                   unit_price, amount, price_basis, delivery_type, delivery_place,
                                   delivery_date, settle_type, status, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'WET', 'PORT_TRUCK', '日照港',
                    current_date + 15, 'MONTH_SETTLE', %s,
                    now() - make_interval(days => %s::int), now() - make_interval(days => %s::int))
            RETURNING id
        """, (order_no, buyer_id, supplier_id, variety_id, grade, qty, price, qty * price,
              status, days_ago, days_ago), returning_id=True)

    def demo_contract(contract_no, order_id, status, plat_status, file_id, buyer_days, supplier_days,
                      confirm_days=None, remark=None):
        execute(conn, """
            INSERT INTO biz_contract (contract_no, order_id, version, signature_type, file_url,
                buyer_sign_at, supplier_sign_at, status, plat_status, plat_remark,
                plat_confirm_at, created_at, updated_at)
            VALUES (%s, %s, 1, 'PLATFORM_CONFIRM', %s,
                now() - make_interval(days => %s::int),
                CASE WHEN %s::int IS NULL THEN NULL ELSE now() - make_interval(days => %s::int) END,
                %s, %s, %s,
                CASE WHEN %s::int IS NULL THEN NULL ELSE now() - make_interval(days => %s::int) END,
                now() - make_interval(days => GREATEST(%s::int, 4)),
                now())
        """, (contract_no, order_id, file_id, buyer_days, supplier_days, supplier_days,
              status, plat_status, remark, confirm_days, confirm_days, max(buyer_days, 4)))

    f1 = demo_file('democontractscan0000000000000001', 'demo-contract-1.pdf', '购销合同扫描件-演示1.pdf')
    f2 = demo_file('democontractscan0000000000000002', 'demo-contract-2.pdf', '购销合同扫描件-演示2.pdf')

    # 订单（演示）：两条履约中 + 两条待生效（对应待核验合同）
    o1 = demo_order('DD-20261108-9001', a_id, v1['id'], '61.50', 20000, 765.00, 'PERFORMING', 3)
    o2 = demo_order('DD-20261109-9002', b_id, v2['id'], '62.00', 12000, 778.00, 'PERFORMING', 2)
    o3 = demo_order('DD-20261110-9003', a_id, v1['id'], '61.50', 8000, 772.00, 'PENDING_EFFECT', 1)
    o4 = demo_order('DD-20261111-9004', b_id, v2['id'], '62.00', 15000, 780.00, 'PENDING_EFFECT', 1)

    # 合同：已核验入台账×2、待核验×2（其一未上传扫描件）、已退回×1
    demo_contract('HT-20261108-9001', o1, 'EFFECTIVE', 'CONFIRMED', f1, 3, 3, confirm_days=2)
    demo_contract('HT-20261109-9002', o2, 'EFFECTIVE', 'CONFIRMED', f2, 2, 2, confirm_days=1)
    demo_contract('HT-20261110-9003', o3, 'PENDING_SUPPLIER', 'PENDING', f1, 1, 1)
    demo_contract('HT-20261111-9004', o4, 'PENDING_SUPPLIER', 'PENDING', None, 1, None)
    demo_contract('HT-20261107-9005', o1, 'PENDING_SUPPLIER', 'RETURNED', None, 4, None,
                  remark='扫描件印章不清晰，请重新上传')

    # 物流方案 + 分段运单（用于运输调度/在途监控展示）
    plan_id = execute(conn, """
        INSERT INTO biz_logistics_plan (plan_no, order_id, org_mode, remark, status, created_at)
        VALUES ('WL-20261109-9001', %s, 'PLATFORM', '演示方案：港口汽运+铁运分两段发运', 'ACTIVE',
                now() - make_interval(days => 1))
        RETURNING id
    """, (o2,), returning_id=True)
    execute(conn, """
        INSERT INTO biz_waybill (waybill_no, order_id, plan_id, segment_no, carrier_id, transport_mode,
            depart_place, arrive_place, plan_depart_date, plan_arrive_date, plan_qty, freight,
            vehicle_no, actual_qty, actual_depart_at, status, created_at)
        VALUES ('YD-20261109-9001', %s, %s, 1, %s, 'ROAD', '日照港', '钢厂厂区',
            current_date - 1, current_date + 1, 6000, 132000.00, '冀A88888', 6000,
            now() - make_interval(hours => 20), 'IN_TRANSIT', now() - make_interval(days => 1))
    """, (o2, plan_id, car_id))
    execute(conn, """
        INSERT INTO biz_waybill (waybill_no, order_id, plan_id, segment_no, carrier_id, transport_mode,
            depart_place, arrive_place, plan_depart_date, plan_arrive_date, plan_qty, freight,
            vehicle_no, status, created_at)
        VALUES ('YD-20261109-9002', %s, %s, 2, %s, 'RAIL', '日照港站', '钢厂专用线',
            current_date + 2, current_date + 4, 6000, 96000.00, 'D0105',
            'PENDING_DEPART', now() - make_interval(days => 1))
    """, (o2, plan_id, car_id))


def seed(conn):
    """幂等：品种档案/港口价格/演示合同单据按幂等补齐；已存在平台管理员则跳过账号/企业。"""
    _ensure_varieties(conn)
    _ensure_categories(conn)
    _ensure_port_prices(conn)
    _ensure_demo_contracts(conn)
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
    # 品种档案已由 _ensure_varieties 幂等补齐（新增品种无需重建库）
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
