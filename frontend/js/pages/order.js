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
      if (r.status === 'PENDING_ASSIGN') {
        btns.push(UI.h('button', { class: 'sm primary', onclick: () => assignModal(r, onChanged, carriers) }, '指派承运商'));
      }
      if (r.status === 'ARRIVED') {
        btns.push(UI.h('button', { class: 'sm success', onclick: async () => {
          if (!(await UI.confirmBox('确认签收运单 ' + r.segment_no + '？'))) return;
          await API.post('/waybills/' + r.id + '/sign');
          UI.toast('已签收', 'ok'); onChanged();
        } }, '签收'));
      }
    }
    if (mode === 'CARRIER') {
      if (r.status === 'PENDING_ACCEPT') {
        btns.push(UI.h('button', { class: 'sm success', onclick: async () => {
          if (!(await UI.confirmBox('确认接单？'))) return;
          await API.put('/waybills/' + r.id + '/accept');
          UI.toast('已接单', 'ok'); onChanged();
        } }, '接单'));
      }
      if (r.status === 'PENDING_DEPART') btns.push(UI.h('button', { class: 'sm primary', onclick: () => nodeModal(r, 'DEPART', onChanged) }, '回填发运'));
      if (r.status === 'IN_TRANSIT') btns.push(UI.h('button', { class: 'sm primary', onclick: () => nodeModal(r, 'ARRIVE', onChanged) }, '回填到达'));
    }
    return btns.length ? UI.h('span', { class: 'inline-flex' }, ...btns) : '-';
  }

  function nodeModal(r, node, onChanged) {
    const occur = UI.h('input', { type: 'datetime-local' });
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

  function assignModal(r, onChanged, carriers) {
    const sel = UI.selectField((carriers || []).map((c) => [c.id, c.companyName]), '');
    const m = UI.modal('指派承运商 · ' + r.segment_no, UI.h('div', {}, UI.formRow('承运商', sel, true)), [
      UI.h('button', { class: 'primary', onclick: async () => {
        if (!sel.value) { UI.toast('请选择承运商', 'err'); return; }
        await API.put('/waybills/' + r.id + '/assign', { carrierId: Number(sel.value) });
        m.close(); UI.toast('已指派', 'ok'); onChanged();
      } }, '指 派'),
    ]);
  }

  /* -------- 订单 -------- */
  Pages.order = async function (page, user) {
    const isSteel = (user.roles || []).indexOf('STEEL_BUYER') >= 0;
    const isSupplier = (user.roles || []).indexOf('SUPPLIER') >= 0;
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
        { key: 'quantity', label: '数量', num: true, render: (r) => UI.fmtMoney(r.quantity) },
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
      if (isSupplier && r.status === 'PENDING_CONFIRM') {
        btns.push(UI.h('button', { class: 'sm success', onclick: async () => {
          if (!(await UI.confirmBox('确认接受订单 ' + r.order_no + '？确认后进入待签合同。'))) return;
          await API.put('/orders/' + r.id + '/confirm');
          UI.toast('订单已确认', 'ok'); load();
        } }, '确认订单'));
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
          { key: 'contract_no', label: '合同号' },
          { key: 'version', label: '版本', num: true },
          { key: 'status', label: '状态', render: (r) => UI.statusTag('CONTRACT', r.status) },
          { key: 'buyer_sign_at', label: '需方签署', render: (r) => UI.fmtDateTime(r.buyer_sign_at) },
          { key: 'supplier_sign_at', label: '供方签署', render: (r) => UI.fmtDateTime(r.supplier_sign_at) },
        ], d.contracts || []));
      UI.modal('订单详情', body, [], { wide: true });
    }

    await load();
  };

  /* -------- 合同 -------- */
  Pages.contract = async function (page, user) {
    const isSteel = (user.roles || []).indexOf('STEEL_BUYER') >= 0;
    const isSupplier = (user.roles || []).indexOf('SUPPLIER') >= 0;
    let pageNo = 1;
    const SIZE = 10;
    const listCard = UI.h('div', { class: 'card' });
    const pagerBox = UI.h('div', {});
    page.appendChild(UI.h('div', { class: 'card' },
      UI.h('div', { class: 'toolbar' },
        UI.h('h3', { style: 'margin:0;border:none;padding:0' }, '合同'),
        UI.h('div', { class: 'spacer' }),
        UI.h('span', { class: 'hint' }, '需方签署后供方方可签署；已生效合同不可作废'))));
    page.appendChild(listCard);
    page.appendChild(pagerBox);

    async function load() {
      const d = await API.get('/contracts' + API.qs({ page: pageNo, size: SIZE }));
      listCard.innerHTML = '';
      listCard.appendChild(UI.table([
        { key: 'contractNo', label: '合同号' },
        { key: 'orderNo', label: '订单号' },
        { key: 'version', label: '版本', num: true },
        { key: 'status', label: '状态', render: (r) => UI.statusTag('CONTRACT', r.status) },
        { key: 'buyerSignAt', label: '需方签署', render: (r) => UI.fmtDateTime(r.buyerSignAt) },
        { key: 'supplierSignAt', label: '供方签署', render: (r) => UI.fmtDateTime(r.supplierSignAt) },
        { key: 'voidReason', label: '作废原因' },
        { key: 'createdAt', label: '创建时间', render: (r) => UI.fmtDateTime(r.createdAt) },
        { label: '操作', render: (r) => acts(r) },
      ], d.list, '暂无合同'));
      pagerBox.innerHTML = '';
      UI.pager(pagerBox, pageNo, SIZE, d.total, (p) => { pageNo = p; load(); });
    }

    function acts(r) {
      const btns = [UI.h('button', { class: 'sm', onclick: () => detail(r.id) }, '详情')];
      if (r.fileUrl) btns.push(UI.h('button', { class: 'sm', onclick: () =>
        API.download('/files/' + String(r.fileUrl).split(',')[0], r.contractNo + '-v' + r.version + '.pdf') }, '下载'));
      if (r.status === 'PENDING_BUYER' && isSteel) btns.push(UI.h('button', { class: 'sm primary', onclick: () => signModal(r, 'BUYER', load) }, '需方签署'));
      if (r.status === 'PENDING_SUPPLIER' && isSupplier) btns.push(UI.h('button', { class: 'sm primary', onclick: () => signModal(r, 'SUPPLIER', load) }, '供方签署'));
      if (isSteel && (r.status === 'PENDING_BUYER' || r.status === 'PENDING_SUPPLIER' || r.status === 'PENDING_GENERATE')) {
        btns.push(UI.h('button', { class: 'sm danger', onclick: () => voidModal(r, load) }, '作废'));
      }
      return UI.h('span', { class: 'inline-flex' }, ...btns);
    }

    function signModal(r, role, onDone) {
      const name = UI.input('text', API.currentUser() ? (API.currentUser().realName || '') : '', { placeholder: '签署人姓名' });
      const confirm = UI.h('input', { type: 'checkbox', style: 'width:auto' });
      const file = UI.h('input', { type: 'file', accept: 'image/*,.pdf' });
      const m = UI.modal((role === 'BUYER' ? '需方' : '供方') + '签署 · ' + r.contractNo,
        UI.h('div', {},
          UI.formRow('签署人', name, true),
          UI.h('div', { class: 'form-row' }, UI.h('label', { class: 'req' }, '已核对合同条款'),
            UI.h('label', { class: 'field' }, confirm, ' 我确认已核对条款')),
          UI.formRow('盖章件', file, true, '扫描件或照片')), [
        UI.h('button', { class: 'primary', onclick: async () => {
          if (!name.value.trim()) { UI.toast('请填写签署人', 'err'); return; }
          if (!confirm.checked) { UI.toast('必须勾选"已核对条款"', 'err'); return; }
          if (!file.files || !file.files.length) { UI.toast('请上传盖章件', 'err'); return; }
          const up = await API.upload(file.files[0]);
          await API.post('/contracts/' + r.id + '/sign', {
            signerName: name.value.trim(), confirm: 'true',
            fileId: up.fileId != null ? up.fileId : up.id,
          });
          m.close(); UI.toast('签署成功', 'ok'); onDone();
        } }, '签 署'),
      ]);
    }

    function voidModal(r, onDone) {
      const reason = UI.h('textarea', { rows: 2, style: 'width:100%', placeholder: '作废原因（必填）' });
      const m = UI.modal('作废合同 · ' + r.contractNo, UI.h('div', {}, UI.formRow('作废原因', reason, true)), [
        UI.h('button', { class: 'danger', onclick: async () => {
          if (!reason.value.trim()) { UI.toast('请填写作废原因', 'err'); return; }
          await API.post('/contracts/' + r.id + '/void', { reason: reason.value.trim() });
          m.close(); UI.toast('已作废，可重新生成合同', 'ok'); onDone();
        } }, '确认作废'),
      ]);
    }

    async function detail(cid) {
      const d = await API.get('/contracts/' + cid);
      const c = d.contract || d;
      const body = UI.h('div', {},
        UI.kv([
          ['合同号', c.contract_no], ['版本', 'v' + c.version],
          ['状态', UI.statusTag('CONTRACT', c.status)],
          ['文件哈希', c.file_hash],
          ['需方签署', UI.fmtDateTime(c.buyer_sign_at)], ['供方签署', UI.fmtDateTime(c.supplier_sign_at)],
          ['作废原因', c.void_reason, true],
        ]),
        d.order ? UI.h('div', {},
          UI.h('h3', { style: 'margin-top:14px' }, '关联订单'),
          UI.kv([
            ['订单号', d.order.order_no], ['状态', UI.statusTag('ORDER', d.order.status)],
            ['数量', UI.fmtMoney(d.order.quantity) + ' 吨'], ['单价', UI.fmtMoney(d.order.unit_price)],
            ['金额', UI.fmtMoney(d.order.amount), true],
          ])) : null,
        c.file_url ? UI.h('div', { style: 'margin-top:12px' },
          UI.h('a', { href: 'javascript:;', onclick: () =>
            API.download('/files/' + String(c.file_url).split(',')[0], c.contract_no + '-v' + c.version + '.pdf') }, '下载合同文件')) : null);
      UI.modal('合同详情', body);
    }

    await load();
  };

  /* -------- 物流方案（钢厂） -------- */
  Pages.logistics = async function (page, user) {
    const orders = (await API.get('/orders?size=100&status=PERFORMING')).list || [];
    const carriers = (await API.get('/companies?type=LOGISTICS&size=100')).list || [];
    if (!orders.length) { page.appendChild(UI.h('div', { class: 'card' }, UI.h('div', { class: 'empty' }, '暂无履约中订单'))); return; }
    const orderSel = UI.selectField(orders.map((o) => [o.id, o.order_no + '（' + (o.varietyName || '') + '）']), orders[0].id);
    const body = UI.h('div', {});
    page.appendChild(UI.h('div', { class: 'card' },
      UI.h('div', { class: 'toolbar' },
        UI.h('h3', { style: 'margin:0;border:none;padding:0' }, '物流方案'),
        UI.h('label', { class: 'field' }, '选择订单 ', orderSel))));
    page.appendChild(body);
    orderSel.addEventListener('change', load);
    await load();

    async function load() {
      body.innerHTML = '';
      const oid = orderSel.value;
      const plan = await API.get('/orders/' + oid + '/logistics-plan');
      if (!plan) {
        body.appendChild(UI.h('div', { class: 'card' },
          UI.h('h3', {}, '创建物流方案'),
          UI.h('div', { class: 'inline-flex' },
            UI.h('label', { class: 'field' }, '组织方式 ',
              UI.selectField([['DIRECT', '整批直发'], ['SEGMENT', '分段发运']], 'SEGMENT', { id: 'org-mode' })),
            UI.h('button', { class: 'primary', onclick: async () => {
              const mode = document.getElementById('org-mode').value;
              await API.post('/orders/' + oid + '/logistics-plan', { orgMode: mode });
              UI.toast('方案已创建', 'ok'); load();
            } }, '创建方案'))));
        return;
      }
      body.appendChild(UI.h('div', { class: 'card' },
        UI.h('h3', {}, '方案 ' + (plan.plan_no || plan.id)),
        UI.kv([
          ['组织方式', plan.org_mode === 'DIRECT' ? '整批直发' : '分段发运'],
          ['创建时间', UI.fmtDateTime(plan.created_at)],
        ])));
      const wbCard = UI.h('div', { class: 'card' }, UI.h('h3', {}, '分段运单'));
      body.appendChild(wbCard);
      const wb = await API.get('/waybills?size=100&orderId=' + oid);
      wbCard.appendChild(UI.table(waybillCols('STEEL', load, carriers), wb.list, '暂无运单'));
      body.appendChild(waybillForm(plan.id, oid, carriers, load));
    }

    function waybillForm(pid, oid, carriers, onDone) {
      const segmentNo = UI.input('text', '', { placeholder: '如 SEG-1' });
      const mode = UI.selectField(Object.entries(MODES), 'ROAD');
      const planQty = UI.input('number', '', { placeholder: '计划量（吨）' });
      const depart = UI.input('date', '');
      const arrive = UI.input('date', '');
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

  /* -------- 运单作业（承运商） -------- */
  Pages.waybill = async function (page, user) {
    let status = '';
    let pageNo = 1;
    const SIZE = 10;
    const listCard = UI.h('div', { class: 'card' });
    const pagerBox = UI.h('div', {});
    page.appendChild(UI.h('div', { class: 'card' },
      UI.h('div', { class: 'toolbar' },
        UI.h('h3', { style: 'margin:0;border:none;padding:0' }, '运单作业'),
        UI.h('div', { class: 'spacer' }),
        UI.statusFilter('WAYBILL', (v) => { status = v; pageNo = 1; load(); }))));
    page.appendChild(listCard);
    page.appendChild(pagerBox);

    async function load() {
      const d = await API.get('/waybills' + API.qs({ page: pageNo, size: SIZE, status }));
      listCard.innerHTML = '';
      listCard.appendChild(UI.table(waybillCols('CARRIER', load), d.list, '暂无运单'));
      pagerBox.innerHTML = '';
      UI.pager(pagerBox, pageNo, SIZE, d.total, (p) => { pageNo = p; load(); });
    }
    await load();
  };

  /* -------- 履约跟踪 -------- */
  Pages.track = async function (page, user) {
    const isSteel = (user.roles || []).indexOf('STEEL_BUYER') >= 0;
    const orders = (await API.get('/orders?size=100')).list || [];
    if (!orders.length) { page.appendChild(UI.h('div', { class: 'card' }, UI.h('div', { class: 'empty' }, '暂无订单'))); return; }
    const orderSel = UI.selectField(orders.map((o) => [o.id, o.order_no + '（' + (o.varietyName || '') + '）']), orders[0].id);
    const body = UI.h('div', {});
    page.appendChild(UI.h('div', { class: 'card' },
      UI.h('div', { class: 'toolbar' },
        UI.h('h3', { style: 'margin:0;border:none;padding:0' }, '履约跟踪'),
        UI.h('label', { class: 'field' }, '选择订单 ', orderSel))));
    page.appendChild(body);
    orderSel.addEventListener('change', load);
    await load();

    async function load() {
      body.innerHTML = '';
      const oid = orderSel.value;
      const t = await API.get('/orders/' + oid + '/timeline');
      body.appendChild(UI.h('div', { class: 'card' },
        UI.h('h3', {}, '履约时间轴'),
        UI.timeline(t.list || []),
        isSteel ? UI.h('div', { style: 'margin-top:12px' }, manualNodeForm(oid, load)) : null));
      const wb = await API.get('/waybills?size=100&orderId=' + oid);
      const carriers = isSteel ? ((await API.get('/companies?type=LOGISTICS&size=100')).list || []) : [];
      body.appendChild(UI.h('div', { class: 'card' },
        UI.h('h3', {}, '运单'),
        UI.table(waybillCols('STEEL', load, carriers), wb.list, '暂无运单')));
    }

    function manualNodeForm(oid, onDone) {
      const code = UI.input('text', '', { placeholder: '节点代码（大写，如 LOAD_DONE）' });
      const occur = UI.h('input', { type: 'datetime-local' });
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
