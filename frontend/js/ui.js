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
    /* noAutoClose: 不自动追加「关 闭」按钮（弹窗已自带取消/保存时使用） */
    const foot = h('div', { class: 'modal-foot' }, ...(footNodes || []),
      (opts && opts.noAutoClose) ? null : h('button', { onclick: close }, '关 闭'));
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

  /* 导出预览：所有数据导出按钮统一先弹窗预览（前 10 条 + 总条数），确认后才下载 CSV
     opts: { title, filename, head:['列1',...], rows:[[v,...],...] }（rows 为行数组，与 head 列一一对应） */
  function exportPreview(opts) {
    const PREVIEW_N = 10;
    const head = opts.head || [];
    const rows = opts.rows || [];
    if (!rows.length) { toast('暂无可导出的数据', 'err'); return; }
    const cols = head.map((label, i) => ({
      label, render: (r) => (r[i] == null || r[i] === '' ? '-' : String(r[i])),
    }));
    const note = h('div', { style: 'font-size:12px;color:#6e6e73;margin-bottom:10px' },
      rows.length > PREVIEW_N
        ? '预览前 ' + PREVIEW_N + ' 条，共 ' + rows.length + ' 条，确认无误后导出全部数据'
        : '共 ' + rows.length + ' 条，确认无误后导出');
    const csvDate = new Date().toISOString().slice(0, 10).replace(/-/g, '');
    const doExport = () => {
      const esc = (s) => '"' + String(s == null ? '' : s).replace(/"/g, '""') + '"';
      const lines = [head.map(esc)].concat(rows.map((r) => r.map(esc).join(',')));
      const blob = new Blob(['\uFEFF' + lines.join('\r\n')], { type: 'text/csv;charset=utf-8' });
      const a = h('a', { href: URL.createObjectURL(blob), download: opts.filename || ('导出_' + csvDate + '.csv') });
      document.body.appendChild(a);
      a.click();
      a.remove();
      toast('已导出 ' + rows.length + ' 条', 'ok');
    };
    let m;
    m = modal(opts.title || '导出预览', h('div', {}, note, table(cols, rows.slice(0, PREVIEW_N), '暂无可导出的数据')), [
      h('button', { class: 'primary', onclick: () => { m.close(); doExport(); } }, '导 出'),
      h('button', { onclick: () => m.close() }, '取 消'),
    ], { wide: true, noAutoClose: true });
  }

  /* columns: [{key,label,num,render(row),cls(自定义列样式,如勾选列 sel-col)}] */
  function table(columns, rows, emptyText) {
    if (!rows || !rows.length) return h('div', { class: 'empty' }, emptyText || '暂无数据');
    // 布局修复：外层 table-wrap 提供横向滚动，列多时表格在卡片内滚动而非溢出
    return h('div', { class: 'table-wrap' },
      h('table', { class: 'grid' },
        h('thead', {}, h('tr', {}, ...columns.map(c => h('th', { class: c.cls || (c.num ? 'num' : '') }, c.label)))),
        h('tbody', {}, ...rows.map(r => h('tr', {},
          ...columns.map(c => h('td', { class: c.cls || (c.num ? 'num' : '') },
            c.render ? c.render(r) : (r[c.key] == null ? '-' : String(r[c.key])))))))));
  }

  /* 分页条：共 N 条 / 每页 N 条（固定） / 页码（1 2 3 … 带省略）/ 前往 X 页 */
  function pager(container, page, size, total, onChange) {
    // 重复调用（状态筛选/查询/刷新）时先移除旧分页条，避免出现多条分页
    Array.from(container.children).forEach((n) => {
      if (n.classList && n.classList.contains('pager')) container.removeChild(n);
    });
    const pages = Math.max(1, Math.ceil(total / size));
    const cur = Math.min(Math.max(1, page), pages);
    const wrap = h('div', { class: 'pager' });
    wrap.appendChild(h('span', { class: 'pager-total' }, '共 ' + total + ' 条'));
    wrap.appendChild(h('span', { class: 'pager-size' }, '每页 ' + size + ' 条'));
    // 页码：总页数 ≤7 全列，否则首页 + 当前±1 + 末页，中间省略
    const nums = [];
    if (pages <= 7) {
      for (let p = 1; p <= pages; p++) nums.push(p);
    } else {
      nums.push(1);
      const s = Math.max(2, cur - 1), e = Math.min(pages - 1, cur + 1);
      if (s > 2) nums.push(null);
      for (let p = s; p <= e; p++) nums.push(p);
      if (e < pages - 1) nums.push(null);
      nums.push(pages);
    }
    wrap.appendChild(h('span', { class: 'pager-nums' }, ...nums.map((p) => (p === null
      ? h('span', { class: 'pager-ellipsis' }, '···')
      : h('button', {
        class: 'pager-num' + (p === cur ? ' active' : ''),
        onclick: () => { if (p !== cur) onChange(p); },
      }, String(p))))));
    const jump = h('input', { class: 'pager-jump', type: 'number', min: '1', max: String(pages), value: '' });
    const go = () => {
      const n = parseInt(jump.value, 10);
      if (!n || n < 1 || n > pages) { toast('请输入 1~' + pages + ' 之间的页码'); return; }
      jump.value = '';
      if (n !== cur) onChange(n);
    };
    jump.addEventListener('keydown', (e) => { if (e.key === 'Enter') go(); });
    wrap.appendChild(h('span', { class: 'pager-jump-box' }, '前往', jump, '页',
      h('button', { class: 'pager-go', onclick: go }, '确定')));
    container.appendChild(wrap);
  }

  const STATUS = {
    /* DEMAND 展示口径：DRAFT/WITHDRAWN/PENDING_DELETE 统一显示「待提交」；筛选用 UNPUSHED 联合查询三者 */
    DEMAND: { DRAFT: ['待提交', 'orange', 'UNPUSHED'], SUBMITTED: ['已提交', 'blue'], AGGREGATED: ['已归集', 'blue'], TO_INQUIRY: ['待询价', 'orange'], WITHDRAWN: ['待提交', 'orange'], PENDING_DELETE: ['待提交', 'orange'], DELETE_AUDIT: ['删除待审核', 'orange'], INQUIRING: ['询价中', 'blue'], DEALT: ['已成交', 'green'], CLOSED: ['已关闭', 'gray'] },
    INQUIRY: { DRAFT: ['草稿', 'gray'], SENT: ['已发出', 'blue'], AGGREGATED: ['已归集', 'orange'], QUOTING: ['报价中', 'blue'], CLOSED: ['已截止', 'gray'], FEEDBACK: ['反馈待处理', 'orange'], BARGAINING: ['议价中', 'blue'], AWARDED: ['已定标', 'green'], FAILED: ['已流标', 'red'] },
    QUOTE: { SUBMITTED: ['已报价', 'blue'], REVEALED: ['已揭示', 'gray'], BARGAINING: ['议价中', 'blue'], WIN: ['中标', 'green'], LOSE: ['未中标', 'red'], REJECTED: ['已拒绝', 'red'] },
    BARGAIN: { PENDING: ['待响应', 'orange'], ONGOING: ['待响应', 'orange'], ACCEPTED: ['已接受', 'green'], REJECTED: ['已拒绝', 'red'], EXPIRED: ['已失效', 'gray'] },
    ORDER: { PENDING_PICKUP: ['待收集提货计划', 'orange'], PENDING_TRANSPORT: ['待制定运输方案', 'blue'], PENDING_CONFIRM: ['待确认', 'orange'], PENDING_CONTRACT: ['待签合同', 'orange'], PENDING_EFFECT: ['待合同生效', 'orange'], PERFORMING: ['履约中', 'blue'], COMPLETED: ['已完成', 'green'], CANCELLED: ['已失效', 'red'] },
    CONTRACT: { PENDING_GENERATE: ['待生成', 'gray'], PENDING_BUYER: ['待需方签署', 'orange'], PENDING_SUPPLIER: ['待供方签署', 'orange'], EFFECTIVE: ['已生效', 'green'], VOID: ['已作废', 'red'] },
    WAYBILL: { PENDING_DEPART: ['待发运', 'orange'], IN_TRANSIT: ['在途', 'blue'], ARRIVED: ['已到达', 'blue'], SIGNED: ['已签收', 'green'], CANCELLED: ['已取消', 'gray'] },
    SETTLEMENT: { PENDING_CONFIRM_SUPPLIER: ['待供应商确认', 'orange'], PENDING_CONFIRM_BUYER: ['待需方确认', 'orange'], CONFIRMED: ['已确认', 'blue'], COMPLETED: ['已完成', 'green'] },
    FORECAST: { EFFECTIVE: ['生效中', 'green'], EXPIRED: ['已失效', 'gray'] },
    ALERT: { PENDING: ['待处理', 'orange'], PROCESSING: ['处理中', 'blue'], CLOSED: ['已关闭', 'gray'] },
    AUDIT: { PENDING: ['待审核', 'orange'], APPROVED: ['已准入', 'green'], REJECTED: ['已驳回', 'red'] },
    CHANGE: { PENDING: ['待审核', 'orange'], APPROVED: ['已通过', 'green'], REJECTED: ['已驳回', 'red'] },
    AGG: { OPEN: ['已归集', 'blue'], INQUIRING: ['询价中', 'orange'], AWARDED: ['已定标', 'green'], CLOSED: ['已关闭', 'gray'] },
    PLAT: { PENDING: ['待归集', 'orange'], CONFIRMED: ['已归集', 'green'], RETURNED: ['已退回', 'red'] },
    ENT: { ENABLED: ['正常', 'green'], DISABLED: ['已禁用', 'red'] },
    USER: { ENABLED: ['正常', 'green'], DISABLED: ['已禁用', 'red'] },
  };
  function statusTag(kind, code) {
    const m = (STATUS[kind] || {})[code];
    if (!m) return h('span', { class: 'tag' }, code || '-');
    return h('span', { class: 'tag ' + m[1] }, m[0]);
  }

  function kv(pairs) {
    /* pairs: [[label, value, full?]]；full=整行展示，标签强制回到第1列另起一行，避免半行字段占位导致标签与值错位 */
    return h('div', { class: 'kv' }, ...pairs.map(([k, v, full]) => [
      h('span', { class: full ? 'k full-k' : 'k' }, k + '：'),
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

  /* 自定义下拉：内嵌浏览器中原生 select 弹层不渲染（点不出选项），改为页面内渲染的下拉面板。
     options: [[value, text], ...]；props: { onchange(value) } */
  function dropdown(options, value, props) {
    const wrap = h('div', { class: 'dd' });
    const cur = options.find((o) => String(o[0]) === String(value == null ? '' : value));
    const btn = h('button', { class: 'dd-btn', type: 'button' },
      h('span', { class: 'dd-text' }, cur ? cur[1] : (options[0] ? options[0][1] : '-')),
      h('i', { class: 'dd-arrow' }));
    const panel = h('div', { class: 'dd-panel' });
    const onChange = props && props.onchange ? props.onchange : null;
    function renderPanel() {
      panel.innerHTML = '';
      options.forEach(([v, t]) => {
        const opt = h('div', { class: 'dd-opt' + (String(v) === String(value == null ? '' : value) ? ' active' : '') }, t);
        opt.addEventListener('click', (e) => {
          e.stopPropagation();
          close();
          value = v;
          btn.querySelector('.dd-text').textContent = t;
          panel.querySelectorAll('.dd-opt').forEach((el) => el.classList.remove('active'));
          opt.classList.add('active');
          if (onChange) onChange(v);
        });
        panel.appendChild(opt);
      });
    }
    function open() { renderPanel(); wrap.classList.add('open'); document.addEventListener('click', close, true); }
    function close() { wrap.classList.remove('open'); document.removeEventListener('click', close, true); }
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      if (wrap.classList.contains('open')) close(); else open();
    });
    wrap.appendChild(btn);
    wrap.appendChild(panel);
    return wrap;
  }

  /* 近30日基准价 SVG 折线（网格坐标轴 + 面积渐变 + 悬浮十字提示） */
  let trendUid = 0;
  /* 'YYYY-MM-DD' + n 天 */
  function _dayAdd(s, n) {
    const m = String(s).match(/(\d{4})-(\d{2})-(\d{2})/);
    if (!m) return String(s);
    const d = new Date(+m[1], +m[2] - 1, +m[3]);
    d.setDate(d.getDate() + n);
    const p = (x) => String(x).padStart(2, '0');
    return d.getFullYear() + '-' + p(d.getMonth() + 1) + '-' + p(d.getDate());
  }
  /* 纵轴显示域：fixedStep 给定时步长全站统一（格数随数据自适应，最小 3 格、中心对齐）；
     否则按数据跨度/3 取 1/2/5×10ⁿ 档固定 3 格。均保证覆盖全部数据、刻度取整等间距 */
  function _niceDomain(rawMin, rawMax, fixedStep) {
    let span = rawMax - rawMin;
    const minSpan = Math.abs(rawMax) * 0.02 || 1;
    if (span < minSpan) span = minSpan;
    if (fixedStep) {
      const n = Math.max(3, Math.ceil(span / fixedStep));
      const center = (rawMin + rawMax) / 2;
      const lo = Math.floor((center - n * fixedStep / 2) / fixedStep) * fixedStep;
      return { lo, hi: lo + n * fixedStep, step: fixedStep };
    }
    const rough = span / 3;
    const mag = Math.pow(10, Math.floor(Math.log10(rough)));
    const center = (rawMin + rawMax) / 2;
    for (const m of [1, 2, 5, 10, 20, 50, 100]) {
      const step = m * mag;
      const lo = Math.floor((center - 1.5 * step) / step) * step;
      const hi = lo + 3 * step;
      if (lo <= rawMin && hi >= rawMax) return { lo, hi, step };
    }
    const step = 100 * mag;  // 兜底：数据跨度远超常规档位（理论不会出现）
    const lo = Math.floor(rawMin / step) * step;
    return { lo, hi: lo + 3 * step, step };
  }
  function trendChart(rows, priceKey, unitLabel) {
    const unit = unitLabel || '元/湿吨';
    const all = (rows || []).filter(r => r[priceKey] != null && r.priceDate);
    if (all.length < 2) return h('div', { class: 'empty' }, '数据不足，暂无走势');
    const H = 260, ML = 48, MR = 14, MT = 18, MB = 28, WIN = 28;
    /* 横轴固定为一个月（4 周）日期域：终点=当天、起点=28 天前，刻度严格每 7 天一档，自动随日期推进 */
    const p2 = (x) => String(x).padStart(2, '0');
    const now = new Date();
    const todayStr = now.getFullYear() + '-' + p2(now.getMonth() + 1) + '-' + p2(now.getDate());
    const minDate = _dayAdd(todayStr, -WIN);
    const pts = all.filter((r) => {
      const d = String(r.priceDate).slice(0, 10);
      return d >= minDate && d <= todayStr;
    }).slice().sort((a, b) => String(a.priceDate).localeCompare(String(b.priceDate)));
    if (pts.length < 2) return h('div', { class: 'empty' }, '数据不足，暂无走势');
    const vals = pts.map(r => parseFloat(r[priceKey]));
    const dayIdx = {};
    for (let i = 0; i <= WIN; i++) dayIdx[_dayAdd(minDate, i)] = i;
    /* 同日多点并排错开：各点位置 = 日期索引 + 日内居中小偏移（两点±0.3档），
       日期与横轴刻度严格对齐——不再整档右移导致"19号数据落在20号刻度上"，同日点连线平缓无竖直跳变 */
    const cnt = {}, seen = {};
    pts.forEach((r) => { const d = String(r.priceDate).slice(0, 10); cnt[d] = (cnt[d] || 0) + 1; });
    const EFF = pts.map((r) => {
      const d = String(r.priceDate).slice(0, 10);
      const k = seen[d] || 0; seen[d] = k + 1;
      return dayIdx[d] + (cnt[d] > 1 ? (k - (cnt[d] - 1) / 2) * 0.6 : 0);
    });
    const WIN_EFF = Math.max(WIN, ...EFF.map((f) => Math.ceil(f)));
    /* 纵轴：价格图步长全站统一（元 → 10），格数随数据自适应；其他单位自适应取档 */
    const dom = _niceDomain(Math.min(...vals), Math.max(...vals), unit.charAt(0) === '元' ? 10 : null);
    /* 运量类数值（非价格单位）不可能为负：纵轴下限钳到 0，避免小运量时 nice 域出现负刻度 */
    let lo = dom.lo, hi = dom.hi; const step = dom.step;
    if (unit.charAt(0) !== '元') { if (lo < 0) lo = 0; if (hi <= lo) hi = lo + step; }
    const Y = (v) => MT + (hi - v) / (hi - lo) * (H - MT - MB);
    const fmtTick = (v) => Number.isInteger(v) ? String(v) : (Math.abs(v) >= 1000 ? v.toFixed(0) : v.toFixed(1));
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
    const wrap = h('div', { class: 'trend-wrap' });
    wrap.appendChild(svg);
    /* 宽度随面板动态重绘：viewBox 宽=实际像素宽，SVG 文字始终按系统字号渲染 */
    const draw = () => {
      const W = Math.max(320, wrap.clientWidth || 600);
      const iw = W - ML - MR;
      const X = (i) => ML + i * iw / WIN_EFF;
      svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
      svg.innerHTML = '';

    // 面积渐变（id 需按实例唯一，避免多图互相覆盖）
    const gid = 'trend-grad-' + (++trendUid);
    const defs = el('defs', {});
    const grad = el('linearGradient', { id: gid, x1: '0', y1: '0', x2: '0', y2: '1' });
    grad.appendChild(el('stop', { offset: '0%', 'stop-color': '#1a5cb0', 'stop-opacity': '0.20' }));
    grad.appendChild(el('stop', { offset: '100%', 'stop-color': '#1a5cb0', 'stop-opacity': '0.02' }));
    defs.appendChild(grad);
    svg.appendChild(defs);

    // y 轴网格线 + 刻度（等间距整值刻度）
    const nTick = Math.round((hi - lo) / step);
    for (let k = 0; k <= nTick; k++) {
      const v = lo + k * step;
      const gy = Y(v).toFixed(1);
      svg.appendChild(el('line', { x1: ML, y1: gy, x2: W - MR, y2: gy, stroke: '#ececf0', 'stroke-width': '1' }));
      svg.appendChild(el('text', { x: ML - 8, y: +gy + 4, 'text-anchor': 'end', 'font-size': '11', fill: '#86868b' }, fmtTick(v)));
    }
    // x 轴日期刻度：整月域固定 5 档（窗口首日 / 每 7 天 / 今日）；今日双条扩展域时今日刻度不再贴右缘
    [0, 7, 14, 21, WIN].forEach((off) => {
      const atEdge = WIN_EFF === WIN && off === WIN;
      svg.appendChild(el('text', {
        x: X(off).toFixed(1), y: H - 8, 'font-size': '11', fill: '#86868b',
        'text-anchor': off === 0 ? 'start' : (atEdge ? 'end' : 'middle'),
      }, fmtDay(_dayAdd(minDate, off))));
    });

    // 面积 + 折线（按截图风格：无逐点圆点，仅悬浮显示数据点）
    const line = pts.map((r, i) => X(EFF[i]).toFixed(1) + ',' + Y(parseFloat(r.price)).toFixed(1)).join(' ');
    const base = (H - MB).toFixed(1);
    svg.appendChild(el('polygon', { points: `${X(EFF[0]).toFixed(1)},${base} ${line} ${X(EFF[EFF.length - 1]).toFixed(1)},${base}`, fill: `url(#${gid})` }));
    svg.appendChild(el('polyline', {
      points: line, fill: 'none', stroke: '#1a5cb0', 'stroke-width': '2.5',
      'stroke-linejoin': 'round', 'stroke-linecap': 'round',
    }));

    // 悬浮十字线 + 提示卡（日期行 + 圆点数值行，样式对齐参考图）
    const hover = el('g', { style: 'display:none' });
    const vline = el('line', { y1: MT, y2: H - MB, stroke: '#c7c7cc', 'stroke-dasharray': '4 3', 'stroke-width': '1' });
    const hdot = el('circle', { r: '4.5', fill: '#1a5cb0', stroke: '#fff', 'stroke-width': '2' });
    const tipG = el('g', {});
    const tipRect = el('rect', { width: '168', height: '56', rx: '8', fill: 'rgba(250,250,252,.97)', stroke: '#e5e5ea' });
    const tipDate = el('text', { x: '12', y: '19', 'font-size': '11', fill: '#86868b' });
    const tipDot = el('circle', { cx: '16', cy: '36', r: '3.5', fill: '#1a5cb0' });
    const tipVal = el('text', { x: '25', y: '40', 'font-size': '12', 'font-weight': '600', fill: '#1d1d1f' });
    tipG.appendChild(tipRect); tipG.appendChild(tipDate); tipG.appendChild(tipDot); tipG.appendChild(tipVal);
    hover.appendChild(vline); hover.appendChild(hdot); hover.appendChild(tipG);
    svg.appendChild(hover);

    const overlay = el('rect', { x: ML, y: MT, width: iw, height: H - MT - MB, fill: 'transparent' });
    overlay.addEventListener('mousemove', (e) => {
      const rect = svg.getBoundingClientRect();
      if (!rect.width) return;
      const px = (e.clientX - rect.left) * (W / rect.width);
      /* 命中最近的数据点（按并排偏移后的实际位置距离），再取该点 */
      const ex = (px - ML) / iw * WIN_EFF;
      let bi = 0, bd = Infinity;
      EFF.forEach((fi, k) => {
        const d = Math.abs(fi - ex);
        if (d < bd) { bd = d; bi = k; }
      });
      const cx = X(EFF[bi]), cy = Y(vals[bi]);
      hover.style.display = '';
      vline.setAttribute('x1', cx); vline.setAttribute('x2', cx);
      hdot.setAttribute('cx', cx); hdot.setAttribute('cy', cy);
      let tx = cx + 12;
      if (tx + 168 > W - MR) tx = cx - 180;
      tipG.setAttribute('transform', `translate(${tx.toFixed(1)},${Math.max(MT, cy - 66).toFixed(1)})`);
      tipDate.textContent = fmtDay(pts[bi].priceDate);
      tipVal.textContent = vals[bi].toFixed(2) + ' ' + unit;
    });
    overlay.addEventListener('mouseleave', () => { hover.style.display = 'none'; });
    svg.appendChild(overlay);
    };
    requestAnimationFrame(draw);
    if (window.ResizeObserver) new ResizeObserver(draw).observe(wrap);
    return wrap;
  }

  /* 多序列折线图（同图多线不同色：行业价格 vs 交易价格），横轴整月每 7 天一档，悬浮按日期展示全部系列 */
  function multiTrendChart(series, unitLabel) {
    const unit = unitLabel || '元/湿吨';
    const wrap = h('div', {});
    const usable = (series || []).filter(s => s.rows && s.rows.length >= 2);
    wrap.appendChild(h('div', { class: 'trend-legend' },
      ...(series || []).map((s) => {
        const has = s.rows && s.rows.length >= 2;
        return h('span', { class: 'trend-legend-item' },
          h('span', { class: 'legend-dot', style: 'background:' + (has ? s.color : '#c7c7cc') }),
          s.name + (has ? '' : '（暂无数据）'));
      }),
      h('span', { style: 'margin-left:auto;color:#86868b' }, '单位：' + unit)));
    if (!usable.length) { wrap.appendChild(h('div', { class: 'empty' }, '数据不足，暂无走势')); return wrap; }

    const H = 260, ML = 48, MR = 14, MT = 18, MB = 28, WIN = 28;
    /* 横轴固定为一个月（4 周）日期域：终点=当天、起点=28 天前，刻度严格每 7 天一档，自动随日期推进 */
    const p2 = (x) => String(x).padStart(2, '0');
    const now = new Date();
    const todayStr = now.getFullYear() + '-' + p2(now.getMonth() + 1) + '-' + p2(now.getDate());
    const minDate = _dayAdd(todayStr, -WIN);
    const dayIdx = {};
    for (let i = 0; i <= WIN; i++) dayIdx[_dayAdd(minDate, i)] = i;
    /* 每系列过滤近一个月并按日期排序 */
    const seriesPts = usable.map((s) => s.rows
      .filter((r) => { const d = String(r.priceDate).slice(0, 10); return d >= minDate && d <= todayStr && r.price != null; })
      .slice().sort((a, b) => String(a.priceDate).localeCompare(String(b.priceDate))));
    /* 同日多点并排错开：各点位置 = 日期索引 + 日内居中小偏移（两点±0.3档、三点±0.6档），
       日期与横轴刻度严格对齐——不再整档右移导致"19号数据落在20号刻度上"，同日点连线短且平缓无竖直跳变 */
    const SPREAD = 0.6;
    const seriesEFF = seriesPts.map((ps) => {
      const cnt = {}, seen = {};
      ps.forEach((r) => { const d = String(r.priceDate).slice(0, 10); cnt[d] = (cnt[d] || 0) + 1; });
      return ps.map((r) => {
        const d = String(r.priceDate).slice(0, 10);
        const k = seen[d] || 0; seen[d] = k + 1;
        return dayIdx[d] + (cnt[d] > 1 ? (k - (cnt[d] - 1) / 2) * SPREAD : 0);
      });
    });
    let WIN_EFF = WIN;
    seriesEFF.forEach((effs) => effs.forEach((fi) => { const c = Math.ceil(fi); if (c > WIN_EFF) WIN_EFF = c; }));
    const allVals = [];
    seriesPts.forEach((ps) => ps.forEach((r) => allVals.push(parseFloat(r.price))));
    if (!allVals.length) { wrap.appendChild(h('div', { class: 'empty' }, '数据不足，暂无走势')); return wrap; }
    /* 纵轴：价格图步长全站统一（元 → 10），格数随数据自适应；其他单位自适应取档 */
    const dom = _niceDomain(Math.min(...allVals), Math.max(...allVals), unit.charAt(0) === '元' ? 10 : null);
    const lo = dom.lo, hi = dom.hi, step = dom.step;
    const Y = (v) => MT + (hi - v) / (hi - lo) * (H - MT - MB);
    const fmtTick = (v) => Number.isInteger(v) ? String(v) : (Math.abs(v) >= 1000 ? v.toFixed(0) : v.toFixed(1));
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
    const chartWrap = h('div', { class: 'trend-wrap' });
    chartWrap.appendChild(svg);
    /* 宽度随面板动态重绘：viewBox 宽=实际像素宽，SVG 文字始终按系统字号渲染 */
    const draw = () => {
      const W = Math.max(320, chartWrap.clientWidth || 600);
      const iw = W - ML - MR;
      const X = (i) => ML + i * iw / WIN_EFF;
      svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
      svg.innerHTML = '';

      // y 轴网格线 + 刻度（等间距整值刻度）
      const nTick = Math.round((hi - lo) / step);
      for (let k = 0; k <= nTick; k++) {
        const v = lo + k * step;
        const gy = Y(v).toFixed(1);
        svg.appendChild(el('line', { x1: ML, y1: gy, x2: W - MR, y2: gy, stroke: '#ececf0', 'stroke-width': '1' }));
        svg.appendChild(el('text', { x: ML - 8, y: +gy + 4, 'text-anchor': 'end', 'font-size': '11', fill: '#86868b' }, fmtTick(v)));
      }
      // x 轴日期刻度：整月域固定 5 档（窗口首日 / 每 7 天 / 今日）；今日双条扩展域时今日刻度不再贴右缘
      [0, 7, 14, 21, WIN].forEach((off) => {
        const atEdge = WIN_EFF === WIN && off === WIN;
        svg.appendChild(el('text', {
          x: X(off).toFixed(1), y: H - 8, 'font-size': '11', fill: '#86868b',
          'text-anchor': off === 0 ? 'start' : (atEdge ? 'end' : 'middle'),
        }, fmtDay(_dayAdd(minDate, off))));
      });

      /* 按日期聚合各系列数值（悬浮提示卡一次展示同日期全部系列） */
      const byDate = {};
      const lineOf = usable.map((s, si) => seriesPts[si].map((r, k) =>
        X(seriesEFF[si][k]).toFixed(1) + ',' + Y(parseFloat(r.price)).toFixed(1)).join(' '));
      usable.forEach((s, si) => {
        if (seriesPts[si].length < 2) return;
        svg.appendChild(el('polyline', {
          points: lineOf[si], fill: 'none', stroke: s.color, 'stroke-width': '2.5',
          'stroke-linejoin': 'round', 'stroke-linecap': 'round',
          'stroke-dasharray': s.dashed ? '7 4' : 'none',
        }));
      });
      usable.forEach((s, si) => {
        seriesPts[si].forEach((r) => {
          const d = String(r.priceDate).slice(0, 10);
          (byDate[d] = byDate[d] || []).push({ name: s.name, color: s.color, val: parseFloat(r.price) });
        });
      });

      const hover = el('g', { style: 'display:none' });
      const vline = el('line', { y1: MT, y2: H - MB, stroke: '#c7c7cc', 'stroke-dasharray': '4 3', 'stroke-width': '1' });
      hover.appendChild(vline);
      /* 每个系列一枚悬浮数据点 */
      const hdots = usable.map((s) => {
        const d = el('circle', { r: '4.5', fill: s.color, stroke: '#fff', 'stroke-width': '2' });
        d.style.display = 'none';
        hover.appendChild(d);
        return d;
      });
      /* 提示卡：日期表头 + 每系列一行（圆点/名称/数值） */
      const tipG = el('g', {});
      const tipRect = el('rect', { width: '176', height: '56', rx: '8', fill: 'rgba(250,250,252,.97)', stroke: '#e5e5ea' });
      const tipDate = el('text', { x: '12', y: '19', 'font-size': '11', fill: '#86868b' });
      tipG.appendChild(tipRect); tipG.appendChild(tipDate);
      const tipRows = usable.map((s) => {
        const dot = el('circle', { cx: '16', r: '3.5', fill: s.color });
        const name = el('text', { x: '25', 'font-size': '11', fill: '#6e6e73' });
        const val = el('text', { x: '164', 'text-anchor': 'end', 'font-size': '12', 'font-weight': '600', fill: '#1d1d1f' });
        tipG.appendChild(dot); tipG.appendChild(name); tipG.appendChild(val);
        return { dot, name, val };
      });
      hover.appendChild(tipG);
      svg.appendChild(hover);

      const overlay = el('rect', { x: ML, y: MT, width: iw, height: H - MT - MB, fill: 'transparent' });
      overlay.addEventListener('mousemove', (e) => {
        const rect = svg.getBoundingClientRect();
        if (!rect.width) return;
        const px = (e.clientX - rect.left) * (W / rect.width);
        /* 命中最近的数据点（按并排偏移后的实际位置距离），提示卡展示该点日期的全部系列 */
        const ex = (px - ML) / iw * WIN_EFF;
        let hi = -1, pi = -1, hd = Infinity;
        seriesEFF.forEach((effs, si) => effs.forEach((fi, k) => {
          const d = Math.abs(fi - ex);
          if (d < hd) { hd = d; hi = si; pi = k; }
        }));
        if (hi < 0) return;
        const hitDate = String(seriesPts[hi][pi].priceDate).slice(0, 10);
        const hitEff = seriesEFF[hi][pi];
        const rows = byDate[hitDate] || [];
        if (!rows.length) return;
        hover.style.display = '';
        const cx = X(hitEff);
        vline.setAttribute('x1', cx); vline.setAttribute('x2', cx);
        hdots.forEach((hd2, si) => {
          /* 悬浮点跟随命中点：命中系列放命中点位置，其余系列放各自该日期最近一条 */
          const effs = seriesEFF[si];
          let k = -1, best = Infinity;
          effs.forEach((fi, idx) => { if (String(seriesPts[si][idx].priceDate).slice(0, 10) === hitDate && Math.abs(fi - hitEff) < best) { best = Math.abs(fi - hitEff); k = idx; } });
          if (k >= 0) {
            hd2.style.display = '';
            hd2.setAttribute('cx', X(effs[k]).toFixed(1));
            hd2.setAttribute('cy', Y(parseFloat(seriesPts[si][k].price)).toFixed(1));
          } else hd2.style.display = 'none';
        });
        const hgt = 30 + rows.length * 20 + 6;
        tipRect.setAttribute('height', String(hgt));
        tipDate.textContent = fmtDay(hitDate);
        tipRows.forEach((tr, i) => {
          const row = rows[i];
          const show = row ? '' : 'none';
          tr.dot.style.display = show; tr.name.style.display = show; tr.val.style.display = show;
          if (!row) return;
          const y = 36 + i * 20;
          tr.dot.setAttribute('cy', String(y - 4));
          tr.name.setAttribute('y', String(y));
          tr.name.textContent = row.name;
          tr.val.setAttribute('y', String(y));
          tr.val.textContent = row.val.toFixed(2) + ' ' + unit;
        });
        let tx = cx + 12;
        if (tx + 176 > W - MR) tx = cx - 188;
        const ty = Math.max(MT, Y(rows[0].val) - 66);
        tipG.setAttribute('transform', `translate(${tx.toFixed(1)},${ty.toFixed(1)})`);
      });
      overlay.addEventListener('mouseleave', () => { hover.style.display = 'none'; });
      svg.appendChild(overlay);
    };
    requestAnimationFrame(draw);
    if (window.ResizeObserver) new ResizeObserver(draw).observe(chartWrap);
    wrap.appendChild(chartWrap);
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
    svg.appendChild(el('text', { x: cx, y: cy + 13, 'text-anchor': 'middle', 'font-size': '10', fill: '#86868b' }, centerLabel || '总量(湿吨)'));
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
        h('span', { class: 'hbar-val' }, fmtInt(parseFloat(item[vk])) + (unitLabel || '湿吨'))));
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
    /* 按显示文案去重（同文案多状态如 DEMAND 待提交 → 合并为一个筛选选项，取 m[2] 联合查询码） */
    const seen = {};
    const opts = [['', '全部状态']].concat(
      Object.entries(STATUS[kind] || {})
        .filter(([code, m]) => (seen[m[0]] ? false : (seen[m[0]] = true)))
        .map(([code, m]) => [m[2] || code, m[0]]));
    return dropdown(opts, '', { onchange: (v) => onChange(v) });
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
  const fmtQty = fmtMoney; /* 吨数同样保留两位小数 */

  /* 报价模式单价展示辅助：单价 = 品种港口现货价 ± 上下浮（如 663.00 +23.00）。
     spotPrices() 拉取一次品种→现货价映射（黄骅港基准）；spotDiff() 按行反推上下浮分解，
     无基准价时回退显示绝对单价 */
  async function spotPrices() {
    try {
      const r = await API.get('/base-prices/ports' + API.qs({ port: '黄骅港' }));
      const map = {};
      (r.list || []).forEach((x) => { map[x.varietyName] = Number(x.price); });
      return map;
    } catch (e) { return {}; }
  }
  function spotDiff(base, price) {
    if (price == null || isNaN(Number(price))) return '-';
    if (base == null || isNaN(Number(base))) return fmtMoney(price);
    const diff = Number(price) - Number(base);
    /* 固定字样展示：不显示当日基准价数字，仅「港口现货价格 ± 上下浮」 */
    return diff === 0 ? '港口现货价格' : '港口现货价格 ' + (diff >= 0 ? '+' : '-') + fmtMoney(Math.abs(diff));
  }
  /* 优先展示报价落库时供应商申报的 ±方向与浮金额（spotShown）；
     无存储值（旧数据）时回退 spotDiff 按当前基准价反推 */
  function spotShown(sign, float) {
    const f = Number(float);
    if ((sign === '+' || sign === '-') && !isNaN(f)) {
      return f === 0 ? '港口现货价格' : '港口现货价格 ' + sign + fmtMoney(Math.abs(f));
    }
    return null;
  }

  /* 行首勾选框列：picked 为选中键 Set（默认键为行 id，无 id 时取整行 JSON）；
     仅作行选择展示，click 阻止冒泡（避免触发行点击，如运输调度选单） */
  function selCol(picked, keyFn) {
    const key = keyFn || ((r) => (r && r.id != null ? r.id : JSON.stringify(r)));
    return {
      label: '', cls: 'sel-col',
      render: (r) => {
        const el = h('input', { type: 'checkbox', title: '勾选该行' });
        el.checked = picked.has(key(r));
        el.addEventListener('click', (e) => e.stopPropagation());
        el.addEventListener('change', () => {
          const k = key(r);
          if (el.checked) picked.add(k); else picked.delete(k);
        });
        return el;
      },
    };
  }

  window.UI = {
    h, toast, modal, confirmBox, exportPreview, table, pager, statusTag, kv, formRow, selectField, dropdown,
    trendChart, multiTrendChart, donutChart, hbarChart, input, statusFilter, timeline, STATUS,
    fmtDate, fmtDateTime, fmtMoney, fmtQty, selCol, spotPrices, spotDiff, spotShown,
  };
})();
