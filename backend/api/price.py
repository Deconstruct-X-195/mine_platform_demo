# -*- coding: utf-8 -*-
"""价格数据模块 (PRD-06)：行情维护/批量导入/成交均价统计/价格看板趋势/下游只读脱敏"""
import io
import re
from flask import Blueprint, request, g
from ..db import get_db, _now
from ..utils import ok, err, log_action, paginate, round2, export_excel
from ..auth import roles_required, company_approved_required

bp = Blueprint('price', __name__)

DATE_RE = re.compile(r'^\d{4}-\d{2}-\d{2}$')


def _num(v):
    """转换为正数（元/吨），非法返回 None"""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if f <= 0:
        return None
    return round2(f)


def _validate(d):
    """行情录入校验，返回 (packed, error)"""
    category = (d.get('ore_category') or '').strip()
    spec = (d.get('spec') or '').strip()
    date = (d.get('quote_date') or '').strip()
    if not category:
        return None, '矿石品类必填'
    if not spec:
        return None, '指标规格必填'
    if len(spec) > 100:
        return None, '指标规格不可超过100字'
    if not DATE_RE.match(date):
        return None, '日期格式应为 YYYY-MM-DD'
    market = _num(d.get('market_price'))
    if market is None:
        return None, '市场参考价必须为大于0的数字'
    deal = None
    if d.get('avg_deal_price') not in (None, ''):
        deal = _num(d.get('avg_deal_price'))
        if deal is None:
            return None, '平台成交均价必须为大于0的数字'
    source = (d.get('source') or '').strip() or None
    remark = (d.get('remark') or '').strip()
    if remark and len(remark) > 200:
        return None, '备注不可超过200字'
    return (category, spec, date, market, deal, source, remark), None


# ================= 管理员 (R4) =================

@bp.post('/admin/price/create')
@roles_required('R4')
def price_create():
    packed, error = _validate(request.get_json(force=True))
    if error:
        return err(error)
    category, spec, date, market, deal, source, remark = packed
    db = get_db()
    cur = db.execute(
        "INSERT INTO ore_price_quote(ore_category,spec,quote_date,market_price,avg_deal_price,"
        "source,remark,operator_id,create_time) VALUES(?,?,?,?,?,?,?,?,?)",
        (category, spec, date, market, deal, source, remark, g.current_user['user_id'], _now()))
    db.commit()
    log_action('录入矿石行情', f"{category} {date} 市场价{market}元/吨", ref_type='ore_price_quote', ref_id=cur.lastrowid)
    return ok({'id': cur.lastrowid})


@bp.put('/admin/price/<int:pid>')
@roles_required('R4')
def price_update(pid):
    db = get_db()
    row = db.execute("SELECT * FROM ore_price_quote WHERE id=?", (pid,)).fetchone()
    if not row:
        return err('行情记录不存在', http=404)
    packed, error = _validate(request.get_json(force=True))
    if error:
        return err(error)
    category, spec, date, market, deal, source, remark = packed
    db.execute(
        "UPDATE ore_price_quote SET ore_category=?,spec=?,quote_date=?,market_price=?,"
        "avg_deal_price=?,source=?,remark=?,operator_id=? WHERE id=?",
        (category, spec, date, market, deal, source, remark, g.current_user['user_id'], pid))
    db.commit()
    log_action('修改矿石行情', f"#{pid} {category} {date}", ref_type='ore_price_quote', ref_id=pid)
    return ok({'id': pid})


@bp.delete('/admin/price/<int:pid>')
@roles_required('R4')
def price_delete(pid):
    db = get_db()
    row = db.execute("SELECT * FROM ore_price_quote WHERE id=?", (pid,)).fetchone()
    if not row:
        return err('行情记录不存在', http=404)
    db.execute("DELETE FROM ore_price_quote WHERE id=?", (pid,))
    db.commit()
    log_action('删除矿石行情', f"#{pid} {row['ore_category']} {row['quote_date']}",
               ref_type='ore_price_quote', ref_id=pid)
    return ok({'id': pid})


@bp.get('/admin/price/list')
@roles_required('R4')
def price_list():
    db = get_db()
    page = int(request.args.get('page', 1)); size = int(request.args.get('page_size', 10))
    sql = "SELECT * FROM ore_price_quote WHERE 1=1"
    args = []
    if request.args.get('ore_category'):
        sql += " AND ore_category=?"; args.append(request.args['ore_category'])
    if request.args.get('date_from'):
        sql += " AND quote_date>=?"; args.append(request.args['date_from'])
    if request.args.get('date_to'):
        sql += " AND quote_date<=?"; args.append(request.args['date_to'])
    sql += " ORDER BY quote_date DESC, id DESC"
    rows, total = paginate(db, sql, args, page, size)
    return ok({'list': rows, 'total': total, 'page': page, 'page_size': size})


@bp.get('/admin/price/template')
@roles_required('R4')
def price_template():
    """下载批量导入 Excel 模板（含示例行）"""
    return export_excel(
        ['矿石品类', '指标规格', '日期', '市场参考价(元/吨)', '平台成交均价(元/吨)', '数据来源', '备注'],
        [('行情导入模板', [['IRON', 'TFe 62%', '2026-01-15', 720.5, '', 'Mysteel', '']])],
        '行情批量导入模板.xlsx')


@bp.post('/admin/price/import')
@roles_required('R4')
def price_import():
    """批量导入行情 Excel：逐行校验，合法行入库，返回行级错误报告"""
    f = request.files.get('file')
    if not f:
        return err('请上传 Excel 文件')
    try:
        from openpyxl import load_workbook
        wb = load_workbook(io.BytesIO(f.read()), data_only=True)
    except Exception:
        return err('文件解析失败，请使用系统提供的导入模板')
    ws = wb.active
    if ws is None:
        return err('文件内容为空')
    rows = list(ws.iter_rows(min_row=2, values_only=True))
    if not rows:
        return err('模板中没有数据行')
    db = get_db()
    now = _now()
    inserted, errors = 0, []
    for idx, r in enumerate(rows, start=2):
        cells = [(c.strip() if isinstance(c, str) else c) for c in (list(r) + [None] * 7)[:7]]
        packed, error = _validate({
            'ore_category': cells[0], 'spec': cells[1], 'quote_date': cells[2],
            'market_price': cells[3], 'avg_deal_price': cells[4] or None,
            'source': cells[5], 'remark': cells[6]})
        if error:
            errors.append({'row': idx, 'message': error})
            continue
        category, spec, date, market, deal, source, remark = packed
        db.execute(
            "INSERT INTO ore_price_quote(ore_category,spec,quote_date,market_price,avg_deal_price,"
            "source,remark,operator_id,create_time) VALUES(?,?,?,?,?,?,?,?,?)",
            (category, spec, date, market, deal, source, remark, g.current_user['user_id'], now))
        inserted += 1
    db.commit()
    log_action('批量导入行情', f"成功{inserted}行，失败{len(errors)}行", ref_type='ore_price_quote')
    return ok({'inserted': inserted, 'failed': len(errors), 'errors': errors[:50]})


def _deal_avg_stats(db, category=None):
    """按品类+月份统计已锁货集采订单成交均价（真实成交数据）"""
    sql = ("SELECT substr(create_time,1,7) AS month, ore_category, COUNT(*) AS order_count,"
           " SUM(total_qty) AS total_qty, ROUND(AVG(unit_price),2) AS avg_unit_price"
           " FROM collective_order WHERE 1=1")
    args = []
    if category:
        sql += " AND ore_category=?"; args.append(category)
    sql += " GROUP BY substr(create_time,1,7), ore_category ORDER BY month DESC"
    return [dict(x) for x in db.execute(sql, args)]


@bp.get('/admin/price/trend')
@roles_required('R4')
def admin_trend():
    """价格看板：行情趋势（市场参考价 vs 平台成交均价）+ 成交均价月度统计"""
    db = get_db()
    sql = "SELECT * FROM ore_price_quote WHERE 1=1"
    args = []
    category = request.args.get('ore_category')
    if category:
        sql += " AND ore_category=?"; args.append(category)
    if request.args.get('date_from'):
        sql += " AND quote_date>=?"; args.append(request.args['date_from'])
    if request.args.get('date_to'):
        sql += " AND quote_date<=?"; args.append(request.args['date_to'])
    sql += " ORDER BY quote_date ASC, id ASC"
    rows = [dict(x) for x in db.execute(sql, args)]
    return ok({
        'trend': rows,
        'deal_stats': _deal_avg_stats(db, category)
    })


# ================= 下游企业 (R1) 只读脱敏 =================

@bp.get('/company/price/trend')
@roles_required('R1')
@company_approved_required
def company_trend():
    """下游行情浏览：仅公开市场参考价，不返回平台成交均价等内部数据"""
    db = get_db()
    sql = ("SELECT id, ore_category, spec, quote_date, market_price, source"
           " FROM ore_price_quote WHERE 1=1")
    args = []
    if request.args.get('ore_category'):
        sql += " AND ore_category=?"; args.append(request.args['ore_category'])
    if request.args.get('date_from'):
        sql += " AND quote_date>=?"; args.append(request.args['date_from'])
    if request.args.get('date_to'):
        sql += " AND quote_date<=?"; args.append(request.args['date_to'])
    sql += " ORDER BY quote_date DESC, id DESC"
    rows, total = paginate(db, sql, args,
                           int(request.args.get('page', 1)), int(request.args.get('page_size', 20)))
    return ok({'list': rows, 'total': total,
               'page': int(request.args.get('page', 1)), 'page_size': int(request.args.get('page_size', 20))})
