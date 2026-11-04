/* ============ 应用核心：路由 / 菜单 / 布局 ============ */
/* 品牌 LOGO：iOS 风格圆角方块 + 蓝色渐变 + 白色山形（与 favicon 同源，全局唯一标识） */
const APP_LOGO = `<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 48 48'>
  <defs><linearGradient id='lg' x1='0' y1='0' x2='0' y2='1'>
    <stop offset='0' stop-color='#42a2ff'/><stop offset='1' stop-color='#0a6fe8'/>
  </linearGradient></defs>
  <rect width='48' height='48' rx='10.8' fill='url(#lg)'/>
  <path d='M9.5 33.5 L19.5 15.5 L26 27.5 L30.5 19.5 L38.5 33.5 Z' fill='#fff' stroke='#fff' stroke-width='2.5' stroke-linejoin='round'/>
  <circle cx='36' cy='11.5' r='2.6' fill='#fff'/>
</svg>`;

const App = {
  user: null,
  views: {},      // key -> {title, roles, render}
  menus: [],      // {key, title, icon, group, roles}
  dicts: {},

  registerView(key, def) { this.views[key] = def; },
  addMenu(items) { this.menus.push(...items); },

  async loadDicts() {
    const cats = ['ORE_CATEGORY', 'PERIOD_TYPE', 'PORT', 'PARTNER_TYPE', 'SUPPLIER_TYPE'];
    for (const c of cats) {
      try { this.dicts[c] = await API.get(`/api/dict/${c}`); } catch (e) { this.dicts[c] = []; }
    }
  },
  dict(cat) { return this.dicts[cat] || []; },

  route() {
    return (location.hash || '#/home').slice(2) || 'home';
  },

  async navigate() {
    const key = this.route();
    const view = this.views[key];
    const contentEl = $('#content');
    if (!view) { location.hash = '#/home'; return; }
    if (view.roles && !view.roles.includes(this.user.role_code)) { location.hash = '#/home'; return; }
    // 高亮菜单
    $$('.menu-item').forEach(mi => mi.classList.toggle('active', mi.dataset.key === key));
    $('#pageTitle').textContent = view.title;
    contentEl.innerHTML = '';
    const loadingEl = UI.loading();
    contentEl.appendChild(loadingEl);
    try {
      await view.render(contentEl);
      loadingEl.remove();  // 视图渲染完成后移除加载占位（视图均以 append 方式挂载，不会自动清除）
    }
    catch (e) { console.error(e); contentEl.innerHTML = ''; contentEl.appendChild(UI.empty('页面加载失败')); }
  },

  logout() {
    API.request('POST', '/api/auth/logout').catch(() => {});
    API.token = '';
    this.user = null;
    location.hash = '#/login';
  },

  async boot() {
    window.addEventListener('hashchange', () => this.handle());
    this.handle();
  },

  async handle() {
    const app = $('#app');
    if (this.route() === 'login') { this.renderLogin(app); return; }
    if (!API.token) { location.hash = '#/login'; return; }
    if (!this.user) {
      try { this.user = await API.get('/api/auth/me'); }
      catch (e) { location.hash = '#/login'; return; }
    }
    if (!Object.keys(this.dicts).length) await this.loadDicts();
    // 布局已存在时仅切换内容区，避免重建侧边栏导致菜单滚动位置丢失
    if ($('#content') && app.querySelector('.sidebar')) { this.navigate(); return; }
    this.renderLayout(app);
  },

  /* ---------- 登录页 ---------- */
  renderLogin(root) {
    root.innerHTML = '';
    const userInput = el('input', { type: 'text', placeholder: '请输入用户名' });
    const pwdInput = el('input', { type: 'password', placeholder: '请输入密码' });
    const form = el('form', { class: 'login-box' }, [
      el('div', { class: 'login-brand' }, [
        el('div', { class: 'brand-logo', html: APP_LOGO }),
        el('h1', null, '矿石集中集采平台')
      ]),
      el('div', { class: 'login-sub' }, '以量换价 · 集中保供 · 全链路可视'),
      el('div', { class: 'field' }, [el('label', null, '用户名'), userInput]),
      el('div', { class: 'field' }, [el('label', null, '密码'), pwdInput]),
      el('button', { class: 'btn btn-primary', type: 'submit' }, '登 录'),
      el('div', { class: 'login-foot' }, [
        el('a', { href: 'javascript:;', onclick: e => { e.preventDefault(); App.showRegister(); } }, '企业主体注册'),
        ' · PC Web 端 · Chrome / Edge 推荐访问'
      ])
    ]);
    form.addEventListener('submit', async e => {
      e.preventDefault();
      if (!userInput.value.trim() || !pwdInput.value) { Toast.error('请输入用户名和密码'); return; }
      const btn = $('button[type=submit]', form);
      btn.disabled = true; btn.textContent = '登录中...';
      try {
        const data = await API.request('POST', '/api/auth/login',
          { username: userInput.value.trim(), password: pwdInput.value }, { silent: true });
        API.token = data.token;
        this.user = null;
        location.hash = '#/home';
        Toast.success(`欢迎回来，${data.user.real_name || data.user.username}`);
      } catch (err) {
        Toast.error(err.message || '登录失败');
      } finally {
        btn.disabled = false; btn.textContent = '登 录';
      }
    });
    root.appendChild(el('div', { class: 'login-page' }, form));
  },

  /* ---------- 主布局 ---------- */
  renderLayout(root) {
    const u = this.user;
    const roleTag = tag(u.role_code);
    const menus = this.menus.filter(m => !m.roles || m.roles.includes(u.role_code));
    const groups = [...new Set(menus.map(m => m.group || '业务功能'))];

    root.innerHTML = '';
    root.appendChild(el('div', { class: 'layout' }, [
      el('aside', { class: 'sidebar' }, [
        el('div', { class: 'brand' }, [
          el('div', { class: 'brand-logo', html: APP_LOGO }),
          el('div', { class: 'brand-name' }, '矿石集采平台')
        ]),
        el('nav', { class: 'menu' }, groups.map(g => [
          groups.length > 1 ? el('div', { class: 'menu-group' }, g) : null,
          ...menus.filter(m => (m.group || '业务功能') === g).map(m =>
            el('div', { class: 'menu-item', 'data-key': m.key, onclick: () => location.hash = '#/' + m.key }, [
              el('span', { class: 'mi-icon' }, m.icon || '◦'),
              el('span', { class: 'mi-text' }, m.title)
            ]))
        ])),
        el('div', { class: 'sidebar-foot' }, [
          el('div', { class: 'user-chip', onclick: () => this.showProfile() }, [
            el('div', { class: 'avatar' }, (u.real_name || u.username).slice(0, 1)),
            el('div', { class: 'user-meta' }, [
              el('div', { class: 'u-name' }, u.real_name || u.username, ' ', roleTag),
              el('div', { class: 'u-comp' }, u.company ? u.company.company_name : '平台运营方')
            ]),
            el('span', { style: { color: 'var(--text-3)', fontSize: '12px' }, title: '退出登录', onclick: e => { e.stopPropagation(); this.logout(); } }, '⎋')
          ])
        ])
      ]),
      el('main', { class: 'main' }, [
        el('header', { class: 'topbar' }, [
          el('div', { class: 'page-title', id: 'pageTitle' }, ''),
          el('div', { style: { display: 'flex', alignItems: 'center', gap: '14px' } }, [
            el('div', { id: 'msgBell', style: { position: 'relative', cursor: 'pointer', fontSize: '18px' },
              title: '消息中心', onclick: () => location.hash = '#/msg.center' }, [
              el('span', null, '🔔'),
              el('span', { id: 'msgBellBadge', style: { display: 'none', position: 'absolute', top: '-6px', right: '-8px',
                background: 'var(--red, #ef4444)', color: '#fff', borderRadius: '9px', fontSize: '10px',
                minWidth: '16px', height: '16px', lineHeight: '16px', textAlign: 'center', padding: '0 3px' } }, '')
            ]),
            el('div', { style: { color: 'var(--text-3)', fontSize: '12.5px' } },
              new Date().toLocaleDateString('zh-CN', { year: 'numeric', month: 'long', day: 'numeric', weekday: 'long' }))
          ])
        ]),
        el('div', { class: 'content', id: 'content' })
      ])
    ]));
    this.startMsgPolling();
    this.navigate();
  },

  /* 消息未读轮询（PRD-12） */
  startMsgPolling() {
    const refresh = async () => {
      if (!this.user) return;
      try {
        const d = await API.get('/api/message/unread-count');
        const badge = document.getElementById('msgBellBadge');
        if (!badge) return;
        if (d.count > 0) { badge.textContent = d.count > 99 ? '99+' : d.count; badge.style.display = 'block'; }
        else badge.style.display = 'none';
      } catch (e) { /* 静默 */ }
    };
    refresh();
    if (this._msgTimer) clearInterval(this._msgTimer);
    this._msgTimer = setInterval(refresh, 30000);
  },

  /* ---------- 企业主体注册 ---------- */
  showRegister() {
    const typeOptions = [
      { value: 'DOWNSTREAM', label: '下游需求企业' },
      { value: 'SUPPLIER', label: '上游供给方' },
      { value: 'PARTNER', label: '履约配套方' }
    ];
    UI.form({
      title: '企业主体注册（提交资质，待平台审核）',
      wide: true,
      fields: [
        { key: 'company_type', label: '企业类型', type: 'select', required: true, options: typeOptions },
        { key: 'company_name', label: '企业名称', type: 'text', required: true, full: true },
        { key: 'credit_code', label: '统一社会信用代码', type: 'text', full: true },
        { key: 'username', label: '登录账号', type: 'text', required: true },
        { key: 'password', label: '登录密码', type: 'text', required: true, hint: '至少6位' },
        { key: 'contact', label: '联系人', type: 'text', required: true },
        { key: 'phone', label: '手机号', type: 'text', required: true },
        { key: 'partner_type', label: '配套方类型', type: 'select', hint: '履约配套方必选',
          options: App.dict('PARTNER_TYPE').map(d => ({ value: d.item_code, label: d.item_name })) },
        { key: 'supplier_type', label: '供方类型', type: 'select', hint: '上游供给方必选',
          options: App.dict('SUPPLIER_TYPE').map(d => ({ value: d.item_code, label: d.item_name })) },
        { key: 'qualifications', label: '资质附件（营业执照等）', type: 'file', required: true, full: true }
      ],
      submitText: '提交注册',
      onSubmit: async v => {
        await API.request('POST', '/api/auth/register', {
          company_type: v.company_type, company_name: v.company_name, credit_code: v.credit_code,
          username: v.username, password: v.password, contact: v.contact, phone: v.phone,
          partner_type: v.partner_type || null, supplier_type: v.supplier_type || null,
          qualifications: (v.qualifications || []).map(f => ({ cert_type: 'BUSINESS_LICENSE', ...f }))
        }, { silent: true });
        Toast.success('注册成功，等待平台资质审核');
      }
    });
  },

  showProfile() {
    const u = this.user;
    UI.detail({
      title: '账号信息',
      sections: [{
        title: '基本信息',
        items: [
          { label: '用户名', value: u.username },
          { label: '姓名', value: u.real_name || '-' },
          { label: '角色', render: () => tag(u.role_code) },
          { label: '所属企业', value: u.company ? u.company.company_name : '平台运营方' },
          u.company ? { label: '资质状态', render: () => tag(u.company.audit_status) } : null,
          u.company && u.company.audit_status === 'REJECTED' ? { label: '驳回原因', value: u.company.audit_remark, full: true } : null
        ].filter(Boolean)
      }]
    });
  }
};
