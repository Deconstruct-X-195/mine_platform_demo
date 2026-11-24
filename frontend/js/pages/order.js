/* 订单合同物流（PRD 4.5-4.7/T12-T16）：订单确认/合同签署/物流方案/运单作业/履约跟踪 */
(function () {
  window.Pages = window.Pages || {};
  const DELIVERY = { PORT_FOB: '港口FOB', PORT_TRUCK: '港口自提', PLANT: '场内自提' };
  const SETTLE = { PREPAY: '预付款', COD: '货到付款', CREDIT: '账期结算', INSTALLMENT: '分期付款' };
  const MODES = { RAIL: '铁路直达', MULTIMODAL: '公铁联运', ROAD: '汽运直达', SEA: '海运' };
  /* 分段语义：铁路直达/公铁联运按列车拆分（第 N 列，每列独立轨迹动态）；
     汽运直达为持续运输过程——从开始发运到该订单全部吨数到站结束，全程一张运单 */
  function segLabel(mode, seg, short) {
    return mode === 'ROAD' ? (short ? '全程' : '全程持续运输') : '第 ' + seg + ' 列';
  }

  /* -------- 共享：运单列 -------- */
  function waybillCols(mode, onChanged, carriers) {
    return [
      { key: 'segment_no', label: '列次', render: (r) => segLabel(r.transport_mode, r.segment_no, true) },
      { key: 'orderNo', label: '订单号' },
      { key: 'transport_mode', label: '运输方式', render: (r) => MODES[r.transport_mode] || r.transport_mode || '-' },
      { key: 'actual_qty', label: '实发/实收', num: true, render: (r) => r.actual_qty != null ? UI.fmtMoney(r.actual_qty) : '-' },
      { key: 'actual_depart_at', label: '发运时间', render: (r) => UI.fmtDateTime(r.actual_depart_at) },
      { key: 'actual_arrive_at', label: '到达时间', render: (r) => UI.fmtDateTime(r.actual_arrive_at) },
      { key: 'status', label: '状态', render: (r) => UI.statusTag('WAYBILL', r.status) },
    ];
  }

  /* -------- 订单 -------- */
  Pages.order = async function (page, user) {
    const isSteel = (user.roles || []).indexOf('STEEL_BUYER') >= 0;
    const isSupplier = (user.roles || []).indexOf('SUPPLIER') >= 0;
    /* 供应商端订单管理：订单列表 + 订单详情 + 订单确认 */
    if (isSupplier) return supplierOrderView();
    let pageNo = 1;
    const SIZE = 10;
    const selected = new Set();   // 勾选的订单 id（供导出）
    const rowCache = new Map();   // id -> 行数据
    let pageRows = [];            // 当前页行
    const listCard = UI.h('div', { class: 'card' });
    const listBox = UI.h('div', { class: 'list-fixed' });   // 定高列表区（同运营端）：表头39px+10行，超出滚动
    const pagerBox = UI.h('div', {});
    /* 「订单」标题后紧跟导出按钮 */
    page.appendChild(UI.h('div', { class: 'card' },
      UI.h('div', { class: 'toolbar' },
        UI.h('h3', { style: 'margin:0;border:none;padding:0' }, '订单'),
        UI.h('button', { onclick: batchExport }, '导 出'))));
    page.appendChild(listCard);
    listCard.appendChild(listBox);    // 定高列表区：纵向超出滚动，横向滚动条固定在分页行上方
    listCard.appendChild(pagerBox);   // 分页条固定在面板右下角

    async function load() {
      const d = await API.get('/orders' + API.qs({ page: pageNo, size: SIZE }));
      const spotMap = await UI.spotPrices();   // 报价模式单价：品种→港口现货价
      pageRows = d.list || [];
      pageRows.forEach((r) => rowCache.set(r.id, r));
      listBox.innerHTML = '';
      const headBox = UI.h('input', {
        type: 'checkbox',
        checked: pageRows.length > 0 && pageRows.every((r) => selected.has(r.id)),
      });
      headBox.addEventListener('change', () => {
        pageRows.forEach((r) => { if (headBox.checked) selected.add(r.id); else selected.delete(r.id); });
        load();
      });
      listBox.appendChild(UI.table([
        {
          cls: 'sel-col', label: headBox,
          render: (r) => UI.h('input', {
            type: 'checkbox', checked: selected.has(r.id),
            onchange: (e) => { if (e.target.checked) selected.add(r.id); else selected.delete(r.id); syncHead(); },
          }),
        },
        { key: 'order_no', label: '订单号' },
        { key: 'varietyName', label: '品种' },
        { key: 'grade', label: '品位(%)' },
        { key: 'quantity', label: '数量(湿吨)', num: true, render: (r) => UI.fmtMoney(r.myQty != null ? r.myQty : r.quantity) },
        { label: '单价(元/湿吨)', num: true,
          render: (r) => UI.spotShown(r.priceSign, r.priceFloat) || UI.spotDiff(spotMap[r.varietyName], r.unit_price) },
        { label: '运费(元/湿吨)', num: true, render: (r) => (r.freight_price != null ? UI.fmtMoney(r.freight_price) : '-') },
        { key: 'delivery_date', label: '预计交货日', render: (r) => UI.fmtDate(r.delivery_date) },
        { key: 'status', label: '状态', render: (r) => UI.statusTag('ORDER', r.status) },
        { key: 'supplierName', label: '供方' },
        { key: 'confirm_deadline', label: '确认截止', render: (r) => UI.fmtDateTime(r.confirm_deadline) },
        { label: '操作', render: (r) => acts(r) },
      ], d.list, '暂无订单'));
      pagerBox.innerHTML = '';
      UI.pager(pagerBox, pageNo, SIZE, d.total, (p) => { pageNo = p; load(); });
    }

    function selRows() {
      return [...selected].map((id) => rowCache.get(id)).filter(Boolean);
    }
    function syncHead() {
      const hb = listCard.querySelector('thead input[type=checkbox]');
      if (hb) hb.checked = pageRows.length > 0 && pageRows.every((r) => selected.has(r.id));
    }
    async function batchExport() {
      const rows = selRows();
      if (!rows.length) { UI.toast('请先勾选订单', 'err'); return; }
      const spotMap = await UI.spotPrices();   // 报价模式单价：品种→港口现货价
      const priceShown = (r) => UI.spotShown(r.priceSign, r.priceFloat) || UI.spotDiff(spotMap[r.varietyName], r.unit_price);
      const ORDER_TXT = { PENDING_PICKUP: '待收集提货计划', PENDING_TRANSPORT: '待制定运输方案', PENDING_CONFIRM: '待确认', PENDING_CONTRACT: '待签合同', PENDING_EFFECT: '待合同生效', PERFORMING: '履约中', COMPLETED: '已完成', CANCELLED: '已失效' };
      const esc = (s) => '"' + String(s == null ? '' : s).replace(/"/g, '""') + '"';
      const lines = [['订单号', '品种', '品位(%)', '数量(湿吨)', '单价(元/湿吨)', '运费(元/湿吨)', '预计交货日', '状态', '供方', '确认截止'].map(esc)]
        .concat(rows.map((r) => [
          r.order_no,
          r.varietyName,
          r.grade,
          UI.fmtMoney(r.myQty != null ? r.myQty : r.quantity),
          priceShown(r),
          r.freight_price != null ? UI.fmtMoney(r.freight_price) : '-',
          UI.fmtDate(r.delivery_date),
          ORDER_TXT[r.status] || r.status,
          r.supplierName,
          UI.fmtDateTime(r.confirm_deadline),
        ].map(esc).join(',')));
      const blob = new Blob(['\uFEFF' + lines.join('\r\n')], { type: 'text/csv;charset=utf-8' });
      const a = UI.h('a', { href: URL.createObjectURL(blob), download: '订单导出_' + new Date().toISOString().slice(0, 10).replace(/-/g, '') + '.csv' });
      document.body.appendChild(a);
      a.click();
      a.remove();
    }

    function acts(r) {
      const btns = [UI.h('button', { class: 'sm', onclick: () => detail(r.id) }, '详情')];
      // 钢厂确认中标订单（待确认状态）：确认后按钮转为「已确认」
      if (isSteel && r.status === 'PENDING_CONFIRM') {
        btns.push(r.myBuyerConfirmAt
          ? UI.h('button', { class: 'sm success', disabled: true }, '已确认')
          : UI.h('button', { class: 'sm success', onclick: async () => {
              if (!(await UI.confirmBox('确认接受订单 ' + r.order_no + '？'))) return;
              await API.post('/orders/' + r.id + '/confirm-buyer');
              UI.toast('订单已确认', 'ok'); load();
            } }, '确认订单'));
      }
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
      // 订单完成确认（履约中）：物流服务推送过轨迹后可点；各方确认齐备订单自动完成
      if (isSteel && r.status === 'PERFORMING') {
        if (r.myFinishConfirmAt || (!r.myQty && r.buyerFinishConfirmAt)) {
          btns.push(UI.h('button', { class: 'sm success', disabled: true }, '已完成确认'));
        } else {
          btns.push(UI.h('button', {
            class: 'sm primary', disabled: !r.logiPublished,
            title: r.logiPublished ? '' : '待运营端推送物流轨迹后可确认',
            onclick: () => finishConfirm(r),
          }, '订单完成'));
        }
      }
      if (isSteel && r.status === 'COMPLETED') {
        btns.push(UI.h('button', { class: 'sm', onclick: () =>
          API.download('/orders/' + r.id + '/archive/export', 'archive-' + r.order_no + '.zip') }, '导出档案'));
      }
      return UI.h('span', { class: 'inline-flex' }, ...btns);
    }

    /* 订单完成确认：请确认已完成提货验收及所有结算；全部钢厂成员 + 供应商确认齐备后订单自动完成 */
    async function finishConfirm(r) {
      if (!(await UI.confirmBox('请确认已完成提货验收及所有结算。\n确认后待各方确认齐备，订单将自动完成。'))) return;
      const d = await API.post('/orders/' + r.id + '/finish-confirm');
      UI.toast(d.completed ? '各方确认齐备，订单已完成' : '订单完成确认成功，待各方确认齐备后自动完成', 'ok');
      load();
    }

    async function detail(oid) {
      const d = await API.get('/orders/' + oid);
      const pk = d.myPickupPlan;
      const spotBase = (await UI.spotPrices())[d.varietyName] ?? null;   // 报价模式单价
      const body = UI.h('div', {},
        UI.kv([
          ['订单号', d.order_no], ['状态', UI.statusTag('ORDER', d.status)],
          ['品种', d.varietyName], ['品位(%)', d.grade],
          ['数量', UI.fmtMoney(d.myQty != null ? d.myQty : d.quantity) + ' 湿吨'],
          ['单价(元/湿吨)', UI.spotShown(d.priceSign, d.priceFloat) || UI.spotDiff(spotBase, d.unit_price)],
          ['运费(元/湿吨)', d.freight_price != null ? UI.fmtMoney(d.freight_price) : '-'],
          ['是否含税', ({ INC_TAX: '含税', EX_TAX: '不含税' }[d.tax_type]) || '-'],
          ['交货方式', DELIVERY[d.delivery_type] || d.delivery_type], ['交货地点', d.delivery_place],
          ['预计到港时间', UI.fmtDate(d.delivery_date)],
          ['结算', (SETTLE[d.settle_type] || d.settle_type || '-') + (d.settle_days ? ' ' + d.settle_days + '天' : '')],
          ['供方', d.supplierName],
          ['确认截止', UI.fmtDateTime(d.confirm_deadline)],
        ]),
        UI.h('h3', { style: 'margin-top:14px' }, '本厂提货计划'),
        pk && pk.status === 'SUBMITTED'
          ? UI.kv([
              ['提货开始日期', UI.fmtDate(pk.startDate)],
              ['日提货吨数', UI.fmtMoney(pk.dailyQty) + ' 湿吨'],
              ['备注', pk.remark || '-'],
              ['提交时间', UI.fmtDateTime(pk.submittedAt)],
            ])
          : UI.h('div', { class: 'empty' },
              pk ? '本厂提货计划尚未提交，请在订单列表点击「提货计划」提交'
                 : '该订单无提货计划（按合同约定交付）'));
      UI.modal('订单详情', body, [], { wide: true });
    }

    /* 提货计划：开始提货日期 + 日提货吨数 + 备注；全部钢厂提交后订单进入待制定运输方案 */
    function pickupPlanModal(r) {
      const start = UI.input('date', '', {});
      const daily = UI.input('number', '', { min: '0', step: '0.01', placeholder: '湿吨/天' });
      const remark = UI.input('text', '', { placeholder: '备注（可选，200 字以内）' });
      const m = UI.modal((r.myPickupStatus === 'SUBMITTED' ? '修改' : '提交') + '提货计划 · ' + r.order_no,
        UI.h('div', {},
          UI.h('div', { class: 'hint', style: 'margin-bottom:8px' },
            '集采订单由多家钢厂共同供货，贵司份额 ' + UI.fmtMoney(r.myQty) + ' 湿吨'),
          UI.h('div', { class: 'form-grid' },
            UI.formRow('开始提货日期', start, true),
            UI.formRow('日提货吨数(湿吨)', daily, true),
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

    /* 供应商端订单管理：订单列表（待确认订单直接在列表中确认，48h 期限）+ 订单详情 */
    async function supplierOrderView() {
      let pageNo = 1;
      const SIZE = 10;
      const spotMap = await UI.spotPrices();   // 报价模式单价：品种→港口现货价
      const listCard = UI.h('div', { class: 'card' });
      const listBox = UI.h('div', { class: 'list-fixed' });   // 定高列表区（同运营端）：表头39px+10行，超出滚动
      const pagerBox = UI.h('div', {});
      page.appendChild(UI.h('div', { class: 'card' },
        UI.h('h3', { class: 'bar-title' }, '订单列表',
          UI.h('span', { class: 'hint', style: 'margin-left:auto' }, '点击「详情」查看订单明细'))));
      page.appendChild(listCard);
      listCard.appendChild(listBox);    // 定高列表区：纵向超出滚动，横向滚动条固定在分页行上方
      listCard.appendChild(pagerBox);   // 分页条固定在面板右下角

      function confirmBtn(r) {
        return UI.h('button', { class: 'sm success', onclick: async () => {
          if (!(await UI.confirmBox('确认接受订单 ' + r.order_no + '？确认后进入提货计划收集环节。'))) return;
          await API.put('/orders/' + r.id + '/confirm');
          UI.toast('订单已确认', 'ok'); load();
        } }, '确认订单');
      }

      /* 供应商订单完成确认：物流服务推送过轨迹后可点；各方确认齐备 → 订单自动完成归档 */
      const finishBtn = (r) => UI.h('button', {
        class: 'sm primary', disabled: !r.logiPublished,
        title: r.logiPublished ? '' : '待运营端推送物流服务后可确认',
        onclick: async () => {
          if (!(await UI.confirmBox('请确认已完成提货验收及所有结算。\n确认后待各方确认齐备，订单将自动完成。'))) return;
          const d = await API.post('/orders/' + r.id + '/finish-confirm');
          UI.toast(d.completed ? '各方确认齐备，订单已完成' : '订单完成确认成功，待各方确认齐备后自动完成', 'ok');
          load();
        },
      }, '订单完成');

      const cols = () => [
        { key: 'order_no', label: '订单号' },
        { key: 'varietyName', label: '品种' },
        { key: 'grade', label: '品位(%)' },
        { key: 'quantity', label: '数量(湿吨)', num: true, render: (r) => UI.fmtMoney(r.myQty != null ? r.myQty : r.quantity) },
        { label: '单价(元/湿吨)', num: true,
          render: (r) => UI.spotShown(r.priceSign, r.priceFloat) || UI.spotDiff(spotMap[r.varietyName], r.unit_price) },
        { label: '运费(元/湿吨)', num: true, render: (r) => (r.freight_price != null ? UI.fmtMoney(r.freight_price) : '-') },
        { key: 'delivery_date', label: '预计到港时间', render: (r) => UI.fmtDate(r.delivery_date) },
        { key: 'status', label: '状态', render: (r) => UI.statusTag('ORDER', r.status) },
        { label: '需方', render: (r) => r.buyerNames || r.buyerName || '-' },
        { key: 'confirm_deadline', label: '确认截止', render: (r) => UI.fmtDateTime(r.confirm_deadline) },
        { label: '操作', render: (r) => {
            const btns = [UI.h('button', { class: 'sm', onclick: () => supplierDetail(r.id) }, '详情')];
            if (r.status === 'PENDING_CONFIRM') btns.push(confirmBtn(r));
            if (r.status === 'PERFORMING') {
              btns.push(r.supplierFinishConfirmAt
                ? UI.h('button', { class: 'sm success', disabled: true }, '已完成确认')
                : finishBtn(r));
            }
            return UI.h('span', { class: 'inline-flex' }, ...btns);
          } },
      ];

      async function load() {
        const d = await API.get('/orders' + API.qs({ page: pageNo, size: SIZE }));
        listBox.innerHTML = '';
        listBox.appendChild(UI.table(cols(), d.list, '暂无订单'));
        pagerBox.innerHTML = '';
        UI.pager(pagerBox, pageNo, SIZE, d.total, (p) => { pageNo = p; load(); });
      }

      /* 订单详情：分区展示（基本信息/交货与结算/需供双方）；需方为参与该归集单的全部钢厂 */
      async function supplierDetail(oid) {
        const d = await API.get('/orders/' + oid);
        const spotBase = (await UI.spotPrices())[d.varietyName] ?? null;   // 报价模式单价
        const body = UI.h('div', {},
          UI.h('div', { class: 'sec-title' }, '基本信息'),
          UI.kv([
            ['订单号', d.order_no], ['状态', UI.statusTag('ORDER', d.status)],
            ['品种', d.varietyName], ['品位(%)', d.grade],
            ['数量', UI.fmtMoney(d.quantity) + ' 湿吨'],
            ['单价(元/湿吨)', UI.spotShown(d.priceSign, d.priceFloat) || UI.spotDiff(spotBase, d.unit_price)],
            ['运费(元/湿吨)', d.freight_price != null ? UI.fmtMoney(d.freight_price) : '-'],
            ['是否含税', ({ INC_TAX: '含税', EX_TAX: '不含税' }[d.tax_type]) || '-'],
          ]),
          UI.h('div', { class: 'sec-title' }, '交货与结算'),
          UI.kv([
            ['交货方式', DELIVERY[d.delivery_type] || d.delivery_type], ['交货地点', d.delivery_place],
            ['预计到港时间', UI.fmtDate(d.delivery_date)],
            ['结算', (SETTLE[d.settle_type] || d.settle_type || '-') + (d.settle_days ? ' ' + d.settle_days + '天' : '')],
          ]),
          UI.h('div', { class: 'sec-title' }, '需供双方'),
          UI.kv([
            ['需方', d.buyerNames || d.buyerName || '-'], ['供方', d.supplierName],
            ['确认截止', UI.fmtDateTime(d.confirm_deadline)],
          ]));
        UI.modal('订单详情 · ' + d.order_no, body, [], { wide: true });
      }

      await load();
    }

    await load();
  };

  /* -------- 物流服务：供应商主视图（95306 轨迹 + 运输方案/分段运单/详情），钢厂端收货视图（方案/运单/签收）；
     运单由运营端运输调度统一创建，物流方案组织方式由钢厂选择 -------- */
  Pages.logistics = async function (page, user) {
    /* 供应商端为主视图：95306 物流节点跟踪（每列车一条轨迹动态）+ 运输方案 + 分段运单（详情）；
       钢厂端为收货视图：运输方案（含创建，组织方式为钢厂选择）+ 分段运单（详情/签收） */
    const isSupplier = (user.roles || []).indexOf('SUPPLIER') >= 0;
    /* 运单状态文案（95306 轨迹面板角标）：须在首次渲染前声明（避免初始 await 先触发 TDZ） */
    const WB_STATE_TXT = {
      PENDING_DEPART: '待发运', IN_TRANSIT: '运输中',
      ARRIVED: '货物已到达', SIGNED: '货物已签收', CANCELLED: '已取消',
    };
    const orders = (await API.get('/orders?size=100')).list || [];
    if (!orders.length) { page.appendChild(UI.h('div', { class: 'card' }, UI.h('div', { class: 'empty' }, '暂无订单'))); return; }
    const orderSel = UI.selectField(orders.map((o) => [o.id, o.order_no + '（' + (o.varietyName || '') + '）']), orders[0].id);

    /* 供应商端：板块一 95306 物流节点跟踪（按运单/运输方式分卡）；钢厂端：工具栏 + 总节点跟踪（合并时间线） */
    let trackBody = null;
    let trackAllBody = null;
    let planInfo = null;
    let cargoBox = null;
    /* 供应商端运输方案内容容器（页面上方卡片，含选择订单） */
    let body = null;
    if (isSupplier) {
      /* 供应商端：运输方案（顶部，含选择订单）+ 物流服务整个框（bar-title 蓝竖线） */
      trackBody = UI.h('div', { style: 'display:grid;gap:12px;padding:0 16px 16px' });
      body = UI.h('div', { style: 'padding:0 16px 16px' });
      page.appendChild(UI.h('div', { class: 'card' },
        UI.h('h3', { class: 'bar-title' }, '运输方案',
          UI.h('label', { class: 'field', style: 'margin-left:auto' }, '选择订单 ', orderSel)),
        body));
      page.appendChild(UI.h('div', { class: 'card' },
        UI.h('h3', { class: 'bar-title' }, '物流服务'),
        trackBody));
    } else {
      /* 钢厂端：物流节点跟踪整个框（与供应商端一致，bar-title 蓝竖线），选择订单置于标题右侧 */
      planInfo = UI.h('div', { class: 'wb-head', style: 'margin:12px 16px 16px' });
      trackAllBody = UI.h('div', { class: 'trace-line' });
      cargoBox = UI.h('div', { class: 'side-kv' });
      page.appendChild(UI.h('div', { class: 'card' },
        UI.h('h3', { class: 'bar-title' }, '物流节点跟踪',
          UI.h('label', { class: 'field', style: 'margin-left:auto' }, '选择订单 ', orderSel)),
        planInfo,
        UI.h('div', { class: 'trace-box trace-body trace-body-tall', style: 'margin:0 16px 16px' },
          UI.h('div', { class: 'trace-panel' }, trackAllBody),
          UI.h('div', { class: 'trace-side' },
            UI.h('div', { class: 'trace-title' }, '货物信息'),
            cargoBox))));
    }

    if (isSupplier) {
      /* 95306 式自动更新：轨迹由运营端运输调度填写，钢厂/供应商端定时拉取节点进度（离开页面自动停止）；
         刷新前后保持滚动位置，避免面板来回跳动 */
      const refreshTimer = setInterval(async () => {
        if (location.hash !== '#/logistics' || !document.body.contains(trackBody)) {
          clearInterval(refreshTimer);
          return;
        }
        const y = window.scrollY;
        await loadTrack();
        await loadPlan();
        window.scrollTo(0, y);
      }, 15000);
    } else {
      /* 钢厂端同源自动刷新：运营端录入节点后，节点跟踪/货物信息约 15 秒自动更新（保持滚动位置） */
      const refreshTimer = setInterval(async () => {
        if (location.hash !== '#/logistics' || !document.body.contains(trackAllBody)) {
          clearInterval(refreshTimer);
          return;
        }
        const y = window.scrollY;
        await loadMerged();
        await loadPlan();
        window.scrollTo(0, y);
      }, 15000);
    }

    /* 数据签名缓存：内容未变化时跳过重建面板，避免定时刷新引起跳动（须在首次渲染前声明） */
    let lastTrackSig = null;
    let lastMergedSig = null;
    let lastPlanSig = null;

    if (isSupplier) {
      orderSel.addEventListener('change', () => { loadTrack(true); loadPlan(true); });
      await loadTrack(true);
    } else {
      orderSel.addEventListener('change', () => { loadMerged(true); loadPlan(true); });
      await loadMerged(true);
    }
    await loadPlan(true);

    async function loadTrack(force) {
      let d0 = null;
      try {
        d0 = await API.get('/orders/' + orderSel.value + '/tracking');
      } catch (e) { d0 = null; }
      const wbs = (d0 && d0.list) || [];
      const cargo = (d0 && d0.cargo) || null;
      const sig = JSON.stringify([wbs, cargo]);
      if (!force && sig === lastTrackSig) return;
      lastTrackSig = sig;
      /* 原位原子更新：先在离屏片段构建，再一次性替换，面板不闪动不跳动 */
      const frag = document.createDocumentFragment();
      if (!wbs.length) {
        frag.appendChild(UI.h('div', { class: 'empty' }, '该订单暂无运单，待运营平台制定运输方案并推送'));
      } else {
        const orderNo = orderSel.selectedOptions[0].textContent.split('（')[0];
        wbs.forEach((w) => frag.appendChild(trackCard(w, orderNo, cargo, wbs)));
      }
      trackBody.replaceChildren(frag);
    }

    /* 钢厂端：物流节点跟踪——全部运单节点合并为一条倒序时间线（不标注运输方式） */
    async function loadMerged(force) {
      if (!trackAllBody) return;
      let wbs = [];
      try {
        wbs = ((await API.get('/orders/' + orderSel.value + '/tracking')).list) || [];
      } catch (e) { wbs = []; }
      const sig = JSON.stringify(wbs);
      if (!force && sig === lastMergedSig) return;
      lastMergedSig = sig;
      /* 原位原子更新：离屏构建后一次性替换 */
      const frag = document.createDocumentFragment();
      if (!wbs.length) {
        frag.appendChild(UI.h('div', { class: 'empty' }, '该订单暂无运单节点，待运营端推送物流轨迹'));
      }
      const all = [];
      wbs.forEach((w) => trackEvents(w).forEach((ev) => all.push(ev)));
      all.sort((a, b) => new Date(String(b[0]).replace(' ', 'T')) - new Date(String(a[0]).replace(' ', 'T')));
      all.forEach(([t, loc, txt], i) => {
        const hm = String(t).split(' ')[1] || '';
        frag.appendChild(UI.h('div', { class: 'trace-item' + (i === 0 && wbs.length ? ' latest' : '') },
          UI.h('div', { class: 'trace-time' }, UI.fmtDate(t) + (hm ? ' ' + hm.slice(0, 5) : '')),
          UI.h('div', { class: 'trace-rail' },
            UI.h('span', { class: 'trace-dot' }),
            UI.h('span', { class: 'trace-seg' })),
          UI.h('div', { class: 'trace-desc' },
            UI.h('span', { class: 'trace-loc' }, '【' + loc + '】'), txt)));
      });
      trackAllBody.replaceChildren(frag);
    }

    /* 95306 式轨迹事件流：节点录入追加的轨迹日志（nodeLog）优先；
       无日志时按固定节点时间兜底（旧数据）；「运单已生成」始终保留 */
    function trackEvents(w) {
      const dot = (s) => (String(s || '').replace(/。*$/, '') + '。');
      const evs = [];
      const nl = Array.isArray(w.nodeLog) ? w.nodeLog : [];
      if (nl.length) {
        nl.forEach((e) => evs.push([e.occurTime, e.loc || '节点', dot(e.desc)]));
      } else {
        if (w.arriveAt) evs.push([w.arriveAt, w.arrivePlace || '目的地', '货物已到达目的地。']);
        if (w.transitAt) evs.push([w.transitAt, w.transitStation || '中转站', '货物已到达中转站。']);
        if (w.departAt) evs.push([w.departAt, w.departPlace || '起运地', '货物已出港发运。']);
        if (w.etaActual) evs.push([w.etaActual, w.departPlace || '起运港', '船已到港，待发运。']);
      }
      evs.push([w.createdAt, w.departPlace || '起运地', '运单已生成，等待发运。']);
      return evs.sort((a, b) => new Date(String(b[0]).replace(' ', 'T')) - new Date(String(a[0]).replace(' ', 'T')));
    }

    function trackCard(w, orderNo, cargo, allWbs) {
      /* 左侧：物流轨迹时间线（倒序，最新一条高亮） */
      const evs = trackEvents(w);
      const trace = UI.h('div', { class: 'trace-line' });
      evs.forEach(([t, loc, txt], i) => {
        const hm = String(t).split(' ')[1] || '';
        const item = UI.h('div', { class: 'trace-item' + (i === 0 ? ' latest' : '') },
          UI.h('div', { class: 'trace-time' }, UI.fmtDate(t) + (hm ? ' ' + hm.slice(0, 5) : '')),
          UI.h('div', { class: 'trace-rail' },
            UI.h('span', { class: 'trace-dot' }),
            i < evs.length - 1 ? UI.h('span', { class: 'trace-seg' }) : null),
          UI.h('div', { class: 'trace-desc' },
            UI.h('span', { class: 'trace-loc' }, '【' + loc + '】'), txt));
        trace.appendChild(item);
      });

      /* 右侧：货物信息（同钢厂端六项）——优先运营端录入/推送的供应商货物信息；未推送时按运单实时汇总 */
      const wbs = allWbs || [w];
      const qtyOf = (x) => (x.actualQty != null ? Number(x.actualQty) : (x.planQty != null ? Number(x.planQty) : 0));
      const wbSum = (sts) => wbs.filter((x) => sts.indexOf(x.status) >= 0).reduce((s, x) => s + qtyOf(x), 0);
      const hasCargo = cargo && (cargo.cargoUpdatedAt || cargo.totalQty != null);
      const rows = hasCargo
        ? [['货物总量', cargo.totalQty], ['出港', cargo.shippedQty], ['在途', cargo.transitQty],
           ['到站', cargo.arrivedQty], ['可提货', cargo.pickupQty]]
        : [['货物总量', null], ['出港', wbSum(['IN_TRANSIT', 'ARRIVED', 'SIGNED'])], ['在途', wbSum(['IN_TRANSIT'])],
           ['到站', wbSum(['ARRIVED', 'SIGNED'])], ['可提货', wbSum(['ARRIVED'])]];
      const sideRow = (k, v) => UI.h('div', { class: 'side-kv-row' },
        UI.h('span', { class: 'side-kv-k' }, k),
        UI.h('span', { class: 'side-kv-v' }, v));

      return UI.h('div', { class: 'track-card' },
        UI.h('div', { class: 'wb-head' },
          UI.h('div', { class: 'wb-head-item' }, UI.h('span', { class: 'wb-k' }, '运单号'), UI.h('b', { class: 'wb-v' }, w.waybillNo)),
          UI.h('div', { class: 'wb-head-item' }, UI.h('span', { class: 'wb-k' }, '订单号'), UI.h('span', { class: 'wb-v' }, orderNo)),
          UI.h('div', { class: 'wb-head-item' }, UI.h('span', { class: 'wb-k' }, '运输方式'), UI.h('span', { class: 'wb-v' }, (MODES[w.transportMode] || w.transportMode || '-') + ' · ' + segLabel(w.transportMode, w.segmentNo))),
          UI.h('div', { class: 'wb-head-item' }, UI.h('span', { class: 'wb-k' }, '发站'), UI.h('span', { class: 'wb-v' }, w.departPlace || '-')),
          UI.h('div', { class: 'wb-head-item' }, UI.h('span', { class: 'wb-k' }, '到站'), UI.h('span', { class: 'wb-v' }, w.arrivePlace || '-'))),
        UI.h('div', { class: 'trace-body' },
          UI.h('div', { class: 'trace-panel' },
            UI.h('div', { class: 'trace-title' }, '物流轨迹'),
            trace),
          UI.h('div', { class: 'trace-side' },
            UI.h('div', { class: 'trace-title' }, '货物信息'),
            UI.h('div', { class: 'side-kv' },
              rows.map(([k, v]) => sideRow(k, v != null && v !== '' ? UI.fmtMoney(Number(v)) + ' 湿吨' : '-')),
              sideRow('信息来源', hasCargo && cargo.cargoUpdatedAt ? '平台 ' + UI.fmtDateTime(cargo.cargoUpdatedAt) : '运单实时汇总')))));
    }

    async function loadPlan(force) {
      const oid = orderSel.value;
      let plan = null;
      try {
        plan = await API.get('/orders/' + oid + '/logistics-plan');
      } catch (e) { plan = null; }
      /* 供应商主视图：运输方案（三框内容由运营端推送后可见并随推送更新）；
         数据齐取后比对签名，未变化跳过重建 */
      if (isSupplier) {
        let pub = null;
        try {
          pub = await API.get('/orders/' + oid + '/tracking');
        } catch (e) { pub = null; }
        const pushed = (pub && pub.plan) ? pub.plan : null;
        const sig = JSON.stringify([plan, pushed]);
        if (!force && sig === lastPlanSig) return;
        lastPlanSig = sig;
        /* 原位原子更新：离屏构建后一次性替换（内容渲染进顶部「运输方案」卡片） */
        const frag = document.createDocumentFragment();
        if (!plan) {
          frag.appendChild(UI.h('div', { class: 'empty', style: 'padding:12px 0' }, '该订单暂无运输方案，待运营平台制定'));
          body.replaceChildren(frag);
          return;
        }
        frag.appendChild(UI.kv([
          ['方案编号', plan.plan_no || plan.id],
          ['组织方式', plan.org_mode === 'SELF' ? '钢厂自提' : '平台配送'],
          ['创建时间', UI.fmtDateTime(plan.created_at)],
        ]));
        /* 三框运输方案内容（推送门控）：运营端「运输方案板块推送供应商 / 推送供应商」后可见并随推送更新 */
        if (pushed) {
          const secOf = (label, txt) => txt ? UI.h('div', { style: 'margin-top:10px' },
            UI.h('div', { style: 'font-weight:600;margin-bottom:4px' }, label),
            UI.h('div', { style: 'white-space:pre-wrap;line-height:1.6;color:var(--ink-2,#555)' }, txt)) : null;
          [['铁路直达', pushed.rail], ['公铁联运', pushed.multimodal], ['汽运直达', pushed.truck]]
            .forEach(([label, txt]) => { const el = secOf(label, txt); if (el) frag.appendChild(el); });
        } else {
          frag.appendChild(UI.h('div', { class: 'empty', style: 'margin-top:10px' }, '运输方案内容待运营端推送后显示'));
        }
        body.replaceChildren(frag);
        return;
      }
      /* 钢厂端：运输方案面板已删除——组织方式/创建时间渲染进节点跟踪面板信息条 */
      if (planInfo) {
        const pf = document.createDocumentFragment();
        pf.appendChild(UI.h('div', { class: 'wb-head-item' },
          UI.h('span', { class: 'wb-k' }, '组织方式'),
          UI.h('span', { class: 'wb-v' }, plan ? (plan.org_mode === 'SELF' ? '钢厂自提' : '平台配送') : '-')));
        pf.appendChild(UI.h('div', { class: 'wb-head-item' },
          UI.h('span', { class: 'wb-k' }, '创建时间'),
          UI.h('span', { class: 'wb-v' }, plan ? UI.fmtDateTime(plan.created_at) : '-')));
        planInfo.replaceChildren(pf);
      }
      await loadCargo(oid);
    }

    /* 钢厂端：货物信息（节点跟踪右侧）——货物总量/出港/在途/到站/可提货（湿吨）；
       推送门控：读发布快照（运营端「推送」后可见）；快照无本厂货物信息时按已推送运单实时汇总 */
    async function loadCargo(oid) {
      if (!cargoBox) return;
      let list = [];
      let cargo = null;
      try {
        const t = await API.get('/orders/' + oid + '/tracking');
        list = t.list || [];
        cargo = t.cargo || null;
      } catch (e) { list = []; cargo = null; }
      const qtyOf = (w) => (w.actualQty != null ? Number(w.actualQty) : (w.planQty != null ? Number(w.planQty) : 0));
      const sum = (sts) => list.filter((w) => sts.indexOf(w.status) >= 0).reduce((s, w) => s + qtyOf(w), 0);
      const rows = cargo
        ? [['货物总量', cargo.totalQty], ['出港', cargo.shippedQty], ['在途', cargo.transitQty],
           ['到站', cargo.arrivedQty], ['可提货', cargo.pickupQty]]
        : [['货物总量', null], ['出港', sum(['IN_TRANSIT', 'ARRIVED', 'SIGNED'])], ['在途', sum(['IN_TRANSIT'])],
           ['到站', sum(['ARRIVED', 'SIGNED'])], ['可提货', sum(['ARRIVED'])]];
      cargoBox.replaceChildren(...rows.map(([k, v]) => UI.h('div', { class: 'side-kv-row' },
        UI.h('span', { class: 'side-kv-k' }, k),
        UI.h('span', { class: 'side-kv-v' }, v != null && v !== '' ? UI.fmtMoney(Number(v)) + ' 湿吨' : '-'))),
        UI.h('div', { class: 'side-kv-row' },
          UI.h('span', { class: 'side-kv-k' }, '信息来源'),
          UI.h('span', { class: 'side-kv-v' }, cargo ? '平台 ' + UI.fmtDateTime(cargo.cargoUpdatedAt) : '运单实时汇总')));
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
    /* 履约节点台账：面板固定高度（约 10 条），多余节点滚动查看 */
    const traceBox = UI.h('div', { class: 'trace-line', style: 'max-height:660px;overflow-y:auto' });
    let fulfillBody = null;
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
          '订单全链五阶段：订单生成 → 双方确认 → 提货计划 → 运输交付 → 验收归档'),
        stageBox));
      page.appendChild(UI.h('div', { class: 'card' },
        UI.h('h3', { class: 'bar-title' }, '履约节点台账',
          UI.h('span', { class: 'hint', style: 'margin-left:auto' }, '节点只增不改（留痕审计）')),
        chips,
        UI.h('div', { style: 'margin-top:14px' }, traceBox)));
    } else {
      /* 钢厂端：五阶段进度 + 全链信息表（节点轨迹台账/手工节点登记/运单面板已下线，信息以表格呈现） */
      page.appendChild(UI.h('div', { class: 'card' },
        UI.h('div', { class: 'toolbar' },
          UI.h('h3', { style: 'margin:0;border:none;padding:0' }, '履约跟踪'),
          UI.h('label', { class: 'field' }, '选择订单 ', orderSel)),
        stageBox));
      fulfillBody = UI.h('div', {});
      page.appendChild(fulfillBody);
    }
    const wbBody = UI.h('div', {});
    if (isSupplier) page.appendChild(wbBody);
    orderSel.addEventListener('change', load);
    await load();

    async function load() {
      const oid = orderSel.value;
      const order = orders.find((o) => String(o.id) === String(oid)) || {};
      if (!isSupplier) {
        /* 钢厂端：五阶段进度 + 全链信息表（一次取数，物流/交付/结算全部覆盖） */
        const [t, f] = await Promise.all([
          API.get('/orders/' + oid + '/timeline'),
          API.get('/orders/' + oid + '/fulfillment'),
        ]);
        allNodesRaw = t.list || [];
        const spotMap = await UI.spotPrices();   // 报价模式单价：品种→港口现货价
        renderStages(order, f.waybills || []);
        renderFulfillment(f, spotMap[order.varietyName] ?? null);
        return;
      }
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
      wbBody.appendChild(UI.h('div', { class: 'card' },
        UI.h('h3', { class: 'bar-title' }, '运单列表',
          UI.h('span', { class: 'hint', style: 'margin-left:auto' }, '只读')),
        UI.table(waybillCols('SUPPLIER', load, []), wb.list || [], '暂无运单')));
    }

    /* 履约五阶段进度：订单生成 → 双方确认 → 提货计划 → 运输交付 → 验收归档 */
    function renderStages(order, wbs) {
      const st = order.status;
      const hasWb = wbs.length > 0;
      const signedAll = hasWb && wbs.every((w) => w.status === 'SIGNED' || w.status === 'CANCELLED');
      const find = (codes) => allNodesRaw.find((n) => codes.indexOf(n.nodeCode) >= 0);
      /* 验收归档：双方确认验收齐备后订单自动完成（付款结算线下完成，平台不登记） */
      const acceptDone = st === 'COMPLETED'
        || (allNodesRaw.some((n) => n.nodeCode === 'SUPPLY_CONFIRMED')
            && allNodesRaw.some((n) => n.nodeCode === 'DEMAND_CONFIRMED'))
        || allNodesRaw.some((n) => n.nodeCode === 'ORDER_ARCHIVED');
      /* 运输交付：运单全部签收，或订单已完成（验收归档完成则前序环节必然完成） */
      const transportDone = (hasWb && signedAll) || acceptDone;
      const stages = [
        ['订单生成', true, find(['AWARDED', 'ORDER_CREATED'])],
        ['双方确认', st !== 'PENDING_CONFIRM', find(['ORDER_CONFIRMED'])],
        ['提货计划', st !== 'PENDING_CONFIRM' && st !== 'PENDING_PICKUP', null],
        ['运输交付', transportDone, null],
        ['验收归档', acceptDone, null],
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
          UI.h('div', { class: 'trace-time' }, UI.fmtDate(n.occurTime) + (hm ? ' ' + hm.slice(0, 5) : '')),
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

    /* 钢厂端全链信息表：询价 / 议价反馈 / 订单 / 提货计划 / 物流方案 / 运单 / 交付验收 / 结算 */
    /* 钢厂端一个订单仅呈现一条运单记录：多段运单聚合为一行（整体轨迹进度，不显示运输方式与分列明细） */
    function aggWaybill(wbs) {
      const act = (wbs || []).filter((w) => w.status !== 'CANCELLED');
      if (!act.length) return null;
      const seg = (act[0].depart_place || '起运地') + ' → ' + (act[act.length - 1].arrive_place || '到达地');
      const deps = act.map((w) => w.actual_depart_at).filter(Boolean).sort();
      const arrs = act.map((w) => w.actual_arrive_at).filter(Boolean).sort();
      const allSigned = act.every((w) => w.status === 'SIGNED');
      const allArrived = allSigned || act.every((w) => w.status === 'ARRIVED' || w.status === 'SIGNED');
      let track, status;
      if (allSigned) {
        track = seg + '（' + UI.fmtDateTime(deps[0]) + ' 发运 → ' + UI.fmtDateTime(arrs[arrs.length - 1]) + ' 到达，已签收）';
        status = 'SIGNED';
      } else if (allArrived) {
        track = seg + '（' + UI.fmtDateTime(deps[0]) + ' 发运 → ' + UI.fmtDateTime(arrs[arrs.length - 1]) + ' 到达）';
        status = 'ARRIVED';
      } else if (deps.length) {
        track = seg + '（' + UI.fmtDateTime(deps[0]) + ' 发运，运输中）';
        status = 'IN_TRANSIT';
      } else {
        track = seg + '（待发运）';
        status = act[0].status;
      }
      return {
        no: act.length === 1 ? act[0].waybill_no : act[0].waybill_no + ' 等 ' + act.length + ' 单',
        track: track,
        status: status,
        arrived: act.filter((w) => w.status === 'ARRIVED'),
        createdAt: act[0].created_at,
      };
    }
    function renderFulfillment(f, spotBase) {
      fulfillBody.innerHTML = '';
      const rows = [];
      const inq = f.inquiry;
      if (inq) {
        /* 钢厂需求品类/吨数 + 报价单价（报价模式：港口现货价格±上下浮；中标 WIN 报价优先，无则取订单单价兜底） */
        const price = inq.winPrice != null && inq.winPrice !== ''
          ? Number(inq.winPrice)
          : (f.unit_price != null ? Number(f.unit_price) : null);
        rows.push(['询价', inq.inquiry_no || '-',
          '需求品类 ' + (inq.varietyName || '-') + ' · 需求吨数 ' + UI.fmtQty(inq.quantity) + ' 湿吨'
            + ' · 报价 ' + (price != null
              ? (UI.spotShown(inq.priceSign, inq.priceFloat) || UI.spotDiff(spotBase, price)) : '-'),
          inq.created_at, UI.statusTag('INQUIRY', inq.status)]);
      }
      const fb = f.feedback;
      if (fb) rows.push(['议价反馈', '-',
        fb.decision === 'ACCEPTED' ? '本厂认可（归集询价评审，全员认可自动成单）' : '本厂不认可：' + (fb.reason || '-'),
        fb.created_at, UI.h('span', { class: 'tag ' + (fb.decision === 'ACCEPTED' ? 'green' : 'red') },
          fb.decision === 'ACCEPTED' ? '已认可' : '已反馈')]);
      rows.push(['订单', f.order_no || '-',
        UI.fmtQty(f.quantity) + ' 湿吨 · 供应商 ' + (f.supplierName || '-'),
        f.created_at, UI.statusTag('ORDER', f.status)]);
      const pk = f.pickup;
      const isAgg = f.buyer_id == null; // 集采聚合订单才有提货计划收集环节，普通订单按合同约定交付
      const pkDone = pk && pk.submitted_at;
      rows.push(['提货计划', '-',
        pkDone
          ? '预期提货时间 ' + UI.fmtDate(pk.pickup_start_date) + ' · 日提 ' + UI.fmtQty(pk.daily_qty) + ' 湿吨'
            + (pk.pickup_remark ? ' · ' + pk.pickup_remark : '')
          : (isAgg ? '本厂提货计划未提交' : '普通订单按合同约定交付，无需提货计划'),
        pkDone ? pk.submitted_at : '-',
        pkDone ? UI.h('span', { class: 'tag blue' }, '已提交')
          : (isAgg ? UI.h('span', { class: 'tag orange' }, '待提交') : UI.h('span', { class: 'tag gray' }, '不适用'))]);
      const pl = f.plan;
      rows.push(['物流方案', pl ? (pl.plan_no || ('WL-' + f.id)) : '-',
        pl ? '组织方式：' + (pl.org_mode === 'SELF' ? '钢厂自提' : '平台配送') : '待运营平台制定',
        pl ? pl.created_at : '-',
        UI.h('span', { class: 'tag ' + (pl ? 'blue' : 'orange') }, pl ? '已生效' : '待制定')]);
      const aw = aggWaybill(f.waybills);
      if (aw) rows.push(['运单', aw.no, aw.track, aw.createdAt, UI.statusTag('WAYBILL', aw.status)]);
      const active = (f.waybills || []).filter((w) => w.status !== 'CANCELLED');
      const signed = active.filter((w) => w.status === 'SIGNED');
      const qc = (f.qualityChecks || [])[0];
      if (signed.length || qc) {
        rows.push(['交付验收', qc ? qc.check_no : '-',
          '已签收 ' + signed.length + '/' + active.length + ' 单'
            + (qc ? ' · 质检结论 ' + (qc.conclusion || '-') + ' · 到货 ' + UI.fmtQty(qc.arrived_qty) + ' 湿吨' : ''),
          qc ? qc.created_at : (signed.length ? signed[signed.length - 1].created_at : '-'),
          UI.h('span', { class: 'tag ' + (active.length && signed.length === active.length ? 'green' : 'blue') },
            active.length && signed.length === active.length ? '已交付' : '交付中')]);
      }

      fulfillBody.appendChild(UI.h('div', { class: 'card' },
        UI.h('h3', { style: 'margin-top:0' }, '全链信息'),
        UI.table([
          { key: 'stage', label: '环节', render: (r) => UI.h('b', {}, r[0]) },
          { key: 'no', label: '单号', render: (r) => r[1] },
          { key: 'desc', label: '内容', render: (r) => r[2] },
          { key: 'time', label: '时间', render: (r) => (r[3] ? UI.fmtDateTime(r[3]) : '-') },
          { key: 'st', label: '状态', render: (r) => r[4] },
        ], rows, '暂无数据')));
    }
  };
})();
