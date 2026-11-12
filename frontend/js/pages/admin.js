/* 运营后台（PRD 4.10/FR-10）：仪表盘/企业审核/基础数据/单据总览/预警/字典/日志 */
(function () {
  window.Pages = window.Pages || {};

  /* -------- 运营仪表盘 -------- */
  Pages.dashboard = async function (page) {
    const d = await API.get('/admin/dashboard');
    const charts = await API.get('/admin/dashboard/charts');
    // 长条统计卡：准入企业 / 集采总货量 / 运单总数 / 总交易额
    const stripItems = [
      ['准入企业', String(d.companyApproved || 0), '家'],
      ['集采总货量', Number(d.procureQty || 0).toLocaleString('zh-CN'), '吨'],
      ['运单总数', String(d.waybillTotal || 0), '单'],
      ['总交易额', '¥' + Number(d.totalAmount || 0).toLocaleString('zh-CN'), ''],
    ];
    page.appendChild(UI.h('div', { class: 'card stat-strip' },
      stripItems.map(([label, val, unit]) => UI.h('div', { class: 'stat-strip-item' },
        UI.h('div', { class: 'stat-label' }, label),
        UI.h('div', { class: 'stat-value' }, val, UI.h('span', { class: 'stat-unit' }, unit))))));

    // 港口现货价 + 平台成交价：左侧同图双线（行业价格 vs 交易价格）
    const portRows = (await API.get('/base-prices/ports')).list || [];
    const portTrend = portRows
      .filter((r) => r.varietyName === 'PB粉' && r.portName === '黄骅港')
      .map((r) => ({ priceDate: r.priceDate, price: r.price }))
      .sort((a, b) => String(a.priceDate).localeCompare(String(b.priceDate)));
    const varieties = (await API.get('/base/varieties')).list || [];
    const pb = varieties.find((v) => v.varietyName === 'PB粉');
    const dealRows = pb
      ? ((await API.get('/base-prices/deal-trend?varietyId=' + pb.id)).list || [])
          .map((r) => ({ priceDate: r.priceDate, price: r.price }))
      : [];
    const trendSeries = [
      { name: '行业价格', color: '#1a5cb0', rows: portTrend },
      { name: '交易价格', color: '#af52de', dashed: true, rows: dealRows },
    ];

    // 右侧行情表与左图数据对应：日期并集 + 行业/交易价格 + 行业价格涨跌
    const dateMap = {};
    portTrend.forEach((r) => { dateMap[r.priceDate] = { priceDate: r.priceDate, industry: r.price }; });
    dealRows.forEach((r) => {
      const k = String(r.priceDate).slice(0, 10);
      const row = dateMap[k] = dateMap[k] || { priceDate: k };
      row.deal = r.price;
    });
    const quoteRows = Object.values(dateMap).sort((a, b) => String(b.priceDate).localeCompare(String(a.priceDate)));
    let prevIndustry = null;
    quoteRows.slice().sort((a, b) => String(a.priceDate).localeCompare(String(b.priceDate))).forEach((r) => {
      r.chg = (r.industry != null && prevIndustry != null) ? r.industry - prevIndustry : null;
      if (r.industry != null) prevIndustry = r.industry;
    });

    // 两栏：左侧 黄骅港 PB粉 双线趋势（垂直居中，详情=价格趋势详情页），右侧近7天行情
    page.appendChild(UI.h('div', { class: 'dash-two-col' },
      UI.h('div', { class: 'card dash-chart-card' },
        UI.h('div', { class: 'toolbar' },
          UI.h('h3', { style: 'margin:0;border:none;padding:0' }, '黄骅港 PB粉 价格趋势'),
          UI.h('div', { class: 'spacer' }),
          UI.h('button', { class: 'sm', onclick: () => { location.hash = '#/port-price'; } }, '详情')),
        UI.h('div', { class: 'trend-chart-wrap' }, UI.multiTrendChart(trendSeries))),
      UI.h('div', { class: 'card dash-quote-card' },
        UI.h('div', { class: 'toolbar' },
          UI.h('h3', { style: 'margin:0;border:none;padding:0' }, 'PB粉 价格行情（近7天）'),
          UI.h('div', { class: 'spacer' }),
          UI.h('button', { class: 'sm', onclick: () => { location.hash = '#/price-records'; } }, '详情')),
        UI.table([
          { label: '日期', render: (r) => UI.fmtDate(r.priceDate) },
          { label: '行业价格(元/吨)', num: true, render: (r) => r.industry != null ? UI.fmtMoney(r.industry) : '—' },
          { label: '交易价格(元/吨)', num: true, render: (r) => r.deal != null ? UI.fmtMoney(r.deal) : '—' },
          { label: '涨跌', render: (r) => chgTag(r.chg) },
        ], quoteRows.slice(0, 7), '暂无价格数据'))));

    // 货运趋势 / 矿种分布 / 运输方式运量对比
    const MODE_LABELS = { ROAD: '公路', RAIL: '铁路', WATER: '水运', SEA: '海运', MULTIMODAL: '多式联运' };
    const freightRows = (charts.freightTrend || [])
      .map((r) => ({ priceDate: r.trendDate, price: r.qty }));
    const varietyDist = (charts.varietyDist || []).map((r) => ({ name: r.name, qty: Number(r.qty) }));
    const modeDist = (charts.modeDist || []).map((r) => ({ name: MODE_LABELS[r.mode] || r.mode, qty: Number(r.qty) }));
    // 货运趋势（单独一行全宽）
    page.appendChild(UI.h('div', { class: 'card' },
      UI.h('div', { class: 'toolbar' },
        UI.h('h3', { style: 'margin:0;border:none;padding:0' }, '货运趋势（近14日运量）')),
      freightRows.length >= 2
        ? UI.trendChart(freightRows, 'price', '吨')
        : UI.h('div', { class: 'empty' }, '暂无运单数据')));
    // 矿种分布 + 运输方式运量对比（同行两列）
    page.appendChild(UI.h('div', { class: 'dash-charts' },
      UI.h('div', { class: 'card' },
        UI.h('h3', {}, '矿种分布'),
        UI.donutChart(varietyDist, 'qty', 'name', '总运量(吨)')),
      UI.h('div', { class: 'card' },
        UI.h('h3', {}, '运输方式运量对比'),
        UI.hbarChart(modeDist, 'qty', 'name', '吨'))));
  };

  /* 涨跌标签：红涨绿跌，无对比基准显示 — */
  function chgTag(chg) {
    if (chg == null) return UI.h('span', { class: 'tag' }, '—');
    if (chg > 0) return UI.h('span', { class: 'tag red' }, '+' + chg.toFixed(2));
    if (chg < 0) return UI.h('span', { class: 'tag green' }, chg.toFixed(2));
    return UI.h('span', { class: 'tag' }, '持平');
  }

  /* -------- 价格趋势详情（独立页面，同钢厂端价格页结构；运营端可见行业+交易两个价格） -------- */
  Pages.port_price = async function (page) {
    const varieties = (await API.get('/base/varieties')).list || [];
    const pb = varieties.find((v) => v.varietyName === 'PB粉');
    if (!pb) {
      page.appendChild(UI.h('div', { class: 'card' }, UI.h('div', { class: 'empty' }, '品种库缺少 PB粉，请先在基础数据中添加')));
      return;
    }
    const portRows = ((await API.get('/base-prices/ports')).list || []).filter((r) => r.varietyName === 'PB粉');

    page.appendChild(UI.h('div', { class: 'card' },
      UI.h('div', { class: 'toolbar' },
        UI.h('h3', { style: 'margin:0;border:none;padding:0' }, 'PB粉 价格趋势详情'),
        UI.h('div', { class: 'spacer' }),
        UI.h('button', { class: 'sm', onclick: () => { location.hash = '#/dashboard'; } }, '返回看板'))));

    // 今日港口价（每港口最新一条）
    const byPort = {};
    portRows.forEach((r) => { (byPort[r.portName] = byPort[r.portName] || []).push(r); });
    const latest = Object.keys(byPort).map((p) =>
      byPort[p].slice().sort((a, b) => String(b.priceDate).localeCompare(String(a.priceDate)))[0]);
    page.appendChild(UI.h('div', { class: 'card' },
      UI.h('h3', {}, '今日港口价'),
      UI.table([
        { key: 'portName', label: '港口' },
        { label: '行业价格(元/吨)', num: true, render: (r) => UI.fmtMoney(r.price) },
        { label: '价格日期', render: (r) => UI.fmtDate(r.priceDate) },
      ], latest, '暂无港口价格，请在下方录入')));

    // 行业价格走势：每港口一张图（多图）
    const trendCard = UI.h('div', { class: 'card' }, UI.h('h3', {}, '行业价格走势（分港口）'));
    Object.keys(byPort).sort().forEach((p) => {
      const rows = byPort[p].slice().sort((a, b) => String(a.priceDate).localeCompare(String(b.priceDate)));
      trendCard.appendChild(UI.h('div', { style: 'margin-bottom:16px' },
        UI.h('div', { class: 'dash-trend-name' }, p + ' · 行业价格'),
        UI.trendChart(rows.map((r) => ({ priceDate: r.priceDate, price: r.price })), 'price')));
    });
    if (!Object.keys(byPort).length) trendCard.appendChild(UI.h('div', { class: 'empty' }, '暂无走势数据'));
    page.appendChild(trendCard);

    // 交易价格走势（平台成交均价，钢厂端不可见）
    const dealRows = ((await API.get('/base-prices/deal-trend?varietyId=' + pb.id)).list || [])
      .map((r) => ({ priceDate: r.priceDate, price: r.price }));
    page.appendChild(UI.h('div', { class: 'card' },
      UI.h('h3', {}, '交易价格走势（平台成交均价）'),
      dealRows.length >= 2 ? UI.trendChart(dealRows, 'price') : UI.h('div', { class: 'empty' }, '暂无成交数据')));
  };

  /* -------- 价格行情详情（全部价格数据 + 港口价格录入） -------- */
  Pages.price_records = async function (page) {
    const varieties = (await API.get('/base/varieties')).list || [];
    const pb = varieties.find((v) => v.varietyName === 'PB粉');
    if (!pb) {
      page.appendChild(UI.h('div', { class: 'card' }, UI.h('div', { class: 'empty' }, '品种库缺少 PB粉，请先在基础数据中添加')));
      return;
    }
    const portRows = ((await API.get('/base-prices/ports')).list || []).filter((r) => r.varietyName === 'PB粉');
    const dealRows = ((await API.get('/base-prices/deal-trend?varietyId=' + pb.id)).list || []);

    // 全部价格数据：日期并集 + 行业/交易价格 + 行业价格涨跌
    const dateMap = {};
    portRows.forEach((r) => {
      const k = String(r.priceDate).slice(0, 10);
      dateMap[k] = { priceDate: k, industry: r.price };
    });
    dealRows.forEach((r) => {
      const k = String(r.priceDate).slice(0, 10);
      const row = dateMap[k] = dateMap[k] || { priceDate: k };
      row.deal = r.price;
    });
    const allRows = Object.values(dateMap).sort((a, b) => String(b.priceDate).localeCompare(String(a.priceDate)));
    let prev = null;
    allRows.slice().sort((a, b) => String(a.priceDate).localeCompare(String(b.priceDate))).forEach((r) => {
      r.chg = (r.industry != null && prev != null) ? r.industry - prev : null;
      if (r.industry != null) prev = r.industry;
    });

    page.appendChild(UI.h('div', { class: 'card' },
      UI.h('div', { class: 'toolbar' },
        UI.h('h3', { style: 'margin:0;border:none;padding:0' }, 'PB粉 价格行情详情'),
        UI.h('div', { class: 'spacer' }),
        UI.h('button', { class: 'sm', onclick: () => { location.hash = '#/dashboard'; } }, '返回看板'))));

    page.appendChild(UI.h('div', { class: 'card' },
      UI.h('h3', {}, '全部价格数据'),
      UI.table([
        { label: '日期', render: (r) => UI.fmtDate(r.priceDate) },
        { label: '行业价格(元/吨)', num: true, render: (r) => r.industry != null ? UI.fmtMoney(r.industry) : '—' },
        { label: '交易价格(元/吨)', num: true, render: (r) => r.deal != null ? UI.fmtMoney(r.deal) : '—' },
        { label: '涨跌', render: (r) => chgTag(r.chg) },
      ], allRows, '暂无价格数据')));

    // 港口价格录入
    const portName = UI.input('text', '', { placeholder: '港口名称，如：黄骅港' });
    const priceDate = UI.input('date', '', {});
    const price = UI.input('number', '', { placeholder: '价格（元/吨）' });
    page.appendChild(UI.h('div', { class: 'card' },
      UI.h('h3', {}, '录入 / 更新港口价格'),
      UI.h('div', { class: 'form-grid' },
        UI.formRow('港口名称', portName, true),
        UI.formRow('价格日期', priceDate, true),
        UI.formRow('价格(元/吨)', price, true)),
      UI.h('div', { class: 'hint' }, '同一港口同一日期重复保存将更新价格'),
      UI.h('div', { style: 'margin-top:10px' },
        UI.h('button', {
          class: 'primary',
          onclick: async () => {
            if (!portName.value.trim()) { UI.toast('港口名称为必填', 'err'); return; }
            if (!priceDate.value) { UI.toast('价格日期为必填', 'err'); return; }
            if (!(Number(price.value) > 0)) { UI.toast('价格需大于 0', 'err'); return; }
            try {
              await API.post('/base-prices/ports', {
                varietyId: pb.id, portName: portName.value.trim(),
                priceDate: priceDate.value, price: Number(price.value),
              });
              UI.toast('已保存', 'ok');
              Pages.price_records(document.getElementById('page'), API.currentUser());
            } catch (e) { /* toast 已提示 */ }
          },
        }, '保 存'))));
  };

  /* -------- 企业审核台 -------- */
  Pages.admin_companies = async function (page) {
    let pageNo = 1;
    const SIZE = 10;
    let auditStatus = '';
    let tab = 'list'; // list=准入申请列表 archive=企业档案信息
    let cache = [];

    const TABS = [
      ['list', '准入申请列表'],
      ['archive', '企业档案信息'],
    ];
    const tabBar = UI.h('div', { class: 'tab-bar' },
      ...TABS.map(([key, label]) => UI.h('button', {
        class: 'tab-btn', 'data-tab': key,
        onclick: () => { tab = key; pageNo = 1; render(); },
      }, label)));

    function syncTabs() {
      tabBar.querySelectorAll('.tab-btn').forEach((b) => {
        b.classList.toggle('active', b.getAttribute('data-tab') === tab);
      });
    }

    const listBox = UI.h('div', {});
    const pagerBox = UI.h('div', {});

    const bigCard = UI.h('div', { class: 'card company-audit-card' },
      UI.h('div', { class: 'toolbar' },
        UI.h('h3', { style: 'margin:0;border:none;padding:0' }, '企业准入'),
        UI.h('div', { class: 'spacer' }),
        UI.h('div', { id: 'audit-filter-box' })),
      tabBar,
      listBox,
      pagerBox);
    page.appendChild(bigCard);
    render();

    /* 表格外层：整表框线 + 超宽横向滚动 + 固定高度区域内滚动 */
    function tableWrap(table) { return UI.h('div', { class: 'table-scroll-wrap' }, table); }

    function filterBox() { return document.getElementById('audit-filter-box'); }

    async function render() {
      const box = filterBox();
      if (!box) return;
      syncTabs();
      box.innerHTML = '';
      if (tab === 'list') {
        box.appendChild(UI.statusFilter('AUDIT', (v) => { auditStatus = v; pageNo = 1; load(); }));
        await load();
      } else {
        box.innerHTML = '';
        listBox.innerHTML = '';
        pagerBox.innerHTML = '';
        if (!cache.length) {
          const d = await API.get('/admin/companies' + API.qs({ auditStatus: '', page: 1, size: 200 }));
          cache = d.list || [];
        }
        if (tab === 'archive') {
          listBox.appendChild(tableWrap(UI.table([
            { label: '序号', render: (r) => String(cache.indexOf(r) + 1) },
            { key: 'companyName', label: '企业名称' },
            { key: 'creditCode', label: '统一社会信用代码' },
            { key: 'companyTypes', label: '企业类型' },
            { key: 'contactName', label: '联系人' },
            { key: 'contactPhone', label: '联系电话' },
            { label: '操作', render: (r) => UI.h('span', { class: 'inline-flex' }, UI.h('button', { class: 'sm', onclick: () => detail(r.id) }, '详情')) },
          ], cache, '暂无企业档案')));
        }
        pagerBox.innerHTML = '';
      }
    }

    async function load() {
      const d = await API.get('/admin/companies' + API.qs({ auditStatus, page: pageNo, size: SIZE }));
      cache = d.list || [];
      listBox.innerHTML = '';
      listBox.appendChild(tableWrap(UI.table([
        { label: '序号', render: (r) => String((pageNo - 1) * SIZE + cache.indexOf(r) + 1) },
        { key: 'companyName', label: '企业名称' },
        { key: 'creditCode', label: '统一社会信用代码' },
        { key: 'companyTypes', label: '企业类型' },
        { key: 'contactName', label: '联系人' },
        { key: 'contactPhone', label: '联系电话' },
        { key: 'createdAt', label: '提交时间', render: (r) => r.createdAt ? UI.fmtDate(String(r.createdAt).replace('T', ' ').slice(0, 16)) : '—' },
        { key: 'status', label: '账号状态', render: (r) => r.status === 'ENABLED' ? UI.h('span', { class: 'tag green' }, '启用') : UI.h('span', { class: 'tag red' }, '停用') },
        { label: '操作', render: (r) => acts(r) },
      ], d.list, '暂无企业')));
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

    async function auditModal(r) {
      // 审核弹窗：先载入企业准入登记资料（提交的完整信息），再给出审核结论
      let c = {};
      try { c = await API.get('/companies/' + r.id); } catch (e) { /* 降级为列表行数据 */ }
      const info = UI.kv([
        ['企业名称', c.companyName || c.company_name || r.companyName],
        ['统一社会信用代码', c.creditCode || c.credit_code || r.creditCode],
        ['企业类型', c.companyTypes || c.company_types || r.companyTypes],
        ['联系人', c.contactName || c.contact_name || r.contactName],
        ['联系电话', c.contactPhone || c.contact_phone || r.contactPhone],
        ['注册地址', c.address || c.registered_address || '-', true],
        ['经营范围', c.businessScope || c.business_scope || '-', true],
      ]);
      const approve = UI.selectField([['true', '通过'], ['false', '驳回']], 'true');
      const remark = UI.h('textarea', { rows: 2, style: 'width:100%', placeholder: '审核意见（驳回必填）' });
      const m = UI.modal('准入审核 · ' + (c.companyName || c.company_name || r.companyName), UI.h('form', { onsubmit: (e) => e.preventDefault() },
        UI.h('h3', { style: 'margin:0 0 8px' }, '准入登记资料'), info,
        UI.h('h3', { style: 'margin:14px 0 8px' }, '审核结论'),
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

    const QUAL_FILE_TYPE = { BUSINESS_LICENSE: '营业执照' };
    const LOG_FIELD = {
      companyName: '企业名称', creditCode: '统一社会信用代码', province: '所在省份', city: '所在城市',
      address: '经营地址', legalPerson: '法定代表人', contactName: '联系人', contactPhone: '联系电话',
      contactEmail: '联系邮箱', businessScope: '经营范围', bankName: '开户银行', bankAccount: '银行账户',
      auditStatus: '审核状态', status: '账号状态',
    };
    function logAction(a) {
      if (!a) return '-';
      if (a === 'UPDATE') return '信息变更';
      if (a === 'CREATE') return '创建档案';
      if (a.indexOf('STATUS') === 0) return '状态变更';
      return a;
    }
    function logContent(after) {
      if (!after) return '-';
      try {
        const o = typeof after === 'string' ? JSON.parse(after) : after;
        const parts = Object.keys(o).map((k) =>
          (LOG_FIELD[k] || k) + '：' + (o[k] == null || o[k] === '' ? '-' : o[k]));
        return parts.join('；') || '-';
      } catch (e) { return String(after); }
    }

    async function detail(cid) {
      const d = await API.get('/companies/' + cid);
      const c = d;
      const box = UI.h('div', {});

      box.appendChild(UI.h('h3', { style: 'margin:0 0 8px' }, '基本信息'));
      box.appendChild(UI.kv([
        ['企业名称', c.companyName || c.company_name],
        ['统一社会信用代码', c.creditCode || c.credit_code],
        ['企业角色', c.companyTypes || c.company_types],
        ['所在省市', ((c.province || '') + ' ' + (c.city || '')).trim() || '-'],
        ['法定代表人', c.legalPerson || c.legal_person],
        ['联系人', c.contactName || c.contact_name],
        ['联系电话', c.contactPhone || c.contact_phone],
        ['联系邮箱', c.contactEmail || c.contact_email],
        ['开户银行', c.bankName || c.bank_name],
        ['银行账户', c.bankAccount || c.bank_account],
        ['经营地址', c.address, true],
        ['经营范围', c.businessScope || c.business_scope, true],
      ]));

      box.appendChild(UI.h('h3', { style: 'margin:14px 0 8px' }, '营业执照'));
      const quals = d.qualifications || [];
      box.appendChild(quals.length ? UI.table([
        { key: 'fileName', label: '文件名称' },
        { key: 'fileType', label: '类型', render: (r) => QUAL_FILE_TYPE[r.fileType] || r.fileType || '-' },
        { label: '操作', render: (r) => r.fileId ? UI.h('a', { href: 'javascript:;', onclick: () => API.downloadFile(r.fileId, r.fileName || '证照文件') }, '下载') : '-' },
      ], quals, '暂无证照文件') : UI.h('div', { class: 'empty' }, '暂无证照文件'));

      box.appendChild(UI.h('h3', { style: 'margin:14px 0 8px' }, '准入信息'));
      box.appendChild(UI.kv([
        ['审核状态', UI.statusTag('AUDIT', c.auditStatus || c.audit_status)],
        ['审核意见', c.auditRemark || c.audit_remark],
        ['准入登记时间', c.createdAt || c.created_at ? UI.fmtDateTime(String(c.createdAt || c.created_at).replace('T', ' ').slice(0, 16)) : '—'],
      ]));

      box.appendChild(UI.h('h3', { style: 'margin:14px 0 8px' }, '合作信息'));
      const coop = d.coop || {};
      box.appendChild(UI.kv([
        ['累计需求单', String(coop.demandCount || 0) + ' 单'],
        ['成交订单数', String(coop.orderCount || 0) + ' 单'],
        ['累计成交量', String(coop.totalQty || 0) + ' 吨'],
        ['累计成交金额', '¥ ' + UI.fmtMoney(coop.totalAmount || 0)],
        ['关联合同数', String(coop.contractCount || 0) + ' 份'],
        ['最近成交时间', coop.lastDealAt ? UI.fmtDateTime(coop.lastDealAt) : '—'],
      ]));

      box.appendChild(UI.h('h3', { style: 'margin:14px 0 8px' }, '企业变更信息'));
      const logs = d.changeLogs || [];
      box.appendChild(logs.length ? UI.table([
        { key: 'createdAt', label: '时间', render: (r) => UI.fmtDateTime(r.createdAt) },
        { key: 'operator', label: '操作人', render: (r) => r.operator || '-' },
        { key: 'action', label: '变更类型', render: (r) => logAction(r.action) },
        { key: 'after_value', label: '变更内容', render: (r) => logContent(r.after_value) },
      ], logs, '暂无变更记录') : UI.h('div', { class: 'empty' }, '暂无变更记录'));

      UI.modal('企业详情', box, null, { wide: true });
    }
  };

  /* -------- 需求归集：需求列表 + 变更申请审核 -------- */
  Pages.demand_pool = async function (page) {
    const SIZE = 10;
    let pageNo = 1;
    let chPageNo = 1;
    let aggPageNo = 1;
    let tab = 'demands'; // demands=需求列表 aggr=归集订单 changes=变更申请审核
    let demandStatus = '';
    let changeStatus = '';
    let aggStatus = '';
    let demandRows = [];
    const picked = new Set(); // 勾选的待归集需求明细 id
    const pickedAgg = new Set(); // 勾选的归集订单（OPEN）
    // 表格横向滚动容器：超宽时面板内右拉
    const scrollWrap = (node, style) => UI.h('div', { class: 'table-scroll-wrap', style }, node);

    const TABS = [
      ['demands', '需求列表'],
      ['aggr', '订单归集'],
      ['changes', '变更申请审核'],
    ];
    const tabBar = UI.h('div', { class: 'tab-bar' },
      ...TABS.map(([key, label]) => UI.h('button', {
        class: 'tab-btn', 'data-tab': key,
        onclick: () => { tab = key; pageNo = 1; chPageNo = 1; aggPageNo = 1; picked.clear(); pickedAgg.clear(); render(); },
      }, label)));

    const filterBox = UI.h('div', {});
    const listBox = UI.h('div', {});
    const pagerBox = UI.h('div', {});

    page.appendChild(UI.h('div', { class: 'card' },
      UI.h('div', { class: 'toolbar' },
        UI.h('h3', { style: 'margin:0;border:none;padding:0' }, '需求归集'),
        UI.h('div', { class: 'spacer' }),
        filterBox),
      tabBar,
      listBox,
      pagerBox));
    render();

    function syncTabs() {
      page.querySelectorAll('.tab-btn').forEach((b) => {
        b.classList.toggle('active', b.getAttribute('data-tab') === tab);
      });
    }

    async function render() {
      syncTabs();
      filterBox.innerHTML = '';
      pagerBox.innerHTML = '';
      if (tab === 'demands') {
        filterBox.appendChild(UI.h('button', {
          class: 'primary', style: 'margin-right:8px', onclick: mergeAggregated,
        }, '合并归集'));
        filterBox.appendChild(UI.statusFilter('DEMAND', (v) => { demandStatus = v; pageNo = 1; picked.clear(); loadDemands(); }));
        await loadDemands();
      } else if (tab === 'aggr') {
        filterBox.appendChild(UI.h('button', {
          class: 'primary', style: 'margin-right:8px',
          onclick: () => {
            // 带上勾选的 OPEN 归集订单，跳转后自动弹出发起询价弹窗
            if (pickedAgg.size) sessionStorage.setItem('agg_inquiry_seed', String([...pickedAgg][0]));
            location.hash = '#/quote-inquiry';
          },
        }, '去询价'));
        filterBox.appendChild(UI.statusFilter('AGG', (v) => { aggStatus = v; aggPageNo = 1; loadAggr(); }));
        await loadAggr();
      } else {
        filterBox.appendChild(UI.statusFilter('CHANGE', (v) => { changeStatus = v; chPageNo = 1; loadChanges(); }));
        await loadChanges();
      }
    }

    async function loadDemands() {
      const d = await API.get('/admin/demand-pool' + API.qs({ status: demandStatus, page: pageNo, size: SIZE }));
      demandRows = d.list || [];
      listBox.innerHTML = '';
      listBox.appendChild(scrollWrap(UI.table([
        { label: '', render: (r) => {
            if (r.status !== 'SUBMITTED') return UI.h('span', { class: 'muted' }, '-');
            const el = UI.h('input', { type: 'checkbox', title: '勾选参与归集' });
            el.checked = picked.has(r.id);
            el.addEventListener('change', () => { if (el.checked) picked.add(r.id); else picked.delete(r.id); });
            return el;
          } },
        { label: '序号', render: (r) => String((pageNo - 1) * SIZE + demandRows.indexOf(r) + 1) },
        { key: 'demandNo', label: '单号' },
        { key: 'companyName', label: '企业' },
        { key: 'category', label: '品类', render: (r) => r.category || '-' },
        { key: 'varietyName', label: '矿种' },
        { key: 'quantity', label: '吨数', num: true },
        { key: 'grade', label: '品位(%)', num: true },
        { label: '提货地点', render: (r) => {
            const t = { PORT_FOB: '港口离岸', PORT_TRUCK: '港口自提', PLANT: '厂内自提' }[r.deliveryType] || '';
            return (r.deliveryPlace || '-') + (t ? '（' + t + '）' : '');
          } },
        { label: '到货日期', render: (r) => UI.fmtDate(r.expectArriveStart) + ' ~ ' + UI.fmtDate(r.expectArriveEnd) },
        { key: 'status', label: '状态', render: (r) => UI.statusTag('DEMAND', r.status) },
        { label: '提交日期', render: (r) => (r.submittedAt ? UI.fmtDate(r.submittedAt) : '-') },
        { label: '操作', render: (r) => UI.h('button', { class: 'sm', onclick: () => demandDetail(r.demandId) }, '详情') },
      ], demandRows, '暂无需求')));
      UI.pager(pagerBox, pageNo, SIZE, d.total, (p) => { pageNo = p; loadDemands(); });
    }

    /* 合并归集：勾选同品种同品位的已提交明细 → 生成归集订单（后端锁定量） */
    async function mergeAggregated() {
      if (!picked.size) { UI.toast('请先在列表中勾选需求明细（仅「已提交」状态可勾选）', 'err'); return; }
      const rows = demandRows.filter((r) => picked.has(r.id));
      const key = (r) => String(r.varietyName) + '@' + (r.grade == null ? '' : String(r.grade));
      if (new Set(rows.map(key)).size > 1) { UI.toast('仅同品种且同品位的明细可合并归集', 'err'); return; }
      const remain = rows.reduce((s, r) => s + (r.quantity - (r.inquiredQty || 0)), 0);
      if (remain <= 0) { UI.toast('勾选明细已无可归集量', 'err'); return; }
      if (!(await UI.confirmBox('将 ' + rows.length + ' 条明细合并为归集订单（合计 ' + remain + ' 吨，全量锁定）？'))) return;
      try {
        const res = await API.post('/admin/aggregated-orders', { itemIds: [...picked] });
        picked.clear();
        UI.toast('归集订单 ' + res.aggNo + ' 已生成（' + res.totalQty + ' 吨），即将跳转归集订单页', 'ok');
        tab = 'aggr'; aggPageNo = 1; // 自动跳转归集订单页
        render();
      } catch (e) { /* toast 已提示 */ }
    }

    async function loadAggr() {
      const d = await API.get('/admin/aggregated-orders' + API.qs({ status: aggStatus, page: aggPageNo, size: SIZE }));
      const rows = d.list || [];
      listBox.innerHTML = '';
      listBox.appendChild(scrollWrap(UI.table([
        { label: '', render: (r) => {
            if (r.status !== 'OPEN') return UI.h('span', { class: 'muted' }, '-');
            const el = UI.h('input', { type: 'checkbox', title: '勾选待询价归集订单' });
            el.checked = pickedAgg.has(r.id);
            el.addEventListener('change', () => { if (el.checked) pickedAgg.add(r.id); else pickedAgg.delete(r.id); });
            return el;
          } },
        { label: '序号', render: (r) => String((aggPageNo - 1) * SIZE + rows.indexOf(r) + 1) },
        { key: 'aggNo', label: '归集单号' },
        { key: 'varietyName', label: '矿种' },
        { key: 'grade', label: '品位(%)', num: true },
        { key: 'totalQty', label: '总吨数', num: true },
        { label: '参与钢厂', render: (r) => r.companyNames || '-' },
        { key: 'memberCount', label: '家数', num: true },
        { label: '关联询价', render: (r) => r.inquiryNo
          ? UI.h('span', {}, r.inquiryNo + ' ', UI.statusTag('INQUIRY', r.inquiryStatus))
          : '-' },
        { key: 'status', label: '状态', render: (r) => {
            const tag = UI.statusTag('AGG', r.status);
            if (r.status === 'INQUIRING') {
              tag.title = '归集订单已进入询价流程（直至定标或关闭）；每一轮询价的具体状态见「关联询价」列';
            }
            return tag;
          } },
        { label: '归集时间', render: (r) => UI.fmtDateTime(r.createdAt) },
        { label: '操作', render: (r) => UI.h('span', { class: 'inline-flex' },
            UI.h('button', { class: 'sm', onclick: () => aggDetail(r.id) }, '详情'),
            r.status === 'OPEN'
              ? UI.h('button', { class: 'sm', onclick: () => aggClose(r) }, '关闭')
              : null) },
      ], rows, '暂无归集订单（在需求列表勾选同品种同品位明细后点「合并归集」生成）')));
      UI.pager(pagerBox, aggPageNo, SIZE, d.total, (p) => { aggPageNo = p; loadAggr(); });
    }

    async function aggDetail(aid) {
      const d = await API.get('/admin/aggregated-orders/' + aid);
      const o = d.order;
      UI.modal('归集订单详情 · ' + o.aggNo, UI.h('div', {},
        UI.kv([
          ['归集单号', o.aggNo],
          ['矿种', (o.varietyName || '-') + '（' + (o.category || '-') + '）'],
          ['品位(%)', o.grade == null ? '-' : String(o.grade)],
          ['总吨数', String(o.totalQty)],
          ['状态', UI.statusTag('AGG', o.status)],
          ['备注', o.remark || '-'],
          ['归集时间', UI.fmtDateTime(o.createdAt)],
        ]),
        UI.h('h3', { style: 'margin:14px 0 8px' }, '参与明细（钢厂份额）'),
        scrollWrap(UI.h('table', { class: 'grid' },
          UI.h('thead', {}, UI.h('tr', {},
            UI.h('th', {}, '钢厂'), UI.h('th', {}, '需求单号'), UI.h('th', {}, '需求名称'),
            UI.h('th', { style: 'text-align:right' }, '归集份额(吨)'))),
          UI.h('tbody', {}, (d.members || []).map((m) => UI.h('tr', {},
            UI.h('td', {}, m.companyName || '-'),
            UI.h('td', {}, m.demandNo || '-'),
            UI.h('td', {}, m.demandName || '-'),
            UI.h('td', { class: 'num' }, String(m.quantity)))))))));
    }

    async function aggClose(r) {
      if (!(await UI.confirmBox('关闭归集订单 ' + r.aggNo + '？将释放各钢厂锁定量，需求回退为已提交。'))) return;
      try {
        await API.put('/admin/aggregated-orders/' + r.id + '/close', {});
        UI.toast('归集订单已关闭，锁定量已释放', 'ok');
        loadAggr();
      } catch (e) { /* toast 已提示 */ }
    }

    function demandDetail(demandId) {
      const rows = demandRows.filter((r) => r.demandId === demandId);
      const head = rows[0] || {};
      const items = rows.map((r) => [r.category || '-', r.varietyName, r.grade, r.quantity]);
      UI.modal('需求详情 · ' + (head.demandNo || ''), UI.h('div', {},
        UI.kv([
          ['单号', head.demandNo],
          ['需求名称', head.demandName],
          ['企业', head.companyName],
          ['状态', UI.statusTag('DEMAND', head.status)],
          ['版本', 'v' + (head.version || 1)],
          ['期望到货', UI.fmtDate(head.expectArriveStart) + ' ~ ' + UI.fmtDate(head.expectArriveEnd)],
          ['提交日期', head.submittedAt ? UI.fmtDate(head.submittedAt) : '-'],
        ]),
        UI.h('h3', { style: 'margin:14px 0 8px' }, '需求明细'),
        scrollWrap(UI.h('table', { class: 'grid' },
          UI.h('thead', {}, UI.h('tr', {},
            UI.h('th', {}, '品类'), UI.h('th', {}, '矿种'),
            UI.h('th', { style: 'text-align:right' }, '品位(%)'),
            UI.h('th', { style: 'text-align:right' }, '吨数'))),
          UI.h('tbody', {}, items.map(([cat, vn, g, q]) => UI.h('tr', {},
            UI.h('td', {}, String(cat)),
            UI.h('td', {}, String(vn || '-')),
            UI.h('td', { class: 'num' }, String(g == null ? '-' : g)),
            UI.h('td', { class: 'num' }, String(q == null ? '-' : q)))))))));
    }

    async function loadChanges() {
      const d = await API.get('/admin/demand-changes' + API.qs({ status: changeStatus, page: chPageNo, size: SIZE }));
      listBox.innerHTML = '';
      listBox.appendChild(scrollWrap(UI.table([
        { label: '序号', render: (r) => String((chPageNo - 1) * SIZE + (d.list.indexOf(r) + 1)) },
        { key: 'changeNo', label: '变更单号' },
        { key: 'demandNo', label: '需求单号', render: (r) => r.demandNo || '-' },
        { key: 'companyName', label: '企业' },
        { label: '变更内容', render: (r) => changeSummary(r) },
        { key: 'reason', label: '变更原因', full: true },
        { key: 'status', label: '状态', render: (r) => UI.statusTag('CHANGE', r.status) },
        { label: '申请日期', render: (r) => UI.fmtDate(r.createdAt) },
        { label: '操作', render: (r) => r.status === 'PENDING'
          ? UI.h('button', { class: 'sm primary', onclick: () => auditModal(r) }, '审核')
          : UI.h('button', { class: 'sm', onclick: () => changeDetail(r) }, '详情') },
      ], d.list, '暂无变更申请')));
      UI.pager(pagerBox, chPageNo, SIZE, d.total, (p) => { chPageNo = p; loadChanges(); });
    }

    function changeSummary(r) {
      const before = r.beforeData || {};
      const after = r.afterData || {};
      const parts = [];
      Object.keys(after).forEach((k) => {
        if (String(before[k]) !== String(after[k])) {
          parts.push(k + ' ' + (before[k] == null ? '-' : before[k]) + '→' + after[k]);
        }
      });
      return parts.join('；') || '-';
    }

    function changeDiff(r) {
      const before = r.beforeData || {};
      const after = r.afterData || {};
      const keys = [];
      Object.keys(before).forEach((k) => { if (keys.indexOf(k) < 0) keys.push(k); });
      Object.keys(after).forEach((k) => { if (keys.indexOf(k) < 0) keys.push(k); });
      if (!keys.length) return UI.h('div', { class: 'hint' }, '无变更明细');
      return scrollWrap(UI.h('table', { class: 'grid' },
        UI.h('thead', {}, UI.h('tr', {},
          UI.h('th', {}, '变更项'),
          UI.h('th', { style: 'text-align:right' }, '变更前'),
          UI.h('th', { style: 'text-align:right' }, '变更后'))),
        UI.h('tbody', {}, keys.map((k) => UI.h('tr', {},
          UI.h('td', {}, k),
          UI.h('td', { class: 'num' }, String(before[k] == null ? '-' : before[k])),
          UI.h('td', { class: 'num' }, String(after[k] == null ? '-' : after[k]))))),
        ), 'margin-bottom:8px');
    }

    function auditModal(r) {
      const approve = UI.selectField([['true', '通过'], ['false', '驳回']], 'true');
      const remark = UI.h('textarea', { rows: 2, style: 'width:100%', placeholder: '审核意见（驳回必填）' });
      const m = UI.modal('变更申请审核 · ' + r.changeNo, UI.h('form', { onsubmit: (e) => e.preventDefault() },
        UI.h('h3', { style: 'margin:0 0 8px' }, '变更内容'),
        changeDiff(r),
        UI.h('div', { class: 'hint', style: 'margin:8px 0' }, '变更原因：' + (r.reason || '-')),
        UI.h('h3', { style: 'margin:14px 0 8px' }, '审核结论'),
        UI.h('div', { class: 'form-grid' },
          UI.formRow('审核结论', approve, true),
          UI.h('div', { class: 'form-row full' }, UI.h('label', {}, '审核意见'), remark))), [
        UI.h('button', { class: 'primary', onclick: async () => {
          if (approve.value === 'false' && !remark.value.trim()) { UI.toast('驳回必须填写原因', 'err'); return; }
          try {
            await API.put('/admin/demand-changes/' + r.id + '/audit', { approve: approve.value, remark: remark.value.trim() });
            m.close(); UI.toast('审核完成', 'ok'); loadChanges();
          } catch (e) { /* toast 已提示 */ }
        } }, '提 交'),
      ]);
    }

    function changeDetail(r) {
      UI.modal('变更申请详情 · ' + r.changeNo, UI.h('div', {},
        UI.h('h3', { style: 'margin:0 0 8px' }, '变更内容'),
        changeDiff(r),
        UI.kv([
          ['需求单号', r.demandNo || '-'],
          ['企业', r.companyName],
          ['变更原因', r.reason || '-', true],
          ['审核结论', UI.statusTag('CHANGE', r.status)],
          ['审核意见', r.auditRemark || '-', true],
          ['审核时间', r.auditAt ? UI.fmtDateTime(r.auditAt) : '-'],
        ])));
    }
  };

  /* -------- 报价询价：汇集需求代钢厂统一询价 → 汇总报价返回钢厂 -------- */
  Pages.quote_inquiry = async function (page) {
    const SIZE = 10;
    let pageNo = 1;
    let status = '';
    // 表格横向滚动容器：超宽时面板内右拉
    const scrollWrap = (node, style) => UI.h('div', { class: 'table-scroll-wrap', style }, node);

    const listCard = UI.h('div', { class: 'card' });
    const pagerBox = UI.h('div', {});
    page.appendChild(UI.h('div', { class: 'card' },
      UI.h('div', { class: 'toolbar' },
        UI.h('h3', { style: 'margin:0;border:none;padding:0' }, '报价询价'),
        UI.h('div', { class: 'spacer' }),
        UI.statusFilter('INQUIRY', (v) => { status = v; pageNo = 1; load(); }),
        UI.h('button', { class: 'primary', onclick: () => createModal() }, '发起询价'))));
    page.appendChild(listCard);
    page.appendChild(pagerBox);
    await load();

    // 从需求归集「去询价」跳转过来：自动弹出发起询价弹窗并带入勾选的归集订单
    const seedAgg = sessionStorage.getItem('agg_inquiry_seed');
    if (seedAgg) {
      sessionStorage.removeItem('agg_inquiry_seed');
      createModal(seedAgg);
    }

    async function load() {
      const d = await API.get('/admin/quote-inquiries' + API.qs({ status, page: pageNo, size: SIZE }));
      listCard.innerHTML = '';
      listCard.appendChild(scrollWrap(UI.table([
        { label: '序号', render: (r) => String((pageNo - 1) * SIZE + d.list.indexOf(r) + 1) },
        { key: 'inquiryNo', label: '询价单号' },
        { key: 'batchNo', label: '批次' },
        { key: 'demandNo', label: '需求单号', render: (r) => r.demandNo || (r.aggNo ? '归集 ' + r.aggNo : '-') },
        { key: 'varietyName', label: '矿种' },
        { key: 'quantity', label: '吨数', num: true },
        { label: '交货地点', render: (r) => r.deliveryPlace || '-' },
        { label: '报价截止', render: (r) => UI.fmtDateTime(r.deadline) },
        { key: 'status', label: '状态', render: (r) => UI.statusTag('INQUIRY', r.status) },
        { label: '响应', render: (r) => r.responded + '/' + r.invited },
        { label: '钢厂反馈', render: (r) => {
            const fa = r.feedbackAccept || 0, fr = r.feedbackReject || 0;
            if (!fa && !fr) return UI.h('span', { class: 'muted' }, '—');
            return UI.h('span', { class: 'inline-flex', style: 'gap:4px' },
              fa ? UI.h('span', { class: 'tag green' }, '认可 ' + fa) : null,
              fr ? UI.h('span', { class: 'tag red', style: 'cursor:pointer', title: '点击查看反馈详情',
                      onclick: () => feedbackModal(r) }, '不认可 ' + fr) : null);
          } },
        { label: '操作', render: (r) => UI.h('span', { class: 'inline-flex' },
            UI.h('button', { class: 'sm', onclick: () => detailModal(r) }, '详情'),
            ((r.feedbackAccept || 0) + (r.feedbackReject || 0)) > 0
              ? UI.h('button', { class: 'sm', onclick: () => feedbackModal(r) }, '反馈详情') : null,
            r.status !== 'FAILED' && r.status !== 'DRAFT'
              ? UI.h('button', {
                  class: (r.status === 'SENT' || r.status === 'QUOTING') && !r.revealed ? 'sm primary' : 'sm',
                  onclick: () => summaryModal(r),
                }, (r.status === 'SENT' || r.status === 'QUOTING') && !r.revealed ? '汇总报价返回钢厂' : '查看汇总')
              : null) },
      ], d.list, '暂无询价单')));
      UI.pager(pagerBox, pageNo, SIZE, d.total, (p) => { pageNo = p; load(); });
    }

    /* 钢厂反馈明细：认可/不认可 + 原因（运营端查看） */
    async function feedbackModal(r) {
      const d = await API.get('/admin/quote-inquiries/' + r.id + '/feedbacks');
      UI.modal('钢厂反馈 · ' + r.inquiryNo, UI.h('div', {},
        UI.h('div', { class: 'hint', style: 'margin-bottom:8px' },
          '归集订单：' + (r.aggNo || '-') + ' · 钢厂反馈后请结合比价结果决定是否重新发起询价'),
        UI.table([
          { key: 'companyName', label: '钢厂' },
          { label: '反馈结论', render: (row) => row.decision === 'ACCEPTED'
              ? UI.h('span', { class: 'tag green' }, '认可')
              : UI.h('span', { class: 'tag red' }, '不认可') },
          { label: '原因', render: (row) => row.reason || '-' },
          { key: 'createdAt', label: '反馈时间' },
        ], d.list || [], '暂无反馈')));
    }

    /* 发起询价：引用归集订单整单询价 + 统一询价条件 + 邀请供应商（仅归集询价）
       seedAggId：从「去询价」跳转带入时预选该归集订单 */
    async function createModal(seedAggId) {
      const d = await API.get('/admin/aggregated-orders' + API.qs({ size: 100 }));
      // OPEN=首次询价；INQUIRING=钢厂不认可等场景下可再次发起（无在途询价时）
      const aggs = (d.list || []).filter((a) => a.status === 'OPEN' || a.status === 'INQUIRING');
      if (!aggs.length) { UI.toast('暂无可发起询价的归集订单（请先在需求归集页勾选明细合并生成）', 'err'); return; }
      const seedOk = seedAggId && aggs.some((a) => String(a.id) === String(seedAggId));
      const aggSel = UI.selectField(aggs.map((a) => [String(a.id),
        a.aggNo + ' · ' + a.varietyName + ' · ' + (a.grade == null ? '-' : a.grade) + '% · '
        + a.totalQty + '吨 · ' + a.memberCount + '家钢厂']),
        String(seedOk ? seedAggId : aggs[0].id));
      const arrive = UI.input('date', new Date(Date.now() + 18 * 86400000).toISOString().slice(0, 10));
      // 报价截止默认 期望到货日 -10 天 18:00（满足"不晚于到货日前 7 天"）
      const ddlDef = new Date(new Date(arrive.value).getTime() - 10 * 86400000).toISOString();
      const ddl = UI.input('datetime-local', ddlDef.slice(0, 10) + 'T18:00');
      const minResp = UI.input('number', 2, { min: 1, max: 10 });
      const cs = (await API.get('/companies' + API.qs({ type: 'SUPPLIER', size: 100 }))).list || [];
      const supChks = cs.map((c) => {
        const chk = UI.h('input', { type: 'checkbox' });
        chk.dataset.supplierId = c.id;
        return chk;
      });
      const supLabels = cs.map((c, i) => UI.h('label',
        { style: 'display:inline-flex;align-items:center;gap:6px;margin:4px 16px 4px 0' }, supChks[i], c.companyName));
      const remark = UI.h('textarea', { rows: 2, style: 'width:100%', placeholder: '询价说明（选填）' });
      const errBox = UI.h('div', { class: 'hint', style: 'color:#c0392b' });
      const m = UI.modal('发起询价 · 归集订单统一询价', UI.h('form', { onsubmit: (e) => e.preventDefault() },
        UI.h('h3', { style: 'margin:0 0 8px' }, '选择归集订单'),
        UI.h('div', { class: 'form-row full' }, UI.h('label', { class: 'req' }, '归集订单'), aggSel),
        UI.h('h3', { style: 'margin:14px 0 8px' }, '统一询价条件'),
        UI.h('div', { class: 'form-grid' },
          UI.formRow('期望到货日', arrive, true),
          UI.formRow('报价截止', ddl, true, '至少为当前时间 +2 小时，且不晚于到货日前 7 天'),
          UI.formRow('最少响应家数', minResp)),
        UI.h('div', { class: 'form-row full' }, UI.h('label', { class: 'req' }, '邀请供应商'),
          UI.h('div', {}, supLabels)),
        UI.h('div', { class: 'form-row full' }, UI.h('label', {}, '询价说明'), remark),
        errBox), [
        UI.h('button', { class: 'primary', onclick: async () => {
          errBox.textContent = '';
          if (!aggSel.value) { errBox.textContent = '请选择归集订单'; return; }
          if (!arrive.value) { errBox.textContent = '请填写期望到货日'; return; }
          if (!ddl.value) { errBox.textContent = '请填写报价截止时间'; return; }
          const ddlVal = ddl.value.replace('T', ' ') + ':00';
          if (new Date(ddl.value).getTime() < Date.now() + 2 * 3600000) {
            errBox.textContent = '报价截止时间必须至少为当前时间 +2 小时'; return;
          }
          const supIds = supChks.filter((el) => el.checked).map((el) => Number(el.dataset.supplierId));
          if (!supIds.length) { errBox.textContent = '至少邀请一家供应商'; return; }
          try {
            const res = await API.post('/admin/quote-inquiries', {
              aggOrderId: Number(aggSel.value),
              arriveDate: arrive.value,
              deadline: ddlVal,
              minResponse: minResp.value,
              inviteSupplierIds: supIds,
              remark: remark.value.trim(),
            });
            m.close();
            UI.toast('归集订单 ' + res.aggNo + ' 询价已发出（批次 ' + res.batchNo + '）', 'ok');
            pageNo = 1; status = ''; load();
          } catch (e) { /* toast 已提示 */ }
        } }, '保存并发出'),
      ]);
    }

    async function detailModal(r) {
      const d = await API.get('/inquiries/' + r.id);
      UI.modal('询价详情 · ' + r.inquiryNo, UI.h('div', {},
        UI.kv([
          ['询价单号', r.inquiryNo],
          ['批次', r.batchNo || '-'],
          ['需求单号', r.demandNo || '-'],
          ['钢厂', r.companyName],
          ['矿种', d.varietyName || r.varietyName],
          ['吨数', r.quantity],
          ['品位(%)', r.grade == null ? '-' : r.grade],
          ['报价截止', UI.fmtDateTime(r.deadline)],
          ['期望到货', UI.fmtDate(r.expectArriveDate)],
          ['最少响应', r.minResponse + ' 家'],
          ['状态', UI.statusTag('INQUIRY', r.status)],
        ]),
        UI.h('h3', { style: 'margin:14px 0 8px' }, '邀请与响应'),
        scrollWrap(UI.table([
          { key: 'supplierName', label: '供应商' },
          { key: 'status', label: '邀请状态', render: (x) => x.status === 'INVITED' ? UI.h('span', { class: 'tag blue' }, '已邀请') : UI.h('span', { class: 'tag gray' }, x.status) },
          { key: 'quoteStatus', label: '报价状态', render: (x) => x.quoteStatus ? UI.statusTag('QUOTE', x.quoteStatus) : '-' },
        ], d.invites || [], '暂无邀请')),
        UI.h('div', { class: 'hint', style: 'margin-top:8px' }, d.notice || '')));
    }

    async function summaryModal(r) {
      const d = await API.get('/admin/quote-inquiries/' + r.id + '/summary');
      const quotes = d.quotes || [];
      const canReturn = (r.status === 'SENT' || r.status === 'QUOTING') && !r.revealed;
      const m = UI.modal((canReturn ? '汇总报价返回钢厂 · ' : '报价汇总 · ') + r.inquiryNo, UI.h('div', {},
        UI.h('div', { class: 'hint', style: 'margin-bottom:8px' },
          '钢厂 ' + (r.companyName || '-') + ' · 矿种 ' + (r.varietyName || '-') + ' · 询价 ' + r.quantity + ' 吨 · 报价 ' + quotes.length + ' 家（价格升序）'),
        scrollWrap(UI.table([
          { label: '序号', render: (x) => String(quotes.indexOf(x) + 1) },
          { key: 'quoteNo', label: '报价单号' },
          { key: 'companyName', label: '供应商' },
          { key: 'price', label: '单价(元/吨)', num: true, render: (x) => UI.fmtMoney(x.price) },
          { key: 'quantity', label: '可供数量(吨)', num: true },
          { key: 'deliveryDate', label: '到货日', render: (x) => UI.fmtDate(x.deliveryDate) },
          { key: 'payTerms', label: '付款条款', render: (x) => x.payTerms || '-' },
        ], quotes, '暂无报价')),
        canReturn ? UI.h('div', { class: 'hint', style: 'margin-top:8px' },
          '确认后报价将揭示给钢厂（钢厂端「询价报价」页即可查看比价），并站内通知钢厂。') : null),
        canReturn ? [UI.h('button', { class: 'primary', onclick: async () => {
          try {
            const res = await API.post('/admin/quote-inquiries/' + r.id + '/return', {});
            m.close();
            UI.toast('已汇总 ' + res.quoteCount + ' 家报价并推送钢厂', 'ok');
            load();
          } catch (e) { /* toast 已提示 */ }
        } }, '确认汇总并返回钢厂')] : []);
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
        { key: 'category', label: '品类', render: (r) => r.category || '-' },
        { key: 'defaultGrade', label: '默认品位(%)' },
        { key: 'unit', label: '计量单位' },
        { key: 'status', label: '状态' },
        { label: '操作', render: (r) => UI.h('button', { class: 'sm', onclick: () => categoryForm(r) }, '改品类') },
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
      const category = UI.input('text', '', { placeholder: '如 粉矿、块矿、球团、混矿' });
      const grade = UI.input('text', '', { placeholder: '如 61.5（品位百分数，纯数字）' });
      const unit = UI.input('text', '吨', { placeholder: '计量单位，默认 吨' });
      const m = UI.modal('新增品种', UI.h('form', { onsubmit: (e) => e.preventDefault() },
        UI.h('div', { class: 'form-grid' },
          UI.formRow('品种代码', code, true),
          UI.formRow('品种名称', name, true),
          UI.formRow('品类', category),
          UI.formRow('默认品位(%)', grade),
          UI.formRow('计量单位', unit))), [
        UI.h('button', { class: 'primary', onclick: async () => {
          if (!code.value.trim() || !name.value.trim()) { UI.toast('请填写品种代码与名称', 'err'); return; }
          const g = grade.value.trim();
          if (g !== '' && (isNaN(Number(g)) || Number(g) < 0 || Number(g) > 999.99)) {
            UI.toast('默认品位必须为 0～999.99 的数字（如 61.5）', 'err'); return;
          }
          try {
            await API.post('/admin/varieties', { varietyCode: code.value.trim(), varietyName: name.value.trim(), category: category.value.trim(), defaultGrade: g || null, unit: unit.value.trim() });
            m.close(); UI.toast('品种已新增', 'ok'); load();
          } catch (e) { /* toast 已提示 */ }
        } }, '保 存'),
      ]);
    }

    function categoryForm(r) {
      const category = UI.input('text', r.category || '', { placeholder: '如 粉矿、块矿、球团、混矿' });
      const m = UI.modal('改品类 · ' + r.varietyName, UI.h('form', { onsubmit: (e) => e.preventDefault() },
        UI.h('div', { class: 'form-grid' },
          UI.formRow('品类', category),
          UI.h('div', { class: 'hint' }, '品类用于需求归集列表展示，如：粉矿/块矿/精粉/球团/混矿'))), [
        UI.h('button', { class: 'primary', onclick: async () => {
          try {
            await API.put('/admin/varieties/' + r.id, { category: category.value.trim() });
            m.close(); UI.toast('品类已更新', 'ok'); load();
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

  /* -------- 合同管理 / 运输调度 / 对账结算：菜单占位（功能建设中） -------- */
  const placeholder = (title, desc) => async function (page) {
    page.appendChild(UI.h('div', { class: 'card' }, [
      UI.h('div', { class: 'card-title' }, title),
      UI.h('div', { class: 'muted', style: 'padding:24px 0;text-align:center' }, desc),
    ]));
  };
  /* -------- 合同管理：合同核验 + 合同台账 -------- */
  Pages.contract_admin = async function (page) {
    const SIZE = 10;
    let pageNo = 1;
    let tab = 'verify'; // verify=合同核验 ledger=合同台账
    let platStatus = '';
    let rows = [];
    const scrollWrap = (node, style) => UI.h('div', { class: 'table-scroll-wrap', style }, node);
    const MODE_LABEL = { SEA: '海运', RAIL: '铁运', ROAD: '汽运', MULTIMODAL: '多式联运' };

    const TABS = [
      ['verify', '合同核验'],
      ['ledger', '合同台账'],
    ];
    const tabBar = UI.h('div', { class: 'tab-bar' },
      ...TABS.map(([key, label]) => UI.h('button', {
        class: 'tab-btn', 'data-tab': key,
        onclick: () => { tab = key; pageNo = 1; platStatus = ''; render(); },
      }, label)));
    const filterBox = UI.h('div', {});
    const listBox = UI.h('div', {});
    const pagerBox = UI.h('div', {});
    page.appendChild(UI.h('div', { class: 'card' },
      UI.h('div', { class: 'toolbar' },
        UI.h('h3', { style: 'margin:0;border:none;padding:0' }, '合同管理'),
        UI.h('div', { class: 'spacer' }),
        filterBox),
      tabBar, listBox, pagerBox));
    render();

    function syncTabs() {
      page.querySelectorAll('.tab-btn').forEach((b) => {
        b.classList.toggle('active', b.getAttribute('data-tab') === tab);
      });
    }

    async function render() {
      syncTabs();
      filterBox.innerHTML = '';
      pagerBox.innerHTML = '';
      if (tab === 'verify') {
        filterBox.appendChild(UI.statusFilter('PLAT', (v) => { platStatus = v; pageNo = 1; loadVerify(); }));
        await loadVerify();
      } else {
        await loadLedger();
      }
    }

    function platCell(r) {
      return r.platStatus
        ? UI.statusTag('PLAT', r.platStatus)
        : UI.h('span', { class: 'muted' }, '签署中');
    }

    function fileCell(r) {
      if (!r.fileUrl) return UI.h('span', { class: 'muted' }, '未上传');
      const fid = String(r.fileUrl).split(',')[0];
      return UI.h('button', { class: 'sm', onclick: () => API.downloadFile(fid) }, '下载扫描件');
    }

    async function loadVerify() {
      const d = await API.get('/admin/contracts' + API.qs({ platStatus, page: pageNo, size: SIZE }));
      rows = d.list || [];
      listBox.innerHTML = '';
      listBox.appendChild(scrollWrap(UI.table([
        { label: '序号', render: (r) => String((pageNo - 1) * SIZE + rows.indexOf(r) + 1) },
        { key: 'contractNo', label: '合同号' },
        { key: 'orderNo', label: '订单号' },
        { key: 'buyerName', label: '需方(钢厂)' },
        { key: 'supplierName', label: '供方(供应商)' },
        { label: '需方签署', render: (r) => (r.buyerSignAt ? UI.fmtDateTime(r.buyerSignAt) : '-') },
        { label: '供方签署', render: (r) => (r.supplierSignAt ? UI.fmtDateTime(r.supplierSignAt) : '-') },
        { label: '扫描件', render: fileCell },
        { label: '平台状态', render: platCell },
        { label: '操作', render: (r) => r.platStatus === 'PENDING'
          ? UI.h('button', { class: 'sm primary', onclick: () => verifyModal(r) }, '核验')
          : UI.h('button', { class: 'sm', onclick: () => detailModal(r) }, '详情') },
      ], rows, '暂无合同')));
      UI.pager(pagerBox, pageNo, SIZE, d.total, (p) => { pageNo = p; loadVerify(); });
    }

    async function loadLedger() {
      const d = await API.get('/admin/contracts' + API.qs({ platStatus: 'CONFIRMED', page: pageNo, size: SIZE }));
      rows = d.list || [];
      listBox.innerHTML = '';
      listBox.appendChild(scrollWrap(UI.table([
        { label: '序号', render: (r) => String((pageNo - 1) * SIZE + rows.indexOf(r) + 1) },
        { key: 'contractNo', label: '合同号' },
        { key: 'orderNo', label: '订单号' },
        { key: 'buyerName', label: '需方(钢厂)' },
        { key: 'supplierName', label: '供方(供应商)' },
        { key: 'status', label: '合同状态', render: (r) => UI.statusTag('CONTRACT', r.status) },
        { label: '平台核验时间', render: (r) => (r.platConfirmAt ? UI.fmtDateTime(r.platConfirmAt) : '-') },
        { label: '关联运单', render: (r) => String(r.waybillCount || 0) + ' 单' },
        { label: '扫描件', render: fileCell },
        { label: '操作', render: (r) => UI.h('button', { class: 'sm', onclick: () => waybillModal(r) }, '查看运单') },
      ], rows, '暂无已确认合同')));
      UI.pager(pagerBox, pageNo, SIZE, d.total, (p) => { pageNo = p; loadLedger(); });
    }

    function verifyModal(r) {
      const approve = UI.selectField(
        [['true', '确认（核验通过，合同生效入台账）'], ['false', '不确认（退回上传方）']], 'true');
      const remark = UI.h('textarea', { rows: 2, style: 'width:100%', placeholder: '退回原因（不确认时必填）' });
      const m = UI.modal('合同核验 · ' + r.contractNo, UI.h('form', { onsubmit: (e) => e.preventDefault() },
        UI.h('h3', { style: 'margin:0 0 8px' }, '合同信息'),
        UI.kv([
          ['合同号', r.contractNo],
          ['订单号', r.orderNo],
          ['需方(钢厂)', r.buyerName],
          ['供方(供应商)', r.supplierName],
          ['签署方式', r.signatureType === 'PLATFORM_CONFIRM' ? '平台上传扫描件' : (r.signatureType || '-')],
          ['需方签署', r.buyerSignAt ? UI.fmtDateTime(r.buyerSignAt) : '-'],
          ['供方签署', r.supplierSignAt ? UI.fmtDateTime(r.supplierSignAt) : '-'],
          ['扫描件', r.fileUrl ? '已上传（列表页可下载）' : '未上传'],
        ]),
        UI.h('h3', { style: 'margin:14px 0 8px' }, '核验结论'),
        UI.h('div', { class: 'form-grid' },
          UI.formRow('核验结论', approve, true),
          UI.h('div', { class: 'form-row full' }, UI.h('label', {}, '退回原因'), remark))), [
        UI.h('button', { class: 'primary', onclick: async () => {
          if (approve.value === 'false' && !remark.value.trim()) { UI.toast('不确认时必须填写退回原因', 'err'); return; }
          try {
            await API.put('/admin/contracts/' + r.id + '/verify', { approve: approve.value, remark: remark.value.trim() });
            m.close();
            UI.toast(approve.value === 'true' ? '合同已生效并纳入台账' : '已退回上传方', 'ok');
            loadVerify();
          } catch (e) { /* toast 已提示 */ }
        } }, '提 交'),
      ]);
    }

    function detailModal(r) {
      UI.modal('合同详情 · ' + r.contractNo, UI.h('div', {},
        UI.kv([
          ['合同号', r.contractNo],
          ['订单号', r.orderNo],
          ['需方(钢厂)', r.buyerName],
          ['供方(供应商)', r.supplierName],
          ['合同状态', UI.statusTag('CONTRACT', r.status)],
          ['平台状态', r.platStatus ? UI.statusTag('PLAT', r.platStatus) : '-'],
          ['需方签署', r.buyerSignAt ? UI.fmtDateTime(r.buyerSignAt) : '-'],
          ['供方签署', r.supplierSignAt ? UI.fmtDateTime(r.supplierSignAt) : '-'],
          ['平台核验时间', r.platConfirmAt ? UI.fmtDateTime(r.platConfirmAt) : '-'],
          ['退回原因', r.platRemark || '-', true],
          ['关联运单', String(r.waybillCount || 0) + ' 单'],
        ])));
    }

    async function waybillModal(r) {
      const d = await API.get('/admin/waybills-ops' + API.qs({ orderId: r.orderId, size: 50 }));
      const items = d.list || [];
      UI.modal('关联运单 · ' + r.contractNo, UI.h('div', {},
        items.length
          ? scrollWrap(UI.table([
              { key: 'waybillNo', label: '运单号' },
              { key: 'segmentNo', label: '分段' },
              { label: '运输方式', render: (w) => MODE_LABEL[w.transportMode] || w.transportMode || '-' },
              { key: 'departPlace', label: '起运地', render: (w) => w.departPlace || '-' },
              { key: 'arrivePlace', label: '到达地', render: (w) => w.arrivePlace || '-' },
              { key: 'planQty', label: '计划量(吨)', num: true },
              { key: 'carrierName', label: '承运商', render: (w) => w.carrierName || '-' },
              { key: 'status', label: '状态', render: (w) => UI.statusTag('WAYBILL', w.status) },
            ], items, '暂无运单'))
          : UI.h('div', { class: 'empty' }, '该订单暂无运单')));
    }
  };
  /* -------- 运输调度：物流调度 + 在途监控 -------- */
  Pages.logistics_dispatch = async function (page) {
    const SIZE = 10;
    let pageNo = 1;
    let tab = 'dispatch'; // dispatch=物流调度 monitor=在途监控
    let wbStatus = '';
    let orderRows = [];
    let wbRows = [];
    let carriers = null;
    const scrollWrap = (node, style) => UI.h('div', { class: 'table-scroll-wrap', style }, node);
    const MODE_LABEL = { SEA: '海运', RAIL: '铁运', ROAD: '汽运', MULTIMODAL: '多式联运' };
    const ORG_LABEL = { SELF: '钢厂自提', PLATFORM: '平台配送' };
    const numInput = (attrs) => UI.h('input', Object.assign({ type: 'number', min: '0' }, attrs || {}));

    const TABS = [
      ['dispatch', '物流调度'],
      ['monitor', '在途监控'],
    ];
    const tabBar = UI.h('div', { class: 'tab-bar' },
      ...TABS.map(([key, label]) => UI.h('button', {
        class: 'tab-btn', 'data-tab': key,
        onclick: () => { tab = key; pageNo = 1; wbStatus = ''; render(); },
      }, label)));
    const filterBox = UI.h('div', {});
    const statsBox = UI.h('div', {});
    const listBox = UI.h('div', {});
    const pagerBox = UI.h('div', {});
    page.appendChild(UI.h('div', { class: 'card dispatch-card' },
      UI.h('div', { class: 'toolbar' },
        UI.h('h3', { style: 'margin:0;border:none;padding:0' }, '运输调度'),
        UI.h('div', { class: 'spacer' }),
        filterBox),
      tabBar, statsBox, listBox, pagerBox));

    /* ---- 保税进出库存分析表（按订单关联，可编辑演示表）：点击订单行显示对应表格 ---- */
    function defaultGrid() {
      const days = ['9/9', '9/10', '9/11', '9/12', '9/13', '9/14', '9/15', '9/16', '9/17', '9/18', '9/19'];
      const spec = [
        ['出港', '汽运', ['汽运出港量', '汽运累计出港量', '汽运库存量']],
        ['出港', '火运', ['火运出港量', '火运累计出港量', '火运库存量', '火运匹配等耗出港量']],
        ['出港', '总计', ['总出港量', '未来会集量总计']],
        ['进港', '汽运', ['计划到港量', '实际到港量', '计划累计到港量', '实际累计到港量', '实际与计划差额', '实际与计划累计差额']],
        ['进港', '火运', ['计划到港量', '实际到港量', '计划累计到港量', '实际累计到港量', '火运计划进港总量']],
        ['进港', '总计', ['计划进港总量', '实际进港总量', '实际与计划差额']],
        ['出厂', '汽运出厂', ['计划出厂量', '实际出厂量', '计划累计出厂量', '实际累计出厂量', '实际与计划差额']],
      ];
      return {
        title: '保税进出库存分析表',
        cols: days.slice(),
        rows: spec.flatMap(([g, s, labels]) => labels.map((label) => ({ g, s, label, cells: days.map(() => '') }))),
        footer: { label: '保税库存状态', value: '' },
      };
    }
    let gridOrder = null; // 当前展示分析表的订单
    let grid = null;
    function gridKey(orderId) { return 'mine_dispatch_analysis_v2_' + orderId; }
    function loadGrid(orderId) {
      try {
        const m = JSON.parse(localStorage.getItem(gridKey(orderId)) || 'null');
        if (m && Array.isArray(m.cols) && Array.isArray(m.rows)) return m;
      } catch (e) { /* 使用默认结构 */ }
      return defaultGrid();
    }
    function saveGrid() {
      if (!gridOrder) return;
      try { localStorage.setItem(gridKey(gridOrder.id), JSON.stringify(grid)); } catch (e) { /* 忽略 */ }
    }
    function selectOrder(r) {
      gridOrder = r;
      grid = loadGrid(r.id);
      renderGrid();
      // 详情视图：只显示分析表，隐藏下方订单列表
      listBox.style.display = 'none';
      pagerBox.style.display = 'none';
      listBox.innerHTML = '';
    }
    function closeAnalysis() {
      gridOrder = null;
      grid = null;
      statsBox.innerHTML = '';
      listBox.style.display = '';
      pagerBox.style.display = '';
      render();
    }
    function gridSpans(rows) {
      const g = new Array(rows.length).fill(0);
      const s = new Array(rows.length).fill(0);
      let i = 0;
      while (i < rows.length) {
        let j = i;
        while (j < rows.length && rows[j].g === rows[i].g) j++;
        g[i] = j - i;
        let k = i;
        while (k < j && rows[k].s === rows[i].s) k++;
        s[i] = k - i;
        i = j;
      }
      return { g, s };
    }
    function editCell(node, fn) {
      node.setAttribute('contenteditable', 'true');
      node.addEventListener('input', () => { fn(node.textContent.trim()); saveGrid(); });
      return node;
    }
    function delBtn(title, fn, cls) {
      return UI.h('span', { class: 'cell-x ' + (cls || ''), title, contenteditable: 'false',
        onclick: (e) => { e.preventDefault(); e.stopPropagation(); fn(); } }, '×');
    }
    function renderGrid() {
      statsBox.innerHTML = '';
      if (!gridOrder || !grid) return;
      const sp = gridSpans(grid.rows);
      const table = UI.h('table', { class: 'grid analysis-grid' },
        UI.h('thead', {}, UI.h('tr', {},
          UI.h('th', { rowspan: '2', style: 'width:64px' }, '分组'),
          UI.h('th', { rowspan: '2', style: 'width:84px' }, '子类'),
          UI.h('th', { rowspan: '2', style: 'width:160px' }, '项目'),
          ...grid.cols.map((c, ci) => UI.h('th', { class: 'col-head' },
            editCell(UI.h('span', { class: 'head-text' }, c), (v) => { grid.cols[ci] = v; }),
            delBtn('删除该列', () => {
              grid.cols.splice(ci, 1);
              grid.rows.forEach((r) => r.cells.splice(ci, 1));
              renderGrid(); saveGrid();
            }))),
          UI.h('th', { rowspan: '2', style: 'width:40px' }, '删行'))),
        UI.h('tbody', {},
          ...grid.rows.map((r, ri) => {
            const tr = UI.h('tr', {});
            if (sp.g[ri]) tr.appendChild(editCell(
              UI.h('td', { rowspan: String(sp.g[ri]), class: 'grp' }, r.g || ''), (v) => { r.g = v; }));
            if (sp.s[ri]) tr.appendChild(editCell(
              UI.h('td', { rowspan: String(sp.s[ri]), class: 'grp' }, r.s || ''), (v) => { r.s = v; }));
            tr.appendChild(editCell(UI.h('td', { class: 'row-label' }, r.label || ''), (v) => { r.label = v; }));
            grid.cols.forEach((_, ci) => tr.appendChild(editCell(
              UI.h('td', { class: 'cell' }, r.cells[ci] || ''), (v) => { r.cells[ci] = v; })));
            tr.appendChild(UI.h('td', { class: 'row-op' },
              delBtn('删除该行', () => { grid.rows.splice(ri, 1); renderGrid(); saveGrid(); }, 'row-x')));
            return tr;
          }),
          UI.h('tr', {},
            editCell(UI.h('td', { colspan: '3', class: 'grp' }, grid.footer.label || ''), (v) => { grid.footer.label = v; }),
            editCell(UI.h('td', { colspan: String(grid.cols.length) }, grid.footer.value || ''), (v) => { grid.footer.value = v; }),
            UI.h('td', { class: 'row-op' }))));
      statsBox.appendChild(UI.h('div', { class: 'grid-tools' },
        UI.h('span', { class: 'grid-order-tag' }, '关联订单：' + (gridOrder.orderNo || '')),
        UI.h('button', { class: 'sm', onclick: () => {
          grid.rows.push({ g: '', s: '', label: '', cells: grid.cols.map(() => '') });
          renderGrid(); saveGrid();
        } }, '添加行'),
        UI.h('button', { class: 'sm', onclick: () => {
          grid.cols.push('新列');
          grid.rows.forEach((r) => r.cells.push(''));
          renderGrid(); saveGrid();
        } }, '添加列'),
        UI.h('button', { class: 'sm', onclick: async () => {
          if (!(await UI.confirmBox('恢复默认表格结构？当前修改将全部清除。'))) return;
          grid = defaultGrid(); renderGrid(); saveGrid();
        } }, '恢复默认'),
        UI.h('button', { class: 'sm', onclick: closeAnalysis }, '关闭分析')));
      statsBox.appendChild(UI.h('div', { class: 'grid-title-wrap' },
        editCell(UI.h('div', { class: 'grid-title' }, (grid.title || '保税进出库存分析表') + ' · ' + (gridOrder.orderNo || '')),
          (v) => { grid.title = v.replace(/\s*·\s*DD-\S+$/, ''); }),
        scrollWrap(table, 'border:1px solid #cfd4dc')));
    }
    if (!document.getElementById('analysis-grid-style')) {
      document.head.appendChild(UI.h('style', { id: 'analysis-grid-style' }, `
        .analysis-grid { width: 100%; }
        .analysis-grid th, .analysis-grid td { border: 1px solid #cfd4dc; text-align: center; padding: 4px 6px; white-space: normal; }
        .analysis-grid td.grp { background: #f6f7fa; font-weight: 600; }
        .analysis-grid [contenteditable='true']:focus { outline: 2px solid #1a5cb0; outline-offset: -2px; background: #f0f6ff; }
        .analysis-grid .cell-x { display: inline-block; margin-left: 4px; width: 14px; height: 14px; line-height: 12px;
          text-align: center; border-radius: 50%; background: #fdeaea; color: #d64545; cursor: pointer;
          font-size: 11px; opacity: 0; transition: opacity .15s; }
        .analysis-grid th:hover .cell-x, .analysis-grid tr:hover .row-x { opacity: 1; }
        .grid-title { text-align: center; font-weight: 700; font-size: 15px; padding: 6px 0 10px; }
        .grid-tools { display: flex; gap: 8px; justify-content: flex-end; align-items: center; margin-bottom: 8px; }
        .grid-order-tag { color: var(--label-2, #6e6e73); font-size: 13px; margin-right: auto; }
        .dispatch-card tr.row-selected td { background: #eaf2fd; }
        .dispatch-card table.grid { border-collapse: collapse; }
        .dispatch-card table.grid th, .dispatch-card table.grid td { border: 1px solid var(--gray-4); }
      `));
    }
    render();

    function syncTabs() {
      page.querySelectorAll('.tab-btn').forEach((b) => {
        b.classList.toggle('active', b.getAttribute('data-tab') === tab);
      });
    }

    async function render() {
      syncTabs();
      filterBox.innerHTML = '';
      pagerBox.innerHTML = '';
      statsBox.innerHTML = '';
      listBox.innerHTML = '';
      listBox.style.display = '';
      pagerBox.style.display = '';
      if (tab === 'dispatch') {
        if (gridOrder) {
          // 详情视图：只显示该订单的分析表
          renderGrid();
          listBox.style.display = 'none';
          pagerBox.style.display = 'none';
        } else {
          await loadOrders();
        }
      } else {
        filterBox.appendChild(UI.statusFilter('WAYBILL', (v) => { wbStatus = v; pageNo = 1; loadWaybills(); }));
        await loadWaybills();
      }
    }

    async function loadCarriers() {
      if (carriers) return;
      const d = await API.get('/admin/companies' + API.qs({ size: 100 }));
      carriers = (d.list || []).filter((c) => String(c.companyTypes || '').split(',').indexOf('LOGISTICS') >= 0
        && c.status === 'ENABLED');
    }
    function carrierField(withEmptyLabel) {
      const opts = [[withEmptyLabel ? '' : '', withEmptyLabel || '暂不指派（创建后另行指派）']]
        .concat((carriers || []).map((c) => [String(c.id), c.companyName]));
      return UI.selectField(opts, '');
    }

    async function loadOrders() {
      const d = await API.get('/admin/logistics-orders' + API.qs({ page: pageNo, size: SIZE }));
      orderRows = d.list || [];
      listBox.innerHTML = '';
      const tbl = UI.table([
        { label: '序号', render: (r) => String((pageNo - 1) * SIZE + orderRows.indexOf(r) + 1) },
        { key: 'orderNo', label: '订单号' },
        { key: 'buyerName', label: '需方(钢厂)' },
        { key: 'supplierName', label: '供方' },
        { key: 'quantity', label: '订单量(吨)', num: true },
        { key: 'contractNo', label: '合同号', render: (r) => r.contractNo || '-' },
        { label: '物流方案', render: (r) => r.planNo
          ? r.planNo + '（' + (ORG_LABEL[r.orgMode] || r.orgMode) + '）'
          : UI.h('span', { class: 'muted' }, '未制定') },
        { label: '运单概况', render: (r) => r.planId
          ? String(r.waybillCount || 0) + ' 段 / 已排 ' + (r.plannedQty || 0) + ' 吨'
          : '-' },
        { label: '操作', render: (r) => r.planId
          ? UI.h('button', { class: 'sm primary', onclick: (e) => { e.stopPropagation(); waybillCreateModal(r); } }, '新增分段运单')
          : UI.h('button', { class: 'sm primary', onclick: (e) => { e.stopPropagation(); planModal(r); } }, '制定方案') },
      ], orderRows, '暂无履约中订单（合同生效后进入调度）');
      listBox.appendChild(scrollWrap(tbl));
      // 点击订单行 → 显示该订单关联的保税进出库存分析表
      tbl.querySelectorAll('tbody tr').forEach((tr, i) => {
        const r = orderRows[i];
        if (!r) return;
        tr.style.cursor = 'pointer';
        tr.title = '点击查看该订单的保税进出库存分析表';
        if (gridOrder && gridOrder.id === r.id) tr.classList.add('row-selected');
        tr.addEventListener('click', () => selectOrder(r));
      });
      UI.pager(pagerBox, pageNo, SIZE, d.total, (p) => { pageNo = p; loadOrders(); });
    }

    function planModal(r) {
      const orgMode = UI.selectField([['PLATFORM', '平台配送'], ['SELF', '钢厂自提']], 'PLATFORM');
      const remark = UI.h('input', { style: 'width:100%', placeholder: '方案说明（可选）' });
      const m = UI.modal('制定物流方案 · ' + r.orderNo, UI.h('form', { onsubmit: (e) => e.preventDefault() },
        UI.kv([
          ['订单号', r.orderNo],
          ['需方(钢厂)', r.buyerName],
          ['订单量', r.quantity + ' 吨'],
          ['合同号', r.contractNo || '-'],
        ]),
        UI.h('div', { class: 'form-grid' },
          UI.formRow('组织方式', orgMode, true),
          UI.h('div', { class: 'form-row full' }, UI.h('label', {}, '方案说明'), remark))), [
        UI.h('button', { class: 'primary', onclick: async () => {
          try {
            await API.post('/admin/logistics-plans', { orderId: r.id, orgMode: orgMode.value, remark: remark.value.trim() || undefined });
            m.close();
            UI.toast('方案已制定并告知钢厂（钢厂无需操作，可在履约跟踪查看）', 'ok');
            loadOrders();
          } catch (e) { /* toast 已提示 */ }
        } }, '提 交'),
      ]);
    }

    async function waybillCreateModal(r) {
      await loadCarriers();
      const remain = Math.max(0, (r.quantity || 0) - (r.plannedQty || 0));
      const segNo = numInput({ value: String((r.waybillCount || 0) + 1), min: '1', style: 'width:100%' });
      const mode = UI.selectField(Object.entries(MODE_LABEL), 'SEA');
      const departPlace = UI.h('input', { style: 'width:100%', placeholder: '如：日照港' });
      const arrivePlace = UI.h('input', { style: 'width:100%', placeholder: '如：钢厂厂区' });
      const departDate = UI.h('input', { type: 'date' });
      const arriveDate = UI.h('input', { type: 'date' });
      const planQty = numInput({ value: String(remain || ''), step: '0.001', style: 'width:100%' });
      const carrier = carrierField();
      const freight = numInput({ step: '0.01', placeholder: '运费总额(元，可选)' });
      const vehicleNo = UI.h('input', { placeholder: '车船号（可选）' });
      const deviationReason = UI.h('textarea', { rows: 2, style: 'width:100%', placeholder: '分段合计与订单量偏差>5%时必填' });
      const m = UI.modal('新增分段运单 · ' + r.orderNo, UI.h('form', { onsubmit: (e) => e.preventDefault() },
        UI.kv([
          ['物流方案', r.planNo + '（' + (ORG_LABEL[r.orgMode] || r.orgMode) + '）'],
          ['订单量', r.quantity + ' 吨'],
          ['已排量', (r.plannedQty || 0) + ' 吨'],
          ['剩余可排', remain + ' 吨'],
        ]),
        UI.h('div', { class: 'form-grid' },
          UI.formRow('分段号', segNo, true),
          UI.formRow('运输方式', mode, true),
          UI.formRow('起运地', departPlace, true),
          UI.formRow('到达地', arrivePlace, true),
          UI.formRow('计划发运日', departDate, true),
          UI.formRow('计划到达日', arriveDate, true),
          UI.formRow('计划量(吨)', planQty, true),
          UI.formRow('承运商匹配', carrier),
          UI.formRow('运费(元)', freight),
          UI.formRow('车船号', vehicleNo),
          UI.h('div', { class: 'form-row full' }, UI.h('label', {}, '偏差说明'), deviationReason))), [
        UI.h('button', { class: 'primary', onclick: async () => {
          const qty = parseFloat(planQty.value);
          if (!qty || qty <= 0) { UI.toast('请填写计划量（吨）', 'err'); return; }
          if (!departDate.value || !arriveDate.value) { UI.toast('请选择计划发运/到达日期', 'err'); return; }
          try {
            const res = await API.post('/admin/logistics-plans/' + r.planId + '/waybills', {
              segmentNo: parseInt(segNo.value, 10) || 1,
              transportMode: mode.value,
              departPlace: departPlace.value.trim() || undefined,
              arrivePlace: arrivePlace.value.trim() || undefined,
              planDepartDate: departDate.value,
              planArriveDate: arriveDate.value,
              planQty: qty,
              carrierId: carrier.value ? parseInt(carrier.value, 10) : undefined,
              freight: freight.value ? parseFloat(freight.value) : undefined,
              vehicleNo: vehicleNo.value.trim() || undefined,
              deviationReason: deviationReason.value.trim() || undefined,
            });
            m.close();
            UI.toast(carrier.value ? '运单已创建并指派承运商（待接单）' : '运单已创建（待指派承运商）', 'ok');
            loadOrders();
          } catch (e) { /* toast 已提示 */ }
        } }, '提 交'),
      ]);
    }

    async function loadWaybills() {
      const d = await API.get('/admin/waybills-ops' + API.qs({ status: wbStatus, page: pageNo, size: SIZE }));
      wbRows = d.list || [];
      listBox.innerHTML = '';
      listBox.appendChild(scrollWrap(UI.table([
        { label: '序号', render: (w) => String((pageNo - 1) * SIZE + wbRows.indexOf(w) + 1) },
        { key: 'waybillNo', label: '运单号' },
        { key: 'orderNo', label: '订单号' },
        { key: 'buyerName', label: '需方(钢厂)' },
        { key: 'segmentNo', label: '分段' },
        { label: '运输方式', render: (w) => MODE_LABEL[w.transportMode] || w.transportMode || '-' },
        { label: '起讫', render: (w) => (w.departPlace || '-') + ' → ' + (w.arrivePlace || '-') },
        { key: 'planQty', label: '计划量(吨)', num: true },
        { key: 'carrierName', label: '承运商', render: (w) => w.carrierName || '-' },
        { label: '计划发运', render: (w) => UI.fmtDate(w.planDepartDate) },
        { label: '实际节点', render: (w) => w.actualArriveAt
          ? '到达 ' + UI.fmtDateTime(w.actualArriveAt)
          : (w.actualDepartAt ? '发运 ' + UI.fmtDateTime(w.actualDepartAt) : '-') },
        { key: 'status', label: '状态', render: (w) => UI.statusTag('WAYBILL', w.status) },
        { label: '操作', render: opCell },
      ], wbRows, '暂无运单')));
      UI.pager(pagerBox, pageNo, SIZE, d.total, (p) => { pageNo = p; loadWaybills(); });
    }

    function opCell(w) {
      if (w.status === 'PENDING_ASSIGN') {
        return UI.h('button', { class: 'sm primary', onclick: () => assignModal(w) }, '指派承运商');
      }
      if (w.status === 'PENDING_DEPART') {
        return UI.h('button', { class: 'sm primary', onclick: () => advanceModal(w, 'DEPART') }, '确认发运');
      }
      if (w.status === 'IN_TRANSIT') {
        return UI.h('button', { class: 'sm primary', onclick: () => advanceModal(w, 'ARRIVE') }, '确认到达');
      }
      if (w.status === 'ARRIVED') {
        return UI.h('button', { class: 'sm primary', onclick: async () => {
          if (!(await UI.confirmBox('确认代钢厂签收运单 ' + w.waybillNo + '？'))) return;
          try {
            await API.put('/admin/waybills/' + w.id + '/advance', { action: 'SIGN' });
            UI.toast('已签收', 'ok');
            loadWaybills();
          } catch (e) { /* toast 已提示 */ }
        } }, '代签收');
      }
      return UI.h('button', { class: 'sm', onclick: () => detailModal(w) }, '详情');
    }

    async function assignModal(w) {
      await loadCarriers();
      const carrier = carrierField('请选择承运商');
      const m = UI.modal('指派承运商 · ' + w.waybillNo, UI.h('form', { onsubmit: (e) => e.preventDefault() },
        UI.kv([
          ['运单号', w.waybillNo],
          ['订单号', w.orderNo],
          ['分段', '第 ' + w.segmentNo + ' 段'],
          ['起讫', (w.departPlace || '-') + ' → ' + (w.arrivePlace || '-')],
          ['计划量', w.planQty + ' 吨'],
        ]),
        UI.h('div', { class: 'form-grid' },
          UI.formRow('承运商', carrier, true))), [
        UI.h('button', { class: 'primary', onclick: async () => {
          if (!carrier.value) { UI.toast('请选择承运商', 'err'); return; }
          try {
            await API.put('/admin/waybills/' + w.id + '/assign', { carrierId: parseInt(carrier.value, 10) });
            m.close();
            UI.toast('已指派，待承运商接单', 'ok');
            loadWaybills();
          } catch (e) { /* toast 已提示 */ }
        } }, '提 交'),
      ]);
    }

    function advanceModal(w, action) {
      const isDepart = action === 'DEPART';
      const occur = UI.h('input', { type: 'datetime-local' });
      const actualQty = numInput({ value: String(w.planQty || ''), step: '0.001', style: 'width:100%' });
      const m = UI.modal((isDepart ? '确认发运' : '确认到达') + ' · ' + w.waybillNo,
        UI.h('form', { onsubmit: (e) => e.preventDefault() },
          UI.kv([
            ['运单号', w.waybillNo],
            ['订单号', w.orderNo],
            ['承运商', w.carrierName || '-'],
            ['起讫', (w.departPlace || '-') + ' → ' + (w.arrivePlace || '-')],
          ]),
          UI.h('div', { class: 'form-grid' },
            UI.formRow(isDepart ? '实际发运时间' : '实际到达时间', occur),
            isDepart ? UI.formRow('实际发运量(吨)', actualQty) : null)), [
        UI.h('button', { class: 'primary', onclick: async () => {
          try {
            await API.put('/admin/waybills/' + w.id + '/advance', {
              action,
              occurTime: occur.value ? occur.value.replace('T', ' ') + (occur.value.length === 16 ? ':00' : '') : undefined,
              actualQty: isDepart && actualQty.value ? parseFloat(actualQty.value) : undefined,
            });
            m.close();
            UI.toast(isDepart ? '已发运（钢厂端可见在途节点）' : '已到达', 'ok');
            loadWaybills();
          } catch (e) { /* toast 已提示 */ }
        } }, '提 交'),
      ]);
    }

    function detailModal(w) {
      UI.modal('运单详情 · ' + w.waybillNo, UI.h('div', {},
        UI.kv([
          ['运单号', w.waybillNo],
          ['订单号', w.orderNo],
          ['合同号', w.contractNo || '-'],
          ['需方(钢厂)', w.buyerName],
          ['供方', w.supplierName],
          ['分段', '第 ' + w.segmentNo + ' 段'],
          ['运输方式', MODE_LABEL[w.transportMode] || w.transportMode || '-'],
          ['起讫', (w.departPlace || '-') + ' → ' + (w.arrivePlace || '-')],
          ['计划量', w.planQty + ' 吨'],
          ['承运商', w.carrierName || '-'],
          ['计划发运', UI.fmtDate(w.planDepartDate)],
          ['计划到达', UI.fmtDate(w.planArriveDate)],
          ['实际发运', w.actualDepartAt ? UI.fmtDateTime(w.actualDepartAt) : '-'],
          ['实际到达', w.actualArriveAt ? UI.fmtDateTime(w.actualArriveAt) : '-'],
          ['状态', UI.statusTag('WAYBILL', w.status)],
        ])));
    }
  };
  Pages.settlement_stats = placeholder('对账结算', '功能建设中：结算统计看板');
})();
