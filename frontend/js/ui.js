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
    // 布局修复：外层 table-wrap 提供横向滚动，列多时表格在卡片内滚动而非溢出
    return h('div', { class: 'table-wrap' },
      h('table', { class: 'grid' },
        h('thead', {}, h('tr', {}, ...columns.map(c => h('th', { class: c.num ? 'num' : '' }, c.label)))),
        h('tbody', {}, ...rows.map(r => h('tr', {},
          ...columns.map(c => h('td', { class: c.num ? 'num' : '' },
            c.render ? c.render(r) : (r[c.key] == null ? '-' : String(r[c.key])))))))));
  }

  function pager(container, page, size, total, onChange) {
    const pages = Math.max(1, Math.ceil(total / size));
    const prev = h('button', { class: 'sm', disabled: page <= 1, onclick: () => onChange(page - 1) }, '上一页');
    const next = h('button', { class: 'sm', disabled: page >= pages, onclick: () => onChange(page + 1) }, '下一页');
    container.appendChild(h('div', { class: 'pager' }, `共 ${total} 条 · 第 ${page}/${pages} 页 `, prev, next));
  }

  const STATUS = {
    DEMAND: { DRAFT: ['草稿', 'gray'], SUBMITTED: ['已提交', 'blue'], INQUIRING: ['询价中', 'blue'], DEALT: ['已成交', 'green'], CLOSED: ['已关闭', 'gray'], WITHDRAWN: ['已撤回', 'orange'] },
    INQUIRY: { DRAFT: ['草稿', 'gray'], SENT: ['已发出', 'blue'], QUOTING: ['报价中', 'blue'], CLOSED: ['已截止', 'gray'], FEEDBACK: ['反馈待处理', 'orange'], BARGAINING: ['议价中', 'blue'], AWARDED: ['已定标', 'green'], FAILED: ['已流标', 'red'] },
    QUOTE: { SUBMITTED: ['已报价', 'blue'], REVEALED: ['已揭示', 'gray'], BARGAINING: ['议价中', 'blue'], WIN: ['中标', 'green'], LOSE: ['未中标', 'red'], REJECTED: ['已拒绝', 'red'] },
    BARGAIN: { PENDING: ['待响应', 'orange'], ONGOING: ['待响应', 'orange'], ACCEPTED: ['已接受', 'green'], REJECTED: ['已拒绝', 'red'], EXPIRED: ['已失效', 'gray'] },
    ORDER: { PENDING_CONFIRM: ['待供应商确认', 'orange'], PENDING_CONTRACT: ['待签合同', 'orange'], PENDING_EFFECT: ['待合同生效', 'orange'], PERFORMING: ['履约中', 'blue'], COMPLETED: ['已完成', 'green'], CANCELLED: ['已失效', 'red'] },
    CONTRACT: { PENDING_GENERATE: ['待生成', 'gray'], PENDING_BUYER: ['待需方签署', 'orange'], PENDING_SUPPLIER: ['待供方签署', 'orange'], EFFECTIVE: ['已生效', 'green'], VOID: ['已作废', 'red'] },
    WAYBILL: { PENDING_ASSIGN: ['待指派', 'gray'], PENDING_ACCEPT: ['待承运商接单', 'orange'], PENDING_DEPART: ['待发运', 'orange'], IN_TRANSIT: ['在途', 'blue'], ARRIVED: ['已到达', 'blue'], SIGNED: ['已签收', 'green'], CANCELLED: ['已取消', 'gray'] },
    SETTLEMENT: { PENDING_CONFIRM_SUPPLIER: ['待供应商确认', 'orange'], PENDING_CONFIRM_BUYER: ['待需方确认', 'orange'], CONFIRMED: ['已确认', 'blue'], COMPLETED: ['已完成', 'green'] },
    FORECAST: { EFFECTIVE: ['生效中', 'green'], EXPIRED: ['已失效', 'gray'] },
    ALERT: { PENDING: ['待处理', 'orange'], PROCESSING: ['处理中', 'blue'], CLOSED: ['已关闭', 'gray'] },
    AUDIT: { PENDING: ['待审核', 'orange'], APPROVED: ['已准入', 'green'], REJECTED: ['已驳回', 'red'] },
    CHANGE: { PENDING: ['待审核', 'orange'], APPROVED: ['已通过', 'green'], REJECTED: ['已驳回', 'red'] },
    AGG: { OPEN: ['已归集', 'blue'], INQUIRING: ['询价中', 'orange'], AWARDED: ['已定标', 'green'], CLOSED: ['已关闭', 'gray'] },
    PLAT: { PENDING: ['待确认', 'orange'], CONFIRMED: ['已确认', 'green'], RETURNED: ['已退回', 'red'] },
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

  /* 近30日基准价 SVG 折线（网格坐标轴 + 面积渐变 + 悬浮十字提示） */
  let trendUid = 0;
  function trendChart(rows, priceKey, unitLabel) {
    const unit = unitLabel || '元/吨';
    const pts = (rows || []).filter(r => r[priceKey] != null);
    if (pts.length < 2) return h('div', { class: 'empty' }, '数据不足，暂无走势');
    const vals = pts.map(r => parseFloat(r[priceKey]));
    const W = 600, H = 230, ML = 48, MR = 14, MT = 16, MB = 28;
    const iw = W - ML - MR, ih = H - MT - MB;
    const rawMin = Math.min(...vals), rawMax = Math.max(...vals);
    const pad = (rawMax - rawMin) * 0.18 || Math.abs(rawMax) * 0.06 || 1;
    const lo = rawMin - pad, hi = rawMax + pad;
    const X = (i) => ML + i * iw / (pts.length - 1);
    const Y = (v) => MT + (hi - v) / (hi - lo) * ih;
    const fmtTick = (v) => Math.abs(v) >= 1000 ? v.toFixed(0) : v.toFixed(1);
    const fmtDay = (s) => { const m = String(s).match(/(\d{4})-(\d{2})-(\d{2})/); return m ? m[2] + '-' + m[3] : String(s); };
    const svgNS = 'http://www.w3.org/2000/svg';
    const el = (tag, attrs, text) => {
      const n = document.createElementNS(svgNS, tag);
      for (const k in attrs) n.setAttribute(k, attrs[k]);
      if (text != null) n.textContent = text;
      return n;
    };
    const svg = document.createElementNS(svgNS, 'svg');
    svg.setAttribute('class', 'trend-svg');
    svg.setAttribute('viewBox', `0 0 ${W} ${H}`);

    // 面积渐变（id 需按实例唯一，避免多图互相覆盖）
    const gid = 'trend-grad-' + (++trendUid);
    const defs = el('defs', {});
    const grad = el('linearGradient', { id: gid, x1: '0', y1: '0', x2: '0', y2: '1' });
    grad.appendChild(el('stop', { offset: '0%', 'stop-color': '#1a5cb0', 'stop-opacity': '0.20' }));
    grad.appendChild(el('stop', { offset: '100%', 'stop-color': '#1a5cb0', 'stop-opacity': '0.02' }));
    defs.appendChild(grad);
    svg.appendChild(defs);

    // y 轴网格线 + 刻度
    const TICKS = 4;
    for (let t = 0; t <= TICKS; t++) {
      const v = lo + (hi - lo) * t / TICKS;
      const gy = Y(v).toFixed(1);
      svg.appendChild(el('line', { x1: ML, y1: gy, x2: W - MR, y2: gy, stroke: '#ececf0', 'stroke-width': '1' }));
      svg.appendChild(el('text', { x: ML - 8, y: +gy + 4, 'text-anchor': 'end', 'font-size': '11', fill: '#86868b' }, fmtTick(v)));
    }
    // x 轴日期刻度（首/尾 + 中间均布）
    const xIdx = new Set([0, pts.length - 1]);
    for (let t = 1; t < 4; t++) xIdx.add(Math.round((pts.length - 1) * t / 4));
    [...xIdx].sort((a, b) => a - b).forEach((i) => {
      svg.appendChild(el('text', {
        x: X(i).toFixed(1), y: H - 8, 'font-size': '11', fill: '#86868b',
        'text-anchor': i === 0 ? 'start' : (i === pts.length - 1 ? 'end' : 'middle'),
      }, fmtDay(pts[i].priceDate)));
    });

    // 面积 + 折线 + 数据点
    const line = vals.map((v, i) => X(i).toFixed(1) + ',' + Y(v).toFixed(1)).join(' ');
    const base = (H - MB).toFixed(1);
    svg.appendChild(el('polygon', { points: `${X(0)},${base} ${line} ${X(pts.length - 1)},${base}`, fill: `url(#${gid})` }));
    svg.appendChild(el('polyline', {
      points: line, fill: 'none', stroke: '#1a5cb0', 'stroke-width': '2',
      'stroke-linejoin': 'round', 'stroke-linecap': 'round',
    }));
    vals.forEach((v, i) => svg.appendChild(el('circle', { cx: X(i).toFixed(1), cy: Y(v).toFixed(1), r: '3', fill: '#1a5cb0' })));

    // 悬浮十字线 + 提示框
    const hover = el('g', { style: 'display:none' });
    const vline = el('line', { y1: MT, y2: H - MB, stroke: '#c7c7cc', 'stroke-dasharray': '4 3', 'stroke-width': '1' });
    const hdot = el('circle', { r: '4.5', fill: '#1a5cb0', stroke: '#fff', 'stroke-width': '2' });
    const tipG = el('g', {});
    const tipRect = el('rect', { width: '118', height: '40', rx: '6', fill: 'rgba(250,250,252,.97)', stroke: '#e5e5ea' });
    const tipDate = el('text', { x: '10', y: '16', 'font-size': '11', fill: '#86868b' });
    const tipVal = el('text', { x: '10', y: '32', 'font-size': '12', 'font-weight': '600', fill: '#1d1d1f' });
    tipG.appendChild(tipRect); tipG.appendChild(tipDate); tipG.appendChild(tipVal);
    hover.appendChild(vline); hover.appendChild(hdot); hover.appendChild(tipG);
    svg.appendChild(hover);

    const overlay = el('rect', { x: ML, y: MT, width: iw, height: ih, fill: 'transparent' });
    overlay.addEventListener('mousemove', (e) => {
      const rect = svg.getBoundingClientRect();
      if (!rect.width) return;
      const px = (e.clientX - rect.left) * (W / rect.width);
      let i = Math.round((px - ML) / iw * (pts.length - 1));
      i = Math.max(0, Math.min(pts.length - 1, i));
      const cx = X(i), cy = Y(vals[i]);
      hover.style.display = '';
      vline.setAttribute('x1', cx); vline.setAttribute('x2', cx);
      hdot.setAttribute('cx', cx); hdot.setAttribute('cy', cy);
      let tx = cx + 10;
      if (tx + 118 > W - MR) tx = cx - 128;
      tipG.setAttribute('transform', `translate(${tx.toFixed(1)},${Math.max(MT, cy - 48).toFixed(1)})`);
      tipDate.textContent = fmtDay(pts[i].priceDate);
      tipVal.textContent = vals[i].toFixed(2) + ' ' + unit;
    });
    overlay.addEventListener('mouseleave', () => { hover.style.display = 'none'; });
    svg.appendChild(overlay);
    return svg;
    svg.setAttribute('preserveAspectRatio', 'none');
    // 底部时间轴基线
    const baseline = document.createElementNS(svgNS, 'line');
    baseline.setAttribute('x1', P); baseline.setAttribute('y1', H - P);
    baseline.setAttribute('x2', W - P); baseline.setAttribute('y2', H - P);
    baseline.setAttribute('stroke', '#d8dde5');
    baseline.setAttribute('stroke-width', '1');
    svg.appendChild(baseline);
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
    // 时间轴：图表下方首尾两个日期刻度（HTML 渲染，避免 SVG 拉伸变形）
    // 首个保留完整日期（含年份），末个省略年份（MM-DD）
    const axis = h('div', { class: 'trend-axis' });
    [0, pts.length - 1].forEach((idx, t) => {
      const raw = String(pts[idx].priceDate || '');
      const m = raw.match(/^\d{4}-(\d{2}-\d{2})/);
      axis.appendChild(h('span', {}, t === 0 ? raw : (m ? m[1] : raw)));
    });
    return h('div', { class: 'trend-wrap' }, svg, axis);
  }

  /* 多序列折线图（同图多线不同色：行业价格 vs 交易价格） */
  function multiTrendChart(series) {
    const wrap = h('div', {});
    const usable = (series || []).filter(s => s.rows && s.rows.length >= 2);
    wrap.appendChild(h('div', { class: 'trend-legend' },
      ...(series || []).map((s) => {
        const has = s.rows && s.rows.length >= 2;
        return h('span', { class: 'trend-legend-item' },
          h('span', { class: 'legend-dot', style: 'background:' + (has ? s.color : '#c7c7cc') }),
          s.name + (has ? '' : '（暂无数据）'));
      })));
    if (!usable.length) { wrap.appendChild(h('div', { class: 'empty' }, '数据不足，暂无走势')); return wrap; }

    const dateSet = new Set();
    usable.forEach((s) => s.rows.forEach((r) => dateSet.add(String(r.priceDate || '').slice(0, 10))));
    const dates = [...dateSet].sort();
    const idxOf = {}; dates.forEach((d, i) => { idxOf[d] = i; });
    const vals = [];
    usable.forEach((s) => s.rows.forEach((r) => vals.push(parseFloat(r.price))));
    const W = 600, H = 230, ML = 48, MR = 14, MT = 16, MB = 28;
    const iw = W - ML - MR, ih = H - MT - MB;
    const rawMin = Math.min(...vals), rawMax = Math.max(...vals);
    const pad = (rawMax - rawMin) * 0.18 || Math.abs(rawMax) * 0.06 || 1;
    const lo = rawMin - pad, hi = rawMax + pad;
    const X = (i) => ML + (dates.length === 1 ? iw / 2 : i * iw / (dates.length - 1));
    const Y = (v) => MT + (hi - v) / (hi - lo) * ih;
    const fmtTick = (v) => Math.abs(v) >= 1000 ? v.toFixed(0) : v.toFixed(1);
    const fmtDay = (t) => { const m = String(t).match(/(\d{4})-(\d{2})-(\d{2})/); return m ? m[2] + '-' + m[3] : String(t); };
    const svgNS = 'http://www.w3.org/2000/svg';
    const el = (tag, attrs, text) => {
      const n = document.createElementNS(svgNS, tag);
      for (const k in attrs) n.setAttribute(k, attrs[k]);
      if (text != null) n.textContent = text;
      return n;
    };
    const svg = document.createElementNS(svgNS, 'svg');
    svg.setAttribute('class', 'trend-svg');
    svg.setAttribute('viewBox', `0 0 ${W} ${H}`);

    const TICKS = 4;
    for (let t = 0; t <= TICKS; t++) {
      const v = lo + (hi - lo) * t / TICKS;
      const gy = Y(v).toFixed(1);
      svg.appendChild(el('line', { x1: ML, y1: gy, x2: W - MR, y2: gy, stroke: '#ececf0', 'stroke-width': '1' }));
      svg.appendChild(el('text', { x: ML - 8, y: +gy + 4, 'text-anchor': 'end', 'font-size': '11', fill: '#86868b' }, fmtTick(v)));
    }
    const xIdx = new Set([0, dates.length - 1]);
    for (let t = 1; t < 4; t++) xIdx.add(Math.round((dates.length - 1) * t / 4));
    [...xIdx].sort((a, b) => a - b).forEach((i) => {
      svg.appendChild(el('text', {
        x: X(i).toFixed(1), y: H - 8, 'font-size': '11', fill: '#86868b',
        'text-anchor': i === 0 ? 'start' : (i === dates.length - 1 ? 'end' : 'middle'),
      }, fmtDay(dates[i])));
    });

    const dots = [];
    usable.forEach((s) => {
      const pts = s.rows.slice().sort((a, b) => String(a.priceDate).localeCompare(String(b.priceDate)));
      const line = pts.map((r) => {
        const x = X(idxOf[String(r.priceDate).slice(0, 10)]).toFixed(1);
        const y = Y(parseFloat(r.price)).toFixed(1);
        return x + ',' + y;
      }).join(' ');
      svg.appendChild(el('polyline', {
        points: line, fill: 'none', stroke: s.color, 'stroke-width': '2',
        'stroke-linejoin': 'round', 'stroke-linecap': 'round',
        'stroke-dasharray': s.dashed ? '7 4' : 'none',
      }));
      pts.forEach((r) => {
        const cx = +X(idxOf[String(r.priceDate).slice(0, 10)]).toFixed(1);
        const cy = +Y(parseFloat(r.price)).toFixed(1);
        const c = el('circle', { cx, cy, r: '3', fill: s.color });
        svg.appendChild(c);
        dots.push({ cx, cy, date: String(r.priceDate).slice(0, 10), name: s.name, color: s.color, val: parseFloat(r.price) });
      });
    });

    const hover = el('g', { style: 'display:none' });
    const vline = el('line', { y1: MT, y2: H - MB, stroke: '#c7c7cc', 'stroke-dasharray': '4 3', 'stroke-width': '1' });
    const hdot = el('circle', { r: '4.5', stroke: '#fff', 'stroke-width': '2' });
    const tipG = el('g', {});
    const tipRect = el('rect', { width: '150', height: '40', rx: '6', fill: 'rgba(250,250,252,.97)', stroke: '#e5e5ea' });
    const tipDate = el('text', { x: '10', y: '16', 'font-size': '11', fill: '#86868b' });
    const tipVal = el('text', { x: '10', y: '32', 'font-size': '12', 'font-weight': '600', fill: '#1d1d1f' });
    tipG.appendChild(tipRect); tipG.appendChild(tipDate); tipG.appendChild(tipVal);
    hover.appendChild(vline); hover.appendChild(hdot); hover.appendChild(tipG);
    svg.appendChild(hover);

    const overlay = el('rect', { x: ML, y: MT, width: iw, height: ih, fill: 'transparent' });
    overlay.addEventListener('mousemove', (e) => {
      const rect = svg.getBoundingClientRect();
      if (!rect.width) return;
      const px = (e.clientX - rect.left) * (W / rect.width);
      let best = null, bd = Infinity;
      for (const p of dots) {
        const d = Math.abs(p.cx - px);
        if (d < bd) { bd = d; best = p; }
      }
      if (!best) return;
      hover.style.display = '';
      vline.setAttribute('x1', best.cx); vline.setAttribute('x2', best.cx);
      hdot.setAttribute('cx', best.cx); hdot.setAttribute('cy', best.cy); hdot.setAttribute('fill', best.color);
      tipRect.setAttribute('width', '150');
      tipDate.setAttribute('x', '10'); tipVal.setAttribute('x', '10');
      let tx = best.cx + 10;
      if (tx + 150 > W - MR) tx = best.cx - 160;
      tipG.setAttribute('transform', `translate(${tx.toFixed(1)},${Math.max(MT, best.cy - 48).toFixed(1)})`);
      tipDate.textContent = fmtDay(best.date) + ' · ' + best.name;
      tipVal.textContent = best.val.toFixed(2) + ' 元/吨';
    });
    overlay.addEventListener('mouseleave', () => { hover.style.display = 'none'; });
    svg.appendChild(overlay);
    wrap.appendChild(svg);
    return wrap;
  }

  /* 环形占比图（矿种分布等）：items=[{name,qty}]，valueKey/nameKey 可定制 */
  const CHART_COLORS = ['#1a5cb0', '#af52de', '#34c759', '#ff9500', '#ff3b30', '#5ac8fa', '#ffcc00', '#8e8e93'];
  function donutChart(items, valueKey, nameKey, centerLabel) {
    const vk = valueKey || 'qty', nk = nameKey || 'name';
    const data = (items || []).filter(i => parseFloat(i[vk]) > 0);
    const wrap = h('div', { class: 'donut-wrap' });
    if (!data.length) { wrap.appendChild(h('div', { class: 'empty' }, '暂无数据')); return wrap; }
    const total = data.reduce((s, i) => s + parseFloat(i[vk]), 0);
    const size = 170, cx = size / 2, cy = size / 2, r = 66, sw = 30;
    const svgNS = 'http://www.w3.org/2000/svg';
    const el = (tag, attrs, text) => {
      const n = document.createElementNS(svgNS, tag);
      for (const k in attrs) n.setAttribute(k, attrs[k]);
      if (text != null) n.textContent = text;
      return n;
    };
    const svg = document.createElementNS(svgNS, 'svg');
    svg.setAttribute('class', 'donut-svg');
    svg.setAttribute('viewBox', `0 0 ${size} ${size}`);
    const C = 2 * Math.PI * r;
    let acc = 0;
    data.forEach((item, i) => {
      const frac = parseFloat(item[vk]) / total;
      svg.appendChild(el('circle', {
        cx, cy, r, fill: 'none', stroke: CHART_COLORS[i % CHART_COLORS.length], 'stroke-width': sw,
        'stroke-dasharray': (frac * C).toFixed(2) + ' ' + C.toFixed(2),
        'stroke-dashoffset': (-acc * C).toFixed(2),
        transform: `rotate(-90 ${cx} ${cy})`,
      }));
      acc += frac;
    });
    const fmtInt = (v) => v >= 10000 ? (v / 10000).toFixed(1) + '万' : v.toFixed(0);
    svg.appendChild(el('text', { x: cx, y: cy - 4, 'text-anchor': 'middle', 'font-size': '15', 'font-weight': '700', fill: '#1d1d1f' }, fmtInt(total)));
    svg.appendChild(el('text', { x: cx, y: cy + 13, 'text-anchor': 'middle', 'font-size': '10', fill: '#86868b' }, centerLabel || '总量(吨)'));
    wrap.appendChild(svg);
    wrap.appendChild(h('div', { class: 'donut-legend' },
      ...data.map((item, i) => h('div', { class: 'donut-legend-item' },
        h('span', { class: 'legend-dot', style: 'background:' + CHART_COLORS[i % CHART_COLORS.length] }),
        h('span', { class: 'donut-legend-name' }, item[nk]),
        h('span', { class: 'donut-legend-val' }, (parseFloat(item[vk]) / total * 100).toFixed(1) + '%')))));
    return wrap;
  }

  /* 横向条形对比图（运输方式运量等）：items=[{name,qty}] */
  function hbarChart(items, valueKey, nameKey, unitLabel) {
    const vk = valueKey || 'qty', nk = nameKey || 'name';
    const data = (items || []).filter(i => parseFloat(i[vk]) > 0);
    const wrap = h('div', { class: 'hbar-wrap' });
    if (!data.length) { wrap.appendChild(h('div', { class: 'empty' }, '暂无数据')); return wrap; }
    const max = Math.max(...data.map(i => parseFloat(i[vk])));
    const fmtInt = (v) => v >= 10000 ? (v / 10000).toFixed(1) + '万' : v.toFixed(0);
    data.forEach((item, i) => {
      wrap.appendChild(h('div', { class: 'hbar-row' },
        h('span', { class: 'hbar-name' }, item[nk]),
        h('div', { class: 'hbar-track' },
          h('div', { class: 'hbar-fill', style: 'width:' + (parseFloat(item[vk]) / max * 100).toFixed(1) + '%;background:' + CHART_COLORS[i % CHART_COLORS.length] })),
        h('span', { class: 'hbar-val' }, fmtInt(parseFloat(item[vk])) + (unitLabel || '吨'))));
    });
    return wrap;
  }

  function input(type, value, props) {
    const el = h('input', Object.assign({}, props || {}));
    if (type) el.type = type;  // 修复：此前 type 参数被忽略，date/number 字段渲染为纯文本框
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

  /* 格式化工具：定义为 IIFE 内局部函数（函数声明会提升），
     供 timeline() 等内部代码直接调用，同时通过 window.UI 导出供页面使用 */
  function fmtDate(v) { return v == null || v === '' ? '-' : String(v).slice(0, 10); }
  function fmtDateTime(v) { return v == null || v === '' ? '-' : String(v).replace('T', ' ').slice(0, 16); }
  function fmtMoney(v) { return v == null || v === '' ? '-' : Number(v).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }); }

  window.UI = {
    h, toast, modal, confirmBox, table, pager, statusTag, kv, formRow, selectField,
    trendChart, multiTrendChart, donutChart, hbarChart, input, statusFilter, timeline, STATUS,
    fmtDate, fmtDateTime, fmtMoney,
  };
})();
