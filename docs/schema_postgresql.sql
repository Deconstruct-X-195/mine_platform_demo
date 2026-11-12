-- =============================================================
-- 大宗矿产集采平台 一期 数据库 DDL（PostgreSQL 14）
-- 与 PRD 5.3 建模约定保持一致；库：mine_platform，编码 UTF8
-- =============================================================

-- 单据编号序列（前缀-YYYYMMDD-4位流水，按日重置，作废不复用）
CREATE TABLE sys_seq (
  biz_date DATE NOT NULL,
  prefix   VARCHAR(8) NOT NULL,
  cur      INT NOT NULL DEFAULT 0,
  PRIMARY KEY (biz_date, prefix)
);

-- 企业档案
CREATE TABLE ent_company (
  id            BIGSERIAL PRIMARY KEY,
  company_name  VARCHAR(100)  NOT NULL,
  credit_code   VARCHAR(18)   NOT NULL, -- 统一社会信用代码，唯一
  company_types VARCHAR(64)   NOT NULL, -- STEEL,SUPPLIER,LOGISTICS 逗号分隔
  province      VARCHAR(32),  city VARCHAR(32), address VARCHAR(200),
  legal_person  VARCHAR(30),
  contact_name  VARCHAR(30), contact_phone VARCHAR(20), contact_email VARCHAR(64),
  business_scope VARCHAR(500),
  bank_name     VARCHAR(100), bank_account VARCHAR(30),
  audit_status  VARCHAR(20)   NOT NULL DEFAULT 'PENDING', -- PENDING/APPROVED/REJECTED
  audit_remark  VARCHAR(500),
  status        VARCHAR(20)   NOT NULL DEFAULT 'ENABLED',
  created_at    TIMESTAMP NOT NULL DEFAULT now(), updated_at TIMESTAMP NOT NULL DEFAULT now(),
  created_by BIGINT, updated_by BIGINT, is_deleted SMALLINT DEFAULT 0,
  CONSTRAINT uk_credit_code UNIQUE (credit_code)
);
CREATE INDEX idx_audit ON ent_company (audit_status);

-- 平台用户（角色代码见 PRD 第 2 章；密码存 BCrypt）
CREATE TABLE sys_user (
  id BIGSERIAL PRIMARY KEY,
  company_id BIGINT, username VARCHAR(50) NOT NULL, -- 手机号
  password_hash VARCHAR(100) NOT NULL, real_name VARCHAR(30),
  roles VARCHAR(64) NOT NULL, status VARCHAR(20) NOT NULL DEFAULT 'ENABLED',
  created_at TIMESTAMP NOT NULL DEFAULT now(), updated_at TIMESTAMP NOT NULL DEFAULT now(),
  created_by BIGINT, updated_by BIGINT, is_deleted SMALLINT DEFAULT 0,
  CONSTRAINT uk_username UNIQUE (username)
);
CREATE INDEX idx_user_company ON sys_user (company_id);

-- 企业资质附件
CREATE TABLE ent_qualification (
  id BIGSERIAL PRIMARY KEY,
  company_id BIGINT NOT NULL, file_id VARCHAR(64) NOT NULL,
  file_name VARCHAR(200), file_type VARCHAR(20) DEFAULT 'BUSINESS_LICENSE',
  created_at TIMESTAMP NOT NULL DEFAULT now(), created_by BIGINT, is_deleted SMALLINT DEFAULT 0
);

-- 品种档案（category：品类，如 粉矿/块矿/精粉/球团/混矿）
CREATE TABLE base_variety (
  id BIGSERIAL PRIMARY KEY,
  variety_code VARCHAR(32) NOT NULL, variety_name VARCHAR(64) NOT NULL,
  category VARCHAR(50),
  default_grade NUMERIC(5,2), unit VARCHAR(16) DEFAULT '吨',
  sort_no INT DEFAULT 0, status VARCHAR(20) DEFAULT 'ENABLED',
  created_at TIMESTAMP NOT NULL DEFAULT now(), updated_at TIMESTAMP NOT NULL DEFAULT now(),
  created_by BIGINT, updated_by BIGINT, is_deleted SMALLINT DEFAULT 0,
  CONSTRAINT uk_code UNIQUE (variety_code)
);

-- 品种基准价（同品种同日唯一；保存修改前值到操作日志）
CREATE TABLE base_price (
  id BIGSERIAL PRIMARY KEY,
  variety_id BIGINT NOT NULL, price_date DATE NOT NULL,
  price NUMERIC(18,2) NOT NULL, price_basis VARCHAR(16) DEFAULT 'WET',
  port VARCHAR(32), grade VARCHAR(16),
  source_desc VARCHAR(200), remark VARCHAR(200),
  created_at TIMESTAMP NOT NULL DEFAULT now(), updated_at TIMESTAMP NOT NULL DEFAULT now(),
  created_by BIGINT, updated_by BIGINT, is_deleted SMALLINT DEFAULT 0,
  CONSTRAINT uk_variety_date_port_grade UNIQUE (variety_id, price_date, port, grade)
);

-- 港口现货价（品种×港口×日期唯一；运营看板"行业数据趋势"数据源，增量表）
CREATE TABLE IF NOT EXISTS base_port_price (
  id BIGSERIAL PRIMARY KEY,
  variety_id BIGINT NOT NULL, port_name VARCHAR(50) NOT NULL, price_date DATE NOT NULL,
  price NUMERIC(18,2) NOT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT now(), created_by BIGINT,
  is_deleted SMALLINT DEFAULT 0,
  CONSTRAINT uk_port_variety_date UNIQUE (variety_id, port_name, price_date)
);
CREATE INDEX IF NOT EXISTS idx_port_price_query ON base_port_price (variety_id, port_name, price_date);

-- 需求单
CREATE TABLE biz_demand (
  id BIGSERIAL PRIMARY KEY,
  demand_no VARCHAR(32) NOT NULL, company_id BIGINT NOT NULL,
  demand_name VARCHAR(50) NOT NULL,
  delivery_type VARCHAR(20) NOT NULL, -- PORT_FOB,PORT_TRUCK,PLANT
  delivery_place VARCHAR(100) NOT NULL,
  expect_arrive_start DATE NOT NULL, expect_arrive_end DATE NOT NULL,
  price_intent VARCHAR(500),
  settle_type VARCHAR(32) NOT NULL, settle_days INT, quality_req VARCHAR(500),
  attachments TEXT, remark VARCHAR(500), version INT DEFAULT 1,
  submitted_at TIMESTAMP,
  status VARCHAR(20) NOT NULL DEFAULT 'DRAFT', -- DRAFT/SUBMITTED/WITHDRAWN
  created_at TIMESTAMP NOT NULL DEFAULT now(), updated_at TIMESTAMP NOT NULL DEFAULT now(),
  created_by BIGINT, updated_by BIGINT, is_deleted SMALLINT DEFAULT 0,
  CONSTRAINT uk_demand_no UNIQUE (demand_no)
);
CREATE INDEX idx_company ON biz_demand (company_id);
CREATE INDEX idx_status ON biz_demand (status);

-- 需求明细（数量控制：已询量 inquired_qty ≤ quantity，成交回填 deal_qty）
CREATE TABLE biz_demand_item (
  id BIGSERIAL PRIMARY KEY,
  demand_id BIGINT NOT NULL, variety_id BIGINT NOT NULL,
  grade NUMERIC(5,2) NOT NULL, quantity NUMERIC(18,3) NOT NULL,
  more_less_rate NUMERIC(6,2) DEFAULT 5.00,
  inquired_qty NUMERIC(18,3) DEFAULT 0, deal_qty NUMERIC(18,3) DEFAULT 0,
  created_at TIMESTAMP NOT NULL DEFAULT now(), updated_at TIMESTAMP NOT NULL DEFAULT now(),
  created_by BIGINT, updated_by BIGINT, is_deleted SMALLINT DEFAULT 0
);
CREATE INDEX idx_demand ON biz_demand_item (demand_id);

-- 需求变更申请（运营端"需求归集-变更申请审核"数据源；PENDING/APPROVED/REJECTED）
CREATE TABLE biz_demand_change (
  id BIGSERIAL PRIMARY KEY,
  change_no VARCHAR(32) NOT NULL, demand_id BIGINT NOT NULL, company_id BIGINT NOT NULL,
  before_data TEXT, after_data TEXT, reason VARCHAR(500),
  status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
  audit_remark VARCHAR(500),
  audit_by BIGINT, audit_at TIMESTAMP,
  created_at TIMESTAMP NOT NULL DEFAULT now(), updated_at TIMESTAMP NOT NULL DEFAULT now(),
  created_by BIGINT, updated_by BIGINT, is_deleted SMALLINT DEFAULT 0,
  CONSTRAINT uk_change_no UNIQUE (change_no)
);
CREATE INDEX idx_change_demand ON biz_demand_change (demand_id);
CREATE INDEX idx_change_status ON biz_demand_change (status);

-- 归集订单（运营平台将多钢厂同品种同品位需求合并发起询价；状态流转见 backend/state_machine.py）
CREATE TABLE biz_aggregated_order (
  id BIGSERIAL PRIMARY KEY,
  agg_no VARCHAR(32) NOT NULL,
  variety_id BIGINT NOT NULL,
  grade NUMERIC(5,2),
  total_qty NUMERIC(18,3) NOT NULL,
  status VARCHAR(20) NOT NULL DEFAULT 'OPEN',
  remark VARCHAR(200),
  created_at TIMESTAMP NOT NULL DEFAULT now(), updated_at TIMESTAMP NOT NULL DEFAULT now(),
  created_by BIGINT, updated_by BIGINT, is_deleted SMALLINT DEFAULT 0,
  CONSTRAINT uk_agg_no UNIQUE (agg_no)
);

-- 归集订单成员明细（一行 = 归集订单 × 钢厂需求明细）
CREATE TABLE biz_aggregated_order_item (
  id BIGSERIAL PRIMARY KEY,
  agg_id BIGINT NOT NULL,
  demand_id BIGINT NOT NULL,
  demand_item_id BIGINT NOT NULL,
  company_id BIGINT NOT NULL,
  quantity NUMERIC(18,3) NOT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT now(),
  is_deleted SMALLINT DEFAULT 0
);
CREATE INDEX idx_agg_item_agg ON biz_aggregated_order_item (agg_id);
CREATE INDEX idx_agg_item_demand ON biz_aggregated_order_item (demand_id);

-- 归集询价反馈（成员钢厂对归集询价的认可/不认可表态；同询价同企业唯一）
CREATE TABLE biz_agg_inquiry_feedback (
  id BIGSERIAL PRIMARY KEY,
  inquiry_id BIGINT NOT NULL,
  agg_id BIGINT NOT NULL,
  company_id BIGINT NOT NULL,
  decision VARCHAR(10) NOT NULL, -- ACCEPT/REJECT
  reason VARCHAR(200),
  created_at TIMESTAMP NOT NULL DEFAULT now(),
  created_by BIGINT,
  is_deleted SMALLINT DEFAULT 0,
  CONSTRAINT uk_agg_feedback UNIQUE (inquiry_id, company_id)
);

-- 询价单
CREATE TABLE biz_inquiry (
  id BIGSERIAL PRIMARY KEY,
  inquiry_no VARCHAR(32) NOT NULL, demand_id BIGINT, demand_item_id BIGINT,
  buyer_id BIGINT, variety_id BIGINT NOT NULL, -- buyer_id 可空：运营平台归集代发询价无买方
  grade NUMERIC(5,2), quantity NUMERIC(18,3) NOT NULL,
  delivery_type VARCHAR(20), delivery_place VARCHAR(100),
  expect_arrive_date DATE, settle_type VARCHAR(32),
  deadline TIMESTAMP NOT NULL, sent_at TIMESTAMP, min_response INT DEFAULT 2,
  inquiry_desc VARCHAR(1000), status VARCHAR(20) NOT NULL DEFAULT 'DRAFT',
  source VARCHAR(16) NOT NULL DEFAULT 'STEEL', -- STEEL=钢厂自发 / PLATFORM=运营平台代发
  batch_no VARCHAR(32), -- 平台批量询价批次号（同批多单同号，可空）
  agg_id BIGINT, -- 归集订单 id（PLATFORM 代发询价关联 biz_aggregated_order）
  reveal_snapshot TEXT, -- 揭示时固化全部报价快照
  created_at TIMESTAMP NOT NULL DEFAULT now(), updated_at TIMESTAMP NOT NULL DEFAULT now(),
  created_by BIGINT, updated_by BIGINT, is_deleted SMALLINT DEFAULT 0,
  CONSTRAINT uk_inquiry_no UNIQUE (inquiry_no)
);
CREATE INDEX idx_buyer ON biz_inquiry (buyer_id);
CREATE INDEX idx_inquiry_status ON biz_inquiry (status);

-- 询价邀请
CREATE TABLE biz_inquiry_invite (
  id BIGSERIAL PRIMARY KEY,
  inquiry_id BIGINT NOT NULL, supplier_id BIGINT NOT NULL,
  status VARCHAR(20) NOT NULL DEFAULT 'INVITED',
  created_at TIMESTAMP NOT NULL DEFAULT now(), is_deleted SMALLINT DEFAULT 0,
  CONSTRAINT uk_inv UNIQUE (inquiry_id, supplier_id)
);

-- 报价响应（密封：截止前仅供应商本人可见；修改版本留痕）
CREATE TABLE biz_quote (
  id BIGSERIAL PRIMARY KEY,
  quote_no VARCHAR(32) NOT NULL, inquiry_id BIGINT NOT NULL,
  supplier_id BIGINT NOT NULL, price NUMERIC(18,2) NOT NULL,
  tax_type VARCHAR(10), -- 含税标识：INC_TAX/EX_TAX（新报价应用层必填，存量行可空）
  freight_price NUMERIC(18,2), -- 运费单价（元/吨）
  delivery_type VARCHAR(20), -- 交付方式：PORT_FOB/PORT_TRUCK/PLANT
  quantity NUMERIC(18,3) NOT NULL, delivery_date DATE NOT NULL,
  delivery_place VARCHAR(100), pay_terms VARCHAR(200), quality_commit VARCHAR(300),
  valid_until DATE, remark VARCHAR(300), version INT DEFAULT 1,
  status VARCHAR(20) NOT NULL DEFAULT 'SUBMITTED', -- SUBMITTED/REJECTED/LOSE/WIN
  created_at TIMESTAMP NOT NULL DEFAULT now(), updated_at TIMESTAMP NOT NULL DEFAULT now(),
  created_by BIGINT, updated_by BIGINT, is_deleted SMALLINT DEFAULT 0,
  CONSTRAINT uk_quote_no UNIQUE (quote_no)
);
CREATE INDEX idx_quote_inquiry ON biz_quote (inquiry_id);
CREATE INDEX idx_quote_supplier ON biz_quote (supplier_id);

-- 议价轮次（轮次序号自 1 递增，上限 10）
CREATE TABLE biz_bargain (
  id BIGSERIAL PRIMARY KEY,
  quote_id BIGINT NOT NULL, inquiry_id BIGINT NOT NULL,
  round_no INT NOT NULL DEFAULT 1, initiator VARCHAR(20) NOT NULL, -- BUYER/SUPPLIER
  price NUMERIC(18,2), quantity NUMERIC(18,3),
  delivery_date DATE, settle_type VARCHAR(32), extra_terms VARCHAR(500),
  status VARCHAR(20) NOT NULL DEFAULT 'PENDING', -- PENDING/ACCEPTED/REJECTED/EXPIRED
  created_at TIMESTAMP NOT NULL DEFAULT now(), updated_at TIMESTAMP NOT NULL DEFAULT now(),
  created_by BIGINT, is_deleted SMALLINT DEFAULT 0
);
CREATE INDEX idx_bargain_quote ON biz_bargain (quote_id);

-- 订单
CREATE TABLE biz_order (
  id BIGSERIAL PRIMARY KEY,
  order_no VARCHAR(32) NOT NULL, inquiry_id BIGINT, quote_id BIGINT, demand_id BIGINT,
  buyer_id BIGINT NOT NULL, supplier_id BIGINT NOT NULL,
  variety_id BIGINT NOT NULL, grade NUMERIC(5,2),
  quantity NUMERIC(18,3) NOT NULL, more_less_rate NUMERIC(6,2) DEFAULT 5.00,
  unit_price NUMERIC(18,2) NOT NULL, amount NUMERIC(18,2) NOT NULL,
  price_basis VARCHAR(16) DEFAULT 'WET',
  delivery_type VARCHAR(20), delivery_place VARCHAR(100), delivery_date DATE,
  settle_type VARCHAR(32), quality_terms VARCHAR(500),
  confirm_deadline TIMESTAMP, -- 供应商确认截止，默认定标后 48 小时
  status VARCHAR(20) NOT NULL DEFAULT 'PENDING_CONFIRM',
  created_at TIMESTAMP NOT NULL DEFAULT now(), updated_at TIMESTAMP NOT NULL DEFAULT now(),
  created_by BIGINT, updated_by BIGINT, is_deleted SMALLINT DEFAULT 0,
  CONSTRAINT uk_order_no UNIQUE (order_no)
);
CREATE INDEX idx_order_buyer ON biz_order (buyer_id);
CREATE INDEX idx_order_supplier ON biz_order (supplier_id);
CREATE INDEX idx_order_status ON biz_order (status);

-- 合同
CREATE TABLE biz_contract (
  id BIGSERIAL PRIMARY KEY,
  contract_no VARCHAR(32) NOT NULL, order_id BIGINT NOT NULL, version INT DEFAULT 1,
  signature_type VARCHAR(20) DEFAULT 'PLATFORM_CONFIRM',
  file_url VARCHAR(500), file_hash VARCHAR(64), -- 生成文件 SHA-256
  buyer_sign_at TIMESTAMP, buyer_sign_user BIGINT, buyer_sign_ip VARCHAR(64),
  supplier_sign_at TIMESTAMP, supplier_sign_user BIGINT, supplier_sign_ip VARCHAR(64),
  void_reason VARCHAR(500),
  status VARCHAR(20) NOT NULL DEFAULT 'PENDING_GENERATE',
  plat_status VARCHAR(20), -- 平台核验：NULL=无扫描件 / PENDING=待运营确认 / CONFIRMED=已核验入台账 / RETURNED=已退回
  plat_remark VARCHAR(500), -- 平台核验意见（退回原因）
  plat_confirm_by BIGINT, plat_confirm_at TIMESTAMP, -- 运营核验人/时间
  created_at TIMESTAMP NOT NULL DEFAULT now(), updated_at TIMESTAMP NOT NULL DEFAULT now(),
  created_by BIGINT, updated_by BIGINT, is_deleted SMALLINT DEFAULT 0,
  CONSTRAINT uk_contract_no UNIQUE (contract_no)
);
CREATE INDEX idx_contract_order ON biz_contract (order_id);

-- 物流方案
CREATE TABLE biz_logistics_plan (
  id BIGSERIAL PRIMARY KEY,
  plan_no VARCHAR(32) NOT NULL, order_id BIGINT NOT NULL,
  org_mode VARCHAR(20) NOT NULL, -- SELF / PLATFORM
  remark VARCHAR(500),
  status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',
  created_at TIMESTAMP NOT NULL DEFAULT now(), updated_at TIMESTAMP NOT NULL DEFAULT now(),
  created_by BIGINT, updated_by BIGINT, is_deleted SMALLINT DEFAULT 0,
  CONSTRAINT uk_plan_no UNIQUE (plan_no)
);

-- 运单
CREATE TABLE biz_waybill (
  id BIGSERIAL PRIMARY KEY,
  waybill_no VARCHAR(32) NOT NULL, order_id BIGINT NOT NULL, plan_id BIGINT NOT NULL,
  segment_no VARCHAR(32) NOT NULL, carrier_id BIGINT,
  transport_mode VARCHAR(20) NOT NULL, depart_place VARCHAR(100), arrive_place VARCHAR(100),
  plan_depart_date DATE, plan_arrive_date DATE, plan_qty NUMERIC(18,3) NOT NULL,
  freight NUMERIC(18,2), vehicle_no VARCHAR(50),
  actual_qty NUMERIC(18,3), actual_depart_at TIMESTAMP, actual_arrive_at TIMESTAMP,
  status VARCHAR(20) NOT NULL DEFAULT 'PENDING_ASSIGN',
  created_at TIMESTAMP NOT NULL DEFAULT now(), updated_at TIMESTAMP NOT NULL DEFAULT now(),
  created_by BIGINT, updated_by BIGINT, is_deleted SMALLINT DEFAULT 0,
  CONSTRAINT uk_waybill_no UNIQUE (waybill_no)
);
CREATE INDEX idx_waybill_order ON biz_waybill (order_id);
CREATE INDEX idx_waybill_carrier ON biz_waybill (carrier_id);

-- 履约节点（只增不改，纠偏记录 correct_node_id 指向原节点）
CREATE TABLE biz_track_node (
  id BIGSERIAL PRIMARY KEY,
  biz_type VARCHAR(20) NOT NULL, -- ORDER,WAYBILL,SETTLEMENT
  biz_id BIGINT NOT NULL, node_code VARCHAR(32) NOT NULL, node_name VARCHAR(64) NOT NULL,
  occur_time TIMESTAMP NOT NULL, source VARCHAR(16) NOT NULL, -- SYSTEM,CARRIER,MANUAL
  remark VARCHAR(500), correct_node_id BIGINT, -- 纠正记录指向的原节点
  created_at TIMESTAMP NOT NULL DEFAULT now(), created_by BIGINT
);
CREATE INDEX idx_track_biz ON biz_track_node (biz_type, biz_id);
CREATE INDEX idx_track_time ON biz_track_node (occur_time);

-- 质检记录
CREATE TABLE biz_quality_check (
  id BIGSERIAL PRIMARY KEY,
  check_no VARCHAR(32) NOT NULL, order_id BIGINT NOT NULL,
  arrived_qty NUMERIC(18,3) NOT NULL, indicators TEXT,
  conclusion VARCHAR(20) NOT NULL, -- ACCEPT/REJECT
  check_desc VARCHAR(500), file_url VARCHAR(500),
  created_at TIMESTAMP NOT NULL DEFAULT now(), created_by BIGINT, is_deleted SMALLINT DEFAULT 0,
  CONSTRAINT uk_check_no UNIQUE (check_no)
);

-- 结算单（金额 =（单价+质量调价）×结算数量 − 扣款，服务端计算）
CREATE TABLE biz_settlement (
  id BIGSERIAL PRIMARY KEY,
  settle_no VARCHAR(32) NOT NULL, order_id BIGINT NOT NULL,
  settle_qty NUMERIC(18,3) NOT NULL, unit_price NUMERIC(18,2) NOT NULL,
  adjust_amount NUMERIC(18,2) DEFAULT 0, -- 质量调价，元/吨
  deduct_amount NUMERIC(18,2) DEFAULT 0, -- 运费及其他扣款
  total_amount NUMERIC(18,2) NOT NULL, settle_desc VARCHAR(500),
  supplier_confirm_at TIMESTAMP, buyer_confirm_at TIMESTAMP,
  status VARCHAR(32) NOT NULL DEFAULT 'PENDING_CONFIRM_SUPPLIER',
  created_at TIMESTAMP NOT NULL DEFAULT now(), updated_at TIMESTAMP NOT NULL DEFAULT now(),
  created_by BIGINT, updated_by BIGINT, is_deleted SMALLINT DEFAULT 0,
  CONSTRAINT uk_settle_no UNIQUE (settle_no)
);
CREATE INDEX idx_settle_order ON biz_settlement (order_id);

-- 付款登记
CREATE TABLE biz_payment (
  id BIGSERIAL PRIMARY KEY,
  payment_no VARCHAR(32) NOT NULL, settlement_id BIGINT NOT NULL,
  payer_id BIGINT NOT NULL, amount NUMERIC(18,2) NOT NULL,
  pay_date DATE NOT NULL, pay_desc VARCHAR(500), file_url VARCHAR(500),
  created_at TIMESTAMP NOT NULL DEFAULT now(), created_by BIGINT, is_deleted SMALLINT DEFAULT 0,
  CONSTRAINT uk_payment_no UNIQUE (payment_no)
);

-- 预警记录（五类；同对象同类型未关闭去重）
CREATE TABLE biz_alert (
  id BIGSERIAL PRIMARY KEY,
  alert_no VARCHAR(32) NOT NULL, alert_type VARCHAR(32) NOT NULL,
  biz_type VARCHAR(20) NOT NULL, biz_id BIGINT NOT NULL,
  company_ids VARCHAR(200), -- 需通知的企业，逗号分隔
  content VARCHAR(500), handler_remark VARCHAR(500), handler_id BIGINT, handled_at TIMESTAMP,
  status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
  created_at TIMESTAMP NOT NULL DEFAULT now(), updated_at TIMESTAMP NOT NULL DEFAULT now(),
  is_deleted SMALLINT DEFAULT 0,
  CONSTRAINT uk_alert_no UNIQUE (alert_no)
);
-- 同对象同类型仅保留一条未关闭预警（PENDING/PROCESSING 均视为未关闭）
CREATE UNIQUE INDEX uk_alert_dedup ON biz_alert (alert_type, biz_type, biz_id)
  WHERE status IN ('PENDING', 'PROCESSING') AND is_deleted = 0;
CREATE INDEX idx_alert_status ON biz_alert (status);

-- 远期预报报价（预判价，非成交价；锁定期内可修改）
CREATE TABLE biz_forecast_quote (
  id BIGSERIAL PRIMARY KEY,
  forecast_no VARCHAR(32) NOT NULL, supplier_id BIGINT NOT NULL,
  variety_id BIGINT NOT NULL, period_type VARCHAR(16) NOT NULL, -- TEN_DAY/MONTHLY
  period_start DATE NOT NULL, period_end DATE NOT NULL,
  available_qty NUMERIC(18,3) NOT NULL, forecast_price NUMERIC(18,2) NOT NULL,
  price_basis VARCHAR(16) DEFAULT 'WET', delivery_port VARCHAR(100),
  valid_until DATE, remark VARCHAR(500),
  status VARCHAR(20) NOT NULL DEFAULT 'EFFECTIVE',
  created_at TIMESTAMP NOT NULL DEFAULT now(), updated_at TIMESTAMP NOT NULL DEFAULT now(),
  created_by BIGINT, updated_by BIGINT, is_deleted SMALLINT DEFAULT 0,
  CONSTRAINT uk_forecast_no UNIQUE (forecast_no)
);

-- 操作日志（所有写操作强制留痕）
CREATE TABLE sys_operation_log (
  id BIGSERIAL PRIMARY KEY,
  user_id BIGINT, company_id BIGINT, biz_type VARCHAR(20), biz_id BIGINT,
  action VARCHAR(64), before_value TEXT, after_value TEXT,
  ip VARCHAR(64), created_at TIMESTAMP NOT NULL DEFAULT now()
);
CREATE INDEX idx_log_user ON sys_operation_log (user_id);
CREATE INDEX idx_log_biz ON sys_operation_log (biz_type, biz_id);
CREATE INDEX idx_log_time ON sys_operation_log (created_at);

-- 站内消息（一期简化项：只写消息表 + 页面提示）
CREATE TABLE sys_message (
  id BIGSERIAL PRIMARY KEY,
  receiver_company_id BIGINT, -- 可空：平台公告/系统级消息无接收企业
  title VARCHAR(100) NOT NULL,
  content VARCHAR(500), biz_type VARCHAR(20), biz_id BIGINT,
  is_read SMALLINT DEFAULT 0,
  created_at TIMESTAMP NOT NULL DEFAULT now()
);

-- 文件附件（PRD 6.1：POST /files 返回 fileId，业务对象只存 fileId；TODO(PRD待确认) 表未在 5.2 清单，按最小实现补充）
CREATE TABLE sys_file (
  id BIGSERIAL PRIMARY KEY,
  file_id VARCHAR(64) NOT NULL, file_name VARCHAR(200) NOT NULL,
  content_type VARCHAR(100), size_bytes BIGINT NOT NULL DEFAULT 0,
  path VARCHAR(500) NOT NULL, company_id BIGINT,
  created_at TIMESTAMP NOT NULL DEFAULT now(), created_by BIGINT, is_deleted SMALLINT DEFAULT 0,
  CONSTRAINT uk_file_id UNIQUE (file_id)
);
