/* 需求管理（PRD 4.2/FR-02/T06-T07）：钢厂需求单 CRUD/提交/撤回/关闭 + 供应商脱敏需求池 */
(function () {
  window.Pages = window.Pages || {};
  const DELIVERY = { PORT_FOB: '港口FOB', PORT_TRUCK: '港口汽运', PLANT: '厂内自提' };
  const SETTLE = { PREPAY: '预付款', COD: '货到付款', CREDIT: '账期' };

  function attachLinks(str) {
    if (!str) return '-';
    return UI.h('span', {}, ...String(str).split(',').filter(Boolean).map((fid, i) => [
      i > 0 ? ' ' : null,
      UI.h('a', { href: 'javascript:;', onclick: () => API.downloadFile(fid, '附件-' + fid) }, '附件' + (i + 1)),
    ]).flat());
  }

  /* -------- 钢厂：需求单列表 -------- */
  Pages.demand = async function (page, user) {
    let status = '';
    let pageNo = 1;
    const SIZE = 10;
    const listCard = UI.h('div', { class: 'card' });
    const pagerBox = UI.h('div', {});
    page.appendChild(UI.h('div', { class: 'card' },
      UI.h('div', { class: 'toolbar' },
        UI.h('h3', { style: 'margin:0;border:none;padding:0' }, '需求单'),
        UI.h('div', { class: 'spacer' }),
        UI.statusFilter('DEMAND', (v) => { status = v; pageNo = 1; load(); }),
        UI.h('button', { class: 'primary', onclick: () => editForm(null, () => load()) }, '新建需求'))));
    page.appendChild(listCard);
    page.appendChild(pagerBox);

    async function load() {
      const d = await API.get('/demands' + API.qs({ page: pageNo, size: SIZE, status }));
      listCard.innerHTML = '';
      listCard.appendChild(UI.table([
        { key: 'demand_no', label: '需求编号' },
        { key: 'demand_name', label: '需求名称' },
        { key: 'delivery_type', label: '交货方式', render: (r) => DELIVERY[r.delivery_type] || r.delivery_type || '-' },
        { key: 'delivery_place', label: '交货地点' },
        { label: '期望到货', render: (r) => UI.fmtDate(r.expect_arrive_start) + ' ~ ' + UI.fmtDate(r.expect_arrive_end) },
        { label: '结算', render: (r) => (SETTLE[r.settle_type] || r.settle_type || '-') + (r.settle_days ? ' ' + r.settle_days + '天' : '') },
        { key: 'status', label: '状态', render: (r) => UI.statusTag('DEMAND', r.status) },
        { key: 'version', label: '版本', num: true },
        { key: 'created_at', label: '创建时间', render: (r) => UI.fmtDateTime(r.created_at) },
        { label: '操作', render: (r) => acts(r) },
      ], d.list, '暂无需求单'));
      pagerBox.innerHTML = '';
      UI.pager(pagerBox, pageNo, SIZE, d.total, (p) => { pageNo = p; load(); });
    }

    function acts(r) {
      const btns = [UI.h('button', { class: 'sm', onclick: () => detail(r.id) }, '详情')];
      if (r.status === 'DRAFT') {
        btns.push(UI.h('button', { class: 'sm', onclick: () => editForm(r, () => load()) }, '编辑'));
        btns.push(UI.h('button', { class: 'sm success', onclick: async () => {
          if (!(await UI.confirmBox('确认提交需求单 ' + r.demand_no + '？提交后不可编辑。'))) return;
          await API.post('/demands/' + r.id + '/submit');
          UI.toast('已提交', 'ok'); load();
        } }, '提交'));
      }
      if (r.status === 'SUBMITTED') {
        btns.push(UI.h('button', { class: 'sm', onclick: async () => {
          // 文案修正（BUG-04 关联）：撤回后状态为"已撤回"（不可编辑，可重新提交生成新版本），
          // 并非回到草稿；原文案误导用户以为可继续编辑。
          if (!(await UI.confirmBox('确认撤回？撤回后需求单不可编辑，可重新提交生成新版本。'))) return;
          await API.post('/demands/' + r.id + '/withdraw');
          UI.toast('已撤回', 'ok'); load();
        } }, '撤回'));
      }
      if (r.status === 'WITHDRAWN') {
        // BUG-04 修复：补充"重新提交"入口。后端状态机本就支持
        // WITHDRAWN→SUBMITTED（生成新版本 version+1），此前 UI 无入口导致流程中断。
        btns.push(UI.h('button', { class: 'sm success', onclick: async () => {
          if (!(await UI.confirmBox('确认重新提交需求单 ' + r.demand_no + '？将生成新版本。'))) return;
          await API.post('/demands/' + r.id + '/submit');
          UI.toast('已重新提交', 'ok'); load();
        } }, '重新提交'));
      }
      if (r.status === 'SUBMITTED' || r.status === 'INQUIRING') {
        btns.push(UI.h('button', { class: 'sm danger', onclick: () => closeForm(r, () => load()) }, '关闭'));
      }
      return UI.h('span', { class: 'inline-flex' }, ...btns);
    }

    async function detail(did) {
      const d = await API.get('/demands/' + did);
      const body = UI.h('div', {},
        UI.kv([
          ['需求编号', d.demand_no], ['状态', UI.statusTag('DEMAND', d.status)],
          ['交货方式', DELIVERY[d.delivery_type] || d.delivery_type], ['交货地点', d.delivery_place],
          ['期望到货', UI.fmtDate(d.expect_arrive_start) + ' ~ ' + UI.fmtDate(d.expect_arrive_end)],
          ['结算方式', (SETTLE[d.settle_type] || d.settle_type || '-') + (d.settle_days ? ' ' + d.settle_days + '天' : '')],
          ['价格意向', d.price_intent], ['质量要求', d.quality_req],
          ['备注', d.remark, true], ['附件', attachLinks(d.attachments), true],
        ]),
        UI.h('h3', { style: 'margin-top:14px' }, '需求明细'),
        UI.table([
          { key: 'varietyName', label: '品种' },
          { key: 'grade', label: '牌号' },
          { key: 'quantity', label: '数量(吨)', num: true, render: (r) => UI.fmtMoney(r.quantity) },
          { key: 'moreLessRate', label: '溢短装(%)', num: true },
          { key: 'inquiredQty', label: '已询量', num: true },
          { key: 'remainQty', label: '剩余可询', num: true },
          { key: 'dealQty', label: '成交量', num: true },
        ], d.items));
      UI.modal('需求单 ' + (d.demand_no || ''), body);
    }

    function closeForm(r, onDone) {
      const reason = UI.h('textarea', { rows: 2, style: 'width:100%', placeholder: '关闭原因（必填）' });
      const m = UI.modal('关闭需求单 ' + r.demand_no, UI.h('div', {}, UI.formRow('关闭原因', reason, true)), [
        UI.h('button', { class: 'primary', onclick: async () => {
          if (!reason.value.trim()) { UI.toast('请填写关闭原因', 'err'); return; }
          await API.post('/demands/' + r.id + '/close', { reason: reason.value.trim() });
          m.close(); UI.toast('已关闭', 'ok'); onDone();
        } }, '确认关闭'),
      ]);
    }

    /* -------- 新建/编辑（含明细动态编辑器） -------- */
    async function editForm(row, onDone) {
      let existing = null;
      if (row) existing = await API.get('/demands/' + row.id);
      const varieties = (await API.get('/base/varieties')).list;
      const vOpts = varieties.map((v) => [v.id, v.varietyName + '(' + v.varietyCode + ')']);
      const f = {
        demandName: UI.input('text', existing ? existing.demand_name : '', { placeholder: '如：3万吨PB粉港口自提' }),
        deliveryType: UI.selectField(Object.entries(DELIVERY), existing ? existing.delivery_type : 'PORT_FOB'),
        deliveryPlace: UI.input('text', existing ? existing.delivery_place : '', { placeholder: '交货地点' }),
        expectStart: UI.input('date', existing ? UI.fmtDate(existing.expect_arrive_start) : ''),
        expectEnd: UI.input('date', existing ? UI.fmtDate(existing.expect_arrive_end) : ''),
        priceIntent: UI.input('text', existing ? existing.price_intent : '', { placeholder: '选填' }),
        settleType: UI.selectField(Object.entries(SETTLE), existing ? existing.settle_type : 'COD'),
        settleDays: UI.input('number', existing ? existing.settle_days : '', { placeholder: '账期天数' }),
        qualityReq: UI.h('textarea', { rows: 2, style: 'width:100%' }),
        remark: UI.h('textarea', { rows: 2, style: 'width:100%' }),
        files: UI.h('input', { type: 'file', multiple: true }),
      };
      if (existing) {
        f.qualityReq.value = existing.quality_req || '';
        f.remark.value = existing.remark || '';
      }
      // BUG-03 修复：编辑时回显已有明细。此前 items=[] 恒为空，编辑弹窗
      // 恒显示"暂无明细，请添加"，误操作会清空原明细。
      const items = ((existing && existing.items) || []).map((it) => ({
        varietyId: it.varietyId == null ? '' : String(it.varietyId),
        grade: it.grade == null ? '' : String(it.grade),
        quantity: it.quantity == null ? '' : String(it.quantity),
        moreLessRate: it.moreLessRate == null ? '' : String(it.moreLessRate),
      }));
      const itemsBox = UI.h('div', {});
      function renderItems() {
        itemsBox.innerHTML = '';
        if (!items.length) { itemsBox.appendChild(UI.h('div', { class: 'empty' }, '暂无明细，请添加')); return; }
        items.forEach((it, idx) => {
          it.varietySel = UI.selectField(vOpts, it.varietyId);
          // BUG-02 修复：新建明细行时未选中任何 option，浏览器默认显示第一项
          // （如 PB粉），但数据模型 it.varietyId 仍为空，仅靠 change 事件同步，
          // 导致"下拉已显示品种、保存却被拦明细不完整"。此处将默认选中项回写模型。
          if (it.varietyId == null || it.varietyId === '') it.varietyId = it.varietySel.value;
          it.varietySel.addEventListener('change', () => { it.varietyId = it.varietySel.value; });
          it.gradeIn = UI.input('text', it.grade, { placeholder: '牌号', onchange: (e) => { it.grade = e.target.value; } });
          it.qtyIn = UI.input('number', it.quantity, { placeholder: '数量', onchange: (e) => { it.quantity = e.target.value; } });
          it.mlIn = UI.input('number', it.moreLessRate, { placeholder: '如 5 表示 ±5%', onchange: (e) => { it.moreLessRate = e.target.value; } });
          itemsBox.appendChild(UI.h('div', { class: 'inline-flex', style: 'margin-bottom:6px' },
            UI.h('span', {}, '明细' + (idx + 1)), it.varietySel, it.gradeIn, it.qtyIn, it.mlIn,
            UI.h('button', { class: 'sm danger', onclick: () => { items.splice(idx, 1); renderItems(); } }, '删除')));
        });
      }
      renderItems();

      const body = UI.h('form', { onsubmit: (e) => e.preventDefault() },
        UI.h('div', { class: 'form-grid' },
          UI.formRow('需求名称', f.demandName, true),
          UI.formRow('交货方式', f.deliveryType, true),
          UI.formRow('交货地点', f.deliveryPlace, true),
          UI.formRow('价格意向', f.priceIntent),
          UI.formRow('期望到货起', f.expectStart, true),
          UI.formRow('期望到货止', f.expectEnd, true),
          UI.formRow('结算方式', f.settleType, true),
          UI.formRow('账期天数', f.settleDays),
          UI.h('div', { class: 'form-row full' }, UI.h('label', {}, '质量要求'), f.qualityReq),
          UI.h('div', { class: 'form-row full' }, UI.h('label', {}, '备注'), f.remark),
          UI.h('div', { class: 'form-row full' }, UI.h('label', {}, '附件'), f.files)),
        UI.h('h3', {}, '需求明细'),
        UI.h('button', { class: 'sm', onclick: () => { items.push({}); renderItems(); } }, '+ 添加明细'),
        itemsBox);

      const m = UI.modal(row ? '编辑需求单' : '新建需求单', body, [
        UI.h('button', {
          class: 'primary',
          onclick: async () => {
            const payload = {
              demandName: f.demandName.value.trim(),
              deliveryType: f.deliveryType.value,
              deliveryPlace: f.deliveryPlace.value.trim(),
              expectArriveStart: f.expectStart.value,
              expectArriveEnd: f.expectEnd.value,
              priceIntent: f.priceIntent.value.trim(),
              settleType: f.settleType.value,
              settleDays: f.settleDays.value ? Number(f.settleDays.value) : null,
              qualityReq: f.qualityReq.value,
              remark: f.remark.value,
            };
            if (!payload.demandName || !payload.deliveryPlace) { UI.toast('需求名称、交货地点为必填', 'err'); return; }
            if (!payload.expectArriveStart || !payload.expectArriveEnd) { UI.toast('期望到货日期为必填', 'err'); return; }
            const its = [];
            for (const it of items) {
              if (!it.varietyId || !it.grade || !it.quantity) { UI.toast('明细需完整填写品种/牌号/数量', 'err'); return; }
              its.push({ varietyId: Number(it.varietyId), grade: it.grade, quantity: Number(it.quantity), moreLessRate: it.moreLessRate ? Number(it.moreLessRate) : 0 });
            }
            if (!its.length) { UI.toast('至少一条需求明细', 'err'); return; }
            payload.items = its;
            try {
              if (f.files.files && f.files.files.length) {
                const ids = [];
                for (const file of f.files.files) {
                  const up = await API.upload(file);
                  ids.push(up.fileId != null ? up.fileId : up.id);
                }
                payload.attachments = ids.join(',');
              }
              if (row) { await API.put('/demands/' + row.id, payload); UI.toast('已保存', 'ok'); }
              else { await API.post('/demands', payload); UI.toast('已创建草稿', 'ok'); }
              m.close(); onDone();
            } catch (e) { /* toast 已提示 */ }
          },
        }, '保 存'),
      ], { wide: true });
    }

    await load();
  };

  /* -------- 供应商：脱敏需求池 -------- */
  Pages.pool = async function (page) {
    let pageNo = 1;
    const SIZE = 10;
    const listCard = UI.h('div', { class: 'card' });
    const pagerBox = UI.h('div', {});
    page.appendChild(UI.h('div', { class: 'card' }, UI.h('h3', { style: 'margin:0;border:none;padding:0' }, '需求池（已脱敏）')));
    page.appendChild(listCard);
    page.appendChild(pagerBox);

    async function load() {
      const d = await API.get('/demands' + API.qs({ page: pageNo, size: SIZE }));
      listCard.innerHTML = '';
      listCard.appendChild(UI.table([
        { key: 'demandNo', label: '需求编号' },
        { label: '品种/牌号', render: (r) => UI.h('span', {}, ...(r.items || []).map((it, i) => [
          i > 0 ? '；' : null, (it.varietyName || '-') + ' ' + (it.grade || ''),
        ]).flat()) },
        { key: 'totalQty', label: '总量(吨)', num: true, render: (r) => UI.fmtMoney(r.totalQty) },
        { key: 'deliveryType', label: '交货方式', render: (r) => DELIVERY[r.deliveryType] || r.deliveryType || '-' },
        { key: 'deliveryRegion', label: '交货区域' },
        { key: 'expectMonth', label: '期望到货月份' },
        { key: 'createdAt', label: '发布时间', render: (r) => UI.fmtDateTime(r.createdAt) },
        { label: '操作', render: (r) => UI.h('button', { class: 'sm', onclick: () => detail(r) }, '详情') },
      ], d.list, '暂无可接需求'));
      pagerBox.innerHTML = '';
      UI.pager(pagerBox, pageNo, SIZE, d.total, (p) => { pageNo = p; load(); });
    }

    async function detail(r) {
      UI.modal('需求 ' + (r.demandNo || ''), UI.h('div', {},
        UI.kv([
          ['需求编号', r.demandNo], ['总量', UI.fmtMoney(r.totalQty) + ' 吨'],
          ['交货方式', DELIVERY[r.deliveryType] || r.deliveryType], ['交货区域', r.deliveryRegion],
          ['期望到货', r.expectMonth], ['发布时间', UI.fmtDateTime(r.createdAt)],
        ]),
        UI.h('h3', { style: 'margin-top:14px' }, '品种明细（脱敏概要）'),
        UI.table([
          { key: 'varietyName', label: '品种' },
          { key: 'grade', label: '牌号' },
          { key: 'quantity', label: '数量(吨)', num: true },
          { key: 'moreLessRate', label: '溢短装(%)', num: true },
        ], r.items || [])));
    }

    await load();
  };
})();
