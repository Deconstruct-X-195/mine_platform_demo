# -*- coding: utf-8 -*-
"""数据库层：SQLite 连接管理与全量表结构（按 PRD-01 数据架构统一定义）"""
import os
import sqlite3
from datetime import datetime, timedelta
from flask import g

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, 'data')
DB_PATH = os.path.join(DATA_DIR, 'app.db')
UPLOAD_DIR = os.path.join(BASE_DIR, 'uploads')

SCHEMA = """
-- ============ 全局基座 (PRD-01/08) ============
CREATE TABLE IF NOT EXISTS company (
  company_id INTEGER PRIMARY KEY AUTOINCREMENT,
  company_name TEXT NOT NULL UNIQUE,
  credit_code TEXT UNIQUE,
  company_type TEXT NOT NULL,             -- DOWNSTREAM / SUPPLIER / PARTNER
  partner_type TEXT,                      -- PARTNER: SEA / PORT / WAREHOUSE / LAND
  supplier_type TEXT,                     -- SUPPLIER: DOMESTIC / OVERSEAS
  contact TEXT,
  phone TEXT,
  audit_status TEXT NOT NULL DEFAULT 'PENDING',  -- PENDING / APPROVED / REJECTED
  audit_remark TEXT,
  auditor_id INTEGER,
  audit_time TEXT,
  create_time TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sys_user (
  user_id INTEGER PRIMARY KEY AUTOINCREMENT,
  company_id INTEGER,
  role_code TEXT NOT NULL,                -- R1 / R2 / R3 / R4
  username TEXT NOT NULL UNIQUE,
  password_hash TEXT NOT NULL,
  salt TEXT NOT NULL,
  real_name TEXT,
  status TEXT NOT NULL DEFAULT 'ACTIVE',  -- ACTIVE / DISABLED
  create_time TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sys_session (
  token TEXT PRIMARY KEY,
  user_id INTEGER NOT NULL,
  create_time TEXT NOT NULL,
  expire_time TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS qualification (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  company_id INTEGER NOT NULL,
  cert_type TEXT NOT NULL,                -- BUSINESS_LICENSE / MINING_LICENSE / OTHER
  file_url TEXT NOT NULL,
  file_name TEXT,
  status TEXT NOT NULL DEFAULT 'PENDING', -- PENDING / APPROVED / REJECTED
  auditor_id INTEGER,
  audit_time TEXT,
  reject_reason TEXT,
  create_time TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS dict_item (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  category TEXT NOT NULL,                 -- ORE_CATEGORY / PERIOD_TYPE / PORT / PARTNER_TYPE / SUPPLIER_TYPE
  item_code TEXT NOT NULL,
  item_name TEXT NOT NULL,
  sort INTEGER DEFAULT 0,
  status INTEGER DEFAULT 1,
  UNIQUE(category, item_code)
);
CREATE TABLE IF NOT EXISTS ore_indicator_template (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ore_category TEXT NOT NULL,
  field_name TEXT NOT NULL,
  field_label TEXT NOT NULL,
  field_type TEXT DEFAULT 'text',         -- text / number
  required INTEGER DEFAULT 0,
  sort INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS sys_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  operator_id INTEGER,
  operator_name TEXT,
  role_code TEXT,
  action TEXT NOT NULL,
  detail TEXT,
  before_status TEXT,
  after_status TEXT,
  ref_type TEXT,
  ref_id TEXT,
  create_time TEXT NOT NULL
);

-- ============ 需求申报 (PRD-02) ============
CREATE TABLE IF NOT EXISTS purchase_demand (
  demand_id INTEGER PRIMARY KEY AUTOINCREMENT,
  demand_no TEXT UNIQUE,
  company_id INTEGER NOT NULL,
  period_type TEXT NOT NULL,              -- MONTH / QUARTER
  period TEXT NOT NULL,                   -- YYYY-MM 或 YYYY-Qn
  ore_category TEXT NOT NULL,
  quantity REAL NOT NULL,
  grade_req TEXT,
  granularity_req TEXT,
  moisture_req TEXT,
  impurity_req TEXT,
  expected_arrival TEXT,
  delivery_place TEXT,
  remark TEXT,
  status TEXT NOT NULL DEFAULT 'DRAFT',   -- DRAFT/SUBMITTED/IN_PROCESS/IN_LIST/IN_EXEC/DISTRIBUTED
  create_time TEXT NOT NULL,
  update_time TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS demand_attachment (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  demand_id INTEGER NOT NULL,
  file_url TEXT NOT NULL,
  file_name TEXT
);
CREATE TABLE IF NOT EXISTS demand_change (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  demand_id INTEGER NOT NULL,
  company_id INTEGER NOT NULL,
  change_type TEXT NOT NULL,              -- QTY / SPEC / CANCEL
  change_desc TEXT NOT NULL,
  new_quantity REAL,
  attachment_url TEXT,
  file_name TEXT,
  status TEXT NOT NULL DEFAULT 'PENDING', -- PENDING / AGREED / REJECTED
  review_remark TEXT,
  create_time TEXT NOT NULL,
  review_time TEXT
);
CREATE TABLE IF NOT EXISTS collective_list (
  list_id INTEGER PRIMARY KEY AUTOINCREMENT,
  list_no TEXT UNIQUE,
  period_type TEXT NOT NULL,
  period TEXT NOT NULL,
  total_qty REAL NOT NULL DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'ACTIVE',  -- ACTIVE(待询价) / INQUIRED(已建询价任务)
  creator_id INTEGER,
  create_time TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS collective_list_detail (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  list_id INTEGER NOT NULL,
  demand_id INTEGER NOT NULL,
  company_id INTEGER NOT NULL,
  ore_category TEXT NOT NULL,
  qty REAL NOT NULL,
  grade_req TEXT,
  expected_arrival TEXT
);

-- ============ 货源资源 (PRD-03) ============
CREATE TABLE IF NOT EXISTS ore_resource (
  resource_id INTEGER PRIMARY KEY AUTOINCREMENT,
  supplier_id INTEGER NOT NULL,
  ore_category TEXT NOT NULL,
  origin TEXT NOT NULL,
  grade TEXT NOT NULL,
  granularity TEXT,
  moisture TEXT,
  impurity TEXT,
  max_qty REAL NOT NULL,
  supply_period TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'DRAFT',   -- DRAFT / ON_SHELF / OFF_SHELF / FORCE_OFF
  is_preferred INTEGER NOT NULL DEFAULT 0,
  down_reason TEXT,
  create_time TEXT NOT NULL,
  update_time TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS resource_attachment (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  resource_id INTEGER NOT NULL,
  file_url TEXT NOT NULL,
  file_name TEXT
);

-- ============ 集采交易 (PRD-04) ============
CREATE TABLE IF NOT EXISTS collective_task (
  task_id INTEGER PRIMARY KEY AUTOINCREMENT,
  task_no TEXT UNIQUE,
  list_id INTEGER NOT NULL,
  ore_category TEXT NOT NULL,
  total_qty REAL NOT NULL,
  indicator_req TEXT,
  supply_time TEXT,
  quote_deadline TEXT,
  status TEXT NOT NULL DEFAULT 'WAIT_QUOTE',  -- WAIT_QUOTE/QUOTING/LOCKED/IN_LOGISTICS/LOGI_DONE/ARCHIVED
  creator_id INTEGER,
  create_time TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS inquiry_task (
  inquiry_id INTEGER PRIMARY KEY AUTOINCREMENT,
  task_id INTEGER NOT NULL,
  supplier_id INTEGER NOT NULL,
  resource_id INTEGER,
  status TEXT NOT NULL DEFAULT 'WAIT_QUOTE',  -- WAIT_QUOTE/QUOTED/NOT_SELECTED/LOCKED/REFUSED
  quote_price REAL,
  quote_qty REAL,
  supply_period TEXT,
  indicator_commit TEXT,
  remark TEXT,
  refuse_reason TEXT,
  create_time TEXT NOT NULL,
  update_time TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS quote_history (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  inquiry_id INTEGER NOT NULL,
  quote_price REAL NOT NULL,
  quote_qty REAL NOT NULL,
  create_time TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS collective_order (
  order_id INTEGER PRIMARY KEY AUTOINCREMENT,
  order_no TEXT UNIQUE,
  task_id INTEGER NOT NULL,
  supplier_id INTEGER NOT NULL,
  ore_category TEXT NOT NULL,
  total_qty REAL NOT NULL,
  unit_price REAL NOT NULL,
  total_amount REAL NOT NULL,
  supply_time TEXT,
  status TEXT NOT NULL DEFAULT 'LOCKED',  -- LOCKED(已锁货)/IN_LOGISTICS(待物流履约)/LOGI_DONE(履约完成)/ARCHIVED(已归档)
  create_time TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS collective_order_detail (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  order_id INTEGER NOT NULL,
  demand_id INTEGER NOT NULL,
  company_id INTEGER NOT NULL,
  ore_category TEXT NOT NULL,
  qty REAL NOT NULL,
  grade_req TEXT,
  expected_arrival TEXT
);

-- ============ 物流跟踪 (PRD-05) ============
CREATE TABLE IF NOT EXISTS logistics_task (
  logi_id INTEGER PRIMARY KEY AUTOINCREMENT,
  logi_no TEXT UNIQUE,
  order_id INTEGER NOT NULL,
  sea_partner_id INTEGER,
  port_partner_id INTEGER,
  warehouse_partner_id INTEGER,
  land_partner_id INTEGER,
  from_place TEXT,
  dest_port TEXT,
  plan_arrival TEXT,
  warehouse TEXT,
  dest_place TEXT,
  current_node INTEGER NOT NULL DEFAULT 0,  -- 已完成到的最大节点 0~7
  create_time TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS logistics_node (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  logi_id INTEGER NOT NULL,
  node_code INTEGER NOT NULL,             -- 1~7 (N1~N7)
  node_name TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'PENDING', -- PENDING / DONE
  actual_time TEXT,
  operator_id INTEGER,
  done_time TEXT
);
CREATE TABLE IF NOT EXISTS logistics_attachment (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  node_id INTEGER NOT NULL,
  doc_type TEXT,
  file_url TEXT NOT NULL,
  file_name TEXT,
  uploader_id INTEGER,
  upload_time TEXT NOT NULL
);

-- ============ 价格数据 (PRD-06) ============
CREATE TABLE IF NOT EXISTS ore_price_quote (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ore_category TEXT NOT NULL,
  spec TEXT NOT NULL,
  quote_date TEXT NOT NULL,
  market_price REAL NOT NULL,
  avg_deal_price REAL,
  source TEXT,
  remark TEXT,
  operator_id INTEGER,
  create_time TEXT NOT NULL
);

-- ============ 对账结算 (PRD-07) ============
CREATE TABLE IF NOT EXISTS allocation_order (
  alloc_id INTEGER PRIMARY KEY AUTOINCREMENT,
  alloc_no TEXT UNIQUE,
  order_id INTEGER NOT NULL,
  company_id INTEGER NOT NULL,
  ore_category TEXT NOT NULL,
  qty REAL NOT NULL,
  unit_price REAL NOT NULL,
  amount REAL NOT NULL,
  destination TEXT,
  status TEXT NOT NULL DEFAULT 'WAIT',    -- WAIT(待分拨)/TRANSIT(配送在途)/WAIT_CONFIRM(待企业确认到货)/DONE(已完成)
  create_time TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS company_bill (
  bill_id INTEGER PRIMARY KEY AUTOINCREMENT,
  bill_no TEXT UNIQUE,
  company_id INTEGER NOT NULL,
  period TEXT,
  total_amount REAL NOT NULL DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'PENDING', -- PENDING/CONFIRMED/DISPUTE/SETTLED
  confirm_time TEXT,
  settle_remark TEXT,
  settle_time TEXT,
  create_time TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS company_bill_detail (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  bill_id INTEGER NOT NULL,
  alloc_id INTEGER NOT NULL,
  ore_category TEXT NOT NULL,
  qty REAL NOT NULL,
  unit_price REAL NOT NULL,
  amount REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS supplier_bill (
  bill_id INTEGER PRIMARY KEY AUTOINCREMENT,
  bill_no TEXT UNIQUE,
  order_id INTEGER NOT NULL,
  supplier_id INTEGER NOT NULL,
  period TEXT,
  total_amount REAL NOT NULL DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'PENDING',
  confirm_time TEXT,
  dispute_reason TEXT,
  settle_remark TEXT,
  settle_time TEXT,
  create_time TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS arrival_feedback (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  alloc_id INTEGER NOT NULL,
  company_id INTEGER NOT NULL,
  feedback_type TEXT,
  description TEXT NOT NULL,
  attachment_url TEXT,
  file_name TEXT,
  status TEXT NOT NULL DEFAULT 'PENDING', -- PENDING / RESOLVED
  resolve_remark TEXT,
  create_time TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS archive_record (
  archive_id INTEGER PRIMARY KEY AUTOINCREMENT,
  order_id INTEGER NOT NULL,
  task_id INTEGER,
  period TEXT,
  archive_time TEXT NOT NULL,
  operator_id INTEGER,
  archive_summary TEXT
);
"""


def get_db():
    """获取请求级数据库连接"""
    if 'db' not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute('PRAGMA foreign_keys = ON')
    return g.db


def close_db(_=None):
    db = g.pop('db', None)
    if db is not None:
        db.close()


def init_db(app):
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    _migrate(conn)
    _seed(conn)
    conn.commit()
    conn.close()


def _migrate(conn):
    """轻量列迁移：已有库缺新列时自动补齐"""
    need_cols = {
        'demand_change': [('new_quantity', 'REAL')],
        'company_bill': [('dispute_reason', 'TEXT'), ('settle_remark', 'TEXT'), ('settle_time', 'TEXT')],
        'supplier_bill': [('period', 'TEXT'), ('dispute_reason', 'TEXT'), ('settle_remark', 'TEXT'), ('settle_time', 'TEXT')],
        'archive_record': [('task_id', 'INTEGER'), ('archive_summary', 'TEXT')],
    }
    for table, cols in need_cols.items():
        existing = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
        for name, decl in cols:
            if name not in existing:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {decl}")


def _now():
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def _seed(conn):
    """初始化种子数据：平台管理员 + 基础字典 + 指标模板"""
    cur = conn.execute("SELECT COUNT(*) c FROM sys_user WHERE role_code='R4'")
    if cur.fetchone()['c'] == 0:
        import hashlib, secrets
        salt = secrets.token_hex(8)
        pwd = hashlib.sha256((salt + 'admin123').encode()).hexdigest()
        conn.execute(
            "INSERT INTO sys_user(role_code, username, password_hash, salt, real_name, status, create_time)"
            " VALUES('R4','admin',?,?,?, 'ACTIVE', ?)", (pwd, salt, '平台管理员', _now()))
    seeds = [
        # 矿石品类字典
        ('ORE_CATEGORY', 'IRON', '铁矿石', 1), ('ORE_CATEGORY', 'CHROME', '铬矿', 2),
        ('ORE_CATEGORY', 'MANGANESE', '锰矿', 3), ('ORE_CATEGORY', 'LIMESTONE', '石灰石', 4),
        # 申报周期
        ('PERIOD_TYPE', 'MONTH', '月度', 1), ('PERIOD_TYPE', 'QUARTER', '季度', 2),
        # 港口信息
        ('PORT', 'QINGDAO', '青岛港', 1), ('PORT', 'RIAZHAO', '日照港', 2),
        ('PORT', 'TANGSHAN', '唐山港', 3), ('PORT', 'SHANGHAI', '上海港', 4),
        # 供方类型 / 配套方类型
        ('SUPPLIER_TYPE', 'DOMESTIC', '国内供应商', 1), ('SUPPLIER_TYPE', 'OVERSEAS', '海外矿山', 2),
        ('PARTNER_TYPE', 'SEA', '海运承运方', 1), ('PARTNER_TYPE', 'PORT', '港口接卸方', 2),
        ('PARTNER_TYPE', 'WAREHOUSE', '仓储方', 3), ('PARTNER_TYPE', 'LAND', '陆运配送方', 4),
    ]
    for cat, code, name, sort in seeds:
        conn.execute("INSERT OR IGNORE INTO dict_item(category,item_code,item_name,sort) VALUES(?,?,?,?)",
                     (cat, code, name, sort))
    # 指标模板（按品类自动带出）
    templates = [
        ('IRON', 'grade', '品位TFe(%)', 'number', 1, 1), ('IRON', 'moisture', '水分(%)', 'number', 0, 2),
        ('IRON', 'impurity', '杂质(硫/磷)', 'text', 0, 3), ('IRON', 'granularity', '粒度(mm)', 'text', 0, 4),
        ('CHROME', 'grade', '品位Cr2O3(%)', 'number', 1, 1), ('CHROME', 'moisture', '水分(%)', 'number', 0, 2),
        ('CHROME', 'impurity', '杂质指标', 'text', 0, 3),
        ('MANGANESE', 'grade', '品位Mn(%)', 'number', 1, 1), ('MANGANESE', 'moisture', '水分(%)', 'number', 0, 2),
        ('LIMESTONE', 'grade', '品位CaO(%)', 'number', 1, 1), ('LIMESTONE', 'granularity', '粒度(mm)', 'text', 0, 2),
    ]
    for cat, fname, flabel, ftype, req, sort in templates:
        exists = conn.execute("SELECT 1 FROM ore_indicator_template WHERE ore_category=? AND field_name=?",
                              (cat, fname)).fetchone()
        if not exists:
            conn.execute(
                "INSERT INTO ore_indicator_template(ore_category,field_name,field_label,field_type,required,sort)"
                " VALUES(?,?,?,?,?,?)", (cat, fname, flabel, ftype, req, sort))
