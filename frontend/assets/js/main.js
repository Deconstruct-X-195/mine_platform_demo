/* ============ 菜单注册与启动 ============ */
App.addMenu([
  { key: 'home', title: '工作台', icon: '⌂', group: '总览' },
  { key: 'msg.center', title: '消息中心', icon: '🔔', group: '总览' },

  /* R1 下游需求企业 */
  { key: 'r1.demand', title: '采购需求管理', icon: '📋', group: '需求申报', roles: ['R1'] },

  /* R2 上游供给方 */
  { key: 'r2.resource', title: '货源管理', icon: '⛏', group: '货源资源', roles: ['R2'] },
  { key: 'r2.inquiry', title: '集采询价任务', icon: '📨', group: '集采交易', roles: ['R2'] },

  /* R3 履约配套方 */
  { key: 'r3.logistics', title: '我的物流任务', icon: '🚚', group: '物流履约', roles: ['R3'] },

  /* R4 平台管理员 */
  { key: 'r4.dashboard', title: '全局看板', icon: '📊', group: '平台运营', roles: ['R4'] },
  { key: 'r4.demand', title: '需求归集', icon: '📥', group: '集采中枢', roles: ['R4'] },
  { key: 'r4.list', title: '集采清单', icon: '📑', group: '集采中枢', roles: ['R4'] },
  { key: 'r4.trade', title: '集采交易', icon: '⚖', group: '集采中枢', roles: ['R4'] },
  { key: 'r4.logistics', title: '物流看板', icon: '🗺', group: '集采中枢', roles: ['R4'] },
  { key: 'r4.alloc', title: '分拨管理', icon: '📦', group: '集采中枢', roles: ['R4'] },
  { key: 'r4.settle', title: '对账结算', icon: '🧾', group: '集采中枢', roles: ['R4'] },
  { key: 'r4.price', title: '行情维护', icon: '💹', group: '价格数据', roles: ['R4'] },
  { key: 'r4.priceBoard', title: '价格看板', icon: '📈', group: '价格数据', roles: ['R4'] },
  { key: 'r4.indicator', title: '指标模板', icon: '🧪', group: '基础数据', roles: ['R4'] },
  { key: 'r4.dict', title: '字典维护', icon: '📖', group: '基础数据', roles: ['R4'] },
  { key: 'r4.ledgerSearch', title: '单据检索', icon: '🔍', group: '审计与检索', roles: ['R4'] },
  { key: 'r4.log', title: '操作日志', icon: '🕰', group: '审计与检索', roles: ['R4'] },
  { key: 'r4.supplierLedger', title: '上游资源台账', icon: '🗄', group: '资源管理', roles: ['R4'] },
  { key: 'r1.market', title: '行情浏览', icon: '🌐', group: '价格数据', roles: ['R1'] },
  { key: 'r1.alloc', title: '我的分拨单', icon: '📦', group: '履约结算', roles: ['R1'] },
  { key: 'r1.logistics', title: '物流进度', icon: '🚚', group: '履约结算', roles: ['R1'] },
  { key: 'r1.bill', title: '我的对账单', icon: '🧾', group: '履约结算', roles: ['R1'] },
  { key: 'r2.bill', title: '对账记录', icon: '🧾', group: '履约结算', roles: ['R2'] },
  { key: 'r4.company', title: '企业资质审核', icon: '🏢', group: '平台后台', roles: ['R4'] },
  { key: 'r4.account', title: '账号管理', icon: '👤', group: '平台后台', roles: ['R4'] },
  { key: 'r4.warnrule', title: '预警规则', icon: '⏰', group: '平台后台', roles: ['R4'] },

  /* PRD-09 质检化验 */
  { key: 'r4.inspect', title: '质检化验管理', icon: '🔬', group: '质检化验', roles: ['R4'] },
  { key: 'r3.inspect', title: '化验录入', icon: '🧫', group: '质检化验', roles: ['R3'] },
  { key: 'r2.inspect', title: '货源预检', icon: '🧪', group: '质检化验', roles: ['R2'] },
  { key: 'r1.inspect', title: '质检记录', icon: '🔬', group: '履约结算', roles: ['R1'] },

  /* PRD-10 合同管理 */
  { key: 'r4.contract', title: '合同台账', icon: '📜', group: '合同管理', roles: ['R4'] },
  { key: 'r1.contract', title: '我的合同', icon: '📜', group: '履约结算', roles: ['R1'] },
  { key: 'r2.contract', title: '我的合同', icon: '📜', group: '货源资源', roles: ['R2'] },

  /* PRD-11 费用分摊 */
  { key: 'r4.expense', title: '费用分摊', icon: '💰', group: '集采中枢', roles: ['R4'] },
  { key: 'r1.expense', title: '费用明细', icon: '💰', group: '履约结算', roles: ['R1'] },

  /* PRD-13/15 报表与变更 */
  { key: 'r4.report', title: '报表中心', icon: '📈', group: '报表与大屏', roles: ['R4'] },
  { key: 'r4.bigscreen', title: '运营大屏', icon: '🖥', group: '报表与大屏', roles: ['R4'] },
  { key: 'r1.report', title: '我的报表', icon: '📈', group: '履约结算', roles: ['R1'] },
  { key: 'r2.report', title: '我的报表', icon: '📈', group: '货源资源', roles: ['R2'] },
  { key: 'biz.apply', title: '变更红冲申请', icon: '✏', group: '履约结算', roles: ['R1', 'R2'] },
  { key: 'r4.bizchange', title: '变更红冲审核', icon: '✅', group: '审计与检索', roles: ['R4'] }
]);

App.boot();
