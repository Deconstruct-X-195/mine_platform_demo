/* ============ DOM 与通用工具 ============ */
function $(sel, root) { return (root || document).querySelector(sel); }
function $$(sel, root) { return Array.from((root || document).querySelectorAll(sel)); }

function el(tag, attrs, children) {
  const node = document.createElement(tag);
  if (attrs) {
    for (const [k, v] of Object.entries(attrs)) {
      if (k === 'class') node.className = v;
      else if (k === 'style' && typeof v === 'object') Object.assign(node.style, v);
      else if (k.startsWith('on') && typeof v === 'function') node.addEventListener(k.slice(2).toLowerCase(), v);
      else if (k === 'html') node.innerHTML = v;
      else if (v !== null && v !== undefined && v !== false) node.setAttribute(k, v === true ? '' : v);
    }
  }
  let kids = children;
  if (kids === null || kids === undefined) kids = [];
  if (!Array.isArray(kids)) kids = [kids];
  kids.flat(Infinity).forEach(c => {
    if (c === null || c === undefined || c === false) return;
    node.appendChild(typeof c === 'object' && c.nodeType ? c : document.createTextNode(String(c)));
  });
  return node;
}

function fmtQty(v) {
  if (v === null || v === undefined || v === '') return '-';
  const n = Number(v);
  return isNaN(n) ? String(v) : n.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}
function fmtMoney(v) { return v === null || v === undefined || v === '' ? '-' : '¥' + fmtQty(v); }
function fmtDate(v) { return v ? String(v).slice(0, 10) : '-'; }
function fmtTime(v) { return v || '-'; }
function esc(s) {
  return String(s == null ? '' : s).replace(/[&<>"']/g, m =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[m]));
}

function debounce(fn, ms) {
  let t = null;
  return function (...args) { clearTimeout(t); t = setTimeout(() => fn.apply(this, args), ms); };
}

/* ---------- Toast ---------- */
const Toast = {
  show(msg, type = 'info', ms = 2400) {
    let wrap = $('.toast-wrap');
    if (!wrap) { wrap = el('div', { class: 'toast-wrap' }); document.body.appendChild(wrap); }
    const t = el('div', { class: `toast toast-${type}` }, msg);
    wrap.appendChild(t);
    setTimeout(() => { t.style.opacity = '0'; t.style.transition = 'opacity .2s'; setTimeout(() => t.remove(), 220); }, ms);
  },
  success(m) { this.show(m, 'success'); },
  error(m) { this.show(m, 'error', 3200); },
  info(m) { this.show(m, 'info'); }
};

/* ---------- 模态框 ---------- */
function openModal({ title, body, footer, wide, onClose }) {
  const mask = el('div', { class: 'modal-mask' });
  const close = () => { mask.remove(); onClose && onClose(); };
  const m = el('div', { class: `modal${wide ? ' wide' : ''}` }, [
    el('div', { class: 'modal-head' }, [
      el('h3', null, title),
      el('button', { class: 'modal-close', onclick: close }, '×')
    ]),
    el('div', { class: 'modal-body' }, body),
    footer ? el('div', { class: 'modal-foot' }, footer(close)) : null
  ]);
  mask.appendChild(m);
  mask.addEventListener('mousedown', e => { if (e.target === mask) close(); });
  document.body.appendChild(mask);
  return { close, root: m };
}

function confirmDialog(message, onOk, { danger, okText = '确定' } = {}) {
  const md = openModal({
    title: '操作确认',
    body: el('div', { style: { padding: '8px 0 14px', color: 'var(--text-2)', fontSize: '13.5px' } }, message),
    footer: close => [
      el('button', { class: 'btn', onclick: close }, '取消'),
      el('button', {
        class: `btn ${danger ? 'btn-danger' : 'btn-primary'}`,
        onclick: () => { close(); onOk && onOk(); }
      }, okText)
    ]
  });
  return md;
}

/* ---------- 状态标签映射 ---------- */
const TAG_MAP = {
  DRAFT: ['草稿', 'gray'], SUBMITTED: ['已提交', 'blue'], IN_PROCESS: ['归集处理中', 'cyan'],
  IN_LIST: ['已纳入集采清单', 'purple'], IN_EXEC: ['集采执行中', 'orange'], DISTRIBUTED: ['已分拨完成', 'green'],
  PENDING: ['待处理', 'orange'], APPROVED: ['已通过', 'green'], REJECTED: ['已驳回', 'red'],
  AGREED: ['已同意', 'green'], ACTIVE: ['生效中', 'green'], INQUIRED: ['已询价', 'blue'],
  WAIT_QUOTE: ['待报价', 'orange'], QUOTED: ['已报价', 'blue'], QUOTING: ['比价中', 'cyan'],
  NOT_SELECTED: ['未选中', 'gray'], LOCKED: ['已锁货', 'green'], REFUSED: ['已拒绝', 'red'],
  WAIT: ['待分拨', 'gray'], TRANSIT: ['配送在途', 'blue'], WAIT_CONFIRM: ['待确认到货', 'orange'],
  DONE: ['已完成', 'green'],
  CONFIRMED: ['已确认', 'green'], DISPUTE: ['有异议', 'red'], SETTLED: ['已结清', 'purple'],
  ON_SHELF: ['已上架', 'green'], OFF_SHELF: ['已下架', 'gray'], FORCE_OFF: ['强制下架', 'red'],  WAIT_LOGI: ['待物流履约', 'orange'], IN_LOGISTICS: ['物流履约中', 'blue'],
  LOGI_DONE: ['履约完成', 'green'], ARCHIVED: ['已归档', 'purple'],
  PENDING_STAMP: ['待盖章', 'orange'], EFFECTIVE: ['已生效', 'green'], EXECUTING: ['履约中', 'blue'],
  FINISHED: ['已完成', 'green'], TERMINATED: ['已终止', 'red'], REDBACKED: ['已红冲作废', 'red'],
  REVOKED: ['已撤销', 'gray'],
  DOWNSTREAM: ['下游需求企业', 'blue'], SUPPLIER: ['上游供给方', 'cyan'], PARTNER: ['履约配套方', 'purple'],
  PLATFORM: ['平台运营方', 'red'], R1: ['下游企业', 'blue'], R2: ['上游供方', 'cyan'],
  R3: ['履约配套', 'purple'], R4: ['平台管理员', 'red'],
  MONTH: ['月度', 'blue'], QUARTER: ['季度', 'cyan'], QTY: ['数量变更', 'blue'],
  SPEC: ['规格变更', 'cyan'], CANCEL: ['取消', 'red'],
  RESOLVED: ['已处理', 'green'], DISABLED: ['已停用', 'gray'],
  CANCELLED: ['已取消', 'red'], DELETED: ['已删除', 'gray']
};
function tag(v) {
  const [name, color] = TAG_MAP[v] || [v, 'gray'];
  return el('span', { class: `tag tag-${color}` }, name);
}

/* ---------- 品类/周期等格式化 ---------- */
function dictName(list, code) {
  const hit = (list || []).find(d => d.item_code === code);
  return hit ? hit.item_name : code || '-';
}
