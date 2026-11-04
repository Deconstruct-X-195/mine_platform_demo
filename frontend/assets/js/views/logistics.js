/* ============ 物流跟踪模块视图 (PRD-05)：R4 物流看板 / R3 我的物流任务 / R1 物流进度 ============ */

const LOGI_PHASES = [
  ['NOT_STARTED', '未启运'], ['IN_TRANSIT', '海运/港口在途'],
  ['WAREHOUSED', '已入仓储'], ['DELIVERED', '已送达']
];

/* ---------- R4 物流看板 ---------- */
App.registerView('r4.logistics', {
  title: '物流看板', roles: ['R4'],
  async render(root) {
    /* 统计卡 */
    const statRow = el('div', { class: 'stat-row', style: { display: 'grid', gridTemplateColumns: 'repeat(5,1fr)', gap: '10px', marginBottom: '14px' } });
    function renderStats(st) {
      statRow.innerHTML = '';
      [['全部任务', st.total, ''], ...LOGI_PHASES.map(([k, label]) => [label, st[k], ''])]
        .forEach(([label, n]) => statRow.appendChild(el('div', { class: 'stat-card' }, [
          el('div', { class: 'stat-num' }, String(n)),
          el('div', { class: 'stat-label' }, label)
        ])));
    }

    const state = { phase: '', supplier: '', dest_port: '', order_no: '' };
    const phaseSel = el('select', null, [el('option', { value: '' }, '全部阶段'),
      ...LOGI_PHASES.map(([k, label]) => el('option', { value: k }, label))]);
    phaseSel.addEventListener('change', () => { state.phase = phaseSel.value; table.reload(); });
    const supplierIn = el('input', { type: 'text', placeholder: '供方名称' });
    const debounceReload = debounce(() => table.reload(), 400);
    supplierIn.addEventListener('input', () => { state.supplier = supplierIn.value.trim(); debounceReload(); });
    const portIn = el('input', { type: 'text', placeholder: '目的港口' });
    portIn.addEventListener('input', () => { state.dest_port = portIn.value.trim(); debounceReload(); });
    const orderIn = el('input', { type: 'text', placeholder: '订单号' });
    orderIn.addEventListener('input', () => { state.order_no = orderIn.value.trim(); debounceReload(); });
    const newBtn = el('button', { class: 'btn btn-primary btn-sm', onclick: showCreateWizard }, '＋ 创建物流任务');

    const table = UI.table({
      columns: [
        { title: '物流单号', key: 'logi_no', strong: true },
        { title: '订单号', key: 'order_no' },
        { title: '供货方', key: 'supplier_name' },
        { title: '品类', render: r => dictName(App.dict('ORE_CATEGORY'), r.ore_category) },
        { title: '吨数', num: true, render: r => fmtQty(r.total_qty) },
        { title: '当前节点', render: r => el('b', null, r.current_name) },
        { title: '阶段', render: r => el('span', { class: 'tag ' + ({ NOT_STARTED: 'gray', IN_TRANSIT: 'blue', WAREHOUSED: 'orange', DELIVERED: 'green' }[r.phase] || 'gray') },
          (LOGI_PHASES.find(p => p[0] === r.phase) || ['', r.phase])[1]) },
        { title: '配套方(海/港/储/陆)', render: r => {
            const p = r.partners || {};
            return [p.sea_partner_id, p.port_partner_id, p.warehouse_partner_id, p.land_partner_id].filter(Boolean).join(' / ') || '-';
          } },
        { title: '操作', render: r => el('div', { style: { display: 'flex', gap: '0' } }, [
          el('button', { class: 'btn btn-sm btn-link', onclick: () => showDetail(r.logi_id) }, '详情')
        ]) }
      ],
      toolbar: { render: () => [phaseSel, supplierIn, portIn, orderIn, el('span', { class: 'fb-sep' }), newBtn] },
      query: state, rowKey: 'logi_id',
      fetch: async q => {
        const res = await API.get('/api/admin/logistics/board', q);
        renderStats(res.stats || {});
        return res;
      }
    });

    /* 创建物流任务：选择已锁货订单 + 分配四方配套方 */
    async function showCreateWizard() {
      let orders = [];
      try {
        const res = await API.get('/api/admin/order/list', { status: 'LOCKED', page: 1, page_size: 100 });
        const board = await API.get('/api/admin/logistics/board', { page: 1, page_size: 100 });
        const has = new Set(board.list.map(x => x.order_id));
        orders = res.list.filter(o => !has.has(o.order_id));
      } catch (e) { return; }
      if (!orders.length) { Toast.info('暂无待建物流任务的已锁货订单'); return; }

      const partners = await API.get('/api/admin/company/list', { company_type: 'PARTNER', audit_status: 'APPROVED', page: 1, page_size: 100 });
      if (!partners.list.length) { Toast.info('暂无资质审核通过的履约配套方，请先在企业管理中完成审核'); return; }
      const pOpts = partners.list.map(c => el('option', { value: c.company_id }, c.company_name));

      const orderSel = el('select', null, [el('option', { value: '' }, '请选择已锁货订单'),
        ...orders.map(o => el('option', { value: o.order_id },
          `${o.order_no}（${dictName(App.dict('ORE_CATEGORY'), o.ore_category)} ${fmtQty(o.total_qty)}吨 · ${o.supplier_name}）`))]);
      const mk = (label, hint) => {
        const s = el('select', null, [el('option', { value: '' }, hint || '可不分配'), ...pOpts]);
        return el('div', { class: 'field' }, [el('label', null, label), s]);
      };
      const seaS = mk('海运承运方'); const portS = mk('港口装卸方');
      const whS = mk('仓储服务方'); const landS = mk('陆运配送方');
      const fromIn = el('input', { type: 'text', placeholder: '如 河北承德' });
      const destPortIn = el('input', { type: 'text', placeholder: '如 曹妃甸港' });
      const planIn = el('input', { type: 'text', placeholder: '如 2026-03-15 10:00' });
      const whIn = el('input', { type: 'text', placeholder: '如 曹妃甸港区一号仓' });
      const destIn = el('input', { type: 'text', placeholder: '如下游企业料场' });

      const body = el('div', null, [
        el('div', { class: 'field' }, [el('label', null, [el('span', { class: 'req' }, '*'), ' 选择集采订单']), orderSel]),
        el('div', { class: 'form-grid' }, [
          el('div', { class: 'field' }, [el('label', null, '起运地'), fromIn]),
          el('div', { class: 'field' }, [el('label', null, '目的港口'), destPortIn]),
          el('div', { class: 'field' }, [el('label', null, '计划到港时间'), planIn]),
          el('div', { class: 'field' }, [el('label', null, '入储仓库'), whIn]),
          el('div', { class: 'field full' }, [el('label', null, '最终交货地'), destIn])
        ]),
        el('div', { class: 'card-title' }, '分配履约配套方（至少一家）'),
        el('div', { class: 'form-grid' }, [seaS, portS, whS, landS])
      ]);

      openModal({
        title: '创建物流任务', wide: true, body,
        footer: close => [
          el('button', { class: 'btn', onclick: close }, '取消'),
          el('button', {
            class: 'btn btn-primary', onclick: async () => {
              if (!orderSel.value) { Toast.error('请选择订单'); return; }
              try {
                await API.post('/api/admin/logistics/create', {
                  order_id: Number(orderSel.value),
                  sea_partner_id: seaS.querySelector('select').value || null,
                  port_partner_id: portS.querySelector('select').value || null,
                  warehouse_partner_id: whS.querySelector('select').value || null,
                  land_partner_id: landS.querySelector('select').value || null,
                  from_place: fromIn.value.trim(), dest_port: destPortIn.value.trim(),
                  plan_arrival: planIn.value.trim(), warehouse: whIn.value.trim(),
                  dest_place: destIn.value.trim()
                });
                Toast.success('物流任务已创建，7个节点待推进');
                close(); table.reload();
              } catch (e) { /* toast 已提示 */ }
            }
          }, '确认创建')
        ]
      });
    }

    /* 详情：订单信息 + 7节点 + 附件 + 回退 */
    async function showDetail(lid) {
      const d = await API.get(`/api/admin/logistics/${lid}`);
      const body = el('div', null);
      const grid = el('div', { class: 'desc-grid', style: { gridTemplateColumns: 'repeat(3,1fr)' } }, [
        { label: '物流单号', value: d.logi_no }, { label: '订单号', value: d.order_no },
        { label: '供货方', value: d.supplier_name },
        { label: '起运地', value: d.from_place || '-' }, { label: '目的港口', value: d.dest_port || '-' },
        { label: '计划到港', value: d.plan_arrival || '-' },
        { label: '入储仓库', value: d.warehouse || '-' }, { label: '最终交货地', value: d.dest_place || '-' },
        { label: '配套方', value: [d.sea_partner_id, d.port_partner_id, d.warehouse_partner_id, d.land_partner_id].filter(Boolean).join(' / ') || '-' }
      ].map(it => el('div', { class: 'desc-item' }, [
        el('div', { class: 'd-label' }, it.label), el('div', { class: 'd-value' }, it.value)
      ])));
      body.appendChild(grid);
      body.appendChild(el('div', { class: 'card-title', style: { margin: '12px 0 8px' } }, '物流节点（N1 → N7）'));
      body.appendChild(UI.steps(d.nodes.map(n => ({
        code: 'N' + n.node_code, name: n.node_name,
        time: n.actual_time || '', done: n.status === 'DONE', cur: n.node_code === d.current_node + 1
      }))));
      const doneNodes = d.nodes.filter(n => n.status === 'DONE');
      if (doneNodes.length) {
        body.appendChild(el('div', { class: 'card-title', style: { margin: '12px 0 8px' } }, '节点单据'));
        doneNodes.forEach(n => {
          body.appendChild(el('div', { style: { display: 'flex', gap: '10px', alignItems: 'flex-start', padding: '7px 0', borderBottom: '1px solid var(--line)', fontSize: '13px' } }, [
            el('span', { class: 'tag tag-blue', style: { flexShrink: 0 } }, `N${n.node_code} ${n.node_name}`),
            n.attachments && n.attachments.length ? fileLinks(n.attachments) : el('span', { style: { color: 'var(--text-3)' } }, '无单据')
          ]));
        });
      }
      openModal({
        title: `物流任务 · ${d.logi_no}`, wide: true, body,
        footer: close => [
          d.current_node > 0 ? el('button', {
            class: 'btn', style: { color: 'var(--red)' }, onclick: () => showRollback(d, close)
          }, '↩ 授权回退') : null,
          el('button', { class: 'btn', onclick: close }, '关闭')
        ].filter(Boolean)
      });
    }

    function showRollback(d, closeDetail) {
      UI.form({
        title: `授权回退 · ${d.logi_no}（当前 N${d.current_node}）`,
        fields: [
          { key: 'node_code', label: '回退至节点', type: 'select', required: true,
            options: d.nodes.filter(n => n.node_code < d.current_node)
              .map(n => ({ value: n.node_code, label: `N${n.node_code} ${n.node_name}` })) },
          { key: 'reason', label: '回退原因', type: 'textarea', required: true, full: true }
        ],
        submitText: '确认回退',
        onSubmit: async v => {
          await API.post(`/api/admin/logistics/${d.logi_id}/rollback`,
            { node_code: Number(v.node_code), reason: v.reason });
          Toast.success('已回退，后续节点重置为待推进');
          closeDetail && closeDetail();
          table.reload();
        }
      });
    }

    root.appendChild(statRow);
    root.appendChild(el('div', { class: 'card' }, [table.root]));
  }
});

/* ---------- R3 我的物流任务 ---------- */
App.registerView('r3.logistics', {
  title: '我的物流任务', roles: ['R3'],
  async render(root) {
    const table = UI.table({
      columns: [
        { title: '物流单号', key: 'logi_no', strong: true },
        { title: '订单号', key: 'order_no' },
        { title: '供货方', key: 'supplier_name' },
        { title: '品类/吨数', render: r => `${dictName(App.dict('ORE_CATEGORY'), r.ore_category)} / ${fmtQty(r.total_qty)}吨` },
        { title: '我的角色', render: r => el('div', { style: { display: 'flex', gap: '4px', flexWrap: 'wrap' } }, r.my_roles.map(x => el('span', { class: 'tag tag-orange' }, x))) },
        { title: '当前进度', render: r => el('b', null, r.current_name) },
        { title: '下一节点', render: r => r.next_node
          ? el('span', null, `N${r.next_node.node_code} ${r.next_node.node_name}`,
            r.mine_to_do ? el('span', { class: 'tag tag-green', style: { marginLeft: '4px' } }, '待我操作') : null)
          : el('span', { class: 'tag tag-green' }, '全部完成') },
        { title: '操作', render: r => el('div', { style: { display: 'flex', gap: '0' } }, [
          r.mine_to_do ? el('button', { class: 'btn btn-sm btn-link', style: { color: 'var(--green)', fontWeight: 600 },
            onclick: () => showAdvance(r) }, `推进N${r.next_node.node_code}`) : null,
          el('button', { class: 'btn btn-sm btn-link', onclick: () => showNodes(r.logi_id) }, '节点明细')
        ].filter(Boolean)) }
      ],
      rowKey: 'logi_id',
      fetch: q => API.get('/api/partner/logistics/list', q)
    });
    root.appendChild(el('div', { class: 'card' }, [
      el('div', { class: 'hint', style: { margin: '0 0 10px' } },
        '按 N1→N7 顺序推进物流节点，仅可操作分配给本企业的节点；推进时建议上传对应单据'),
      table.root
    ]));

    function showAdvance(r) {
      const code = r.next_node.node_code;
      UI.form({
        title: `推进节点 · N${code} ${r.next_node.node_name}（${r.logi_no}）`,
        wide: true,
        fields: [
          { key: 'actual_time', label: '实际完成时间', type: 'text', required: true,
            placeholder: 'YYYY-MM-DD HH:MM，如 2026-03-05 14:30' },
          { key: 'attachments', label: '随附单据（舱单/卸货凭证/入仓单等）', type: 'file', full: true }
        ],
        submitText: `确认完成 N${code}`,
        onSubmit: async v => {
          await API.post(`/api/partner/logistics/${r.logi_id}/advance`, {
            node_code: code,
            actual_time: (v.actual_time || '').trim(),
            attachments: (v.attachments || []).map(f => ({ doc_type: 'DOC', file_url: f.file_url, file_name: f.file_name }))
          });
          Toast.success(`N${code} ${r.next_node.node_name} 已完成`);
          table.reload();
        }
      });
    }

    async function showNodes(lid) {
      const d = await API.get(`/api/partner/logistics/${lid}/nodes`);
      const body = el('div', null);
      body.appendChild(UI.steps(d.nodes.map(n => ({
        code: 'N' + n.node_code, name: n.node_name,
        time: n.actual_time || '', done: n.status === 'DONE', cur: n.node_code === d.current_node + 1
      }))));
      const mine = d.nodes.filter(n => n.status === 'DONE' && n.attachments && n.attachments.length);
      if (mine.length) {
        body.appendChild(el('div', { class: 'card-title', style: { margin: '12px 0 8px' } }, '已完成节点单据'));
        mine.forEach(n => body.appendChild(el('div', { style: { display: 'flex', gap: '10px', padding: '6px 0', borderBottom: '1px solid var(--line)', fontSize: '13px', alignItems: 'flex-start' } }, [
          el('span', { class: 'tag tag-blue', style: { flexShrink: 0 } }, `N${n.node_code}`),
          fileLinks(n.attachments)
        ])));
      }
      openModal({
        title: `节点明细 · ${d.logi_no}`, wide: true, body,
        footer: close => [el('button', { class: 'btn', onclick: close }, '关闭')]
      });
    }
  }
});

/* ---------- R1 物流进度（下游只读） ---------- */
App.registerView('r1.logistics', {
  title: '物流进度', roles: ['R1'],
  async render(root) {
    const wrap = el('div', null, [UI.loading()]);
    root.appendChild(wrap);
    const res = await API.get('/api/company/logistics/list');
    wrap.innerHTML = '';
    if (!res.list.length) {
      wrap.appendChild(UI.empty('暂无分拨物流记录，货物分拨后可在此查看配送进度'));
      return;
    }
    res.list.forEach(item => {
      const card = el('div', { class: 'card', style: { marginBottom: '12px' } });
      card.appendChild(el('div', { style: { display: 'flex', gap: '12px', alignItems: 'center', flexWrap: 'wrap' } }, [
        el('b', null, item.alloc_no),
        el('span', { class: 'tag tag-blue' }, dictName(App.dict('ORE_CATEGORY'), item.ore_category)),
        el('span', { style: { fontSize: '13px' } }, `${fmtQty(item.qty)} 吨 → ${item.destination || '-'}`),
        item.logistics ? el('span', { class: 'tag ' + (item.logistics.phase === 'DELIVERED' ? 'tag-green' : 'tag-orange') },
          item.logistics.phase === 'DELIVERED' ? '已送达' : '配送中') : null
      ]));
      if (item.logistics) {
        card.appendChild(el('div', { style: { marginTop: '10px' } }, UI.steps(
          item.logistics.nodes.map(n => ({
            code: 'N' + n.node_code, name: n.node_name,
            time: n.actual_time || '', done: n.status === 'DONE'
          })))));
      }
      wrap.appendChild(card);
    });
  }
});
