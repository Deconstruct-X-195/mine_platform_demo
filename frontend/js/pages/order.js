/* 订单合同物流（PRD 4.5-4.7/T12-T16）：订单确认/合同签署/物流方案/运单作业/履约跟踪 */
(function () {
  window.Pages = window.Pages || {};
  const DELIVERY = { PORT_FOB: '港口FOB', PORT_TRUCK: '港口汽运', PLANT: '厂内自提' };
  const SETTLE = { PREPAY: '预付款', COD: '货到付款', CREDIT: '账期' };
  const MODES = { ROAD: '公路', RAIL: '铁路', SEA: '海运', MULTIMODAL: '多式联运' };

  /* -------- 共享：运单列 -------- */
  function waybillCols(mode, onChanged, carriers) {
    return [
      { key: 'segment_no', label: '分段号' },
      { key: 'order_no', label: '订单号' },
      { key: 'transport_mode', label: '运输方式', render: (r) => MODES[r.transport_mode] || r.transport_mode || '-' },
      { key: 'plan_qty', label: '计划量', num: true, render: (r) => UI.fmtMoney(r.plan_qty) },
      { key: 'actual_qty', label: '实发/实收', num: true, render: (r) => r.actual_qty != null ? UI.fmtMoney(r.actual_qty) : '-' },
      { key: 'plan_depart_date', label: '计划发运', render: (r) => UI.fmtDate(r.plan_depart_date) },
      { key: 'plan_arrive_date', label: '计划到达', render: (r) => UI.fmtDate(r.plan_arrive_date) },
      { key: 'actual_depart_at', label: '实发运', render: (r) => UI.fmtDateTime(r.actual_depart_at) },
      { key: 'actual_arrive_at', label: '实到达', render: (r) => UI.fmtDateTime(r.actual_arrive_at) },
      { key: 'freight', label: '运费', num: true, render: (r) => r.freight != null ? UI.fmtMoney(r.freight) : '-' },
      { key: 'vehicle_no', label: '车船号' },
      { key: 'carrier_name', label: '承运商' },
      { key: 'status', label: '状态', render: (r) => UI.statusTag('WAYBILL', r.status) },
      { label: '操作', render: (r) => waybillActs(r, mode, onChanged, carriers) },
    ];
  }

  function waybillActs(r, mode, onChanged, carriers) {
    const btns = [];
    if (mode === 'STEEL') {
      if (r.status === 'ARRIVED') {
        btns.push(UI.h('button', { class: 'sm success', onclick: async () => {
          if (!(await UI.confirmBox('确认签收运单 ' + r.segment_no + '？'))) return;
          await API.post('/waybills/' + r.id + '/sign');
          UI.toast('已签收', 'ok'); onChanged();
        } }, '签收'));
      }
    }
    return btns.length ? UI.h('span', { class: 'inline-flex' }, ...btns) : '-';
  }

  function nodeModal(r, node, onChanged) {
    const occur = UI.h('input', { type: 'datetime-local', placeholder: '发生时间' });
    const qty = UI.input('number', '', { placeholder: '实际数量（吨，选填）' });
    const m = UI.modal((node === 'DEPART' ? '回填发运' : '回填到达') + ' · ' + r.segment_no,
      UI.h('div', { class: 'form-grid' },
        UI.formRow('发生时间', occur, false, '留空默认当前时间'),
        UI.formRow('实际数量', qty)), [
      UI.h('button', { class: 'primary', onclick: async () => {
        const body = { node };
        if (occur.value) body.occurTime = occur.value.replace('T', ' ') + ':00';
        if (qty.value !== '') body.actualQty = qty.value;
        await API.put('/waybills/' + r.id + '/node', body);
        m.close(); UI.toast('节点已回填', 'ok'); onChanged();
      } }, '提 交'),
    ]);
  }

  /* -------- 订单 -------- */
  Pages.order = async function (page, user) {
    const isSteel = (user.roles || []).indexOf('STEEL_BUYER') >= 0;
    const isSupplier = (user.roles || []).indexOf('SUPPLIER') >= 0;
    /* 供应商端订单管理：订单列表 + 订单详情 + 订单确认 */
    if (isSupplier) return supplierOrderView();
    let pageNo = 1;
    const SIZE = 10;
    const listCard = UI.h('div', { class: 'card' });
    const pagerBox = UI.h('div', {});
    page.appendChild(UI.h('div', { class: 'card' }, UI.h('h3', { style: 'margin:0;border:none;padding:0' }, '订单')));
    page.appendChild(listCard);
    page.appendChild(pagerBox);

    async function load() {
      const d = await API.get('/orders' + API.qs({ page: pageNo, size: SIZE }));
      listCard.innerHTML = '';
      listCard.appendChild(UI.table([
        { key: 'order_no', label: '订单号' },
        { key: 'varietyName', label: '品种' },
        { key: 'grade', label: '品位(%)' },
        { key: 'quantity', label: '数量', num: true, render: (r) => UI.fmtMoney(r.myQty != null ? r.myQty : r.quantity) },
        { key: 'unit_price', label: '单价', num: true, render: (r) => UI.fmtMoney(r.unit_price) },
        { key: 'amount', label: '金额', num: true, render: (r) => UI.fmtMoney(r.amount) },
        { key: 'delivery_date', label: '交货日', render: (r) => UI.fmtDate(r.delivery_date) },
        { key: 'status', label: '状态', render: (r) => UI.statusTag('ORDER', r.status) },
        { key: 'buyerName', label: '需方' },
        { key: 'supplierName', label: '供方' },
        { key: 'confirm_deadline', label: '确认截止', render: (r) => UI.fmtDateTime(r.confirm_deadline) },
        { label: '操作', render: (r) => acts(r) },
      ], d.list, '暂无订单'));
      pagerBox.innerHTML = '';
      UI.pager(pagerBox, pageNo, SIZE, d.total, (p) => { pageNo = p; load(); });
    }

    function acts(r) {
      const btns = [UI.h('button', { class: 'sm', onclick: () => detail(r.id) }, '详情')];
      // 集采聚合订单：参与钢厂提交/修改提货计划（仅「待收集提货计划」状态可填写）
      if (isSteel && r.status === 'PENDING_PICKUP' && r.myQty != null) {
        btns.push(UI.h('button', { class: 'sm primary', onclick: () => pickupPlanModal(r) },
          r.myPickupStatus === 'SUBMITTED' ? '修改提货计划' : '提货计划'));
      }
      if (isSteel && r.status === 'PENDING_CONTRACT') {
        btns.push(UI.h('button', { class: 'sm primary', onclick: async () => {
          await API.post('/orders/' + r.id + '/contract/generate');
          UI.toast('合同已生成（新版本）', 'ok'); load();
        } }, '生成合同'));
      }
      if (isSteel && r.status === 'COMPLETED') {
        btns.push(UI.h('button', { class: 'sm', onclick: () =>
          API.download('/orders/' + r.id + '/archive/export', 'archive-' + r.order_no + '.zip') }, '导出档案'));
      }
      return UI.h('span', { class: 'inline-flex' }, ...btns);
    }

    async function detail(oid) {
      const d = await API.get('/orders/' + oid);
      const body = UI.h('div', {},
        UI.kv([
          ['订单号', d.order_no], ['状态', UI.statusTag('ORDER', d.status)],
          ['品种', d.varietyName], ['品位(%)', d.grade],
          ['数量', UI.fmtMoney(d.quantity) + ' 吨'], ['单价', UI.fmtMoney(d.unit_price)],
          ['金额', UI.fmtMoney(d.amount)], ['溢短装', d.more_less_rate != null ? d.more_less_rate + '%' : '-'],
          ['交货方式', DELIVERY[d.delivery_type] || d.delivery_type], ['交货地点', d.delivery_place],
          ['交货日', UI.fmtDate(d.delivery_date)],
          ['结算', (SETTLE[d.settle_type] || d.settle_type || '-') + (d.settle_days ? ' ' + d.settle_days + '天' : '')],
          ['需方', d.buyerName], ['供方', d.supplierName],
          ['确认截止', UI.fmtDateTime(d.confirm_deadline)],
        ]),
        UI.h('h3', { style: 'margin-top:14px' }, '关联合同'),
        UI.table([
          { key: 'version', label: '版本', num: true },
          { key: 'status', label: '状态', render: (r) => UI.statusTag('CONTRACT', r.status) },
          { key: 'buyer_sign_at', label: '需方签署', render: (r) => UI.fmtDateTime(r.buyer_sign_at) },
          { key: 'supplier_sign_at', label: '供方签署', render: (r) => UI.fmtDateTime(r.supplier_sign_at) },
        ], d.contracts || []));
      UI.modal('订单详情', body, [], { wide: true });
    }

    /* 提货计划：开始提货日期 + 日提货吨数 + 备注；全部钢厂提交后订单进入待制定运输方案 */
    function pickupPlanModal(r) {
      const start = UI.input('date', '', {});
      const daily = UI.input('number', '', { min: '0', step: '0.001', placeholder: '吨/天' });
      const remark = UI.input('text', '', { placeholder: '备注（可选，200 字以内）' });
      const m = UI.modal((r.myPickupStatus === 'SUBMITTED' ? '修改' : '提交') + '提货计划 · ' + r.order_no,
        UI.h('div', {},
          UI.h('div', { class: 'hint', style: 'margin-bottom:8px' },
            '集采订单由多家钢厂共同供货，贵司份额 ' + UI.fmtMoney(r.myQty) + ' 吨'),
          UI.h('div', { class: 'form-grid' },
            UI.formRow('开始提货日期', start, true),
            UI.formRow('日提货吨数(吨)', daily, true),
            UI.formRow('备注', remark))), [
          UI.h('button', { class: 'primary', onclick: async () => {
            if (!start.value) { UI.toast('请选择开始提货日期', 'err'); return; }
            const qty = parseFloat(daily.value);
            if (!(qty > 0)) { UI.toast('日提货吨数必须大于 0', 'err'); return; }
            try {
              await API.post('/orders/' + r.id + '/pickup-plan', {
                startDate: start.value, dailyQty: qty, remark: remark.value.trim() || undefined,
              });
              m.close(); UI.toast('提货计划已提交', 'ok'); load();
            } catch (e) { /* toast 已提示 */ }
          } }, '保 存'),
        ]);
    }

    /* 供应商端订单管理：订单列表 + 订单详情 + 订单确认（48h 期限） */
    async function supplierOrderView() {
      let pageNo = 1;
      const SIZE = 10;
      const listCard = UI.h('div', { class: 'card' });
      const pagerBox = UI.h('div', {});
      const confirmCard = UI.h('div', { class: 'card' });
      page.appendChild(UI.h('div', { class: 'card' },
        UI.h('h3', { class: 'bar-title' }, '订单列表',
          UI.h('span', { class: 'hint', style: 'margin-left:auto' }, '点击「详情」查看订单明细与关联合同'))));
      page.appendChild(listCard);
      page.appendChild(pagerBox);
      page.appendChild(UI.h('div', { class: 'card' },
        UI.h('h3', { class: 'bar-title' }, '订单确认',
          UI.h('span', { class: 'hint', style: 'margin-left:auto' }, '中标订单须在确认截止前确认，超期将自动取消'))));
      page.appendChild(confirmCard);

      function confirmBtn(r) {
        return UI.h('button', { class: 'sm success', onclick: async () => {
          if (!(await UI.confirmBox('确认接受订单 ' + r.order_no + '？确认后进入提货计划收集环节。'))) return;
          await API.put('/orders/' + r.id + '/confirm');
          UI.toast('订单已确认', 'ok'); load();
        } }, '确认订单');
      }

      const cols = (withConfirm) => [
        { key: 'order_no', label: '订单号' },
        { key: 'varietyName', label: '品种' },
        { key: 'grade', label: '品位(%)' },
        { key: 'quantity', label: '数量', num: true, render: (r) => UI.fmtMoney(r.myQty != null ? r.myQty : r.quantity) },
        { key: 'unit_price', label: '单价', num: true, render: (r) => UI.fmtMoney(r.unit_price) },
        { key: 'amount', label: '金额', num: true, render: (r) => UI.fmtMoney(r.amount) },
        { key: 'delivery_date', label: '交货日', render: (r) => UI.fmtDate(r.delivery_date) },
        { key: 'status', label: '状态', render: (r) => UI.statusTag('ORDER', r.status) },
        { key: 'buyerName', label: '需方' },
        { key: 'confirm_deadline', label: '确认截止', render: (r) => UI.fmtDateTime(r.confirm_deadline) },
        { label: '操作', render: (r) => {
            const btns = [UI.h('button', { class: 'sm', onclick: () => supplierDetail(r.id) }, '详情')];
            if (withConfirm && r.status === 'PENDING_CONFIRM') btns.push(confirmBtn(r));
            return UI.h('span', { class: 'inline-flex' }, ...btns);
          } },
      ];

      async function load() {
        const d = await API.get('/orders' + API.qs({ page: pageNo, size: SIZE }));
        listCard.innerHTML = '';
        listCard.appendChild(UI.table(cols(false), d.list, '暂无订单'));
        pagerBox.innerHTML = '';
        UI.pager(pagerBox, pageNo, SIZE, d.total, (p) => { pageNo = p; load(); });
        const pend = (await API.get('/orders' + API.qs({ page: 1, size: 50, status: 'PENDING_CONFIRM' }))).list || [];
        confirmCard.innerHTML = '';
        confirmCard.appendChild(pend.length ? UI.table(cols(true), pend, '暂无待确认订单')
          : UI.h('div', { class: 'empty' }, '暂无待确认订单'));
      }

      /* 订单详情：分区展示（基本信息/交货与结算/需供双方/关联合同） */
      async function supplierDetail(oid) {
        const d = await API.get('/orders/' + oid);
        const body = UI.h('div', {},
          UI.h('div', { class: 'sec-title' }, '基本信息'),
          UI.kv([
            ['订单号', d.order_no], ['状态', UI.statusTag('ORDER', d.status)],
            ['品种', d.varietyName], ['品位(%)', d.grade],
            ['数量', UI.fmtMoney(d.quantity) + ' 吨'], ['单价', UI.fmtMoney(d.unit_price)],
            ['金额', UI.fmtMoney(d.amount)], ['溢短装', d.more_less_rate != null ? d.more_less_rate + '%' : '-'],
          ]),
          UI.h('div', { class: 'sec-title' }, '交货与结算'),
          UI.kv([
            ['交货方式', DELIVERY[d.delivery_type] || d.delivery_type], ['交货地点', d.delivery_place],
            ['交货日', UI.fmtDate(d.delivery_date)],
            ['结算', (SETTLE[d.settle_type] || d.settle_type || '-') + (d.settle_days ? ' ' + d.settle_days + '天' : '')],
          ]),
          UI.h('div', { class: 'sec-title' }, '需供双方'),
          UI.kv([
            ['需方', d.buyerName], ['供方', d.supplierName],
            ['确认截止', UI.fmtDateTime(d.confirm_deadline)],
          ]),
          UI.h('div', { class: 'sec-title' }, '关联合同'),
          UI.table([
            { key: 'version', label: '版本', num: true },
            { key: 'status', label: '状态', render: (r) => UI.statusTag('CONTRACT', r.status) },
            { key: 'buyer_sign_at', label: '需方签署', render: (r) => UI.fmtDateTime(r.buyer_sign_at) },
            { key: 'supplier_sign_at', label: '供方签署', render: (r) => UI.fmtDateTime(r.supplier_sign_at) },
          ], d.contracts || []));
        UI.modal('订单详情 · ' + d.order_no, body, [], { wide: true });
      }

      await load();
    }

    await load();
  };

  /* -------- 物流服务（钢厂/供应商）：节点跟踪 + 运输方案/分段运单（供应商只读） -------- */
  Pages.logistics = async function (page, user) {
    /* 供应商端物流服务：仅查看运输方案与物流轨迹（95306 式，同钢厂端），无创建/编辑能力 */
    const isSupplier = (user.roles || []).indexOf('SUPPLIER') >= 0;
    const orders = (await API.get('/orders?size=100')).list || [];
    const carriers = isSupplier ? [] : (await API.get('/companies?type=LOGISTICS&size=100')).list || [];
    if (!orders.length) { page.appendChild(UI.h('div', { class: 'card' }, UI.h('div', { class: 'empty' }, '暂无订单'))); return; }
    const orderSel = UI.selectField(orders.map((o) => [o.id, o.order_no + '（' + (o.varietyName || '') + '）']), orders[0].id);

    /* 板块一：物流节点跟踪（船到港 → 货物出港 → 到达中转站 → 到达目的地） */
    const trackBody = UI.h('div', { style: 'display:grid;gap:12px' });
    page.appendChild(UI.h('div', { class: 'card' },
      UI.h('div', { class: 'toolbar' },
        UI.h('h3', { style: 'margin:0;border:none;padding:0' }, '物流服务'),
        UI.h('div', { class: 'spacer' }),
        UI.h('label', { class: 'field' }, '选择订单 ', orderSel)),
      UI.h('div', { class: 'hint' },
        '节点跟踪：船到港 → 货物出港 → 到达中转站（公铁联运）→ 到达目的地；运营平台录入节点后本页自动刷新（约 15 秒）。'),
      trackBody));

    /* 95306 式自动更新：运营端录入节点后，钢厂端定时拉取节点进度（离开页面自动停止） */
    const refreshTimer = setInterval(async () => {
      if (location.hash !== '#/logistics' || !document.body.contains(trackBody)) {
        clearInterval(refreshTimer);
        return;
      }
      await loadTrack();
    }, 15000);

    /* 板块二：运输方案与分段运单（保留原有创建/新增能力） */
    const body = UI.h('div', {});
    page.appendChild(body);

    orderSel.addEventListener('change', () => { loadTrack(); loadPlan(); });
    await loadTrack();
    await loadPlan();

    async function loadTrack() {
      trackBody.innerHTML = '';
      let wbs = [];
      try {
        wbs = ((await API.get('/orders/' + orderSel.value + '/tracking')).list) || [];
      } catch (e) { wbs = []; }
      if (!wbs.length) {
        trackBody.appendChild(UI.h('div', { class: 'empty' }, '该订单暂无运单，待运营平台制定运输方案'));
        return;
      }
      wbs.forEach((w) => trackBody.appendChild(trackCard(w, orderSel.selectedOptions[0].textContent.split('（')[0])));
    }

    /* 95306 式轨迹事件流：按运单倒序生成「时间 + 【地点】+ 描述」 */
    const WB_STATE_TXT = {
      PENDING_DEPART: '待发运', IN_TRANSIT: '运输中',
      ARRIVED: '货物已到达', SIGNED: '货物已签收', CANCELLED: '已取消',
    };

    function trackEvents(w) {
      const evs = [];
      if (w.arriveAt) evs.push([w.arriveAt, w.arrivePlace || '目的地', '货物已到达目的地。']);
      if (w.transitAt) evs.push([w.transitAt, w.transitStation || '中转站', '货物已到达中转站。']);
      if (w.departAt) evs.push([w.departAt, w.departPlace || '起运地', '货物已出港发运。']);
      if (w.etaActual) evs.push([w.etaActual, w.departPlace || '起运港', '船已到港，待发运。']);
      evs.push([w.createdAt, w.departPlace || '起运地', '运单已生成，等待发运。']);
      return evs.sort((a, b) => new Date(b[0].replace(' ', 'T')) - new Date(a[0].replace(' ', 'T')));
    }

    function trackCard(w, orderNo) {
      /* 左侧：物流轨迹时间线（倒序，最新一条高亮） */
      const evs = trackEvents(w);
      const trace = UI.h('div', { class: 'trace-line' });
      evs.forEach(([t, loc, txt], i) => {
        const hm = String(t).split(' ')[1] || '';
        const item = UI.h('div', { class: 'trace-item' + (i === 0 ? ' latest' : '') },
          UI.h('div', { class: 'trace-time' }, UI.fmtDate(t), hm ? UI.h('div', {}, hm.slice(0, 5)) : null),
          UI.h('div', { class: 'trace-rail' },
            UI.h('span', { class: 'trace-dot' }),
            i < evs.length - 1 ? UI.h('span', { class: 'trace-seg' }) : null),
          UI.h('div', { class: 'trace-desc' },
            UI.h('span', { class: 'trace-loc' }, '【' + loc + '】'), txt));
        trace.appendChild(item);
      });

      return UI.h('div', { class: 'track-card' },
        UI.h('div', { class: 'wb-head' },
          UI.h('div', { class: 'wb-head-item' }, UI.h('span', { class: 'wb-k' }, '运单号'), UI.h('b', { class: 'wb-v' }, w.waybillNo)),
          UI.h('div', { class: 'wb-head-item' }, UI.h('span', { class: 'wb-k' }, '订单号'), UI.h('span', { class: 'wb-v' }, orderNo)),
          UI.h('div', { class: 'wb-head-item' }, UI.h('span', { class: 'wb-k' }, '运输方式'), UI.h('span', { class: 'wb-v' }, (MODES[w.transportMode] || w.transportMode || '-') + ' · 第 ' + w.segmentNo + ' 段')),
          UI.h('div', { class: 'wb-head-item' }, UI.h('span', { class: 'wb-k' }, '发站'), UI.h('span', { class: 'wb-v' }, w.departPlace || '-')),
          UI.h('div', { class: 'wb-head-item' }, UI.h('span', { class: 'wb-k' }, '到站'), UI.h('span', { class: 'wb-v' }, w.arrivePlace || '-')),
          UI.h('div', { class: 'wb-head-item' }, UI.h('span', { class: 'wb-k' }, '车船号'), UI.h('span', { class: 'wb-v' }, w.vehicleNo || '-')),
          UI.h('div', { class: 'wb-head-item' }, UI.h('span', { class: 'wb-k' }, '计划量'), UI.h('span', { class: 'wb-v' }, w.planQty != null ? UI.fmtQty(w.planQty) + ' 吨' : '-'))),
        UI.h('div', { class: 'trace-body' },
          UI.h('div', { class: 'trace-panel' },
            UI.h('div', { class: 'trace-title' }, '物流轨迹',
              UI.h('span', { class: 'trace-state' }, '【' + (WB_STATE_TXT[w.status] || w.status) + '】')),
            trace),
          UI.h('div', { class: 'trace-side' },
            UI.h('div', { class: 'trace-title' }, '运输信息'),
            UI.h('div', { class: 'side-kv' },
              [['计划发运', UI.fmtDate(w.planDepartDate)],
               ['计划到达', UI.fmtDate(w.planArriveDate)],
               ['预计船到港', UI.fmtDateTime(w.etaPlan)],
               ['中转站', w.transitStation || '-'],
               ['承运商', w.carrierName || '-'],
               ['运费', w.freight != null ? UI.fmtMoney(w.freight) : '-']]
                .map(([k, v]) => UI.h('div', { class: 'side-kv-row' },
                  UI.h('span', { class: 'side-kv-k' }, k),
                  UI.h('span', { class: 'side-kv-v' }, v)))))));
    }

    async function loadPlan() {
      body.innerHTML = '';
      const oid = orderSel.value;
      let plan = null;
      try {
        plan = await API.get('/orders/' + oid + '/logistics-plan');
      } catch (e) { plan = null; }
      /* 供应商只读视图：运输方案 + 分段运单，无创建/新增入口 */
      if (isSupplier) {
        if (!plan) {
          body.appendChild(UI.h('div', { class: 'card' },
            UI.h('div', { class: 'empty' }, '该订单暂无运输方案，待运营平台制定')));
          return;
        }
        body.appendChild(UI.h('div', { class: 'card' },
          UI.h('h3', { class: 'bar-title' }, '运输方案'),
          UI.kv([
            ['方案编号', plan.plan_no || plan.id],
            ['组织方式', plan.org_mode === 'SELF' ? '钢厂自提' : '平台配送'],
            ['创建时间', UI.fmtDateTime(plan.created_at)],
          ])));
        const wbCard = UI.h('div', { class: 'card' },
          UI.h('h3', { class: 'bar-title' }, '分段运单'));
        body.appendChild(wbCard);
        const wb = await API.get('/waybills?size=100&orderId=' + oid);
        wbCard.appendChild(UI.table(waybillCols('SUPPLIER', loadPlan, []), wb.list, '暂无运单'));
        return;
      }
      if (!plan) {
        body.appendChild(UI.h('div', { class: 'card' },
          UI.h('h3', {}, '创建物流方案'),
          UI.h('div', { class: 'inline-flex' },
            UI.h('label', { class: 'field' }, '组织方式 ',
              UI.selectField([['PLATFORM', '平台配送'], ['SELF', '钢厂自提']], 'PLATFORM', { id: 'org-mode' })),
            UI.h('button', { class: 'primary', onclick: async () => {
              const mode = document.getElementById('org-mode').value;
              await API.post('/orders/' + oid + '/logistics-plan', { orgMode: mode });
              UI.toast('方案已创建', 'ok'); loadPlan();
            } }, '创建方案'))));
        return;
      }
      body.appendChild(UI.h('div', { class: 'card' },
        UI.h('h3', {}, '运输方案 ' + (plan.plan_no || plan.id)),
        UI.kv([
          ['组织方式', plan.org_mode === 'SELF' ? '钢厂自提' : '平台配送'],
          ['创建时间', UI.fmtDateTime(plan.created_at)],
        ])));
      const wbCard = UI.h('div', { class: 'card' }, UI.h('h3', {}, '分段运单'));
      body.appendChild(wbCard);
      const wb = await API.get('/waybills?size=100&orderId=' + oid);
      wbCard.appendChild(UI.table(waybillCols('STEEL', loadPlan, carriers), wb.list, '暂无运单'));
      body.appendChild(waybillForm(plan.id, oid, carriers, loadPlan));
    }

    function waybillForm(pid, oid, carriers, onDone) {
      const segmentNo = UI.input('text', '', { placeholder: '如 SEG-1' });
      const mode = UI.selectField(Object.entries(MODES), 'ROAD');
      const planQty = UI.input('number', '', { placeholder: '计划量（吨）' });
      const depart = UI.input('date', '', { placeholder: '计划发运日' });
      const arrive = UI.input('date', '', { placeholder: '计划到达日' });
      const departPlace = UI.input('text', '', { placeholder: '发运地（选填）' });
      const arrivePlace = UI.input('text', '', { placeholder: '到达地（选填）' });
      const freight = UI.input('number', '', { placeholder: '运费（选填）' });
      const vehicle = UI.input('text', '', { placeholder: '车船号（选填）' });
      const carrierSel = UI.selectField([['', '暂不指派']].concat(carriers.map((c) => [c.id, c.companyName])), '');
      const deviation = UI.h('textarea', { rows: 2, style: 'width:100%', placeholder: '分段合计偏差 >5% 时必填' });
      return UI.h('div', { class: 'card' },
        UI.h('h3', {}, '新增分段运单'),
        UI.h('div', { class: 'form-grid' },
          UI.formRow('分段号', segmentNo, true),
          UI.formRow('运输方式', mode, true),
          UI.formRow('计划量', planQty, true),
          UI.formRow('计划发运日', depart, true),
          UI.formRow('计划到达日', arrive, true),
          UI.formRow('发运地', departPlace),
          UI.formRow('到达地', arrivePlace),
          UI.formRow('运费', freight),
          UI.formRow('车船号', vehicle),
          UI.formRow('承运商', carrierSel),
          UI.h('div', { class: 'form-row full' }, UI.h('label', {}, '偏差说明'), deviation)),
        UI.h('button', { class: 'primary', onclick: async () => {
          const body = {
            segmentNo: segmentNo.value.trim(), transportMode: mode.value,
            planQty: planQty.value, planDepartDate: depart.value, planArriveDate: arrive.value,
          };
          if (!body.segmentNo || !body.planQty || !body.planDepartDate || !body.planArriveDate) {
            UI.toast('分段号/计划量/计划发运日/计划到达日为必填', 'err'); return;
          }
          if (departPlace.value.trim()) body.departPlace = departPlace.value.trim();
          if (arrivePlace.value.trim()) body.arrivePlace = arrivePlace.value.trim();
          if (freight.value !== '') body.freight = freight.value;
          if (vehicle.value.trim()) body.vehicleNo = vehicle.value.trim();
          if (carrierSel.value) body.carrierId = Number(carrierSel.value);
          if (deviation.value.trim()) body.deviationReason = deviation.value.trim();
          try {
            await API.post('/logistics-plans/' + pid + '/waybills', body);
            UI.toast('运单已创建', 'ok'); onDone();
          } catch (e) { /* toast 已提示 */ }
        } }, '创建运单'));
    }
  };

  /* -------- 履约跟踪 -------- */
  Pages.track = async function (page, user) {
    const isSteel = (user.roles || []).indexOf('STEEL_BUYER') >= 0;
    const isSupplier = (user.roles || []).indexOf('SUPPLIER') >= 0;
    const orders = (await API.get('/orders?size=100')).list || [];
    if (!orders.length) { page.appendChild(UI.h('div', { class: 'card' }, UI.h('div', { class: 'empty' }, '暂无订单'))); return; }
    const orderSel = UI.selectField(orders.map((o) => [o.id, o.order_no + '（' + (o.varietyName || '') + '）']), orders[0].id);
    const stageBox = UI.h('div', { class: 'flow-steps' });
    const chips = UI.h('div', { class: 'inline-flex', style: 'gap:8px;margin-top:12px' });
    const traceBox = UI.h('div', { class: 'trace-line' });
    const wbMap = new Map();
    const FILTERS = [['ALL', '全部'], ['ORDER', '订单'], ['WAYBILL', '运单'], ['SETTLEMENT', '结算']];
    const BIZ_TAG = { ORDER: ['订单', 'blue'], WAYBILL: ['运单', 'green'], SETTLEMENT: ['结算', 'orange'] };
    /* 历史节点码兜底名称（seed 旧数据与方案节点未入 NODE_TITLES 的） */
    const EXTRA_TITLES = { WAYBILL_ARRIVED: '已到达', WAYBILL_DEPARTED: '已发运', LOGISTICS_PLAN_CREATED: '物流方案配置' };
    let allNodes = [];   // 倒序（最新在前）
    let allNodesRaw = []; // 原始顺序（阶段判定用）
    let filter = 'ALL';

    if (isSupplier) {
      /* 供应商履约跟踪：履约进度 / 履约节点台账 分区（运单列表只读，见 load()） */
      page.appendChild(UI.h('div', { class: 'card' },
        UI.h('h3', { class: 'bar-title' }, '履约进度',
          UI.h('label', { class: 'field', style: 'margin-left:auto' }, '选择订单 ', orderSel)),
        UI.h('div', { class: 'hint', style: 'margin-top:8px' },
          '订单全链五阶段：订单生成 → 双方确认 → 提货计划 → 运输交付 → 结算归档'),
        stageBox));
      page.appendChild(UI.h('div', { class: 'card' },
        UI.h('h3', { class: 'bar-title' }, '履约节点台账',
          UI.h('span', { class: 'hint', style: 'margin-left:auto' }, '节点只增不改（留痕审计），95306 式倒序展示，最新节点高亮')),
        chips,
        UI.h('div', { style: 'margin-top:14px' }, traceBox)));
    } else {
      page.appendChild(UI.h('div', { class: 'card' },
        UI.h('div', { class: 'toolbar' },
          UI.h('h3', { style: 'margin:0;border:none;padding:0' }, '履约跟踪'),
          UI.h('label', { class: 'field' }, '选择订单 ', orderSel)),
        UI.h('div', { class: 'hint' },
          '订单全链节点台账：订单生成 → 双方确认 → 提货计划 → 运输交付 → 结算归档；节点只增不改（留痕审计），95306 式倒序展示，最新节点高亮。'),
        stageBox,
        chips,
        UI.h('div', { style: 'margin-top:14px' }, traceBox),
        isSteel ? UI.h('div', { style: 'margin-top:12px' }, manualNodeForm(orderSel.value, load)) : null));
    }
    const wbBody = UI.h('div', {});
    page.appendChild(wbBody);
    orderSel.addEventListener('change', load);
    await load();

    async function load() {
      const oid = orderSel.value;
      const order = orders.find((o) => String(o.id) === String(oid)) || {};
      const [t, wb] = await Promise.all([
        API.get('/orders/' + oid + '/timeline'),
        API.get('/waybills?size=100&orderId=' + oid),
      ]);
      allNodesRaw = t.list || [];
      allNodes = allNodesRaw.slice()
        .sort((a, b) => new Date(String(b.occurTime).replace(' ', 'T')) - new Date(String(a.occurTime).replace(' ', 'T')));
      wbMap.clear();
      (wb.list || []).forEach((w) => wbMap.set(String(w.id), w.waybillNo || w.waybill_no));
      renderStages(order, wb.list || []);
      renderChips();
      renderTrace();
      wbBody.innerHTML = '';
      const carriers = isSteel ? ((await API.get('/companies?type=LOGISTICS&size=100')).list || []) : [];
      wbBody.appendChild(UI.h('div', { class: 'card' },
        isSupplier
          ? UI.h('h3', { class: 'bar-title' }, '运单列表',
              UI.h('span', { class: 'hint', style: 'margin-left:auto' }, '只读，签收由需方确认'))
          : UI.h('h3', {}, '运单'),
        UI.table(waybillCols(isSupplier ? 'SUPPLIER' : 'STEEL', load, carriers), wb.list || [], '暂无运单')));
    }

    /* 履约五阶段进度：订单生成 → 双方确认 → 提货计划 → 运输交付 → 结算归档 */
    function renderStages(order, wbs) {
      const st = order.status;
      const hasWb = wbs.length > 0;
      const signedAll = hasWb && wbs.every((w) => w.status === 'SIGNED' || w.status === 'CANCELLED');
      const find = (codes) => allNodesRaw.find((n) => codes.indexOf(n.nodeCode) >= 0);
      const settleDone = st === 'COMPLETED'
        || allNodesRaw.some((n) => ['SETTLEMENT_CREATED', 'QUALITY_CHECKED', 'ORDER_ARCHIVED'].indexOf(n.nodeCode) >= 0);
      const stages = [
        ['订单生成', true, find(['AWARDED', 'ORDER_CREATED'])],
        ['双方确认', st !== 'PENDING_CONFIRM', find(['ORDER_CONFIRMED'])],
        ['提货计划', st !== 'PENDING_PICKUP', null],
        ['运输交付', hasWb && signedAll, null],
        ['结算归档', settleDone, null],
      ];
      stageBox.innerHTML = '';
      let curFound = false;
      stages.forEach(([name, done, node], i) => {
        if (i) stageBox.appendChild(UI.h('span', { class: 'flow-arrow' }, '→'));
        const active = !done && !curFound;
        if (active) curFound = true;
        stageBox.appendChild(UI.h('div', {
          class: 'flow-step' + (active ? ' active' : '') + (done ? ' done' : ''),
          title: node ? node.nodeName + ' · ' + node.occurTime : '',
        },
          UI.h('span', { class: 'flow-circle flow-num' }, done ? '✓' : String(i + 1)),
          UI.h('div', { class: 'flow-name' }, name),
          UI.h('div', { class: 'flow-time' },
            done && node ? UI.fmtDateTime(node.occurTime) : (done ? '已完成' : (active ? '进行中' : '待进行')))));
      });
    }

    function renderChips() {
      chips.innerHTML = '';
      FILTERS.forEach(([code, name]) => {
        const count = code === 'ALL' ? allNodes.length : allNodes.filter((n) => n.bizType === code).length;
        chips.appendChild(UI.h('button', {
          class: 'sm' + (filter === code ? ' primary' : ''),
          onclick: () => { filter = code; renderChips(); renderTrace(); },
        }, name + ' ' + count));
      });
    }

    function renderTrace() {
      traceBox.innerHTML = '';
      const list = allNodes.filter((n) => filter === 'ALL' || n.bizType === filter);
      if (!list.length) { traceBox.appendChild(UI.h('div', { class: 'empty' }, '暂无节点记录')); return; }
      list.forEach((n, i) => {
        const hm = String(n.occurTime).split(' ')[1] || '';
        const [tagTxt, tagCls] = BIZ_TAG[n.bizType] || [n.bizType, 'gray'];
        const wbNo = n.bizType === 'WAYBILL' ? wbMap.get(String(n.bizId)) : null;
        const itemName = n.nodeName || EXTRA_TITLES[n.nodeCode] || n.nodeCode;
        const item = UI.h('div', { class: 'trace-item' + (i === 0 ? ' latest' : '') },
          UI.h('div', { class: 'trace-time' }, UI.fmtDate(n.occurTime), hm ? UI.h('div', {}, hm.slice(0, 5)) : null),
          UI.h('div', { class: 'trace-rail' },
            UI.h('span', { class: 'trace-dot' }),
            i < list.length - 1 ? UI.h('span', { class: 'trace-seg' }) : null),
          UI.h('div', { class: 'trace-desc' },
            UI.h('span', { class: 'tag ' + tagCls }, tagTxt),
            ' ',
            wbNo ? UI.h('b', {}, wbNo + ' · ') : null,
            '【' + itemName + '】',
            n.remark ? UI.h('div', { style: 'margin-top:3px;font-size:12px;color:var(--gray-2)' }, n.remark) : null));
        traceBox.appendChild(item);
      });
    }

    function manualNodeForm(oid, onDone) {
      const code = UI.input('text', '', { placeholder: '节点代码（大写，如 LOAD_DONE）' });
      const occur = UI.h('input', { type: 'datetime-local', placeholder: '发生时间' });
      const remark = UI.h('textarea', { rows: 2, style: 'width:100%', placeholder: '备注' });
      const box = UI.h('div', {});
      box.appendChild(UI.h('h3', { style: 'margin:12px 0 8px' }, '手工节点登记'));
      box.appendChild(UI.h('div', { class: 'inline-flex', style: 'flex-wrap:wrap' },
        UI.h('label', { class: 'field' }, '节点代码 ', code),
        UI.h('label', { class: 'field' }, '发生时间 ', occur),
        UI.h('button', { class: 'primary', onclick: async () => {
          if (!code.value.trim()) { UI.toast('请填写节点代码', 'err'); return; }
          const body = { nodeCode: code.value.trim().toUpperCase() };
          if (occur.value) body.occurTime = occur.value.replace('T', ' ') + ':00';
          if (remark.value.trim()) body.remark = remark.value.trim();
          await API.post('/orders/' + oid + '/nodes', body);
          UI.toast('节点已登记', 'ok'); onDone();
        } }, '登 记')));
      box.appendChild(UI.h('div', { style: 'margin-top:8px' }, remark));
      return box;
    }
  };
})();
