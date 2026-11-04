/* ============ 价格数据模块视图 (PRD-06)：R4 行情维护/价格看板 / R1 行情浏览 ============ */

const PRICE_COLORS = { market: '#2563eb', deal: '#f59e0b' };

/* ---------- R4 行情维护 ---------- */
App.registerView('r4.price', {
  title: '行情维护', roles: ['R4'],
  async render(root) {
    const state = { ore_category: '', date_from: '', date_to: '' };
    const catSel = el('select', null, [el('option', { value: '' }, '全部品类'),
      ...App.dict('ORE_CATEGORY').map(d => el('option', { value: d.item_code }, d.item_name))]);
    catSel.addEventListener('change', () => { state.ore_category = catSel.value; table.reload(); });
    const fromIn = el('input', { type: 'date' }); const toIn = el('input', { type: 'date' });
    const debounceReload = debounce(() => table.reload(), 300);
    fromIn.addEventListener('change', () => { state.date_from = fromIn.value; debounceReload(); });
    toIn.addEventListener('change', () => { state.date_to = toIn.value; debounceReload(); });
    const addBtn = el('button', { class: 'btn btn-primary btn-sm', onclick: () => showForm() }, '＋ 录入行情');
    const tplBtn = el('button', { class: 'btn btn-sm', onclick: () => API.download('/api/admin/price/template', {}, '行情批量导入模板.xlsx') }, '下载导入模板');
    const impBtn = el('button', { class: 'btn btn-sm', onclick: showImport }, '批量导入');

    const table = UI.table({
      columns: [
        { title: '品类', render: r => dictName(App.dict('ORE_CATEGORY'), r.ore_category) },
        { title: '指标规格', key: 'spec' },
        { title: '日期', key: 'quote_date' },
        { title: '市场参考价', num: true, render: r => fmtMoney(r.market_price) },
        { title: '平台成交均价', num: true, render: r => r.avg_deal_price != null ? fmtMoney(r.avg_deal_price) : '-' },
        { title: '数据来源', render: r => r.source || '-' },
        { title: '备注', render: r => r.remark || '-' },
        { title: '操作', render: r => el('div', { style: { display: 'flex', gap: '0' } }, [
          el('button', { class: 'btn btn-sm btn-link', onclick: () => showForm(r) }, '编辑'),
          el('button', { class: 'btn btn-sm btn-link', style: { color: 'var(--red)' }, onclick: () => doDelete(r) }, '删除')
        ]) }
      ],
      toolbar: { render: () => [catSel, fromIn, toIn, el('span', { class: 'fb-sep' }), addBtn, tplBtn, impBtn] },
      query: state, rowKey: 'id',
      fetch: q => API.get('/api/admin/price/list', q)
    });
    root.appendChild(el('div', { class: 'card' }, [table.root]));

    function showForm(r) {
      UI.form({
        title: r ? `编辑行情 #${r.id}` : '录入矿石行情',
        wide: true,
        fields: [
          { key: 'ore_category', label: '矿石品类', type: 'select', required: true, value: r ? r.ore_category : '',
            options: App.dict('ORE_CATEGORY').map(d => ({ value: d.item_code, label: d.item_name })) },
          { key: 'quote_date', label: '日期', type: 'date', required: true, value: r ? r.quote_date : '' },
          { key: 'spec', label: '指标规格', type: 'text', required: true, value: r ? r.spec : '', placeholder: '如 TFe 62%' },
          { key: 'market_price', label: '市场参考价（元/吨）', type: 'number', required: true, value: r ? r.market_price : '' },
          { key: 'avg_deal_price', label: '平台成交均价（元/吨）', type: 'number', value: r && r.avg_deal_price != null ? r.avg_deal_price : '',
            hint: '系统按历史集采订单自动统计，也可手工修正' },
          { key: 'source', label: '数据来源', type: 'text', value: r ? r.source : '', placeholder: '如 Mysteel / 钢联' },
          { key: 'remark', label: '备注', type: 'textarea', full: true, value: r ? r.remark : '', maxlength: 200 }
        ],
        submitText: r ? '保存修改' : '确认录入',
        onSubmit: async v => {
          if (r) await API.put(`/api/admin/price/${r.id}`, v);
          else await API.post('/api/admin/price/create', v);
          Toast.success(r ? '行情已更新' : '行情录入成功');
          table.reload();
        }
      });
    }

    function doDelete(r) {
      confirmDialog(`确认删除行情记录？${dictName(App.dict('ORE_CATEGORY'), r.ore_category)} ${r.quote_date} 市场价 ${fmtMoney(r.market_price)} 元/吨`, async () => {
        await API.del(`/api/admin/price/${r.id}`);
        Toast.success('已删除');
        table.reload();
      });
    }

    function showImport() {
      const body = el('div', null, [
        el('div', { class: 'hint', style: { marginBottom: '8px' } },
          '请先下载导入模板，按模板列顺序填写后上传（.xlsx）；逐行校验，合法行入库并返回行级错误报告。'),
        el('div', { class: 'field' }, [
          el('label', null, '选择 Excel 文件'),
          el('input', { type: 'file', accept: '.xlsx', id: 'price-import-file' })
        ]),
        el('div', { id: 'price-import-result' })
      ]);
      openModal({
        title: '批量导入行情', wide: true, body,
        footer: close => [
          el('button', { class: 'btn', onclick: close }, '取消'),
          el('button', {
            class: 'btn btn-primary', onclick: async () => {
              const f = $('#price-import-file').files[0];
              if (!f) { Toast.error('请选择文件'); return; }
              const fd = new FormData();
              fd.append('file', f);
              try {
                const res = await API.request('POST', '/api/admin/price/import', fd);
                const box = $('#price-import-result');
                box.innerHTML = '';
                box.appendChild(el('div', { class: `tag ${res.failed ? 'tag-orange' : 'tag-green'}` },
                  `导入完成：成功 ${res.inserted} 行，失败 ${res.failed} 行`));
                (res.errors || []).forEach(e => box.appendChild(
                  el('div', { style: { fontSize: '12.5px', color: 'var(--red)', marginTop: '4px' } },
                    `第${e.row}行：${e.message}`)));
                Toast.success(`导入完成，成功 ${res.inserted} 行`);
                table.reload();
              } catch (e) { /* toast 已提示 */ }
            }
          }, '开始导入')
        ]
      });
    }
  }
});

/* ---------- R4 价格看板 ---------- */
App.registerView('r4.priceBoard', {
  title: '价格看板', roles: ['R4'],
  async render(root) {
    const state = { ore_category: 'IRON', date_from: '', date_to: '' };
    const catSel = el('select', null, App.dict('ORE_CATEGORY').map(d =>
      el('option', Object.assign({ value: d.item_code }, d.item_code === 'IRON' ? { selected: true } : {}), d.item_name)));
    catSel.addEventListener('change', () => { state.ore_category = catSel.value; reload(); });
    const fromIn = el('input', { type: 'date' }); const toIn = el('input', { type: 'date' });
    fromIn.addEventListener('change', () => { state.date_from = fromIn.value; reload(); });
    toIn.addEventListener('change', () => { state.date_to = toIn.value; reload(); });

    const chartBox = el('div', { class: 'card', style: { height: '300px', padding: '12px' } },
      el('canvas', { style: { width: '100%', height: '100%' } }));
    const statBox = el('div', { class: 'card', style: { marginTop: '12px' } });

    root.appendChild(el('div', { class: 'card', style: { marginBottom: '12px' } },
      el('div', { style: { display: 'flex', gap: '10px', alignItems: 'center', flexWrap: 'wrap' } }, [
        el('span', { style: { fontSize: '13px', color: 'var(--text-2)' } }, '品类'), catSel,
        el('span', { style: { fontSize: '13px', color: 'var(--text-2)' } }, '日期区间'), fromIn, toIn,
        el('span', { class: 'tag tag-blue', style: { marginLeft: 'auto' } }, '━ 市场参考价'),
        el('span', { class: 'tag tag-orange' }, '━ 平台成交均价')
      ])));
    root.appendChild(chartBox);
    root.appendChild(statBox);

    async function reload() {
      const res = await API.get('/api/admin/price/trend', state);
      const labels = res.trend.map(t => t.quote_date.slice(5)); // MM-DD
      Charts.line(chartBox.querySelector('canvas'), labels, [
        { name: '市场参考价', color: PRICE_COLORS.market, data: res.trend.map(t => t.market_price) },
        { name: '平台成交均价', color: PRICE_COLORS.deal, data: res.trend.map(t => t.avg_deal_price) }
      ], { unit: '元' });
      // 成交均价月度统计（系统自动统计自集采订单）
      statBox.innerHTML = '';
      statBox.appendChild(el('div', { class: 'card-title' }, '平台成交均价月度统计（按集采订单自动汇总）'));
      const tb = el('table', { class: 'tb' }, [
        el('thead', null, el('tr', null, ['月份', '品类', '订单数', '总吨数', '成交均价(元/吨)'].map(h => el('th', null, h)))),
        el('tbody', null, res.deal_stats.length ? res.deal_stats.map(s => el('tr', null, [
          el('td', { class: 'strong' }, s.month),
          el('td', null, dictName(App.dict('ORE_CATEGORY'), s.ore_category)),
          el('td', { class: 'num' }, String(s.order_count)),
          el('td', { class: 'num' }, fmtQty(s.total_qty)),
          el('td', { class: 'num' }, fmtMoney(s.avg_unit_price))
        ])) : el('tr', null, el('td', { colspan: 5 }, UI.empty('暂无集采成交数据，锁货后自动统计'))))
      ]);
      statBox.appendChild(el('div', { class: 'table-wrap' }, tb));
    }
    await reload();
  }
});

/* ---------- R1 行情浏览（只读脱敏） ---------- */
App.registerView('r1.market', {
  title: '行情浏览', roles: ['R1'],
  async render(root) {
    const state = { ore_category: '', date_from: '', date_to: '', page: 1, page_size: 20 };
    const catSel = el('select', null, [el('option', { value: '' }, '全部品类'),
      ...App.dict('ORE_CATEGORY').map(d => el('option', { value: d.item_code }, d.item_name))]);
    catSel.addEventListener('change', () => { state.ore_category = catSel.value; state.page = 1; reload(); });
    const fromIn = el('input', { type: 'date' }); const toIn = el('input', { type: 'date' });
    fromIn.addEventListener('change', () => { state.date_from = fromIn.value; state.page = 1; reload(); });
    toIn.addEventListener('change', () => { state.date_to = toIn.value; state.page = 1; reload(); });

    const chartBox = el('div', { class: 'card', style: { height: '260px', padding: '12px', marginBottom: '12px' } },
      el('canvas', { style: { width: '100%', height: '100%' } }));
    const listBox = el('div', { class: 'card' });

    root.appendChild(el('div', { class: 'card', style: { marginBottom: '12px' } },
      el('div', { style: { display: 'flex', gap: '10px', alignItems: 'center', flexWrap: 'wrap' } }, [
        catSel, fromIn, toIn,
        el('span', { class: 'hint', style: { marginLeft: 'auto', margin: 0 } }, '公开市场行情 · 仅供采购决策参考')
      ])));
    root.appendChild(chartBox);
    root.appendChild(listBox);

    async function reload() {
      const res = await API.get('/api/company/price/trend', state);
      // 图表按日期升序
      const asc = [...res.list].reverse();
      Charts.line(chartBox.querySelector('canvas'), asc.map(t => t.quote_date.slice(5)), [
        { name: '市场参考价', color: PRICE_COLORS.market, data: asc.map(t => t.market_price) }
      ], { unit: '元' });
      listBox.innerHTML = '';
      const tb = el('table', { class: 'tb' }, [
        el('thead', null, el('tr', null, ['品类', '指标规格', '日期', '市场参考价(元/吨)', '数据来源'].map(h => el('th', null, h)))),
        el('tbody', null, res.list.length ? res.list.map(r => el('tr', null, [
          el('td', { class: 'strong' }, dictName(App.dict('ORE_CATEGORY'), r.ore_category)),
          el('td', null, r.spec),
          el('td', null, r.quote_date),
          el('td', { class: 'num' }, fmtMoney(r.market_price)),
          el('td', null, r.source || '-')
        ])) : el('tr', null, el('td', { colspan: 5 }, UI.empty('暂无行情数据'))))
      ]);
      listBox.appendChild(el('div', { class: 'table-wrap' }, tb));
      if (res.total > res.page_size) {
        const totalPages = Math.ceil(res.total / res.page_size);
        const pager = el('div', { class: 'pager', style: { display: 'flex', gap: '8px', padding: '10px 4px', alignItems: 'center' } }, [
          el('button', { class: 'btn btn-sm', disabled: res.page <= 1 ? true : null,
            onclick: () => { state.page = res.page - 1; reload(); } }, '上一页'),
          el('span', { style: { fontSize: '13px', color: 'var(--text-3)' } }, `第 ${res.page} / ${totalPages} 页 · 共 ${res.total} 条`),
          el('button', { class: 'btn btn-sm', disabled: res.page >= totalPages ? true : null,
            onclick: () => { state.page = res.page + 1; reload(); } }, '下一页')
        ]);
        listBox.appendChild(pager);
      }
    }
    await reload();
  }
});
