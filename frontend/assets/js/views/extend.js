/* ============ 扩展视图：合同(PRD-10) 费用分摊(PRD-11) 消息预警(PRD-12) 报表大屏(PRD-13) 变更红冲(PRD-15) ============ */

/* ---------- R4 合同管理 ---------- */
App.registerView('r4.contract', {
  title: '合同台账', roles: ['R4'],
  async render(root) {
    const state = { contract_type: '', status: '', keyword: '' };
    const kw = el('input', { type: 'text', placeholder: '搜索合同编号 / 品类' });
    kw.addEventListener('input', debounce(() => { state.keyword = kw.value; table.reload(); }, 300));
    const typeSel = el('select', null, [el('option', { value: '' }, '全部类型'),
      el('option', { value: '1' }, '上游供货'), el('option', { value: '2' }, '下游分拨')]);
    typeSel.addEventListener('change', () => { state.contract_type = typeSel.value; table.reload(); });
    const stSel = el('select', null, [el('option', { value: '' }, '全部状态'),
      ...['DRAFT', 'PENDING_STAMP', 'EFFECTIVE', 'EXECUTING', 'FINISHED', 'TERMINATED'].map(v => el('option', { value: v }, v))]);
    stSel.addEventListener('change', () => { state.status = stSel.value; table.reload(); });

    const table = UI.table({
      columns: [
        { title: '合同编号', key: 'contract_no', strong: true },
        { title: '类型', render: r => r.contract_type === 1 ? tag('SUPPLIER') : tag('DOWNSTREAM') },
        { title: '相对方', key: 'enterprise_name' },
        { title: '品类', render: r => dictName(App.dict('ORE_CATEGORY'), r.ore_category) },
        { title: '吨数/金额', render: r => `${r.plan_ton ?? '-'}吨 / ¥${r.contract_amount ?? '-'}` },
        { title: '状态', render: r => tag(r.status) },
        { title: '到期日', render: r => r.expire_date || '-' },
        { title: '操作', render: r => el('div', { style: { display: 'flex', gap: '2px' } }, [
          el('button', { class: 'btn btn-sm btn-link', onclick: () => showDetail(r.contract_id) }, '详情'),
          r.status === 'DRAFT' ? el('button', { class: 'btn btn-sm btn-link', onclick: () => flow(r) }, '流转') : null,
          ['EFFECTIVE', 'EXECUTING'].includes(r.status) ? el('button', { class: 'btn btn-sm btn-link', onclick: () => addChange(r) }, '变更') : null
        ]) }
      ],
      toolbar: { render: () => [kw, typeSel, stSel, el('span', { class: 'fb-sep' }),
        el('button', { class: 'btn btn-sm', onclick: () => API.download('/api/contract/export', state) }, '导出'),
        el('button', { class: 'btn btn-primary btn-sm', onclick: () => editContract(null) }, '+ 新建合同')] },
      query: state, rowKey: 'contract_id',
      fetch: q => API.get('/api/contract/list', q)
    });
    root.appendChild(el('div', { class: 'card' }, [table.root]));

    function editContract(c) {
      UI.formDual({
        title: c ? `编辑合同草稿 · ${c.contract_no}` : '新建合同（默认草稿）',
        wide: true,
        fields: [
          { key: 'contract_type', label: '合同类型', type: 'select', required: true, value: c?.contract_type || 1,
            options: [{ value: 1, label: '上游供货合同（关联集采订单）' }, { value: 2, label: '下游分拨合同（关联分拨单）' }] },
          { key: 'order_id', label: '集采订单', type: 'number', value: c?.order_id ?? '', full: true, hint: '类型=上游供货时必填' },
          { key: 'alloc_id', label: '分拨单', type: 'number', value: c?.alloc_id ?? '', full: true, hint: '类型=下游分拨时必填' },
          { key: 'enterprise_id', label: '相对方企业ID', type: 'number', value: c?.enterprise_id ?? '', hint: '留空自动取关联单据主体' },
          { key: 'ore_category', label: '品类', type: 'text', value: c?.ore_category || '', hint: '留空自动取关联单据品类' },
          { key: 'plan_ton', label: '预估吨数', type: 'number', value: c?.plan_ton ?? '' },
          { key: 'unit_price', label: '单价', type: 'number', value: c?.unit_price ?? '' },
          { key: 'contract_amount', label: '合同金额', type: 'number', value: c?.contract_amount ?? '' },
          { key: 'sign_date', label: '签订日期', type: 'date', value: c?.sign_date || '' },
          { key: 'effective_date', label: '生效日期', type: 'date', value: c?.effective_date || '' },
          { key: 'expire_date', label: '到期日期', type: 'date', value: c?.expire_date || '' },
          { key: 'pay_remark', label: '付款条款', type: 'text', full: true },
          { key: 'remark', label: '备注', type: 'text', full: true }
        ],
        buttons: [{ text: '取消', action: 'cancel' }, { text: '保存草稿', action: 'save', primary: true }],
        onSubmit: async (v, action) => {
          if (action === 'cancel') return;
          await API.post('/api/contract/save', { ...v, contract_id: c?.contract_id });
          Toast.success('合同已保存');
          table.reload();
        }
      });
    }

    function flow(r) {
      const nextMap = { DRAFT: 'PENDING_STAMP', PENDING_STAMP: 'EFFECTIVE', EFFECTIVE: 'EXECUTING' };
      const next = nextMap[r.status];
      if (!next) { Toast.info('当前状态无可流转操作'); return; }
      const fields = [];
      if (next === 'EFFECTIVE') {
        fields.push({ key: 'stamp_no', label: '盖章编号', type: 'text', required: true },
          { key: 'effective_date', label: '生效日期', type: 'date', value: r.effective_date || '' });
      }
      UI.form({
        title: `合同流转 · ${r.contract_no}`,
        fields,
        submitText: `确认置为「${{ PENDING_STAMP: '待盖章', EFFECTIVE: '已生效', EXECUTING: '履约中' }[next]}」`,
        onSubmit: async v => {
          await API.post('/api/contract/status/update', { contract_id: r.contract_id, status: next, ...v });
          Toast.success('状态已更新');
          table.reload();
        }
      });
    }

    function addChange(r) {
      UI.form({
        title: `新增合同变更记录 · ${r.contract_no}`,
        wide: true,
        fields: [
          { key: 'change_content', label: '变更内容', type: 'textarea', required: true, full: true },
          { key: 'reason', label: '变更原因', type: 'text', full: true },
          { key: 'attachment_url', label: '补充协议附件', type: 'file', full: true }
        ],
        submitText: '提交变更记录',
        onSubmit: async v => {
          await API.post('/api/contract/change/add', { contract_id: r.contract_id, ...v });
          Toast.success('变更记录已添加');
          table.reload();
        }
      });
    }

    async function showDetail(cid) {
      const d = await API.get(`/api/contract/detail?contract_id=${cid}`);
      UI.detail({
        title: `合同 · ${d.contract_no}`,
        sections: [
          { title: '基本信息', items: [
            { label: '类型', value: d.contract_type_name },
            { label: '相对方', value: d.enterprise_name },
            { label: '品类', value: dictName(App.dict('ORE_CATEGORY'), d.ore_category) },
            { label: '状态', render: () => tag(d.status) },
            { label: '吨数', value: d.plan_ton ?? '-' },
            { label: '单价', value: d.unit_price ?? '-' },
            { label: '合同金额', value: d.contract_amount ?? '-', strong: true },
            { label: '签订日期', value: d.sign_date || '-' },
            { label: '生效日期', value: d.effective_date || '-' },
            { label: '到期日期', value: d.expire_date || '-' },
            { label: '付款条款', value: d.pay_remark || '-', full: true },
            d.terminate_reason ? { label: '终止原因', value: d.terminate_reason, full: true } : null
          ].filter(Boolean) },
          { title: '附件', items: [
            { label: '合同附件', full: true, render: () => d.attachments.length
              ? fileLinks(d.attachments.map(a => ({ file_url: a.file_url, file_name: a.file_name })))
              : el('span', null, '-') }
          ] },
          { title: '变更记录', items: [
            { label: '变更历史', full: true, render: () => d.changes.length
              ? el('div', null, d.changes.map(ch => el('div', { style: { padding: '6px 0', borderBottom: '1px dashed var(--line, #eee)' } }, [
                  el('div', { style: { fontSize: '13px' } }, ch.change_content),
                  el('div', { style: { fontSize: '12px', color: 'var(--text-3)' } }, `${fmtTime(ch.create_time)} ${ch.reason || ''}`)
                ])))
              : el('span', null, '暂无变更记录') }
          ] }
        ]
      });
    }
  }
});

/* ---------- R2 / R1 合同查看（只读） ---------- */
function readOnlyContractView(key, title, roles) {
  App.registerView(key, {
    title, roles,
    async render(root) {
      const state = { status: '' };
      const stSel = el('select', null, [el('option', { value: '' }, '全部状态'),
        ...['EFFECTIVE', 'EXECUTING', 'FINISHED', 'TERMINATED'].map(v => el('option', { value: v }, v))]);
      stSel.addEventListener('change', () => { state.status = stSel.value; table.reload(); });
      const table = UI.table({
        columns: [
          { title: '合同编号', key: 'contract_no', strong: true },
          { title: '品类', render: r => dictName(App.dict('ORE_CATEGORY'), r.ore_category) },
          { title: '吨数/金额', render: r => `${r.plan_ton ?? '-'}吨 / ¥${r.contract_amount ?? '-'}` },
          { title: '状态', render: r => tag(r.status) },
          { title: '到期日', render: r => r.expire_date || '-' }
        ],
        toolbar: { render: () => [stSel, el('span', { class: 'fb-sep' }),
          el('button', { class: 'btn btn-sm', onclick: () => API.download('/api/contract/export', state) }, '导出')] },
        query: state, rowKey: 'contract_id',
        fetch: q => API.get('/api/contract/list', q)
      });
      root.appendChild(el('div', { class: 'card' }, [table.root]));
    }
  });
}
readOnlyContractView('r2.contract', '供货合同', ['R2']);
readOnlyContractView('r1.contract', '采购合同', ['R1']);

/* ---------- R4 费用分摊 ---------- */
App.registerView('r4.expense', {
  title: '费用分摊', roles: ['R4'],
  async render(root) {
    const tab = el('div', { style: { display: 'flex', gap: '8px', marginBottom: '14px' } });
    const body = el('div');
    let current = 'bill';
    const renderTab = () => {
      tab.innerHTML = ''; body.innerHTML = '';
      [['bill', '费用单台账'], ['share', '分摊工作台']].forEach(([k, t]) => {
        tab.appendChild(el('button', { class: `btn btn-sm ${current === k ? 'btn-primary' : ''}`,
          onclick: () => { current = k; renderTab(); } }, t));
      });
      if (current === 'bill') renderBills(); else renderShare();
    };

    function renderBills() {
      const state = { expense_type: '' };
      const typeSel = el('select', null, [el('option', { value: '' }, '全部费用类型'),
        ...(App.dict('EXPENSE_TYPE') || []).map(d => el('option', { value: d.item_code }, d.item_name))]);
      typeSel.addEventListener('change', () => { state.expense_type = typeSel.value; table.reload(); });
      const table = UI.table({
        columns: [
          { title: '费用单号', key: 'expense_no', strong: true },
          { title: '订单号', key: 'order_no' },
          { title: '费用类型', render: r => dictName(App.dict('EXPENSE_TYPE'), r.expense_type) },
          { title: '金额', render: r => `¥${r.expense_amount}`, num: true },
          { title: '发生日期', render: r => r.happen_date || '-' },
          { title: '已分摊笔数', render: r => r.allocated_count },
          { title: '操作', render: r => !r.allocated_count
            ? el('button', { class: 'btn btn-sm btn-link', style: { color: 'var(--red)' },
                onclick: () => confirmDialog(`确认删除费用单 ${r.expense_no}？`, async () => {
                  await API.post(`/api/expense/bill/${r.expense_id}/delete`); Toast.success('已删除'); table.reload();
                }, { danger: true }) }, '删除')
            : el('span', null, '已分摊') }
        ],
        toolbar: { render: () => [typeSel, el('span', { class: 'fb-sep' }),
          el('button', { class: 'btn btn-sm', onclick: () => API.download('/api/expense/bill/export', {}) }, '导出'),
          el('button', { class: 'btn btn-primary btn-sm', onclick: () => editBill(null) }, '+ 新增费用单')] },
        query: state, rowKey: 'expense_id',
        fetch: q => API.get('/api/expense/bill/list', q)
      });
      body.appendChild(el('div', { class: 'card' }, [table.root]));

      function editBill(b) {
        UI.form({
          title: b ? '编辑费用单' : '新增费用单',
          fields: [
            { key: 'order_id', label: '集采订单ID', type: 'number', required: true, value: b?.order_id ?? '' },
            { key: 'expense_type', label: '费用类型', type: 'text', required: true, value: b?.expense_type || '', hint: '如 SEA_FREIGHT 海运费' },
            { key: 'expense_amount', label: '费用金额', type: 'number', required: true, value: b?.expense_amount ?? '' },
            { key: 'happen_date', label: '发生日期', type: 'date', value: b?.happen_date || '' },
            { key: 'payee', label: '收款方', type: 'text', value: b?.payee || '' },
            { key: 'remark', label: '备注', type: 'text', full: true }
          ],
          submitText: '保存',
          onSubmit: async v => { await API.post('/api/expense/bill/save', v); Toast.success('费用单已保存'); table.reload(); }
        });
      }
    }

    function renderShare() {
      const orderInp = el('input', { type: 'number', placeholder: '集采订单ID' });
      const runBtn = el('button', { class: 'btn btn-primary btn-sm', onclick: async () => {
        if (!orderInp.value) { Toast.error('请输入集采订单ID'); return; }
        try {
          const r = await API.post('/api/expense/share/run', { order_id: Number(orderInp.value) });
          Toast.success(`分摊完成：${r.bills} 笔费用分摊到 ${r.alloc_orders} 张分拨单`);
        } catch (e) { /* toast 已提示 */ }
      } }, '执行分摊');
      const revokeBtn = el('button', { class: 'btn btn-sm', style: { color: 'var(--orange)' }, onclick: async () => {
        if (!orderInp.value) { Toast.error('请输入集采订单ID'); return; }
        confirmDialog('确认撤销该订单的全部分摊记录？（可重新执行分摊）', async () => {
          await API.post('/api/expense/share/revoke', { order_id: Number(orderInp.value) });
          Toast.success('已撤销');
        }, { danger: true });
      } }, '撤销分摊');
      body.appendChild(el('div', { class: 'card' }, [
        el('div', { class: 'card-title' }, '分摊工作台'),
        el('div', { style: { display: 'flex', gap: '8px', alignItems: 'center', flexWrap: 'wrap' } },
          [el('span', null, '集采订单：'), orderInp, runBtn, revokeBtn]),
        el('div', { class: 'hint', style: { marginTop: '8px' } },
          '前置条件：订单已有审核通过的到港船检化验单；分摊权重=各分拨单结算吨数（有出库检取其结算吨）；最后一单兜尾差保证金额守恒')
      ]));
    }

    renderTab();
    root.appendChild(el('div', null, [tab, body]));
  }
});

/* ---------- R1 分项结算明细 ---------- */
App.registerView('r1.expense', {
  title: '费用结算明细', roles: ['R1'],
  async render(root) {
    const body = el('div');
    const selBox = el('div', { style: { display: 'flex', gap: '8px', alignItems: 'center', marginBottom: '14px' } });
    const allocInp = el('input', { type: 'number', placeholder: '分拨单ID' });
    const loadBtn = el('button', { class: 'btn btn-primary btn-sm', onclick: load }, '查询');
    selBox.append(el('span', null, '分拨单：'), allocInp, loadBtn);
    root.appendChild(el('div', null, [selBox, body]));

    async function load() {
      if (!allocInp.value) { Toast.error('请输入分拨单ID'); return; }
      body.innerHTML = '';
      let d;
      try { d = await API.get(`/api/expense/share/detail?alloc_id=${allocInp.value}`); }
      catch (e) { return; }
      body.appendChild(el('div', { class: 'card' }, [
        el('div', { class: 'card-title' }, '费用汇总'),
        el('table', { class: 'tb' }, [
          el('thead', null, el('tr', null, ['费用类型', '笔数', '分摊金额'].map(h => el('th', null, h)))),
          el('tbody', null, d.summary.length ? d.summary.map(s => el('tr', null, [
            el('td', null, dictName(App.dict('EXPENSE_TYPE'), s.expense_type)),
            el('td', null, String(s.count)),
            el('td', null, `¥${s.total}`)
          ])) : el('tr', null, el('td', { colspan: 3, style: { textAlign: 'center', color: 'var(--text-3)' } }, '暂无分摊明细'))),
          el('tfoot', null, el('tr', null, [
            el('th', null, '杂费合计'), el('th', null, ''), el('th', null, `¥${d.expense_total}`)
          ]))
        ])
      ]));
      if (d.alloc) {
        body.appendChild(el('div', { class: 'card', style: { marginTop: '12px' } }, [
          el('div', { class: 'card-title' }, '应付合计'),
          el('div', { style: { display: 'flex', gap: '24px', fontSize: '14px' } }, [
            el('span', null, `货款：¥${d.alloc.ore_amount}（${d.alloc.qty}吨 × ¥${d.alloc.unit_price}）`),
            el('span', null, `杂费：¥${d.expense_total}`),
            el('span', { style: { fontWeight: 700, color: 'var(--orange)' } }, `应付合计：¥${d.total_payable}`)
          ])
        ]));
      }
    }
  }
});

/* ---------- 消息中心（全员） ---------- */
App.registerView('msg.center', {
  title: '消息中心', roles: ['R1', 'R2', 'R3', 'R4'],
  async render(root) {
    const state = { msg_type: '', is_read: '' };
    const typeSel = el('select', null, [el('option', { value: '' }, '全部消息'),
      el('option', { value: '1' }, '待办'), el('option', { value: '2' }, '通知'), el('option', { value: '3' }, '预警')]);
    typeSel.addEventListener('change', () => { state.msg_type = typeSel.value; table.reload(); });
    const readSel = el('select', null, [el('option', { value: '' }, '全部'),
      el('option', { value: '0' }, '未读'), el('option', { value: '1' }, '已读')]);
    readSel.addEventListener('change', () => { state.is_read = readSel.value; table.reload(); });
    const readAllBtn = el('button', { class: 'btn btn-sm', onclick: async () => {
      await API.post('/api/message/read-all'); Toast.success('已全部标记已读'); table.reload();
    } }, '全部已读');

    const table = UI.table({
      columns: [
        { title: '类型', render: r => {
          const map = { 1: ['待办', 'orange'], 2: ['通知', 'blue'], 3: ['预警', 'red'] };
          const [n, c] = map[r.msg_type] || ['通知', 'blue'];
          return el('span', { class: `tag tag-${c}` }, n);
        } },
        { title: '标题', strong: true, render: r => el('span', { style: r.is_read ? { color: 'var(--text-3)' } : { fontWeight: 600 } }, r.title) },
        { title: '内容', render: r => el('span', { style: { color: 'var(--text-2)', fontSize: '12.5px' } }, r.content || '') },
        { title: '时间', render: r => fmtTime(r.create_time) },
        { title: '状态', render: r => r.msg_type === 1
            ? (r.is_finish ? tag('DONE') : tag('WAIT'))
            : (r.is_read ? tag('DONE') : tag('WAIT_QUOTE')) },
        { title: '操作', render: r => !r.is_read
          ? el('button', { class: 'btn btn-sm btn-link', onclick: () => readOne(r) }, '标记已读')
          : el('span', null, '-') }
      ],
      toolbar: { render: () => [typeSel, readSel, el('span', { class: 'fb-sep' }), readAllBtn] },
      query: state, rowKey: 'msg_id',
      fetch: q => API.get('/api/message/list', q)
    });
    root.appendChild(el('div', { class: 'card' }, [table.root]));

    async function readOne(r) {
      await API.post(`/api/message/${r.msg_id}/read`);
      table.reload();
    }
  }
});

/* ---------- R4 预警规则 ---------- */
App.registerView('r4.warnrule', {
  title: '业务预警规则', roles: ['R4'],
  async render(root) {
    const scanBtn = el('button', { class: 'btn btn-sm', onclick: async () => {
      const r = await API.post('/api/warn/scan');
      Toast.success(`扫描完成，生成预警 ${r.total} 条：合同到期${r.generated.CONTRACT_EXPIRE} / 价格异动${r.generated.PRICE_CHANGE} / 物流超时${r.generated.LOGI_STALE} / 货源周期${r.generated.RESOURCE_EXPIRE}`);
    } }, '立即执行预警扫描');

    const table = UI.table({
      columns: [
        { title: '规则名称', key: 'rule_name', strong: true },
        { title: '预警类型', key: 'warn_type_name' },
        { title: '阈值', render: r => `${r.threshold} ${r.threshold_unit}` },
        { title: '状态', render: r => r.enable_status ? tag('ACTIVE') : tag('OFF_SHELF') },
        { title: '操作', render: r => el('div', { style: { display: 'flex', gap: '2px' } }, [
          el('button', { class: 'btn btn-sm btn-link', onclick: () => editRule(r) }, '编辑'),
          el('button', { class: 'btn btn-sm btn-link', onclick: async () => {
            await API.post(`/api/warn/rule/${r.rule_id}/toggle`); Toast.success('操作成功'); table.reload();
          } }, r.enable_status ? '停用' : '启用')
        ]) }
      ],
      toolbar: { render: () => [el('span', { class: 'fb-sep' }), scanBtn,
        el('button', { class: 'btn btn-primary btn-sm', onclick: () => editRule(null) }, '+ 新增规则')] },
      rowKey: 'rule_id',
      fetch: q => API.get('/api/warn/rule/list', q)
    });
    root.appendChild(el('div', { class: 'card' }, [table.root]));

    function editRule(r) {
      UI.form({
        title: r ? '编辑预警规则' : '新增预警规则',
        fields: [
          { key: 'rule_name', label: '规则名称', type: 'text', required: true, value: r?.rule_name || '' },
          { key: 'warn_type', label: '预警类型', type: 'select', required: true, value: r?.warn_type || 'CONTRACT_EXPIRE',
            options: [
              { value: 'CONTRACT_EXPIRE', label: '合同到期预警（阈值=提前天数）' },
              { value: 'RESOURCE_EXPIRE', label: '货源周期到期（阈值=提前天数）' },
              { value: 'PRICE_CHANGE', label: '价格行情异动（阈值=波动幅度%）' },
              { value: 'LOGI_STALE', label: '物流节点超时（阈值=未更新天数）' }
            ] },
          { key: 'threshold', label: '阈值', type: 'number', required: true, value: r?.threshold ?? '' }
        ],
        submitText: '保存',
        onSubmit: async v => {
          await API.post('/api/warn/rule/save', { ...v, rule_id: r?.rule_id });
          Toast.success('规则已保存');
          table.reload();
        }
      });
    }
  }
});

/* ---------- R4 报表中心 ---------- */
App.registerView('r4.report', {
  title: '数据报表中心', roles: ['R4'],
  async render(root) {
    const tab = el('div', { style: { display: 'flex', gap: '8px', marginBottom: '14px', flexWrap: 'wrap' } });
    const body = el('div');
    let current = 'summary';
    const TABS = [['summary', '采购汇总'], ['trade', '交易汇总'], ['logistics', '物流时效'], ['settlement', '结算汇总'], ['price', '价格趋势']];
    const RENDERERS = { summary, trade, logistics, settlement, price };
    const renderTab = () => {
      tab.innerHTML = ''; body.innerHTML = '';
      TABS.forEach(([k, t]) => tab.appendChild(el('button', { class: `btn btn-sm ${current === k ? 'btn-primary' : ''}`,
        onclick: () => { current = k; renderTab(); } }, t)));
      RENDERERS[current]();
    };
    const rangeBar = () => {
      const s = el('input', { type: 'date' }); const e = el('input', { type: 'date' });
      const btn = el('button', { class: 'btn btn-sm btn-primary', onclick: () => renderTab() }, '查询');
      return { node: el('div', { style: { display: 'flex', gap: '8px', marginBottom: '12px', alignItems: 'center' } },
        [el('span', null, '时间区间：'), s, e, btn]), get: () => ({ start_date: s.value, end_date: e.value }) };
    };
    const mkTable = (headers, rows) => el('div', { class: 'card' }, el('table', { class: 'tb' }, [
      el('thead', null, el('tr', null, headers.map(h => el('th', null, h)))),
      el('tbody', null, rows.length ? rows : el('tr', null, el('td', { colspan: headers.length, style: { textAlign: 'center', color: 'var(--text-3)' } }, '暂无数据')))
    ]));

    async function summary() { const q = rangeBar(); body.appendChild(q.node);
      const d = await API.get('/api/report/summary', q.get());
      body.appendChild(mkTable(['品类', '需求数', '总吨数'], d.by_category.map(r => el('tr', null, [
        el('td', null, dictName(App.dict('ORE_CATEGORY'), r.ore_category)),
        el('td', null, String(r.demand_cnt)), el('td', null, `${r.total_qty}`)
      ]))));
      body.appendChild(mkTable(['企业', '需求数', '总吨数'], d.by_company.map(r => el('tr', null, [
        el('td', null, r.company_name), el('td', null, String(r.demand_cnt)), el('td', null, `${r.total_qty}`)
      ]))));
    }
    async function trade() { const q = rangeBar(); body.appendChild(q.node);
      const d = await API.get('/api/report/trade', q.get());
      body.appendChild(mkTable(['月份', '订单数', '吨数', '金额'], d.by_month.map(r => el('tr', null, [
        el('td', null, r.month), el('td', null, String(r.order_cnt)),
        el('td', null, `${r.total_qty}`), el('td', null, `¥${r.total_amount}`)
      ]))));
      body.appendChild(mkTable(['品类', '订单数', '吨数', '金额', '均价'], d.by_category.map(r => el('tr', null, [
        el('td', null, dictName(App.dict('ORE_CATEGORY'), r.ore_category)), el('td', null, String(r.order_cnt)),
        el('td', null, `${r.total_qty}`), el('td', null, `¥${r.total_amount}`), el('td', null, `¥${r.avg_price}`)
      ]))));
    }
    async function logistics() { const q = rangeBar(); body.appendChild(q.node);
      const d = await API.get('/api/report/logistics', q.get());
      body.appendChild(el('div', { class: 'card' }, el('div', { style: { display: 'flex', gap: '24px', fontSize: '14px' } }, [
        el('span', null, `任务总数：${d.total}`), el('span', null, `平均时效：${d.avg_days ?? '-'} 天`), el('span', null, `完成率：${d.finish_rate ?? '-'}%`)
      ])));
      body.appendChild(mkTable(['物流单号', '当前节点', '已完成节点', '总时效(天)'], d.stats.map(r => el('tr', null, [
        el('td', null, r.logi_no), el('td', null, `N${r.current_node}`),
        el('td', null, `${r.finished}/7`), el('td', null, r.days ?? '-')
      ]))));
    }
    async function settlement() { const q = rangeBar(); body.appendChild(q.node);
      const d = await API.get('/api/report/settlement', q.get());
      body.appendChild(mkTable(['下游企业', '对账单数', '总金额', '已确认', '待确认'], d.by_company.map(r => el('tr', null, [
        el('td', null, r.company_name), el('td', null, String(r.bill_cnt)),
        el('td', null, `¥${r.total_amount}`), el('td', null, `¥${r.confirmed_amount}`), el('td', null, `¥${r.pending_amount}`)
      ]))));
    }
    async function price() {
      const catSel = el('select', null, (App.dict('ORE_CATEGORY') || []).map(d =>
        el('option', { value: d.item_code, selected: d.item_code === 'IRON' }, d.item_name)));
      const bar = el('div', { style: { display: 'flex', gap: '8px', marginBottom: '12px', alignItems: 'center' } },
        [el('span', null, '品类：'), catSel]);
      catSel.addEventListener('change', loadTrend);
      body.appendChild(bar);
      const canvas = el('canvas', { style: { width: '100%', height: '300px' } });
      const chartCard = el('div', { class: 'card' }, canvas);
      body.appendChild(chartCard);
      async function loadTrend() {
        const d = await API.get('/api/report/price-trend', { ore_category: catSel.value });
        Charts.line(canvas, d.trend.map(t => t.quote_date), [
          { name: '市场参考价', color: '#4f7cff', data: d.trend.map(t => t.market_price) },
          { name: '成交均价', color: '#22c55e', data: d.trend.map(t => t.avg_deal_price) }
        ], { unit: '元' });
      }
      await loadTrend();
    }

    renderTab();
    root.appendChild(el('div', null, [tab, body]));
  }
});

/* ---------- R4 运营大屏 ---------- */
App.registerView('r4.bigscreen', {
  title: '运营大屏', roles: ['R4'],
  async render(root) {
    root.appendChild(el('div', { id: 'bigscreen-root' }));
    let timer = null;
    async function load() {
      const box = document.getElementById('bigscreen-root');
      if (!box) return;
      let d;
      try { d = await API.get('/api/dashboard/overview'); } catch (e) { return; }
      const c = d.cards;
      box.innerHTML = '';
      const card = (label, value, color) => el('div', { class: 'card', style: { padding: '14px 18px' } }, [
        el('div', { style: { fontSize: '12px', color: 'var(--text-3)' } }, label),
        el('div', { style: { fontSize: '24px', fontWeight: 700, color: color || 'var(--text-1)' } }, value)
      ]);
      box.appendChild(el('div', { style: { display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: '10px', marginBottom: '12px' } }, [
        card('入驻企业', c.total_companies), card('待审资质', c.pending_audit, c.pending_audit ? '#ef4444' : null),
        card('需求总量(吨)', c.total_qty), card('锁货吨数(吨)', c.locked_qty), card('交易额(¥)', c.trade_amount)
      ]));
      box.appendChild(el('div', { style: { display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: '10px', marginBottom: '12px' } }, [
        card('在途物流', c.logi_running, '#f59e0b'), card('已送达', c.logi_done, '#22c55e'),
        card('对账总额(¥)', c.bill_total), card('已确认(¥)', c.bill_confirmed), card('未读预警', c.unread_warn, c.unread_warn ? '#ef4444' : null)
      ]));

      const canvas1 = el('canvas', { style: { width: '100%', height: '260px' } });
      const canvas2 = el('canvas', { style: { width: '100%', height: '260px' } });
      const grid = el('div', { style: { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' } }, [
        el('div', { class: 'card' }, [el('div', { class: 'card-title' }, '月度订单趋势'), canvas1]),
        el('div', { class: 'card' }, [el('div', { class: 'card-title' }, '下游分拨分布 TOP8'), canvas2])
      ]);
      box.appendChild(grid);
      Charts.line(canvas1, d.order_trend.map(x => x.month), [
        { name: '订单数', color: '#4f7cff', data: d.order_trend.map(x => x.cnt) },
        { name: '金额(万)', color: '#22c55e', data: d.order_trend.map(x => Math.round(x.amount / 10000 * 100) / 100) }
      ], { unit: '' });
      Charts.bar(canvas2, d.alloc_map.map(x => x.company_name.slice(0, 6)), [
        { name: '分拨吨数', color: '#8b5cf6', data: d.alloc_map.map(x => x.qty) }
      ], { unit: '吨' });
    }
    await load();
    if (this._screenTimer) clearInterval(this._screenTimer);
    this._screenTimer = setInterval(load, 5 * 60 * 1000); // 5分钟自动刷新
  }
});

/* ---------- R1 / R2 自助报表 ---------- */
App.registerView('r1.report', {
  title: '我的业务报表', roles: ['R1'],
  async render(root) {
    const body = el('div');
    root.appendChild(body);
    const [summary, logistics, settlement] = await Promise.all([
      API.get('/api/report/summary'), API.get('/api/report/logistics'), API.get('/api/report/settlement')
    ]);
    body.appendChild(el('div', { class: 'card' }, [
      el('div', { class: 'card-title' }, '我的采购需求汇总'),
      el('table', { class: 'tb' }, [
        el('thead', null, el('tr', null, ['品类', '需求数', '总吨数'].map(h => el('th', null, h)))),
        el('tbody', null, summary.by_category.length ? summary.by_category.map(r => el('tr', null, [
          el('td', null, dictName(App.dict('ORE_CATEGORY'), r.ore_category)),
          el('td', null, String(r.demand_cnt)), el('td', null, `${r.total_qty}`)
        ])) : el('tr', null, el('td', { colspan: 3, style: { textAlign: 'center', color: 'var(--text-3)' } }, '暂无数据')))
      ])
    ]));
    body.appendChild(el('div', { class: 'card', style: { marginTop: '12px' } }, [
      el('div', { class: 'card-title' }, `物流履约：共 ${logistics.total} 单，平均时效 ${logistics.avg_days ?? '-'} 天`),
      el('table', { class: 'tb' }, [
        el('thead', null, el('tr', null, ['物流单号', '进度', '时效(天)'].map(h => el('th', null, h)))),
        el('tbody', null, logistics.stats.slice(0, 20).map(r => el('tr', null, [
          el('td', null, r.logi_no), el('td', null, `节点${r.current_node}/7`), el('td', null, r.days ?? '-')
        ])))
      ])
    ]));
  }
});

App.registerView('r2.report', {
  title: '我的交易报表', roles: ['R2'],
  async render(root) {
    const body = el('div');
    root.appendChild(body);
    const trade = await API.get('/api/report/trade');
    body.appendChild(el('div', { class: 'card' }, [
      el('div', { class: 'card-title' }, '我的订单月度汇总'),
      el('table', { class: 'tb' }, [
        el('thead', null, el('tr', null, ['月份', '订单数', '吨数', '金额'].map(h => el('th', null, h)))),
        el('tbody', null, trade.by_month.length ? trade.by_month.map(r => el('tr', null, [
          el('td', null, r.month), el('td', null, String(r.order_cnt)),
          el('td', null, `${r.total_qty}`), el('td', null, `¥${r.total_amount}`)
        ])) : el('tr', null, el('td', { colspan: 4, style: { textAlign: 'center', color: 'var(--text-3)' } }, '暂无数据')))
      ])
    ]));
    body.appendChild(el('div', { class: 'card', style: { marginTop: '12px' } }, [
      el('div', { class: 'card-title' }, '品类分布'),
      el('table', { class: 'tb' }, [
        el('thead', null, el('tr', null, ['品类', '订单数', '吨数', '金额', '均价'].map(h => el('th', null, h)))),
        el('tbody', null, trade.by_category.map(r => el('tr', null, [
          el('td', null, dictName(App.dict('ORE_CATEGORY'), r.ore_category)), el('td', null, String(r.order_cnt)),
          el('td', null, `${r.total_qty}`), el('td', null, `¥${r.total_amount}`), el('td', null, `¥${r.avg_price}`)
        ])))
      ])
    ]));
  }
});

/* ---------- R1/R2 变更红冲申请 ---------- */
App.registerView('biz.apply', {
  title: '单据变更/红冲申请', roles: ['R1', 'R2'],
  async render(root) {
    const tab = el('div', { style: { display: 'flex', gap: '8px', marginBottom: '14px' } });
    const body = el('div');
    let current = 'change';
    const renderTab = () => {
      tab.innerHTML = ''; body.innerHTML = '';
      [['change', '变更申请'], ['redback', '红冲申请']].forEach(([k, t]) => {
        tab.appendChild(el('button', { class: `btn btn-sm ${current === k ? 'btn-primary' : ''}`,
          onclick: () => { current = k; renderTab(); } }, t));
      });
      if (current === 'change') renderChange(); else renderRedback();
    };

    function bizFields() {
      return [
        { key: 'biz_type', label: '单据类型', type: 'select', required: true,
          options: [{ value: 'INSPECT', label: '化验单' }, { value: 'ALLOC', label: '分拨单' },
            { value: 'BILL', label: '对账单' }, { value: 'CONTRACT', label: '合同' }] },
        { key: 'biz_id', label: '单据ID', type: 'number', required: true, hint: '可在对应业务视图的单据编号中查看' }
      ];
    }
    function renderChange() {
      const btn = el('button', { class: 'btn btn-primary btn-sm', onclick: () => UI.form({
        title: '发起变更申请',
        wide: true,
        fields: [...bizFields(),
          { key: 'before_content', label: '变更前内容', type: 'textarea', required: true, full: true },
          { key: 'after_content', label: '变更后内容', type: 'textarea', required: true, full: true },
          { key: 'reason', label: '变更原因', type: 'text', full: true }],
        submitText: '提交申请',
        onSubmit: async v => { await API.post('/api/biz/change/apply', v); Toast.success('变更申请已提交，等待平台审核'); }
      }) }, '+ 发起变更申请');
      body.appendChild(el('div', { class: 'card' }, [
        el('div', { class: 'hint' }, '变更申请提交后由平台管理员审核；审核结果将通过消息中心通知您。'),
        el('div', { style: { marginTop: '10px' } }, [btn])
      ]));
    }
    function renderRedback() {
      const btn = el('button', { class: 'btn btn-primary btn-sm', onclick: () => UI.form({
        title: '发起红冲申请',
        wide: true,
        fields: [...bizFields(),
          { key: 'redback_ton', label: '红冲吨数', type: 'number', hint: '选填' },
          { key: 'redback_amount', label: '红冲金额', type: 'number', hint: '选填' },
          { key: 'reason', label: '红冲原因', type: 'textarea', required: true, full: true, hint: '不少于5个字' }],
        submitText: '提交申请',
        onSubmit: async v => { await API.post('/api/biz/redback/apply', v); Toast.success('红冲申请已提交，等待平台审核'); }
      }) }, '+ 发起红冲申请');
      body.appendChild(el('div', { class: 'card' }, [
        el('div', { class: 'hint' }, '红冲审核通过后，原单据将被标记「已红冲作废」，不再参与后续结算。'),
        el('div', { style: { marginTop: '10px' } }, [btn])
      ]));
    }
    renderTab();
    root.appendChild(el('div', null, [tab, body]));
  }
});

/* ---------- R4 变更红冲审核 ---------- */
App.registerView('r4.bizchange', {
  title: '变更红冲审核', roles: ['R4'],
  async render(root) {
    const tab = el('div', { style: { display: 'flex', gap: '8px', marginBottom: '14px' } });
    const body = el('div');
    let current = 'change';
    const renderTab = () => {
      tab.innerHTML = ''; body.innerHTML = '';
      [['change', '变更申请审核'], ['redback', '红冲申请审核']].forEach(([k, t]) => {
        tab.appendChild(el('button', { class: `btn btn-sm ${current === k ? 'btn-primary' : ''}`,
          onclick: () => { current = k; renderTab(); } }, t));
      });
      if (current === 'change') renderChange(); else renderRedback();
    };

    function auditForm(kind, r) {
      const isRed = kind === 'redback';
      UI.form({
        title: `${isRed ? '红冲' : '变更'}申请审核 · ${r.biz_type_name} ${r.biz_no}`,
        wide: true,
        fields: isRed ? [
          { key: 'reason_ro', label: '红冲原因', type: 'text', value: r.reason || '', full: true },
          { key: 'amount_ro', label: '红冲吨数/金额', type: 'text', value: `${r.redback_ton ?? '-'} / ${r.redback_amount ?? '-'}` },
          { key: 'result', label: '审核结论', type: 'select', required: true,
            options: [{ value: 'APPROVED', label: '通过（原单作废）' }, { value: 'REJECTED', label: '驳回' }] },
          { key: 'review_remark', label: '审核备注', type: 'text', full: true, hint: '驳回时必填' }
        ] : [
          { key: 'before_ro', label: '变更前', type: 'text', value: r.before_content || '', full: true },
          { key: 'after_ro', label: '变更后', type: 'text', value: r.after_content || '', full: true },
          { key: 'reason_ro', label: '变更原因', type: 'text', value: r.reason || '', full: true },
          { key: 'result', label: '审核结论', type: 'select', required: true,
            options: [{ value: 'APPROVED', label: '通过' }, { value: 'REJECTED', label: '驳回' }] },
          { key: 'review_remark', label: '审核备注', type: 'text', full: true, hint: '驳回时必填' }
        ],
        submitText: '提交审核',
        onSubmit: async v => {
          if (v.result === 'REJECTED' && !v.review_remark.trim()) { Toast.error('驳回必须填写备注'); throw new Error(''); }
          await API.post(isRed ? `/api/biz/redback/audit` : `/api/biz/change/audit`,
            { result: v.result, review_remark: v.review_remark,
              [isRed ? 'redback_id' : 'change_id']: r[isRed ? 'redback_id' : 'change_id'] });
          Toast.success(isRed && v.result === 'APPROVED' ? '审核通过，原单已红冲作废' : '审核完成');
          renderTab();
        }
      });
    }

    function renderChange() {
      const state = { status: '' };
      const stSel = el('select', null, [el('option', { value: '' }, '全部状态'),
        ...['PENDING', 'APPROVED', 'REJECTED'].map(v => el('option', { value: v }, v))]);
      stSel.addEventListener('change', () => { state.status = stSel.value; table.reload(); });
      const table = UI.table({
        columns: [
          { title: '单据类型', render: r => r.biz_type_name },
          { title: '单据编号', key: 'biz_no' },
          { title: '变更前→后', render: r => el('span', { style: { fontSize: '12.5px' } }, `${(r.before_content || '').slice(0, 20)} → ${(r.after_content || '').slice(0, 20)}`) },
          { title: '申请人', key: 'apply_user' },
          { title: '状态', render: r => tag(r.status) },
          { title: '操作', render: r => el('div', { style: { display: 'flex', gap: '2px' } }, [
            r.status === 'PENDING' ? el('button', { class: 'btn btn-sm btn-link', onclick: () => auditForm('change', r) }, '审核') : null
          ]) }
        ],
        toolbar: { render: () => [stSel] },
        query: state, rowKey: 'change_id',
        fetch: q => API.get('/api/biz/apply/list', { ...q, kind: 'change' })
      });
      body.appendChild(el('div', { class: 'card' }, [table.root]));
    }
    function renderRedback() {
      const state = { status: '' };
      const stSel = el('select', null, [el('option', { value: '' }, '全部状态'),
        ...['PENDING', 'APPROVED', 'REJECTED'].map(v => el('option', { value: v }, v))]);
      stSel.addEventListener('change', () => { state.status = stSel.value; table.reload(); });
      const table = UI.table({
        columns: [
          { title: '红冲单号', key: 'redback_no', strong: true },
          { title: '单据类型', render: r => r.biz_type_name },
          { title: '原单编号', key: 'biz_no' },
          { title: '红冲吨数/金额', render: r => `${r.redback_ton ?? '-'} / ${r.redback_amount ?? '-'}` },
          { title: '申请人', key: 'apply_user' },
          { title: '状态', render: r => tag(r.status) },
          { title: '操作', render: r => r.status === 'PENDING'
            ? el('button', { class: 'btn btn-sm btn-link', onclick: () => auditForm('redback', r) }, '审核') : el('span', null, '-') }
        ],
        toolbar: { render: () => [stSel] },
        query: state, rowKey: 'redback_id',
        fetch: q => API.get('/api/biz/apply/list', { ...q, kind: 'redback' })
      });
      body.appendChild(el('div', { class: 'card' }, [table.root]));
    }
    renderTab();
    root.appendChild(el('div', null, [tab, body]));
  }
});
