/* 价格（PRD 4.3/FR-03）：基准价行情（钢厂） */
(function () {
  window.Pages = window.Pages || {};
  const PB = { WET: '湿基', DRY: '干基' };

  /* -------- 钢厂：基准价行情 -------- */
  const GRADE_OF = { 'PB粉': 61.5, '中华混一号': 61.5 };
  Pages.price = async function (page) {
    const d = await API.get('/base-prices/current');
    const card = UI.h('div', { class: 'card' },
      UI.h('h3', {}, '今日基准价'),
      UI.table([
        { key: 'varietyName', label: '产品名称' },
        { label: '品位', render: (r) => { const g = r.grade != null ? r.grade : GRADE_OF[r.varietyName]; return g != null ? String(g).replace(/\.?0+$/, '') + '%' : '-'; } },
        { label: '港口', render: (r) => r.port || '平台综合' },
        { key: 'price', label: '基准价(元/湿吨)', num: true, render: (r) => UI.fmtMoney(r.price) },
        { key: 'priceBasis', label: '计价口径', render: (r) => PB[r.priceBasis] || r.priceBasis || '-' },
        { key: 'priceDate', label: '价格日期', render: (r) => UI.fmtDate(r.priceDate) },
        { key: 'sourceDesc', label: '来源' },
      ], d.today, '今日暂无基准价'));
    page.appendChild(card);

    /* 近30日走势：每港口一张图，名称行下方右侧品位切换（同运营端，PB粉 61.5%/60.8%） */
    const byKey = {};
    (d.trend || []).forEach((r) => {
      const key = r.varietyId + '|' + (r.port || '');
      (byKey[key] = byKey[key] || []).push(r);
    });
    const nameOf = {};
    (d.trend || []).forEach((r) => { if (r.varietyName) nameOf[r.varietyId] = r.varietyName; });
    (d.today || []).forEach((r) => { nameOf[r.varietyId] = r.varietyName; });
    const titleOf = (vid) => nameOf[vid] || '产品 ' + vid;
    const trendCard = UI.h('div', { class: 'card' }, UI.h('h3', {}, '近 30 日走势'));
    const ids = Object.keys(byKey);
    if (!ids.length) trendCard.appendChild(UI.h('div', { class: 'empty' }, '暂无走势数据'));
    ids.forEach((key) => {
      const [vid, port] = key.split('|');
      const byGrade = {};
      byKey[key].forEach((r) => {
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
          byGrade[cur].map((r) => ({ priceDate: r.priceDate, price: r.price }))
            .sort((a, b) => String(a.priceDate).localeCompare(String(b.priceDate))), 'price'));
      }
      render();
      trendCard.appendChild(UI.h('div', { style: 'margin-bottom:16px' },
        UI.h('div', { style: 'font-weight:bold;margin-bottom:6px' },
          titleOf(vid) + (port ? ' · ' + port : ' · 平台综合')),
        UI.h('div', { style: 'text-align:right;margin:-4px 0 4px' }, ...gradeBtns),
        chartBox));
    });
    page.appendChild(trendCard);
  };

})();
