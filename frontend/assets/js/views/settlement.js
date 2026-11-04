/* ============ 对账结算模块视图 (PRD-07)：R4 分拨/对账/归档/台账 / R1 分拨确认与对账 / R2 供方对账 ============ */

const ALLOC_TAG = { TRANSIT: 'tag-blue', WAIT_CONFIRM: 'tag-orange', DONE: 'tag-green' };
const BILL_TAG = { PENDING: 'tag-orange', CONFIRMED: 'tag-green', DISPUTE: 'tag-red', SETTLED: 'tag-purple' };

function allocTag(s) { return el('span', { class: 'tag ' + (ALLOC_TAG[s] || 'tag-gray') }, (TAG_MAP[s] || [s])[0]); }
function billTag(s) { return el('span', { class: 'tag ' + (BILL_TAG[s] || 'tag-gray') }, (TAG_MAP[s] || [s])[0]); }

/* ---------- R4 分拨管理 ---------- */
App.registerView('r4.alloc', {
  title: '分拨管理', roles: ['R4'],
  async render(root) {
    const state = { status: '', order_no: '', company: '' };
    const statusSel = el('select', null, [el('option', { value: '' }, '全部状态'),
      ...['TRANSIT', 'WAIT_CONFIRM', 'DONE'].map(s => el('option', { value: s }, TAG_MAP[s][0]))]);
    statusSel.addEventListener('change', () => { state.status = statusSel.value; table.reload(); });
    const noIn = el('input', { type: 'text', placeholder: '订单号' });
    noIn.addEventListener('input', debounce(() => { state.order_no = noIn.value.trim(); table.reload(); }, 300));
    const coIn = el('input', { type: 'text', placeholder: '企业名称' });
    coIn.addEventListener('input', debounce(() => { state.company = coIn.value.trim(); table.reload(); }, 300));
    const newBtn = el('button', { class: 'btn btn-primary btn-sm', onclick: showAllocWizard }, '📦 生成分拨单');

    const table = UI.table({
      columns: [
        { title: '分拨单号', key: 'alloc_no', strong: true },
        { title: '订单号', key: 'order_no' },
        { title: '下游企业', key: 'company_name' },
        { title: '品类', render: r => dictName(App.dict('ORE_CATEGORY'), r.ore_category) },
        { title: '分拨吨数', num: true, render: r => fmtQty(r.qty) + ' 吨' },
        { title: '结算单价', num: true, render: r => fmtMoney(r.unit_price) },
        { title: '分拨金额', num: true, render: r => fmtMoney(r.amount) },
        { title: '交货目的地', render: r => r.destination || '-' },
        { title: '状态', render: r => allocTag(r.status) },
        { title: '分拨时间', key: 'create_time' }
      ],
      toolbar: { render: () => [statusSel, noIn, coIn, el('span', { class: 'fb-sep' }), newBtn] },
      query: state, rowKey: 'alloc_id',
      fetch: q => API.get('/api/admin/allocation/list', q)
    });
    root.appendChild(el('div', { class: 'card' }, [table.root]));

    /* 到货异常反馈处理 */
    const fbCard = el('div', { class: 'card', style: { marginTop: '12px' } });
    fbCard.appendChild(el('div', { class: 'card-title' }, '到货异常反馈处理'));
    const fbTable = UI.table({
      columns: [
        { title: '分拨单号', key: 'alloc_no', strong: true },
        { title: '反馈企业', key: 'company_name' },
        { title: '异常描述', render: r => el('span', { title: r.description, style: { display: 'inline-block', maxWidth: '360px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', verticalAlign: 'bottom' } }, r.description) },
        { title: '附件', render: r => r.attachment_url ? el('a', { href: r.attachment_url, target: '_blank', class: 'btn btn-sm btn-link' }, '查看') : '-' },
        { title: '状态', render: r => r.status === 'PENDING' ? tag('PENDING') : tag('RESOLVED') },
        { title: '反馈时间', key: 'create_time' },
        { title: '操作', render: r => r.status === 'PENDING'
          ? el('button', { class: 'btn btn-sm btn-link', onclick: () => showResolve(r) }, '处理') : (r.resolve_remark || '-') }
      ],
      query: {}, rowKey: 'id', page_size: 5,
      fetch: q => API.get('/api/admin/feedback/list', q)
    });
    fbCard.appendChild(el('div', { class: 'table-wrap' }, fbTable.root));
    root.appendChild(fbCard);

    function showResolve(r) {
      UI.form({
        title: `处理异常反馈 · ${r.alloc_no}`,
        fields: [
          { key: 'resolve_remark', label: '处理结果说明', type: 'textarea', required: true, full: true, maxlength: 300,
            hint: `企业反馈：${r.description}` }
        ],
        submitText: '确认处理',
        onSubmit: async v => {
          await API.post(`/api/admin/feedback/${r.id}/resolve`, { resolve_remark: v.resolve_remark });
          Toast.success('反馈已处理');
          fbTable.reload();
        }
      });
    }

    /* 生成分拨向导 */
    async function showAllocWizard() {
      const body = el('div', null);
      body.appendChild(el('div', { class: 'hint', style: { marginBottom: '8px' } },
        '前提：集采订单货物已完成入仓（物流节点 N5）。按下游企业申报需求拆分，各分拨合计吨数不可超过集采实际到货量。'));
      // 订单选择
      const orderRes = await API.get('/api/admin/order/list', { page: 1, page_size: 100 });
      const orderSel = el('select', null, [el('option', { value: '' }, '— 选择集采订单 —'),
        ...orderRes.list.map(o => el('option', { value: o.order_id },
          `${o.order_no}（${dictName(App.dict('ORE_CATEGORY'), o.ore_category)} · ${fmtQty(o.total_qty)}吨 · ${(TAG_MAP[o.status] || [o.status])[0]}）`))]);
      body.appendChild(el('div', { class: 'field' }, [el('label', null, '集采订单 *'), orderSel]));
      const rowsBox = el('div', null);
      body.appendChild(rowsBox);
      const sumTip = el('div', { class: 'hint', style: { marginTop: '6px' } });
      body.appendChild(sumTip);
      const rows = [];

      function addRow(companies) {
        const rowEl = el('div', { style: { display: 'flex', gap: '8px', alignItems: 'center', marginTop: '8px', flexWrap: 'wrap' } });
        const cSel = el('select', null, [el('option', { value: '' }, '— 选择下游企业 —'),
          ...companies.map(c => el('option', { value: c.company_id }, `${c.company_name}（${c.audit_status === 'APPROVED' ? '已审核' : '未过审'}）`))]);
        const qtyIn = el('input', { type: 'number', min: '0.01', step: '0.01', placeholder: '分拨吨数', style: { width: '120px' } });
        const priceIn = el('input', { type: 'number', min: '0.01', step: '0.01', placeholder: '单价 元/吨', style: { width: '120px' } });
        const destIn = el('input', { type: 'text', placeholder: '交货目的地', style: { width: '160px' } });
        const delBtn = el('button', { class: 'btn btn-sm', onclick: () => { const i = rows.indexOf(row); if (i >= 0) rows.splice(i, 1); rowEl.remove(); updateSum(); } }, '✕');
        const row = { cSel, qtyIn, priceIn, destIn };
        [qtyIn, priceIn].forEach(inp => inp.addEventListener('input', updateSum));
        rows.push(row);
        rowEl.appendChild(cSel); rowEl.appendChild(qtyIn); rowEl.appendChild(priceIn); rowEl.appendChild(destIn); rowEl.appendChild(delBtn);
        rowsBox.appendChild(rowEl);
      }

      function updateSum() {
        const sum = rows.reduce((s, r) => s + (Number(r.qtyIn.value) || 0), 0);
        const selOrder = orderRes.list.find(o => String(o.order_id) === orderSel.value);
        sumTip.textContent = selOrder
          ? `已分配合计：${fmtQty(sum)} 吨 / 集采到货量：${fmtQty(selOrder.total_qty)} 吨${sum > selOrder.total_qty ? '（超量！）' : ''}`
          : `已分配合计：${fmtQty(sum)} 吨`;
        sumTip.style.color = selOrder && sum > selOrder.total_qty ? 'var(--red)' : '';
      }
      orderSel.addEventListener('change', () => { rows.length = 0; rowsBox.innerHTML = ''; updateSum(); });

      openModal({
        title: '生成按需分拨单', wide: true, body,
        footer: close => [
          el('button', { class: 'btn', onclick: async () => {
            if (!orderSel.value) { Toast.error('请选择集采订单'); return; }
            const cres = await API.get('/api/admin/company/list', { company_type: 'DOWNSTREAM', audit_status: 'APPROVED', page: 1, page_size: 100 });
            addRow(cres.list || []);
          } }, '＋ 添加企业分拨行'),
          el('button', { class: 'btn', onclick: close }, '取消'),
          el('button', { class: 'btn btn-primary', onclick: async () => {
            if (!orderSel.value) { Toast.error('请选择集采订单'); return; }
            const allocs = rows.filter(r => r.cSel.value).map(r => ({
              company_id: Number(r.cSel.value), qty: Number(r.qtyIn.value),
              unit_price: Number(r.priceIn.value), destination: r.destIn.value.trim()
            }));
            if (!allocs.length) { Toast.error('请至少添加一条分拨明细'); return; }
            if (allocs.some(a => !(a.qty > 0) || !(a.unit_price > 0))) { Toast.error('分拨吨数、单价必须大于0'); return; }
            await API.post('/api/admin/allocation/create', { order_id: Number(orderSel.value), allocs });
            Toast.success('分拨单已生成并下发企业');
            close(); table.reload(); fbTable.reload();
          } }, '确认生成')
        ]
      });
    }
  }
});

/* ---------- R4 对账结算（企业单/供方单/归档台账 三Tab） ---------- */
App.registerView('r4.settle', {
  title: '对账结算', roles: ['R4'],
  async render(root) {
    const tabBar = el('div', { style: { display: 'flex', gap: '8px', marginBottom: '14px' } });
    const tabs = { company: '企业对账单', supplier: '供方对账单', ledger: '归档与履约台账' };
    let curTab = sessionStorage.getItem('r4.settle.tab') || 'company';
    const container = el('div', null);

    function renderTabs() {
      tabBar.innerHTML = '';
      Object.entries(tabs).forEach(([k, t]) => {
        tabBar.appendChild(el('button', {
          class: `btn btn-sm ${curTab === k ? 'btn-primary' : ''}`,
          onclick: () => { curTab = k; sessionStorage.setItem('r4.settle.tab', k); renderTabs(); renderBody(); }
        }, t));
      });
    }

    function renderBody() {
      container.innerHTML = '';
      container.appendChild(curTab === 'company' ? renderBillTable('company')
        : curTab === 'supplier' ? renderBillTable('supplier') : renderLedger());
    }

    function renderBillTable(kind) {
      const state = { kind, status: '', period: '' };
      const statusSel = el('select', null, [el('option', { value: '' }, '全部状态'),
        ...['PENDING', 'CONFIRMED', 'DISPUTE', 'SETTLED'].map(s => el('option', { value: s }, TAG_MAP[s][0]))]);
      statusSel.addEventListener('change', () => { state.status = statusSel.value; table.reload(); });
      const periodIn = el('input', { type: 'text', placeholder: '周期 如 2026-01', style: { width: '130px' } });
      periodIn.addEventListener('input', debounce(() => { state.period = periodIn.value.trim(); table.reload(); }, 300));

      const table = UI.table({
        columns: [
          { title: '对账单号', key: 'bill_no', strong: true },
          { title: kind === 'company' ? '下游企业' : '上游供方', key: 'peer_name' },
          { title: '订单号', key: 'order_no', render: r => r.order_no || '-' },
          { title: '周期', key: 'period' },
          { title: '金额', num: true, render: r => fmtMoney(r.total_amount) },
          { title: '状态', render: r => billTag(r.status) },
          { title: '异议原因', render: r => r.dispute_reason || '-' },
          { title: '生成时间', key: 'create_time' },
          { title: '操作', render: r => r.status !== 'SETTLED'
            ? el('button', { class: 'btn btn-sm btn-link', onclick: () => showSettle(r) }, '结清') : (r.settle_remark || '-') }
        ],
        toolbar: { render: () => [statusSel, periodIn] },
        query: state, rowKey: 'bill_id',
        fetch: q => API.get('/api/admin/bill/list', q)
      });

      function showSettle(r) {
        UI.form({
          title: `对账结清 · ${r.bill_no}`,
          fields: [{ key: 'remark', label: '结清说明', type: 'textarea', full: true, maxlength: 200,
            hint: kind === 'company' ? '确认双方账务核对一致后结清' : '确认与供方货款结清' }],
          submitText: '确认结清',
          onSubmit: async v => {
            await API.post(`/api/admin/bill/${kind}/${r.bill_id}/settle`, { remark: v.remark });
            Toast.success('已结清');
            table.reload();
          }
        });
      }

      const wrap = el('div', null);
      wrap.appendChild(el('div', { class: 'card' }, [table.root]));
      wrap.appendChild(el('div', { class: 'hint', style: { marginTop: '8px' } },
        kind === 'company'
          ? '企业对账单基于分拨明细按企业聚合生成；对账状态由企业在线确认/异议驱动。'
          : '供方对账单基于集采总订单（一单一供方）生成；由供方在线确认/异议驱动。'));
      return wrap;
    }

    function renderLedger() {
      const wrap = el('div', null);
      /* 归档操作卡片 */
      const archCard = el('div', { class: 'card', style: { marginBottom: '12px' } });
      archCard.appendChild(el('div', { class: 'card-title' }, '履约归档（全部分拨完成 + 对账全部结清后可归档）'));
      const archRow = el('div', { style: { display: 'flex', gap: '10px', alignItems: 'center', flexWrap: 'wrap' } });
      const orderSel = el('select', { style: { minWidth: '260px' } }, [el('option', { value: '' }, '— 选择集采订单 —')]);
      const sumIn = el('input', { type: 'text', placeholder: '归档摘要（选填）', style: { width: '260px' } });
      const archBtn = el('button', { class: 'btn btn-primary btn-sm', onclick: doArchive }, '🗂 执行归档');
      archRow.appendChild(orderSel); archRow.appendChild(sumIn); archRow.appendChild(archBtn);
      archCard.appendChild(archRow);
      const archList = el('div', { style: { marginTop: '10px' } });
      archCard.appendChild(archList);
      wrap.appendChild(archCard);

      async function loadArchList() {
        const res = await API.get('/api/admin/order/list', { page: 1, page_size: 100 });
        orderSel.innerHTML = '';
        orderSel.appendChild(el('option', { value: '' }, '— 选择集采订单 —'));
        res.list.filter(o => o.status !== 'ARCHIVED').forEach(o => orderSel.appendChild(
          el('option', { value: o.order_id }, `${o.order_no}（${(TAG_MAP[o.status] || [o.status])[0]}）`)));
        const al = await API.get('/api/admin/archive/list', {});
        archList.innerHTML = '';
        if (al.list.length) {
          const tb = el('table', { class: 'tb' }, [
            el('thead', null, el('tr', null, ['订单号', '品类', '总金额', '归档时间', '摘要'].map(h => el('th', null, h)))),
            el('tbody', null, al.list.map(a => el('tr', null, [
              el('td', { class: 'strong' }, a.order_no),
              el('td', null, dictName(App.dict('ORE_CATEGORY'), a.ore_category)),
              el('td', { class: 'num' }, fmtMoney(a.total_amount)),
              el('td', null, a.archive_time),
              el('td', null, a.archive_summary || '-')
            ])))
          ]);
          archList.appendChild(el('div', { class: 'table-wrap' }, tb));
        }
      }

      async function doArchive() {
        if (!orderSel.value) { Toast.error('请选择集采订单'); return; }
        confirmDialog('归档后该集采任务全部关联单据（清单/询价/订单/分拨/物流/对账）将只读不可修改，确认归档？', async () => {
          await API.post('/api/admin/archive', { order_id: Number(orderSel.value), summary: sumIn.value.trim() });
          Toast.success('归档完成，需求全链路闭环');
          loadArchList(); ledgerTable.reload();
        });
      }
      loadArchList();

      /* 履约台账 */
      const ledCard = el('div', { class: 'card' });
      ledCard.appendChild(el('div', { class: 'card-title' }, '履约台账（按周期/企业/品类检索，支持导出）'));
      const lstate = { period: '', company: '', ore_category: '' };
      const lperiod = el('input', { type: 'text', placeholder: '周期 如 2026-01', style: { width: '130px' } });
      lperiod.addEventListener('input', debounce(() => { lstate.period = lperiod.value.trim(); ledgerTable.reload(); }, 300));
      const lcompany = el('input', { type: 'text', placeholder: '企业名称' });
      lcompany.addEventListener('input', debounce(() => { lstate.company = lcompany.value.trim(); ledgerTable.reload(); }, 300));
      const lcat = el('select', null, [el('option', { value: '' }, '全部品类'),
        ...App.dict('ORE_CATEGORY').map(d => el('option', { value: d.item_code }, d.item_name))]);
      lcat.addEventListener('change', () => { lstate.ore_category = lcat.value; ledgerTable.reload(); });
      const exportBtn = el('button', { class: 'btn btn-sm', onclick: () => API.download('/api/admin/ledger/export', lstate, '履约台账.xlsx') }, '⬇ 导出台账');

      const ledgerTable = UI.table({
        columns: [
          { title: '周期', key: 'period' },
          { title: '分拨单号', key: 'alloc_no', strong: true },
          { title: '订单号', key: 'order_no' },
          { title: '下游企业', key: 'company_name' },
          { title: '品类', render: r => dictName(App.dict('ORE_CATEGORY'), r.ore_category) },
          { title: '吨数', num: true, render: r => fmtQty(r.qty) },
          { title: '金额', num: true, render: r => fmtMoney(r.amount) },
          { title: '分拨状态', render: r => allocTag(r.status) },
          { title: '对账状态', render: r => r.bill_status ? billTag(r.bill_status) : el('span', { class: 'tag tag-gray' }, '未生成') },
          { title: '归档', render: r => r.archived ? tag('ARCHIVED') : el('span', { class: 'tag tag-gray' }, '未归档') }
        ],
        toolbar: { render: () => [lperiod, lcompany, lcat, el('span', { class: 'fb-sep' }), exportBtn] },
        query: lstate, rowKey: 'alloc_id',
        fetch: q => API.get('/api/admin/ledger', q)
      });
      ledCard.appendChild(el('div', { class: 'table-wrap' }, ledgerTable.root));
      wrap.appendChild(ledCard);
      return wrap;
    }

    renderTabs(); renderBody();
    root.appendChild(tabBar); root.appendChild(container);
  }
});

/* ---------- R1 我的分拨单 ---------- */
App.registerView('r1.alloc', {
  title: '我的分拨单', roles: ['R1'],
  async render(root) {
    const listBox = el('div', null);
    root.appendChild(listBox);

    async function reload() {
      const res = await API.get('/api/company/allocation/list', {});
      listBox.innerHTML = '';
      if (!res.list.length) {
        listBox.appendChild(el('div', { class: 'card' }, UI.empty('暂无分拨单，平台分拨后将自动下发')));
        return;
      }
      res.list.forEach(a => {
        const card = el('div', { class: 'card', style: { marginBottom: '12px' } });
        const head = el('div', { style: { display: 'flex', gap: '10px', alignItems: 'center', flexWrap: 'wrap', marginBottom: '8px' } }, [
          el('span', { class: 'strong', style: { fontSize: '14.5px' } }, a.alloc_no),
          el('span', { style: { color: 'var(--text-3)', fontSize: '13px' } }, `订单 ${a.order_no}`),
          allocTag(a.status),
          a.order_archived ? tag('ARCHIVED') : null,
          el('span', { style: { marginLeft: 'auto', color: 'var(--text-3)', fontSize: '12.5px' } }, a.create_time)
        ]);
        card.appendChild(head);
        const grid = el('div', { class: 'desc-grid', style: { gridTemplateColumns: 'repeat(5,1fr)' } }, [
          { label: '矿石品类', value: dictName(App.dict('ORE_CATEGORY'), a.ore_category) },
          { label: '分拨吨数', value: fmtQty(a.qty) + ' 吨' },
          { label: '结算单价', value: fmtMoney(a.unit_price) + ' 元/吨' },
          { label: '分拨金额', value: fmtMoney(a.amount) + ' 元' },
          { label: '交货目的地', value: a.destination || '-' }
        ].map(it => el('div', { class: 'desc-item' }, [
          el('div', { class: 'd-label' }, it.label), el('div', { class: 'd-value' }, it.value)
        ])));
        card.appendChild(grid);
        if (a.feedback) {
          card.appendChild(el('div', { style: { marginTop: '8px', padding: '8px 10px', background: 'var(--bg-2, #f7f8fa)', borderRadius: '8px', fontSize: '13px' } }, [
            el('span', { class: 'tag ' + (a.feedback.status === 'PENDING' ? 'tag-orange' : 'tag-green') },
              a.feedback.status === 'PENDING' ? '异常反馈处理中' : '异常已处理'),
            el('span', { style: { marginLeft: '8px', color: 'var(--text-2)' } }, a.feedback.description),
            a.feedback.resolve_remark ? el('span', { style: { marginLeft: '8px', color: 'var(--text-3)' } }, `平台回复：${a.feedback.resolve_remark}`) : null
          ]));
        }
        const ops = el('div', { style: { display: 'flex', gap: '8px', marginTop: '10px' } });
        if (!a.order_archived) {
          if (a.status === 'TRANSIT' || a.status === 'WAIT_CONFIRM') {
            ops.appendChild(el('button', { class: 'btn btn-primary btn-sm', onclick: () => doConfirm(a) }, '✓ 确认到货'));
            ops.appendChild(el('button', { class: 'btn btn-sm', onclick: () => showFeedback(a) }, '⚠ 到货异常反馈'));
          }
        }
        if (ops.children.length) card.appendChild(ops);
        listBox.appendChild(card);
      });
    }

    async function doConfirm(a) {
      confirmDialog(`确认分拨单 ${a.alloc_no} 货物已送达并验收无误？（${fmtQty(a.qty)} 吨 · ${fmtMoney(a.amount)} 元）`, async () => {
        await API.post(`/api/company/allocation/${a.alloc_id}/confirm`, {});
        Toast.success('到货已确认，分拨单完成');
        reload();
      });
    }

    function showFeedback(a) {
      UI.form({
        title: `到货异常反馈 · ${a.alloc_no}`,
        fields: [
          { key: 'description', label: '异常说明', type: 'textarea', required: true, full: true, maxlength: 500,
            hint: '如数量短缺、品位不符、破损等，请尽量描述具体差异' },
          { key: 'attachment', label: '附件链接（磅单/照片，选填）', type: 'text', full: true }
        ],
        submitText: '提交反馈',
        onSubmit: async v => {
          await API.post(`/api/company/allocation/${a.alloc_id}/feedback`, v);
          Toast.success('反馈已提交，平台将尽快处理');
          reload();
        }
      });
    }

    await reload();
  }
});

/* ---------- R1 我的对账单 ---------- */
App.registerView('r1.bill', {
  title: '我的对账单', roles: ['R1'],
  async render(root) {
    const table = UI.table({
      columns: [
        { title: '对账单号', key: 'bill_no', strong: true },
        { title: '周期', key: 'period' },
        { title: '金额合计', num: true, render: r => fmtMoney(r.total_amount) },
        { title: '状态', render: r => billTag(r.status) },
        { title: '异议/结清说明', render: r => r.dispute_reason || r.settle_remark || '-' },
        { title: '生成时间', key: 'create_time' },
        { title: '操作', render: r => el('div', { style: { display: 'flex', gap: '0' } }, [
          el('button', { class: 'btn btn-sm btn-link', onclick: () => showDetail(r) }, '明细'),
          r.status === 'PENDING' || r.status === 'DISPUTE'
            ? el('button', { class: 'btn btn-sm btn-link', onclick: () => doConfirm(r) }, '确认无误') : null,
          r.status !== 'SETTLED'
            ? el('button', { class: 'btn btn-sm btn-link', style: { color: 'var(--orange)' }, onclick: () => doDispute(r) }, '提出异议') : null,
          el('button', { class: 'btn btn-sm btn-link', onclick: () => API.download(`/api/company/bill/${r.bill_id}/export`, {}, `${r.bill_no}.xlsx`) }, '导出')
        ].filter(Boolean)) }
      ],
      query: {}, rowKey: 'bill_id', page_size: 10,
      fetch: q => API.get('/api/company/bill/list', q)
    });
    root.appendChild(el('div', { class: 'card' }, [table.root]));

    async function showDetail(r) {
      const fresh = (await API.get('/api/company/bill/list', {})).list.find(b => b.bill_id === r.bill_id) || r;
      const body = el('div', null);
      body.appendChild(el('div', { class: 'desc-grid', style: { gridTemplateColumns: 'repeat(4,1fr)' } }, [
        { label: '对账单号', value: fresh.bill_no }, { label: '周期', value: fresh.period || '-' },
        { label: '金额合计', value: fmtMoney(fresh.total_amount) + ' 元' }, { label: '状态', value: (TAG_MAP[fresh.status] || [fresh.status])[0] }
      ].map(it => el('div', { class: 'desc-item' }, [
        el('div', { class: 'd-label' }, it.label), el('div', { class: 'd-value' }, it.value)
      ]))));
      body.appendChild(el('div', { class: 'card-title', style: { margin: '12px 0 8px' } }, '分拨明细'));
      const tb = el('table', { class: 'tb' }, [
        el('thead', null, el('tr', null, ['分拨单号', '订单号', '品类', '吨数', '单价', '金额', '交货地'].map(h => el('th', null, h)))),
        el('tbody', null, fresh.details.map(d => el('tr', null, [
          el('td', { class: 'strong' }, d.alloc_no), el('td', null, d.order_no),
          el('td', null, dictName(App.dict('ORE_CATEGORY'), d.ore_category)),
          el('td', { class: 'num' }, fmtQty(d.qty)), el('td', { class: 'num' }, fmtMoney(d.unit_price)),
          el('td', { class: 'num' }, fmtMoney(d.amount)), el('td', null, d.destination || '-')
        ])))
      ]);
      body.appendChild(el('div', { class: 'table-wrap' }, tb));
      openModal({ title: `对账单明细 · ${fresh.bill_no}`, wide: true, body, footer: close => [el('button', { class: 'btn', onclick: close }, '关闭')] });
    }

    function doConfirm(r) {
      confirmDialog(`确认对账单 ${r.bill_no}（${fmtMoney(r.total_amount)} 元）金额核对无误？`, async () => {
        await API.post(`/api/company/bill/${r.bill_id}/confirm`, {});
        Toast.success('对账单已确认');
        table.reload();
      });
    }

    function doDispute(r) {
      UI.form({
        title: `对账异议 · ${r.bill_no}`,
        fields: [{ key: 'reason', label: '异议原因', type: 'textarea', required: true, full: true, maxlength: 300,
          hint: '请说明与分拨/锁货信息的具体差异，便于平台核对' }],
        submitText: '提交异议',
        onSubmit: async v => {
          await API.post(`/api/company/bill/${r.bill_id}/dispute`, v);
          Toast.success('异议已提交，等待平台处理');
          table.reload();
        }
      });
    }
  }
});

/* ---------- R2 供方对账记录 ---------- */
App.registerView('r2.bill', {
  title: '对账记录', roles: ['R2'],
  async render(root) {
    const table = UI.table({
      columns: [
        { title: '对账单号', key: 'bill_no', strong: true },
        { title: '订单号', key: 'order_no' },
        { title: '品类', render: r => dictName(App.dict('ORE_CATEGORY'), r.ore_category) },
        { title: '锁定吨数', num: true, render: r => fmtQty(r.total_qty) + ' 吨' },
        { title: '总金额', num: true, render: r => fmtMoney(r.total_amount) },
        { title: '周期', render: r => r.period || '-' },
        { title: '状态', render: r => billTag(r.status) },
        { title: '异议/结清说明', render: r => r.dispute_reason || r.settle_remark || '-' },
        { title: '生成时间', key: 'create_time' },
        { title: '操作', render: r => el('div', { style: { display: 'flex', gap: '0' } }, [
          r.status === 'PENDING' || r.status === 'DISPUTE'
            ? el('button', { class: 'btn btn-sm btn-link', onclick: () => doConfirm(r) }, '确认无误') : null,
          r.status !== 'SETTLED'
            ? el('button', { class: 'btn btn-sm btn-link', style: { color: 'var(--orange)' }, onclick: () => doDispute(r) }, '提出异议') : null
        ].filter(Boolean)) }
      ],
      query: {}, rowKey: 'bill_id', page_size: 10,
      fetch: q => API.get('/api/supplier/bill/list', q)
    });
    root.appendChild(el('div', { class: 'card' }, [table.root]));

    function doConfirm(r) {
      confirmDialog(`确认供方对账单 ${r.bill_no}（${fmtMoney(r.total_amount)} 元）金额无误？`, async () => {
        await API.post(`/api/supplier/bill/${r.bill_id}/confirm`, {});
        Toast.success('对账单已确认');
        table.reload();
      });
    }

    function doDispute(r) {
      UI.form({
        title: `对账异议 · ${r.bill_no}`,
        fields: [{ key: 'reason', label: '异议原因', type: 'textarea', required: true, full: true, maxlength: 300 }],
        submitText: '提交异议',
        onSubmit: async v => {
          await API.post(`/api/supplier/bill/${r.bill_id}/dispute`, v);
          Toast.success('异议已提交，等待平台处理');
          table.reload();
        }
      });
    }
  }
});
