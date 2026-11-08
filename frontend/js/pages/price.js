/* 价格（PRD 4.3/FR-03/T07）：基准价行情（钢厂）+ 远期预报发布与失效（供应商） */
(function () {
  window.Pages = window.Pages || {};
  const PT = { TEN_DAY: '旬度', MONTHLY: '月度' };
  const PB = { WET: '湿基', DRY: '干基' };

  /* -------- 钢厂：基准价行情 -------- */
  Pages.price = async function (page) {
    const d = await API.get('/base-prices/current');
    const card = UI.h('div', { class: 'card' },
      UI.h('h3', {}, '今日基准价'),
      UI.table([
        { key: 'varietyName', label: '品种' },
        { key: 'price', label: '基准价(元/吨)', num: true, render: (r) => UI.fmtMoney(r.price) },
        { key: 'priceBasis', label: '计价口径', render: (r) => PB[r.priceBasis] || r.priceBasis || '-' },
        { key: 'priceDate', label: '价格日期', render: (r) => UI.fmtDate(r.priceDate) },
        { key: 'sourceDesc', label: '来源' },
      ], d.today, '今日暂无基准价'));
    page.appendChild(card);

    const byVariety = {};
    (d.trend || []).forEach((r) => {
      (byVariety[r.varietyId] = byVariety[r.varietyId] || []).push(r);
    });
    const nameOf = {};
    (d.today || []).forEach((r) => { nameOf[r.varietyId] = r.varietyName; });
    const trendCard = UI.h('div', { class: 'card' }, UI.h('h3', {}, '近 30 日走势'));
    const ids = Object.keys(byVariety);
    if (!ids.length) trendCard.appendChild(UI.h('div', { class: 'empty' }, '暂无走势数据'));
    ids.forEach((vid) => {
      const rows = byVariety[vid].slice().sort((a, b) => String(a.priceDate).localeCompare(String(b.priceDate)));
      trendCard.appendChild(UI.h('div', { style: 'margin-bottom:16px' },
        UI.h('div', { style: 'font-weight:bold;margin-bottom:6px' }, nameOf[vid] || ('品种 ' + vid)),
        UI.trendChart(rows, 'price')));
    });
    page.appendChild(trendCard);
  };

  /* -------- 供应商：远期预报 -------- */
  Pages.forecast = async function (page) {
    const varieties = (await API.get('/base/varieties')).list;
    const vOpts = varieties.map((v) => [v.id, v.varietyName + '(' + v.varietyCode + ')']);

    const mineCard = UI.h('div', { class: 'card' });
    const poolCard = UI.h('div', { class: 'card' });
    page.appendChild(UI.h('div', { class: 'card' },
      UI.h('div', { class: 'toolbar' },
        UI.h('h3', { style: 'margin:0;border:none;padding:0' }, '我的预报'),
        UI.h('div', { class: 'spacer' }),
        UI.h('button', { class: 'primary', onclick: () => forecastForm(load) }, '新增预报'))));
    page.appendChild(mineCard);
    page.appendChild(UI.h('div', { class: 'card' }, UI.h('h3', { style: 'margin:0;border:none;padding:0' }, '预报池（全部已生效预报，标注：预判价，非平台成交价）')));
    page.appendChild(poolCard);

    const cols = (mine) => [
      { key: 'forecastNo', label: '预报编号' },
      { key: 'varietyName', label: '品种' },
      { label: '周期', render: (r) => (PT[r.periodType] || r.periodType || '-') + '（' + UI.fmtDate(r.periodStart) + ' ~ ' + UI.fmtDate(r.periodEnd) + '）' },
      { key: 'availableQty', label: '可供量(吨)', num: true, render: (r) => UI.fmtMoney(r.availableQty) },
      { key: 'forecastPrice', label: '预判价', num: true, render: (r) => UI.fmtMoney(r.forecastPrice) },
      { key: 'priceBasis', label: '口径', render: (r) => PB[r.priceBasis] || r.priceBasis || '-' },
      { key: 'deliveryPort', label: '交货港口' },
      { key: 'validUntil', label: '有效期至', render: (r) => UI.fmtDate(r.validUntil) },
      { key: 'status', label: '状态', render: (r) => UI.statusTag('FORECAST', r.status) },
    ].concat(mine ? [{ label: '操作', render: (r) => r.status === 'EFFECTIVE'
      ? UI.h('button', { class: 'sm danger', onclick: async () => {
          if (!(await UI.confirmBox('确认将该预报置为失效？'))) return;
          await API.post('/forecast-quotes/' + r.id + '/expire');
          UI.toast('已失效', 'ok'); load();
        } }, '置为失效')
      : '-' }] : [{ key: 'supplierName', label: '供应商' }]);

    async function load() {
      const mine = await API.get('/forecast-quotes?mine=1&size=100');
      mineCard.innerHTML = '';
      mineCard.appendChild(UI.table(cols(true), mine.list || mine, '暂无预报'));
      const pool = await API.get('/forecast-quotes?status=EFFECTIVE&size=100');
      poolCard.innerHTML = '';
      poolCard.appendChild(UI.table(cols(false), pool.list || pool, '暂无生效预报'));
    }

    function forecastForm(onDone) {
      const varietySel = UI.selectField(vOpts, vOpts.length ? vOpts[0][0] : '');
      const pt = UI.selectField(Object.entries(PT), 'MONTHLY');
      const start = UI.input('date', '', { placeholder: '周期开始日，如 2026-11-01' });
      const end = UI.input('date', '', { placeholder: '周期结束日，如 2026-11-30' });
      const qty = UI.input('number', '', { placeholder: '可供数量（吨）' });
      const price = UI.input('number', '', { placeholder: '预判价（元/吨）' });
      const basis = UI.selectField(Object.entries(PB), 'WET');
      const port = UI.input('text', '', { placeholder: '交货港口（选填）' });
      const valid = UI.input('date', '', { placeholder: '预报有效期截止日' });
      const remark = UI.h('textarea', { rows: 2, style: 'width:100%', placeholder: '选填，补充说明' });
      const m = UI.modal('新增远期预报', UI.h('form', { onsubmit: (e) => e.preventDefault() },
        UI.h('div', { class: 'form-grid' },
          UI.formRow('品种', varietySel, true),
          UI.formRow('周期类型', pt, true),
          UI.formRow('周期开始', start, true),
          UI.formRow('周期结束', end, true),
          UI.formRow('可供数量', qty, true),
          UI.formRow('预判价', price, true),
          UI.formRow('计价口径', basis),
          UI.formRow('交货港口', port),
          UI.formRow('有效期至', valid),
          UI.h('div', { class: 'form-row full' }, UI.h('label', {}, '备注'), remark)),
        UI.h('div', { class: 'hint' }, '发布后将向需方展示，并标注"预判价，非平台成交价"')), [
        UI.h('button', { class: 'primary', onclick: async () => {
          const body = {
            varietyId: Number(varietySel.value), periodType: pt.value,
            periodStart: start.value, periodEnd: end.value,
            availableQty: qty.value, forecastPrice: price.value,
            priceBasis: basis.value,
          };
          if (!body.periodStart || !body.periodEnd) { UI.toast('周期日期为必填', 'err'); return; }
          if (!body.availableQty || !body.forecastPrice) { UI.toast('可供数量与预判价为必填', 'err'); return; }
          if (port.value.trim()) body.deliveryPort = port.value.trim();
          if (valid.value) body.validUntil = valid.value;
          if (remark.value.trim()) body.remark = remark.value.trim();
          try {
            await API.post('/forecast-quotes', body);
            m.close(); UI.toast('预报已发布', 'ok'); onDone();
          } catch (e) { /* toast 已提示 */ }
        } }, '发 布'),
      ], { wide: true });
    }

    await load();
  };
})();
