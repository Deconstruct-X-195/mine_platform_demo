/* 运营后台（PRD 4.10/FR-10）：仪表盘/企业审核/基础数据/单据总览/预警/字典/日志 */
(function () {
  window.Pages = window.Pages || {};

  /* -------- 运营仪表盘 -------- */
  Pages.dashboard = async function (page) {
    const d = await API.get('/admin/dashboard');
    const cards = [
      ['注册企业', d.companyTotal, '家'],
      ['待审核企业', d.companyPending, '家'],
      ['履约中订单', d.orderActive, '单'],
      ['订单总数', d.orderTotal, '单'],
      ['未关闭预警', d.alertPending, '条'],
      ['询价进行中', d.inquiryQuoting, '单'],
    ];
    page.appendChild(UI.h('div', { class: 'stat-grid' },
      cards.map(([label, val, unit]) => UI.h('div', { class: 'card stat-card' },
        UI.h('div', { class: 'stat-label' }, label),
        UI.h('div', { class: 'stat-value' }, String(val || 0), UI.h('span', { class: 'stat-unit' }, unit))))));
    page.appendChild(UI.h('div', { class: 'card' },
      UI.h('h3', {}, '快捷入口'),
      UI.h('div', { style: 'display:flex;gap:10px;flex-wrap:wrap' },
        UI.h('button', { class: 'sm', onclick: () => { location.hash = '#/admin-companies'; } }, '企业审核'),
        UI.h('button', { class: 'sm', onclick: () => { location.hash = '#/base-data'; } }, '基础数据'),
        UI.h('button', { class: 'sm', onclick: () => { location.hash = '#/alerts'; } }, '预警处理'),
        UI.h('button', { class: 'sm', onclick: () => { location.hash = '#/doc-overview'; } }, '单据总览'),
        UI.h('button', { class: 'sm', onclick: () => { location.hash = '#/logs'; } }, '操作日志'))));
  };

  /* -------- 企业审核台 -------- */
  Pages.admin_companies = async function (page) {
    let pageNo = 1;
    const SIZE = 10;
    let auditStatus = '';
    const listCard = UI.h('div', { class: 'card' });
    const pagerBox = UI.h('div', {});
    page.appendChild(UI.h('div', { class: 'card' },
      UI.h('div', { class: 'toolbar' },
        UI.h('h3', { style: 'margin:0;border:none;padding:0' }, '企业审核'),
        UI.h('div', { class: 'spacer' }),
        UI.statusFilter('AUDIT', (v) => { auditStatus = v; pageNo = 1; load(); }))));
    page.appendChild(listCard);
    page.appendChild(pagerBox);
    await load();

    async function load() {
      const d = await API.get('/admin/companies' + API.qs({ auditStatus, page: pageNo, size: SIZE }));
      listCard.innerHTML = '';
      listCard.appendChild(UI.table([
        { key: 'companyName', label: '企业名称' },
        { key: 'creditCode', label: '统一社会信用代码' },
        { key: 'companyTypes', label: '角色' },
        { key: 'contactName', label: '联系人' },
        { key: 'contactPhone', label: '联系电话' },
        { key: 'auditStatus', label: '审核状态', render: (r) => UI.statusTag('AUDIT', r.auditStatus) },
        { key: 'status', label: '账号', render: (r) => r.status === 'ENABLED' ? UI.h('span', { class: 'tag green' }, '启用') : UI.h('span', { class: 'tag red' }, '停用') },
        { label: '操作', render: (r) => acts(r) },
      ], d.list, '暂无企业'));
      pagerBox.innerHTML = '';
      UI.pager(pagerBox, pageNo, SIZE, d.total, (p) => { pageNo = p; load(); });
    }

    function acts(r) {
      const btns = [UI.h('button', { class: 'sm', onclick: () => detail(r.id) }, '详情')];
      if (r.auditStatus === 'PENDING') {
        btns.push(UI.h('button', { class: 'sm success', onclick: () => auditModal(r) }, '审核'));
      }
      if (r.auditStatus === 'APPROVED') {
        btns.push(r.status === 'ENABLED'
          ? UI.h('button', { class: 'sm danger', onclick: () => toggle(r, 'DISABLED') }, '停用')
          : UI.h('button', { class: 'sm success', onclick: () => toggle(r, 'ENABLED') }, '启用'));
      }
      return UI.h('span', { class: 'inline-flex' }, ...btns);
    }

    function auditModal(r) {
      const approve = UI.selectField([['true', '通过'], ['false', '驳回']], 'true');
      const remark = UI.h('textarea', { rows: 2, style: 'width:100%', placeholder: '审核意见（驳回必填）' });
      const m = UI.modal('企业审核 · ' + r.companyName, UI.h('form', { onsubmit: (e) => e.preventDefault() },
        UI.h('div', { class: 'form-grid' },
          UI.formRow('审核结论', approve, true),
          UI.h('div', { class: 'form-row full' }, UI.h('label', {}, '审核意见'), remark))), [
        UI.h('button', { class: 'primary', onclick: async () => {
          if (approve.value === 'false' && !remark.value.trim()) { UI.toast('驳回必须填写原因', 'err'); return; }
          try {
            await API.put('/admin/companies/' + r.id + '/audit',
              { approve: approve.value, remark: remark.value.trim() });
            m.close(); UI.toast('审核完成', 'ok'); load();
          } catch (e) { /* toast 已提示 */ }
        } }, '提 交'),
      ]);
    }

    async function toggle(r, status) {
      if (!(await UI.confirmBox((status === 'ENABLED' ? '启用' : '停用') + '企业「' + r.companyName + '」？'))) return;
      await API.put('/admin/companies/' + r.id + '/status', { status });
      UI.toast('操作成功', 'ok'); load();
    }

    async function detail(cid) {
      const c = await API.get('/companies/' + cid);
      UI.modal('企业详情', UI.kv([
        ['企业名称', c.companyName || c.company_name],
        ['统一社会信用代码', c.creditCode || c.credit_code],
        ['企业角色', c.companyTypes || c.company_types],
        ['审核状态', UI.statusTag('AUDIT', c.auditStatus || c.audit_status)],
        ['账号状态', c.status],
        ['联系人', c.contactName || c.contact_name],
        ['联系电话', c.contactPhone || c.contact_phone],
        ['注册地址', c.address || c.registered_address || '-', true],
        ['经营范围', c.businessScope || c.business_scope || '-', true],
      ]));
    }
  };

  /* -------- 基础数据：品种 + 基准价 -------- */
  Pages.base_data = async function (page) {
    page.appendChild(UI.h('div', { class: 'card' },
      UI.h('div', { class: 'toolbar' },
        UI.h('h3', { style: 'margin:0;border:none;padding:0' }, '品种管理'),
        UI.h('div', { class: 'spacer' }),
        UI.h('button', { class: 'primary', onclick: varietyForm }, '新增品种'))));
    const varCard = UI.h('div', { class: 'card' });
    const priceCard = UI.h('div', { class: 'card' });
    page.appendChild(varCard);
    page.appendChild(priceCard);
    await load();

    async function load() {
      const vars = (await API.get('/base/varieties')).list || [];
      varCard.innerHTML = '';
      varCard.appendChild(UI.h('h3', {}, '品种列表'));
      varCard.appendChild(UI.table([
        { key: 'varietyCode', label: '品种代码' },
        { key: 'varietyName', label: '品种名称' },
        { key: 'defaultGrade', label: '默认品位(%)' },
        { key: 'unit', label: '计量单位' },
        { key: 'status', label: '状态' },
      ], vars, '暂无品种'));

      const prices = await API.get('/base-prices/current');
      priceCard.innerHTML = '';
      priceCard.appendChild(UI.h('h3', {}, '今日基准价'));
      priceCard.appendChild(UI.table([
        { key: 'varietyName', label: '品种' },
        { key: 'price', label: '基准价（元/吨）', num: true, render: (r) => UI.fmtMoney(r.price) },
        { key: 'priceBasis', label: '计价基准', render: (r) => ({ WET: '湿基', DRY: '干基' }[r.priceBasis] || r.priceBasis) },
        { key: 'priceDate', label: '报价日期', render: (r) => UI.fmtDate(r.priceDate) },
        { key: 'sourceDesc', label: '数据来源' },
        { label: '操作', render: (r) => UI.h('button', { class: 'sm', onclick: () => priceForm(r.varietyId, r.varietyName) }, '重新录入') },
      ], prices.today || [], '今日暂无基准价'));
      priceCard.appendChild(UI.h('div', { style: 'margin-top:10px' },
        UI.h('button', { class: 'primary', onclick: () => priceForm('', '') }, '录入基准价')));
    }

    function varietyForm() {
      const code = UI.input('text', '', { placeholder: '如 PB、FMG' });
      const name = UI.input('text', '', { placeholder: '如 PB 粉、高品位铁矿' });
      const grade = UI.input('text', '', { placeholder: '如 61.5（品位百分数，纯数字）' });
      const unit = UI.input('text', '吨', { placeholder: '计量单位，默认 吨' });
      const m = UI.modal('新增品种', UI.h('form', { onsubmit: (e) => e.preventDefault() },
        UI.h('div', { class: 'form-grid' },
          UI.formRow('品种代码', code, true),
          UI.formRow('品种名称', name, true),
          UI.formRow('默认品位(%)', grade),
          UI.formRow('计量单位', unit))), [
        UI.h('button', { class: 'primary', onclick: async () => {
          if (!code.value.trim() || !name.value.trim()) { UI.toast('请填写品种代码与名称', 'err'); return; }
          const g = grade.value.trim();
          if (g !== '' && (isNaN(Number(g)) || Number(g) < 0 || Number(g) > 999.99)) {
            UI.toast('默认品位必须为 0～999.99 的数字（如 61.5）', 'err'); return;
          }
          try {
            await API.post('/admin/varieties', { varietyCode: code.value.trim(), varietyName: name.value.trim(), defaultGrade: g || null, unit: unit.value.trim() });
            m.close(); UI.toast('品种已新增', 'ok'); load();
          } catch (e) { /* toast 已提示 */ }
        } }, '保 存'),
      ]);
    }

    function priceForm(varietyId, varietyName) {
      API.get('/base/varieties').then((vd) => {
        const vars = vd.list || [];
        const sel = UI.selectField(vars.map((v) => [v.id, v.varietyName]), varietyId || (vars[0] && vars[0].id));
        const pdate = UI.input('date', new Date().toISOString().slice(0, 10), { placeholder: '报价日期' });
        const price = UI.input('number', '', { placeholder: '基准价（元/吨）' });
        const basis = UI.selectField([['WET', '湿基'], ['DRY', '干基']], 'WET');
        const src = UI.input('text', '', { placeholder: '数据来源说明（如 Mysteel 旬报）' });
        const m = UI.modal('基准价录入' + (varietyName ? ' · ' + varietyName : ''),
          UI.h('form', { onsubmit: (e) => e.preventDefault() },
            UI.h('div', { class: 'form-grid' },
              UI.formRow('品种', sel, true),
              UI.formRow('报价日期', pdate, true),
              UI.formRow('基准价', price, true),
              UI.formRow('计价基准', basis),
              UI.formRow('数据来源', src))), [
          UI.h('button', { class: 'primary', onclick: async () => {
            if (!price.value) { UI.toast('请填写基准价', 'err'); return; }
            try {
              await API.post('/admin/base-prices', { varietyId: sel.value, priceDate: pdate.value, price: price.value, priceBasis: basis.value, sourceDesc: src.value.trim() });
              m.close(); UI.toast('基准价已录入', 'ok'); load();
            } catch (e) { /* toast 已提示 */ }
          } }, '保 存'),
        ]);
      });
    }
  };

  /* -------- 单据总览 -------- */
  Pages.doc_overview = async function (page) {
    const d = await API.get('/admin/doc-overview');
    const cards = UI.h('div', { class: 'stat-grid' }, Object.entries(d).map(([t, info]) =>
      UI.h('div', { class: 'card stat-card' },
        UI.h('div', { class: 'stat-label' }, info.label),
        UI.h('div', { class: 'stat-value' }, String(info.total)),
        UI.h('div', { class: 'hint', style: 'margin-top:6px' },
          Object.entries(info.byStatus || {}).map(([s, c]) => s + ':' + c).join('　') || '无数据'))));
    page.appendChild(cards);
  };

  /* -------- 预警处理 -------- */
  Pages.alerts = async function (page) {
    let pageNo = 1;
    const SIZE = 10;
    let status = '';
    const listCard = UI.h('div', { class: 'card' });
    const pagerBox = UI.h('div', {});
    page.appendChild(UI.h('div', { class: 'card' },
      UI.h('div', { class: 'toolbar' },
        UI.h('h3', { style: 'margin:0;border:none;padding:0' }, '预警处理'),
        UI.h('div', { class: 'spacer' }),
        UI.statusFilter('ALERT', (v) => { status = v; pageNo = 1; load(); }))));
    page.appendChild(listCard);
    page.appendChild(pagerBox);
    await load();

    async function load() {
      const d = await API.get('/alerts' + API.qs({ status, page: pageNo, size: SIZE }));
      listCard.innerHTML = '';
      listCard.appendChild(UI.table([
        { key: 'alertNo', label: '预警编号' },
        { key: 'alertType', label: '类型', render: (r) => UI.h('span', { class: 'tag orange' }, r.alertType) },
        { key: 'content', label: '预警内容', full: true },
        { key: 'bizType', label: '业务对象' },
        { key: 'status', label: '状态', render: (r) => UI.statusTag('ALERT', r.status) },
        { key: 'createdAt', label: '时间', render: (r) => UI.fmtDateTime(r.createdAt) },
        { label: '操作', render: (r) => r.status === 'PENDING' || r.status === 'PROCESSING'
          ? UI.h('button', { class: 'sm', onclick: () => handleModal(r) }, '处理') : '-' },
      ], d.list, '暂无预警'));
      pagerBox.innerHTML = '';
      UI.pager(pagerBox, pageNo, SIZE, d.total, (p) => { pageNo = p; load(); });
    }

    function handleModal(r) {
      const action = UI.selectField([['PROCESSING', '登记处理中'], ['CLOSE', '关闭预警']], 'PROCESSING');
      const remark = UI.h('textarea', { rows: 2, style: 'width:100%', placeholder: '处理意见（关闭必填）' });
      const m = UI.modal('预警处理 · ' + r.alertNo, UI.h('form', { onsubmit: (e) => e.preventDefault() },
        UI.h('div', { class: 'form-grid' },
          UI.formRow('处理动作', action, true),
          UI.h('div', { class: 'form-row full' }, UI.h('label', {}, '处理意见'), remark),
          UI.h('div', { class: 'form-row full' }, UI.h('div', { class: 'hint' }, r.content)))), [
        UI.h('button', { class: 'primary', onclick: async () => {
          if (action.value === 'CLOSE' && !remark.value.trim()) { UI.toast('关闭预警必须填写处理意见', 'err'); return; }
          try {
            await API.put('/alerts/' + r.id + '/handle', { action: action.value, handlerRemark: remark.value.trim() });
            m.close(); UI.toast('预警已处理', 'ok'); load();
          } catch (e) { /* toast 已提示 */ }
        } }, '提 交'),
      ]);
    }
  };

  /* -------- 数据字典 -------- */
  Pages.dict = async function (page) {
    const d = await API.get('/admin/dicts');
    /* 字典说明元数据：仅用于页面展示，不参与任何业务逻辑。
       label=中文业务名；kind=UI.STATUS 标签种类；intro=业务流程简介；
       desc=逐状态业务含义；notes=特殊取值/业务关联规则提示 */
    const META = {
      biz_demand: {
        label: '需求单', kind: 'DEMAND',
        intro: '钢厂发布采购需求，提交后可发起询价，达成交易后转入订单履约。',
        desc: {
          DRAFT: '需求单尚未提交，仅本企业可见，可继续编辑完善',
          SUBMITTED: '需求已正式提交平台，可据此发起询价',
          INQUIRING: '需求已发起询价，正在等待供应商报价',
          DEALT: '需求已达成交易，后续转入订单履约',
          CLOSED: '需求终止，不再参与询价与交易',
          WITHDRAWN: '提交人主动撤回，可修改后重新提交',
        },
        notes: ['已撤回的需求单重新提交时将生成新版本，历史版本留痕可查'],
      },
      biz_inquiry: {
        label: '询价单', kind: 'INQUIRY',
        intro: '面向受邀供应商发出的采购询价，经报价、议价后定标成交。',
        desc: {
          DRAFT: '询价单尚未发出，仅创建方可见',
          SENT: '询价已发送给受邀供应商，等待其在截止时间前报价',
          QUOTING: '已有供应商提交报价，截止前持续接收',
          CLOSED: '报价截止，进入比价、议价与定标环节',
          BARGAINING: '正与供应商就价格与条款磋商',
          AWARDED: '已确定中标供应商，随后生成订单',
          FAILED: '本次询价未达成交易而终止',
        },
        notes: ['订单超时失效后，已定标的询价单会重新开放定标（回到"已截止"），可再次议价定标'],
      },
      biz_quote: {
        label: '报价单', kind: 'QUOTE',
        intro: '供应商针对询价提交的密封报价，揭示前对其他参与方保密。',
        desc: {
          SUBMITTED: '供应商已提交密封报价，揭示前对其他参与方保密',
          REVEALED: '报价到期揭示，采供双方可见报价内容',
          BARGAINING: '该报价已进入议价磋商',
          WIN: '该报价被采纳，供应商赢得交易',
          LOSE: '该报价未被采纳',
          REJECTED: '报价被拒收，不进入后续环节',
        },
        notes: ['订单超时失效后，中标报价会回退重新参与定标；再次未中则标记为"未中标"'],
      },
      biz_bargain: {
        label: '议价轮次', kind: 'BARGAIN',
        intro: '比价后与供应商发起的一对一议价，按轮次记录双方响应结果。',
        desc: {
          PENDING: '议价条件已发出，等待对方响应',
          ONGOING: '与"待响应"含义相同的兼容取值（历史数据）',
          ACCEPTED: '对方接受议价条件，可继续推进定标',
          REJECTED: '对方拒绝该议价条件',
          EXPIRED: '议价超时未响应，自动失效',
        },
      },
      biz_order: {
        label: '订单', kind: 'ORDER',
        intro: '定标成交后生成的采购订单，经确认、签署合同后进入履约。',
        desc: {
          PENDING_CONFIRM: '订单已生成，等待供应商确认接单，超时未确认将自动失效',
          PENDING_CONTRACT: '供应商已确认，等待生成合同并完成签署',
          PENDING_EFFECT: '双方已签署，等待合同生效',
          PERFORMING: '合同已生效，进入发货、运输、签收与结算环节',
          COMPLETED: '履约与结算全部完成，订单归档',
          CANCELLED: '订单被取消或超时未确认而失效',
        },
        notes: ['合同作废后，订单会退回"待签合同"，重新走合同生成与签署流程'],
      },
      biz_contract: {
        label: '合同', kind: 'CONTRACT',
        intro: '订单确认后由系统生成合同文本，双方依次签署后生效。',
        desc: {
          PENDING_GENERATE: '订单确认后等待生成合同文本',
          PENDING_BUYER: '合同已生成，等待需方（钢厂）签署',
          PENDING_SUPPLIER: '需方已签署，等待供应商签署',
          EFFECTIVE: '双方签署完成，合同正式生效，可据此履约',
          VOID: '合同已作废，需重新生成并签署',
        },
        notes: ['合同须先由需方签署、再由供方签署；已生效的合同不可作废'],
      },
      biz_waybill: {
        label: '运单', kind: 'WAYBILL',
        intro: '合同生效后按物流方案生成的运输单据，跟踪货物从发运到签收。',
        desc: {
          PENDING_ASSIGN: '运单已生成，等待指派承运商',
          PENDING_ACCEPT: '已指派承运商，等待其确认接单',
          PENDING_DEPART: '承运商已接单，等待车辆发运',
          IN_TRANSIT: '货物已发运，正在运输途中',
          ARRIVED: '货物已到达收货地，等待质检与签收',
          SIGNED: '收货方完成签收，运输环节结束',
          CANCELLED: '运单被取消（如发运前取消），不再流转',
        },
      },
      biz_settlement: {
        label: '结算单', kind: 'SETTLEMENT',
        intro: '到货质检后按实收数量生成的结算单据，供需双方先后确认。',
        desc: {
          PENDING_CONFIRM_SUPPLIER: '结算单已生成，等待供应商核对确认',
          PENDING_CONFIRM_BUYER: '供应商已确认，等待需方（钢厂）确认',
          CONFIRMED: '双方确认完成，可登记付款',
          COMPLETED: '付款完成，结算闭环',
        },
        notes: ['结算金额由系统按"单价×实收数量−扣罚"计算，实收与订单数量的偏差计入结算'],
      },
      biz_alert: {
        label: '预警', kind: 'ALERT',
        intro: '业务过程中自动触发的风险提示，由平台统一跟进处理。',
        desc: {
          PENDING: '预警已触发，等待平台处理',
          PROCESSING: '平台已登记受理，正在跟进处理',
          CLOSED: '预警处理完毕，流程结束',
        },
        notes: ['关闭预警必须填写处理意见，处理过程留痕可查'],
      },
      ent_company: {
        label: '企业准入', kind: 'AUDIT',
        intro: '企业注册资料的准入审核状态（对应字段 audit_status）。',
        desc: {
          PENDING: '注册资料已提交，等待平台准入审核',
          APPROVED: '审核通过，企业可正常使用业务功能',
          REJECTED: '审核未通过，可补充资料后重新提交',
        },
        notes: [
          '企业关键信息变更后会重新进入"待审核"',
          '此处仅为企业准入审核状态；企业账号另有独立的"启用/禁用"开关，二者互不影响',
        ],
      },
    };

    const wrap = UI.h('div', { class: 'card' }, UI.h('h3', {}, '状态机字典（FR-10-05）'),
      UI.h('div', { class: 'hint', style: 'margin-bottom:16px;line-height:1.9' },
        UI.h('div', {}, '用途：集中说明平台各业务单据的状态含义与允许的流转路径，帮助运营人员快速对照单据当前所处环节。'),
        UI.h('div', {}, '数据来源：内容由系统状态机直接输出，与各业务单据实际执行的流转校验完全一致，随系统版本自动更新。'),
        UI.h('div', {}, '更新规则：状态定义与流转规则随业务流程版本统一调整；每次状态变化均写入操作日志，历史留痕可追溯。')));

    // 展示顺序：按业务流程排列（需求→询价→报价→议价→订单→合同→运单→结算→预警→准入），未识别的实体追加在末尾
    const ORDER = ['biz_demand', 'biz_inquiry', 'biz_quote', 'biz_bargain', 'biz_order',
      'biz_contract', 'biz_waybill', 'biz_settlement', 'biz_alert', 'ent_company'];
    const bizKeys = Object.keys(d.transitions || {});
    bizKeys.sort((a, b) => {
      const ia = ORDER.indexOf(a), ib = ORDER.indexOf(b);
      return (ia === -1 ? 999 : ia) - (ib === -1 ? 999 : ib);
    });
    let first = true;
    bizKeys.forEach((biz) => {
      const trs = d.transitions[biz];
      const meta = META[biz] || {};
      const kind = meta.kind || '';
      // 分节标题：中文业务名 + 灰色编码（便于与操作日志中的 bizType 对照）；非首节加分隔线
      wrap.appendChild(UI.h('h4', {
        style: first ? 'margin:14px 0 6px' : 'margin:22px 0 6px;padding-top:18px;border-top:1px solid var(--separator)',
      }, meta.label || biz, UI.h('span', { class: 'hint', style: 'margin-left:8px;font-weight:400' }, biz)));
      first = false;
      if (meta.intro) wrap.appendChild(UI.h('div', { class: 'hint', style: 'margin-bottom:10px' }, meta.intro));

      // 状态含义表：状态取值以页面元数据为主，UI.STATUS 与流转表兜底补充，保证不遗漏
      const codes = [];
      const seen = {};
      const addCode = (c) => { if (c && !seen[c]) { seen[c] = 1; codes.push(c); } };
      Object.keys(meta.desc || {}).forEach(addCode);
      Object.keys(UI.STATUS[kind] || {}).forEach(addCode);
      Object.entries(trs || {}).forEach(([f, ts]) => { addCode(f); (ts || []).forEach(addCode); });
      wrap.appendChild(UI.h('div', { class: 'hint', style: 'margin:12px 0 6px;font-weight:600' }, '状态含义'));
      wrap.appendChild(UI.table([
        { key: 'code', label: '状态', render: (r) => UI.h('span', { title: r.code }, UI.statusTag(kind, r.code)) },
        { key: 'desc', label: '业务含义', render: (r) => r.desc || '-' },
      ], codes.map((c) => ({ code: c, desc: (meta.desc || {})[c] })), '暂无状态'));

      // BUG-01 修复：后端 TRANSITIONS 为嵌套 dict {from: [to...]}，须展开为行数组
      // 再交给 UI.table 渲染；此前直接传 dict 导致判空显示"无流转"。
      const rows = [];
      Object.entries(trs || {}).forEach(([from, tos]) => (tos || []).forEach((to) => rows.push({ from, to })));
      wrap.appendChild(UI.h('div', { class: 'hint', style: 'margin:12px 0 6px;font-weight:600' }, '流转路径'));
      wrap.appendChild(UI.table([
        { key: 'from', label: '起始状态', render: (r) => UI.h('span', { title: r.from }, UI.statusTag(kind, r.from)) },
        { key: 'to', label: '目标状态', render: (r) => UI.h('span', { title: r.to }, UI.statusTag(kind, r.to)) },
      ], rows, '无流转'));

      // 特殊取值规则 / 业务关联提示
      (meta.notes || []).forEach((n) => wrap.appendChild(
        UI.h('div', { class: 'hint', style: 'margin-top:6px' }, '※ ' + n)));
    });
    page.appendChild(wrap);
  };

  /* -------- 操作日志 -------- */
  Pages.logs = async function (page) {
    let pageNo = 1;
    const SIZE = 15;
    const bizType = UI.input('text', '', { placeholder: '业务类型（如 DEMAND）', style: 'width:160px' });
    const bizId = UI.input('text', '', { placeholder: '业务ID', style: 'width:100px' });
    const listCard = UI.h('div', { class: 'card' });
    const pagerBox = UI.h('div', {});
    page.appendChild(UI.h('div', { class: 'card' },
      UI.h('div', { class: 'toolbar' },
        UI.h('h3', { style: 'margin:0;border:none;padding:0' }, '操作日志'),
        UI.h('div', { class: 'spacer' }),
        bizType, bizId,
        UI.h('button', { class: 'sm primary', onclick: () => { pageNo = 1; load(); } }, '查询'))));
    page.appendChild(listCard);
    page.appendChild(pagerBox);
    await load();

    async function load() {
      const d = await API.get('/logs' + API.qs({ bizType: bizType.value.trim(), bizId: bizId.value.trim(), page: pageNo, size: SIZE }));
      listCard.innerHTML = '';
      listCard.appendChild(UI.table([
        { key: 'bizType', label: '业务类型' },
        { key: 'bizId', label: '业务ID' },
        { key: 'action', label: '动作' },
        { key: 'after', label: '变更内容', full: true },
        { key: 'createdAt', label: '时间', render: (r) => UI.fmtDateTime(r.createdAt) },
      ], d.list, '暂无日志'));
      pagerBox.innerHTML = '';
      UI.pager(pagerBox, pageNo, SIZE, d.total, (p) => { pageNo = p; load(); });
    }
  };
})();
