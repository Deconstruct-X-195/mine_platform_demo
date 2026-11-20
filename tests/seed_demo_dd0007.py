# -*- coding: utf-8 -*-
"""重建钢厂端物流服务/履约跟踪页演示数据（对齐 2026-11-15/16 截图口径，幂等）。

数据集一：集采聚合订单 DD-20261115-0007（示范钢铁成员份额 6,500 湿吨 · 供应商示范矿产贸易）
  - 归集订单 GC-20261115-0002 / 询价 XJ-20261115-0009（平台归集询价，已定标 2026-11-15 20:48）
  - 议价反馈：本厂认可
  - 提货计划：开始 2026-12-01 · 日提 400 湿吨（已提交 2026-11-15 20:49）
  - 物流方案 WL-20261115-0004（平台配送，创建 2026-11-15 20:50）
  - 运单×4（节点时间对齐截图时间线 9 条事件）：
      YD-20261115-0005 铁路直达 第1列 3,000 已签收（出港 11-16 09:52 / 到达 11-17 09:52）
      YD-20261115-0006 铁路直达 第2列 3,500 已到达（船到港 11-25 09:30 / 出港 11-26 08:00 / 到达 11-30 15:00）
      YD-20261116-0001 公铁联运 第3列 3,000 待发运（创建 11-16 22:10）
      YD-20261116-0002 汽运直达 全程 2,500 待发运（创建 11-16 22:10）
  - 订单履约节点（ORDER_CREATED/ORDER_CONFIRMED 2026-11-15 20:48）
  预期货物信息：出港 6,500 / 在途 0 / 到站 6,500 / 可提货 3,500 湿吨。

数据集二：DD-20261115-0009 聚合订单待供应商确认
  （履约跟踪页五阶段「双方确认进行中 / 提货计划待提交」演示单）。

运行：py tests/seed_demo_dd0007.py（幂等：按单号守卫，已存在则跳过）
"""
import os
import sys
from datetime import datetime, timedelta

import psycopg
from psycopg.rows import dict_row

PG_DSN = os.environ.get('MINE_PG_DSN', 'postgresql://postgres:Langchain2026@127.0.0.1:5432/mine_platform')

ORDER_NO = 'DD-20261115-0007'


def cols(conn, table):
    """活库列名集合（以实际库为准，兼容 schema 演进）。"""
    rows = conn.execute("""
        SELECT column_name FROM information_schema.columns WHERE table_name=%s
    """, (table,)).fetchall()
    return {r['column_name'] for r in rows}


def ins(conn, table, data):
    """按活库实际存在的列过滤后插入，返回 id。"""
    have = cols(conn, table)
    filtered = {k: v for k, v in data.items() if k in have}
    keys = ', '.join(filtered.keys())
    phs = ', '.join('%(' + k + ')s' for k in filtered)
    sql = 'INSERT INTO %s (%s) VALUES (%s) RETURNING id' % (table, keys, phs)
    return conn.execute(sql, filtered).fetchone()['id']


def node(conn, biz_type, biz_id, code, name, occur):
    ins(conn, 'biz_track_node', {
        'biz_type': biz_type, 'biz_id': biz_id, 'node_code': code, 'node_name': name,
        'occur_time': occur, 'source': 'SYSTEM', 'created_at': occur,
    })


def ensure_variety(conn):
    v = conn.execute("SELECT id FROM base_variety WHERE variety_name='铁矿石粉矿' AND is_deleted=0").fetchone()
    if v:
        return v
    vid = ins(conn, 'base_variety', {
        'variety_code': 'IRON_ORE_FINES', 'variety_name': '铁矿石粉矿',
        'default_grade': '61.50', 'unit': '湿吨', 'sort_no': 3,
    })
    ins(conn, 'base_price', {
        'variety_id': vid, 'price_date': '2026-11-15', 'price': 749.00,
        'price_basis': 'WET', 'source_desc': '演示数据（2026-11-15 定标价锚点）',
    })
    return {'id': vid}


def seed_dd0007(conn, steel, sup, carrier, v):
    """DD-20261115-0007：聚合订单履约中（方案 + 4 运单 + 节点时间线）。"""
    # 归集订单（聚合询价来源，满足反馈表 agg_id 非空约束）
    agg_id = ins(conn, 'biz_aggregated_order', {
        'agg_no': 'GC-20261115-0002', 'variety_id': v['id'], 'grade': '61.50',
        'total_qty': 6500, 'status': 'CLOSED', 'remark': '演示归集：铁矿石粉矿 61.50%',
        'created_at': '2026-11-15 20:46:00', 'updated_at': '2026-11-15 20:48:00',
    })
    # 询价（平台归集询价，已定标）
    inq_id = ins(conn, 'biz_inquiry', {
        'inquiry_no': 'XJ-20261115-0009', 'buyer_id': None, 'variety_id': v['id'],
        'grade': '61.50', 'quantity': 6500, 'deadline': '2026-11-19 18:00:00',
        'status': 'AWARDED', 'source': 'PLATFORM', 'agg_id': agg_id,
        'delivery_place': '特钢厂区', 'settle_type': 'MONTH_SETTLE',
        'created_at': '2026-11-15 20:48:00', 'updated_at': '2026-11-15 20:48:00',
    })
    # 订单（集采聚合：buyer_id 空，成员行存钢厂份额）
    oid = ins(conn, 'biz_order', {
        'order_no': ORDER_NO, 'inquiry_id': inq_id, 'buyer_id': None, 'supplier_id': sup['id'],
        'variety_id': v['id'], 'grade': '61.50', 'quantity': 6500,
        'unit_price': 749.00, 'amount': 4868500.00, 'price_basis': 'WET',
        'delivery_type': 'PORT_PICKUP', 'delivery_place': '特钢厂区',
        'delivery_date': '2026-12-05', 'settle_type': 'MONTH_SETTLE',
        'status': 'PERFORMING',
        'created_at': '2026-11-15 20:48:00', 'updated_at': '2026-11-15 20:50:00',
    })
    # 成员钢厂（份额 + 提货计划已提交）
    ins(conn, 'biz_order_member', {
        'order_id': oid, 'company_id': steel['id'], 'quantity': 6500,
        'pickup_status': 'SUBMITTED', 'pickup_start_date': '2026-12-01',
        'daily_qty': 400, 'pickup_remark': '连续提货',
        'submitted_at': '2026-11-15 20:49:00',
        'created_at': '2026-11-15 20:48:00',
    })
    # 议价反馈（本厂认可）
    ins(conn, 'biz_agg_inquiry_feedback', {
        'inquiry_id': inq_id, 'agg_id': agg_id, 'company_id': steel['id'],
        'decision': 'ACCEPTED', 'created_at': '2026-11-15 20:48:30',
    })
    # 履约节点：订单生成 / 双方确认
    node(conn, 'ORDER', oid, 'ORDER_CREATED', '订单生成', '2026-11-15 20:48:00')
    node(conn, 'ORDER', oid, 'ORDER_CONFIRMED', '订单确认', '2026-11-15 20:48:00')
    # 物流方案（平台配送，创建 2026-11-15 20:50）
    plan_id = ins(conn, 'biz_logistics_plan', {
        'plan_no': 'WL-20261115-0004', 'order_id': oid, 'org_mode': 'PLATFORM',
        'remark': '演示方案：铁路两列 + 公铁联运一列 + 汽运直达',
        'status': 'ACTIVE', 'created_at': '2026-11-15 20:50:00', 'updated_at': '2026-11-15 20:50:00',
    })
    # 运单×4（节点时间对齐截图时间线）
    wbs = [
        {  # 第1列：已签收（出港 11-16 09:52 → 到达 11-17 09:52）
            'waybill_no': 'YD-20261115-0005', 'order_id': oid, 'plan_id': plan_id,
            'segment_no': '1', 'carrier_id': carrier['id'], 'transport_mode': 'RAIL',
            'depart_place': '黄骅港', 'arrive_place': '特钢厂区',
            'plan_depart_date': '2026-11-16', 'plan_arrive_date': '2026-11-17',
            'plan_qty': 3000, 'actual_qty': 3000, 'freight': 96000.00, 'vehicle_no': 'D0101',
            'actual_depart_at': '2026-11-16 09:52:00', 'actual_arrive_at': '2026-11-17 09:52:00',
            'status': 'SIGNED', 'created_at': '2026-11-15 20:51:00', 'updated_at': '2026-11-17 10:05:00',
        },
        {  # 第2列：已到达（船到港 11-25 09:30 → 出港 11-26 08:00 → 到达 11-30 15:00）
            'waybill_no': 'YD-20261115-0006', 'order_id': oid, 'plan_id': plan_id,
            'segment_no': '2', 'carrier_id': carrier['id'], 'transport_mode': 'RAIL',
            'depart_place': '黄骅港', 'arrive_place': '特钢厂区',
            'plan_depart_date': '2026-11-26', 'plan_arrive_date': '2026-11-30',
            'plan_qty': 3500, 'actual_qty': 3500, 'freight': 112000.00, 'vehicle_no': 'D0102',
            'eta_at': '2026-11-24 18:00:00', 'actual_eta_at': '2026-11-25 09:30:00',
            'actual_depart_at': '2026-11-26 08:00:00', 'actual_arrive_at': '2026-11-30 15:00:00',
            'status': 'ARRIVED', 'created_at': '2026-11-15 20:51:00', 'updated_at': '2026-11-30 15:10:00',
        },
        {  # 第3列：公铁联运待发运
            'waybill_no': 'YD-20261116-0001', 'order_id': oid, 'plan_id': plan_id,
            'segment_no': '3', 'carrier_id': carrier['id'], 'transport_mode': 'MULTIMODAL',
            'depart_place': '黄骅港', 'arrive_place': '特钢厂区', 'transit_station': '沧州北站',
            'plan_depart_date': '2026-12-01', 'plan_arrive_date': '2026-12-03',
            'plan_qty': 3000, 'freight': 108000.00, 'vehicle_no': 'D0105',
            'status': 'PENDING_DEPART', 'created_at': '2026-11-16 22:10:00', 'updated_at': '2026-11-16 22:10:00',
        },
        {  # 汽运直达待发运
            'waybill_no': 'YD-20261116-0002', 'order_id': oid, 'plan_id': plan_id,
            'segment_no': '4', 'carrier_id': carrier['id'], 'transport_mode': 'ROAD',
            'depart_place': '黄骅港', 'arrive_place': '特钢厂区',
            'plan_depart_date': '2026-12-01', 'plan_arrive_date': '2026-12-02',
            'plan_qty': 2500, 'freight': 82500.00, 'vehicle_no': '冀A66666',
            'status': 'PENDING_DEPART', 'created_at': '2026-11-16 22:10:00', 'updated_at': '2026-11-16 22:10:00',
        },
    ]
    for w in wbs:
        wid = ins(conn, 'biz_waybill', w)
        # 运单生成节点（供应商端 95306 轨迹与履约台账用）
        node(conn, 'WAYBILL', wid, 'WAYBILL_CREATED', '运单已生成', w['created_at'])
    conn.commit()
    print('OK: %s 已重建（order_id=%s，运单×4，方案 WL-20261115-0004）' % (ORDER_NO, oid))


def seed_dd0009(conn, steel, sup, v):
    """DD-20261115-0009：聚合订单待供应商确认（五阶段「双方确认进行中/提货计划待提交」演示）。"""
    oid9 = ins(conn, 'biz_order', {
        'order_no': 'DD-20261115-0009', 'buyer_id': None, 'supplier_id': sup['id'],
        'variety_id': v['id'], 'grade': '61.50', 'quantity': 6000,
        'unit_price': 752.00, 'amount': 4512000.00, 'price_basis': 'WET',
        'delivery_type': 'PORT_PICKUP', 'delivery_place': '特钢厂区',
        'delivery_date': '2026-12-08', 'settle_type': 'MONTH_SETTLE',
        'status': 'PENDING_CONFIRM',
        # 确认截止动态取未来 2 天：避免 jobs._expire_orders 把演示单扫描失效（原 2026-11-17 20:52 已过期）
        'confirm_deadline': (datetime.now() + timedelta(days=2)).strftime('%Y-%m-%d %H:%M:%S'),
        'created_at': '2026-11-15 20:52:00', 'updated_at': '2026-11-15 20:52:00',
    })
    ins(conn, 'biz_order_member', {
        'order_id': oid9, 'company_id': steel['id'], 'quantity': 6000,
        'pickup_status': 'PENDING', 'created_at': '2026-11-15 20:52:00',
    })
    node(conn, 'ORDER', oid9, 'ORDER_CREATED', '订单生成', '2026-11-15 20:52:00')
    conn.commit()
    print('OK: DD-20261115-0009 已重建（order_id=%s，PENDING_CONFIRM）' % oid9)


def main():
    with psycopg.connect(PG_DSN, row_factory=dict_row) as conn:
        # 企业
        steel = conn.execute("SELECT id FROM ent_company WHERE company_name='示范钢铁集团有限公司' AND is_deleted=0").fetchone()
        sup = conn.execute("SELECT id FROM ent_company WHERE company_name='示范矿产贸易有限公司' AND is_deleted=0").fetchone()
        carrier = conn.execute("SELECT id FROM ent_company WHERE company_name='示范物流运输有限公司' AND is_deleted=0").fetchone()
        assert steel and sup and carrier, '种子企业缺失（请先启动后端完成 seed）'
        v = ensure_variety(conn)
        if conn.execute("SELECT id FROM biz_order WHERE order_no=%s", (ORDER_NO,)).fetchone():
            print('SKIP: %s 已存在' % ORDER_NO)
        else:
            seed_dd0007(conn, steel, sup, carrier, v)
        if conn.execute("SELECT id FROM biz_order WHERE order_no='DD-20261115-0009'").fetchone():
            print('SKIP: DD-20261115-0009 已存在')
        else:
            seed_dd0009(conn, steel, sup, v)


if __name__ == '__main__':
    main()
    sys.exit(0)
