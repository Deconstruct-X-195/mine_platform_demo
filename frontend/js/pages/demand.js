/* 需求管理（PRD 4.2/FR-02/T06-T07）：钢厂需求单 CRUD/提交/撤回/关闭 + 供应商脱敏需求池 */
(function () {
  window.Pages = window.Pages || {};
  const DELIVERY = { PLANT: '到厂', STATION_SELF: '到站自提', PORT_FOB: '港口FOB', PORT_TRUCK: '港口汽运' };
  const SETTLE = { PREPAY: '预付款', COD: '货到付款', CREDIT: '账期' };

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
          ['交货方式', DELIVERY[d.delivery_type] || d.delivery_type],
          ['交货地点', d.delivery_place || '-'],
          ['期望到货', UI.fmtDate(d.expect_arrive_start) + ' ~ ' + UI.fmtDate(d.expect_arrive_end)],
          ['结算方式', (SETTLE[d.settle_type] || d.settle_type || '-') + (d.settle_days ? ' ' + d.settle_days + '天' : '')],
          ['质量要求', d.quality_req, true],
        ]),
        UI.h('h3', { style: 'margin-top:14px' }, '需求明细'),
        UI.table([
          { key: 'varietyName', label: '品种' },
          { key: 'grade', label: '品位(%)' },
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

    /* -------- 新建/编辑（精简表单：产品名称/交货方式/到货日期/结算账期/质量要求） -------- */
    async function editForm(row, onDone) {
      let existing = null;
      if (row) existing = await API.get('/demands/' + row.id);
      const varieties = (await API.get('/base/varieties')).list;
      const vOpts = varieties.map((v) => [v.id, v.varietyName + '(' + v.varietyCode + ')']);
      const firstItem = (existing && existing.items && existing.items[0]) || {};
      const f = {
        variety: UI.selectField(vOpts, firstItem.varietyId == null ? '' : String(firstItem.varietyId)),
        grade: UI.input('number', firstItem.grade == null ? '' : String(firstItem.grade), { placeholder: '品位%，如 62' }),
        quantity: UI.input('number', firstItem.quantity == null ? '' : String(firstItem.quantity), { placeholder: '数量（吨）' }),
        deliveryType: UI.selectField([['PLANT', DELIVERY.PLANT], ['STATION_SELF', DELIVERY.STATION_SELF]],
          existing ? existing.delivery_type : 'PLANT'),
        place: UI.input('text', existing ? (existing.delivery_place || '') : '', { placeholder: '交货地点，如：黄骅港港区' }),
        expectStart: UI.input('date', existing ? UI.fmtDate(existing.expect_arrive_start) : ''),
        expectEnd: UI.input('date', existing ? UI.fmtDate(existing.expect_arrive_end) : ''),
        settleType: UI.selectField(Object.entries(SETTLE), existing ? existing.settle_type : 'COD'),
        settleDays: UI.input('number', existing && existing.settle_days ? String(existing.settle_days) : '',
          { placeholder: '账期天数，如 30' }),
        qualityReq: UI.h('textarea', { rows: 4, style: 'width:100%',
          placeholder: '如：Fe≥62%，水分≤8%；其他补充说明（备注）' }),
      };
      if (existing) f.qualityReq.value = existing.quality_req || '';

      const body = UI.h('form', { onsubmit: (e) => e.preventDefault() },
        UI.h('div', { class: 'form-grid' },
          UI.formRow('产品名称', f.variety, true),
          UI.formRow('品位(%)', f.grade, true),
          UI.formRow('数量(吨)', f.quantity, true),
          UI.formRow('交货方式', f.deliveryType, true),
          UI.formRow('交货地点', f.place, true),
          UI.formRow('期望到货起', f.expectStart, true),
          UI.formRow('期望到货止', f.expectEnd, true),
          UI.formRow('结算方式', f.settleType, true),
          UI.formRow('账期天数', f.settleDays),
          UI.h('div', { class: 'form-row full' }, UI.h('label', {}, '质量要求（含备注）'), f.qualityReq)));

      const m = UI.modal(row ? '编辑需求单' : '新建需求单', body, [
        UI.h('button', {
          class: 'primary',
          onclick: async () => {
            if (!f.variety.value) { UI.toast('请选择产品名称', 'err'); return; }
            if (!f.grade.value || !f.quantity.value) { UI.toast('品位、数量为必填', 'err'); return; }
            if (!f.place.value.trim()) { UI.toast('请填写交货地点', 'err'); return; }
            if (!f.expectStart.value || !f.expectEnd.value) { UI.toast('期望到货日期为必填', 'err'); return; }
            if (f.expectEnd.value < f.expectStart.value) { UI.toast('期望到货截止日不能早于起始日', 'err'); return; }
            const vName = (varieties.find((v) => String(v.id) === f.variety.value) || {}).varietyName || '矿产品';
            const payload = {
              demandName: vName + '采购需求',
              deliveryType: f.deliveryType.value,
              deliveryPlace: f.place.value.trim(),
              expectArriveStart: f.expectStart.value,
              expectArriveEnd: f.expectEnd.value,
              settleType: f.settleType.value,
              settleDays: f.settleDays.value ? Number(f.settleDays.value) : null,
              qualityReq: f.qualityReq.value,
              items: [{
                varietyId: Number(f.variety.value),
                grade: f.grade.value,
                quantity: Number(f.quantity.value),
                moreLessRate: firstItem.moreLessRate == null ? 5 : Number(firstItem.moreLessRate),
              }],
            };
            try {
              if (row) { await API.put('/demands/' + row.id, payload); UI.toast('已保存', 'ok'); }
              else { await API.post('/demands', payload); UI.toast('已创建草稿', 'ok'); }
              m.close(); onDone();
            } catch (e) { /* toast 已提示 */ }
          },
        }, '保 存'),
      ]);
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
        { label: '品种/品位', render: (r) => UI.h('span', {}, ...(r.items || []).map((it, i) => [
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
          { key: 'grade', label: '品位(%)' },
          { key: 'quantity', label: '数量(吨)', num: true },
          { key: 'moreLessRate', label: '溢短装(%)', num: true },
        ], r.items || [])));
    }

    await load();
  };
})();
