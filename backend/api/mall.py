# -*- coding: utf-8 -*-
"""采购商城模块（现货直购）：有限铁矿石商品、搜索/筛选、下游企业下单、我的商城订单"""
from flask import Blueprint, request, g
from ..db import get_db, _now
from ..utils import ok, err, log_action, paginate
from ..auth import roles_required, company_approved_required

bp = Blueprint('mall', __name__)

# 商城在售商品（demo：有限铁矿石产品，ore_type 对应 IRON_ORE_TYPE 字典，ore_category 对应 ORE_CATEGORY 字典）
# image：本地实拍图（frontend/assets/img/mall/，按矿种对应）；market_price：市场参考价（随行情）；price：商城售价
_IMG_FILES = {
    'PB_FINES':   '/assets/img/mall/pb_fines.jpg',
    'CARTER':     '/assets/img/mall/carter.jpg',
    'ULTRA_FINE': '/assets/img/mall/ultra_fine.jpg',
    'BR_BLEND':   '/assets/img/mall/br_blend.jpg',
    'BR_COARSE':  '/assets/img/mall/br_coarse.jpg',
    'NEWMAN':     '/assets/img/mall/newman.jpg',
    'JIMBLEBAR':  '/assets/img/mall/jimblebar.jpg',
    'SA_FINES':   '/assets/img/mall/sa_fines.jpg',
    'KA_FINE':    '/assets/img/mall/ka_fine.jpg',
    'FMG_BLEND':  '/assets/img/mall/fmg_blend.jpg',
}
PRODUCTS = [
    {'id': 1,  'ore_category': 'IRON', 'ore_type': 'PB_FINES',   'name': 'PB粉',      'spec': 'TFe 61.5%', 'origin': '澳大利亚', 'brand': '皮尔巴拉矿业', 'price': 782,  'market_price': 786, 'sold': 126, 'tags': ['现货', '含税出厂']},
    {'id': 2,  'ore_category': 'IRON', 'ore_type': 'CARTER',     'name': '卡特粉',    'spec': 'TFe 61%',   'origin': '澳大利亚', 'brand': '卡特矿业',     'price': 748,  'market_price': 753, 'sold': 87,  'tags': ['现货']},
    {'id': 3,  'ore_category': 'IRON', 'ore_type': 'ULTRA_FINE', 'name': '超特粉',    'spec': 'TFe 56.5%', 'origin': '澳大利亚', 'brand': '超特联合矿业', 'price': 665,  'market_price': 668, 'sold': 203, 'tags': ['现货', '促销']},
    {'id': 4,  'ore_category': 'IRON', 'ore_type': 'BR_BLEND',   'name': '巴西混合',  'spec': 'TFe 62%',   'origin': '巴西',     'brand': '淡水河谷',     'price': 826,  'market_price': 830, 'sold': 64,  'tags': ['现货', '含税出厂']},
    {'id': 5,  'ore_category': 'IRON', 'ore_type': 'BR_COARSE',  'name': '巴西粗粉',  'spec': 'TFe 62.2%', 'origin': '巴西',     'brand': '淡水河谷',     'price': 838,  'market_price': 843, 'sold': 51,  'tags': ['现货']},
    {'id': 6,  'ore_category': 'IRON', 'ore_type': 'NEWMAN',     'name': '纽曼筛后',  'spec': 'TFe 61.8%', 'origin': '澳大利亚', 'brand': '必和必拓',     'price': 842,  'market_price': 847, 'sold': 43,  'tags': ['现货']},
    {'id': 7,  'ore_category': 'IRON', 'ore_type': 'JIMBLEBAR',  'name': '金布巴粉',  'spec': 'TFe 61.3%', 'origin': '澳大利亚', 'brand': '必和必拓',     'price': 824,  'market_price': 829, 'sold': 38,  'tags': ['现货', '含税出厂']},
    {'id': 8,  'ore_category': 'IRON', 'ore_type': 'SA_FINES',   'name': '南非粉',    'spec': 'TFe 58.5%', 'origin': '南非',     'brand': '南非 Kumba',   'price': 705,  'market_price': 709, 'sold': 95,  'tags': ['现货']},
    {'id': 9,  'ore_category': 'IRON', 'ore_type': 'KA_FINE',    'name': '卡粉',      'spec': 'TFe 61.8%', 'origin': '巴西',     'brand': '淡水河谷',     'price': 855,  'market_price': 860, 'sold': 29,  'tags': ['现货', '精品']},
    {'id': 10, 'ore_category': 'IRON', 'ore_type': 'FMG_BLEND',  'name': 'FMG混合粉', 'spec': 'TFe 58%',   'origin': '澳大利亚', 'brand': 'FMG 福蒂斯丘', 'price': 688,  'market_price': 692, 'sold': 178, 'tags': ['现货', '促销']},
]
# 注入商品实拍图
for _p in PRODUCTS:
    _p['image'] = _IMG_FILES[_p['ore_type']]


@bp.get('/mall/products')
def mall_products():
    """商品列表：支持关键词（名称/产地/规格）、品类与矿种筛选（品类↔矿种级联）"""
    kw = (request.args.get('keyword') or '').strip()
    ore_category = (request.args.get('ore_category') or '').strip()
    ore_type = (request.args.get('ore_type') or '').strip()
    items = PRODUCTS
    if kw:
        items = [p for p in items if kw in p['name'] or kw in p['origin'] or kw in p['spec']]
    if ore_category:
        items = [p for p in items if p['ore_category'] == ore_category]
    if ore_type:
        items = [p for p in items if p['ore_type'] == ore_type]
    return ok({'list': items, 'total': len(items)})


@bp.post('/mall/order')
@roles_required('R1')
@company_approved_required
def mall_order():
    """商城下单（现货直购）"""
    d = request.get_json(force=True)
    product = next((p for p in PRODUCTS if p['id'] == d.get('product_id')), None)
    if not product:
        return err('商品不存在或已下架', http=404)
    qty = d.get('qty')
    if not isinstance(qty, (int, float)) or qty <= 0:
        return err('购买数量必须大于0')
    if qty > 1_000_000:
        return err('单笔订单数量超出合理范围')
    db = get_db()
    now = _now()
    cur = db.execute(
        "INSERT INTO mall_order(company_id,ore_type,product_name,spec,qty,unit_price,total_amount,"
        "dest_port,period_type,period,ore_category,grade_req,expected_arrival,delivery_place,"
        "contact_name,contact_phone,remark,status,create_time) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'SUBMITTED',?)",
        (g.current_user['company_id'], product['ore_type'], product['name'], product['spec'],
         round(qty, 2), product['price'], round(qty * product['price'], 2),
         (d.get('dest_port') or '').strip() or None,
         (d.get('period_type') or '').strip() or None, (d.get('period') or '').strip() or None,
         product['ore_category'], (d.get('grade_req') or '').strip() or None,
         (d.get('expected_arrival') or '').strip() or None, (d.get('dest_port') or '').strip() or None,
         (d.get('contact_name') or '').strip() or None, (d.get('contact_phone') or '').strip() or None,
         (d.get('remark') or '').strip() or None,
         now))
    order_id = cur.lastrowid
    db.execute("UPDATE mall_order SET order_no=? WHERE order_id=?",
               (f"MO{now.replace('-', '').replace(':', '').replace(' ', '')}{order_id:05d}", order_id))
    db.commit()
    log_action('商城下单', f"商品 {product['name']} 数量 {round(qty, 2)}吨 金额 {round(qty * product['price'], 2)}元",
               after='SUBMITTED', ref_type='mall_order', ref_id=order_id)
    return ok({'order_id': order_id, 'order_no': None}, message='下单成功，等待平台确认')


@bp.get('/mall/orders')
@roles_required('R1')
@company_approved_required
def mall_orders():
    """我的商城订单"""
    db = get_db()
    page = int(request.args.get('page', 1)); size = int(request.args.get('page_size', 10))
    sql = "SELECT * FROM mall_order WHERE company_id=?"
    args = [g.current_user['company_id']]
    if request.args.get('status'):
        sql += " AND status=?"; args.append(request.args['status'])
    sql += " ORDER BY create_time DESC"
    rows, total = paginate(db, sql, args, page, size)
    return ok({'list': rows, 'total': total, 'page': page, 'page_size': size})


@bp.post('/mall/order/<int:oid>/change')
@roles_required('R1')
@company_approved_required
def mall_order_change(oid):
    """商城预购订单变更申请（与采购需求变更同一审核流，demand_id 取负数区分）"""
    from ..utils import round2
    db = get_db()
    row = db.execute("SELECT * FROM mall_order WHERE order_id=? AND company_id=?",
                     (oid, g.current_user['company_id'])).fetchone()
    if not row:
        return err('订单不存在', http=404)
    if row['status'] not in ('SUBMITTED', 'CONFIRMED'):
        return err('当前状态不可变更')
    d = request.get_json(force=True)
    if d.get('change_type') not in ('QTY', 'SPEC', 'CANCEL'):
        return err('无效的变更类型')
    if not (d.get('change_desc') or '').strip():
        return err('变更说明必填')
    new_qty = d.get('new_quantity')
    if d['change_type'] == 'QTY':
        if new_qty is None or new_qty <= 0:
            return err('数量变更需提供有效的新数量')
    db.execute(
        "INSERT INTO demand_change(demand_id,company_id,change_type,change_desc,attachment_url,file_name,"
        "new_quantity,status,create_time,ref_no) VALUES(?,?,?,?,?,?,?,'PENDING',?,?)",
        (-oid, g.current_user['company_id'], d['change_type'], d['change_desc'].strip(), d.get('attachment_url'),
         d.get('file_name'), round2(new_qty) if new_qty else None, _now(), row['order_no']))
    db.commit()
    log_action('提交订单变更申请', f"订单 {row['order_no']} 变更类型 {d['change_type']}",
               before=row['status'], after='PENDING', ref_type='mall_order_change', ref_id=oid)
    return ok(message='变更申请已提交，待平台处理')
