/* 通用 UI 组件：DOM 构建、表格、弹窗、toast、状态标签、分页、趋势图 */
(function () {
  function h(tag, props, ...children) {
    const el = document.createElement(tag);
    for (const [k, v] of Object.entries(props || {})) {
      if (k === 'class') el.className = v;
      else if (k === 'style') el.style.cssText = v;
      else if (k.startsWith('on') && typeof v === 'function') el.addEventListener(k.slice(2), v);
      else if (k === 'value') el.value = v;
      else if (k === 'checked') el.checked = !!v;
      else if (k === 'disabled') el.disabled = !!v;
      else if (k === 'selected') el.selected = !!v;
      else el.setAttribute(k, v == null ? '' : v);
    }
    for (const c of children.flat(9)) {
      if (c == null || c === false) continue;
      el.appendChild(typeof c === 'string' || typeof c === 'number' ? document.createTextNode(String(c)) : c);
    }
    return el;
  }

  function toast(msg, type) {
    const t = h('div', { class: 'toast ' + (type || '') }, msg);
    document.getElementById('toast-wrap').appendChild(t);
    setTimeout(() => t.remove(), 3200);
  }

  function modal(title, bodyNode, footNodes, opts) {
    const close = () => mask.remove();
    const foot = h('div', { class: 'modal-foot' }, ...(footNodes || []), h('button', { onclick: close }, '关 闭'));
    const mask = h('div', { class: 'modal-mask', onclick: (e) => { if (e.target === mask) close(); } },
      h('div', { class: 'modal ' + ((opts && opts.wide) ? 'wide' : '') },
        h('div', { class: 'modal-head' }, title, h('span', { class: 'close', onclick: close }, '✕')),
        h('div', { class: 'modal-body' }, bodyNode), foot));
    document.body.appendChild(mask);
    return { close, mask };
  }

  function confirmBox(msg) {
    return new Promise((resolve) => {
      let m;
      const yes = () => { m.close(); resolve(true); };
      const no = () => { m.close(); resolve(false); };
      m = modal('请确认', h('div', {}, msg), [h('button', { class: 'primary', onclick: yes }, '确 定'),
        h('button', { onclick: no }, '取 消')]);
    });
  }

  /* columns: [{key,label,num,render(row)}] */
  function table(columns, rows, emptyText) {
    if (!rows || !rows.length) return h('div', { class: 'empty' }, emptyText || '暂无数据');
    return h('table', { class: 'grid' },
      h('thead', {}, h('tr', {}, ...columns.map(c => h('th', { class: c.num ? 'num' : '' }, c.label)))),
      h('tbody', {}, ...rows.map(r => h('tr', {},
        ...columns.map(c => h('td', { class: c.num ? 'num' : '' },
          c.render ? c.render(r) : (r[c.key] == null ? '-' : String(r[c.key]))))))));
  }

  function pager(container, page, size, total, onChange) {
    const pages = Math.max(1, Math.ceil(total / size));
    const prev = h('button', { class: 'sm', disabled: page <= 1, onclick: () => onChange(page - 1) }, '上一页');
    const next = h('button', { class: 'sm', disabled: page >= pages, onclick: () => onChange(page + 1) }, '下一页');
    container.appendChild(h('div', { class: 'pager' }, `共 ${total} 条 · 第 ${page}/${pages} 页 `, prev, next));
  }

  const STATUS = {
    DEMAND: { DRAFT: ['草稿', 'gray'], SUBMITTED: ['已提交', 'blue'], INQUIRING: ['询价中', 'blue'], DEALT: ['已成交', 'green'], CLOSED: ['已关闭', 'gray'], WITHDRAWN: ['已撤回', 'orange'] },
    INQUIRY: { DRAFT: ['草稿', 'gray'], SENT: ['已发出', 'blue'], QUOTING: ['报价中', 'blue'], CLOSED: ['已截止', 'gray'], BARGAINING: ['议价中', 'blue'], AWARDED: ['已定标', 'green'], FAILED: ['已流标', 'red'] },
    QUOTE: { SUBMITTED: ['已报价', 'blue'], REVEALED: ['已揭示', 'gray'], BARGAINING: ['议价中', 'blue'], WIN: ['中标', 'green'], LOSE: ['未中标', 'red'], REJECTED: ['已拒绝', 'red'] },
    BARGAIN: { PENDING: ['待响应', 'orange'], ACCEPTED: ['已接受', 'green'], REJECTED: ['已拒绝', 'red'], EXPIRED: ['已失效', 'gray'] },
    ORDER: { PENDING_CONFIRM: ['待供应商确认', 'orange'], PENDING_CONTRACT: ['待签合同', 'orange'], PENDING_EFFECT: ['待合同生效', 'orange'], PERFORMING: ['履约中', 'blue'], COMPLETED: ['已完成', 'green'], CANCELLED: ['已失效', 'red'] },
    CONTRACT: { PENDING_GENERATE: ['待生成', 'gray'], PENDING_BUYER: ['待需方签署', 'orange'], PENDING_SUPPLIER: ['待供方签署', 'orange'], EFFECTIVE: ['已生效', 'green'], VOID: ['已作废', 'red'] },
    WAYBILL: { PENDING_ASSIGN: ['待指派', 'gray'], PENDING_ACCEPT: ['待承运商接单', 'orange'], PENDING_DEPART: ['待发运', 'orange'], IN_TRANSIT: ['在途', 'blue'], ARRIVED: ['已到达', 'blue'], SIGNED: ['已签收', 'green'] },
    SETTLEMENT: { PENDING_CONFIRM_SUPPLIER: ['待供应商确认', 'orange'], PENDING_CONFIRM_BUYER: ['待需方确认', 'orange'], CONFIRMED: ['已确认', 'blue'], COMPLETED: ['已完成', 'green'] },
    FORECAST: { EFFECTIVE: ['生效中', 'green'], EXPIRED: ['已失效', 'gray'] },
    ALERT: { PENDING: ['待处理', 'orange'], PROCESSING: ['处理中', 'blue'], CLOSED: ['已关闭', 'gray'] },
    AUDIT: { PENDING: ['待审核', 'orange'], APPROVED: ['已准入', 'green'], REJECTED: ['已驳回', 'red'] },
    ENT: { ENABLED: ['正常', 'green'], DISABLED: ['已禁用', 'red'] },
    USER: { ENABLED: ['正常', 'green'], DISABLED: ['已禁用', 'red'] },
  };
  function statusTag(kind, code) {
    const m = (STATUS[kind] || {})[code];
    if (!m) return h('span', { class: 'tag' }, code || '-');
    return h('span', { class: 'tag ' + m[1] }, m[0]);
  }

  function kv(pairs) {
    /* pairs: [[label, value, full?]] */
    return h('div', { class: 'kv' }, ...pairs.map(([k, v, full]) => [
      h('span', { class: 'k' }, k + '：'),
      h('span', { class: full ? 'full' : '' }, v == null || v === '' ? '-' : v),
    ]).flat());
  }

  function formRow(label, input, required, hint) {
    return h('div', { class: 'form-row' },
      h('label', { class: required ? 'req' : '' }, label),
      input, hint ? h('div', { class: 'hint' }, hint) : null);
  }

  function selectField(options, value, props) {
    return h('select', Object.assign({}, props, { value: value == null ? '' : value }),
      ...options.map(([v, t]) => h('option', { value: v, selected: String(v) === String(value) }, t)));
  }

  /* 近30日基准价 SVG 折线 */
  function trendChart(rows, priceKey) {
    const pts = (rows || []).filter(r => r[priceKey] != null);
    if (pts.length < 2) return h('div', { class: 'empty' }, '数据不足，暂无走势');
    const vals = pts.map(r => parseFloat(r[priceKey]));
    const min = Math.min(...vals), max = Math.max(...vals);
    const span = (max - min) || 1;
    const W = 600, H = 140, P = 10;
    const xy = (i) => [P + i * (W - 2 * P) / (pts.length - 1), H - P - (vals[i] - min) / span * (H - 2 * P)];
    const line = vals.map((_, i) => xy(i).join(',')).join(' ');
    const svgNS = 'http://www.w3.org/2000/svg';
    const svg = document.createElementNS(svgNS, 'svg');
    svg.setAttribute('class', 'trend-svg');
    svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
    svg.setAttribute('preserveAspectRatio', 'none');
    const poly = document.createElementNS(svgNS, 'polyline');
    poly.setAttribute('points', line);
    poly.setAttribute('fill', 'none');
    poly.setAttribute('stroke', '#1a5cb0');
    poly.setAttribute('stroke-width', '2');
    svg.appendChild(poly);
    for (let i = 0; i < pts.length; i++) {
      const [x, y] = xy(i);
      const c = document.createElementNS(svgNS, 'circle');
      c.setAttribute('cx', x); c.setAttribute('cy', y); c.setAttribute('r', '3');
      c.setAttribute('fill', '#1a5cb0');
      const title = document.createElementNS(svgNS, 'title');
      title.textContent = `${pts[i].priceDate || ''}  ${vals[i]}`;
      c.appendChild(title);
      svg.appendChild(c);
    }
    return svg;
  }

  function input(type, value, props) {
    const el = h('input', Object.assign({}, props || {}));
    if (value != null && value !== '') el.value = value;
    return el;
  }

  function statusFilter(kind, onChange) {
    const opts = [['', '全部状态']].concat(
      Object.entries(STATUS[kind] || {}).map(([code, m]) => [code, m[0]]));
    return selectField(opts, '', { onchange: (e) => onChange(e.target.value) });
  }

  function timeline(nodes) {
    if (!nodes || !nodes.length) return h('div', { class: 'empty' }, '暂无节点记录');
    return h('ul', { class: 'timeline' }, ...nodes.map((n) => h('li',
      { class: n.correctNodeId ? 'corrected' : '' },
      h('span', { class: 't-time' }, fmtDateTime(n.occurTime)),
      h('span', { class: 't-name' }, n.nodeName || n.nodeCode || '-'),
      n.source === 'MANUAL' ? h('span', { class: 'tag orange' }, '手工') : null,
      n.source === 'CARRIER' ? h('span', { class: 'tag blue' }, '承运商') : null,
      n.remark ? h('div', { class: 't-remark' }, n.remark) : null)));
  }

  window.UI = {
    h, toast, modal, confirmBox, table, pager, statusTag, kv, formRow, selectField,
    trendChart, input, statusFilter, timeline, STATUS,
    fmtDate(v) { return v == null || v === '' ? '-' : String(v).slice(0, 10); },
    fmtDateTime(v) { return v == null || v === '' ? '-' : String(v).replace('T', ' ').slice(0, 16); },
    fmtMoney(v) { return v == null || v === '' ? '-' : Number(v).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }); },
  };
})();
