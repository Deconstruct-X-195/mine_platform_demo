/* ============ 集采交易模块视图 (PRD-04)：R4 集采交易 / R2 集采询价任务 ============ */

/* ---------- R4 集采交易（任务 + 订单 双Tab） ---------- */
App.registerView('r4.trade', {
  title: '集采交易', roles: ['R4'],
  async render(root) {
    const tabBar = el('div', { style: { display: 'flex', gap: '8px', marginBottom: '14px' } });
    const viewKey = { task: '集采任务', order: '集采订单' };
    let curTab = sessionStorage.getItem('r4.trade.tab') || 'task';
    const container = el('div', null);

    function renderTabs() {
      tabBar.innerHTML = '';
      Object.entries(viewKey).forEach(([k, t]) => {
        tabBar.appendChild(el('button', {
          class: `btn btn-sm ${curTab === k ? 'btn-primary' : ''}`,
          onclick: () => { curTab = k; sessionStorage.setItem('r4.trade.tab', k); renderTabs(); renderBody(); }
        }, t));
      });
    }

    function renderBody() {
      container.innerHTML = '';
      container.appendChild(curTab === 'task' ? renderTaskTable() : renderOrderTable());
    }

    /* ----- 集采任务 ----- */
    function renderTaskTable() {
      const state = { ore_category: '', status: '' };
      const catSel = el('select', null, [el('option', { value: '' }, '全部品类'),
        ...App.dict('ORE_CATEGORY').map(d => el('option', { value: d.item_code }, d.item_name))]);
      catSel.addEventListener('change', () => { state.ore_category = catSel.value; table.reload(); });
      const statusSel = el('select', null, [el('option', { value: '' }, '全部状态'),
        ...['WAIT_QUOTE', 'QUOTING', 'LOCKED'].map(s => el('option', { value: s }, TAG_MAP[s][0]))]);
      statusSel.addEventListener('change', () => { state.status = statusSel.value; table.reload(); });
      const newBtn = el('button', { class: 'btn btn-primary btn-sm', onclick: showInquiryWizard }, '⚖ 发起询价');

      const table = UI.table({
        columns: [
          { title: '任务号', key: 'task_no', strong: true },
          { title: '清单号', key: 'list_no' },
          { title: '品类', render: r => dictName(App.dict('ORE_CATEGORY'), r.ore_category) },
          { title: '需求吨数', num: true, render: r => fmtQty(r.total_qty) + ' 吨' },
          { title: '指标要求', render: r => r.indicator_req || '-' },
          { title: '要求供货时间', render: r => r.supply_time || '-' },
          { title: '报价截止', key: 'quote_deadline' },
          { title: '询价进度', num: true, render: r => `${r.quoted_total}/${r.inquiry_total} 家已报价` },
          { title: '状态', render: r => tag(r.status) },
          { title: '操作', render: r => el('div', { style: { display: 'flex', gap: '0', flexWrap: 'wrap' } }, [
            el('button', { class: 'btn btn-sm btn-link', onclick: () => showCompare(r) }, '比价'),
            ['WAIT_QUOTE', 'QUOTING'].includes(r.status)
              ? el('button', { class: 'btn btn-sm btn-link', style: { color: 'var(--orange)' }, onclick: () => showLock(r) }, '锁货') : null,
            el('button', { class: 'btn btn-sm btn-link', onclick: () => API.download(`/api/admin/task/${r.task_id}/compare/export`, {}, `报价对比表-${r.task_no}.xlsx`) }, '导出')
          ].filter(Boolean)) }
        ],
        toolbar: { render: () => [catSel, statusSel, el('span', { class: 'fb-sep' }), newBtn] },
        query: state, rowKey: 'task_id',
        fetch: q => API.get('/api/admin/task/list', q)
      });
      return el('div', { class: 'card' }, [table.root]);
    }

    /* 发起询价向导：选清单 → 选货源 → 填截止时间 */
    async function showInquiryWizard() {
      let lists = [];
      try {
        const res = await API.get('/api/admin/collective/list', { page: 1, page_size: 100 });
        lists = res.list.filter(x => x.status === 'ACTIVE');
      } catch (e) { return; }
      if (!lists.length) { Toast.info('暂无待询价的集采清单，请先在「集采清单」中生成'); return; }

      const body = el('div', null);
      const listSel = el('select', null, [el('option', { value: '' }, '请选择集采清单'),
        ...lists.map(l => el('option', { value: l.list_id },
          `${l.list_no}（${l.period_type === 'MONTH' ? '月度' : '季度'} ${l.period} · ${l.ore_categories.map(c => dictName(App.dict('ORE_CATEGORY'), c)).join('/')} · ${fmtQty(l.total_qty)}吨）`))]);
      const resBox = el('div', { class: 'pick-box', style: { margin: '10px 0', maxHeight: '220px', overflowY: 'auto', border: '1px solid var(--line)', borderRadius: '8px', padding: '8px', display: 'none' } });
      const hint = el('div', { class: 'hint', style: { margin: '6px 0' } }, '');
      const dlIn = el('input', { type: 'text', placeholder: '如 2026-03-31 18:00' });
      const indIn = el('input', { type: 'text', placeholder: '如 TFe>=62%，水分<8%（可空）' });
      const stIn = el('input', { type: 'text', placeholder: '如 2026-04（可空）' });

      listSel.addEventListener('change', async () => {
        const lid = Number(listSel.value);
        resBox.innerHTML = ''; hint.textContent = '';
        if (!lid) { resBox.style.display = 'none'; return; }
        const head = lists.find(l => l.list_id === lid);
        const cat = head.ore_categories[0];
        const res = await API.get('/api/admin/resource/list', { status: 'ON_SHELF', ore_category: cat, page: 1, page_size: 100 });
        if (!res.list.length) {
          hint.textContent = '该品类暂无在架货源，请先通知供方上架货源';
          resBox.style.display = 'none';
          return;
        }
        res.list.forEach(r => {
          const cb = el('input', { type: 'checkbox', value: r.resource_id, style: { marginRight: '8px' } });
          resBox.appendChild(el('label', { style: { display: 'flex', alignItems: 'center', padding: '7px 6px', borderBottom: '1px solid var(--line)', cursor: 'pointer', fontSize: '13px' } }, [
            cb,
            el('span', { style: { flex: '1' } }, [
              r.is_preferred ? el('span', { class: 'tag tag-orange', style: { marginRight: '6px' } }, '★ 优选') : null,
              `${r.company_name} · ${r.origin} · ${r.grade} · 可供${fmtQty(r.max_qty)}吨`
            ])
          ]));
        });
        resBox.style.display = 'block';
      });

      body.appendChild(el('div', { class: 'field' }, [el('label', null, [el('span', { class: 'req' }, '*'), ' 选择集采清单']), listSel]));
      body.appendChild(hint);
      body.appendChild(resBox);
      body.appendChild(el('div', { class: 'form-grid', style: { marginTop: '10px' } }, [
        el('div', { class: 'field' }, [el('label', null, [el('span', { class: 'req' }, '*'), ' 报价截止时间']), dlIn]),
        el('div', { class: 'field' }, [el('label', null, '指标要求'), indIn]),
        el('div', { class: 'field full' }, [el('label', null, '要求供货时间'), stIn])
      ]));

      openModal({
        title: '发起集采询价', wide: true, body,
        footer: close => [
          el('button', { class: 'btn', onclick: close }, '取消'),
          el('button', {
            class: 'btn btn-primary', onclick: async () => {
              const lid = Number(listSel.value);
              if (!lid) { Toast.error('请选择集采清单'); return; }
              const rids = $$('input[type=checkbox]:checked', resBox).map(cb => Number(cb.value));
              if (!rids.length) { Toast.error('请至少勾选1家供货方货源'); return; }
              if (!dlIn.value.trim()) { Toast.error('请填写报价截止时间'); return; }
              try {
                const res = await API.post('/api/admin/task/create', {
                  list_id: lid, resource_ids: rids,
                  quote_deadline: dlIn.value.trim(),
                  indicator_req: indIn.value.trim(), supply_time: stIn.value.trim()
                });
                Toast.success(`询价已下发 ${res.inquiry_count} 家供方`);
                close(); renderBody();
              } catch (e) { /* toast 已提示 */ }
            }
          }, '确认下发询价')
        ]
      });
    }

    /* 比价视图 */
    async function showCompare(t) {
      const data = await API.get(`/api/admin/task/${t.task_id}/compare`);
      const body = el('div', null);
      body.appendChild(el('div', { class: 'hint', style: { marginBottom: '8px' } },
        `需求：${dictName(App.dict('ORE_CATEGORY'), data.task.ore_category)} ${fmtQty(data.task.total_qty)}吨 · 指标 ${data.task.indicator_req || '-'} · 供货 ${data.task.supply_time || '-'} · 截止 ${data.task.quote_deadline}`));
      const tb = el('table', { class: 'tb' }, [
        el('thead', null, el('tr', null, ['供方', '产地/品位', '报价单价(元/吨)', '可供吨数', '供货周期', '指标承诺', '状态'].map(h => el('th', null, h)))),
        el('tbody', null, data.compares.length ? data.compares.map(c => el('tr', null, [
          el('td', { class: 'strong' }, c.company_name),
          el('td', null, `${c.origin || '-'} / ${c.grade || '-'}`),
          el('td', { class: 'num' }, c.quote_price != null ? fmtQty(c.quote_price) : '未报价'),
          el('td', { class: 'num' }, c.quote_qty != null ? fmtQty(c.quote_qty) : '-'),
          el('td', null, c.supply_period || '-'),
          el('td', null, c.indicator_commit || '-'),
          el('td', null, tag(c.status))
        ])) : el('tr', null, el('td', { colspan: 7 }, UI.empty('暂无供方报价'))))
      ]);
      body.appendChild(el('div', { class: 'table-wrap' }, tb));
      openModal({
        title: `比价工作台 · ${data.task.task_no}`, wide: true, body,
        footer: close => [el('button', { class: 'btn', onclick: close }, '关闭')]
      });
    }

    /* 锁货确认 */
    async function showLock(t) {
      const data = await API.get(`/api/admin/task/${t.task_id}/compare`);
      const quoted = data.compares.filter(c => c.status === 'QUOTED');
      if (!quoted.length) { Toast.info('暂无可锁货的报价（供方尚未报价）'); return; }
      const body = el('div', null);
      body.appendChild(el('div', { class: 'hint', style: { marginBottom: '8px' } },
        `需求总量 ${fmtQty(t.total_qty)} 吨 · 勾选供方并填写锁货单价与吨数，合计须覆盖需求量`));
      const rows = [];
      const sumSpan = el('b', { style: { color: 'var(--primary)' } }, '0.00');
      function refreshSum() {
        const s = rows.reduce((acc, r) => acc + (r.checked ? (Number(r.qtyIn.value) || 0) : 0), 0);
        sumSpan.textContent = fmtQty(s) + ' 吨';
        sumSpan.style.color = s + 1e-9 >= t.total_qty ? 'var(--green)' : 'var(--red)';
      }
      quoted.forEach(c => {
        const cb = el('input', { type: 'checkbox', style: { marginRight: '8px' } });
        const priceIn = el('input', { type: 'number', step: '0.01', min: '0', value: c.quote_price, style: { width: '110px' } });
        const qtyIn = el('input', { type: 'number', step: '0.01', min: '0', value: c.quote_qty, style: { width: '110px' } });
        const row = { cb, priceIn, qtyIn, iid: c.inquiry_id, checked: false };
        cb.addEventListener('change', () => { row.checked = cb.checked; refreshSum(); });
        qtyIn.addEventListener('input', refreshSum);
        rows.push(row);
        body.appendChild(el('div', { style: { display: 'flex', alignItems: 'center', gap: '10px', padding: '9px 6px', borderBottom: '1px solid var(--line)', flexWrap: 'wrap' } }, [
          cb,
          el('span', { style: { flex: '1', minWidth: '160px', fontSize: '13px' } },
            `${c.company_name}（报价 ${fmtQty(c.quote_price)} 元/吨 · 可供 ${fmtQty(c.quote_qty)} 吨）`),
          el('span', { style: { fontSize: '12px', color: 'var(--text-3)' } }, '锁定价'),
          priceIn,
          el('span', { style: { fontSize: '12px', color: 'var(--text-3)' } }, '吨数'),
          qtyIn
        ]));
      });
      body.appendChild(el('div', { style: { padding: '10px 6px', fontSize: '13.5px' } },
        ['当前合计：', sumSpan, ` / 需求 ${fmtQty(t.total_qty)} 吨`]));

      openModal({
        title: `锁货确认 · ${t.task_no}`, wide: true, body,
        footer: close => [
          el('button', { class: 'btn', onclick: close }, '取消'),
          el('button', {
            class: 'btn btn-primary', onclick: async () => {
              const locks = rows.filter(r => r.checked).map(r => ({
                inquiry_id: r.iid, unit_price: Number(r.priceIn.value), qty: Number(r.qtyIn.value)
              }));
              if (!locks.length) { Toast.error('请至少勾选一家供方'); return; }
              try {
                const res = await API.post(`/api/admin/task/${t.task_id}/lock`, { locks });
                Toast.success(`锁货成功，已生成 ${res.orders.length} 张集采订单`);
                close(); renderBody();
              } catch (e) { /* toast 已提示 */ }
            }
          }, '确认锁货')
        ]
      });
    }

    /* ----- 集采订单 ----- */
    function renderOrderTable() {
      const state = { status: '' };
      const statusSel = el('select', null, [el('option', { value: '' }, '全部状态'),
        ...['LOCKED', 'IN_LOGISTICS', 'LOGI_DONE', 'ARCHIVED'].map(s => el('option', { value: s }, TAG_MAP[s][0]))]);
      statusSel.addEventListener('change', () => { state.status = statusSel.value; table.reload(); });
      const table = UI.table({
        columns: [
          { title: '订单号', key: 'order_no', strong: true },
          { title: '任务号', key: 'task_no' },
          { title: '供货方', key: 'supplier_name' },
          { title: '品类', render: r => dictName(App.dict('ORE_CATEGORY'), r.ore_category) },
          { title: '锁定吨数', num: true, render: r => fmtQty(r.total_qty) },
          { title: '锁定单价', num: true, render: r => fmtMoney(r.unit_price) },
          { title: '总金额', num: true, render: r => fmtMoney(r.total_amount) },
          { title: '供货时间', render: r => r.supply_time || '-' },
          { title: '状态', render: r => tag(r.status) },
          { title: '操作', render: r => el('button', { class: 'btn btn-sm btn-link', onclick: () => showOrderDetail(r) }, '详情') }
        ],
        toolbar: { render: () => [statusSel] },
        query: state, rowKey: 'order_id',
        fetch: q => API.get('/api/admin/order/list', q)
      });
      return el('div', { class: 'card' }, [table.root]);
    }

    async function showOrderDetail(o) {
      const d = await API.get(`/api/admin/order/${o.order_id}`);
      const body = el('div', null);
      const grid = el('div', { class: 'desc-grid' }, [
        { label: '订单号', value: d.order_no }, { label: '关联清单号', value: d.list_no || '-' },
        { label: '供货方', value: d.supplier_name },
        { label: '矿石品类', value: dictName(App.dict('ORE_CATEGORY'), d.ore_category) },
        { label: '锁定总吨数', value: fmtQty(d.total_qty) + ' 吨' },
        { label: '锁定单价', value: fmtMoney(d.unit_price) + '/吨' },
        { label: '总金额', value: fmtMoney(d.total_amount) },
        { label: '供货时间', value: d.supply_time || '-' },
        { label: '状态', render: () => tag(d.status) },
        { label: '下单时间', value: fmtTime(d.create_time) }
      ].map(it => {
        const dv = el('div', { class: 'd-value' });
        const v = it.render ? it.render() : it.value;
        if (v instanceof Node) dv.appendChild(v); else dv.textContent = v;
        return el('div', { class: 'desc-item' }, [el('div', { class: 'd-label' }, it.label), dv]);
      }));
      body.appendChild(grid);
      body.appendChild(el('div', { class: 'card-title', style: { marginTop: '14px' } }, '下游企业申报明细（仅平台可见）'));
      const tb = el('table', { class: 'tb' }, [
        el('thead', null, el('tr', null, ['下游企业', '品类', '申报吨数', '品位要求', '期望到货'].map(h => el('th', null, h)))),
        el('tbody', null, d.details.length ? d.details.map(x => el('tr', null, [
          el('td', { class: 'strong' }, x.company_name),
          el('td', null, dictName(App.dict('ORE_CATEGORY'), x.ore_category)),
          el('td', { class: 'num' }, fmtQty(x.qty)),
          el('td', null, x.grade_req || '-'),
          el('td', null, fmtDate(x.expected_arrival))
        ])) : el('tr', null, el('td', { colspan: 5 }, UI.empty())))
      ]);
      body.appendChild(el('div', { class: 'table-wrap' }, tb));
      openModal({
        title: `集采订单 · ${d.order_no}`, wide: true, body,
        footer: close => [el('button', { class: 'btn', onclick: close }, '关闭')]
      });
    }

    renderTabs();
    renderBody();
    root.appendChild(tabBar);
    root.appendChild(container);
  }
});

/* ---------- R2 集采询价任务 ---------- */
App.registerView('r2.inquiry', {
  title: '集采询价任务', roles: ['R2'],
  async render(root) {
    const state = { status: '' };
    const statusSel = el('select', null, [el('option', { value: '' }, '全部状态'),
      ...['WAIT_QUOTE', 'QUOTED', 'REFUSED', 'NOT_SELECTED', 'LOCKED'].map(s => el('option', { value: s }, TAG_MAP[s][0]))]);
    statusSel.addEventListener('change', () => { state.status = statusSel.value; table.reload(); });

    const table = UI.table({
      columns: [
        { title: '任务号', key: 'task_no', strong: true },
        { title: '品类', render: r => dictName(App.dict('ORE_CATEGORY'), r.ore_category) },
        { title: '需求总吨数', num: true, render: r => fmtQty(r.total_qty) + ' 吨' },
        { title: '指标要求', render: r => r.indicator_req || '-' },
        { title: '要求供货时间', render: r => r.supply_time || '-' },
        { title: '报价截止', key: 'quote_deadline' },
        { title: '我的报价', render: r => r.quote_price != null
          ? `${fmtMoney(r.quote_price)}/吨 · ${fmtQty(r.quote_qty)}吨`
          : (r.status === 'REFUSED' ? el('span', { title: '拒绝原因: ' + r.refuse_reason, style: { color: 'var(--red)', fontSize: '12px' } }, '⚠ 已拒绝') : '-') },
        { title: '状态', render: r => tag(r.status) },
        { title: '操作', render: r => el('div', { style: { display: 'flex', gap: '0', flexWrap: 'wrap' } }, [
          r.status === 'WAIT_QUOTE' ? el('button', { class: 'btn btn-sm btn-link', style: { color: 'var(--green)' }, onclick: () => showQuote(r, false) }, '提交报价') : null,
          r.status === 'QUOTED' ? el('button', { class: 'btn btn-sm btn-link', onclick: () => showQuote(r, true) }, '修改报价') : null,
          ['WAIT_QUOTE', 'QUOTED'].includes(r.status) ? el('button', { class: 'btn btn-sm btn-link', style: { color: 'var(--red)' }, onclick: () => doRefuse(r) }, '拒绝询价') : null,
          r.status === 'LOCKED' ? el('span', { style: { color: 'var(--green)', fontSize: '12px', alignSelf: 'center' } }, '★ 已确认锁货') : null
        ].filter(Boolean)) }
      ],
      toolbar: { render: () => [statusSel] },
      query: state, rowKey: 'inquiry_id',
      fetch: q => API.get('/api/supplier/inquiry/list', q)
    });
    root.appendChild(el('div', { class: 'card' }, [
      el('div', { class: 'hint', style: { margin: '0 0 10px' } },
        '平台集采询价 · 请在报价截止时间前提交报价；报价截止前可修改报价（保留历史版本）'),
      table.root
    ]));

    function quoteFields(r, isModify) {
      return [
        { key: 'quote_price', label: '报价单价（元/吨）', type: 'number', required: true, value: isModify ? r.quote_price : '', hint: '保留2位小数' },
        { key: 'quote_qty', label: '可供货吨数', type: 'number', required: true, value: isModify ? r.quote_qty : '',
          hint: r.resource_max_qty ? `不可超过货源可供应量 ${fmtQty(r.resource_max_qty)} 吨` : '' },
        { key: 'supply_period', label: '供货周期', type: 'text', required: true, value: isModify ? r.supply_period : '', placeholder: '如 2026-03 ~ 2026-04' },
        { key: 'indicator_commit', label: '指标承诺', type: 'text', value: isModify ? r.indicator_commit : '', placeholder: '品位、水分等承诺值（可空）' },
        { key: 'remark', label: '备注', type: 'textarea', full: true, value: isModify ? r.remark : '', maxlength: 500 }
      ];
    }

    function showQuote(r, isModify) {
      UI.form({
        title: `${isModify ? '修改报价' : '提交报价'} · ${r.task_no} ${dictName(App.dict('ORE_CATEGORY'), r.ore_category)} ${fmtQty(r.total_qty)}吨`,
        fields: quoteFields(r, isModify), wide: true,
        submitText: isModify ? '保存修改' : '提交报价',
        onSubmit: async v => {
          if (isModify) await API.put(`/api/supplier/inquiry/${r.inquiry_id}/quote`, v);
          else await API.post(`/api/supplier/inquiry/${r.inquiry_id}/quote`, v);
          Toast.success(isModify ? '报价已更新' : '报价提交成功');
          table.reload();
        }
      });
    }

    function doRefuse(r) {
      UI.form({
        title: `拒绝询价 · ${r.task_no}`,
        fields: [{ key: 'reason', label: '拒绝原因', type: 'textarea', required: true, full: true, hint: '必填，将展示给平台' }],
        submitText: '确认拒绝',
        onSubmit: async v => {
          await API.post(`/api/supplier/inquiry/${r.inquiry_id}/refuse`, { reason: v.reason });
          Toast.success('已拒绝本次询价');
          table.reload();
        }
      });
    }
  }
});
