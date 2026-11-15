/* 应用外壳：角色菜单、hash 路由、消息徽标、登录态 */
(function () {
  /* 消息分类标签（通知/预警/公告/活动信息） */
  const MSG_CAT_LABEL = { NOTICE: '通知', WARN: '预警', ANNOUNCE: '公告', ACTIVITY: '活动' };
  const MENU_META = {
    overview: ['总览', '#/overview'],
    demand: ['需求管理', '#/demand'],
    price: ['基准价行情', '#/price'],
    inquiry: ['询价报价', '#/inquiry'],
    bargain: ['议价定标', '#/bargain'],
    order: ['订单管理', '#/order'],
    logistics: ['物流服务', '#/logistics'],
    track: ['履约跟踪', '#/track'],
    profile: ['企业信息', '#/profile'],
    dashboard: ['运营看板', '#/dashboard'],
    port_price: ['价格趋势详情', '#/port-price'],
    price_records: ['价格行情详情', '#/price-records'],
    admin_companies: ['企业准入', '#/admin-companies'],
    demand_pool: ['需求归集', '#/demand-pool'],
    quote_center: ['报价询价', null],
    quote_inquiry: ['询价', '#/quote-inquiry'],
    quote_history: ['询价历史', '#/quote-history'],
    order_admin: ['订单管理', '#/order-admin'],
    logistics_dispatch: ['运输调度', '#/logistics-dispatch'],
    base_data: ['基础数据', '#/base-data'],
    alerts: ['预警处理', '#/alerts'],
    dict: ['状态字典', '#/dict'],
    logs: ['操作日志', '#/logs'],
  };
  // 二级菜单：父级键 → 子菜单键顺序（父级不可点击，仅作分组标题）
  const MENU_GROUPS = { quote_center: ['quote_inquiry', 'quote_history'] };
  const MENU_PARENT = { quote_inquiry: 'quote_center', quote_history: 'quote_center' };
  // 角色级菜单名覆盖：键为角色，值为 { 菜单键: 显示名 }
  const MENU_ROLE_LABEL = { STEEL_BUYER: { inquiry: '采购询价' } };
  function menuLabel(user, code) {
    const roles = (user && user.roles) || [];
    for (const r of roles) {
      const ov = MENU_ROLE_LABEL[r];
      if (ov && ov[code]) return ov[code];
    }
    return MENU_META[code][0];
  }
  const HOME = {
    STEEL_BUYER: '#/overview',
    SUPPLIER: '#/overview',
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
    for (const r of ['PLAT_ADMIN', 'STEEL_BUYER', 'SUPPLIER']) {
      if (roles.indexOf(r) >= 0) return HOME[r];
    }
    return '#/login';
  }

  function menuLinks(user) {
    const codes = (user.menus || []).filter((c) => MENU_META[c]);
    const nodes = [];
    const used = {};
    codes.forEach((code) => {
      const parent = MENU_PARENT[code];
      if (parent) {
        if (used[parent]) return;
        used[parent] = true;
        const children = MENU_GROUPS[parent].filter((c) => codes.indexOf(c) >= 0);
        if (!children.length) return;
        nodes.push(UI.h('div', { class: 'nav-group', 'data-group': parent },
          UI.h('div', { class: 'nav-group-title' }, menuLabel(user, parent)),
          ...children.map((c) => UI.h('a', { 'data-menu': c, href: MENU_META[c][1] }, menuLabel(user, c)))));
      } else {
        nodes.push(UI.h('a', { 'data-menu': code, href: MENU_META[code][1] }, menuLabel(user, code)));
      }
    });
    return nodes;
  }

  function buildShell(user) {
    const root = document.getElementById('app');
    root.innerHTML = '';
    const nav = UI.h('nav', {}, ...menuLinks(user));
    const company = user.company;
    const badge = UI.h('span', { class: 'msg-badge', id: 'msg-badge', style: 'display:none' }, '0');
    const bell = UI.h('button', { class: 'bell-btn', title: '消息通知', onclick: toggleDrawer },
      badge);
    const shell = UI.h('div', { class: 'layout' },
      UI.h('aside', { class: 'sidebar' },
        UI.h('div', { class: 'logo' }, TITLE),
        nav),
      UI.h('div', { class: 'main' },
        UI.h('div', { class: 'topbar' },
          UI.h('div', { class: 'page-title', id: 'page-title' }, ''),
          bell,
          UI.h('div', { class: 'user-box' },
            UI.h('b', {}, user.realName || user.username),
            UI.h('span', {}, company ? company.companyName : '平台运营'),
            UI.h('button', { class: 'sm', onclick: logout }, '退 出'))),
        UI.h('div', { class: 'content', id: 'page' })));
    // 消息抽屉（点击铃铛从右侧滑出）：任务 / 消息 / 更多
    const mask = UI.h('div', { class: 'drawer-mask', id: 'drawer-mask', onclick: closeDrawer });
    const drawer = UI.h('aside', { class: 'drawer', id: 'drawer' },
      UI.h('div', { class: 'drawer-head' },
        UI.h('div', { class: 'drawer-tabs' },
          UI.h('button', { class: 'drawer-tab active', 'data-dtab': 'task', onclick: () => switchDrawerTab('task') }, '任务'),
          UI.h('button', { class: 'drawer-tab', 'data-dtab': 'msg', onclick: () => switchDrawerTab('msg') }, '消息')),
        UI.h('a', { class: 'drawer-more', href: '#/messages', onclick: () => closeDrawer() }, '更多')),
      UI.h('div', { class: 'drawer-body', id: 'drawer-body' }));
    root.appendChild(shell);
    root.appendChild(mask);
    root.appendChild(drawer);
    return root;
  }

  /* -------- 消息抽屉逻辑 -------- */
  let drawerTab = 'task';
  function toggleDrawer() {
    if (document.body.classList.contains('drawer-open')) closeDrawer();
    else openDrawer();
  }
  function openDrawer() {
    document.body.classList.add('drawer-open');
    loadDrawerBody();
  }
  function closeDrawer() { document.body.classList.remove('drawer-open'); }
  function switchDrawerTab(t) {
    drawerTab = t;
    document.querySelectorAll('.drawer-tab').forEach((b) => {
      b.classList.toggle('active', b.getAttribute('data-dtab') === t);
    });
    loadDrawerBody();
  }
  async function loadDrawerBody() {
    const body = document.getElementById('drawer-body');
    if (!body) return;
    body.innerHTML = '<div class="empty">加载中…</div>';
    try {
      if (drawerTab === 'task') {
        const d = await API.get('/tasks/todos');
        const list = d.list || [];
        body.innerHTML = '';
        if (!list.length) {
          body.appendChild(UI.h('div', { class: 'empty' }, '暂无待办任务'));
          return;
        }
        list.forEach((r) => {
          body.appendChild(UI.h('div', {
            class: 'drawer-item',
            onclick: () => { closeDrawer(); if (r.hash && r.hash !== location.hash) location.hash = r.hash; },
          },
            UI.h('div', { class: 'drawer-item-title' }, r.title || '-'),
            UI.h('div', { class: 'drawer-item-time' }, UI.fmtDateTime(r.createdAt))));
        });
      } else {
        const d = await API.get('/messages?page=1&size=8');
        const list = d.list || [];
        body.innerHTML = '';
        if (!list.length) {
          body.appendChild(UI.h('div', { class: 'empty' }, '暂无消息'));
          return;
        }
        list.forEach((r) => {
          body.appendChild(UI.h('div', {
            class: 'drawer-item' + (r.isRead ? '' : ' unread'),
            onclick: async () => {
              try {
                if (!r.isRead) {
                  await API.put('/messages/' + r.id + '/read');
                  App.refreshMsgBadge();
                }
                closeDrawer();
                const t = window.msgJumpTarget ? window.msgJumpTarget(r) : '';
                if (t && t !== location.hash) location.hash = t;
              } catch (e) { /* toast 已提示 */ }
            },
          },
            UI.h('div', { class: 'drawer-item-title' },
              UI.h('span', { class: 'msg-cat msg-cat-' + (r.msgCategory || 'NOTICE') }, MSG_CAT_LABEL[r.msgCategory] || '通知'),
              r.title || '-'),
            UI.h('div', { class: 'drawer-item-content' }, r.content || '-'),
            UI.h('div', { class: 'drawer-item-time' }, UI.fmtDateTime(r.createdAt))));
        });
      }
    } catch (e) {
      body.innerHTML = '';
      body.appendChild(UI.h('div', { class: 'empty' }, '加载失败：' + (e.message || e)));
    }
  }

  function highlight(pageKey) {
    document.querySelectorAll('.sidebar nav a[data-menu]').forEach((a) => {
      const on = a.getAttribute('data-menu') === pageKey;
      a.className = on ? 'active' : '';
    });
    const meta = MENU_META[pageKey];
    const title = document.getElementById('page-title');
    if (title) title.textContent = meta ? menuLabel(API.currentUser(), pageKey) : '大宗矿产集采平台';
  }

  /* 会话菜单静默刷新：每次页面加载调用一次 /auth/me，
     若后端菜单有更新则原地重建侧边栏，无需重新登录。 */
  let sessionRefreshed = false;
  async function refreshSession() {
    if (sessionRefreshed) return;
    sessionRefreshed = true;
    try {
      const fresh = await API.get('/auth/me');
      if (!fresh || !fresh.menus || !API.token()) return;
      const old = API.currentUser();
      const before = JSON.stringify((old && old.menus) || []);
      const after = JSON.stringify(fresh.menus || []);
      API.saveAuth(API.token(), fresh);
      if (before !== after) {
        const nav = document.querySelector('.sidebar nav');
        if (nav) {
          nav.innerHTML = '';
          menuLinks(fresh).forEach((a) => nav.appendChild(a));
          highlight(pageOf());
        }
      }
    } catch (e) { /* 401 等由统一错误处理走登出 */ }
  }

  function renderLoginRegister(pageKey) {
    const root = document.getElementById('app');
    root.innerHTML = '';
    const box = UI.h('div', { class: 'auth-wrap' });
    root.appendChild(box);
    if (window.Pages && window.Pages[pageKey]) window.Pages[pageKey](box, API.currentUser());
    else window.Pages.login(box, null);
  }

  /* 路由序号：并发触发（如登录时 hashchange 与显式 route() 同时调用）时，
     仅最新一次路由的渲染结果落地，避免页面内容重复拼接 */
  let routeSeq = 0;
  async function route() {
    const seq = ++routeSeq;
    const user = API.currentUser();
    const pageKey = pageOf();
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
    refreshSession();
    const target = document.getElementById('page');
    target.innerHTML = '<div class="empty" data-loading="1">加载中…</div>';
    /* 渲染到独立容器，完成后整体换入：过期路由直接丢弃 */
    const holder = UI.h('div', {});
    try {
      if (pageKey === 'messages') {
        await window.Pages.messages(holder, user);
      } else if (window.Pages && window.Pages[pageKey]) {
        await window.Pages[pageKey](holder, user);
      } else {
        holder.appendChild(UI.h('div', { class: 'empty' }, '页面不存在'));
      }
      if (seq !== routeSeq) return;
      target.innerHTML = '';
      while (holder.firstChild) target.appendChild(holder.firstChild);
    } catch (e) {
      if (seq !== routeSeq) return;
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
