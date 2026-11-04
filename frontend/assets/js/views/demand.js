/* ============ 需求申报模块视图 (PRD-02) ============ */

/* ---------- R1 采购需求管理 ---------- */
App.registerView('r1.demand', {
  title: '采购需求管理', roles: ['R1'],
  async render(root) {
    const state = { period: '', ore_category: '', status: '' };
    const periodIn = el('input', { type: 'text', placeholder: '周期 如 2026-01' });
    periodIn.addEventListener('input', debounce(() => { state.period = periodIn.value.trim(); table.reload(); }, 300));
    const catSel = el('select', null, [el('option', { value: '' }, '全部品类'),
      ...App.dict('ORE_CATEGORY').map(d => el('option', { value: d.item_code }, d.item_name))]);
    catSel.addEventListener('change', () => { state.ore_category = catSel.value; table.reload(); });
    const statusSel = el('select', null, [el('option', { value: '' }, '全部状态'),
      ...['DRAFT', 'SUBMITTED', 'IN_PROCESS', 'IN_LIST', 'IN_EXEC', 'DISTRIBUTED'].map(s => el('option', { value: s }, TAG_MAP[s][0]))]);
    statusSel.addEventListener('change', () => { state.status = statusSel.value; table.reload(); });
    const newBtn = el('button', { class: 'btn btn-primary btn-sm', onclick: () => showForm(null) }, '+ 新增申报');

    const table = UI.table({
      columns: [
        { title: '申报周期', render: r => `${TAG_MAP[r.period_type][0]} ${r.period}`, strong: true },
        { title: '矿石品类', render: r => dictName(App.dict('ORE_CATEGORY'), r.ore_category) },
        { title: '申报吨数', num: true, render: r => fmtQty(r.quantity) + ' 吨' },
        { title: '品位要求', key: 'grade_req' },
        { title: '期望到货', render: r => fmtDate(r.expected_arrival) },
        { title: '状态', render: r => tag(r.status) },
        { title: '更新时间', render: r => fmtTime(r.update_time) },
        { title: '操作', render: r => el('div', { style: { display: 'flex', gap: '0', flexWrap: 'wrap' } }, [
          el('button', { class: 'btn btn-sm btn-link', onclick: () => showDetail(r) }, '详情'),
          r.status === 'DRAFT' ? el('button', { class: 'btn btn-sm btn-link', onclick: () => showForm(r) }, '编辑') : null,
          r.status === 'DRAFT' ? el('button', { class: 'btn btn-sm btn-link', style: { color: 'var(--green)' }, onclick: () => doSubmit(r) }, '提交') : null,
          r.status === 'DRAFT' ? el('button', { class: 'btn btn-sm btn-link', style: { color: 'var(--red)' }, onclick: () => doDelete(r) }, '删除') : null,
          !['DRAFT', 'CANCELLED'].includes(r.status) ? el('button', { class: 'btn btn-sm btn-link', style: { color: 'var(--orange)' }, onclick: () => showChange(r) }, '变更申请') : null
        ]) }
      ],
      toolbar: { render: () => [periodIn, catSel, statusSel, el('span', { class: 'fb-sep' }), newBtn] },
      query: state, rowKey: 'demand_id',
      fetch: q => API.get('/api/demand/list', q)
    });
    root.appendChild(el('div', { class: 'card' }, [table.root]));

    function catOptions() { return App.dict('ORE_CATEGORY').map(d => ({ value: d.item_code, label: d.item_name })); }

    /* 双按钮表单：保存草稿 / 保存并提交 */
    async function showForm(row) {
      const isEdit = !!row;
      const fields = buildDemandForm(row);
      UI.formDual({
        title: isEdit ? '编辑采购需求申报（草稿）' : '新增采购需求申报',
        fields,
        wide: true,
        buttons: [
          { text: '保存草稿', action: 'draft' },
          { text: '保存并提交', action: 'submit', primary: true }
        ],
        onSubmit: async (values, action) => {
          const payload = { ...values, action };
          payload.attachments = (values.attachments || []).map(f => ({ file_url: f.file_url, file_name: f.file_name }));
          if (isEdit) await API.put(`/api/demand/${row.demand_id}`, payload);
          else await API.post('/api/demand/create', payload);
          Toast.success(action === 'draft' ? '草稿已保存' : '提交成功');
          table.reload();
        }
      });
    }

    function buildDemandForm(row) {
      return [
        { key: 'period_type', label: '申报周期类型', type: 'select', required: true,
          options: App.dict('PERIOD_TYPE').map(d => ({ value: d.item_code, label: d.item_name })),
          value: row ? row.period_type : 'MONTH' },
        { key: 'period', label: '申报周期', type: 'text', required: true, value: row ? row.period : '',
          placeholder: '月度 2026-01 / 季度 2026-Q1', hint: '月度 YYYY-MM；季度 YYYY-Qn' },
        { key: 'ore_category', label: '矿石品类', type: 'select', required: true, options: catOptions(), value: row ? row.ore_category : '' },
        { key: 'quantity', label: '采购数量（吨）', type: 'number', required: true, value: row ? row.quantity : '', hint: '大于0，保留2位小数' },
        { key: 'grade_req', label: '品位要求', type: 'text', required: true, value: row ? row.grade_req : '', placeholder: '如 TFe>=62%' },
        { key: 'granularity_req', label: '粒度要求', type: 'text', value: row ? row.granularity_req : '' },
        { key: 'moisture_req', label: '水分要求(%)', type: 'text', value: row ? row.moisture_req : '' },
        { key: 'impurity_req', label: '杂质要求', type: 'text', value: row ? row.impurity_req : '', placeholder: '硫、磷等指标' },
        { key: 'expected_arrival', label: '期望到货时间', type: 'date', required: true, value: row ? row.expected_arrival : '' },
        { key: 'delivery_place', label: '交货地点', type: 'text', value: row ? row.delivery_place : '' },
        { key: 'remark', label: '备注', type: 'textarea', full: true, value: row ? row.remark : '', maxlength: 500 },
        { key: 'attachments', label: '附件', type: 'file', full: true, value: row ? [] : [] }
      ];
    }

    async function doSubmit(r) {
      await confirmDialog(`确认提交申报 ${r.period} ${dictName(App.dict('ORE_CATEGORY'), r.ore_category)} ${fmtQty(r.quantity)}吨？提交后不可自行修改。`, async () => {
        await API.post(`/api/demand/${r.demand_id}/submit`);
        Toast.success('提交成功');
        table.reload();
      });
    }

    async function doDelete(r) {
      await confirmDialog('确认删除该草稿？', async () => {
        await API.post(`/api/demand/${r.demand_id}/delete`);
        Toast.success('删除成功');
        table.reload();
      }, { danger: true });
    }

    function showChange(r) {
      UI.form({
        title: `变更申请 · ${r.period} ${dictName(App.dict('ORE_CATEGORY'), r.ore_category)}`,
        fields: [
          { key: 'change_type', label: '变更类型', type: 'select', required: true,
            options: [{ value: 'QTY', label: '数量变更' }, { value: 'SPEC', label: '规格变更' }, { value: 'CANCEL', label: '取消需求' }] },
          { key: 'new_quantity', label: '新数量（吨）', type: 'number', hint: '仅数量变更时填写' },
          { key: 'change_desc', label: '变更说明', type: 'textarea', required: true, full: true },
          { key: 'attachment_url', label: '附件', type: 'file', full: true }
        ],
        submitText: '提交变更',
        onSubmit: async v => {
          const payload = {
            change_type: v.change_type, change_desc: v.change_desc,
            new_quantity: v.change_type === 'QTY' ? v.new_quantity : null,
            attachment_url: (v.attachment_url && v.attachment_url[0]) ? v.attachment_url[0].file_url : null,
            file_name: (v.attachment_url && v.attachment_url[0]) ? v.attachment_url[0].file_name : null
          };
          await API.post(`/api/demand/${r.demand_id}/change`, payload);
          Toast.success('变更申请已提交，待平台处理');
          table.reload();
        }
      });
    }

    async function showDetail(r) {
      const d = await API.get(`/api/demand/${r.demand_id}`);
      const sections = [{
        title: '申报信息', items: [
          { label: '申报单号', value: d.demand_no },
          { label: '所属企业', value: d.company_name },
          { label: '申报周期', value: `${TAG_MAP[d.period_type][0]} ${d.period}` },
          { label: '矿石品类', value: dictName(App.dict('ORE_CATEGORY'), d.ore_category) },
          { label: '申报吨数', value: fmtQty(d.quantity) + ' 吨' },
          { label: '品位要求', value: d.grade_req },
          { label: '粒度要求', value: d.granularity_req || '-' },
          { label: '水分要求', value: d.moisture_req || '-' },
          { label: '杂质要求', value: d.impurity_req || '-' },
          { label: '期望到货', value: fmtDate(d.expected_arrival) },
          { label: '交货地点', value: d.delivery_place || '-' },
          { label: '状态', render: () => tag(d.status) },
          { label: '备注', value: d.remark || '-', full: true },
          { label: '附件', full: true, render: () => fileLinks(d.attachments) }
        ]
      }];
      if (d.changes.length) {
        sections.push({ title: '变更记录', items: d.changes.map(c => ({
          label: `${TAG_MAP[c.change_type][0]} · ${fmtTime(c.create_time)}`,
          full: true, render: () => el('span', null, [tag(c.status), ` ${c.change_desc}`])
        })) });
      }
      UI.detail({ title: '申报详情', sections, wide: true });
    }
  }
});

/* ---------- R4 需求归集 ---------- */
App.registerView('r4.demand', {
  title: '需求归集', roles: ['R4'],
  async render(root) {
    const tab = el('div', { style: { display: 'flex', gap: '8px', marginBottom: '14px' } });
    const viewKey = { demand: '需求列表', change: '变更申请审核' };
    let curTab = sessionStorage.getItem('r4.demand.tab') || 'demand';
    const container = el('div', null);

    function renderTabs() {
      tab.innerHTML = '';
      Object.entries(viewKey).forEach(([k, t]) => {
        tab.appendChild(el('button', {
          class: `btn btn-sm ${curTab === k ? 'btn-primary' : ''}`,
          onclick: () => { curTab = k; sessionStorage.setItem('r4.demand.tab', k); renderTabs(); renderBody(); }
        }, t));
      });
    }

    function renderBody() {
      container.innerHTML = '';
      container.appendChild(curTab === 'demand' ? renderDemandTable() : renderChangeTable());
    }

    function renderDemandTable() {
      const state = { period: '', company: '', ore_category: '', status: '' };
      const periodIn = el('input', { type: 'text', placeholder: '周期 如 2026-01' });
      periodIn.addEventListener('input', debounce(() => { state.period = periodIn.value.trim(); table.reload(); }, 300));
      const compIn = el('input', { type: 'text', placeholder: '企业名称' });
      compIn.addEventListener('input', debounce(() => { state.company = compIn.value.trim(); table.reload(); }, 300));
      const catSel = el('select', null, [el('option', { value: '' }, '全部品类'),
        ...App.dict('ORE_CATEGORY').map(d => el('option', { value: d.item_code }, d.item_name))]);
      catSel.addEventListener('change', () => { state.ore_category = catSel.value; table.reload(); });
      const statusSel = el('select', null, [el('option', { value: '' }, '全部状态'),
        ...['DRAFT', 'SUBMITTED', 'IN_PROCESS', 'IN_LIST', 'IN_EXEC', 'DISTRIBUTED', 'CANCELLED'].map(s => el('option', { value: s }, TAG_MAP[s][0]))]);
      statusSel.addEventListener('change', () => { state.status = statusSel.value; table.reload(); });
      const genBtn = el('button', { class: 'btn btn-primary btn-sm', onclick: showGenerate }, '⚙ 生成集采清单');

      const table = UI.table({
        columns: [
          { title: '周期', render: r => `${TAG_MAP[r.period_type][0]} ${r.period}`, strong: true },
          { title: '企业', key: 'company_name' },
          { title: '品类', render: r => dictName(App.dict('ORE_CATEGORY'), r.ore_category) },
          { title: '吨数', num: true, render: r => fmtQty(r.quantity) },
          { title: '品位', key: 'grade_req' },
          { title: '状态', render: r => tag(r.status) },
          { title: '提交时间', render: r => fmtTime(r.create_time) },
          { title: '操作', render: r => el('button', { class: 'btn btn-sm btn-link', onclick: () => UI.detail({
              title: `申报详情 · ${r.company_name}`,
              sections: [{ title: '申报信息', items: [
                { label: '申报单号', value: r.demand_no }, { label: '品类', value: dictName(App.dict('ORE_CATEGORY'), r.ore_category) },
                { label: '吨数', value: fmtQty(r.quantity) + ' 吨' }, { label: '品位', value: r.grade_req },
                { label: '粒度', value: r.granularity_req || '-' }, { label: '水分', value: r.moisture_req || '-' },
                { label: '杂质', value: r.impurity_req || '-' }, { label: '期望到货', value: fmtDate(r.expected_arrival) },
                { label: '交货地点', value: r.delivery_place || '-' }, { label: '状态', render: () => tag(r.status) },
                { label: '备注', value: r.remark || '-', full: true }] }] }) }, '详情') }
        ],
        toolbar: { render: () => [periodIn, compIn, catSel, statusSel, el('span', { class: 'fb-sep' }), genBtn] },
        query: state, rowKey: 'demand_id',
        fetch: q => API.get('/api/admin/demand/list', q)
      });
      const wrap = el('div', { class: 'card' }, [table.root]);
      return wrap;

      async function showGenerate() {
        const periodType = UI.form;
        UI.form({
          title: '生成集采清单',
          fields: [
            { key: 'period_type', label: '周期类型', type: 'select', required: true,
              options: App.dict('PERIOD_TYPE').map(d => ({ value: d.item_code, label: d.item_name })) },
            { key: 'period', label: '周期', type: 'text', required: true, placeholder: '如 2026-01 / 2026-Q1',
              hint: '系统将该周期下「已提交/归集处理中」需求按品类归集为集采清单' }
          ],
          submitText: '生成',
          onSubmit: async v => {
            const res = await API.post('/api/admin/collective/create', v);
            Toast.success(res.message || '生成成功');
            table.reload();
            const lists = el('div', null, res.lists.map(l => el('div', { style: { padding: '6px 0', borderBottom: '1px solid var(--border-1)' } },
              `${l.ore_category}：${fmtQty(l.total_qty)} 吨（${l.detail_count} 家企业）`)));
            openModal({ title: '生成结果', body: lists, footer: c => [el('button', { class: 'btn btn-primary', onclick: c }, '好的')] });
          }
        });
      }
    }

    function renderChangeTable() {
      const state = { status: 'PENDING' };
      const statusSel = el('select', null, [el('option', { value: 'PENDING' }, '待处理'),
        el('option', { value: 'AGREED' }, '已同意'), el('option', { value: 'REJECTED' }, '已驳回')]);
      statusSel.addEventListener('change', () => { state.status = statusSel.value; table.reload(); });
      const table = UI.table({
        columns: [
          { title: '申报单号', key: 'demand_no', strong: true },
          { title: '企业', key: 'company_name' },
          { title: '变更类型', render: r => tag(r.change_type) },
          { title: '变更说明', render: r => el('span', { title: r.change_desc }, String(r.change_desc).slice(0, 20) + (String(r.change_desc).length > 20 ? '…' : '')) },
          { title: '新数量', render: r => r.new_quantity ? fmtQty(r.new_quantity) + ' 吨（原 ' + fmtQty(r.old_qty) + '）' : '-' },
          { title: '状态', render: r => tag(r.status) },
          { title: '申请时间', render: r => fmtTime(r.create_time) },
          { title: '操作', render: r => r.status === 'PENDING' ? el('button', { class: 'btn btn-sm btn-link', onclick: () => review(r) }, '处理') : '-' }
        ],
        toolbar: { render: () => [statusSel] },
        query: state, rowKey: 'id',
        fetch: q => API.get('/api/admin/demand/change/list', q)
      });
      return el('div', { class: 'card' }, [table.root]);

      function review(r) {
        UI.form({
          title: `变更审核 · ${r.demand_no}`,
          fields: [
            { key: 'result', label: '处理结论', type: 'select', required: true,
              options: [{ value: 'AGREED', label: '同意变更' }, { value: 'REJECTED', label: '驳回' }] },
            { key: 'review_remark', label: '处理备注', type: 'text' }
          ],
          submitText: '提交',
          onSubmit: async v => {
            await API.post(`/api/admin/demand/change/${r.id}/review`, v);
            Toast.success('处理完成');
            table.reload();
          }
        });
      }
    }

    renderTabs();
    renderBody();
    root.appendChild(tab);
    root.appendChild(container);
  }
});

/* ---------- R4 集采清单 ---------- */
App.registerView('r4.list', {
  title: '集采清单', roles: ['R4'],
  async render(root) {
    const state = { period: '' };
    const periodIn = el('input', { type: 'text', placeholder: '周期 如 2026-01' });
    periodIn.addEventListener('input', debounce(() => { state.period = periodIn.value.trim(); table.reload(); }, 300));
    const exportBtn = el('button', { class: 'btn btn-primary btn-sm', onclick: () => API.download('/api/admin/collective/export', {}, '集采清单导出.xlsx') }, '⬇ 导出全部清单');

    const table = UI.table({
      columns: [
        { title: '清单编号', key: 'list_no', strong: true },
        { title: '周期', render: r => `${TAG_MAP[r.period_type][0]} ${r.period}` },
        { title: '品类', render: r => r.ore_categories.map(c => dictName(App.dict('ORE_CATEGORY'), c)).join('、') },
        { title: '总需求吨数', num: true, render: r => fmtQty(r.total_qty) + ' 吨' },
        { title: '企业明细数', render: r => r.detail_count + ' 家' },
        { title: '状态', render: r => tag(r.status) },
        { title: '生成时间', render: r => fmtTime(r.create_time) },
        { title: '操作', render: r => el('button', { class: 'btn btn-sm btn-link', onclick: () => showDetail(r) }, '查看明细') }
      ],
      toolbar: { render: () => [periodIn, el('span', { class: 'fb-sep' }), exportBtn] },
      query: state, rowKey: 'list_id',
      fetch: q => API.get('/api/admin/collective/list', q)
    });
    root.appendChild(el('div', { class: 'card' }, [table.root]));

    async function showDetail(r) {
      const d = await API.get(`/api/admin/collective/${r.list_id}`);
      UI.detail({
        title: `集采清单 · ${d.list_no}`,
        wide: true,
        sections: [
          { title: '汇总', items: [
            { label: '清单编号', value: d.list_no },
            { label: '周期', value: `${TAG_MAP[d.period_type][0]} ${d.period}` },
            { label: '总需求吨数', value: fmtQty(d.total_qty) + ' 吨' },
            { label: '生成时间', value: fmtTime(d.create_time) }
          ] },
          { title: '各企业申报明细', items: [
            { label: '明细', full: true, render: () => {
              const tb = el('table', { class: 'tb' }, [
                el('thead', null, el('tr', null, ['企业', '品类', '吨数', '品位要求', '期望到货'].map(h => el('th', null, h)))),
                el('tbody', null, d.details.map(x => el('tr', null, [
                  el('td', null, x.company_name), el('td', null, dictName(App.dict('ORE_CATEGORY'), x.ore_category)),
                  el('td', { class: 'num' }, fmtQty(x.qty)), el('td', null, x.grade_req || '-'),
                  el('td', null, fmtDate(x.expected_arrival))
                ])))
              ]);
              return el('div', { class: 'table-wrap' }, tb);
            } }
          ] }
        ]
      });
    }
  }
});
