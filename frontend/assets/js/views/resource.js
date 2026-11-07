/* ============ 货源资源模块视图 (PRD-03) ============ */

function resFields(row) {
  return [
    { key: 'ore_category', label: '矿石品类', type: 'select', required: true,
      options: App.dict('ORE_CATEGORY').map(d => ({ value: d.item_code, label: d.item_name })), value: row ? row.ore_category : '' },
    { key: 'origin', label: '产地', type: 'text', required: true, value: row ? row.origin : '', placeholder: '如 澳大利亚皮尔巴拉' },
    { key: 'grade', label: '品位', type: 'text', required: true, value: row ? row.grade : '', placeholder: '如 TFe 62.5%' },
    { key: 'max_qty', label: '可供应最大吨数', type: 'number', required: true, value: row ? row.max_qty : '', hint: '大于0' },
    { key: 'granularity', label: '粒度', type: 'text', value: row ? row.granularity : '' },
    { key: 'moisture', label: '水分(%)', type: 'text', value: row ? row.moisture : '' },
    { key: 'impurity', label: '杂质指标', type: 'text', value: row ? row.impurity : '' },
    { key: 'supply_period', label: '可供应周期', type: 'text', required: true, value: row ? row.supply_period : '', placeholder: '如 2026-01 ~ 2026-06' },
    { key: 'remark', label: '备注', type: 'textarea', full: true, value: row ? row.remark : '', maxlength: 500 },
    { key: 'attachments', label: '附件（质检报告等）', type: 'file', full: true, value: [] }
  ];
}

/* ---------- R2 货源管理 ---------- */
App.registerView('r2.resource', {
  title: '货源管理', roles: ['R2'],
  async render(root) {
    const state = { ore_category: '', status: '' };
    const catSel = el('select', null, [el('option', { value: '' }, '全部品类'),
      ...App.dict('ORE_CATEGORY').map(d => el('option', { value: d.item_code }, d.item_name))]);
    catSel.addEventListener('change', () => { state.ore_category = catSel.value; table.reload(); });
    const statusSel = el('select', null, [el('option', { value: '' }, '全部状态'),
      ...['DRAFT', 'ON_SHELF', 'OFF_SHELF', 'FORCE_OFF'].map(s => el('option', { value: s }, TAG_MAP[s][0]))]);
    statusSel.addEventListener('change', () => { state.status = statusSel.value; table.reload(); });
    const newBtn = el('button', { class: 'btn btn-primary btn-sm', onclick: () => showForm(null) }, '+ 新增货源');

    const table = UI.table({
      columns: [
        { title: '品类', render: r => dictName(App.dict('ORE_CATEGORY'), r.ore_category), strong: true },
        { title: '产地', key: 'origin' },
        { title: '品位', key: 'grade' },
        { title: '最大吨数', num: true, render: r => fmtQty(r.max_qty) + ' 吨' },
        { title: '供应周期', key: 'supply_period' },
        { title: '优选', render: r => r.is_preferred ? el('span', { class: 'tag tag-orange' }, '★ 优选') : '-' },
        { title: '状态', render: r => tag(r.status) },
        { title: '更新时间', render: r => fmtTime(r.update_time) },
        { title: '操作', render: r => el('div', { style: { display: 'flex', gap: '0', whiteSpace: 'nowrap' } }, [
          el('button', { class: 'btn btn-sm btn-link', onclick: () => showDetail(r) }, '详情'),
          r.status === 'DRAFT' ? el('button', { class: 'btn btn-sm btn-link', onclick: () => showForm(r) }, '编辑') : null,
          r.status === 'DRAFT' ? el('button', { class: 'btn btn-sm btn-link', style: { color: 'var(--green)' }, onclick: () => doAction(r, 'submit', '提交上架') }, '上架') : null,
          r.status === 'ON_SHELF' ? el('button', { class: 'btn btn-sm btn-link', style: { color: 'var(--orange)' }, onclick: () => doAction(r, 'off', '主动下架') }, '下架') : null,
          ['OFF_SHELF', 'FORCE_OFF'].includes(r.status) ? el('button', { class: 'btn btn-sm btn-link', style: { color: 'var(--green)' }, onclick: () => doAction(r, 'on', '重新上架') }, '重新上架') : null,
          r.status === 'FORCE_OFF' && r.down_reason ? el('span', { title: '强制下架原因: ' + r.down_reason, style: { color: 'var(--red)', fontSize: '12px', alignSelf: 'center' } }, '⚠') : null
        ]) }
      ],
      toolbar: { render: () => [catSel, statusSel, el('span', { class: 'fb-sep' }), newBtn] },
      query: state, rowKey: 'resource_id',
      fetch: q => API.get('/api/resource/list', q)
    });
    root.appendChild(el('div', { class: 'card' }, [table.root]));

    async function showForm(row) {
      UI.formDual({
        title: row ? '编辑货源（草稿）' : '新增货源',
        fields: resFields(row), wide: true,
        buttons: [
          { text: '保存草稿', action: 'draft' },
          { text: '保存并上架', action: 'submit', primary: true }
        ],
        onSubmit: async (v, action) => {
          const payload = { ...v, action, attachments: (v.attachments || []).map(f => ({ file_url: f.file_url, file_name: f.file_name })) };
          if (row) await API.put(`/api/resource/${row.resource_id}`, payload);
          else await API.post('/api/resource/create', payload);
          Toast.success(action === 'draft' ? '草稿已保存' : '已上架');
          table.reload();
        }
      });
    }

    async function doAction(r, act, label) {
      await confirmDialog(`确认${label}该货源（${dictName(App.dict('ORE_CATEGORY'), r.ore_category)} · ${r.origin}）？`, async () => {
        await API.post(`/api/resource/${r.resource_id}/${act}`);
        Toast.success(label + '成功');
        table.reload();
      });
    }

    async function showDetail(r) {
      const d = await API.get(`/api/resource/${r.resource_id}`);
      UI.detail({
        title: `货源详情 · ${dictName(App.dict('ORE_CATEGORY'), d.ore_category)}`,
        wide: true,
        sections: [{ title: '货源信息', items: [
          { label: '供方', value: d.company_name },
          { label: '品类', value: dictName(App.dict('ORE_CATEGORY'), d.ore_category) },
          { label: '产地', value: d.origin },
          { label: '品位', value: d.grade },
          { label: '粒度', value: d.granularity || '-' },
          { label: '水分', value: d.moisture || '-' },
          { label: '杂质', value: d.impurity || '-' },
          { label: '最大吨数', value: fmtQty(d.max_qty) + ' 吨' },
          { label: '供应周期', value: d.supply_period },
          { label: '优选', render: () => d.is_preferred ? el('span', { class: 'tag tag-orange' }, '★ 优选') : '-' },
          { label: '状态', render: () => tag(d.status) },
          d.down_reason ? { label: '下架原因', value: d.down_reason, full: true } : null,
          { label: '备注', value: d.remark || '-', full: true },
          { label: '附件', full: true, render: () => fileLinks(d.attachments) }
        ].filter(Boolean) }]
      });
    }
  }
});

/* ---------- R4 上游资源台账 ---------- */
App.registerView('r4.supplierLedger', {
  title: '上游资源台账', roles: ['R4'],
  async render(root) {
    const state = { ore_category: '', status: '', supplier: '' };
    const supIn = el('input', { type: 'text', placeholder: '供方名称' });
    supIn.addEventListener('input', debounce(() => { state.supplier = supIn.value.trim(); table.reload(); }, 300));
    const catSel = el('select', null, [el('option', { value: '' }, '全部品类'),
      ...App.dict('ORE_CATEGORY').map(d => el('option', { value: d.item_code }, d.item_name))]);
    catSel.addEventListener('change', () => { state.ore_category = catSel.value; table.reload(); });
    const statusSel = el('select', null, [el('option', { value: '' }, '全部状态'),
      ...['DRAFT', 'ON_SHELF', 'OFF_SHELF', 'FORCE_OFF'].map(s => el('option', { value: s }, TAG_MAP[s][0]))]);
    statusSel.addEventListener('change', () => { state.status = statusSel.value; table.reload(); });
    const exportBtn = el('button', { class: 'btn btn-primary btn-sm', onclick: () => API.download('/api/admin/resource/export', {}, '上游资源台账.xlsx') }, '⬇ 导出台账');

    const table = UI.table({
      columns: [
        { title: '供方', key: 'company_name', strong: true },
        { title: '品类', render: r => dictName(App.dict('ORE_CATEGORY'), r.ore_category) },
        { title: '产地', key: 'origin' },
        { title: '品位', key: 'grade' },
        { title: '最大吨数', num: true, render: r => fmtQty(r.max_qty) },
        { title: '优选', render: r => r.is_preferred ? el('span', { class: 'tag tag-orange' }, '★') : '-' },
        { title: '状态', render: r => tag(r.status) },
        { title: '操作', render: r => el('div', { style: { display: 'flex', gap: '0', whiteSpace: 'nowrap' } }, [
          r.status === 'ON_SHELF' ? el('button', { class: 'btn btn-sm btn-link', style: { color: 'var(--red)' }, onclick: () => forceOff(r) }, '强制下架') : null,
          el('button', { class: 'btn btn-sm btn-link', onclick: () => prefer(r, !r.is_preferred) },
            r.is_preferred ? '取消优选' : (r.status === 'ON_SHELF' ? '标优选' : null) || '标优选')
        ]) }
      ],
      toolbar: { render: () => [supIn, catSel, statusSel, el('span', { class: 'fb-sep' }), exportBtn] },
      query: state, rowKey: 'resource_id',
      fetch: q => API.get('/api/admin/resource/list', q)
    });
    root.appendChild(el('div', { class: 'card' }, [table.root]));

    function forceOff(r) {
      UI.form({
        title: `强制下架 · ${r.company_name} ${dictName(App.dict('ORE_CATEGORY'), r.ore_category)}`,
        fields: [{ key: 'reason', label: '下架原因', type: 'textarea', required: true, full: true, hint: '将展示给供方' }],
        submitText: '确认强制下架',
        onSubmit: async v => {
          await API.post(`/api/admin/resource/${r.resource_id}/force_off`, v);
          Toast.success('已强制下架');
          table.reload();
        }
      });
    }

    async function prefer(r, flag) {
      await confirmDialog(flag ? `确认将「${r.company_name} · ${dictName(App.dict('ORE_CATEGORY'), r.ore_category)}」标记为优选货源？`
                              : '确认取消优选标记？', async () => {
        await API.post(`/api/admin/resource/${r.resource_id}/prefer`, { is_preferred: flag });
        Toast.success('操作成功');
        table.reload();
      });
    }
  }
});
