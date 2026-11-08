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
        { key: 'defaultGrade', label: '默认牌号' },
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
      const unit = UI.input('text', '吨');
      const m = UI.modal('新增品种', UI.h('form', { onsubmit: (e) => e.preventDefault() },
        UI.h('div', { class: 'form-grid' },
          UI.formRow('品种代码', code, true),
          UI.formRow('品种名称', name, true),
          UI.formRow('默认牌号', grade),
          UI.formRow('计量单位', unit))), [
        UI.h('button', { class: 'primary', onclick: async () => {
          if (!code.value.trim() || !name.value.trim()) { UI.toast('请填写品种代码与名称', 'err'); return; }
          const g = grade.value.trim();
          if (g !== '' && (isNaN(Number(g)) || Number(g) < 0 || Number(g) > 999.99)) {
            UI.toast('默认牌号必须为 0～999.99 的数字（如 61.5）', 'err'); return;
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
        const pdate = UI.input('date', new Date().toISOString().slice(0, 10));
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
    const wrap = UI.h('div', { class: 'card' }, UI.h('h3', {}, '状态机字典（FR-10-05）'));
    Object.entries(d.transitions || {}).forEach(([biz, trs]) => {
      wrap.appendChild(UI.h('h4', { style: 'margin:14px 0 6px' }, biz));
      // BUG-01 修复：后端 TRANSITIONS 为嵌套 dict {from: [to...]}，须展开为行数组
      // 再交给 UI.table 渲染；此前直接传 dict 导致判空显示"无流转"。
      const rows = [];
      Object.entries(trs || {}).forEach(([from, tos]) => (tos || []).forEach((to) => rows.push({ from, to })));
      wrap.appendChild(UI.table([
        { key: 'from', label: '起始状态' },
        { key: 'to', label: '目标状态' },
      ], rows, '无流转'));
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
