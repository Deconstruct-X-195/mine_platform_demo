/* 应用外壳：角色菜单、hash 路由、消息徽标、登录态 */
(function () {
  const MENU_META = {
    demand: ['需求管理', '#/demand'],
    pool: ['需求池', '#/pool'],
    price: ['基准价行情', '#/price'],
    forecast: ['远期预报', '#/forecast'],
    inquiry: ['询价报价', '#/inquiry'],
    bargain: ['议价定标', '#/bargain'],
    order: ['订单', '#/order'],
    contract: ['合同', '#/contract'],
    logistics: ['物流方案', '#/logistics'],
    waybill: ['运单作业', '#/waybill'],
    track: ['履约跟踪', '#/track'],
    settlement: ['结算管理', '#/settlement'],
    profile: ['企业信息', '#/profile'],
    dashboard: ['运营看板', '#/dashboard'],
    admin_companies: ['企业准入', '#/admin-companies'],
    base_data: ['基础数据', '#/base-data'],
    doc_overview: ['单据总览', '#/doc-overview'],
    alerts: ['预警处理', '#/alerts'],
    dict: ['状态字典', '#/dict'],
    logs: ['操作日志', '#/logs'],
  };
  const HOME = {
    STEEL_BUYER: '#/demand',
    SUPPLIER: '#/pool',
    LOGISTICS_CARRIER: '#/waybill',
    PLAT_ADMIN: '#/dashboard',
  };
  const TITLE = '大宗矿产集采平台';

  function pageOf() {
    const m = (location.hash || '').match(/^#\/([a-z][a-z0-9-]*)$/);
    // hash 用连字符（#/admin-companies），页面/菜单键用下划线（admin_companies）
    return m ? m[1].replace(/-/g, '_') : '';
  }

  function homeFor(user) {
    const roles = (user && user.roles) || [];
    for (const r of ['PLAT_ADMIN', 'STEEL_BUYER', 'SUPPLIER', 'LOGISTICS_CARRIER']) {
      if (roles.indexOf(r) >= 0) return HOME[r];
    }
    return '#/login';
  }

  function buildShell(user) {
    const root = document.getElementById('app');
    root.innerHTML = '';
    const nav = UI.h('nav', {},
      ...((user.menus && user.menus.length ? user.menus : [])).map((code) => {
        const meta = MENU_META[code];
        if (!meta) return null;
        return UI.h('a', { 'data-menu': code, href: meta[1] }, meta[0]);
      }).filter(Boolean));
    const company = user.company;
    const badge = UI.h('a', { class: 'msg-badge', href: '#/messages', id: 'msg-badge', style: 'display:none' }, '0');
    const shell = UI.h('div', { class: 'layout' },
      UI.h('aside', { class: 'sidebar' },
        UI.h('div', { class: 'logo' }, TITLE),
        nav),
      UI.h('div', { class: 'main' },
        UI.h('div', { class: 'topbar' },
          UI.h('div', { class: 'page-title', id: 'page-title' }, ''),
          UI.h('a', { href: '#/messages' }, '消息', badge),
          UI.h('div', { class: 'user-box' },
            UI.h('b', {}, user.realName || user.username),
            UI.h('span', {}, company ? company.companyName : '平台运营'),
            UI.h('button', { class: 'sm', onclick: logout }, '退 出'))),
        UI.h('div', { class: 'content', id: 'page' })));
    root.appendChild(shell);
    return root;
  }

  function highlight(pageKey) {
    document.querySelectorAll('.sidebar nav a[data-menu]').forEach((a) => {
      const on = a.getAttribute('data-menu') === pageKey;
      a.className = on ? 'active' : '';
    });
    const meta = MENU_META[pageKey];
    const title = document.getElementById('page-title');
    if (title) title.textContent = meta ? meta[0] : '大宗矿产集采平台';
  }

  function renderLoginRegister(pageKey) {
    const root = document.getElementById('app');
    root.innerHTML = '';
    const box = UI.h('div', { class: 'auth-wrap' });
    root.appendChild(box);
    if (window.Pages && window.Pages[pageKey]) window.Pages[pageKey](box, API.currentUser());
    else window.Pages.login(box, null);
  }

  async function route() {
    const user = API.currentUser();
    const pageKey = pageOf();
    if (!user || !user.tokenAlias) { /* 占位，下方判断 token */ }
    if (!user) {
      renderLoginRegister(pageKey === 'register' ? 'register' : 'login');
      return;
    }
    if (pageKey === 'login' || pageKey === 'register' || pageKey === '') {
      location.hash = homeFor(user);
      return;
    }
    if (!document.querySelector('.layout')) buildShell(user);
    const pageEl = document.getElementById('page');
    if (!pageEl) { buildShell(user); }
    highlight(pageKey);
    const target = document.getElementById('page');
    target.innerHTML = '<div class="empty" data-loading="1">加载中…</div>';
    try {
      if (pageKey === 'messages') {
        window.Pages.messages(target, user);
      } else if (window.Pages && window.Pages[pageKey]) {
        await window.Pages[pageKey](target, user);
      } else {
        target.innerHTML = '';
        target.appendChild(UI.h('div', { class: 'empty' }, '页面不存在'));
      }
      const ph = target.querySelector('[data-loading]');
      if (ph) ph.remove();
    } catch (e) {
      target.innerHTML = '';
      target.appendChild(UI.h('div', { class: 'empty' }, '页面加载失败：' + (e.message || e)));
    }
  }

  async function refreshMsgBadge() {
    const badge = document.getElementById('msg-badge');
    if (!badge || !API.currentUser()) return;
    try {
      const d = await API.get('/messages?page=1&size=1', { silent: true });
      const n = d && d.unread ? Number(d.unread) : 0;
      badge.textContent = String(n);
      badge.style.display = n > 0 ? '' : 'none';
    } catch (e) { /* 静默 */ }
  }

  function logout() {
    API.clearAuth();
    location.hash = '#/login';
    route();
  }

  window.App = { route, logout, homeFor, refreshMsgBadge, MENU_META };
  window.addEventListener('hashchange', route);
  window.addEventListener('DOMContentLoaded', () => {
    route();
    refreshMsgBadge();
  });
})();
