/* ============ 矿石质检&化验管理 (PRD-09)：R4审核/规则 + R3录入 + R2预检 + R1查看 ============ */

const REPORT_TYPES_EXT = { 1: '货源预检', 2: '到港船检', 3: '仓内抽检', 4: '分拨出库检' };

function inspectStatusTag(s) {
  const map = { DRAFT: ['草稿', 'gray'], PENDING: ['待审核', 'orange'], APPROVED: ['已通过', 'green'],
    REJECTED: ['已驳回', 'red'], REDBACKED: ['已红冲', 'red'] };
  const [n, c] = map[s] || [s, 'gray'];
  return el('span', { class: `tag tag-${c}` }, n);
}

/* 化验单表单（自定义模态）：类型联动 + 动态指标行 + 保存草稿/提交审核双按钮 */
function inspectForm({ title, mode, defaults, onSubmit }) {
  const F = (label, input, hint, req) => el('div', { class: 'field' }, [
    el('label', null, [label, req ? el('span', { class: 'req' }, '*') : null]), input,
    hint ? el('div', { class: 'hint' }, hint) : null
  ]);
  const mk = (v, ph, type) => { const i = el('input', { type: type || 'text', placeholder: ph }); if (v != null && v !== '') i.value = v; return i; };

  const typeSel = el('select', null, Object.entries(REPORT_TYPES_EXT).map(([v, l]) =>
    el('option', { value: v, selected: Number(v) === Number(defaults.report_type || (mode === 'source' ? 1 : 2)) }, l)));
  const linkInp = mk(defaults.source_id || defaults.order_id || defaults.alloc_id || '',
    mode === 'source' ? '关联货源' : mode === 'order' ? '关联集采订单' : '关联分拨单', 'number');
  const orgInp = mk(defaults.inspect_org, '化验机构');
  const sampleInp = mk(defaults.sample_date, '', 'date');
  const testInp = mk(defaults.test_date, '', 'date');
  const wetInp = mk(defaults.wet_ton, '湿基吨数', 'number');
  const placeInp = mk(defaults.sample_place, '采样地点');
  const batchInp = mk(defaults.batch_no, '批次号');
  const conclInp = mk(defaults.conclusion, '化验结论');
  const remarkInp = mk(defaults.remark, '备注');
  const fileStore = { files: [] };
  const filesBox = el('div', { class: 'file-list' });

  const grid = el('div', { class: 'form-grid' }, [
    F('化验单类型', typeSel, mode === 'source' ? '货源预检：仅供方/平台' : mode === 'order' ? '到港船检：仅化验机构/平台' : '仓检/出库检', true),
    F(mode === 'source' ? '货源编号' : mode === 'order' ? '集采订单' : '分拨单编号', linkInp, null, true),
    F('化验机构', orgInp), F('采样日期', sampleInp), F('化验日期', testInp),
    F('湿基吨数', wetInp, '留空则不参与结算扣减计算'),
    F('采样地点', placeInp), F('批次号', batchInp), F('化验结论', conclInp), F('备注', remarkInp),
    F('检测报告附件', (() => {
      const box = el('div', { class: 'upload-box' }, '点击上传附件（PDF/图片）');
      const fi = el('input', { type: 'file', multiple: true, style: { display: 'none' } });
      box.addEventListener('click', () => fi.click());
      fi.addEventListener('change', async () => {
        if (!fi.files.length) return;
        try {
          const ups = await API.upload(Array.from(fi.files));
          fileStore.files.push(...ups);
          renderFiles();
          Toast.success('上传成功');
        } catch (e) { /* toast 已提示 */ }
        fi.value = '';
      });
      function renderFiles() {
        filesBox.innerHTML = '';
        fileStore.files.forEach((x, i) => filesBox.appendChild(el('div', { class: 'file-item' }, [
          el('span', null, '📄'), el('span', { class: 'fi-name' }, x.file_name || x.file_url),
          el('span', { class: 'fi-del', onclick: () => { fileStore.files.splice(i, 1); renderFiles(); } }, '删除')
        ])));
      }
      renderFiles();
      const wrap = el('div', null, [box, filesBox]);
      wrap.insertBefore(fi, box);
      return wrap;
    })(), null, false)
  ]);

  // 动态指标行区
  const idxBox = el('div', { style: { marginTop: '10px' } });
  const addIdxRow = (name, value, unit) => {
    const row = el('div', { style: { display: 'flex', gap: '8px', marginBottom: '6px' } }, [
      Object.assign(mk(name, '指标名称'), { className: 'ipt idx-name', style: { flex: '1' } }),
      Object.assign(mk(value, '指标值'), { style: { flex: '1' } }),
      Object.assign(mk(unit, '单位'), { style: { width: '80px' } }),
      el('button', { class: 'btn btn-sm', type: 'button', onclick: () => row.remove() }, '×')
    ]);
    idxBox.appendChild(row);
  };
  (async () => {
    let rows = [];
    try { rows = (await API.get('/api/indicator/template/IRON') || []).map(t => ({ name: t.field_label, unit: t.unit })); } catch (e) { /* 忽略 */ }
    if (!rows.length) rows = [{ name: '水分', unit: '%' }, { name: '品位', unit: '%' }, { name: '杂质', unit: '%' }];
    rows.forEach(r => addIdxRow(r.name, '', r.unit));
    idxBox.appendChild(el('button', { class: 'btn btn-sm', type: 'button', onclick: () => addIdxRow('', '', '') }, '+ 增加指标'));
  })();

  const collect = (submit) => {
    const linkKey = mode === 'source' ? 'source_id' : mode === 'order' ? 'order_id' : 'alloc_id';
    const linkVal = linkInp.value.trim();
    if (!linkVal) { Toast.error('请填写关联单据编号'); return null; }
    const indexes = [...idxBox.querySelectorAll('div[style]')].map(row => {
      const ins = row.querySelectorAll('input');
      return ins.length >= 2 ? { index_name: ins[0].value.trim(), index_value: ins[1].value.trim(), index_unit: ins[2] ? ins[2].value.trim() : '' } : null;
    }).filter(x => x && x.index_name);
    return {
      report_id: defaults.report_id || null,
      report_type: Number(typeSel.value), [linkKey]: Number(linkVal),
      inspect_org: orgInp.value.trim(), sample_date: sampleInp.value, test_date: testInp.value,
      wet_ton: wetInp.value === '' ? null : Number(wetInp.value),
      sample_place: placeInp.value.trim(), batch_no: batchInp.value.trim(),
      conclusion: conclInp.value.trim(), remark: remarkInp.value.trim(),
      attachment_url: fileStore.files[0]?.file_url || null, file_name: fileStore.files[0]?.file_name || null,
      indexes, submit
    };
  };

  const md = openModal({
    title, wide: true,
    body: el('div', null, [
      grid,
      el('div', { class: 'field full' }, [el('label', null, '化验指标明细'), idxBox])
    ]),
    footer: close => [
      el('button', { class: 'btn', onclick: close }, '取消'),
      el('button', { class: 'btn', onclick: async () => {
        const v = collect(false);
        if (!v) return;
        try { await onSubmit(v); close(); } catch (e) { /* toast 已提示 */ }
      } }, '保存草稿'),
      el('button', { class: 'btn btn-primary', onclick: async () => {
        const v = collect(true);
        if (!v) return;
        try { await onSubmit(v); close(); } catch (e) { /* toast 已提示 */ }
      } }, '保存并提交审核')
    ]
  });
  return md;
}

/* ---------- R4 化验质检管理（台账 + 审核规则） ---------- */
App.registerView('r4.inspect', {
  title: '化验质检管理', roles: ['R4'],
  async render(root) {
    const tab = el('div', { style: { display: 'flex', gap: '8px', marginBottom: '14px' } });
    const body = el('div');
    let current = 'list';
    const renderTab = () => {
      tab.innerHTML = ''; body.innerHTML = '';
      [['list', '化验单台账'], ['rule', '扣水扣杂规则']].forEach(([k, t]) => {
        tab.appendChild(el('button', { class: `btn btn-sm ${current === k ? 'btn-primary' : ''}`,
          onclick: () => { current = k; renderTab(); } }, t));
      });
      if (current === 'list') renderList(); else renderRules();
    };

    function renderList() {
      const state = { report_type: '', status: '', start_date: '', end_date: '' };
      const typeSel = el('select', null, [el('option', { value: '' }, '全部类型'),
        ...Object.entries(REPORT_TYPES_EXT).map(([v, l]) => el('option', { value: v }, l))]);
      typeSel.addEventListener('change', () => { state.report_type = typeSel.value; table.reload(); });
      const stSel = el('select', null, [el('option', { value: '' }, '全部状态'),
        ...['DRAFT', 'PENDING', 'APPROVED', 'REJECTED'].map(v => el('option', { value: v }, inspectStatusTag(v).textContent))]);
      stSel.addEventListener('change', () => { state.status = stSel.value; table.reload(); });
      const exportBtn = el('button', { class: 'btn btn-sm', onclick: () => API.download('/api/inspect/report/export', state) }, '导出台账');

      const table = UI.table({
        columns: [
          { title: '化验单号', key: 'report_no', strong: true },
          { title: '类型', render: r => REPORT_TYPES_EXT[r.report_type] },
          { title: '品类', render: r => dictName(App.dict('ORE_CATEGORY'), r.ore_category) },
          { title: '化验机构', render: r => r.inspect_org || '-' },
          { title: '湿基/结算吨', render: r => `${r.wet_ton ?? '-'} / ${r.settle_ton ?? '-'}` },
          { title: '扣减(吨)', render: r => el('span', { style: { color: 'var(--orange)' } }, r.deduct_ton || 0) },
          { title: '状态', render: r => inspectStatusTag(r.status) },
          { title: '操作', render: r => el('div', { style: { display: 'flex', gap: '2px' } }, [
            el('button', { class: 'btn btn-sm btn-link', onclick: () => showDetail(r.report_id) }, '详情'),
            r.status === 'PENDING' ? el('button', { class: 'btn btn-sm btn-link', onclick: () => doAudit(r) }, '审核') : null
          ]) }
        ],
        toolbar: { render: () => [typeSel, stSel, el('span', { class: 'fb-sep' }), exportBtn] },
        query: state, rowKey: 'report_id',
        fetch: q => API.get('/api/inspect/report/list', q)
      });
      body.appendChild(el('div', { class: 'card' }, [table.root]));
    }

    async function showDetail(rid) {
      const d = await API.get(`/api/inspect/report/detail?report_id=${rid}`);
      UI.detail({
        title: `化验单 · ${d.report_no}`,
        sections: [
          { title: '基本信息', items: [
            { label: '类型', value: REPORT_TYPES_EXT[d.report_type] },
            { label: '品类', value: dictName(App.dict('ORE_CATEGORY'), d.ore_category) },
            { label: '化验机构', value: d.inspect_org || '-' },
            { label: '采样/化验日期', value: `${d.sample_date || '-'} ~ ${d.test_date || '-'}` },
            { label: '湿基吨数', value: d.wet_ton ?? '-' },
            { label: '扣减吨数', value: d.deduct_ton ?? 0 },
            { label: '结算干基吨数', value: d.settle_ton ?? '-', strong: true },
            { label: '结论', value: d.conclusion || '-' },
            { label: '状态', render: () => inspectStatusTag(d.status) },
            d.reject_reason ? { label: '驳回原因', value: d.reject_reason, full: true } : null
          ].filter(Boolean) },
          { title: '化验指标', items: [
            { label: '指标明细', full: true, render: () => el('table', { class: 'tb' }, [
              el('thead', null, el('tr', null, ['指标', '数值', '单位'].map(h => el('th', null, h)))),
              el('tbody', null, d.indexes.map(i => el('tr', null, [
                el('td', null, i.index_name), el('td', null, i.index_value || '-'), el('td', null, i.index_unit || '-')
              ])))
            ]) }
          ] }
        ]
      });
    }

    function doAudit(r) {
      UI.form({
        title: `化验单审核 · ${r.report_no}`,
        fields: [
          { key: 'result', label: '审核结论', type: 'select', required: true,
            options: [{ value: 'APPROVED', label: '审核通过' }, { value: 'REJECTED', label: '驳回' }] },
          { key: 'reject_reason', label: '驳回原因', type: 'text', hint: '驳回时必填' }
        ],
        submitText: '提交',
        onSubmit: async v => {
          if (v.result === 'REJECTED' && !v.reject_reason.trim()) { Toast.error('驳回必须填写原因'); throw new Error(''); }
          await API.post('/api/inspect/report/audit', { report_id: r.report_id, ...v });
          Toast.success('审核完成');
          table.reload();
        }
      });
    }

    function renderRules() {
      const state = { ore_category: '' };
      const catSel = el('select', null, [el('option', { value: '' }, '全部品类'),
        ...(App.dict('ORE_CATEGORY') || []).map(d => el('option', { value: d.item_code }, d.item_name))]);
      catSel.addEventListener('change', () => { state.ore_category = catSel.value; table.reload(); });

      const table = UI.table({
        columns: [
          { title: '规则名称', key: 'rule_name', strong: true },
          { title: '品类', render: r => dictName(App.dict('ORE_CATEGORY'), r.ore_category) },
          { title: '指标', key: 'index_name' },
          { title: '阈值', key: 'threshold', num: true },
          { title: '扣减比例(%)', key: 'deduct_rate', num: true },
          { title: '状态', render: r => r.status ? tag('APPROVED') : tag('DISABLED') },
          { title: '操作', render: r => el('div', { style: { display: 'flex', gap: '2px' } }, [
            el('button', { class: 'btn btn-sm btn-link', onclick: () => editRule(r) }, '编辑'),
            el('button', { class: 'btn btn-sm btn-link', onclick: () => toggleRule(r) }, r.status ? '停用' : '启用')
          ]) }
        ],
        toolbar: { render: () => [catSel, el('span', { class: 'fb-sep' }),
          el('button', { class: 'btn btn-primary btn-sm', onclick: () => editRule(null) }, '+ 新增规则')] },
        query: state, rowKey: 'rule_id',
        fetch: q => API.get('/api/inspect/rule/list', q)
      });
      body.appendChild(el('div', { class: 'card' }, [table.root]));

      function editRule(r) {
        UI.form({
          title: r ? '编辑扣减规则' : '新增扣减规则',
          fields: [
            { key: 'rule_name', label: '规则名称', type: 'text', required: true, value: r?.rule_name || '' },
            { key: 'ore_category', label: '矿石品类', type: 'text', required: true, value: r?.ore_category || '', hint: '如 IRON' },
            { key: 'index_name', label: '指标名称', type: 'text', required: true, value: r?.index_name || '', hint: '需与化验单指标名一致' },
            { key: 'threshold', label: '阈值', type: 'number', step: '0.01', required: true, value: r?.threshold ?? '' },
            { key: 'deduct_rate', label: '扣减比例(%)', type: 'number', step: '0.01', required: true, value: r?.deduct_rate ?? '' }
          ],
          submitText: '保存',
          onSubmit: async v => {
            await API.post('/api/inspect/rule/save', { ...v, rule_id: r?.rule_id });
            Toast.success('保存成功');
            table.reload();
          }
        });
      }
      async function toggleRule(r) {
        await API.post(`/api/inspect/rule/${r.rule_id}/toggle`);
        Toast.success('操作成功');
        table.reload();
      }
    }

    renderTab();
    root.appendChild(el('div', null, [tab, body]));
  }
});

/* ---------- R3 化验录入 ---------- */
App.registerView('r3.inspect', {
  title: '化验数据录入', roles: ['R3'],
  async render(root) {
    const createBtn = el('button', { class: 'btn btn-primary btn-sm',
      onclick: () => inspectForm({
        title: '新建化验单', mode: 'order', defaults: {},
        onSubmit: async (v, extra) => {
          await API.post('/api/inspect/report/save', { ...v, ...extra });
          Toast.success('化验单已保存');
          table.reload();
        }
      }) }, '+ 新建化验单');

    const table = UI.table({
      columns: [
        { title: '化验单号', key: 'report_no', strong: true },
        { title: '类型', render: r => REPORT_TYPES_EXT[r.report_type] },
        { title: '品类', render: r => dictName(App.dict('ORE_CATEGORY'), r.ore_category) },
        { title: '湿基/结算吨', render: r => `${r.wet_ton ?? '-'} / ${r.settle_ton ?? '-'}` },
        { title: '状态', render: r => inspectStatusTag(r.status) },
        { title: '操作', render: r => (r.status === 'DRAFT' || r.status === 'REJECTED')
          ? el('button', { class: 'btn btn-sm btn-link', onclick: () => {
              const mode = r.report_type === 1 ? 'source' : r.report_type === 2 ? 'order' : 'alloc';
              inspectForm({
                title: `编辑化验单 · ${r.report_no}`, mode,
                defaults: { ...r, report_type: r.report_type },
                onSubmit: async v => {
                  await API.post('/api/inspect/report/save', v);
                  Toast.success('化验单已更新');
                  table.reload();
                }
              });
            } }, '编辑')
          : el('span', null, '-') }
      ],
      toolbar: { render: () => [createBtn] },
      rowKey: 'report_id',
      fetch: q => API.get('/api/inspect/report/list', q)
    });
    root.appendChild(el('div', { class: 'card' }, [table.root]));
  }
});

/* ---------- R2 货源预检 ---------- */
App.registerView('r2.inspect', {
  title: '货源预检化验', roles: ['R2'],
  async render(root) {
    const createBtn = el('button', { class: 'btn btn-primary btn-sm',
      onclick: () => inspectForm({
        title: '新建货源预检单', mode: 'source', defaults: { report_type: 1 },
        onSubmit: async (v, extra) => {
          await API.post('/api/inspect/report/save', { ...v, ...extra, report_type: 1 });
          Toast.success('预检单已保存');
          table.reload();
        }
      }) }, '+ 新建预检单');

    const table = UI.table({
      columns: [
        { title: '化验单号', key: 'report_no', strong: true },
        { title: '关联货源', render: r => r.source_no || '-' },
        { title: '品类', render: r => dictName(App.dict('ORE_CATEGORY'), r.ore_category) },
        { title: '湿基/结算吨', render: r => `${r.wet_ton ?? '-'} / ${r.settle_ton ?? '-'}` },
        { title: '状态', render: r => inspectStatusTag(r.status) },
        { title: '创建时间', render: r => fmtTime(r.create_time) }
      ],
      toolbar: { render: () => [createBtn] },
      rowKey: 'report_id',
      fetch: q => API.get('/api/inspect/report/list', { ...q, report_type: 1 })
    });
    root.appendChild(el('div', { class: 'card' }, [table.root]));
  }
});

/* ---------- R1 化验单查看 ---------- */
App.registerView('r1.inspect', {
  title: '化验单查看', roles: ['R1'],
  async render(root) {
    const table = UI.table({
      columns: [
        { title: '化验单号', key: 'report_no', strong: true },
        { title: '类型', render: r => REPORT_TYPES_EXT[r.report_type] },
        { title: '分拨单', render: r => r.alloc_no || '-' },
        { title: '品类', render: r => dictName(App.dict('ORE_CATEGORY'), r.ore_category) },
        { title: '湿基/结算吨', render: r => `${r.wet_ton ?? '-'} / ${r.settle_ton ?? '-'}` },
        { title: '状态', render: r => inspectStatusTag(r.status) }
      ],
      rowKey: 'report_id',
      fetch: q => API.get('/api/inspect/report/list', q)
    });
    root.appendChild(el('div', { class: 'card' }, [table.root]));
  }
});
