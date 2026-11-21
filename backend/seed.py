"""种子数据（幂等）：基础数据（品种档案/当日基准价/港口现货价）+ 演示数据（企业/账号/合同/消息）。

生产部署：MINE_SEED_BASE=1 仅写入基础数据（不含任何账号与企业，管理员经 manage.py create-admin 创建）；
本地开发/回归测试：MINE_SEED_DEMO=1 写入基础数据 + 演示数据全套。

业务单据由实际操作产生；仅合同管理/运输调度预置少量演示单据（_ensure_demo_contracts，幂等）。

演示账号约定（仅 MINE_SEED_DEMO=1 时写入）：
  平台管理员  13800000000 / admin123456
  钢厂        13800000001 / demo123456
  供应商×3    13800000002-04 / demo123456
  承运商      13800000005 / demo123456
"""
import os

from . import UPLOAD_DIR
from .db import execute, q1, qall
from .security import hash_password

VARIETIES = [
    # (variety_code, variety_name, default_grade, 当日基准价)
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
    """品种档案幂等补齐：按 variety_code 或同名品种判定已存在（兼容旧编码库，避免同名重复）。"""
    for code, vname, grade, price in VARIETIES:
        if q1(conn, "SELECT id FROM base_variety WHERE variety_code=%s OR variety_name=%s",
              (code, vname)):
            continue
        vid = execute(conn, """
            INSERT INTO base_variety (variety_code, variety_name, default_grade, unit, sort_no)
            VALUES (%s, %s, %s, '吨', %s)
            RETURNING id
        """, (code, vname, grade, len(code)), returning_id=True)
        execute(conn, """
            INSERT INTO base_price (variety_id, price_date, price, price_basis, source_desc)
            VALUES (%s, current_date, %s, 'WET', '运营手工维护')
        """, (vid, price))


def _pb_variety(conn):
    """取 PB粉 品种（兼容新旧编码，按名称查找）。"""
    return q1(conn, "SELECT id FROM base_variety WHERE variety_name='PB粉' ORDER BY id LIMIT 1")


def _ensure_port_prices(conn):
    """港口现货价演示数据（幂等：表为空时写入近 14 日 黄骅港/日照港 PB粉 价格）。
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
            ON CONFLICT (variety_id, port_name, price_date, grade) DO NOTHING
        """, (vid, offset, hi))
        execute(conn, """
            INSERT INTO base_port_price (variety_id, port_name, price_date, price, grade)
            VALUES (%s, '黄骅港', current_date - %s, %s, 60.8)
            ON CONFLICT (variety_id, port_name, price_date, grade) DO NOTHING
        """, (vid, offset, hi - 5))
        step2 = (13 - offset) % 4
        lo = 775 + step2 * 2
        execute(conn, """
            INSERT INTO base_port_price (variety_id, port_name, price_date, price, grade)
            VALUES (%s, '日照港', current_date - %s, %s, 61.5)
            ON CONFLICT (variety_id, port_name, price_date, grade) DO NOTHING
        """, (vid, offset, lo))
        execute(conn, """
            INSERT INTO base_port_price (variety_id, port_name, price_date, price, grade)
            VALUES (%s, '日照港', current_date - %s, %s, 60.8)
            ON CONFLICT (variety_id, port_name, price_date, grade) DO NOTHING
        """, (vid, offset, lo - 5))


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
    v1 = q1(conn, "SELECT id FROM base_variety WHERE variety_name='中华混一号' ORDER BY id LIMIT 1") \
        or q1(conn, "SELECT id FROM base_variety ORDER BY id LIMIT 1")
    v2 = _pb_variety(conn)
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
    o2 = demo_order('DD-20261109-9002', b_id, v2['id'], '61.50', 12000, 778.00, 'PERFORMING', 2)
    o3 = demo_order('DD-20261110-9003', a_id, v1['id'], '61.50', 8000, 772.00, 'PENDING_EFFECT', 1)
    o4 = demo_order('DD-20261111-9004', b_id, v2['id'], '61.50', 15000, 780.00, 'PENDING_EFFECT', 1)

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


def _ensure_demo_messages(conn):
    """消息中心演示数据（幂等：按分类补齐，不覆盖业务消息）。

    四类消息：通知 NOTICE / 预警 WARN / 公告 ANNOUNCE / 活动信息 ACTIVITY。
    平台消息 receiver_company_id 为空（运营端可见）；企业消息按企业写入。
    """
    # 平台演示消息（尚无公告/活动/预警类平台消息时写入）
    if not q1(conn, "SELECT id FROM sys_message WHERE receiver_company_id IS NULL "
                    "AND msg_category IN ('ANNOUNCE','ACTIVITY','WARN') LIMIT 1"):
        plats = [
            ('平台11月集采专场启动公告', '11 月 20 日 10:00 开启 PB粉/中华混一号 集采专场，欢迎各钢厂参与联合采购。', 'ANNOUNCE'),
            ('邀请好友活动进行中', '11 月 30 日前成功邀请合作企业入驻，双方各得 500 元平台服务费抵扣券。', 'ACTIVITY'),
            ('价格异动提醒', '今日 PB粉 港口现货价较昨日上涨 0.8%，请关注采购成本变化。', 'WARN'),
            ('系统维护通知', '11 月 15 日 02:00-04:00 系统升级维护，期间将暂停服务，请提前安排业务。', 'NOTICE'),
        ]
        for title, content, cat in plats:
            execute(conn, """
                INSERT INTO sys_message (receiver_company_id, title, content, biz_type, biz_id, msg_category)
                VALUES (NULL, %s, %s, NULL, NULL, %s)
            """, (title, content, cat))
    # 企业演示消息（尚无企业收到的预警类消息时写入）
    if not q1(conn, "SELECT id FROM sys_message WHERE receiver_company_id IS NOT NULL AND msg_category='WARN' LIMIT 1"):
        comps = qall(conn, "SELECT id FROM ent_company WHERE is_deleted=0 ORDER BY id LIMIT 5")
        comp_msgs = [
            ('合同签署提醒', '您有合同待签署，请及时进入合同模块处理。', 'NOTICE', 'CONTRACT'),
            ('运单时效预警', '您名下有运单即将超出计划发运时间，请尽快安排。', 'WARN', 'WAYBILL'),
            ('新询价邀请', '您收到新的询价邀请，报价截止前请及时响应。', 'NOTICE', 'INQUIRY'),
        ]
        for c in comps:
            for title, content, cat, bt in comp_msgs:
                execute(conn, """
                    INSERT INTO sys_message (receiver_company_id, title, content, biz_type, biz_id, msg_category)
                    VALUES (%s, %s, %s, %s, NULL, %s)
                """, (c['id'], title, content, bt, cat))


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


def _ensure_pb_port_prices(conn):
    """PB粉 港口+品位维度基准价分档（幂等）：当日已有分档行则跳过。
    锚点：兰格钢铁网 2026-11-09 天津港 60.8% 657 元；61.5% 按品位价差 +10 推算 667。"""
    pb = _pb_variety(conn)
    if not pb:
        return
    if q1(conn, "SELECT id FROM base_price WHERE variety_id=%s AND price_date=current_date "
                "AND port IS NOT NULL LIMIT 1", (pb['id'],)):
        return
    # 61.5%/60.8% 两档分档价
    for grade, tj in (('61.50', 667.00), ('60.80', 657.00)):
        for port, p in (('天津港', tj), ('黄骅港', round(tj - 2, 2))):
            execute(conn, """
                INSERT INTO base_price (variety_id, price_date, price, price_basis, port, grade, source_desc)
                VALUES (%s, current_date, %s, 'WET', %s, %s, '兰格钢铁网公开报价锚点·锚点间线性内插')
            """, (pb['id'], p, port, grade))


def seed_base_data(conn):
    """生产基础数据（幂等，不含任何账号与企业）：品种档案、当日基准价、港口现货价。

    由 run.py 在 MINE_SEED_BASE=1 时调用；管理员账号经 manage.py create-admin 创建。"""
    _ensure_varieties(conn)
    _ensure_port_prices(conn)
    _ensure_grade_608(conn)
    _ensure_pb_port_prices(conn)


def seed(conn):
    """幂等：基础数据/港口价格/演示合同单据/演示消息按幂等补齐；已存在平台管理员则跳过账号/企业。"""
    seed_base_data(conn)
    _ensure_demo_contracts(conn)
    _ensure_demo_messages(conn)
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
    return True

