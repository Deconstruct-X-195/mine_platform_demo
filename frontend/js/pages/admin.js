/* 运营后台（PRD 4.10/FR-10）：仪表盘/企业审核/基础数据/订单管理/运输调度/预警/字典/日志 */
(function () {
  window.Pages = window.Pages || {};
  /* 跨页交接：详情页「保税库存分析表」→ 返回运输调度列表页后直接打开对应分析表 */
  let pendingGridOrder = null;

  /* 吨数统一两位小数（后端数值可能带 3 位小数） */
  function fmtQty(v) {
    if (v == null || v === '') return '-';
    const n = Number(v);
    return isNaN(n) ? String(v) : n.toFixed(2);
  }

  /* 报价详情：展示供应商报价单全部填写信息（运营端，不受密封期限制） */
  async function quoteDetailModal(iid, x) {
    try {
      const d = await API.get('/admin/quote-inquiries/' + iid + '/summary');
      const q = (d.quotes || []).find((z) => z.id === x.quoteId) || {};
      /* 单价：与供应商报价模式一致（「港口现货价格」仅固定字样），直接展示报价存储的方向与上下浮金额，
         不关联品种当日港口价格数据 */
      let priceBox = UI.h('span', { class: 'hint' }, '-');
      if (q.priceSign) {
        const fAbs = q.priceFloat != null ? Math.abs(Number(q.priceFloat)) : null;
        if (fAbs === 0) {
          /* 上下浮=0（平价）：单价仅「港口现货价格」字样，不显示 ±0 */
          priceBox = UI.h('input', { value: '港口现货价格', disabled: true,
            style: 'width:150px;background:#f5f5f7;color:var(--label-2)' });
        } else {
          priceBox = UI.h('span', { class: 'inline-flex', style: 'gap:8px;flex-wrap:nowrap;align-items:center' },
            UI.h('input', { value: '港口现货价格', disabled: true,
              style: 'width:150px;background:#f5f5f7;color:var(--label-2)' }),
            UI.h('span', { style: 'padding:0 4px;font-weight:600' }, q.priceSign),
            UI.h('input', { value: q.priceFloat != null ? UI.fmtMoney(fAbs) : '', disabled: true,
              style: 'width:110px;background:#f5f5f7' }));
        }
      } else if (q.price != null) {
        priceBox = UI.h('span', { class: 'hint' }, '单价 ' + UI.fmtMoney(q.price) + ' 元/湿吨');
      }
      UI.modal('报价详情 · ' + (q.quoteNo || ''), UI.h('div', {},
        UI.h('div', { class: 'form-row' },
          UI.h('label', { class: 'req' }, '单价(元/湿吨)'), priceBox),
        UI.kv([
          ['报价单号', q.quoteNo || '-'],
          ['供应商', q.companyName || x.supplierName || '-'],
          ['矿种', q.varietyName || (d.inquiry && d.inquiry.varietyName) || '-'],
          ['产地', q.origin || '-'],
          ['品位(%)', q.grade != null ? String(q.grade) : '-'],
          ['含税/不含税', ({ INC_TAX: '含税', EX_TAX: '不含税' }[q.taxType]) || '-'],
          ['运费(元/湿吨)', q.freightPrice != null ? UI.fmtMoney(q.freightPrice) : '-'],
          ['可供数量(湿吨)', q.quantity != null ? fmtQty(q.quantity) : '-'],
          ['预计到港时间', q.deliveryDate ? UI.fmtDate(q.deliveryDate) : '-'],
          ['到货港口', q.deliveryPlace || '-'],
          ['付款条款', q.payTerms || '-'],
          ['其他', q.qualityCommit || '-'],
          ['备注', q.remark || '-'],
          ['有效期至', q.validUntil ? UI.fmtDate(q.validUntil) : '-'],
          ['版本', q.version != null ? 'v' + q.version : '-'],
          ['报价状态', q.status ? UI.statusTag('QUOTE', q.status) : '-'],
        ])));
    } catch (e) { /* toast 已提示 */ }
  }

  /* 文件在线预览：文件流 Blob → objectURL → iframe（无需下载）；暴露到 window 供其他页面模块复用 */
  async function previewFile(fileId, fileName) {
    try {
      const blob = await API.fileBlob(fileId);
      const url = URL.createObjectURL(blob);
      const frame = UI.h('iframe', { src: url, style: 'width:100%;height:70vh;border:none;border-radius:8px;background:#fff' });
      UI.modal('预览 · ' + (fileName || '文件'), UI.h('div', {}, frame), null, { wide: true });
    } catch (e) { /* toast 已提示 */ }
  }
  window.previewFile = previewFile;

  /* -------- 运营仪表盘 -------- */
  Pages.dashboard = async function (page) {
    const d = await API.get('/admin/dashboard');
    const charts = await API.get('/admin/dashboard/charts');
    // 长条统计卡：准入企业 / 集采总货量 / 订单总数 / 本月成交单数
    const stripItems = [
      ['准入企业', String(d.companyApproved || 0), '家'],
      ['集采总货量', Number(d.procureQty || 0).toLocaleString('zh-CN'), '湿吨'],
      ['订单总数', String(d.orderTotal || 0), '单'],
      ['本月成交单数', String(d.monthOrders || 0), '单'],
    ];
    page.appendChild(UI.h('div', { class: 'card stat-strip' },
      stripItems.map(([label, val, unit]) => UI.h('div', { class: 'stat-strip-item' },
        UI.h('div', { class: 'stat-label' }, label),
        UI.h('div', { class: 'stat-value' }, val, UI.h('span', { class: 'stat-unit' }, unit))))));

    // 港口现货价 + 平台成交价：左侧同图双线（行业价格 vs 交易价格）
    /* 黄骅港 PB粉 按品位分组（61.5%/60.8%，价格不同），默认 61.5%，工具栏可切换 */
    const portRows = (await API.get('/base-prices/ports')).list || [];
    const hbByGrade = {};
    portRows
      .filter((r) => r.varietyName === 'PB粉' && r.portName === '黄骅港')
      .forEach((r) => {
        const g = r.grade != null ? Number(r.grade) : 61.5;
        (hbByGrade[g] = hbByGrade[g] || []).push(r);
      });
    const hbGrades = Object.keys(hbByGrade).map(Number).sort((a, b) => b - a);
    let curHbGrade = hbGrades.includes(61.5) ? 61.5 : (hbGrades[0] || 61.5);
    const varieties = (await API.get('/base/varieties')).list || [];
    const pb = varieties.find((v) => v.varietyName === 'PB粉');
    /* 交易价格按品位分组（订单品位 61.5%/60.8%），与行业价格品位切换联动 */
    const dealRaw = pb ? ((await API.get('/base-prices/deal-trend?varietyId=' + pb.id)).list || []) : [];
    const dealByGrade = {};
    dealRaw.forEach((r) => {
      /* 订单品位归并到最近的演示品位（61.5/60.8），保证与品位切换联动 */
      const raw = r.grade != null ? Number(r.grade) : 61.5;
      const g = Math.abs(raw - 61.5) <= Math.abs(raw - 60.8) ? 61.5 : 60.8;
      (dealByGrade[g] = dealByGrade[g] || []).push({ priceDate: r.priceDate, price: r.price });
    });
    const dealRowsOf = (g) => (dealByGrade[g] || [])
      .slice().sort((a, b) => String(a.priceDate).localeCompare(String(b.priceDate)));

    /* 右侧行情表：仅展示行业价格记录日，交易价格取该条记录录入的 dealPrice（选填）；
       订单推导的价格不再并入本表（不在趋势图交易价格线之外产生独立行） */
    function quoteRowsOf(grade) {
      const list = (hbByGrade[grade] || [])
        .slice().sort((a, b) => String(b.priceDate).localeCompare(String(a.priceDate)))
        .map((r) => ({ priceDate: r.priceDate, industry: r.price, deal: r.dealPrice }));
      let prev = null;
      list.slice().sort((a, b) => String(a.priceDate).localeCompare(String(b.priceDate))).forEach((r) => {
        r.chg = (r.industry != null && prev != null) ? r.industry - prev : null;
        if (r.industry != null) prev = r.industry;
      });
      return list;
    }

    /* 品位切换：重绘趋势图（行业价格=所选品位，交易价格不变）+ 右侧行情表 */
    const chartBox = UI.h('div', { class: 'trend-chart-wrap' });
    const quoteBox = UI.h('div', {});
    const hbGradeBtns = hbGrades.map((g) => UI.h('button', {
      class: 'sm',
      style: 'margin-right:6px;padding:2px 10px;font-size:12px',
      onclick: () => { curHbGrade = g; renderHb(); },
    }, String(g).replace(/\.?0+$/, '') + '%'));
    function renderHb() {
      hbGradeBtns.forEach((b, i) => {
        const on = hbGrades[i] === curHbGrade;
        b.style.background = on ? '#1a5cb0' : '#f2f2f7';
        b.style.color = on ? '#fff' : '#1d1d1f';
        b.style.borderColor = on ? '#1a5cb0' : '#e5e5ea';
      });
      chartBox.innerHTML = '';
      chartBox.appendChild(UI.multiTrendChart([
        { name: '行业价格', color: '#1a5cb0',
          rows: (hbByGrade[curHbGrade] || []).map((r) => ({ priceDate: r.priceDate, price: r.price }))
            .sort((a, b) => String(a.priceDate).localeCompare(String(b.priceDate))) },
        { name: '交易价格', color: '#af52de', dashed: true, rows: dealRowsOf(curHbGrade) },
      ]));
      quoteBox.innerHTML = '';
      quoteBox.appendChild(UI.table([
        { label: '日期', render: (r) => UI.fmtDate(r.priceDate) },
        { label: '行业价格(元/湿吨)', num: true, render: (r) => r.industry != null ? UI.fmtMoney(r.industry) : '—' },
        { label: '交易价格(元/湿吨)', num: true, render: (r) => r.deal != null ? UI.fmtMoney(r.deal) : '—' },
        { label: '涨跌', render: (r) => chgTag(r.chg) },
      ], quoteRowsOf(curHbGrade).slice(0, 7), '暂无价格数据'));
    }

    // 两栏：左侧 黄骅港 PB粉 双线趋势（品位切换），右侧近7天行情（同一行）
    page.appendChild(UI.h('div', { class: 'dash-two-col' },
      UI.h('div', { class: 'card dash-chart-card' },
        UI.h('div', { class: 'toolbar' },
          UI.h('h3', { style: 'margin:0;border:none;padding:0' }, '黄骅港 PB粉 价格趋势'),
          UI.h('div', { class: 'spacer' }),
          ...hbGradeBtns,
          UI.h('button', { class: 'sm', onclick: () => { location.hash = '#/port-price'; } }, '详情')),
        chartBox),
      UI.h('div', { class: 'card dash-quote-card' },
        UI.h('div', { class: 'toolbar' },
          UI.h('h3', { style: 'margin:0;border:none;padding:0' }, 'PB粉 价格行情（近7天）'),
          UI.h('div', { class: 'spacer' }),
          UI.h('button', { class: 'sm', onclick: () => { location.hash = '#/price-records'; } }, '详情')),
        quoteBox)));
    renderHb();

    // 货运趋势 / 矿种分布 / 运输方式运量对比
    const MODE_LABELS = { ROAD: '公路', RAIL: '铁路', WATER: '水运', SEA: '海运', MULTIMODAL: '多式联运' };
    const freightRows = (charts.freightTrend || [])
      .map((r) => ({ priceDate: r.trendDate, price: r.qty }))
      .filter((r) => Number(r.price) > 0); // 每日运输总量：运量为 0 的日子不做渲染
    const varietyDist = (charts.varietyDist || []).map((r) => ({ name: r.name, qty: Number(r.qty) }));
    const modeDist = (charts.modeDist || []).map((r) => ({ name: MODE_LABELS[r.mode] || r.mode, qty: Number(r.qty) }));
    // 货运趋势（整行全宽，展示近 30 日每日运输总量，无运单日为 0）+ 矿种分布 / 运输方式运量对比
    page.appendChild(UI.h('div', { class: 'card' },
      UI.h('div', { class: 'toolbar' },
        UI.h('h3', { style: 'margin:0;border:none;padding:0' }, '货运趋势（每日运输总量）')),
      freightRows.length > 0
        ? UI.trendChart(freightRows, 'price', '湿吨')
        : UI.h('div', { class: 'empty' }, '暂无运单数据')));
    // 矿种分布 + 运输方式运量对比（同行两列）
    page.appendChild(UI.h('div', { class: 'dash-charts' },
      UI.h('div', { class: 'card' },
        UI.h('h3', {}, '矿种分布'),
        UI.donutChart(varietyDist, 'qty', 'name', '总运量(湿吨)')),
      UI.h('div', { class: 'card' },
        UI.h('h3', {}, '运输方式运量对比'),
        UI.hbarChart(modeDist, 'qty', 'name', '湿吨'))));
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

    // 今日港口价：与钢厂端基准价行情同源同格式（产品名称/品位/港口/行业价格/计价口径/价格日期/来源）
    const cur = await API.get('/base-prices/current');
    const GRADE_OF = { 'PB粉': 61.5, '中华混一号': 61.5 };
    /* 港口筛选：今日港口价与行业价格走势同步过滤（默认黄骅港，可选其他港口/全部） */
    let curPort = '黄骅港';
    const todayPorts = Array.from(new Set(
      (cur.today || []).map((r) => r.port || r.portName).filter(Boolean))).sort();
    const portOpts = [['', '全部港口']].concat(todayPorts.map((p) => [p, p]));
    if (!todayPorts.includes('黄骅港')) portOpts.push(['黄骅港', '黄骅港']);
    const portSel = UI.selectField(portOpts, curPort,
      { onchange: (e) => { curPort = e.target.value; renderToday(); renderTrend(); } });
    const todayBox = UI.h('div', {});
    function renderToday() {
      const rows = (cur.today || []).filter((r) => !curPort || (r.port || r.portName) === curPort);
      todayBox.replaceChildren(UI.table([
        { key: 'varietyName', label: '产品名称' },
        { label: '品位', render: (r) => { const g = r.grade != null ? r.grade : GRADE_OF[r.varietyName]; return g != null ? String(g).replace(/\.?0+$/, '') + '%' : '-'; } },
        { label: '港口', render: (r) => r.port || r.portName || '-' },
        { key: 'price', label: '行业价格(元/湿吨)', num: true, render: (r) => UI.fmtMoney(r.price) },
        { key: 'priceBasis', label: '计价口径', render: (r) => r.priceBasis === 'DRY' ? '干基' : (r.priceBasis === 'WET' ? '湿基' : (r.priceBasis || '-')) },
        { key: 'priceDate', label: '价格日期', render: (r) => UI.fmtDate(r.priceDate) },
        { key: 'sourceDesc', label: '来源' },
      ], rows, '暂无港口价格，请在下方录入'));
    }
    renderToday();
    page.appendChild(UI.h('div', { class: 'card' },
      UI.h('h3', {}, '今日港口价',
        UI.h('label', { class: 'field', style: 'margin-left:auto' }, '港口筛选 ', portSel)),
      todayBox));

    // 行业价格走势：每港口一张图（多图），随港口筛选过滤
    const trendBox = UI.h('div', {});
    function renderTrend() {
      trendBox.replaceChildren();
      const byPort = {};
      portRows.forEach((r) => { (byPort[r.portName] = byPort[r.portName] || []).push(r); });
      const portKeys = Object.keys(byPort).filter((p) => !curPort || p === curPort).sort();
      portKeys.forEach((p) => {
        const rows = byPort[p].slice().sort((a, b) => String(a.priceDate).localeCompare(String(b.priceDate)));
        /* 按品位分组（PB粉 61.5% / 60.8%，不同品位价格不同），名称行下方右侧品位切换 */
        const byGrade = {};
        rows.forEach((r) => {
          const g = r.grade != null ? Number(r.grade) : 61.5;
          (byGrade[g] = byGrade[g] || []).push(r);
        });
        const grades = Object.keys(byGrade).map(Number).sort((a, b) => b - a);
        if (!grades.length) return;
        let cur = grades.includes(61.5) ? 61.5 : grades[0];
        const chartBox = UI.h('div', {});
        const gradeBtns = grades.map((g) => UI.h('button', {
          class: 'sm',
          style: 'margin-left:6px;padding:2px 10px;font-size:12px',
          onclick: () => { cur = g; render(); },
        }, String(g).replace(/\.?0+$/, '') + '%'));
        function render() {
          gradeBtns.forEach((b, i) => {
            const on = grades[i] === cur;
            b.style.background = on ? '#1a5cb0' : '#f2f2f7';
            b.style.color = on ? '#fff' : '#1d1d1f';
            b.style.borderColor = on ? '#1a5cb0' : '#e5e5ea';
          });
          chartBox.innerHTML = '';
          chartBox.appendChild(UI.trendChart(
            byGrade[cur].map((r) => ({ priceDate: r.priceDate, price: r.price })), 'price'));
        }
        render();
        trendBox.appendChild(UI.h('div', { style: 'margin-bottom:16px' },
          UI.h('div', { class: 'dash-trend-name' }, p + ' · 行业价格'),
          UI.h('div', { style: 'text-align:right;margin:-4px 0 4px' }, ...gradeBtns),
          chartBox));
      });
      if (!portKeys.length) trendBox.appendChild(UI.h('div', { class: 'empty' }, '暂无走势数据'));
    }
    renderTrend();
    page.appendChild(UI.h('div', { class: 'card' },
      UI.h('h3', {}, '行业价格走势（分港口）'),
      trendBox));

    // 交易价格走势（平台成交均价，钢厂端不可见）：按品位分组（订单品位归并到 61.5/60.8），品位切换同行业价格卡片
    const dealRaw = ((await API.get('/base-prices/deal-trend?varietyId=' + pb.id)).list || []);
    const dealByGrade = {};
    dealRaw.forEach((r) => {
      const raw = r.grade != null ? Number(r.grade) : 61.5;
      const g = Math.abs(raw - 61.5) <= Math.abs(raw - 60.8) ? 61.5 : 60.8;
      (dealByGrade[g] = dealByGrade[g] || []).push({ priceDate: r.priceDate, price: r.price });
    });
    const dealGrades = Object.keys(dealByGrade).map(Number).sort((a, b) => b - a);
    let curDealGrade = dealGrades.includes(61.5) ? 61.5 : (dealGrades[0] || 61.5);
    const dealBox = UI.h('div', {});
    const dealGradeBtns = dealGrades.map((g) => UI.h('button', {
      class: 'sm',
      style: 'margin-left:6px;padding:2px 10px;font-size:12px',
      onclick: () => { curDealGrade = g; renderDeal(); },
    }, String(g).replace(/\.?0+$/, '') + '%'));
    function renderDeal() {
      dealGradeBtns.forEach((b, i) => {
        const on = dealGrades[i] === curDealGrade;
        b.style.background = on ? '#1a5cb0' : '#f2f2f7';
        b.style.color = on ? '#fff' : '#1d1d1f';
        b.style.borderColor = on ? '#1a5cb0' : '#e5e5ea';
      });
      dealBox.innerHTML = '';
      const rows = (dealByGrade[curDealGrade] || [])
        .slice().sort((a, b) => String(a.priceDate).localeCompare(String(b.priceDate)));
      dealBox.appendChild(rows.length >= 2
        ? UI.trendChart(rows, 'price')
        : UI.h('div', { class: 'empty' }, '该品位暂无成交数据'));
    }
    renderDeal();
    page.appendChild(UI.h('div', { class: 'card' },
      UI.h('div', { class: 'toolbar' },
        UI.h('h3', { style: 'margin:0;border:none;padding:0' }, '交易价格走势（平台成交均价）'),
        UI.h('div', { class: 'spacer' }),
        ...dealGradeBtns),
      dealBox));
  };

  /* -------- 价格行情详情（全部价格数据 + 港口价格录入） -------- */
  Pages.price_records = async function (page) {
    const varieties = (await API.get('/base/varieties')).list || [];
    const pb = varieties.find((v) => v.varietyName === 'PB粉');
    if (!pb) {
      page.appendChild(UI.h('div', { class: 'card' }, UI.h('div', { class: 'empty' }, '品种库缺少 PB粉，请先在基础数据中添加')));
      return;
    }
    const portRows = (await API.get('/base-prices/ports')).list || [];

    // 全部价格数据：港口价记录（产品名称/品位/港口/行业价格/计价口径/价格日期/来源 + 涨跌按港口逐日计算）
    const GRADE_OF = { 'PB粉': 61.5, '中华混一号': 61.5 };
    const gradeOf = (r) => (r.grade != null ? Number(r.grade) : GRADE_OF[r.varietyName]);
    const gradeTxt = (g) => (g != null ? String(g).replace(/\.?0+$/, '') + '%' : '-');
    /* 涨跌按 港口×品位 分组逐日计算（同港口不同品位价格独立） */
    const byPortChg = {};
    portRows.forEach((r) => {
      const key = (r.portName || r.port || '') + '|' + gradeOf(r);
      (byPortChg[key] = byPortChg[key] || []).push(r);
    });
    Object.keys(byPortChg).forEach((p) => {
      let prev = null;
      byPortChg[p].slice().sort((a, b) => String(a.priceDate).localeCompare(String(b.priceDate)) || (a.id - b.id)).forEach((r) => {
        r.chg = prev != null ? r.price - prev : null;
        prev = r.price;
      });
    });
    const allRows = portRows.slice().sort((a, b) => String(b.priceDate).localeCompare(String(a.priceDate)));

    page.appendChild(UI.h('div', { class: 'card' },
      UI.h('div', { class: 'toolbar' },
        UI.h('h3', { style: 'margin:0;border:none;padding:0' }, '价格行情详情'),
        UI.h('div', { class: 'spacer' }),
        UI.h('button', { class: 'sm', onclick: () => { location.hash = '#/dashboard'; } }, '返回看板'))));

    /* 筛选框（品类/港口/日期范围）独立一行置于标题下方，变化即重渲染表格；每页 10 条分页 */
    const ports = Array.from(new Set(portRows.map((r) => r.portName || r.port || ''))).filter(Boolean).sort();
    let fVariety = '';
    let fPort = '';
    let fFrom = '';
    let fTo = '';
    let pageNo = 1;
    const picked = new Set(); // 行首勾选框（批量删除/导出）
    const pageSize = 10;
    const varietySel = UI.selectField([['', '全部品类']].concat(
      varieties.filter((v) => v.varietyName === 'PB粉' || v.varietyName === '中华混一号')
        .map((v) => [String(v.id), v.varietyName])), '',
      { onchange: (e) => { fVariety = e.target.value; pageNo = 1; renderTable(); } });
    const portSel = UI.selectField([['', '全部港口']].concat(ports.map((p) => [p, p])), '',
      { onchange: (e) => { fPort = e.target.value; pageNo = 1; renderTable(); } });
    const dateFromInp = UI.input('date', '', { onchange: (e) => { fFrom = e.target.value; pageNo = 1; renderTable(); } });
    const dateToInp = UI.input('date', '', { onchange: (e) => { fTo = e.target.value; pageNo = 1; renderTable(); } });

    const COLS = [
      UI.selCol(picked),
      { key: 'varietyName', label: '产品名称' },
      { label: '品位', render: (r) => gradeTxt(gradeOf(r)) },
      { label: '港口', render: (r) => r.portName || r.port || '-' },
      { key: 'price', label: '行业价格(元/湿吨)', num: true, render: (r) => UI.fmtMoney(r.price) },
      { label: '交易价格(元/湿吨)', num: true, render: (r) => r.dealPrice != null ? UI.fmtMoney(r.dealPrice) : '—' },
      { label: '计价口径', render: (r) => r.priceBasis === 'DRY' ? '干基' : '湿基' },
      { key: 'priceDate', label: '价格日期', render: (r) => UI.fmtDate(r.priceDate) },
      { label: '来源', render: () => 'Mysteel' },
      { label: '涨跌', render: (r) => chgTag(r.chg) },
      { label: '操作', render: (r) => UI.h('button', { class: 'sm', onclick: () => openEntryModal(r) }, '重新录入') },
    ];
    /* 定高列表区 + 分页行同卡片（同需求归集）：横向滚动条固定在分页行上方 */
    /* 当前筛选条件下的全部行（列表渲染与导出共用） */
    function filteredRows() {
      return allRows.filter((r) =>
        (!fVariety || String(r.varietyId) === fVariety)
        && (!fPort || (r.portName || r.port) === fPort)
        && (!fFrom || String(r.priceDate).slice(0, 10) >= fFrom)
        && (!fTo || String(r.priceDate).slice(0, 10) <= fTo));
    }
    const tableBox = UI.h('div', { class: 'list-fixed' });
    const pagerBox = UI.h('div', {});
    function renderTable() {
      const rows = filteredRows();
      const pages = Math.max(1, Math.ceil(rows.length / pageSize));
      if (pageNo > pages) pageNo = pages;
      tableBox.innerHTML = '';
      tableBox.appendChild(UI.table(COLS,
        rows.slice((pageNo - 1) * pageSize, pageNo * pageSize), '暂无价格数据'));
      pagerBox.innerHTML = '';
      UI.pager(pagerBox, pageNo, pageSize, rows.length, (p) => { pageNo = p; renderTable(); });
    }

    /* 价格录入弹窗：填 产品名称/品位/港口/价格/价格日期（默认当天），计价口径(湿基)、来源(Mysteel) 由系统自动补充 */
    const todayStr = (() => {
      const t = new Date();
      const pad = (x) => String(x).padStart(2, '0');
      return t.getFullYear() + '-' + pad(t.getMonth() + 1) + '-' + pad(t.getDate());
    })();
    function openEntryModal(row) {
      /* 产品名称仅可选 PB粉 / 中华混一号；row 传入时预填该行信息 */
      const entryVarieties = varieties.filter((v) => v.varietyName === 'PB粉' || v.varietyName === '中华混一号');
      const defVar = row ? String(row.varietyId) : String(pb.id);
      const varietySel = UI.selectField(entryVarieties.map((v) => [String(v.id), v.varietyName]), defVar);
      const rowPort = row ? (row.portName || row.port || '') : '';
      /* 港口：既可选择现有港口（datalist 下拉建议），也可直接录入新港口名称 */
      const portInp = UI.input('text', rowPort, {
        list: ports.length ? 'port-datalist' : null,
        placeholder: ports.length ? '选择或输入港口名称' : '港口名称，如：黄骅港',
        autocomplete: 'off',
      });
      const portPick = UI.h('div', { style: 'display:flex' },
        portInp,
        ports.length ? UI.h('datalist', { id: 'port-datalist' },
          ports.map((p) => UI.h('option', { value: p }))) : null);
      const priceInp = UI.input('number', row ? Number(row.price).toFixed(2) : '',
        { placeholder: '价格（元/湿吨）', step: '0.01' });
      /* 交易价格：选填（非必填），随行业价格一并录入/修改；留空表示不填（重新录入留空则清除） */
      const dealInp = UI.input('number', row && row.dealPrice != null ? Number(row.dealPrice).toFixed(2) : '',
        { placeholder: '选填，元/湿吨', step: '0.01' });
      const FORM_GRADES = [61.5, 60.8];
      let curGrade = row ? gradeOf(row) : 61.5;
      const gradeBtns = FORM_GRADES.map((g) => UI.h('button', {
        class: 'sm',
        style: 'margin-right:6px;padding:2px 10px;font-size:12px',
        onclick: () => { curGrade = g; syncGrade(); },
      }, String(g).replace(/\.?0+$/, '') + '%'));
      function syncGrade() {
        gradeBtns.forEach((b, i) => {
          const on = FORM_GRADES[i] === curGrade;
          b.style.background = on ? '#1a5cb0' : '#f2f2f7';
          b.style.color = on ? '#fff' : '#1d1d1f';
          b.style.borderColor = on ? '#1a5cb0' : '#e5e5ea';
        });
      }
      syncGrade();
      const dateInp = UI.input('date', row ? String(row.priceDate).slice(0, 10) : todayStr, {});
      const m = UI.modal(row ? '价格重新录入' : '价格录入', UI.h('form', { onsubmit: (e) => e.preventDefault() },
        UI.h('div', { class: 'form-grid' },
          UI.formRow('产品名称', varietySel, true),
          UI.formRow('品位', UI.h('div', { style: 'display:flex;align-items:center' }, ...gradeBtns), true),
          UI.formRow('港口', portPick, true),
          UI.formRow('价格(元/湿吨)', priceInp, true),
          UI.formRow('交易价格(元/湿吨)', dealInp, false),
          UI.formRow('价格日期', dateInp, true),
          UI.formRow('计价口径', UI.input('text', '湿基', {}), false),
          UI.formRow('来源', UI.input('text', 'Mysteel', {}), false)),
        row ? null : UI.h('div', { class: 'hint', style: 'margin-top:8px' },
          '同一品种×港口×日期×品位已有价格时，不覆盖原记录，提醒后新增一条记录')), [
        UI.h('button', { class: 'sm', onclick: () => m.close() }, '取 消'),
        UI.h('button', { class: 'primary', onclick: async () => {
          const portName = String(portInp.value || '').trim();
          if (!portName) { UI.toast('请选择或填写港口', 'err'); return; }
          if (!(Number(priceInp.value) > 0)) { UI.toast('价格需大于 0', 'err'); return; }
          if (dealInp.value !== '' && !(Number(dealInp.value) > 0)) { UI.toast('交易价格需大于 0', 'err'); return; }
          if (!dateInp.value) { UI.toast('请选择价格日期', 'err'); return; }
          const dealPrice = dealInp.value === '' ? null : Number(dealInp.value);
          try {
            if (row) {
              /* 重新录入：按记录 id 原地更新该条内容，不新增 */
              await API.put('/base-prices/ports/' + row.id, {
                varietyId: Number(varietySel.value), portName,
                priceDate: dateInp.value, price: Number(priceInp.value), grade: curGrade,
                dealPrice,
              });
              m.close();
              UI.toast('已更新该条价格记录，页面数据已自动更新', 'ok');
            } else {
              /* 价格录入：总是新增一条，不覆盖已有记录 */
              const res = await API.post('/base-prices/ports', {
                varietyId: Number(varietySel.value), portName,
                priceDate: dateInp.value, price: Number(priceInp.value), grade: curGrade,
                dealPrice,
              });
              m.close();
              if (res && res.duplicated) {
                UI.toast('同品种/港口/日期/品位已有价格记录（'
                  + Number(res.existingPrice).toFixed(2) + ' 元/湿吨），未覆盖原记录，已新增一条');
              } else {
                UI.toast('已保存，页面数据已自动更新', 'ok');
              }
            }
            /* 整页重渲染：全部价格数据/今日港口价/趋势图按录入的新数据自动更新 */
            window.App.route();
          } catch (e) { /* toast 已提示 */ }
        } }, '保 存'),
      ], { noAutoClose: true });
    }

    /* 批量删除：按行首勾选框选择，确认后软删除 */
    async function batchDelete() {
      if (!picked.size) { UI.toast('请先勾选要删除的行', 'err'); return; }
      const yes = await UI.confirmBox('确定删除选中的 ' + picked.size + ' 条价格记录吗？删除后不可恢复。');
      if (!yes) return;
      const ids = Array.from(picked);
      const rs = await Promise.allSettled(ids.map((id) => API.del('/base-prices/ports/' + id)));
      const failN = rs.filter((r) => r.status === 'rejected').length;
      if (!failN) UI.toast('已删除 ' + ids.length + ' 条记录', 'ok');
      else UI.toast('删除完成：成功 ' + (ids.length - failN) + ' 条，失败 ' + failN + ' 条',
        failN === ids.length ? 'err' : 'ok');
      picked.clear();
      window.App.route();
    }

    /* 导出 CSV：勾选了行则导出勾选行，否则导出当前筛选结果的全部行；先预览确认再下载 */
    function exportRows() {
      const rows = filteredRows();
      const chosen = picked.size ? rows.filter((r) => picked.has(r.id)) : rows;
      if (!chosen.length) { UI.toast('暂无可导出的数据', 'err'); return; }
      UI.exportPreview({
        title: '导出预览 — 价格数据',
        filename: '价格数据_' + todayStr.replace(/-/g, '') + '.csv',
        head: ['产品名称', '品位', '港口', '行业价格(元/湿吨)', '计价口径', '价格日期', '来源', '涨跌'],
        rows: chosen.map((r) => [
          r.varietyName, gradeTxt(gradeOf(r)), r.portName || r.port || '-',
          Number(r.price).toFixed(2), r.priceBasis === 'DRY' ? '干基' : '湿基',
          String(r.priceDate).slice(0, 10), 'Mysteel',
          r.chg == null ? '' : (r.chg > 0 ? '+' : '') + Number(r.chg).toFixed(2),
        ]),
      });
    }

    page.appendChild(UI.h('div', { class: 'card' },
      UI.h('div', { class: 'toolbar' },
        UI.h('h3', {}, '全部价格数据'),
        UI.h('div', { class: 'spacer' }),
        UI.h('button', { class: 'sm', onclick: () => openEntryModal() }, '价格录入'),
        UI.h('button', { class: 'sm', style: 'margin-left:8px', onclick: batchDelete }, '删除'),
        UI.h('button', { class: 'sm', style: 'margin-left:8px', onclick: exportRows }, '导出')),
      UI.h('div', { class: 'toolbar' },
        UI.h('span', { style: 'font-size:12px;color:#6e6e73;margin-right:6px' }, '品类'),
        varietySel,
        UI.h('span', { style: 'font-size:12px;color:#6e6e73;margin:0 6px 0 12px' }, '港口'),
        portSel,
        UI.h('span', { style: 'font-size:12px;color:#6e6e73;margin:0 6px 0 12px' }, '日期'),
        dateFromInp,
        UI.h('span', { style: 'font-size:12px;color:#6e6e73;margin:0 6px' }, '至'),
        dateToInp),
      tableBox,
      pagerBox));
    renderTable();
  };

  /* -------- 企业审核台 --------
     initialTab: list=准入申请列表 archive=企业档案信息（由侧边栏二级菜单路由决定） */
  Pages.admin_companies = async function (page, initialTab) {
    let pageNo = 1;
    let archivePageNo = 1;
    const SIZE = 10;
    let auditStatus = '';
    let tab = initialTab || 'list'; // list=准入申请列表 archive=企业档案信息
    let keyword = '';
    let cache = [];
    const pickedRows = new Set(); // 行首勾选框（仅行选择展示）

    /* 定高列表区（同需求归集，10 行/页）：纵向超出滚动，横向滚动条固定在分页行上方 */
    const listBox = UI.h('div', { class: 'list-fixed' });
    const pagerBox = UI.h('div', {});

    const filterEl = UI.h('div', {});  // 筛选行（标题面板，标题下方）
    const actionEl = UI.h('div', { class: 'toolbar' });  // 操作行（数据面板顶部）
    /* 面板拆分：标题面板（标题+筛选）与数据面板（操作+表格）两块独立 */
    page.appendChild(UI.h('div', { class: 'card' },
      UI.h('div', { class: 'toolbar stacked' },
        UI.h('h3', { style: 'margin:0;border:none;padding:0' },
          tab === 'archive' ? '企业档案信息' : '准入申请列表'),
        filterEl)));
    page.appendChild(UI.h('div', { class: 'card' },
      actionEl,
      listBox,
      pagerBox));
    render();

    /* 表格外层：与需求列表一致，仅超宽时横向滚动 */
    function tableWrap(table) { return UI.h('div', { class: 'table-scroll-wrap' }, table); }

    function filterBox() { return filterEl; }

    /* 企业类型中文显示（STEEL/SUPPLIER/LOGISTICS → 钢铁企业/供应商/承运商） */
    const TYPE_CN = { STEEL: '钢铁企业（需方）', SUPPLIER: '供应商（供方）', LOGISTICS: '承运商' };
    function typesCn(s) {
      if (!s) return '-';
      return String(s).split(',').map((t) => TYPE_CN[t.trim()] || t.trim()).join('、');
    }

    async function render() {
      const box = filterBox();
      if (!box) return;
      box.innerHTML = '';
      // 两个页签都在表格上方提供关键字检索（企业名称/信用代码/联系人/账号）
      const kwInput = UI.input('text', keyword, {
        placeholder: '企业名称 / 信用代码 / 联系人 / 账号',
        style: 'width:230px;margin-right:8px',
      });
      const go = () => { keyword = kwInput.value.trim(); pageNo = 1; archivePageNo = 1; render(); };
      kwInput.addEventListener('keydown', (e) => { if (e.key === 'Enter') go(); });
      box.appendChild(UI.h('span', { class: 'inline-flex' },
        kwInput,
        UI.h('button', { class: 'sm', onclick: go }, '查询')));
      actionEl.innerHTML = '';
      actionEl.appendChild(UI.h('button', { class: 'primary', onclick: () => companyRegisterModal() }, '新 增'));
      actionEl.appendChild(UI.h('button', { class: 'sm', onclick: exportCsv }, '导 出'));
      // 现阶段企业注册即默认准入，不再提供准入状态筛选
      if (tab === 'list') {
        await load();
      } else {
        await loadArchive();
      }
    }

    /* 导出当前查询结果（两个页签列不同：准入列表含注册时间/账号/账号状态）；先预览确认再下载 */
    async function exportCsv() {
      const isList = tab === 'list';
      const d = await API.get('/admin/companies' + API.qs({
        auditStatus: isList ? auditStatus : '',
        keyword, page: 1, size: 500 }));
      const rows = d.list || [];
      if (!rows.length) { UI.toast('暂无可导出的数据', 'err'); return; }
      const head = isList
        ? ['企业名称', '统一社会信用代码', '企业类型', '联系人', '联系电话', '注册时间', '账号', '账号状态']
        : ['企业名称', '统一社会信用代码', '企业类型', '联系人', '联系电话'];
      UI.exportPreview({
        title: '导出预览 — ' + (isList ? '准入申请列表' : '企业档案信息'),
        filename: (isList ? '准入申请列表' : '企业档案信息') + '_' + new Date().toISOString().slice(0, 10).replace(/-/g, '') + '.csv',
        head,
        rows: rows.map((r) => (isList ? [
          r.companyName, r.creditCode, typesCn(r.companyTypes), r.contactName, r.contactPhone,
          r.createdAt ? UI.fmtDateTime(r.createdAt) : '', r.account || '', r.status === 'ENABLED' ? '启用' : '停用',
        ] : [
          r.companyName, r.creditCode, typesCn(r.companyTypes), r.contactName, r.contactPhone,
        ])),
      });
    }

    /* 运营代注册：字段同登录页企业注册表单，但全部选填（缺失字段由后端自动占位；
       登录账号填写且企业角色已选时才创建账号，密码缺省自动生成并回显转告企业） */
    function companyRegisterModal() {
      const f = {};
      const field = (key, label, props) => {
        f[key] = UI.input((props && props.type) || 'text', '', Object.assign({ placeholder: label }, props || {}));
        return UI.formRow(label, f[key], false); // 与注册页同结构，但无必填星号
      };

      /* 企业角色：radio 严格单选（同注册页交互），可全不选 */
      const TYPES = [['STEEL_BUYER', '钢铁企业（需方）'], ['SUPPLIER', '供应商（供方）']];
      const ROLE_DESC = {
        STEEL_BUYER: '采购铁矿石等大宗原料，发起需求与询价',
        SUPPLIER: '参与密封报价、议价与合同签订',
      };
      const roleCards = TYPES.map(([code, name]) => {
        const radio = UI.h('input', { type: 'radio', name: 'companyType', value: code });
        const card = UI.h('label', { class: 'role-card', 'data-code': code },
          UI.h('span', { class: 'role-name' }, name),
          UI.h('span', { class: 'role-desc' }, ROLE_DESC[code]),
          UI.h('span', { class: 'role-check' }, '✓'),
          radio);
        radio.addEventListener('change', () => {
          roleCards.forEach((c) => {
            const r = c.querySelector('input');
            if (r.checked) { c.classList.add('on'); } else { c.classList.remove('on'); }
          });
        });
        return card;
      });

      /* 营业执照：同注册页交互——选择后进入下方文件框，可删除、点击文件名预览；再次选择替换 */
      let licenseFile = null;
      const license = UI.h('input', { type: 'file', accept: 'image/*,.pdf' });
      const uploadBox = UI.h('div', { class: 'upload-box', style: 'display:none' });
      const fmtSize = (n) => (n >= 1024 * 1024 ? (n / 1024 / 1024).toFixed(1) + ' MB' : Math.max(1, Math.round(n / 1024)) + ' KB');
      const previewLicense = (file) => {
        const url = URL.createObjectURL(file);
        const isPdf = file.type === 'application/pdf' || /\.pdf$/i.test(file.name);
        const body = isPdf
          ? UI.h('iframe', { src: url, style: 'width:100%;height:70vh;border:1px solid var(--separator);background:#fff' })
          : UI.h('img', { src: url, style: 'max-width:100%;max-height:70vh;display:block;margin:0 auto' });
        UI.modal('营业执照预览 · ' + file.name, body, null, { wide: true });
        setTimeout(() => URL.revokeObjectURL(url), 10 * 60 * 1000);
      };
      const renderUpload = () => {
        uploadBox.innerHTML = '';
        if (!licenseFile) { uploadBox.style.display = 'none'; return; }
        uploadBox.style.display = '';
        uploadBox.appendChild(UI.h('div', { class: 'upload-item' },
          UI.h('a', { class: 'upload-name', title: '点击预览', href: 'javascript:;', onclick: () => previewLicense(licenseFile) }, licenseFile.name),
          UI.h('span', { class: 'upload-size' }, fmtSize(licenseFile.size)),
          UI.h('a', { class: 'upload-del', href: 'javascript:;', onclick: () => { licenseFile = null; renderUpload(); } }, '删除')));
      };
      license.addEventListener('change', () => {
        const file = license.files && license.files[0];
        if (!file) return;
        licenseFile = file;
        renderUpload();
        license.value = ''; // 允许再次选择同一文件替换
      });
      const form = UI.h('form', { onsubmit: (e) => e.preventDefault() },
        UI.h('div', { class: 'sec' }, '企业信息'),
        UI.h('div', { class: 'form-grid' },
          field('companyName', '企业名称', { placeholder: '请输入工商注册全称（选填，缺省自动占位）' }),
          field('creditCode', '统一社会信用代码', { placeholder: '18 位字母数字，如 91130000XXXXXXXXXX' }),
          UI.h('div', { class: 'form-row full' },
            UI.h('label', {}, '企业角色（仅可选择一个，选填；填写登录账号时必选）'),
            UI.h('div', { class: 'role-grid' }, ...roleCards)),
          field('legalPerson', '法定代表人', { placeholder: '请输入法定代表人姓名' }),
          field('address', '注册地址', { placeholder: '请输入注册详细地址' }),
          UI.h('div', { class: 'form-row full' },
            UI.h('label', {}, '经营范围'),
            UI.h('textarea', { rows: 2, style: 'width:100%', placeholder: '选填，如：铁矿石进口、销售', onchange: (e) => { f.businessScope = e.target.value; } }))),
        UI.h('div', { class: 'sec' }, '联系信息'),
        UI.h('div', { class: 'form-grid' },
          field('contactName', '联系人', { placeholder: '请输入联系人姓名' }),
          field('contactPhone', '联系电话', { placeholder: '11 位手机号' }),
          field('contactEmail', '联系邮箱', { placeholder: '选填，如 name@company.com' })),
        UI.h('div', { class: 'sec' }, '账号与营业执照'),
        UI.h('div', { class: 'form-grid' },
          field('username', '登录账号（11 位手机号）', { placeholder: '设置登录手机号，11 位（选填，填写后为企业创建登录账号）' }),
          field('password', '密码（至少 8 位）', { type: 'password', autocomplete: 'new-password',
            placeholder: '至少 8 位，建议字母与数字组合（选填，缺省自动生成）' }),
          UI.h('div', { class: 'form-row full' },
            UI.h('label', {}, '营业执照（选填）'),
            license, UI.h('div', { class: 'hint' }, '支持图片 / PDF，选择后可在下方查看文件'),
            uploadBox)));
      const m = UI.modal('运营代注册 · 企业信息（全部选填）', form, [
        UI.h('button', { class: 'primary', onclick: async () => {
          /* 提交时直接以 DOM 勾选态为准（同注册页）；全部字段非必填，仅对已填内容做格式与组合校验 */
          const checkedRole = form.querySelector('input[name="companyType"]:checked');
          const body = {
            companyName: f.companyName.value.trim(),
            creditCode: f.creditCode.value.trim(),
            companyTypes: checkedRole ? checkedRole.value : '',
            address: f.address.value.trim(),
            legalPerson: f.legalPerson.value.trim(),
            contactName: f.contactName.value.trim(),
            contactPhone: f.contactPhone.value.trim(),
            contactEmail: f.contactEmail.value.trim(),
            businessScope: f.businessScope || '',
            username: f.username.value.trim(),
            password: f.password.value,
          };
          if (body.creditCode && !/^[0-9A-Z]{15,18}$/.test(body.creditCode)) { UI.toast('统一社会信用代码应为 15~18 位大写字母或数字', 'err'); return; }
          if (body.contactPhone && !/^1\d{10}$/.test(body.contactPhone)) { UI.toast('联系电话应为 11 位手机号', 'err'); return; }
          if (body.contactEmail && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(body.contactEmail)) { UI.toast('联系邮箱格式不正确，如 name@company.com', 'err'); return; }
          if (body.username) {
            if (!/^1\d{10}$/.test(body.username)) { UI.toast('登录账号必须为 11 位手机号', 'err'); return; }
            if (!body.companyTypes) { UI.toast('填写登录账号时须选择企业角色', 'err'); return; }
            if (body.password && body.password.length < 8) { UI.toast('密码至少 8 位，建议字母与数字组合', 'err'); return; }
          } else if (body.password) { UI.toast('已填写密码但未填写登录账号，请补填登录账号或清空密码', 'err'); return; }
          try {
            if (licenseFile) {
              const up = await API.upload(licenseFile, '/auth/license');
              body.licenseFileId = up.fileId != null ? up.fileId : up.id;
            }
            const res = await API.post('/admin/companies/register', body);
            let msg = '代注册成功（企业 ' + res.companyId + '，待准入审核）';
            if (res.generatedPassword) msg += '；已生成密码 ' + res.generatedPassword + '，请转告企业';
            else if (res.username) msg += '；登录账号 ' + res.username + ' 已创建';
            else msg += '；暂未创建登录账号';
            UI.toast(msg, 'ok');
            m.close();
            render();
          } catch (e) { /* toast 已提示 */ }
        } }, '提交注册'),
      ], { wide: true });
    }

    async function load() {
      const d = await API.get('/admin/companies' + API.qs({ auditStatus, keyword, page: pageNo, size: SIZE }));
      cache = d.list || [];
      listBox.innerHTML = '';
      listBox.appendChild(tableWrap(UI.table([
        UI.selCol(pickedRows),
        { label: '序号', render: (r) => String((pageNo - 1) * SIZE + cache.indexOf(r) + 1) },
        { key: 'companyName', label: '企业名称' },
        { key: 'creditCode', label: '统一社会信用代码' },
        { label: '企业类型', render: (r) => typesCn(r.companyTypes) },
        { key: 'contactName', label: '联系人' },
        { key: 'contactPhone', label: '联系电话' },
        { key: 'createdAt', label: '注册时间', render: (r) => r.createdAt ? UI.fmtDateTime(r.createdAt) : '—' },
        { key: 'account', label: '账号', render: (r) => r.account || '-' },
        { key: 'status', label: '账号状态', render: (r) => r.status === 'ENABLED' ? UI.h('span', { class: 'tag green' }, '启用') : UI.h('span', { class: 'tag red' }, '停用') },
        { label: '操作', render: (r) => acts(r) },
      ], d.list, '暂无企业')));
      pagerBox.innerHTML = '';
      UI.pager(pagerBox, pageNo, SIZE, d.total, (p) => { pageNo = p; load(); });
    }

    /* 企业档案信息页签：与准入列表同款分页（每页 10 条，分页条置于表格下方） */
    async function loadArchive() {
      const d = await API.get('/admin/companies' + API.qs({ auditStatus: '', keyword, page: archivePageNo, size: SIZE }));
      cache = d.list || [];
      listBox.innerHTML = '';
      listBox.appendChild(tableWrap(UI.table([
        UI.selCol(pickedRows),
        { label: '序号', render: (r) => String((archivePageNo - 1) * SIZE + cache.indexOf(r) + 1) },
        { key: 'companyName', label: '企业名称' },
        { key: 'creditCode', label: '统一社会信用代码' },
        { label: '企业类型', render: (r) => typesCn(r.companyTypes) },
        { key: 'contactName', label: '联系人' },
        { key: 'contactPhone', label: '联系电话' },
        { label: '操作', render: (r) => UI.h('span', { class: 'inline-flex' }, UI.h('button', { class: 'sm', onclick: () => detail(r.id, 'archive') }, '详情')) },
      ], cache, keyword ? '未找到匹配的企业' : '暂无企业档案')));
      pagerBox.innerHTML = '';
      UI.pager(pagerBox, archivePageNo, SIZE, d.total, (p) => { archivePageNo = p; loadArchive(); });
    }

    function acts(r) {
      const btns = [UI.h('button', { class: 'sm', onclick: () => detail(r.id, 'register', r) }, '详情')];
      if (r.auditStatus === 'PENDING') {
        btns.push(UI.h('button', { class: 'sm success', onclick: () => auditModal(r) }, '审核'));
      }
      if (r.auditStatus === 'APPROVED') {
        btns.push(r.status === 'ENABLED'
          ? UI.h('button', { class: 'sm danger', onclick: () => toggle(r, 'DISABLED') }, '停用')
          : UI.h('button', { class: 'sm success', onclick: () => toggle(r, 'ENABLED') }, '启用'));
      }
      if (r.account) {
        btns.push(UI.h('button', { class: 'sm', onclick: () => resetPwd(r) }, '重置密码'));
      }
      return UI.h('span', { class: 'inline-flex' }, ...btns);
    }

    /* 运营端重置企业账号密码：弹窗输入新口令（强度校验在后端） */
    function resetPwd(r) {
      const p1 = UI.h('input', { type: 'password', style: 'width:100%', autocomplete: 'new-password',
        placeholder: '至少8位，须同时包含字母和数字' });
      const p2 = UI.h('input', { type: 'password', style: 'width:100%', autocomplete: 'new-password',
        placeholder: '再次输入新密码' });
      const m = UI.modal('重置密码 · ' + r.companyName,
        UI.h('form', { onsubmit: (e) => e.preventDefault() },
          UI.h('p', { style: 'margin:0 0 12px;color:#6b7280' },
            '将重置企业「' + r.companyName + '」账号「' + (r.account || '') + '」的登录密码，请设置新密码并线下告知该企业'),
          UI.formRow('新密码', p1, true),
          UI.formRow('确认新密码', p2, true)), [
        UI.h('button', { class: 'primary', onclick: async () => {
          if (!p1.value || p1.value !== p2.value) { UI.toast('两次输入的密码不一致', 'err'); return; }
          try {
            await API.put('/admin/companies/' + r.id + '/reset-password', { password: p1.value });
            m.close(); UI.toast('密码已重置，请将新密码线下告知该企业账号', 'ok');
          } catch (e) { /* toast 已提示 */ }
        } }, '确 定'),
      ]);
    }

    async function auditModal(r) {
      // 审核弹窗：先载入企业准入登记资料（提交的完整信息），再给出审核结论；
      // 若企业有待审核信息变更（pendingChanges），展示「字段/当前值/变更后」对比
      let c = {};
      try { c = await API.get('/companies/' + r.id); } catch (e) { /* 降级为列表行数据 */ }
      const pending = c.pendingChanges || c.pending_changes || null;
      const hasChange = pending && Object.keys(pending).length > 0;
      const SNAKE = { companyName: 'company_name', creditCode: 'credit_code', province: 'province',
        city: 'city', address: 'address', legalPerson: 'legal_person', contactName: 'contact_name',
        contactPhone: 'contact_phone', contactEmail: 'contact_email', businessScope: 'business_scope',
        bankName: 'bank_name', bankAccount: 'bank_account' };
      let changeBox = null;
      if (hasChange) {
        const rows = Object.keys(pending).map((k) => {
          const curV = (c[k] != null && c[k] !== '') ? c[k] : (c[SNAKE[k]] != null ? c[SNAKE[k]] : '-');
          return UI.h('tr', {},
            UI.h('td', { style: 'padding:6px 8px' }, LOG_FIELD[k] || k),
            UI.h('td', { style: 'padding:6px 8px' }, String(curV == null || curV === '' ? '-' : curV)),
            UI.h('td', { style: 'padding:6px 8px;color:#2563eb;font-weight:600' },
              String(pending[k] == null || pending[k] === '' ? '-' : pending[k])));
        });
        changeBox = UI.h('div', {},
          UI.h('h3', { style: 'margin:14px 0 8px;color:#d97706' }, '待审核变更内容（审核通过后自动更新）'),
          UI.h('table', { style: 'width:100%;border-collapse:collapse;border:1px solid #e5e7eb' },
            UI.h('thead', {}, UI.h('tr', { style: 'background:#f9fafb' },
              UI.h('td', { style: 'padding:6px 8px;font-weight:600' }, '字段'),
              UI.h('td', { style: 'padding:6px 8px;font-weight:600' }, '当前值'),
              UI.h('td', { style: 'padding:6px 8px;font-weight:600' }, '变更后'))),
            rows));
      }
      const info = UI.kv([
        ['企业名称', c.companyName || c.company_name || r.companyName],
        ['统一社会信用代码', c.creditCode || c.credit_code || r.creditCode],
        ['企业类型', typesCn(c.companyTypes || c.company_types || r.companyTypes)],
        ['联系人', c.contactName || c.contact_name || r.contactName],
        ['联系电话', c.contactPhone || c.contact_phone || r.contactPhone],
        ['注册地址', c.address || c.registered_address || '-', true],
        ['经营范围', c.businessScope || c.business_scope || '-', true],
      ]);
      const approve = UI.selectField([['true', '通过'], ['false', '驳回']], 'true');
      const remark = UI.h('textarea', { rows: 2, style: 'width:100%', placeholder: '审核意见（驳回必填）' });
      const m = UI.modal((hasChange ? '信息变更审核 · ' : '准入审核 · ') + (c.companyName || c.company_name || r.companyName),
        UI.h('form', { onsubmit: (e) => e.preventDefault() },
        UI.h('h3', { style: 'margin:0 0 8px' }, hasChange ? '当前生效信息（变更审核通过前保持不变）' : '准入登记资料'), info,
        changeBox,
        UI.h('h3', { style: 'margin:14px 0 8px' }, '审核结论'),
        UI.h('div', { class: 'form-grid' },
          UI.formRow('审核结论', approve, true),
          UI.h('div', { class: 'form-row full' }, UI.h('label', {}, '审核意见'), remark))), [
        UI.h('button', { class: 'primary', onclick: async () => {
          if (approve.value === 'false' && !remark.value.trim()) { UI.toast('驳回必须填写原因', 'err'); return; }
          try {
            await API.put('/admin/companies/' + r.id + '/audit',
              { approve: approve.value, remark: remark.value.trim() });
            m.close(); UI.toast(hasChange ? '审核完成，变更已处理' : '审核完成', 'ok'); load();
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

    function licenseTable(quals) {
      if (!quals || !quals.length) return UI.h('div', { class: 'empty' }, '暂无证照文件');
      return UI.table([
        { key: 'fileName', label: '文件名称', render: (r) => r.fileId
          ? UI.h('a', { href: 'javascript:;', style: 'color:#1a5cb0', onclick: () => previewFile(r.fileId, r.fileName) }, r.fileName || '证照文件')
          : (r.fileName || '-') },
        { key: 'fileType', label: '类型', render: (r) => QUAL_FILE_TYPE[r.fileType] || r.fileType || '-' },
        { label: '操作', render: (r) => r.fileId ? UI.h('span', { class: 'inline-flex' },
          UI.h('a', { href: 'javascript:;', style: 'color:#1a5cb0;margin-right:10px', onclick: () => previewFile(r.fileId, r.fileName) }, '预览'),
          UI.h('a', { href: 'javascript:;', style: 'color:#1a5cb0', onclick: () => API.downloadFile(r.fileId, r.fileName || '证照文件') }, '下载')) : '-' },
      ], quals, '暂无证照文件');
    }

    /* 详情：register=准入申请列表（注册信息 + 营业执照点击预览）；archive=企业档案信息（完整档案视图，内容不变） */
    async function detail(cid, mode, row) {
      const d = await API.get('/companies/' + cid);
      const c = d;
      const box = UI.h('div', {});

      if (mode === 'archive') {
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
        box.appendChild(licenseTable(d.qualifications || []));

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
          ['累计成交量', String(coop.totalQty || 0) + ' 湿吨'],
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
        return;
      }

      /* 准入申请列表详情：注册时提交的信息 */
      box.appendChild(UI.h('h3', { style: 'margin:0 0 8px' }, '注册信息'));
      box.appendChild(UI.kv([
        ['企业名称', c.companyName || c.company_name],
        ['账号', (row && row.account) || c.account || '-'],
        ['统一社会信用代码', c.creditCode || c.credit_code],
        ['企业类型', typesCn(c.companyTypes || c.company_types)],
        ['所在省市', ((c.province || '') + ' ' + (c.city || '')).trim() || '-'],
        ['法定代表人', c.legalPerson || c.legal_person],
        ['联系人', c.contactName || c.contact_name],
        ['联系电话', c.contactPhone || c.contact_phone],
        ['联系邮箱', c.contactEmail || c.contact_email],
        ['经营地址', c.address, true],
        ['经营范围', c.businessScope || c.business_scope, true],
      ]));

      box.appendChild(UI.h('h3', { style: 'margin:14px 0 8px' }, '营业执照'));
      box.appendChild(licenseTable(d.qualifications || []));

      UI.modal('企业注册信息 · ' + (c.companyName || c.company_name || ''), box, null, { wide: true });
    }
  };

  /* 企业准入二级菜单路由：准入申请列表 / 企业档案信息（复用同一页面，初始页签不同） */
  Pages.company_list = function (page) { return Pages.admin_companies(page, 'list'); };
  Pages.company_archive = function (page) { return Pages.admin_companies(page, 'archive'); };

  /* -------- 需求归集：需求列表 / 订单归集 / 变更申请审核
     initialTab 由侧边栏二级菜单路由决定 -------- */
  Pages.demand_pool = async function (page, initialTab) {
    const SIZE = 10;
    let pageNo = 1;
    let chPageNo = 1;
    let aggPageNo = 1;
    // demands=需求列表 aggr=订单归集 group=需求归集 changes=变更申请审核（route() 传参可能为查询对象，仅接受合法页签字符串）
    let tab = (initialTab === 'demands' || initialTab === 'aggr' || initialTab === 'group' || initialTab === 'changes')
      ? initialTab : 'demands';
    let demandStatus = '';
    let changeStatus = '';
    let aggStatus = '';
    let demandRows = [];
    const picked = new Set(); // 勾选的待归集需求明细 id
    const groupPicked = new Set(); // 需求归集页行首勾选框（行选择展示，用于后续批量推送供应商）
    const pickedAgg = new Set(); // 勾选的归集订单（OPEN）
    const pickedCh = new Set(); // 变更申请行首勾选框（仅行选择展示）
    // 表格横向滚动容器：超宽时面板内右拉
    const scrollWrap = (node, style) => UI.h('div', { class: 'table-scroll-wrap', style }, node);

    const filterBox = UI.h('div', {});  // 筛选行（标题面板，标题下方）
    const actionBox = UI.h('div', { class: 'toolbar' });  // 操作行（数据面板顶部）
    /* 三个二级菜单共用列表容器：定高列表区（.list-fixed，表头39px+10行×48px），切换页签高度保持不变；纵向超出滚动，横向滚动条固定在分页行上方 */
    const listBox = UI.h('div', { class: 'list-fixed' });
    const pagerBox = UI.h('div', {});

    /* 卡片标题随二级菜单页签变化：需求列表/订单归集/需求归集/变更申请 */
    const TAB_TITLE = { demands: '需求列表', aggr: '订单归集', group: '需求归集', changes: '变更申请' };
    const titleEl = UI.h('h3', { style: 'margin:0;border:none;padding:0' }, TAB_TITLE[tab] || '需求列表');
    /* 面板拆分：标题面板（标题+筛选）与数据面板（操作+表格）两块独立（四个页签共用） */
    page.appendChild(UI.h('div', { class: 'card' },
      UI.h('div', { class: 'toolbar stacked' },
        titleEl,
        UI.h('div', { class: 'spacer' }),
        filterBox)));
    page.appendChild(UI.h('div', { class: 'card' },
      actionBox,
      listBox,
      pagerBox));
    render();

    async function render() {
      titleEl.textContent = TAB_TITLE[tab] || '需求列表';
      filterBox.innerHTML = '';
      actionBox.innerHTML = '';
      pagerBox.innerHTML = '';
      if (tab === 'demands') {
        actionBox.appendChild(UI.h('button', {
          class: 'primary', onclick: mergeAggregated,
        }, '合并归集'));
        filterBox.appendChild(UI.statusFilter('DEMAND', (v) => { demandStatus = v; pageNo = 1; picked.clear(); loadDemands(); }));
        await loadDemands();
      } else if (tab === 'aggr') {
        actionBox.appendChild(UI.h('button', {
          class: 'primary',
          onclick: () => {
            // 带上勾选的 OPEN 归集订单，跳转后自动弹出发起询价弹窗
            if (pickedAgg.size) sessionStorage.setItem('agg_inquiry_seed', String([...pickedAgg][0]));
            location.hash = '#/quote-inquiry';
          },
        }, '去询价'));
        filterBox.appendChild(UI.statusFilter('AGG', (v) => { aggStatus = v; aggPageNo = 1; loadAggr(); }));
        await loadAggr();
      } else if (tab === 'group') {
        filterBox.appendChild(UI.statusFilter('AGG', (v) => { aggStatus = v; aggPageNo = 1; loadGroup(); }));
        actionBox.appendChild(UI.h('button', { class: 'primary', onclick: pushGroups }, '推送供应商'));
        await loadGroup();
      } else {
        filterBox.appendChild(UI.statusFilter('CHANGE', (v) => { changeStatus = v; chPageNo = 1; loadChanges(); }));
        await loadChanges();
      }
    }

    /* 申报周期展示：QUARTER → 2026年第4季度；MONTH → 2026年11月；ONE_TIME → 一次性订单（2026年12月） */
    function cycleTxt(r) {
      if (r && r.cycleType === 'ONE_TIME') {
        return (r.cycleYear && r.cycleValue)
          ? '一次性订单（' + r.cycleYear + '年' + r.cycleValue + '月）' : '一次性订单';
      }
      if (!r || !r.cycleType) return '—';
      return r.cycleYear + '年' + (r.cycleType === 'QUARTER' ? '第' + r.cycleValue + '季度' : r.cycleValue + '月');
    }

    /* 周期类型文案：MONTH→月度，QUARTER→季度，ONE_TIME→一次性订单 */
    function cycleTypeTxt(t) {
      return ({ MONTH: '月度', QUARTER: '季度', ONE_TIME: '一次性订单' }[t]) || '—';
    }

    /* 申报周期值文案（不含类型前缀，配合独立的「周期类型」列）：ONE_TIME/MONTH → 2026年12月，QUARTER → 2026年第4季度 */
    function cycleValueTxt(r) {
      if (!r || !r.cycleType || !r.cycleYear || !r.cycleValue) return '—';
      return r.cycleYear + '年' + (r.cycleType === 'QUARTER' ? '第' + r.cycleValue + '季度' : r.cycleValue + '月');
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
        { label: '单号', render: (r) => noLink(r.demandNo, () => demandDetail(r.demandId)) },
        { key: 'companyName', label: '企业' },
        /* 品类列展示矿种名称（PB粉/中华混一号），周期类型+申报周期两列分开展示 */
        { key: 'varietyName', label: '品类', render: (r) => r.varietyName || r.category || '-' },
        { label: '周期类型', render: (r) => cycleTypeTxt(r.cycleType) },
        { label: '申报周期', render: (r) => cycleValueTxt(r) },
        { key: 'quantity', label: '吨数(湿吨)', num: true, render: (r) => fmtQty(r.quantity) },
        { key: 'grade', label: '品位(%)', num: true },
        { label: '提货地点', render: (r) => {
            const t = { PORT_FOB: '港口离岸', PORT_TRUCK: '港口自提', PLANT: '场内自提' }[r.deliveryType] || '';
            return (r.deliveryPlace || '-') + (t ? '（' + t + '）' : '');
          } },
        { label: '预期到货时间', render: (r) => UI.fmtDate(r.expectArriveStart) + ' ~ ' + UI.fmtDate(r.expectArriveEnd) },
        { label: '归集单号', render: (r) => noLink(r.aggNo, () => aggDetail(r.aggId)) },
        { label: '询价单号', render: (r) => noLink(r.inquiryNo, () => inquiryModal(r.inquiryId, r.inquiryNo)) },
        { key: 'status', label: '状态', render: (r) => UI.statusTag('DEMAND', r.status) },
        { label: '提交日期', render: (r) => (r.submittedAt ? UI.fmtDate(r.submittedAt) : '-') },
        { label: '操作', render: (r) => UI.h('button', { class: 'sm', onclick: () => demandDetail(r.demandId) }, '详情') },
      ], demandRows, '暂无需求')));
      UI.pager(pagerBox, pageNo, SIZE, d.total, (p) => { pageNo = p; loadDemands(); });
    }

    /* 合并归集：勾选同品种同品位同周期分组的已提交明细 → 生成归集单（后端锁定量）。
       一次性订单明细 → 「订单归集」；月度/季度计划 → 「需求归集」（须申报周期一致），两类不可混合。
       存在同品种同品位同分组、未询价（OPEN）的归集单时，可选择并入已有单或生成新单。 */
    async function mergeAggregated() {
      if (!picked.size) { UI.toast('请先在列表中勾选需求明细（仅「已提交」状态可勾选）', 'err'); return; }
      const rows = demandRows.filter((r) => picked.has(r.id));
      const key = (r) => String(r.varietyName) + '@' + (r.grade == null ? '' : String(r.grade));
      if (new Set(rows.map(key)).size > 1) { UI.toast('仅同品种且同品位的明细可合并归集', 'err'); return; }
      const kindOf = (r) => (r.cycleType === 'ONE_TIME' || !r.cycleType) ? 'ORDER' : 'DEMAND';
      if (new Set(rows.map(kindOf)).size > 1) {
        UI.toast('一次性订单与月度/季度计划不可混合归集，请分开勾选分别归集', 'err'); return;
      }
      const kind = kindOf(rows[0]);
      const remain = rows.reduce((s, r) => s + (r.quantity - (r.inquiredQty || 0)), 0);
      if (remain <= 0) { UI.toast('勾选明细已无可归集量', 'err'); return; }
      const r0 = rows[0];
      /* 同品种同品位同分组、未询价（OPEN）的归集单：提供「并入已有 / 生成新单」选择 */
      let targetId = null;
      try {
        const openAggs = ((await API.get('/admin/aggregated-orders' + API.qs({ status: 'OPEN', kind, size: 100 }))).list || [])
          .filter((a) => a.varietyName === r0.varietyName && Number(a.grade) === Number(r0.grade));
        if (openAggs.length) {
          targetId = await new Promise((resolve) => {
            const sel = UI.selectField([['', '生成新归集订单']].concat(
              openAggs.map((a) => [String(a.id), a.aggNo + '（现有 ' + fmtQty(a.totalQty) + ' 湿吨）'])), '');
            const m = UI.modal('合并归集 · 选择目标归集订单', UI.h('form', { onsubmit: (e) => e.preventDefault() },
              UI.h('div', { class: 'hint', style: 'margin-bottom:8px' },
                '存在同品种同品位、未询价的归集订单，可将本次勾选明细并入其中，或生成新订单：'),
              UI.formRow('目标归集订单', sel, true)), [
              UI.h('button', { class: 'primary', onclick: () => {
                const v = sel.value ? Number(sel.value) : null;
                m.close(); resolve(v);
              } }, '确 定'),
            ]);
          });
        }
      } catch (e) { /* 查询失败按生成新订单处理 */ }
      if (!(await UI.confirmBox('将 ' + rows.length + ' 条明细（合计 ' + remain + ' 湿吨，全量锁定）'
        + (targetId ? '并入所选归集订单？' : '合并为新的归集订单？')))) return;
      try {
        const res = await API.post('/admin/aggregated-orders',
          targetId ? { itemIds: [...picked], aggId: targetId } : { itemIds: [...picked] });
        picked.clear();
        UI.toast((targetId ? '已并入' : '生成') + (res.kind === 'DEMAND' ? '需求归集 ' : '归集订单 ')
          + res.aggNo + '（' + res.totalQty + ' 湿吨）', 'ok');
        // 按周期分组跳转：月度/季度 → 需求归集页；一次性订单 → 订单归集页
        location.hash = res.kind === 'DEMAND' ? '#/demand-group' : '#/demand-aggr';
      } catch (e) { /* toast 已提示 */ }
    }

    async function loadAggr() {
      const d = await API.get('/admin/aggregated-orders' + API.qs({ kind: 'ORDER', status: aggStatus, page: aggPageNo, size: SIZE }));
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
        { label: '归集单号', render: (r) => noLink(r.aggNo, () => aggDetail(r.id)) },
        { key: 'varietyName', label: '矿种' },
        { key: 'grade', label: '品位(%)', num: true },
        { key: 'totalQty', label: '总吨数(湿吨)', num: true, render: (r) => fmtQty(r.totalQty) },
        { label: '参与钢厂', render: (r) => UI.h('div', { class: 'cell-xscroll', title: r.companyNames || '' }, r.companyNames || '-') },
        { key: 'memberCount', label: '钢厂数', num: true },
        { label: '询价单号', render: (r) => noLink(r.inquiryNo, () => inquiryModal(r.inquiryId, r.inquiryNo)) },
        { label: '询价状态', render: (r) => (r.inquiryStatus ? UI.statusTag('INQUIRY', r.inquiryStatus) : '—') },
        { label: '归集时间', render: (r) => UI.fmtDateTime(r.createdAt) },
        { label: '询价时间', render: (r) => (r.inquirySentAt ? UI.fmtDateTime(r.inquirySentAt) : '—') },
        { label: '操作', render: (r) => UI.h('span', { class: 'inline-flex' },
            UI.h('button', { class: 'sm', onclick: () => aggDetail(r.id) }, '详情')) },
      ], rows, '暂无归集订单（在需求列表勾选同品种同品位明细后点「合并归集」生成）')));
      UI.pager(pagerBox, aggPageNo, SIZE, d.total, (p) => { aggPageNo = p; loadAggr(); });
    }

    /* 需求归集：月度/季度计划合并归集结果（一次性订单归集在「订单归集」页）。
       此页归集单不用于询价，勾选后推送给供应商作为采购参考 */
    async function loadGroup() {
      const d = await API.get('/admin/aggregated-orders' + API.qs({ kind: 'DEMAND', status: aggStatus, page: aggPageNo, size: SIZE }));
      const rows = d.list || [];
      listBox.innerHTML = '';
      listBox.appendChild(UI.h('div', { class: 'hint', style: 'margin:0 0 8px' },
        '此页为月度/季度计划的需求归集，不用于询价：可勾选归集单推送给供应商，作为其采购参考'));
      listBox.appendChild(scrollWrap(UI.table([
        UI.selCol(groupPicked),
        { label: '序号', render: (r) => String((aggPageNo - 1) * SIZE + rows.indexOf(r) + 1) },
        { label: '归集单号', render: (r) => noLink(r.aggNo, () => aggDetail(r.id)) },
        { key: 'varietyName', label: '矿种' },
        { key: 'grade', label: '品位(%)', num: true },
        { key: 'totalQty', label: '总吨数(湿吨)', num: true, render: (r) => fmtQty(r.totalQty) },
        { label: '参与钢厂', render: (r) => UI.h('div', { class: 'cell-xscroll', title: r.companyNames || '' }, r.companyNames || '-') },
        { key: 'memberCount', label: '钢厂数', num: true },
        { label: '周期类型', render: (r) => cycleTypeTxt(r.cycleType) },
        { label: '申报周期', render: (r) => cycleValueTxt(r) },
        { label: '归集时间', render: (r) => UI.fmtDateTime(r.createdAt) },
        { label: '推送状态', render: (r) => r.pushedAt
          ? UI.h('span', { class: 'tag blue', title: '推送时间：' + UI.fmtDateTime(r.pushedAt) }, '已推送')
          : UI.h('span', { class: 'tag gray' }, '未推送') },
        { label: '操作', render: (r) => UI.h('button', { class: 'sm', onclick: () => aggDetail(r.id) }, '详情') },
      ], rows, '暂无需求归集（在需求列表勾选同品种同品位同周期的月度/季度计划后点「合并归集」生成）')));
      UI.pager(pagerBox, aggPageNo, SIZE, d.total, (p) => { aggPageNo = p; loadGroup(); });
    }

    /* 推送需求归集：勾选归集单 → 弹窗选择接收供应商（准入且启用）→ 确认推送（采购参考，非询价） */
    async function pushGroups() {
      if (!groupPicked.size) { UI.toast('请先勾选要推送的需求归集单', 'err'); return; }
      let opts;
      try { opts = (await API.get('/admin/supplier-options')).list || []; }
      catch (e) { return; /* toast 已提示 */ }
      if (!opts.length) { UI.toast('暂无可推送的准入供应商', 'err'); return; }
      const cbAll = () => box.querySelectorAll('input[type=checkbox]');
      const box = UI.h('div', {},
        UI.h('div', { class: 'hint', style: 'margin:0 0 10px' },
          '将勾选的 ' + groupPicked.size + ' 条需求归集推送给所选供应商，供应商可在其「需求归集」菜单查看归集详情（含钢厂参与明细）'),
        UI.h('div', { style: 'display:flex;align-items:center;gap:8px;margin-bottom:6px' },
          UI.h('span', { class: 'muted', style: 'font-size:12px;flex:1' }, '选择接收供应商（准入且启用）'),
          UI.h('button', { class: 'sm', onclick: () => cbAll().forEach((c) => { c.checked = true; }) }, '全选'),
          UI.h('button', { class: 'sm', onclick: () => cbAll().forEach((c) => { c.checked = false; }) }, '清空')),
        UI.h('div', { style: 'max-height:300px;overflow-y:auto;border:1px solid #e5e5ea;border-radius:8px;padding:8px 14px' },
          opts.map((s) => UI.h('label', { style: 'display:flex;align-items:center;gap:9px;padding:5px 0;cursor:pointer' },
            UI.h('input', { type: 'checkbox', 'data-id': s.id }),
            UI.h('span', {}, s.companyName || ('#' + s.id))))));
      const m = UI.modal('选择推送供应商', box, [
        UI.h('button', { class: 'primary', onclick: async () => {
          const supIds = Array.from(box.querySelectorAll('input[type=checkbox]:checked'))
            .map((c) => Number(c.dataset.id));
          if (!supIds.length) { UI.toast('请选择至少一家供应商', 'err'); return; }
          try {
            const res = await API.post('/admin/aggregated-orders/push',
              { ids: [...groupPicked], supplierIds: supIds });
            groupPicked.clear();
            UI.toast('已推送 ' + res.pushed + ' 条需求归集给 ' + res.suppliers + ' 家供应商', 'ok');
            loadGroup();
          } catch (e) { return; /* toast 已提示 */ }
          m.close();
        } }, '确认推送'),
      ]);
    }

    async function aggDetail(aid) {
      const d = await API.get('/admin/aggregated-orders/' + aid);
      const o = d.order;
      /* 取消归集：仅未询价（OPEN）且非按询价单归集（无来源询价单）的成员可移出 */
      const canCancel = (m) => o.status === 'OPEN' && !m.inquiryId;
      async function cancelAggItem(m) {
        if (!(await UI.confirmBox('将 ' + (m.companyName || '-') + ' 的 ' + (m.demandNo || '-')
          + '（' + fmtQty(m.quantity) + ' 湿吨）移出归集订单？'
          + '该需求将回到未归集前的「已提交」状态，可重新合并归集。'))) return;
        try {
          await API.put('/admin/aggregated-orders/' + aid + '/items/' + m.id + '/cancel');
          UI.toast('已取消归集：' + (m.demandNo || '-') + ' 已回到需求列表', 'ok');
          dlg.close();
          aggDetail(aid);
        } catch (e) { /* toast 已提示 */ }
      }
      const isDemand = o.aggKind === 'DEMAND';
      const dlg = UI.modal((isDemand ? '需求归集详情 · ' : '归集订单详情 · ') + o.aggNo, UI.h('div', {},
        /* 需求归集详情：仅展示归集单号/矿种/品位/总吨数/周期类型/申报周期/归集时间（不用于询价，无状态与备注） */
        UI.kv(isDemand ? [
          ['归集单号', o.aggNo],
          ['矿种', o.varietyName || '-'],
          ['品位(%)', o.grade == null ? '-' : String(o.grade)],
          ['总吨数(湿吨)', fmtQty(o.totalQty)],
          ['周期类型', cycleTypeTxt(o.cycleType)],
          ['申报周期', cycleValueTxt(o)],
          ['归集时间', UI.fmtDateTime(o.createdAt)],
        ] : [
          ['归集单号', o.aggNo],
          ['矿种', (o.varietyName || '-') + '（' + (o.category || '-') + '）'],
          ['品位(%)', o.grade == null ? '-' : String(o.grade)],
          ['总吨数(湿吨)', fmtQty(o.totalQty)],
          ['状态', UI.statusTag('AGG', o.status)],
          ['备注', o.remark || '-'],
          ['归集时间', UI.fmtDateTime(o.createdAt)],
        ]),
        UI.h('h3', { style: 'margin:14px 0 8px' }, isDemand ? '参与明细' : '参与明细（钢厂份额）'),
        scrollWrap(UI.h('table', { class: 'grid' },
          UI.h('thead', {}, UI.h('tr', {}, (isDemand
            ? ['钢厂', '矿种', '品位(%)', '数量(湿吨)', '预期到货时间']
            : ['钢厂', '需求单号', '矿种', '来源询价单', '询价状态', '归集份额(湿吨)', '操作'])
            .map((t) => UI.h('th', {}, t)))),
          UI.h('tbody', {}, (d.members || []).map((m) => isDemand
            ? UI.h('tr', {},
              UI.h('td', {}, m.companyName || '-'),
              UI.h('td', {}, m.varietyName || '-'),
              UI.h('td', { class: 'num' }, m.grade == null ? '-' : String(m.grade)),
              UI.h('td', { class: 'num' }, fmtQty(m.quantity)),
              /* 周期 = 预期到货时间范围 */
              UI.h('td', {}, m.expectArriveStart
                ? UI.fmtDate(m.expectArriveStart) + ' ~ ' + UI.fmtDate(m.expectArriveEnd) : '—'))
            : UI.h('tr', {},
              UI.h('td', {}, m.companyName || '-'),
              UI.h('td', {}, m.demandNo || '-'),
              UI.h('td', {}, m.varietyName || '-'),
              UI.h('td', {}, m.inquiryNo
                ? UI.h('a', { href: 'javascript:;', onclick: () => inquiryModal(m.inquiryId, m.inquiryNo) }, m.inquiryNo)
                : '—'),
              UI.h('td', {}, m.inquiryStatus ? UI.statusTag('INQUIRY', m.inquiryStatus) : '—'),
              UI.h('td', { class: 'num' }, fmtQty(m.quantity)),
              UI.h('td', {}, canCancel(m)
                ? UI.h('button', { class: 'sm', onclick: () => cancelAggItem(m) }, '取消归集')
                : UI.h('span', { class: 'muted' }, '—')))))))));
    }

    /* 单号超链接：点击跳转对应详情 */
    const noLink = (text, onclick) => (text
      ? UI.h('a', { href: 'javascript:;', style: 'color:#1a5cb0', onclick }, String(text))
      : '—');

    /* 询价单号点击：弹窗展示询价详情（基本信息 + 邀请与响应） */
    async function inquiryModal(iid, inquiryNo) {
      if (!iid) return;
      try {
        const d = await API.get('/inquiries/' + iid);
        UI.modal('询价详情 · ' + (d.inquiryNo || inquiryNo || ''), UI.h('div', {},
          UI.kv([
            ['询价单号', d.inquiryNo || inquiryNo],
            ['矿种', (d.varietyName || '-') + (d.grade != null ? ' / ' + d.grade + '%' : '')],
            ['吨数(湿吨)', fmtQty(d.quantity)],
            ['期望到货', UI.fmtDate(d.expectArriveDate)],
            ['询价说明', d.inquiry_desc || '-'],
            ['状态', UI.statusTag('INQUIRY', d.status)],
          ]),
          UI.h('h3', { style: 'margin:14px 0 8px' }, '邀请与响应'),
          scrollWrap(UI.table([
            { key: 'supplierName', label: '供应商' },
            { label: '邀请状态', render: (x) => (x.status === 'INVITED'
              ? UI.h('span', { class: 'tag blue' }, '已邀请')
              : UI.h('span', { class: 'tag gray' }, x.status)) },
            { label: '报价状态', render: (x) => (x.quoteStatus ? UI.statusTag('QUOTE', x.quoteStatus) : '-') },
            { label: '报价详情', render: (x) => (x.quoteId
              ? UI.h('button', { class: 'sm', onclick: () => quoteDetailModal(iid, x) }, '详情')
              : '-') },
          ], d.invites || [], '暂无邀请'))));
      } catch (e) { /* toast 已提示 */ }
    }

    function demandDetail(demandId) {
      const rows = demandRows.filter((r) => r.demandId === demandId);
      const head = rows[0] || {};
      /* 采购周期文案（与钢厂端需求单一致）：月度→2026年11月，季度→2026年第4季度，一次性订单→一次性订单（2026年12月） */
      const cyc = (r) => (r.cycleType === 'ONE_TIME')
        ? ((r.cycleYear && r.cycleValue) ? '一次性订单（' + r.cycleYear + '年' + r.cycleValue + '月）' : '一次性订单')
        : (r.cycleType && r.cycleYear && r.cycleValue)
          ? r.cycleYear + '年' + (r.cycleType === 'QUARTER' ? '第' + r.cycleValue + '季度' : r.cycleValue + '月')
          : '—';
      const items = rows.map((r) => [r.category || '-', r.varietyName, r.grade, cyc(r), r.quantity]);
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
            UI.h('th', {}, '品位(%)'),
            UI.h('th', {}, '采购周期'),
            UI.h('th', {}, '吨数(湿吨)'))),
          UI.h('tbody', {}, items.map(([cat, vn, g, cy2, q]) => UI.h('tr', {},
            UI.h('td', {}, String(cat)),
            UI.h('td', {}, String(vn || '-')),
            UI.h('td', { class: 'num' }, String(g == null ? '-' : g)),
            UI.h('td', {}, String(cy2)),
            UI.h('td', { class: 'num' }, fmtQty(q)))))))));
    }

    async function loadChanges() {
      const d = await API.get('/admin/demand-changes' + API.qs({ status: changeStatus, page: chPageNo, size: SIZE }));
      listBox.innerHTML = '';
      listBox.appendChild(scrollWrap(UI.table([
        UI.selCol(pickedCh),
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

    /* 变更差异行：中文字段名 + 值翻译，仅列出有变化的项（删除申请无内容差异） */
    function chgRows(r) {
      if ((r.afterData || {}).deleteRequest) return [];
      const DELIVERY = { PLANT: '到场', STATION_SELF: '到站自提', PORT_FOB: '港口FOB', PORT_TRUCK: '港口自提' };
      const SETTLE = { PREPAY: '现货现款', COD: '货到付款', CREDIT: '账期结算', INSTALLMENT: '分期' };
      const b = r.beforeData || {}, a = r.afterData || {};
      const rows = [];
      /* 数值归一化：8000.000 与 8600 按数值比较，展示去掉尾零 */
      const norm = (v) => {
        if (v == null || v === '') return '';
        const n = parseFloat(v);
        return isNaN(n) ? String(v) : String(n);
      };
      const push = (label, x, y) => {
        const nx = norm(x), ny = norm(y);
        if (nx !== ny) rows.push([label, nx, ny]);
      };
      const cyc = (it) => (it && it.cycleType === 'ONE_TIME')
        ? ((it.cycleYear && it.cycleValue)
          ? '一次性订单（' + it.cycleYear + '年' + it.cycleValue + '月）' : '一次性订单')
        : (!it || !it.cycleType ? '-' :
          (it.cycleYear || '-') + '年' + (it.cycleType === 'QUARTER'
            ? '第' + (it.cycleValue || '-') + '季度' : (it.cycleValue || '-') + '月'));
      push('需求名称', b.demandName, a.demandName);
      push('交货方式', DELIVERY[b.deliveryType] || b.deliveryType, DELIVERY[a.deliveryType] || a.deliveryType);
      push('交货地点', b.deliveryPlace || '-', a.deliveryPlace || '-');
      push('期望到货开始', b.expectArriveStart || '-', a.expectArriveStart || '-');
      push('期望到货结束', b.expectArriveEnd || '-', a.expectArriveEnd || '-');
      push('结算方式', SETTLE[b.settleType] || b.settleType, SETTLE[a.settleType] || a.settleType);
      push('账期天数', b.settleDays || '-', a.settleDays || '-');
      push('质量要求', b.qualityReq || '-', a.qualityReq || '-');
      const bi = (b.items || [])[0] || {}, ai = (a.items || [])[0] || {};
      push('品类', bi.varietyName, ai.varietyName);
      push('品位(%)', bi.grade, ai.grade);
      push('吨数(湿吨)', bi.quantity, ai.quantity);
      push('溢短装(%)', bi.moreLessRate, ai.moreLessRate);
      push('采购周期', cyc(bi), cyc(ai));
      return rows;
    }

    function changeSummary(r) {
      if ((r.afterData || {}).deleteRequest) return '删除申请（通过后需求单关闭）';
      return chgRows(r).map(([k, x, y]) => k + ' ' + (x == null ? '-' : x) + '→' + (y == null ? '-' : y)).join('；') || '-';
    }

    function changeDiff(r) {
      const rows = chgRows(r);
      if ((r.afterData || {}).deleteRequest) {
        return UI.h('div', { class: 'hint' },
          '该记录为删除申请：审核通过后需求单将关闭并自动移出未询价归集订单（份额释放）；驳回则需求回退删除前状态。');
      }
      if (!rows.length) return UI.h('div', { class: 'hint' }, '无变更明细');
      return scrollWrap(UI.h('table', { class: 'grid' },
        UI.h('thead', {}, UI.h('tr', {},
          UI.h('th', {}, '变更项'),
          UI.h('th', {}, '变更前'),
          UI.h('th', {}, '变更后'))),
        UI.h('tbody', {}, rows.map(([k, x, y]) => UI.h('tr', {},
          UI.h('td', {}, k),
          UI.h('td', { class: 'num' }, String(x == null ? '-' : x)),
          UI.h('td', { class: 'num' }, String(y == null ? '-' : y)))))),
        'margin-bottom:8px');
    }

    function auditModal(r) {
      const approve = UI.selectField([['true', '通过'], ['false', '驳回']], 'true');
      const remark = UI.h('textarea', { rows: 2, style: 'width:100%', placeholder: '审核意见（驳回必填）' });
      const m = UI.modal('变更申请 · ' + r.changeNo, UI.h('form', { onsubmit: (e) => e.preventDefault() },
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

  /* 需求归集二级菜单路由：需求列表 / 订单归集 / 需求归集 / 变更申请审核（复用同一页面，初始页签不同） */
  Pages.demand_list = function (page) { return Pages.demand_pool(page, 'demands'); };
  Pages.demand_aggr = function (page) { return Pages.demand_pool(page, 'aggr'); };
  Pages.demand_group = function (page) { return Pages.demand_pool(page, 'group'); };
  Pages.demand_changes = function (page) { return Pages.demand_pool(page, 'changes'); };

  /* -------- 询价报价：汇集需求代钢厂统一询价 → 汇总报价返回钢厂 -------- */
  Pages.quote_inquiry = async function (page) {
    const SIZE = 10;
    let pageNo = 1;
    let status = '';
    const picked = new Set(); // 行首勾选框（仅行选择展示）
    // 表格横向滚动容器：超宽时面板内右拉
    const scrollWrap = (node, style) => UI.h('div', { class: 'table-scroll-wrap', style }, node);

    /* 定高列表区 + 分页行同卡片（同需求归集）：横向滚动条固定在分页行上方 */
    const listBox = UI.h('div', { class: 'list-fixed' });
    const pagerBox = UI.h('div', {});
    /* 面板拆分：标题面板（标题+筛选）与数据面板（操作+表格）两块独立 */
    page.appendChild(UI.h('div', { class: 'card' },
      UI.h('div', { class: 'toolbar stacked' },
        UI.h('h3', { style: 'margin:0;border:none;padding:0' }, '询价报价'),
        UI.h('div', { class: 'spacer' }),
        UI.statusFilter('INQUIRY', (v) => { status = v; pageNo = 1; load(); }))));
    page.appendChild(UI.h('div', { class: 'card' },
      UI.h('div', { class: 'toolbar' },
        UI.h('button', { class: 'primary', onclick: () => createModal() }, '发起询价')),
      listBox,
      pagerBox));
    await load();

    // 从需求归集「去询价」跳转过来：自动弹出发起询价弹窗并带入勾选的归集订单
    const seedAgg = sessionStorage.getItem('agg_inquiry_seed');
    if (seedAgg) {
      sessionStorage.removeItem('agg_inquiry_seed');
      createModal(seedAgg);
    }

    async function load() {
      const d = await API.get('/admin/quote-inquiries' + API.qs({ status, page: pageNo, size: SIZE }));
      listBox.innerHTML = '';
      listBox.appendChild(scrollWrap(UI.table([
        UI.selCol(picked),
        { label: '序号', render: (r) => String((pageNo - 1) * SIZE + d.list.indexOf(r) + 1) },
        { label: '询价单号', render: (r) => UI.h('a', {
            href: 'javascript:;', style: 'color:#1a5cb0', onclick: () => detailModal(r) }, r.inquiryNo) },
        { key: 'batchNo', label: '批次' },
        { label: '归集单号', render: (r) => (r.aggNo
            ? UI.h('a', { href: 'javascript:;', style: 'color:#1a5cb0', onclick: () => aggModal(r.aggId) }, r.aggNo)
            : (r.demandNo || '-')) },
        { key: 'varietyName', label: '矿种' },
        { key: 'quantity', label: '吨数(湿吨)', num: true, render: (r) => fmtQty(r.quantity) },
        { label: '交货地点', render: (r) => r.deliveryPlace || '-' },
        { key: 'status', label: '状态', render: (r) => UI.statusTag('INQUIRY', r.status) },
        { label: '响应', render: (r) => r.responded + '/' + r.invited },
        { label: '操作', render: (r) => UI.h('span', { class: 'inline-flex' },
            UI.h('button', { class: 'sm', onclick: () => detailModal(r) }, '详情'),
            r.status === 'FEEDBACK'
              ? UI.h('button', { class: 'sm primary', onclick: () => requoteModal(r) }, '重新询价') : null,
            r.status !== 'FAILED' && r.status !== 'DRAFT'
              ? UI.h('button', {
                  class: (r.status === 'SENT' || r.status === 'QUOTING') && !r.revealed ? 'sm primary' : 'sm',
                  onclick: () => summaryModal(r),
                }, (r.status === 'SENT' || r.status === 'QUOTING') && !r.revealed ? '汇总报价返回钢厂' : '报价汇总')
              : null) },
      ], d.list, '暂无询价单')));
      UI.pager(pagerBox, pageNo, SIZE, d.total, (p) => { pageNo = p; load(); });
    }

    /* 重新询价（钢厂反馈不认可后）：直接在本行发起，带回该归集订单与钢厂反馈意见 */
    async function requoteModal(r) {
      if (!r.aggId) { UI.toast('该询价单无关联归集订单，无法重新询价', 'err'); return; }
      const d = await API.get('/admin/quote-inquiries/' + r.id + '/feedbacks');
      const lines = (d.list || []).map((f) => f.companyName
        + (f.decision === 'ACCEPTED' ? ' 认可' : ' 不认可')
        + (f.reason ? '（' + f.reason + '）' : ''));
      const preset = lines.length
        ? '钢厂反馈（上一轮 ' + r.inquiryNo + '）：' + lines.join('；') + '。请据此调整采购条件后重新报价。'
        : '';
      createModal(r.aggId, preset);
    }

    /* 发起询价：引用归集订单整单询价 + 统一询价条件 + 邀请供应商（仅归集询价）
       seedAggId：从「去询价」跳转带入时预选该归集订单 */
    async function createModal(seedAggId, presetRemark) {
      const d = await API.get('/admin/aggregated-orders' + API.qs({ kind: 'ORDER', size: 100 }));
      // OPEN=首次询价；INQUIRING=钢厂不认可等场景下可再次发起（无在途询价时）；仅一次性订单归集可发起询价
      const aggs = (d.list || []).filter((a) => a.status === 'OPEN' || a.status === 'INQUIRING');
      if (!aggs.length) { UI.toast('暂无可发起询价的归集订单（请先在需求归集页勾选明细合并生成）', 'err'); return; }
      const seedOk = seedAggId && aggs.some((a) => String(a.id) === String(seedAggId));
      const aggSel = UI.selectField(aggs.map((a) => [String(a.id),
        a.aggNo + ' · ' + a.varietyName + ' · ' + (a.grade == null ? '-' : a.grade) + '% · '
        + a.totalQty + '湿吨 · ' + a.memberCount + '家钢厂']),
        String(seedOk ? seedAggId : aggs[0].id));
      const arrive = UI.input('date', new Date(Date.now() + 18 * 86400000).toISOString().slice(0, 10));
      /* 期望到货日默认取所选归集单内各钢厂预期到货最早日（运营可手动更改） */
      function applyAggArrive(aid) {
        if (!aid) return;
        API.get('/admin/aggregated-orders/' + aid).then((det) => {
          const ds = (det.members || []).map((mm) => String(mm.expectArriveStart || '').slice(0, 10))
            .filter(Boolean).sort();
          if (ds.length && ds[0] !== arrive.value) {
            arrive.value = ds[0];
          }
        }).catch(() => { /* 拉取失败保留默认 */ });
      }
      aggSel.addEventListener('change', () => applyAggArrive(aggSel.value));
      applyAggArrive(aggSel.value);
      const cs = (await API.get('/companies' + API.qs({ type: 'SUPPLIER', size: 100 }))).list || [];
      const supChks = cs.map((c) => {
        const chk = UI.h('input', { type: 'checkbox' });
        chk.dataset.supplierId = c.id;
        return chk;
      });
      const supLabels = cs.map((c, i) => UI.h('label',
        { style: 'display:inline-flex;align-items:center;gap:6px;margin:4px 16px 4px 0' }, supChks[i], c.companyName));
      const remark = UI.h('textarea', { rows: 3, style: 'width:100%', placeholder: '询价说明（选填）' });
      if (presetRemark) remark.value = presetRemark;  // 重新询价：自动带入钢厂反馈意见
      const errBox = UI.h('div', { class: 'hint', style: 'color:#c0392b' });
      const m = UI.modal('发起询价 · 归集订单统一询价' + (presetRemark ? '（重新询价）' : ''), UI.h('form', { onsubmit: (e) => e.preventDefault() },
        UI.h('h3', { style: 'margin:0 0 8px' }, '选择归集订单'),
        UI.h('div', { class: 'form-row full' }, UI.h('label', { class: 'req' }, '归集订单'), aggSel),
        UI.h('h3', { style: 'margin:14px 0 8px' }, '统一询价条件'),
        UI.h('div', { class: 'form-grid' },
          UI.formRow('期望到货日', arrive, true)),
        UI.h('div', { class: 'form-row full' }, UI.h('label', { class: 'req' }, '邀请供应商'),
          UI.h('div', {}, supLabels)),
        UI.h('div', { class: 'form-row full' }, UI.h('label', {}, '询价说明'), remark),
        errBox), [
        UI.h('button', { class: 'primary', onclick: async () => {
          errBox.textContent = '';
          if (!aggSel.value) { errBox.textContent = '请选择归集订单'; return; }
          if (!arrive.value) { errBox.textContent = '请填写期望到货日'; return; }
          const supIds = supChks.filter((el) => el.checked).map((el) => Number(el.dataset.supplierId));
          if (!supIds.length) { errBox.textContent = '至少邀请一家供应商'; return; }
          try {
            const res = await API.post('/admin/quote-inquiries', {
              aggOrderId: Number(aggSel.value),
              arriveDate: arrive.value,
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

    /* 归集单号点击：跳转归集订单详情（钢厂 × 需求 × 份额） */
    async function aggModal(aid) {
      if (!aid) return;
      const d = await API.get('/admin/aggregated-orders/' + aid);
      const o = d.order || {};
      UI.modal('归集订单详情 · ' + (o.aggNo || ''), UI.h('div', {},
        UI.kv([
          ['归集单号', o.aggNo || '-'],
          ['矿种', (o.varietyName || '-') + (o.category ? '（' + o.category + '）' : '')],
          ['品位(%)', o.grade == null ? '-' : o.grade],
          ['总吨数(湿吨)', fmtQty(o.totalQty)],
          ['状态', UI.statusTag('AGG', o.status)],
          ['备注', o.remark || '-'],
          ['归集时间', UI.fmtDateTime(o.createdAt)],
        ]),
        UI.h('h3', { style: 'margin:14px 0 8px' }, '参与明细（钢厂份额）'),
        scrollWrap(UI.table([
          { key: 'companyName', label: '钢厂' },
          { key: 'demandNo', label: '需求单号' },
          { key: 'varietyName', label: '矿种' },
          { label: '归集份额(湿吨)', num: true, render: (m) => fmtQty(m.quantity) },
        ], d.members || [], '暂无明细'))));
    }

    async function detailModal(r) {
      const d = await API.get('/inquiries/' + r.id);
      // 归集询价：钢厂反馈（认可/不认可 + 原因）并入详情展示
      let fbs = [];
      if (r.aggId) {
        fbs = ((await API.get('/admin/quote-inquiries/' + r.id + '/feedbacks')).list) || [];
      }
      UI.modal('询价详情 · ' + r.inquiryNo, UI.h('div', {},
        UI.kv([
          ['询价单号', r.inquiryNo],
          ['批次', r.batchNo || '-'],
          ['需求单号', r.demandNo || '-'],
          ['归集单号', r.aggNo || '-'],
          ['钢厂', r.companyName],
          ['矿种', d.varietyName || r.varietyName],
          ['吨数(湿吨)', fmtQty(r.quantity)],
          ['品位(%)', r.grade == null ? '-' : r.grade],
          ['期望到货', UI.fmtDate(r.expectArriveDate)],
          ['询价说明', d.inquiry_desc || '-'],
          ['状态', UI.statusTag('INQUIRY', r.status)],
        ]),
        UI.h('h3', { style: 'margin:14px 0 8px' }, '邀请与响应'),
        scrollWrap(UI.table([
          { key: 'supplierName', label: '供应商' },
          { key: 'status', label: '邀请状态', render: (x) => x.status === 'INVITED' ? UI.h('span', { class: 'tag blue' }, '已邀请') : UI.h('span', { class: 'tag gray' }, x.status) },
          { key: 'quoteStatus', label: '报价状态', render: (x) => x.quoteStatus ? UI.statusTag('QUOTE', x.quoteStatus) : '-' },
          { label: '报价详情', render: (x) => (x.quoteId
            ? UI.h('button', { class: 'sm', onclick: () => quoteDetailModal(r.id, x) }, '详情')
            : '-') },
        ], d.invites || [], '暂无邀请')),
        r.aggId ? UI.h('div', {},
          UI.h('h3', { style: 'margin:14px 0 8px' }, '钢厂反馈'),
          UI.h('div', { class: 'hint', style: 'margin-bottom:8px' },
            '归集订单：' + (r.aggNo || '-') + ' · 反馈后请结合比价结果决定是否重新发起询价'),
          fbs.length
            ? UI.table([
                { key: 'companyName', label: '钢厂' },
                { label: '反馈结论', render: (row) => row.decision === 'ACCEPTED'
                    ? UI.h('span', { class: 'tag green' }, '认可')
                    : UI.h('span', { class: 'tag red' }, '不认可') },
                { label: '原因', render: (row) => row.reason || '-' },
                { label: '反馈时间', render: (row) => row.createdAt },
              ], fbs)
            : UI.h('div', { class: 'empty' }, '无钢厂进行反馈')) : null,
        UI.h('div', { class: 'hint', style: 'margin-top:8px' }, d.notice || '')));
    }

    async function summaryModal(r) {
      const d = await API.get('/admin/quote-inquiries/' + r.id + '/summary');
      const quotes = d.quotes || [];
      const spotMap = await UI.spotPrices();   // 报价模式单价：品种→港口现货价
      const canReturn = (r.status === 'SENT' || r.status === 'QUOTING') && !r.revealed;
      // 按份额定标：仅归集询价、已截止（已揭示）时可操作
      const canAward = !!r.aggId && r.status === 'CLOSED';
      let shares = [];
      if (canAward) {
        const ad = await API.get('/admin/aggregated-orders/' + r.aggId);
        const byCompany = {};
        (ad.members || []).forEach((x) => {
          byCompany[x.companyName] = (byCompany[x.companyName] || 0) + Number(x.quantity);
        });
        shares = Object.keys(byCompany).map((k) => ({ name: k, qty: byCompany[k] }));
      }
      const m = UI.modal((canReturn ? '汇总报价返回钢厂 · ' : '报价汇总 · ') + r.inquiryNo, UI.h('div', {},
        UI.h('div', { class: 'hint', style: 'margin-bottom:8px' },
          '钢厂 ' + (r.companyName || '-') + ' · 矿种 ' + (r.varietyName || '-') + ' · 询价 ' + fmtQty(r.quantity) + ' 湿吨 · 报价 ' + quotes.length + ' 家（价格升序）'),
        scrollWrap(UI.table([
          { label: '序号', render: (x) => String(quotes.indexOf(x) + 1) },
          { key: 'quoteNo', label: '报价单号' },
          { key: 'companyName', label: '供应商' },
          { label: '单价(元/湿吨)', num: true,
            render: (x) => UI.spotShown(x.priceSign, x.priceFloat)
              || UI.spotDiff(spotMap[x.varietyName || r.varietyName], x.price) },
          { key: 'taxType', label: '是否含税', render: (x) => ({ INC_TAX: '含税', EX_TAX: '不含税' }[x.taxType] || '-') },
          { key: 'freightPrice', label: '运费(元/湿吨)', num: true,
            render: (x) => (x.freightPrice != null ? UI.fmtMoney(x.freightPrice) : '-') },
          { key: 'quantity', label: '可供数量(湿吨)', num: true, render: (x) => fmtQty(x.quantity) },
          { key: 'deliveryDate', label: '预计到港时间', render: (x) => UI.fmtDate(x.deliveryDate) },
          { key: 'deliveryPlace', label: '港口', render: (x) => x.deliveryPlace || '-' },
          { label: '操作', render: (x) => (canAward
              ? UI.h('button', { class: 'sm primary', onclick: () => awardQuote(r, x, shares, m) }, '定标')
              : '-') },
        ], quotes, '暂无报价')),
        canAward ? UI.h('div', { class: 'hint', style: 'margin-top:8px' },
          '按份额定标：整单锁货锁价，将生成 1 张订单并向各钢厂收集提货计划。'
          + '份额预览：' + shares.map((s) => s.name + ' ' + fmtQty(s.qty) + ' 湿吨').join('；')
          + '（合计 ' + fmtQty(shares.reduce((a, b) => a + b.qty, 0)) + ' 湿吨）') : null,
        canReturn ? UI.h('div', { class: 'hint', style: 'margin-top:8px' },
          '确认后报价将揭示给钢厂（钢厂端「询价报价」页即可查看比价），并站内通知钢厂。') : null),
        canReturn ? [UI.h('button', { class: 'primary', onclick: async () => {
          try {
            const res = await API.post('/admin/quote-inquiries/' + r.id + '/return', {});
            m.close();
            UI.toast('已汇总 ' + res.quoteCount + ' 家报价并推送钢厂', 'ok');
            load();
          } catch (e) { /* toast 已提示 */ }
        } }, '确认汇总并返回钢厂')] : [], { wide: true });
    }

    /* 按份额定标：整单锁货锁价，只生成 1 张订单，并向各钢厂收集提货计划 */
    async function awardQuote(r, q, shares, modal) {
      const total = shares.reduce((a, b) => a + b.qty, 0);
      if (total > Number(q.quantity)) {
        UI.toast('该报价可供量不足定标总量，请选择其他报价', 'err');
        return;
      }
      if (!(await UI.confirmBox('按 ' + q.companyName + ' 的报价 ' + UI.fmtMoney(q.price)
          + ' 元/湿吨定标？整单锁货锁价，将生成 1 张订单（合计 ' + fmtQty(total)
          + ' 湿吨）并向各钢厂收集提货计划，其余报价置为未中标。'))) return;
      try {
        const res = await API.post('/admin/quote-inquiries/' + r.id + '/award', { quoteId: q.id });
        modal.close();
        UI.toast('已定标，生成订单 ' + res.orderNo + '，待 ' + res.memberCount + ' 家钢厂提交提货计划', 'ok');
        load();
      } catch (e) { /* toast 已提示 */ }
    }
  };

  /* -------- 询价历史（按轮次追溯历史报价与钢厂反馈） -------- */
  Pages.quote_history = async function (page) {
    const SIZE = 10;
    let pageNo = 1;
    const picked = new Set(); // 行首勾选框（仅行选择展示）
    const scrollWrap = (node) => UI.h('div', { class: 'table-scroll-wrap' }, node);
    /* 定高列表区 + 分页行同卡片（同需求归集）：横向滚动条固定在分页行上方 */
    const listBox = UI.h('div', { class: 'list-fixed' });
    const pagerBox = UI.h('div', {});
    /* 面板拆分：工具栏（标题+说明）与表格数据分为两块独立面板 */
    page.appendChild(UI.h('div', { class: 'card' },
      UI.h('div', { class: 'toolbar' },
        UI.h('h3', { style: 'margin:0;border:none;padding:0' }, '询价历史'),
        UI.h('div', { class: 'spacer' }),
        UI.h('span', { class: 'hint' }, '按轮次记录每轮询价、全部报价与钢厂反馈，重新询价后历史不丢失'))));
    page.appendChild(UI.h('div', { class: 'card' },
      listBox,
      pagerBox));
    await load();

    async function load() {
      const d = await API.get('/admin/quote-history' + API.qs({ page: pageNo, size: SIZE }));
      listBox.innerHTML = '';
      listBox.appendChild(scrollWrap(UI.table([
        UI.selCol(picked),
        { label: '序号', render: (r) => String((pageNo - 1) * SIZE + d.list.indexOf(r) + 1) },
        { label: '归集单号', render: (r) => r.aggNo || '-' },
        { label: '询价单号', render: (r) => UI.h('a', {
            href: 'javascript:;', style: 'color:#1a5cb0', onclick: () => detail(r) }, r.inquiryNo) },
        { key: 'batchNo', label: '批次' },
        { key: 'varietyName', label: '矿种' },
        { label: '吨数(湿吨)', num: true, render: (r) => fmtQty(r.quantity) },
        { label: '操作', render: (r) => UI.h('button', { class: 'sm', onclick: () => detail(r) }, '历史明细') },
      ], d.list, '暂无历史询价（平台代发后自动记录）')));
      UI.pager(pagerBox, pageNo, SIZE, d.total, (p) => { pageNo = p; load(); });
    }

    /* 单轮历史明细：本轮全部报价 + 本轮钢厂反馈（只读留痕） */
    async function detail(r) {
      const d = await API.get('/admin/quote-history/' + r.id);
      const inq = d.inquiry || {};
      UI.modal('询价历史明细 · ' + inq.inquiryNo, UI.h('div', {},
        UI.kv([
          ['归集单号', inq.aggNo || '-'],
          ['询价单号', inq.inquiryNo],
          ['批次', inq.batchNo || '-'],
          ['矿种', inq.varietyName || '-'],
          ['吨数(湿吨)', fmtQty(inq.quantity)],
          ['交货地点', inq.deliveryPlace || '-'],
          ['发出时间', inq.sentAt || '-'],
          ['状态', UI.statusTag('INQUIRY', inq.status)],
          ['询价说明', inq.inquiryDesc || '-'],
        ]),
        UI.h('h3', { style: 'margin:14px 0 8px' }, '历史报价（' + (d.quotes || []).length + ' 家）'),
        (d.quotes || []).length ? scrollWrap(UI.table([
          { key: 'quoteNo', label: '报价单号' },
          { key: 'companyName', label: '供应商' },
          { label: '单价(元/湿吨)', num: true, render: (x) => UI.fmtMoney(x.price) },
          { label: '可供数量(湿吨)', num: true, render: (x) => fmtQty(x.quantity) },
          { label: '到货日', render: (x) => UI.fmtDate(x.deliveryDate) },
          { key: 'payTerms', label: '付款条款', render: (x) => x.payTerms || '-' },
          { key: 'quotedAt', label: '报价时间' },
          { key: 'status', label: '报价状态', render: (x) => UI.statusTag('QUOTE', x.status) },
        ], d.quotes)) : UI.h('div', { class: 'empty' }, '本轮暂无报价'),
        UI.h('h3', { style: 'margin:14px 0 8px' }, '钢厂反馈（' + (d.feedbacks || []).length + ' 家）'),
        (d.feedbacks || []).length ? UI.table([
          { key: 'companyName', label: '钢厂' },
          { label: '反馈结论', render: (x) => (x.decision === 'ACCEPTED'
            ? UI.h('span', { class: 'tag green' }, '认可')
            : UI.h('span', { class: 'tag red' }, '不认可')) },
          { label: '原因', render: (x) => x.reason || '-' },
          { key: 'createdAt', label: '反馈时间' },
        ], d.feedbacks) : UI.h('div', { class: 'empty' }, '无钢厂进行反馈')), null, { wide: true });
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
    page.appendChild(varCard);
    await load();

    async function load() {
      const vars = (await API.get('/base/varieties')).list || [];
      varCard.innerHTML = '';
      varCard.appendChild(UI.h('h3', {}, '品种列表'));
      /* 定高列表区（品种为少量基础数据，不设分页，面板高度与其他表格面板统一） */
      const pickedRows = new Set(); // 行首勾选框（仅行选择展示）
      const listBox = UI.h('div', { class: 'list-fixed' });
      listBox.appendChild(UI.table([
        UI.selCol(pickedRows),
        { key: 'varietyCode', label: '品种代码' },
        { key: 'varietyName', label: '品种名称' },
        { key: 'category', label: '品类', render: (r) => r.category || '-' },
        { key: 'defaultGrade', label: '默认品位(%)' },
        { key: 'unit', label: '计量单位' },
        { key: 'status', label: '状态' },
        { label: '操作', render: (r) => UI.h('button', { class: 'sm', onclick: () => categoryForm(r) }, '改品类') },
      ], vars, '暂无品种'));
      varCard.appendChild(listBox);
    }

    function varietyForm() {
      const code = UI.input('text', '', { placeholder: '如 PB、FMG' });
      const name = UI.input('text', '', { placeholder: '如 PB 粉、高品位铁矿' });
      const category = UI.input('text', '', { placeholder: '如 粉矿、块矿、球团、混矿' });
      const grade = UI.input('text', '', { placeholder: '如 61.5（品位百分数，纯数字）' });
      const unit = UI.input('text', '湿吨', { placeholder: '计量单位，默认 湿吨' });
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
  };

  /* -------- 订单管理（集采订单：提货计划汇总 → 运输方案） -------- */
  Pages.order_admin = async function (page) {
    let pageNo = 1;
    const SIZE = 10;
    let status = '';
    let keyword = '';
    const picked = new Set(); // 行首勾选框（仅行选择展示）
    const scrollWrap = (node) => UI.h('div', { class: 'table-scroll-wrap' }, node);
    /* 定高列表区 + 分页行同卡片（同需求归集）：横向滚动条固定在分页行上方 */
    const listBox = UI.h('div', { class: 'list-fixed' });
    const pagerBox = UI.h('div', {});
    const kw = UI.input('text', '', { placeholder: '订单号（模糊）', style: 'width:180px' });
    const search = () => { keyword = kw.value.trim(); pageNo = 1; load(); };
    /* 面板拆分：标题面板（标题+筛选/查询，全为筛选类）与数据面板两块独立 */
    page.appendChild(UI.h('div', { class: 'card' },
      UI.h('div', { class: 'toolbar stacked' },
        UI.h('h3', { style: 'margin:0;border:none;padding:0' }, '订单管理'),
        UI.h('div', { class: 'spacer' }),
        UI.statusFilter('ORDER', (v) => { status = v; pageNo = 1; load(); }),
        kw,
        UI.h('button', { class: 'primary', onclick: search }, '查询'))));
    page.appendChild(UI.h('div', { class: 'card' },
      listBox,
      pagerBox));
    await load();

    async function load() {
      const d = await API.get('/admin/orders' + API.qs({ page: pageNo, size: SIZE, status, keyword }));
      const spotMap = await UI.spotPrices();   // 报价模式单价：品种→港口现货价
      listBox.innerHTML = '';
      listBox.appendChild(scrollWrap(UI.table([
        UI.selCol(picked),
        { key: 'orderNo', label: '订单号' },
        { label: '询价单号', render: (r) => r.inquiryNo || '-' },
        { key: 'varietyName', label: '矿种' },
        { key: 'grade', label: '品位(%)' },
        { label: '总吨数(湿吨)', num: true, render: (r) => fmtQty(r.totalQty) },
        { label: '单价(元/湿吨)', num: true,
          render: (r) => UI.spotShown(r.priceSign, r.priceFloat) || UI.spotDiff(spotMap[r.varietyName], r.unitPrice) },
        { label: '运费(元/湿吨)', num: true, render: (r) => (r.freightPrice != null ? UI.fmtMoney(r.freightPrice) : '-') },
        { label: '供应商', render: (r) => r.supplierName || '-' },
        { label: '参与钢厂数', num: true, render: (r) => String(r.millCount || 0) },
        { label: '提货计划', render: (r) => (r.millCount
            ? r.pickupDoneCount + '/' + r.millCount + ' 已提交' : '-') },
        { label: '状态', render: (r) => UI.statusTag('ORDER', r.status) },
        { label: '创建时间', render: (r) => UI.fmtDateTime(r.createdAt) },
        { label: '操作', render: (r) => UI.h('span', { class: 'inline-flex' },
          UI.h('button', { class: 'sm', onclick: () => detail(r) }, '详情'),
          UI.h('button', { class: 'sm primary', onclick: () => { location.hash = '#/logistics-dispatch'; } }, '运输方案')) },
      ], d.list, '暂无订单')));
      pagerBox.innerHTML = '';
      UI.pager(pagerBox, pageNo, SIZE, d.total, (p) => { pageNo = p; load(); });
    }

    async function detail(r) {
      const d = await API.get('/admin/orders/' + r.id);
      const spotMap = await UI.spotPrices();   // 报价模式单价：品种→港口现货价
      const members = d.members || [];
      const sum = d.pickupSummary || { totalMills: 0, doneMills: 0 };
      const pickupTag = (s) => (s === 'SUBMITTED'
        ? UI.h('span', { class: 'tag green' }, '已提交')
        : UI.h('span', { class: 'tag orange' }, '未提交'));
      /* 订单完成确认情况：供应商 + 各钢厂成员（传统单看需方行）；全部确认后订单状态自动已完成 */
      const finishTag = (at) => (at
        ? UI.h('span', { class: 'tag green' }, UI.fmtDateTime(at))
        : UI.h('span', { class: 'tag orange' }, '未确认'));
      const finishRows = [{ name: d.supplierName || '-', role: '供应商', at: d.supplierFinishConfirmAt }]
        .concat(members.length
          ? members.map((m) => ({ name: m.companyName, role: '钢厂成员', at: m.finishConfirmAt }))
          : [{ name: d.buyerFinishName || '需方钢厂', role: '钢厂（需方）', at: d.buyerFinishConfirmAt }]);
      UI.modal('订单详情 · ' + d.orderNo, UI.h('div', {},
        UI.kv([
          ['订单号', d.orderNo],
          ['询价单号', d.inquiryNo || '-'],
          ['归集单号', d.aggNo || '-'],
          ['矿种', d.varietyName || '-'],
          ['品位(%)', d.grade],
          ['总吨数(湿吨)', fmtQty(d.totalQty)],
          ['单价(元/湿吨)', UI.spotShown(d.priceSign, d.priceFloat)
            || UI.spotDiff(spotMap[d.varietyName], d.unitPrice)],
          ['运费(元/湿吨)', d.freightPrice != null ? UI.fmtMoney(d.freightPrice) : '-'],
          ['供应商', d.supplierName || '-'],
          ['交货地点', d.deliveryPlace || '-'],
          ['预计到港时间', UI.fmtDate(d.deliveryDate)],
          ['状态', UI.statusTag('ORDER', d.status)],
          ['创建时间', UI.fmtDateTime(d.createdAt)],
          ['提货计划', sum.doneMills + '/' + sum.totalMills + ' 已提交'],
        ]),
        UI.h('h3', { style: 'margin:14px 0 8px' }, '提货计划明细'),
        members.length ? scrollWrap(UI.table([
          { key: 'companyName', label: '钢厂' },
          { label: '份额吨数', num: true, render: (m) => fmtQty(m.quantity) },
          { label: '开始提货日期', render: (m) => (m.pickupStartDate ? UI.fmtDate(m.pickupStartDate) : '未提交') },
          { label: '日提货吨数', num: true, render: (m) => (m.pickupStatus === 'SUBMITTED' ? fmtQty(m.dailyQty) : '未提交') },
          { label: '备注', render: (m) => m.pickupRemark || '-' },
          { label: '状态', render: (m) => pickupTag(m.pickupStatus) },
          { label: '提交时间', render: (m) => (m.submittedAt ? UI.fmtDateTime(m.submittedAt) : '未提交') },
        ], members)) : UI.h('div', { class: 'empty' }, '暂无参与钢厂'),
        UI.h('h3', { style: 'margin:14px 0 8px' }, '订单完成确认情况'),
        UI.table([
          { key: 'name', label: '企业' },
          { key: 'role', label: '角色' },
          { label: '确认时间', render: (x) => finishTag(x.at) },
        ], finishRows)), null, { wide: true });
    }
  };

  /* -------- 预警处理 -------- */
  Pages.alerts = async function (page) {
    let pageNo = 1;
    const SIZE = 10;
    let status = '';
    const picked = new Set(); // 行首勾选框（仅行选择展示）
    /* 定高列表区 + 分页行同卡片（同需求归集）：横向滚动条固定在分页行上方 */
    const listBox = UI.h('div', { class: 'list-fixed' });
    const pagerBox = UI.h('div', {});
    page.appendChild(UI.h('div', { class: 'card' },
      UI.h('div', { class: 'toolbar' },
        UI.h('h3', { style: 'margin:0;border:none;padding:0' }, '预警处理'),
        UI.h('div', { class: 'spacer' }),
        UI.statusFilter('ALERT', (v) => { status = v; pageNo = 1; load(); })),
      listBox,
      pagerBox));
    await load();

    async function load() {
      const d = await API.get('/alerts' + API.qs({ status, page: pageNo, size: SIZE }));
      listBox.innerHTML = '';
      listBox.appendChild(UI.table([
        UI.selCol(picked),
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
          SENT: '询价已发送给受邀供应商，等待供应商报价',
          QUOTING: '已有供应商提交报价，持续接收报价中',
          CLOSED: '询价已截止，进入比价、议价与定标环节',
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
          PENDING_EFFECT: '双方已上传签署件，等待运营端合同归集生效',
          PERFORMING: '合同已生效，进入发货、运输、签收与验收环节（付款结算线下完成）',
          COMPLETED: '供需双方确认验收完成，订单归档',
          CANCELLED: '订单被取消或超时未确认而失效',
        },
        notes: ['合同作废后，订单会退回"待签合同"，重新走合同生成与签署流程'],
      },
      biz_contract: {
        label: '合同', kind: 'CONTRACT',
        intro: '订单确认后由系统生成合同，双方线下签署并上传签署件，运营端归集后生效。',
        desc: {
          PENDING_GENERATE: '订单确认后等待生成合同文本',
          PENDING_BUYER: '合同已生成，线下签署中，等待需方（钢厂）上传签署件',
          PENDING_SUPPLIER: '需方已上传，线下签署中，等待供应商上传签署件',
          EFFECTIVE: '双方签署件已由运营端归集，合同正式生效，可据此履约',
          VOID: '合同已作废，需重新生成并签署',
        },
        notes: ['合同为线下签署：双方分别上传本方签署件，运营端「合同归集」完成后合同生效；已生效的合同不可作废'],
      },
      biz_waybill: {
        label: '运单', kind: 'WAYBILL',
        intro: '合同生效后按物流方案生成的运输单据，跟踪货物从发运到签收。',
        desc: {
          PENDING_DEPART: '运单已确认生效（平台承担运输），等待发运',
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

  /* -------- 操作日志（内容全中文展示：动作/业务类型/状态/变更内容键值均做中文映射） -------- */
  Pages.logs = async function (page) {
    let pageNo = 1;
    const SIZE = 10;
    const bizType = UI.input('text', '', { placeholder: '业务类型编码（可选）', style: 'width:160px' });
    const bizId = UI.input('text', '', { placeholder: '业务ID', style: 'width:100px' });
    const picked = new Set(); // 行首勾选框（仅行选择展示）
    /* 定高列表区 + 分页行同卡片（同需求归集） */
    const listBox = UI.h('div', { class: 'list-fixed' });
    const pagerBox = UI.h('div', {});
    page.appendChild(UI.h('div', { class: 'card' },
      UI.h('div', { class: 'toolbar' },
        UI.h('h3', { style: 'margin:0;border:none;padding:0' }, '操作日志'),
        UI.h('div', { class: 'spacer' }),
        bizType, bizId,
        UI.h('button', { class: 'sm primary', onclick: () => { pageNo = 1; load(); } }, '查询')),
      listBox,
      pagerBox));

    /* ---- 中文映射表 ---- */
    const BIZ_TYPE = { ent_company: '企业准入', ent_qualification: '企业资质', sys_user: '平台用户',
      sys_file: '文件', base_variety: '品种', base_price: '基准价', base_port_price: '港口价格',
      biz_demand: '需求单', biz_demand_change: '变更申请', biz_inquiry: '询价单', biz_quote: '报价单',
      biz_bargain: '议价', biz_aggregated_order: '归集订单', biz_order: '订单', biz_order_member: '订单成员',
      biz_member_cargo: '成员货物', biz_contract: '合同', biz_logistics_plan: '物流方案',
      biz_waybill: '运单', biz_track_node: '轨迹节点', biz_forecast_quote: '预测报价',
      biz_settlement: '结算单', biz_payment: '支付单', biz_quality_check: '质检单' };
    const BIZ_GROUP = { biz_demand: 'DEMAND', biz_demand_change: 'CHANGE', biz_inquiry: 'INQUIRY',
      biz_quote: 'QUOTE', biz_bargain: 'BARGAIN', biz_aggregated_order: 'AGG', biz_order: 'ORDER',
      biz_order_member: 'ORDER', biz_member_cargo: 'ORDER', biz_contract: 'CONTRACT',
      biz_waybill: 'WAYBILL', biz_settlement: 'SETTLEMENT', biz_payment: 'SETTLEMENT',
      biz_quality_check: 'SETTLEMENT', biz_forecast_quote: 'FORECAST', ent_company: 'AUDIT',
      sys_user: 'USER' };
    const NODE_LABEL = { ETA: '船到港', DEPART: '开始卸船', TRANSIT: '到达中转站',
      ARRIVE: '卸货完成', PLACES: '起讫地' };
    const ACTION_LABEL = { LOGIN: '登录', REGISTER: '企业注册', UPLOAD: '上传资质', CREATE: '新增',
      UPDATE: '修改', DELETE: '删除', CLOSE: '关闭', UPSERT: '保存', 'CHANGE REQUEST': '提交信息变更',
      'CHANGE APPROVED': '信息变更审核通过', 'CHANGE REJECTED': '信息变更审核驳回',
      'SET STATUS': '设置账号状态', RESET_PASSWORD: '重置密码', 'CHANGE SYNC': '变更同步需求',
      'AGG FEEDBACK': '归集询价反馈', 'PLATFORM CREATE': '平台代发询价', 'PLATFORM RETURN': '平台退回',
      AWARD: '定标生成订单', CONSOLIDATE: '合并归集', SET_CARGO: '录入货物信息', PLATFORM_CREATE: '创建',
      DEVIATION: '分段偏差说明', PUSH_SUPPLIER: '推送供应商', PUSH_MEMBER: '推送钢厂货物信息',
      PUSH_MILLS: '推送至钢厂（轨迹）', PLATFORM_ASSIGN: '指派承运商', ASSIGN: '指派承运商',
      SET_PLACES: '保存起讫地', WB_NODE_DRAFT: '保存节点草稿',
      'PLATFORM_ADVANCE SUBMIT_DRAFT': '节点统一提交',
      PICKUP_PLAN: '提交提货计划', GENERATE: '生成合同', VOID: '合同作废', SIGN: '货物签收',
      MANUAL_NODE: '手工轨迹节点' };
    const KEY_CN = { orderNo: '订单号', aggNo: '归集订单号', demandNo: '需求单号', inquiryNo: '询价单号',
      waybillNo: '运单号', planNo: '方案号', mills: '推送钢厂', supplierId: '供方', buyerName: '需方',
      companyName: '企业名称', demandName: '需求单名称', quantity: '数量', invites: '邀请供应商',
      reason: '原因', result: '结果', version: '版本', carrierId: '承运商', planQty: '计划量',
      fileName: '文件名', size: '大小', rail: '铁路直达方案', multimodal: '公铁联运方案',
      truck: '汽运直达方案', remark: '方案说明', departPlace: '起始地', arrivePlace: '目的地',
      occurTime: '发生时间', orgMode: '组织方式', segmentNo: '分段号', freight: '运费',
      accounts: '账号数', company: '企业', status: '状态', action: '节点',
      ETA: '船到港时间', DEPART: '开始卸船时间', TRANSIT: '到达中转站', ARRIVE: '卸货完成' };
    const VALUE_CN = { ENABLED: '启用', DISABLED: '停用', PLATFORM: '平台配送', SELF: '钢厂自提',
      RAIL: '铁路直达', MULTIMODAL: '公铁联运', ROAD: '汽运直达' };
    /* 状态码 → 中文（优先按业务类型取对应状态字典组，找不到再全库兜底） */
    function st(code, biz) {
      if (code == null || code === '') return code;
      const grp = (BIZ_GROUP[biz] && UI.STATUS[BIZ_GROUP[biz]]) || null;
      if (grp && grp[code]) return grp[code][0];
      for (const g of Object.values(UI.STATUS)) if (g[code]) return g[code][0];
      return code;
    }
    function fmtAction(raw, biz) {
      const s = String(raw);
      const hit = ACTION_LABEL[s];
      if (hit) return hit;
      let m = s.match(/^STATUS (\w+)->(\w+)$/);
      if (m) return '状态 ' + st(m[1], biz) + ' → ' + st(m[2], biz);
      m = s.match(/^PLATFORM_ADVANCE (\w+)$/);
      if (m) return '节点录入 · ' + (NODE_LABEL[m[1]] || m[1]);
      m = s.match(/^NODE (\w+)$/);
      if (m) return '登记节点 · ' + (NODE_LABEL[m[1]] || m[1]);
      m = s.match(/^RETURN\((.+)\)$/);
      if (m) return '退回（' + m[1] + '）';
      m = s.match(/^UPLOAD_SIGNED\((.+)\)$/);
      if (m) return '上传已签章合同（' + m[1] + '）';
      return s;
    }
    /* 变更内容 JSON → 中文「键：值」串 */
    function fmtAfter(after, biz) {
      if (after == null || after === '') return '—';
      let obj = after;
      if (typeof after === 'string') {
        try { obj = JSON.parse(after); } catch (e) { return after; }
      }
      if (obj && typeof obj === 'object' && !Array.isArray(obj)) {
        return Object.entries(obj).map(([k, v]) => {
          let vv = v;
          if (k === 'status') vv = st(v, biz);
          else if (k === 'action') vv = NODE_LABEL[v] || v;
          else if (Array.isArray(v)) vv = v.map((x) => VALUE_CN[x] || x).join('、');
          else if (VALUE_CN[v] != null) vv = VALUE_CN[v];
          else if (v && typeof v === 'object') vv = JSON.stringify(v);
          return (KEY_CN[k] || k) + '：' + vv;
        }).join('；');
      }
      return String(obj);
    }

    async function load() {
      const d = await API.get('/logs' + API.qs({ bizType: bizType.value.trim(), bizId: bizId.value.trim(), page: pageNo, size: SIZE }));
      listBox.innerHTML = '';
      listBox.appendChild(UI.table([
        UI.selCol(picked),
        { key: 'bizType', label: '业务类型', render: (r) => BIZ_TYPE[r.bizType] || r.bizType },
        { key: 'bizId', label: '业务ID' },
        { label: '动作', render: (r) => fmtAction(r.action, r.bizType) },
        { label: '变更内容', full: true, render: (r) => fmtAfter(r.after, r.bizType) },
        { key: 'createdAt', label: '时间', render: (r) => UI.fmtDateTime(r.createdAt) },
      ], d.list, '暂无日志'));
      pagerBox.innerHTML = '';
      UI.pager(pagerBox, pageNo, SIZE, d.total, (p) => { pageNo = p; load(); });
    }

    await load();
  };

  /* -------- 运输调度：订单列表 → 订单详情独立页（钢铁企业框 / 供应商框）--------
     opts.oid 存在时渲染订单详情独立页（路由 #/logistics-order-detail?oid=） */
  function logisticsPage(page, opts) {
    const SIZE = 10;
    let pageNo = 1;
    let orderRows = [];
    const pickedRows = new Set(); // 行首勾选框（仅行选择展示）
    const scrollWrap = (node, style) => UI.h('div', { class: 'table-scroll-wrap', style }, node);
    const MODE_LABEL = { RAIL: '铁路直达', MULTIMODAL: '公铁联运', ROAD: '汽运直达' };
    const ORG_LABEL = { SELF: '钢厂自提', PLATFORM: '平台配送' };
    const numInput = (attrs) => UI.h('input', Object.assign({ type: 'number', min: '0' }, attrs || {}));

    const statsBox = UI.h('div', {});
    /* 定高列表区（同需求归集，10 行/页）：纵向超出滚动，横向滚动条固定在分页行上方 */
    const listBox = UI.h('div', { class: 'list-fixed' });
    const pagerBox = UI.h('div', {});
    const mainCard = UI.h('div', { class: 'card dispatch-card' },
      UI.h('div', { class: 'toolbar' },
        UI.h('h3', { style: 'margin:0;border:none;padding:0' }, '运输调度')),
      statsBox, listBox, pagerBox);
    /* 订单详情独立页：真实路由跳转（#/logistics-order-detail?oid=），页面内分钢铁企业 / 供应商两个框 */
    if (opts && opts.oid) {
      return renderStandaloneDetail(Number(opts.oid));
    }
    page.appendChild(mainCard);

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
        ['出场', '汽运出场', ['计划出场量', '实际出场量', '计划累计出场量', '实际累计出场量', '实际与计划差额']],
      ];
      return {
        title: '保税进出库存分析表',
        cols: days.slice(),
        rows: spec.flatMap(([g, s, labels]) => labels.map((label) => ({ g, s, label, cells: days.map(() => '') }))),
        merges: [], // Excel 式合并单元格 [r0,c0,r1,c1]（列坐标：0分组 1子类 2项目 3+数据列）
        footer: { label: '保税库存状态', value: '' },
      };
    }
    let gridOrder = null; // 当前展示分析表的订单
    let grid = null;
    let sel = null; // Excel 式选区：点选起始格 + Shift 点选结束格
    function gridKey(orderId) { return 'mine_dispatch_analysis_v2_' + orderId; }
    function loadGrid(orderId) {
      try {
        const m = JSON.parse(localStorage.getItem(gridKey(orderId)) || 'null');
        if (m && Array.isArray(m.cols) && Array.isArray(m.rows)) return Object.assign({ merges: [] }, m);
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
    /* ---- Excel 式合并单元格：merges=[r0,c0,r1,c1]，列坐标 0分组 1子类 2项目 3+数据列 ---- */
    function getCell(row, ci) { return ci === 2 ? (row.label || '') : (row.cells[ci - 3] || ''); }
    function setCell(row, ci, v) { if (ci === 2) row.label = v; else row.cells[ci - 3] = v; }
    function inMerge(ri, ci) {
      return (grid.merges || []).find((m) => ri >= m[0] && ri <= m[2] && ci >= m[1] && ci <= m[3]) || null;
    }
    function normSel() {
      if (!sel) return null;
      return { r0: Math.min(sel.r0, sel.r1), r1: Math.max(sel.r0, sel.r1),
        c0: Math.min(sel.c0, sel.c1), c1: Math.max(sel.c0, sel.c1) };
    }
    function adjustMerges(delR, delC) {
      const out = [];
      (grid.merges || []).forEach((m) => {
        let r0 = m[0], c0 = m[1], r1 = m[2], c1 = m[3];
        if (delR != null) {
          if (r1 < delR) { out.push(m); return; }
          if (r0 > delR) { out.push([r0 - 1, c0, r1 - 1, c1]); return; }
          r1 -= 1;
        } else {
          if (c1 < delC) { out.push(m); return; }
          if (c0 > delC) { out.push([r0, c0 - 1, r1, c1 - 1]); return; }
          c1 -= 1;
        }
        if (r1 >= r0 && c1 >= c0) out.push([r0, c0, r1, c1]);
      });
      grid.merges = out;
    }
    function mergeSel() {
      const s = normSel();
      if (!s || (s.r0 === s.r1 && s.c0 === s.c1)) {
        UI.toast('请先点选起始格，再按住 Shift 点选结束格，选择要合并的区域', 'err'); return;
      }
      const overlap = (grid.merges || []).some((m) => !(m[2] < s.r0 || m[0] > s.r1 || m[3] < s.c0 || m[1] > s.c1));
      if (overlap) { UI.toast('选择区域与已有合并单元格重叠', 'err'); return; }
      grid.merges = (grid.merges || []).concat([[s.r0, s.c0, s.r1, s.c1]]);
      sel = { r0: s.r0, c0: s.c0, r1: s.r0, c1: s.c0 };
      renderGrid(); saveGrid();
      UI.toast('已合并居中（内容保留左上格）', 'ok');
    }
    function unmergeSel() {
      const s = normSel();
      if (!s) { UI.toast('请先点选已合并的单元格', 'err'); return; }
      const m = inMerge(s.r0, s.c0);
      if (!m) { UI.toast('所选区域未合并', 'err'); return; }
      grid.merges = (grid.merges || []).filter((x) => x !== m);
      sel = null;
      renderGrid(); saveGrid();
    }
    function renderGrid() {
      statsBox.innerHTML = '';
      if (!gridOrder || !grid) return;
      const sp = gridSpans(grid.rows);
      const nCol = 3 + grid.cols.length; // 0分组 1子类 2项目 3+数据
      const selR = normSel();
      /* 可选单元格（项目列与数据列，含合并格）：点击选区、Shift 扩选、双击编辑，不重建表格以保留输入焦点 */
      const makeCell = (r, ri, ci) => {
        const m = inMerge(ri, ci);
        if (m && (m[0] !== ri || m[1] !== ci)) return null; // 被合并覆盖
        const attrs = { class: 'cell-text', 'data-r': String(ri), 'data-c': String(ci),
          style: 'min-height:18px;display:block' };
        const td = UI.h('td', ci === 2 ? { class: 'row-label' } : { class: 'cell' });
        if (m) {
          td.setAttribute('rowspan', String(m[2] - m[0] + 1));
          td.setAttribute('colspan', String(m[3] - m[1] + 1));
          td.classList.add('merged');
        }
        const span = UI.h('span', attrs, getCell(r, ci));
        td.appendChild(span);
        editCell(span, (v) => { setCell(r, ci, v); });
        td.addEventListener('click', (e) => {
          if (e.shiftKey && sel) { sel.r1 = ri; sel.c1 = ci; } else { sel = { r0: ri, c0: ci, r1: ri, c1: ci }; }
          highlightSel();
        });
        return td;
      };
      function highlightSel() {
        const s = normSel();
        table.querySelectorAll('.cell-text[data-r]').forEach((el) => {
          const ri = Number(el.dataset.r); const ci = Number(el.dataset.c);
          el.classList.toggle('selm', !!(s && ri >= s.r0 && ri <= s.r1 && ci >= s.c0 && ci <= s.c1));
        });
      }
      const table = UI.h('table', { class: 'grid analysis-grid' },
        UI.h('thead', {}, UI.h('tr', {},
          UI.h('th', { rowspan: '2', style: 'width:64px' }, '分组'),
          UI.h('th', { rowspan: '2', style: 'width:84px' }, '子类'),
          UI.h('th', { rowspan: '2', style: 'width:160px' }, '项目'),
          ...grid.cols.map((c, ci) => UI.h('th', { class: 'col-head' },
            editCell(UI.h('span', { class: 'head-text' }, c), (v) => { grid.cols[ci] = v; }),
            delBtn('删除该列', () => {
              const gci = 3 + ci;
              (grid.merges || []).forEach((m) => {
                if (m[1] === gci && m[3] > m[1]) setCell(grid.rows[m[0]], gci + 1, getCell(grid.rows[m[0]], gci));
              });
              grid.cols.splice(ci, 1);
              grid.rows.forEach((r) => r.cells.splice(ci, 1));
              adjustMerges(null, gci); sel = null;
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
            for (let ci = 2; ci < nCol; ci++) {
              const td = makeCell(r, ri, ci);
              if (td) tr.appendChild(td);
            }
            tr.appendChild(UI.h('td', { class: 'row-op' },
              delBtn('删除该行', () => {
                (grid.merges || []).forEach((m) => {
                  if (m[0] === ri && m[2] > m[0]) setCell(grid.rows[ri + 1], m[1], getCell(grid.rows[ri], m[1]));
                });
                grid.rows.splice(ri, 1); adjustMerges(ri, null); sel = null;
                renderGrid(); saveGrid();
              }, 'row-x')));
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
        UI.h('button', { class: 'sm', onclick: mergeSel }, '合并居中'),
        UI.h('button', { class: 'sm', onclick: unmergeSel }, '取消合并'),
        UI.h('span', { class: 'muted', style: 'font-size:12px;align-self:center' },
          '点选起始格，按住 Shift 点选结束格后「合并居中」'),
        UI.h('button', { class: 'sm', onclick: async () => {
          if (!(await UI.confirmBox('恢复默认表格结构？当前修改将全部清除。'))) return;
          grid = defaultGrid(); sel = null; renderGrid(); saveGrid();
        } }, '恢复默认'),
        UI.h('button', { class: 'sm', onclick: closeAnalysis }, '关闭分析')));
      statsBox.appendChild(UI.h('div', { class: 'grid-title-wrap' },
        editCell(UI.h('div', { class: 'grid-title' }, (grid.title || '保税进出库存分析表') + ' · ' + (gridOrder.orderNo || '')),
          (v) => { grid.title = v.replace(/\s*·\s*DD-\S+$/, ''); }),
        scrollWrap(table, 'border:1px solid #cfd4dc')));
      highlightSel();
    }
    if (!document.getElementById('analysis-grid-style')) {
      document.head.appendChild(UI.h('style', { id: 'analysis-grid-style' }, `
        .analysis-grid { width: 100%; }
        .analysis-grid th, .analysis-grid td { border: 1px solid #cfd4dc; text-align: center; padding: 4px 6px; white-space: normal; }
        .analysis-grid .cell-text { display: block; min-height: 18px; min-width: 40px; border-radius: 2px; }
        .analysis-grid .cell-text.selm { background: #dceafc; box-shadow: inset 0 0 0 2px #1a5cb0; }
        .analysis-grid td.merged { vertical-align: middle; }
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
        /* 边框仅用于保税进出库存分析表（Excel 式）；普通业务表格与其他页面样式一致（无竖线，hairline 行分隔） */
        .dispatch-card table.analysis-grid { border-collapse: collapse; }
        .dispatch-card table.analysis-grid th, .dispatch-card table.analysis-grid td { border: 1px solid var(--gray-4); }
      `));
    }
    render();
    /* 从详情页点「保税库存分析表」跳回列表页时，直接打开对应分析表 */
    if (pendingGridOrder) {
      const r0 = pendingGridOrder;
      pendingGridOrder = null;
      selectOrder(r0);
    }

    async function render() {
      pagerBox.innerHTML = '';
      statsBox.innerHTML = '';
      listBox.innerHTML = '';
      listBox.style.display = '';
      pagerBox.style.display = '';
      if (gridOrder) {
        // 详情视图：只显示该订单的分析表
        renderGrid();
        listBox.style.display = 'none';
        pagerBox.style.display = 'none';
      } else {
        await loadOrders();
      }
    }

    async function loadOrders() {
      const d = await API.get('/admin/logistics-orders' + API.qs({ page: pageNo, size: SIZE }));
      orderRows = d.list || [];
      listBox.innerHTML = '';
      const tbl = UI.table([
        UI.selCol(pickedRows),
        { label: '序号', render: (r) => String((pageNo - 1) * SIZE + orderRows.indexOf(r) + 1) },
        { key: 'orderNo', label: '订单号' },
        { key: 'buyerName', label: '需方(钢厂)' },
        { key: 'supplierName', label: '供方' },
        { key: 'quantity', label: '订单量(湿吨)', num: true },
        { label: '物流方案', render: (r) => r.planNo
          ? r.planNo + '（' + (ORG_LABEL[r.orgMode] || r.orgMode) + '）'
          : UI.h('span', { class: 'muted' }, '未制定') },
        { label: '运单概况', render: (r) => r.planId
          ? String(r.waybillCount || 0) + ' 段 / 已排 ' + (r.plannedQty || 0) + ' 湿吨'
          : '-' },
        { label: '操作', render: (r) => UI.h('span', { class: 'inline-flex' },
          r.planId
            ? UI.h('button', { class: 'sm primary', onclick: (e) => { e.stopPropagation(); waybillCreateModal(r); } }, '新增分段运单')
            : UI.h('button', { class: 'sm primary', onclick: (e) => { e.stopPropagation(); planModal(r); } }, '制定方案')) },
      ], orderRows, '暂无履约中订单（合同生效后进入调度）');
      listBox.appendChild(scrollWrap(tbl));
      // 点击订单行 → 订单详情整页（钢厂端 / 供应商端两个独立框）
      tbl.querySelectorAll('tbody tr').forEach((tr, i) => {
        const r = orderRows[i];
        if (!r) return;
        tr.style.cursor = 'pointer';
        tr.title = '点击查看成员钢厂与物流节点轨迹';
        if (gridOrder && gridOrder.id === r.id) tr.classList.add('row-selected');
        tr.addEventListener('click', () => { location.hash = '#/logistics-order-detail?oid=' + r.id; });
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
          ['订单量', r.quantity + ' 湿吨'],
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

    async function waybillCreateModal(r, afterSave) {
      const remain = Math.max(0, (r.quantity || 0) - (r.plannedQty || 0));
      const segNo = numInput({ value: String((r.waybillCount || 0) + 1), min: '1', style: 'width:100%' });
      /* 运输方式：内嵌浏览器原生 select 弹层点不出选项，改用页面内渲染的下拉面板 */
      let modeVal = 'RAIL';
      const mode = UI.dropdown(Object.entries(MODE_LABEL), modeVal,
        { onchange: (v) => { modeVal = v; } });
      /* 各运输方式已排量：供应商端方案分方式排量，每种运输方式单独录入运输量 */
      const byMode = {};
      (r.waybills || []).forEach((w) => {
        const k = w.transportMode || '-';
        byMode[k] = (byMode[k] || 0) + (Number(w.planQty) || 0);
      });
      const modeTxt = Object.keys(MODE_LABEL).filter((k) => byMode[k])
        .map((k) => MODE_LABEL[k] + ' ' + Math.round(byMode[k] * 100) / 100 + ' 湿吨').join(' · ') || '暂无';
      /* 起始地/目的地默认与订单一致（成交报价到货港口 / 钢厂交货地址），可修改 */
      const departPlace = UI.h('input', { type: 'text', style: 'width:100%;height:32px', placeholder: '如：黄骅港', value: r.startPlace || '' });
      const arrivePlace = UI.h('input', { type: 'text', style: 'width:100%;height:32px', placeholder: '如：邯郸南站 / 钢厂场区', value: r.destPlace || '' });
      /* 运输量：本次分段运单的排量（默认剩余可排，可改）。分段运输量不强制与订单量一致：
         支持多个分段自由排载，各段合计允许与订单量存在偏差（>5% 自动记录偏差审计） */
      const planQty = numInput({ value: Number(remain).toFixed(2), min: '0.01', step: '0.01', style: 'width:100%' });
      const m = UI.modal('新增分段运单 · ' + r.orderNo, UI.h('form', { onsubmit: (e) => e.preventDefault() },
        UI.kv([
          ['物流方案', r.planNo + '（' + (ORG_LABEL[r.orgMode] || r.orgMode) + '）'],
          ['订单量', r.quantity + ' 湿吨'],
          ['已排量', (r.plannedQty || 0) + ' 湿吨'],
          ['各方式已排', modeTxt],
          ['剩余可排（参考，分段量不强制等于订单量）', remain + ' 湿吨'],
        ]),
        UI.h('div', { class: 'form-grid' },
          UI.formRow('分段号', segNo, true),
          UI.formRow('运输方式', mode, true),
          UI.formRow('运输量(湿吨)', planQty, true),
          UI.formRow('起始地', departPlace, true),
          UI.formRow('目的地', arrivePlace, true))), [
        UI.h('button', { class: 'primary', onclick: async () => {
          const q = parseFloat(planQty.value);
          if (!departPlace.value.trim()) { UI.toast('请填写起始地', 'err'); return; }
          if (!arrivePlace.value.trim()) { UI.toast('请填写目的地', 'err'); return; }
          if (!(q > 0)) { UI.toast('请填写运输量（必须大于 0）', 'err'); return; }
          try {
            await API.post('/admin/logistics-plans/' + r.planId + '/waybills', {
              segmentNo: parseInt(segNo.value, 10) || 1,
              transportMode: modeVal,
              planQty: q,
              departPlace: departPlace.value.trim(),
              arrivePlace: arrivePlace.value.trim(),
            });
            m.close();
            UI.toast('运单已创建（待发运），运输量 ' + q + ' 湿吨', 'ok');
            if (afterSave) afterSave(); else loadOrders();
          } catch (e) { /* toast 已提示 */ }
        } }, '提 交'),
      ]);
    }

    /* ---- 分段运单条 + 合并轨迹时间线 ----
       供应商面板：分段运单条（段/方式/状态/节点录入）+ 合并时间线；
       钢铁企业面板：仅合并时间线（不分段、不区分运输方式），传 { segBar: false } */
    /* 轨迹事件收集：节点录入追加的轨迹日志（nodeLog）优先；无日志时按固定节点时间兜底（旧数据）；已生成始终保留 */
    function traceEventsOf(w) {
      const dot = (s) => (String(s || '').replace(/。*$/, '') + '。');
      const evs = [];
      const nl = Array.isArray(w.nodeLog) ? w.nodeLog : [];
      if (nl.length) {
        nl.forEach((e) => evs.push([e.occurTime, e.loc || '节点', dot(e.desc)]));
      } else {
        if (w.arriveAt) evs.push([w.arriveAt, w.arrivePlace || '目的地', '货物已到达目的地。']);
        if (w.transitAt) evs.push([w.transitAt, w.transitStation || '中转站', '货物已到达中转站。']);
        if (w.departAt) evs.push([w.departAt, w.departPlace || '起运地', '货物已出港发运。']);
        if (w.etaActual) evs.push([w.etaActual, w.departPlace || '起运港', '船已到港，待发运。']);
      }
      evs.push([w.createdAt, w.departPlace || '起运地', '运单已生成，等待发运。']);
      return evs;
    }

    /* ---- 订单详情独立页（#/logistics-order-detail?oid=）：页面内分两个框 ----
       框一「钢铁企业」：成员钢厂与货物信息 + 物流节点轨迹（货物信息各厂独立，录入后钢厂端自动更新）；
       框二「供应商」：运输说明（可编辑）+ 物流运输轨迹 + 推送供应商（供应商端物流服务自动更新） */
    async function renderStandaloneDetail(oid) {
      let d;
      try {
        d = await API.get('/admin/logistics-orders/' + oid);
      } catch (e) { return; }
      const r = { id: oid, orderNo: d.order.orderNo, supplierName: d.order.supplierName };
      const memberBox = UI.h('div', {});
      const traceSteel = UI.h('div', {});
      const traceSup = UI.h('div', {});
      /* 运输方案三个框：铁路直达 / 公铁联运 / 汽运直达（随方案推送供应商） */
      const railTa = UI.h('textarea', { rows: 2, style: 'width:100%;height:64px;flex:1',
        placeholder: '铁路直达运输方案（装卸/交接/注意事项等，不超过500字）' });
      railTa.value = d.order.railRemark || d.order.remark || '';
      const multiTa = UI.h('textarea', { rows: 2, style: 'width:100%;height:64px;flex:1',
        placeholder: '公铁联运运输方案（装卸/交接/注意事项等，不超过500字）' });
      multiTa.value = d.order.multimodalRemark || '';
      const truckTa = UI.h('textarea', { rows: 2, style: 'width:100%;height:64px;flex:1',
        placeholder: '汽运直达运输方案（装卸/交接/注意事项等，不超过500字）' });
      truckTa.value = d.order.truckRemark || '';
      const modeRow = (label, ta) => UI.h('div', { style: 'display:flex;gap:12px;align-items:flex-start' },
        UI.h('span', { style: 'flex:none;width:72px;line-height:64px;color:var(--ink-2,#555)' }, label), ta);

      function renderMembers() {
        memberBox.replaceChildren(UI.table([
          { key: 'companyName', label: '钢厂' },
          { label: '份额(湿吨)', num: true, render: (x) => x.quantity != null ? UI.fmtQty(x.quantity) : '-' },
          { label: '货物总量', num: true, render: (x) => x.totalQty != null ? UI.fmtQty(x.totalQty) : '-' },
          { label: '出港', num: true, render: (x) => x.shippedQty != null ? UI.fmtQty(x.shippedQty) : '-' },
          { label: '在途', num: true, render: (x) => x.transitQty != null ? UI.fmtQty(x.transitQty) : '-' },
          { label: '到站', num: true, render: (x) => x.arrivedQty != null ? UI.fmtQty(x.arrivedQty) : '-' },
          { label: '可提货', num: true, render: (x) => x.pickupQty != null ? UI.fmtQty(x.pickupQty) : '-' },
          { label: '操作', render: (x) => UI.h('span', { class: 'inline-flex' },
            UI.h('button', { class: 'sm', onclick: () => cargoModal(x) }, '录入货物信息'),
            UI.h('button', { class: 'sm', onclick: async () => {
              try {
                const res = await API.post('/admin/logistics-orders/' + d.order.id + '/members/' + x.companyId + '/push');
                UI.toast('已推送到 ' + (res.companyName || x.companyName), 'ok');
              } catch (e) { /* toast 已提示 */ }
            } }, '推送')) },
        ], d.members, '暂无成员钢厂'));
      }

      function cargoModal(x) {
        const FIELDS = [
          ['totalQty', '货物总量(湿吨)'],
          ['shippedQty', '出港(湿吨)'],
          ['transitQty', '在途(湿吨)'],
          ['arrivedQty', '到站(湿吨)'],
          ['pickupQty', '可提货(湿吨)'],
        ];
        const inputs = FIELDS.map(([k, label]) => [
          UI.h('input', { type: 'number', min: '0', step: '0.01', style: 'width:100%', value: x[k] != null ? Number(x[k]).toFixed(2) : '' }),
          label, k,
        ]);
        const mm = UI.modal('录入货物信息 · ' + x.companyName, UI.h('form', { onsubmit: (e) => e.preventDefault() },
          UI.kv([['所属订单', d.order.orderNo], ['份额(湿吨)', x.quantity != null ? UI.fmtQty(x.quantity) : '-']]),
          UI.h('div', { class: 'form-grid' },
            inputs.map(([inp, label]) => UI.formRow(label, inp)))), [
          UI.h('button', { class: 'primary', onclick: async () => {
            try {
              const payload = {};
              inputs.forEach(([inp, , k]) => { payload[k] = inp.value ? parseFloat(inp.value) : undefined; });
              await API.put('/admin/logistics-orders/' + d.order.id + '/members/' + x.companyId + '/cargo', payload);
              mm.close();
              UI.toast('货物信息已保存（点击「推送」后钢厂端可见）', 'ok');
              const fresh = await API.get('/admin/logistics-orders/' + d.order.id);
              d.members = fresh.members;
              renderMembers();
            } catch (e) { /* toast 已提示 */ }
          } }, '保 存'),
        ]);
      }

      /* 钢铁企业面板轨迹节点录入：单运单直接打开，多运单先选运单 */
      function steelNodeEntry() {
        const wbs = d.waybills || [];
        if (!wbs.length) { UI.toast('该订单暂无运单，无法录入节点', 'err'); return; }
        if (wbs.length === 1) { nodeEntryModal(wbs[0], refreshDetail); return; }
        const m = UI.modal('选择运单', UI.h('div', { style: 'display:flex;flex-direction:column;gap:8px' },
          wbs.map((w) => UI.h('span', { class: 'inline-flex', style: 'gap:6px;align-items:center' },
            UI.h('span', { class: 'wb-v' }, w.waybillNo || ('运单 #' + w.id)),
            UI.statusTag('WAYBILL', w.status),
            UI.h('button', { class: 'sm', onclick: () => { m.close(); nodeEntryModal(w, refreshDetail); } }, '节点录入')))), []);
      }

      /* 钢铁企业面板：95306 式物流节点跟踪（左侧合并时间线 + 右侧货物信息），内容同钢厂端物流服务页 */
      function renderTraceSteel() {
        const wbs = d.waybills || [];
        const line = UI.h('div', { class: 'trace-line', style: 'margin-top:4px' });
        if (!wbs.length) {
          line.appendChild(UI.h('div', { class: 'empty' }, '该订单暂无运单，请在供应商面板增加轨迹'));
        } else {
          const all = [];
          wbs.forEach((w) => traceEventsOf(w).forEach((ev) => all.push(ev)));
          all.sort((a, b) => new Date(String(b[0]).replace(' ', 'T')) - new Date(String(a[0]).replace(' ', 'T')));
          all.forEach(([t, loc, txt], i) => {
            const hm = String(t).split(' ')[1] || '';
            line.appendChild(UI.h('div', { class: 'trace-item' + (i === 0 ? ' latest' : '') },
              UI.h('div', { class: 'trace-time' }, UI.fmtDate(t) + (hm ? ' ' + hm.slice(0, 5) : '')),
              UI.h('div', { class: 'trace-rail' },
                UI.h('span', { class: 'trace-dot' }),
                UI.h('span', { class: 'trace-seg' })),
              UI.h('div', { class: 'trace-desc' },
                UI.h('span', { class: 'trace-loc' }, '【' + loc + '】'), txt)));
          });
        }
        /* 右侧货物信息：成员货物信息按厂汇总；平台未录入时按运单实时汇总（同钢厂端逻辑） */
        const members = d.members || [];
        const hasCargo = members.some((m) => m.totalQty != null || m.shippedQty != null
          || m.transitQty != null || m.arrivedQty != null || m.pickupQty != null);
        const sumOf = (k) => members.reduce((s, m) => s + (m[k] != null ? Number(m[k]) : 0), 0);
        const qtyOf = (w) => (w.actualQty != null ? Number(w.actualQty) : (w.planQty != null ? Number(w.planQty) : 0));
        const wbSum = (sts) => wbs.filter((w) => sts.indexOf(w.status) >= 0).reduce((s, w) => s + qtyOf(w), 0);
        const rows = hasCargo
          ? [['货物总量', sumOf('totalQty')], ['出港', sumOf('shippedQty')], ['在途', sumOf('transitQty')],
             ['到站', sumOf('arrivedQty')], ['可提货', sumOf('pickupQty')]]
          : [['货物总量', null], ['出港', wbSum(['IN_TRANSIT', 'ARRIVED', 'SIGNED'])], ['在途', wbSum(['IN_TRANSIT'])],
             ['到站', wbSum(['ARRIVED', 'SIGNED'])], ['可提货', wbSum(['ARRIVED'])]];
        /* 原位原子更新：整体构建后一次性替换，面板不闪动 */
        traceSteel.replaceChildren(UI.h('div', { class: 'trace-body' },
          UI.h('div', { class: 'trace-panel' }, line),
          UI.h('div', { class: 'trace-side' },
            UI.h('div', { class: 'trace-title' }, '货物信息'),
            UI.h('div', { class: 'side-kv' },
              rows.map(([k, v]) => UI.h('div', { class: 'side-kv-row' },
                UI.h('span', { class: 'side-kv-k' }, k),
                UI.h('span', { class: 'side-kv-v' }, v != null && v !== '' ? UI.fmtMoney(Number(v)) + ' 湿吨' : '-'))),
              UI.h('div', { class: 'side-kv-row' },
                UI.h('span', { class: 'side-kv-k' }, '信息来源'),
                UI.h('span', { class: 'side-kv-v' }, hasCargo ? '平台录入汇总' : '运单实时汇总'))))));
      }

      /* 供应商面板：物流运输轨迹——分段筛选（按已新增分段运单生成：方式+列次）+ 节点录入（录入所选分段轨迹）+ 右侧货物信息 */
      let segSel = null;
      function renderTraceSup() {
        const wbs = d.waybills || [];
        /* 分段筛选框：选项来自新增的分段运单（如「铁路直达 第1列」），选择哪个显示哪个分段的轨迹 */
        const prev = segSel ? segSel.value : null;
        segSel = UI.selectField(wbs.map((w) => [
          String(w.id),
          (MODE_LABEL[w.transportMode] || w.transportMode || '-')
            + (w.transportMode === 'ROAD' ? '（全程）' : ' 第' + w.segmentNo + '列'),
        ]), prev && wbs.some((w) => String(w.id) === prev) ? prev : (wbs.length ? String(wbs[0].id) : ''));
        segSel.addEventListener('change', () => renderTraceSup());
        const cur = wbs.find((w) => String(w.id) === segSel.value) || wbs[0] || null;
        /* 左侧：所选分段的物流轨迹时间线（倒序，最新一条高亮） */
        const line = UI.h('div', { class: 'trace-line', style: 'margin-top:4px' });
        if (!wbs.length) {
          line.appendChild(UI.h('div', { class: 'empty' }, '该订单暂无运单，请先制定物流方案并新增分段运单'));
        } else {
          traceEventsOf(cur).forEach(([t, loc, txt], i) => {
            const hm = String(t).split(' ')[1] || '';
            line.appendChild(UI.h('div', { class: 'trace-item' + (i === 0 ? ' latest' : '') },
              UI.h('div', { class: 'trace-time' }, UI.fmtDate(t) + (hm ? ' ' + hm.slice(0, 5) : '')),
              UI.h('div', { class: 'trace-rail' },
                UI.h('span', { class: 'trace-dot' }),
                UI.h('span', { class: 'trace-seg' })),
              UI.h('div', { class: 'trace-desc' },
                UI.h('span', { class: 'trace-loc' }, '【' + loc + '】'), txt)));
          });
        }
        /* 右侧货物信息：优先运营端录入的供应商货物信息；未录入时按运单实时汇总 */
        const sc = d.order.suppCargo || null;
        const qtyOf = (w) => (w.actualQty != null ? Number(w.actualQty) : (w.planQty != null ? Number(w.planQty) : 0));
        const wbSum = (sts) => wbs.filter((w) => sts.indexOf(w.status) >= 0).reduce((s, w) => s + qtyOf(w), 0);
        const hasSupp = sc && sc.updatedAt;
        const rows = hasSupp
          ? [['货物总量', sc.totalQty], ['出港', sc.shippedQty], ['在途', sc.transitQty],
             ['到站', sc.arrivedQty], ['可提货', sc.pickupQty]]
          : [['货物总量', null], ['出港', wbSum(['IN_TRANSIT', 'ARRIVED', 'SIGNED'])], ['在途', wbSum(['IN_TRANSIT'])],
             ['到站', wbSum(['ARRIVED', 'SIGNED'])], ['可提货', wbSum(['ARRIVED'])]];
        /* 分段筛选 + 节点录入（录入所选分段轨迹），置于轨迹内容上方 */
        traceSup.replaceChildren(
          UI.h('div', { style: 'display:flex;gap:8px;align-items:center;margin:8px 0' },
            segSel,
            UI.h('button', { class: 'sm', onclick: () => { if (cur) nodeEntryModal(cur, refreshDetail); } }, '节点录入')),
          UI.h('div', { class: 'trace-body' },
            UI.h('div', { class: 'trace-panel' }, line),
            UI.h('div', { class: 'trace-side' },
              UI.h('div', { class: 'trace-title' }, '货物信息'),
              UI.h('div', { class: 'side-kv' },
                rows.map(([k, v]) => UI.h('div', { class: 'side-kv-row' },
                  UI.h('span', { class: 'side-kv-k' }, k),
                  UI.h('span', { class: 'side-kv-v' }, v != null && v !== '' ? UI.fmtMoney(Number(v)) + ' 湿吨' : '-'))),
                UI.h('div', { class: 'side-kv-row' },
                  UI.h('span', { class: 'side-kv-k' }, '信息来源'),
                  UI.h('span', { class: 'side-kv-v' }, hasSupp ? '平台 ' + UI.fmtDateTime(sc.updatedAt) : '运单实时汇总')),
                UI.h('div', { style: 'margin-top:8px' },
                  UI.h('button', { class: 'sm primary', onclick: suppCargoModal }, '录入货物信息'))))));
      }

      /* 供应商货物信息录入：货物总量/出港/在途/到站/可提货（每保存一次供应商端物流服务自动更新） */
      function suppCargoModal() {
        const FIELDS = [
          ['totalQty', '货物总量(湿吨)'],
          ['shippedQty', '出港(湿吨)'],
          ['transitQty', '在途(湿吨)'],
          ['arrivedQty', '到站(湿吨)'],
          ['pickupQty', '可提货(湿吨)'],
        ];
        const sc = d.order.suppCargo || {};
        const inputs = FIELDS.map(([k, label]) => [
          UI.h('input', { type: 'number', min: '0', step: '0.01', style: 'width:100%', value: sc[k] != null ? Number(sc[k]).toFixed(2) : '' }),
          label, k,
        ]);
        const mm = UI.modal('录入货物信息 · ' + (d.order.supplierName || '供应商'),
          UI.h('form', { onsubmit: (e) => e.preventDefault() },
            UI.kv([['所属订单', d.order.orderNo]]),
            UI.h('div', { class: 'form-grid' },
              inputs.map(([inp, label]) => UI.formRow(label, inp)))), [
          UI.h('button', { class: 'primary', onclick: async () => {
            try {
              const payload = {};
              inputs.forEach(([inp, , k]) => { payload[k] = inp.value ? parseFloat(inp.value) : undefined; });
              await API.put('/admin/logistics-orders/' + d.order.id + '/supplier-cargo', payload);
              mm.close();
              UI.toast('供应商货物信息已保存，供应商端物流服务将自动更新', 'ok');
              await refreshDetail();
            } catch (e) { /* toast 已提示 */ }
          } }, '保 存'),
        ]);
      }

      function renderTraces() {
        /* 钢铁企业面板 / 供应商面板：均 95306 式（左侧时间线 + 右侧货物信息），内容不闪动原位更新 */
        renderTraceSteel();
        renderTraceSup();
      }

      async function refreshDetail() {
        try {
          const fresh = await API.get('/admin/logistics-orders/' + oid);
          d = fresh;
          railTa.value = d.order.railRemark || d.order.remark || '';
          multiTa.value = d.order.multimodalRemark || '';
          truckTa.value = d.order.truckRemark || '';
          renderMembers();
          renderTraces();
        } catch (e) { /* 静默 */ }
      }

      /* 运输方案板块独立推送：仅推送三个运输方案文本（供应商端推送后才更新方案内容） */
      async function pushPlanOnly() {
        if (!d.order.planId) { UI.toast('该订单尚未制定物流方案，无法推送', 'err'); return; }
        try {
          await API.post('/admin/logistics-plans/' + d.order.planId + '/push',
            { railRemark: railTa.value.trim() || undefined,
              multimodalRemark: multiTa.value.trim() || undefined,
              truckRemark: truckTa.value.trim() || undefined });
          UI.toast('运输方案已推送供应商', 'ok');
        } catch (e) { /* toast 已提示 */ }
      }

      renderMembers();
      renderTraces();
      /* 顶部：页面标题 + 返回列表 / 保税库存分析表（跳回列表页并直接打开分析表） */
      page.appendChild(UI.h('div', { class: 'card', style: 'margin-bottom:12px' },
        UI.h('div', { class: 'toolbar' },
          UI.h('h3', { style: 'margin:0;border:none;padding:0' }, '运输调度 · ' + d.order.orderNo),
          UI.h('div', { class: 'spacer' }),
          UI.h('button', { onclick: () => { location.hash = '#/logistics-dispatch'; } }, '返回列表'),
          UI.h('button', { class: 'sm', onclick: () => {
            pendingGridOrder = { id: d.order.id, orderNo: d.order.orderNo };
            location.hash = '#/logistics-dispatch';
          } }, '保税库存分析表'))));
      /* 页签切换：钢铁企业 / 供应商（分别对应下方两个面板） */
      const steelCard = UI.h('div', { class: 'card dispatch-card', style: 'margin-bottom:12px' },
        UI.h('div', { class: 'toolbar' },
          UI.h('h3', { style: 'margin:0;border:none;padding:0' }, '钢铁企业')),
        UI.h('div', { style: 'margin:2px 0 8px' }, UI.kv([
          ['订单号', d.order.orderNo],
          ['品种', (d.order.varietyName || '-') + (d.order.grade ? ' ' + d.order.grade + '%' : '')],
          ['订单量', UI.fmtMoney(d.order.quantity) + ' 湿吨'],
          ['供方', d.order.supplierName || '-'],
          ['物流方案', d.order.planNo ? d.order.planNo + '（' + (ORG_LABEL[d.order.orgMode] || d.order.orgMode || '-') + '）' : '未制定'],
          ['起始地', d.order.startPlace || '-'],
          ['目的地', d.order.destPlace || '-'],
        ])),
        UI.h('div', { class: 'sec-title' }, '成员钢厂与货物信息'),
        memberBox);
      /* 物流节点轨迹：独立整框卡片（与钢厂端物流节点跟踪同款布局，外框线）；
         「推送至钢厂」置于卡片右下角——推送的正是这里的轨迹 */
      const steelTraceCard = UI.h('div', { class: 'card', style: 'margin-bottom:12px' },
        UI.h('h3', { class: 'bar-title' }, '物流节点轨迹',
          UI.h('button', { class: 'sm', style: 'margin-left:auto', onclick: steelNodeEntry }, '节点录入')),
        UI.h('div', { class: 'trace-box' }, traceSteel),
        UI.h('div', { style: 'display:flex;justify-content:flex-end;margin-top:10px' },
          UI.h('button', { class: 'primary', onclick: async () => {
            try {
              const res = await API.post('/admin/logistics-orders/' + d.order.id + '/push-mills');
              UI.toast('物流节点轨迹已推送至 ' + (res.pushed || 0) + ' 家钢厂，钢厂端「物流服务」将自动更新', 'ok');
            } catch (e) { /* toast 已提示 */ }
          } }, '推送至钢厂')));
      /* 供应商面板：需方（参与本单集采的钢铁企业）+ 运输方案三框 + 分段轨迹 + 推送 */
      /* 新增分段运单弹窗所需行数据（从详情数据构造：已排量/段数按运单汇总；带运单明细与起讫地预填） */
      const rWb = {
        id: d.order.id, orderNo: d.order.orderNo, planId: d.order.planId,
        planNo: d.order.planNo, orgMode: d.order.orgMode,
        quantity: Number(d.order.quantity) || 0,
        plannedQty: (d.waybills || []).reduce((s, w) => s + (Number(w.planQty) || 0), 0),
        waybillCount: (d.waybills || []).length,
        waybills: d.waybills || [],
        startPlace: d.order.startPlace || '',
        destPlace: d.order.destPlace || '',
      };
      const supCard = UI.h('div', { class: 'card dispatch-card', style: 'margin-bottom:12px' },
        UI.h('div', { class: 'toolbar' },
          UI.h('h3', { style: 'margin:0;border:none;padding:0' }, '供应商')),
        UI.h('div', { style: 'margin:2px 0 8px' }, UI.kv([
          ['订单号', d.order.orderNo],
          ['订单量', UI.fmtMoney(d.order.quantity) + ' 湿吨'],
          ['供方', d.order.supplierName || '-'],
          ['需方', d.order.buyerName || '平台集采'],
          ['物流方案', d.order.planNo ? d.order.planNo + '（' + (ORG_LABEL[d.order.orgMode] || d.order.orgMode || '-') + '）' : '未制定'],
          ['起始地', d.order.startPlace || '-'],
          ['目的地', d.order.destPlace || '-'],
        ])),
        UI.h('div', { class: 'sec-title', style: 'display:flex;align-items:center;justify-content:space-between' },
          UI.h('span', {}, '运输方案'),
          UI.h('button', { class: 'sm primary', onclick: pushPlanOnly }, '推送供应商')),
        UI.h('div', { style: 'margin:4px 0 2px;display:flex;flex-direction:column;gap:10px' },
          modeRow('铁路直达', railTa),
          modeRow('公铁联运', multiTa),
          modeRow('汽运直达', truckTa)));
      /* 物流运输轨迹：独立整框卡片（增加分段运单 + 分段筛选 + 节点录入，外框线）；
         「推送轨迹 / 推送货物信息」置于卡片右下角——推送的正是这里的轨迹与货物信息 */
      const supTraceCard = UI.h('div', { class: 'card', style: 'margin-bottom:12px' },
        UI.h('h3', { class: 'bar-title' }, '物流运输轨迹',
          UI.h('button', { class: 'sm primary', style: 'margin-left:auto', onclick: () => waybillCreateModal(rWb, refreshDetail) }, '增加')),
        UI.h('div', { class: 'trace-box' }, traceSup),
        UI.h('div', { style: 'display:flex;justify-content:flex-end;gap:8px;margin-top:10px' },
          UI.h('button', { class: 'primary', onclick: async () => {
            try {
              await API.post('/admin/logistics-orders/' + d.order.id + '/push-supplier', { scope: 'TRACE' });
              UI.toast('物流运输轨迹已推送，供应商端「物流服务」将自动更新', 'ok');
            } catch (e) { /* toast 已提示 */ }
          } }, '推送轨迹'),
          UI.h('button', { class: 'primary', onclick: async () => {
            try {
              await API.post('/admin/logistics-orders/' + d.order.id + '/push-supplier', { scope: 'CARGO' });
              UI.toast('货物信息已推送，供应商端「物流服务」将自动更新', 'ok');
            } catch (e) { /* toast 已提示 */ }
          } }, '推送货物信息')));
      const tabRow = UI.h('div', { style: 'display:flex;gap:8px;margin-bottom:12px' },
        UI.h('button', { class: 'primary', onclick: () => switchTab('steel') }, '钢铁企业'),
        UI.h('button', { onclick: () => switchTab('supplier') }, '供应商'));
      page.appendChild(tabRow);
      page.appendChild(steelCard);
      page.appendChild(steelTraceCard);
      page.appendChild(supCard);
      page.appendChild(supTraceCard);
      function switchTab(t) {
        const btns = tabRow.querySelectorAll('button');
        btns[0].className = t === 'steel' ? 'primary' : '';
        btns[1].className = t === 'supplier' ? 'primary' : '';
        steelCard.style.display = t === 'steel' ? '' : 'none';
        steelTraceCard.style.display = t === 'steel' ? '' : 'none';
        supCard.style.display = t === 'supplier' ? '' : 'none';
        supTraceCard.style.display = t === 'supplier' ? '' : 'none';
      }
      switchTab('steel');
    }

    /* 95306 式节点录入：起运地/到达地首次录入后固定（只读展示）；
       「运单当前到达节点（可选可编辑）+ 节点发生时间」每提交一次向物流轨迹新增一条，
       同一节点再次录入（时间不同）覆盖原记录（覆盖前提示确认）；
       onDone：录入成功后的刷新回调（订单详情弹窗传入轨迹刷新） */
    function nodeEntryModal(w, onDone) {
      const SUGGEST = ['船已到港，待发运', '货物已出港发运', '货物已到达中转站', '货物已到达目的地'];
      const textRow = (v) => UI.h('div', { style: 'line-height:32px;color:var(--ink-3,#888)' }, v);
      /* 起讫：首次录入后固定（已有值只读展示） */
      const departInp = w.departPlace ? null : UI.h('input', { style: 'width:100%;height:32px', placeholder: '如：黄骅港' });
      const arriveInp = w.arrivePlace ? null : UI.h('input', { style: 'width:100%;height:32px', placeholder: '如：邯郸南站 / 钢厂场区' });
      const placeVal = (inp, fixed) => (inp ? inp.value.trim() : (fixed || ''));
      const placesPayload = () => ({
        departPlace: placeVal(departInp, w.departPlace) || undefined,
        arrivePlace: placeVal(arriveInp, w.arrivePlace) || undefined,
      });
      const placesChanged = () => (departInp && departInp.value.trim() !== (w.departPlace || ''))
        || (arriveInp && arriveInp.value.trim() !== (w.arrivePlace || ''));
      /* 运单当前到达节点：文本框 + 建议列表（可自行编辑任意节点描述） */
      const nodeInp = UI.h('input', {
        type: 'text', list: 'node-suggest-' + w.id,
        style: 'width:100%;height:32px',
        placeholder: '选择或自行录入节点，如：船已到港，待发运',
      });
      const occur = UI.h('input', { type: 'datetime-local', style: 'height:32px' });
      const fmtT = (v) => v.replace('T', ' ') + (v.length === 16 ? ':00' : '');
      const norm = (s) => String(s || '').replace(/。*$/, '');
      /* 同节点重复录入检测：时间不同 → 覆盖原记录（前端提示确认） */
      const hasSameNode = (txt) => (Array.isArray(w.nodeLog) ? w.nodeLog : [])
        .some((e) => norm(e.desc) === norm(txt));
      /* 保存：起讫信息一并保存；轨迹节点 + 发生时间新增/覆盖一条物流轨迹 */
      const save = async () => {
        const txt = (nodeInp.value || '').trim();
        if (!txt) { UI.toast('请填写运单当前到达节点', 'err'); return; }
        if (!occur.value) { UI.toast('请填写节点发生时间', 'err'); return; }
        if (txt.length > 100) { UI.toast('节点描述不能超过 100 字', 'err'); return; }
        const dup = hasSameNode(txt);
        if (dup && !(await UI.confirmBox('节点「' + txt + '」已录入过，再次录入将覆盖原记录，是否继续？'))) return;
        const dp = placeVal(departInp, w.departPlace);
        const ap = placeVal(arriveInp, w.arrivePlace);
        const locOf = {
          '船已到港，待发运': dp || '起运港',
          '货物已出港发运': dp || '起运地',
          '货物已到达中转站': w.transitStation || '中转站',
          '货物已到达目的地': ap || '目的地',
        };
        try {
          if (placesChanged()) {
            await API.put('/admin/waybills/' + w.id + '/advance',
              Object.assign({ action: 'PLACES' }, placesPayload()));
          }
          await API.post('/admin/waybills/' + w.id + '/trace-log',
            { desc: txt, loc: locOf[txt] || '节点', occurTime: fmtT(occur.value) });
          m.close();
          UI.toast(dup ? '节点「' + txt + '」已覆盖更新，物流轨迹已同步' : '节点已录入，物流轨迹已新增一条', 'ok');
          if (onDone) onDone();
        } catch (e) { /* toast 已提示 */ }
      };
      const m = UI.modal('节点录入 · ' + w.waybillNo,
        UI.h('form', { onsubmit: (e) => e.preventDefault() },
          UI.h('div', { class: 'form-grid' },
            UI.formRow('运单号', textRow(w.waybillNo)),
            UI.formRow('订单号', textRow(w.orderNo || '-')),
            w.departPlace ? UI.formRow('起运地', textRow(w.departPlace)) : UI.formRow('起运地', departInp),
            w.arrivePlace ? UI.formRow('到达地', textRow(w.arrivePlace)) : UI.formRow('到达地', arriveInp),
            /* 整行：运单当前到达节点（可选可编辑）+ 节点发生时间 */
            UI.h('div', { class: 'form-row full' },
              UI.h('label', {}, '运单当前到达节点'), nodeInp,
              UI.h('datalist', { id: 'node-suggest-' + w.id },
                SUGGEST.map((t) => UI.h('option', { value: t })))),
            UI.h('div', { class: 'form-row full' }, UI.h('label', {}, '节点发生时间'), occur))), [
          UI.h('button', { class: 'primary', onclick: save }, '保 存'),
        ]);
    }
  }
  Pages.logistics_dispatch = function (page) { return logisticsPage(page); };
  Pages.logistics_order_detail = function (page, user, query) { return logisticsPage(page, { oid: query && Number(query.oid) }); };
})();
