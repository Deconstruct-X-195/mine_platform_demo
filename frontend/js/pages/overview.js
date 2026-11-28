/* 总览（#/overview）：钢厂端 KPI+采购全流程+待办事项；供应商端 KPI+待办事项+近期动态 */
(function () {
  window.Pages = window.Pages || {};

  /* 全流程 8 阶段线性图标（与后端 flow 顺序一一对应） */
  const FLOW_ICONS = [
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="5" y="4" width="14" height="17" rx="2"/><path d="M9 2h6v4H9z"/><path d="M9 11h6M9 15h6"/></svg>',
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M21 11.5a8.5 8.5 0 0 1-8.5 8.5c-1.5 0-2.9-.4-4.1-1L3 20l1.1-4.9A8.5 8.5 0 1 1 21 11.5z"/></svg>',
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="5" width="18" height="14" rx="2"/><path d="M3 7.5l9 6 9-6"/></svg>',
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="7"/><path d="M21 21l-4.3-4.3"/></svg>',
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M14 3H6a1 1 0 0 0-1 1v16a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1V8z"/><path d="M14 3v5h5"/><path d="M9 13h6M9 17h6"/></svg>',
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M2.5 7h11.5v9H2.5z"/><path d="M14 10h4l3.5 3v3H14z"/><circle cx="7" cy="18.5" r="1.8"/><circle cx="17" cy="18.5" r="1.8"/></svg>',
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M21 8l-9-5-9 5v8l9 5 9-5z"/><path d="M3 8l9 5 9-5"/><path d="M12 13v8"/></svg>',
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="6" width="20" height="12" rx="2"/><circle cx="12" cy="12" r="3"/><path d="M6 12h.01M18 12h.01"/></svg>',
  ];
  const flowIcon = (i) => {
    const el = document.createElement('span');
    el.className = 'flow-circle';
    el.innerHTML = FLOW_ICONS[i] || '';
    return el;
  };

  Pages.overview = async function (page, user) {
    const roles = (user && user.roles) || [];
    if (roles.indexOf('SUPPLIER') >= 0) return supplierOverview(page);
    const d = await API.get('/buyer/overview');
    const kpi = d.kpi || {};                       // P3-14：后端缺字段/接口异常时空值兜底，防整页渲染失败
    const flow = Array.isArray(d.flow) ? d.flow : [];

    /* 1. KPI 面板 */
    const kpis = [
      ['订单总数', kpi.orderTotal, '单', '#/order'],
      ['待询价', kpi.pendingInquiry, '条', '#/demand'],
      ['运输中', kpi.inTransit, '票', '#/logistics'],
      ['待付款', kpi.pendingPay, '笔', '#/order'],
    ];
    page.appendChild(UI.h('div', { class: 'card stat-strip' },
      kpis.map(([label, val, unit, hash]) => UI.h('a', { class: 'stat-strip-item ov-kpi', href: hash },
        UI.h('div', { class: 'stat-label' }, label),
        UI.h('div', { class: 'stat-value' }, String(val), UI.h('span', { class: 'stat-unit' }, unit))))));

    /* 2. 采购全流程概览：圆形图标步骤条（数量+阶段名），有业务量的阶段高亮，可点击跳转 */
    page.appendChild(UI.h('div', { class: 'card' },
      UI.h('h3', { class: 'bar-title' }, '采购全流程概览',
        UI.h('button', { class: 'sm primary', style: 'margin-left:auto', onclick: () => { location.hash = '#/demand'; } }, '去采购')),
      UI.h('div', { class: 'flow-steps' },
        flow.map((s, i) => [
          i ? UI.h('span', { class: 'flow-arrow' }, '→') : null,
          UI.h('a', {
            class: 'flow-step' + (s.count > 0 ? ' active' : '') + (s.hash ? '' : ' disabled'),
            href: s.hash || 'javascript:;',
            onclick: s.hash ? null : (e) => e.preventDefault(),
          },
            flowIcon(i),
            UI.h('div', { class: 'flow-count' }, String(s.count), UI.h('span', { class: 'unit' }, '笔')),
            UI.h('div', { class: 'flow-name' }, s.label)),
        ]).flat())));

    /* 3. 待办事项列表（与供应商端一致）：需求待提交/重提 · 询价待评审/议价中 · 到货待签收 */
    const todos = d.todos || [];
    page.appendChild(UI.h('div', { class: 'card' },
      UI.h('h3', { class: 'bar-title' }, '待办事项',
        UI.h('span', { class: 'hint', style: 'margin-left:auto' },
          todos.length ? '共 ' + todos.length + ' 项待处理' : '')),
      todos.length ? UI.table([
        { label: '类型', render: (t) => {
            const [txt, color] = STEEL_TODO_TAG[t.kind] || ['待办', ''];
            return UI.h('span', { class: 'tag' + color }, txt);
          } },
        { label: '事项', render: (t) => t.main },
        { label: '时间', render: (t) => t.time ? UI.fmtDateTime(t.time) : '-' },
        { label: '操作', render: (t) => UI.h('button', { class: 'sm primary',
            onclick: () => { location.hash = STEEL_TODO_HASH[t.kind] || '#/'; } }, '去处理') },
      ], todos) : UI.h('div', { class: 'empty' }, '暂无待办事项，一切进展顺利')));
  };

  /* 钢厂端待办：类型标签与跳转菜单（#/bargain 页面已并入询价报价议价页，P2-1 修复死链） */
  const STEEL_TODO_TAG = {
    DEMAND: ['待提交', ' orange'], REVIEW: ['待评审', ' red'],
    BARGAIN: ['议价中', ' blue'], ARRIVED: ['待签收', ' blue'],
  };
  const STEEL_TODO_HASH = { DEMAND: '#/demand', REVIEW: '#/inquiry', BARGAIN: '#/inquiry', ARRIVED: '#/track' };

  /* 供应商端总览：KPI 五卡 + 待办事项列表 + 近期动态 */
  const SUP_TODO_TAG = { QUOTE: ['待报价', ' orange'], CONFIRM: ['待确认', ' red'] };
  const SUP_TODO_HASH = { QUOTE: '#/inquiry', CONFIRM: '#/order' };

  async function supplierOverview(page) {
    const d = await API.get('/supplier/overview');
    const kpi = d.kpi || {};                       // P3-14：空值兜底同钢厂端

    /* 1. KPI 面板（五卡） */
    const kpis = [
      ['总订单数', kpi.orderTotal, '单', '#/order'],
      ['总吨数', UI.fmtQty(kpi.totalQty), '湿吨', '#/order'],
      ['待报价单数', kpi.pendingQuote, '条', '#/inquiry'],
      ['运输中单数', kpi.inTransit, '票', '#/track'],
      ['已完成订单', kpi.completed, '单', '#/order'],
    ];
    page.appendChild(UI.h('div', { class: 'card stat-strip' },
      kpis.map(([label, val, unit, hash]) => UI.h('a', { class: 'stat-strip-item ov-kpi', href: hash },
        UI.h('div', { class: 'stat-label' }, label),
        UI.h('div', { class: 'stat-value' }, String(val), UI.h('span', { class: 'stat-unit' }, unit))))));

    /* 2. 待办事项列表 */
    const todos = d.todos || [];
    page.appendChild(UI.h('div', { class: 'card' },
      UI.h('h3', { class: 'bar-title' }, '待办事项',
        UI.h('span', { class: 'hint', style: 'margin-left:auto' },
          todos.length ? '共 ' + todos.length + ' 项待处理' : '')),
      todos.length ? UI.table([
        { label: '类型', render: (t) => {
            const [txt, color] = SUP_TODO_TAG[t.kind] || ['待办', ''];
            return UI.h('span', { class: 'tag' + color }, txt);
          } },
        { label: '事项', render: (t) => t.main },
        { label: '时间', render: (t) => t.time ? UI.fmtDateTime(t.time) : '-' },
        { label: '操作', render: (t) => UI.h('button', { class: 'sm primary',
            onclick: () => { location.hash = SUP_TODO_HASH[t.kind] || '#/'; } }, '去处理') },
      ], todos) : UI.h('div', { class: 'empty' }, '暂无待办事项，一切进展顺利')));

    /* 3. 近期动态（运营端发布的公告/活动信息，最近 10 条；订单相关的任务/消息在小铃铛中显示） */
    const recent = d.recent || [];
    page.appendChild(UI.h('div', { class: 'card' },
      UI.h('h3', { class: 'bar-title' }, '近期动态'),
      recent.length ? UI.table([
        { label: '分类', render: (r) => UI.h('span', { class: 'tag' },
          ({ ANNOUNCE: '公告', ACTIVITY: '活动' }[r.msgCategory || r.category] || '消息')) },
        { label: '动态', render: (r) => UI.h('span', {}, r.title,
            UI.h('div', { class: 'hint' }, r.content)) },
        { label: '时间', render: (r) => UI.fmtDateTime(r.created_at) },
      ], recent) : UI.h('div', { class: 'empty' }, '暂无动态')));
  }
})();
