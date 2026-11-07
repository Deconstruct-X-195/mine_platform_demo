/* ============ 平台后台核心视图：企业资质审核 / 账号管理 / 字典维护 ============ */

/* ---------- R4 企业资质审核 ---------- */
App.registerView('r4.company', {
  title: '企业资质审核', roles: ['R4'],
  async render(root) {
    const state = { keyword: '', company_type: '', audit_status: '' };
    const keyword = el('input', { type: 'text', placeholder: '搜索企业名称 / 联系人' });
    keyword.addEventListener('input', debounce(() => { state.keyword = keyword.value; table.reload(); }, 300));
    const typeSel = el('select', null, [el('option', { value: '' }, '全部类型'),
      ...App.dict('PARTNER_TYPE') && [['DOWNSTREAM', '下游需求企业'], ['SUPPLIER', '上游供给方'], ['PARTNER', '履约配套方']]
        .map(([v, t]) => el('option', { value: v }, t))]);
    typeSel.addEventListener('change', () => { state.company_type = typeSel.value; table.reload(); });
    const statusSel = el('select', null, [el('option', { value: '' }, '全部状态'),
      ...[['PENDING', '待审核'], ['APPROVED', '已通过'], ['REJECTED', '已驳回']]
        .map(([v, t]) => el('option', { value: v }, t))]);
    statusSel.addEventListener('change', () => { state.audit_status = statusSel.value; table.reload(); });

    const table = UI.table({
      columns: [
        { title: '企业名称', key: 'company_name', strong: true },
        { title: '类型', render: r => tag(r.company_type) },
        { title: '联系人', render: r => `${r.contact || '-'} / ${r.phone || '-'}` },
        { title: '资质附件', render: r => r.qualifications.length ? `${r.qualifications.length} 份` : '-' },
        { title: '资质状态', render: r => tag(r.audit_status) },
        { title: '提交时间', render: r => fmtTime(r.create_time) },
        {
          title: '操作', render: r => el('div', { style: { display: 'flex', gap: '2px' } }, [
            el('button', { class: 'btn-link btn btn-sm', onclick: () => showDetail(r) }, '详情'),
            r.audit_status === 'PENDING' ? el('button', { class: 'btn-link btn btn-sm', onclick: () => doAudit(r) }, '审核') : null
          ])
        }
      ],
      toolbar: { render: () => [keyword, typeSel, statusSel] },
      query: state,
      rowKey: 'company_id',
      fetch: q => API.get('/api/admin/company/list', q)
    });
    root.appendChild(el('div', { class: 'card' }, [table.root]));

    function showDetail(r) {
      UI.detail({
        title: `企业详情 · ${r.company_name}`,
        sections: [
          { title: '基本信息', items: [
            { label: '企业名称', value: r.company_name },
            { label: '统一社会信用代码', value: r.credit_code || '-' },
            { label: '类型', render: () => tag(r.company_type) },
            { label: '联系人', value: r.contact },
            { label: '手机号', value: r.phone },
            { label: '资质状态', render: () => tag(r.audit_status) },
            r.audit_remark ? { label: '审核备注/驳回原因', value: r.audit_remark, full: true } : null,
            { label: '登录账号', value: r.username || '-' },
            { label: '提交时间', value: fmtTime(r.create_time) }
          ].filter(Boolean) },
          { title: '资质附件', items: [
            { label: '资质文件', full: true, render: () => fileLinks(r.qualifications.map(q => ({ file_url: q.file_url, file_name: q.file_name }))) }
          ] }
        ]
      });
    }

    function doAudit(r) {
      UI.form({
        title: `资质审核 · ${r.company_name}`,
        fields: [
          { key: 'result', label: '审核结论', type: 'select', required: true,
            options: [{ value: 'APPROVED', label: '审核通过' }, { value: 'REJECTED', label: '驳回' }] },
          { key: 'reject_reason', label: '驳回原因', type: 'text', hint: '驳回时必填' }
        ],
        submitText: '提交审核',
        onSubmit: async v => {
          if (v.result === 'REJECTED' && !v.reject_reason.trim()) { Toast.error('驳回必须填写原因'); throw new Error(''); }
          await API.post(`/api/admin/company/${r.company_id}/audit`,
            { result: v.result, reject_reason: v.reject_reason });
          Toast.success('审核完成');
          table.reload();
        }
      });
    }
  }
});

/* ---------- R4 账号管理 ---------- */
App.registerView('r4.account', {
  title: '账号管理', roles: ['R4'],
  async render(root) {
    const state = { keyword: '', role_code: '' };
    const kw = el('input', { type: 'text', placeholder: '搜索用户名 / 姓名' });
    kw.addEventListener('input', debounce(() => { state.keyword = kw.value; table.reload(); }, 300));
    const roleSel = el('select', null, [el('option', { value: '' }, '全部角色'),
      ...['R1', 'R2', 'R3', 'R4'].map(r => el('option', { value: r }, TAG_MAP[r][0]))]);
    roleSel.addEventListener('change', () => { state.role_code = roleSel.value; table.reload(); });
    const createBtn = el('button', { class: 'btn btn-primary btn-sm', onclick: () => showCreate() }, '+ 新增账号');

    const table = UI.table({
      columns: [
        { title: '用户名', key: 'username', strong: true },
        { title: '姓名', key: 'real_name' },
        { title: '角色', render: r => tag(r.role_code) },
        { title: '所属企业', render: r => r.company_name || '平台运营方' },
        { title: '状态', render: r => tag(r.status === 'ACTIVE' ? 'APPROVED' : 'DISABLED') },
        { title: '创建时间', render: r => fmtTime(r.create_time) },
        { title: '操作', render: r => el('div', { style: { display: 'flex', gap: '2px' } }, [
          r.status === 'ACTIVE'
            ? el('button', { class: 'btn btn-sm btn-link', style: { color: 'var(--orange)' }, onclick: () => toggle(r, 'DISABLED') }, '停用')
            : el('button', { class: 'btn btn-sm btn-link', style: { color: 'var(--green)' }, onclick: () => toggle(r, 'ACTIVE') }, '启用')
        ]) }
      ],
      toolbar: { render: () => [kw, roleSel, el('span', { class: 'fb-sep' }), createBtn] },
      query: state, rowKey: 'user_id',
      fetch: q => API.get('/api/admin/account/list', q)
    });
    root.appendChild(el('div', { class: 'card' }, [table.root]));

    async function toggle(r, status) {
      await confirmDialog(`确认${status === 'DISABLED' ? '停用' : '启用'}账号 ${r.username}？`, async () => {
        await API.put(`/api/admin/account/${r.user_id}`, { status });
        Toast.success('操作成功');
        table.reload();
      }, { danger: status === 'DISABLED' });
    }

    function showCreate() {
      UI.form({
        title: '新增账号',
        fields: [
          { key: 'username', label: '用户名', type: 'text', required: true },
          { key: 'password', label: '初始密码', type: 'text', required: true, hint: '至少6位' },
          { key: 'real_name', label: '姓名', type: 'text' },
          { key: 'role_code', label: '角色', type: 'select', required: true,
            options: [['R1', '下游企业操作员'], ['R2', '上游供方操作员'], ['R3', '履约配套方操作员'], ['R4', '平台管理员']]
              .map(([v, l]) => ({ value: v, label: l })) }
        ],
        submitText: '创建',
        onSubmit: async v => { await API.post('/api/admin/account/create', v); Toast.success('创建成功'); table.reload(); }
      });
    }
  }
});

/* ---------- R4 字典维护 ---------- */
const DICT_CATS = [
  ['ORE_CATEGORY', '矿石品类'], ['PERIOD_TYPE', '申报周期'],
  ['PORT', '港口信息'], ['SUPPLIER_TYPE', '供方类型'], ['PARTNER_TYPE', '配套方类型']
];
App.registerView('r4.dict', {
  title: '字典维护', roles: ['R4'],
  async render(root) {
    const state = { category: 'ORE_CATEGORY' };
    const catTabs = el('div', { style: { display: 'flex', gap: '8px', marginBottom: '14px', flexWrap: 'wrap' } });
    const table = UI.table({
      columns: [
        { title: '编码', key: 'item_code', strong: true },
        { title: '名称', key: 'item_name' },
        { title: '排序', key: 'sort', num: true },
        { title: '状态', render: r => r.status === 1 ? tag('APPROVED') : tag('DISABLED') },
        { title: '操作', render: r => el('div', { style: { display: 'flex', gap: '2px' } }, [
          el('button', { class: 'btn btn-sm btn-link', onclick: () => showEdit(r) }, '编辑'),
          state.category === 'ORE_CATEGORY' ? el('button', { class: 'btn btn-sm btn-link',
            style: r.item_code === 'IRON' ? { color: 'var(--blue, #2563eb)' } : { color: 'var(--text-3)' },
            onclick: () => r.item_code === 'IRON' ? showOreTypes(r) : Toast.info('仅铁矿石品类支持配置矿种') }, '矿种') : null,
          el('button', { class: 'btn btn-sm btn-link', style: { color: 'var(--red)' },
            onclick: () => confirmDialog(`确认删除字典项「${r.item_name}」？`, async () => {
              await API.post(`/api/admin/dict/${r.id}/delete`); Toast.success('已删除'); table.reload();
            }, { danger: true }) }, '删除')
        ]) }
      ],
      query: state, rowKey: 'id', pageSize: 20,
      fetch: q => API.get('/api/admin/dict/list', { ...q, category: state.category })
    });

    function renderTabs() {
      catTabs.innerHTML = '';
      DICT_CATS.forEach(([code, name]) => {
        catTabs.appendChild(el('button', {
          class: `btn btn-sm ${state.category === code ? 'btn-primary' : ''}`,
          onclick: () => { state.category = code; renderTabs(); table.reload(); }
        }, name));
      });
      catTabs.appendChild(el('span', { class: 'fb-sep' }));
      catTabs.appendChild(el('button', { class: 'btn btn-primary btn-sm', onclick: () => showEdit(null) }, '+ 新增字典项'));
    }
    renderTabs();

    function showEdit(r) {
      UI.form({
        title: r ? '编辑字典项' : `新增字典项 · ${DICT_CATS.find(c => c[0] === state.category)[1]}`,
        fields: [
          { key: 'item_code', label: '编码', type: 'text', required: true, value: r ? r.item_code : '', hint: r ? '编码不可修改' : '如 IRON' },
          { key: 'item_name', label: '名称', type: 'text', required: true, value: r ? r.item_name : '' },
          { key: 'sort', label: '排序', type: 'number', value: r ? r.sort : 0, step: '1' }
        ],
        submitText: '保存',
        onSubmit: async v => {
          if (r) { await API.post('/api/admin/dict', { ...v, id: r.id, category: state.category }); }
          else { await API.post('/api/admin/dict', { ...v, category: state.category }); }
          Toast.success('保存成功');
          await App.loadDicts();
          table.reload();
        }
      });
    }

    root.appendChild(el('div', { class: 'card' }, [catTabs, table.root]));

    /* 铁矿石品类 ↔ 矿种 对应管理：查看/新增/删除该品类下矿种 */
    async function showOreTypes(catRow) {
      const body = el('div');
      const addInput = el('input', { type: 'text', placeholder: '矿种名称，如 PB粉', style: { flex: '1' } });
      const addBtn = el('button', { class: 'btn btn-primary btn-sm', onclick: () => addItem() }, '+ 新增矿种');
      const bar = el('div', { style: { display: 'flex', gap: '8px', marginBottom: '10px' } }, [addInput, addBtn]);
      body.appendChild(bar);
      const listBox = el('div');
      body.appendChild(listBox);

      async function loadList() {
        const d = await API.get('/api/admin/dict/list', { category: 'IRON_ORE_TYPE', page_size: 100 });
        const rows = d.list;
        listBox.innerHTML = '';
        listBox.appendChild(el('div', { style: { marginBottom: '6px', color: 'var(--text-3)', fontSize: '12.5px' } },
          `品类「${catRow.item_name}」(${catRow.item_code}) 共配置 ${rows.length} 个矿种，申报单选择铁矿石时可调取`));
        listBox.appendChild(el('table', { class: 'tb' }, [
          el('thead', null, el('tr', null, ['编码', '名称', '排序', '状态', '操作'].map(h => el('th', null, h)))),
          el('tbody', null, rows.length ? rows.map(r => el('tr', null, [
            el('td', null, r.item_code), el('td', null, r.item_name), el('td', null, String(r.sort)),
            el('td', null, r.status === 1 ? tag('APPROVED') : tag('DISABLED')),
            el('td', null, el('button', { class: 'btn btn-sm btn-link', style: { color: 'var(--red)' },
              onclick: () => confirmDialog(`确认删除矿种「${r.item_name}」？`, async () => {
                await API.post(`/api/admin/dict/${r.id}/delete`);
                Toast.success('已删除'); await App.loadDicts(); loadList();
              }, { danger: true }) }, '删除'))
          ])) : el('tr', null, el('td', { colspan: 5, style: { textAlign: 'center', color: 'var(--text-3)' } }, '暂无矿种')))
        ]));
      }

      async function addItem() {
        const name = addInput.value.trim();
        if (!name) { Toast.error('请输入矿种名称'); return; }
        const sort = Date.now() % 10000; // 追加到末尾
        await API.post('/api/admin/dict', {
          category: 'IRON_ORE_TYPE', item_code: 'IRON_TYPE_' + Date.now().toString(36).toUpperCase(),
          item_name: name, sort
        });
        Toast.success('矿种已添加');
        addInput.value = '';
        await App.loadDicts();
        loadList();
      }

      await loadList();
      openModal({ title: `矿种管理 · ${catRow.item_name}`, body, wide: true });
    }
  }
});

/* ---------- R4 全局数据统计看板 (PRD-08 §2.4) ---------- */
App.registerView('r4.dashboard', {
  title: '全局看板', roles: ['R4'],
  async render(root) {
    const state = { start_date: '', end_date: '' };
    const startIn = el('input', { type: 'date' });
    const endIn = el('input', { type: 'date' });
    startIn.addEventListener('change', () => { state.start_date = startIn.value; load(); });
    endIn.addEventListener('change', () => { state.end_date = endIn.value; load(); });

    const barBox = el('div', { style: { height: '260px', position: 'relative' } }, el('canvas', { style: { width: '100%', height: '100%' } }));
    const lineBox = el('div', { style: { height: '260px', position: 'relative' } }, el('canvas', { style: { width: '100%', height: '100%' } }));
    const pieBox = el('div', { style: { height: '260px', position: 'relative' } }, el('canvas', { style: { width: '100%', height: '100%' } }));
    const cardsBox = el('div', { class: 'stat-grid', style: { display: 'grid', gridTemplateColumns: 'repeat(6,1fr)', gap: '10px', marginBottom: '14px' } });

    root.appendChild(el('div', { class: 'card' }, el('div', { style: { display: 'flex', gap: '10px', alignItems: 'center' } }, [
      el('span', { class: 'card-title', style: { margin: 0 } }, '统计时间范围'),
      startIn, el('span', { class: 'hint' }, '至'), endIn,
      el('span', { class: 'hint', style: { marginLeft: 'auto' } }, '留空 = 全部历史')
    ])));
    root.appendChild(cardsBox);
    root.appendChild(el('div', { style: { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px', marginTop: '12px' } }, [
      el('div', { class: 'card' }, [el('div', { class: 'card-title' }, '各周期申报需求量（吨）'), barBox]),
      el('div', { class: 'card' }, [el('div', { class: 'card-title' }, '集采订单月度趋势（吨）'), lineBox])
    ]));
    root.appendChild(el('div', { class: 'card', style: { marginTop: '12px' } }, [el('div', { class: 'card-title' }, '品类需求分布（吨）'), pieBox]));

    async function load() {
      const d = await API.get('/api/admin/dashboard/summary', state);
      cardsBox.innerHTML = '';
      const co = d.companies;
      const cards = [
        ['下游企业', co.DOWNSTREAM, '家'], ['上游供方', co.SUPPLIER, '家'], ['物流配套方', co.PARTNER, '家'],
        ['待审核企业', co.PENDING, '家'], ['集采订单', d.execution.order_count, '单'],
        ['锁货总量', fmtQty(d.locked.total_qty), '吨']
      ];
      cards.forEach(([label, val, unit]) => cardsBox.appendChild(el('div', { class: 'card', style: { padding: '14px 16px', margin: 0 } }, [
        el('div', { class: 'd-label' }, label),
        el('div', { class: 'd-value', style: { fontSize: '22px', fontWeight: 700 } }, String(val)),
        el('div', { class: 'hint' }, unit)
      ])));
      Charts.bar(barBox.firstChild, d.demand_by_period.map(x => x.period),
        [{ name: '申报需求', color: '#4f7cff', data: d.demand_by_period.map(x => x.total_qty) }], { unit: '吨' });
      Charts.line(lineBox.firstChild, d.order_trend.map(x => x.ym),
        [{ name: '锁货吨数', color: '#22c55e', data: d.order_trend.map(x => x.total_qty) }], { unit: '吨' });
      Charts.pie(pieBox.firstChild, d.demand_pie.map(x => ({ name: dictName(App.dict('ORE_CATEGORY'), x.ore_category), value: x.total_qty })), { unit: '吨' });
    }
    await load();
  }
});

/* ---------- R4 全量业务单据检索 (PRD-08 §2.5) ---------- */
const DOC_CATS = [['demand', '申报需求'], ['list', '集采清单'], ['task', '询价任务'], ['order', '集采订单'],
  ['alloc', '分拨单'], ['logistics', '物流任务'], ['bill', '对账单']];
const DOC_STATUS = {
  demand: ['DRAFT', 'SUBMITTED', 'IN_PROCESS', 'IN_LIST', 'IN_EXEC', 'DISTRIBUTED', 'CANCELLED'],
  list: ['WAIT', 'INQUIRED', 'EXECUTING', 'DONE'],
  task: ['WAIT_QUOTE', 'QUOTING', 'LOCKED', 'IN_LOGISTICS', 'LOGI_DONE', 'ARCHIVED'],
  order: ['LOCKED', 'IN_LOGISTICS', 'WAIT_CONFIRM', 'SETTLED', 'ARCHIVED'],
  alloc: ['TRANSIT', 'WAIT_CONFIRM', 'DONE'],
  logistics: [], bill: ['PENDING', 'CONFIRMED', 'DISPUTE', 'SETTLED']
};

App.registerView('r4.ledgerSearch', {
  title: '单据检索', roles: ['R4'],
  async render(root) {
    const state = { doc_type: 'demand', keyword: '', company: '', status: '', start_date: '', end_date: '' };
    const tabBar = el('div', { style: { display: 'flex', gap: '8px', marginBottom: '14px', flexWrap: 'wrap' } });
    const kwIn = el('input', { type: 'text', placeholder: '单号/关键词', style: { width: '170px' } });
    kwIn.addEventListener('input', debounce(() => { state.keyword = kwIn.value.trim(); table.reload(); }, 350));
    const coIn = el('input', { type: 'text', placeholder: '企业名称', style: { width: '150px' } });
    coIn.addEventListener('input', debounce(() => { state.company = coIn.value.trim(); table.reload(); }, 350));
    const stSel = el('select', null, [el('option', { value: '' }, '全部状态')]);
    stSel.addEventListener('change', () => { state.status = stSel.value; table.reload(); });
    const sIn = el('input', { type: 'date' }); sIn.addEventListener('change', () => { state.start_date = sIn.value; table.reload(); });
    const eIn = el('input', { type: 'date' }); eIn.addEventListener('change', () => { state.end_date = eIn.value; table.reload(); });

    const table = UI.table({
      columns: [
        { title: '单据编号', key: 'doc_no', strong: true, render: r => r.doc_no || r.list_no || `#${r.id}` },
        { title: '企业', render: r => r.company_name || '-' },
        { title: '周期', render: r => r.period || '-' },
        { title: '品类', render: r => r.ore_category ? dictName(App.dict('ORE_CATEGORY'), r.ore_category) : '-' },
        { title: '数量/金额', num: true, render: r => r.quantity != null ? (r.ore_category ? fmtQty(r.quantity) + ' 吨' : fmtMoney(r.quantity)) : (r.total_amount != null ? fmtMoney(r.total_amount) : '-') },
        { title: '状态', render: r => r.status ? tag(r.status) : (r.current_node ? el('span', { class: 'tag tag-blue' }, `N${r.current_node}`) : '-') },
        { title: '创建时间', key: 'create_time' },
        { title: '操作', render: r => el('button', { class: 'btn btn-sm btn-link', onclick: () => showDoc(r) }, '详情·轨迹') }
      ],
      toolbar: { render: () => [kwIn, coIn, stSel, sIn, eIn] },
      query: state, rowKey: 'id',
      fetch: q => API.get('/api/admin/ledger/search', q).then(res => {
        const g = res.groups[0];
        return { list: g.list, total: g.total };
      })
    });

    function renderTabs() {
      tabBar.innerHTML = '';
      DOC_CATS.forEach(([k, name]) => {
        tabBar.appendChild(el('button', {
          class: `btn btn-sm ${state.doc_type === k ? 'btn-primary' : ''}`,
          onclick: () => {
            state.doc_type = k; state.status = '';
            stSel.innerHTML = '';
            stSel.appendChild(el('option', { value: '' }, '全部状态'));
            (DOC_STATUS[k] || []).forEach(s => stSel.appendChild(el('option', { value: s }, (TAG_MAP[s] || [s])[0])));
            renderTabs(); table.reload();
          }
        }, name));
      });
    }
    renderTabs();
    root.appendChild(el('div', { class: 'card' }, [tabBar, table.root]));

    async function showDoc(r) {
      const d = await API.get(`/api/admin/ledger/doc?doc_type=${state.doc_type}&id=${r.id}`);
      const body = el('div', null);
      body.appendChild(el('div', { class: 'desc-grid', style: { gridTemplateColumns: 'repeat(4,1fr)' } },
        Object.entries(d.doc).filter(([k]) => !['creator_id', 'operator_id', 'task_id', 'collective_id'].includes(k))
          .slice(0, 16).map(([k, v]) => el('div', { class: 'desc-item' }, [
            el('div', { class: 'd-label' }, k),
            el('div', { class: 'd-value' }, v == null || v === '' ? '-' : String(v))
          ]))));
      body.appendChild(el('div', { class: 'card-title', style: { margin: '14px 0 8px' } }, '操作轨迹'));
      if (!d.logs.length) body.appendChild(el('div', { class: 'hint' }, '暂无关联日志'));
      else {
        const tb = el('table', { class: 'tb' }, [
          el('thead', null, el('tr', null, ['时间', '操作人', '角色', '操作', '详情', '状态变化'].map(h => el('th', null, h)))),
          el('tbody', null, d.logs.map(l => el('tr', null, [
            el('td', null, l.create_time), el('td', { class: 'strong' }, l.operator_name),
            el('td', null, l.role_code || '-'), el('td', null, l.action),
            el('td', null, l.detail || '-'),
            el('td', null, l.before_status || l.after_status ? `${l.before_status || '-'} → ${l.after_status || '-'}` : '-')
          ])))
        ]);
        body.appendChild(el('div', { class: 'table-wrap' }, tb));
      }
      openModal({ title: `单据详情 · ${r.doc_no || `#${r.id}`}`, wide: true, body,
        footer: close => [el('button', { class: 'btn', onclick: close }, '关闭')] });
    }
  }
});

/* ---------- R4 操作日志审计 (PRD-08 §2.6) ---------- */
App.registerView('r4.log', {
  title: '操作日志', roles: ['R4'],
  async render(root) {
    const state = { action: '', role_code: '', start_date: '', end_date: '' };
    const aIn = el('input', { type: 'text', placeholder: '操作类型关键词', style: { width: '160px' } });
    aIn.addEventListener('input', debounce(() => { state.action = aIn.value.trim(); table.reload(); }, 350));
    const rSel = el('select', null, [el('option', { value: '' }, '全部角色'), ...['R1', 'R2', 'R3', 'R4'].map(r => el('option', { value: r }, r))]);
    rSel.addEventListener('change', () => { state.role_code = rSel.value; table.reload(); });
    const sIn = el('input', { type: 'date' }); sIn.addEventListener('change', () => { state.start_date = sIn.value; table.reload(); });
    const eIn = el('input', { type: 'date' }); eIn.addEventListener('change', () => { state.end_date = eIn.value; table.reload(); });
    const expBtn = el('button', { class: 'btn btn-sm', onclick: () => API.download('/api/admin/log/export', state, '操作日志.xlsx') }, '⬇ 导出');

    const table = UI.table({
      columns: [
        { title: '时间', key: 'create_time' },
        { title: '操作人', key: 'operator_name', strong: true },
        { title: '角色', render: r => r.role_code ? el('span', { class: 'tag tag-gray' }, r.role_code) : '-' },
        { title: '操作', key: 'action' },
        { title: '详情', render: r => el('span', { title: r.detail, style: { display: 'inline-block', maxWidth: '340px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', verticalAlign: 'bottom' } }, r.detail || '-') },
        { title: '状态变化', render: r => (r.before_status || r.after_status) ? `${r.before_status || '-'} → ${r.after_status || '-'}` : '-' },
        { title: '关联单据', render: r => r.ref_type ? `${r.ref_type}#${r.ref_id}` : '-' }
      ],
      toolbar: { render: () => [aIn, rSel, sIn, eIn, el('span', { class: 'fb-sep' }), expBtn] },
      query: state, rowKey: 'id', page_size: 15,
      fetch: q => API.get('/api/admin/log/list', q)
    });
    root.appendChild(el('div', { class: 'card' }, [table.root]));
  }
});

/* ---------- R4 矿石化验指标模板 (PRD-08 §2.3) ---------- */
App.registerView('r4.indicator', {
  title: '指标模板', roles: ['R4'],
  async render(root) {
    const table = UI.table({
      columns: [
        { title: '品类', render: r => dictName(App.dict('ORE_CATEGORY'), r.ore_category) },
        { title: '字段名', key: 'field_name', strong: true },
        { title: '显示名', key: 'field_label' },
        { title: '类型', render: r => r.field_type === 'number' ? '数值' : '文本' },
        { title: '必填', render: r => r.required ? tag('APPROVED') : el('span', { class: 'tag tag-gray' }, '选填') },
        { title: '排序', key: 'sort', num: true },
        { title: '操作', render: r => el('div', { style: { display: 'flex', gap: '2px' } }, [
          el('button', { class: 'btn btn-sm btn-link', onclick: () => showEdit(r) }, '编辑'),
          el('button', { class: 'btn btn-sm btn-link', style: { color: 'var(--red)' },
            onclick: () => confirmDialog(`确认删除指标字段「${r.field_label}」？`, async () => {
              await API.post(`/api/admin/indicator/template/${r.id}/delete`); Toast.success('已删除'); table.reload();
            }, { danger: true }) }, '删除')
        ]) }
      ],
      query: {}, rowKey: 'id', pageSize: 20,
      fetch: q => API.get('/api/admin/indicator/template', q)
    });

    function showEdit(r) {
      UI.form({
        title: r ? '编辑指标字段' : '新增指标字段',
        fields: [
          { key: 'ore_category', label: '矿石品类', type: 'select', required: true,
            options: App.dict('ORE_CATEGORY').map(d => ({ value: d.item_code, label: d.item_name })),
            value: r ? r.ore_category : '' },
          { key: 'field_name', label: '字段名（英文标识）', type: 'text', required: true, value: r ? r.field_name : '', hint: '如 fe / moisture / size' },
          { key: 'field_label', label: '显示名', type: 'text', required: true, value: r ? r.field_label : '', hint: '如 铁品位(%)' },
          { key: 'field_type', label: '字段类型', type: 'select', options: [{ value: 'text', label: '文本' }, { value: 'number', label: '数值' }], value: r ? r.field_type : 'text' },
          { key: 'required', label: '是否必填', type: 'select', options: [{ value: 1, label: '必填' }, { value: 0, label: '选填' }], value: r ? r.required : 0 },
          { key: 'sort', label: '排序', type: 'number', value: r ? r.sort : 0, step: '1' }
        ],
        submitText: '保存',
        onSubmit: async v => {
          await API.post('/api/admin/indicator/template', { ...v, id: r ? r.id : undefined });
          Toast.success('保存成功');
          table.reload();
        }
      });
    }

    root.appendChild(el('div', { class: 'card' }, [
      el('div', { style: { display: 'flex', alignItems: 'center', marginBottom: '10px' } }, [
        el('div', { class: 'card-title', style: { margin: 0 } }, '矿石化验指标模板（按品类驱动货源/申报表单字段）'),
        el('button', { class: 'btn btn-primary btn-sm', style: { marginLeft: 'auto' }, onclick: () => showEdit(null) }, '+ 新增指标字段')
      ]),
      table.root
    ]));
  }
});
