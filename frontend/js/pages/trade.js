/* 询价报价议价（PRD 4.4/FR-04/FR-05/T08-T12）：密封报价、截止揭示比价、多轮议价、定标、流标 */
(function () {
  window.Pages = window.Pages || {};
  const SETTLE = { PREPAY: '预付款', COD: '货到付款', CREDIT: '账期' };

  /* 议价对标面板：基准价 + 他人匿名价 + 近期成交均价 */
  async function contextPanel(iid) {
    const box = UI.h('div', { class: 'card', style: 'margin-bottom:12px' });
    try {
      const c = await API.get('/inquiries/' + iid + '/bargain-context');
      box.appendChild(UI.h('h3', {}, '议价对标'));
      box.appendChild(UI.kv([
        ['平台基准价', c.basePrice ? UI.fmtMoney(c.basePrice.price) + ' 元/吨（' + UI.fmtDate(c.basePrice.priceDate) + '，' + (c.basePrice.priceBasis === 'DRY' ? '干基' : '湿基') + '）' : '无'],
        ['他人匿名报价', c.otherAnonymousPrices && c.otherAnonymousPrices.length ? c.otherAnonymousPrices.join(' / ') : '无'],
        ['近期成交均价', c.recentAvgPrice || '无'],
        ['近期成交笔数', c.recentDealCount != null ? String(c.recentDealCount) : '-'],
      ]));
    } catch (e) { box.appendChild(UI.h('div', { class: 'hint' }, '对标信息不可用')); }
    return box;
  }

  /* 议价轮次表 + 轮次操作 */
  function roundsPanel(quoteId, myRole, onChanged) {
    const box = UI.h('div', { class: 'card', style: 'margin-bottom:12px' });
    box.appendChild(UI.h('h3', {}, '议价轮次'));
    const body = UI.h('div', {}, UI.h('div', { class: 'hint' }, '加载中…'));
    box.appendChild(body);
    API.get('/bargains' + API.qs({ quoteId })).then((d) => {
      body.innerHTML = '';
      const list = d.list || [];
      if (!list.length) { body.appendChild(UI.h('div', { class: 'empty' }, '暂无议价轮次')); return; }
      body.appendChild(UI.table([
        { key: 'roundNo', label: '轮次', num: true },
        { key: 'initiator', label: '发起方', render: (r) => (r.initiator === 'BUYER' ? '需方' : '供方') },
        { key: 'price', label: '价格', num: true, render: (r) => UI.fmtMoney(r.price) },
        { key: 'quantity', label: '数量', num: true, render: (r) => UI.fmtMoney(r.quantity) },
        { key: 'deliveryDate', label: '到货日', render: (r) => UI.fmtDate(r.deliveryDate) },
        { key: 'settleType', label: '结算', render: (r) => SETTLE[r.settleType] || r.settleType || '-' },
        { key: 'extraTerms', label: '附加条款' },
        { key: 'status', label: '状态', render: (r) => UI.statusTag('BARGAIN', r.status) },
        { label: '操作', render: (r) => {
          if (r.status !== 'PENDING' || r.initiator === myRole) return '-';
          return UI.h('span', { class: 'inline-flex' },
            UI.h('button', { class: 'sm success', onclick: async () => {
              if (!(await UI.confirmBox('确认接受该轮还价？其余在途轮次将自动失效。'))) return;
              await API.put('/bargains/' + r.id + '/accept');
              UI.toast('已接受', 'ok'); onChanged();
            } }, '接受'),
            UI.h('button', { class: 'sm danger', onclick: async () => {
              if (!(await UI.confirmBox('确认拒绝该轮还价？'))) return;
              await API.put('/bargains/' + r.id + '/reject');
              UI.toast('已拒绝', 'ok'); onChanged();
            } }, '拒绝'));
        } },
      ], list));
    }).catch(() => { body.innerHTML = ''; body.appendChild(UI.h('div', { class: 'hint' }, '轮次加载失败')); });
    return box;
  }

  /* 发起新一轮议价 */
  function newRoundForm(quoteId, defaultPrice, onChanged) {
    const price = UI.input('number', defaultPrice, { placeholder: '还价（元/吨）' });
    const qty = UI.input('number', '', { placeholder: '数量（选填）' });
    const ddate = UI.input('date', '', { placeholder: '到货日（选填）' });
    const settle = UI.selectField([['', '结算不变']].concat(Object.entries(SETTLE)), '');
    const extra = UI.h('textarea', { rows: 2, style: 'width:100%', placeholder: '附加条款（选填）' });
    return UI.h('div', { class: 'card' },
      UI.h('h3', {}, '发起新一轮还价'),
      UI.h('div', { class: 'inline-flex', style: 'flex-wrap:wrap' },
        UI.h('label', { class: 'field' }, '价格 ', price),
        UI.h('label', { class: 'field' }, '数量 ', qty),
        UI.h('label', { class: 'field' }, '到货日 ', ddate),
        UI.h('label', { class: 'field' }, '结算 ', settle),
        UI.h('button', { class: 'primary', onclick: async () => {
          const body = { quoteId: Number(quoteId) };
          if (price.value !== '') body.price = price.value;
          if (qty.value !== '') body.quantity = qty.value;
          if (ddate.value) body.deliveryDate = ddate.value;
          if (settle.value) body.settleType = settle.value;
          if (extra.value.trim()) body.extraTerms = extra.value.trim();
          try {
            await API.post('/bargains', body);
            UI.toast('还价已发出', 'ok'); onChanged();
          } catch (e) { /* toast 已提示 */ }
        } }, '发出还价')),
      UI.h('div', { style: 'margin-top:8px' }, extra));
  }

  /* 议价弹窗（供比价表行内调用） */
  function bargainModal(iid, quoteId, defaultPrice, onDone) {
    const body = UI.h('div', {});
    const m = UI.modal('议价（询价 ' + iid + '）', body, [], { wide: true });
    async function refresh() {
      body.innerHTML = '';
      body.appendChild(await contextPanel(iid));
      body.appendChild(roundsPanel(quoteId, 'BUYER', refresh));
      body.appendChild(newRoundForm(quoteId, defaultPrice, refresh));
    }
    m.mask.addEventListener('click', () => { if (onDone) onDone(); });
    refresh();
  }

  /* 比价快照渲染（定标/流标入口） */
  function renderSnapshot(snap, iid, onDone) {
    const body = UI.h('div', {},
      UI.kv([
        ['询价编号', snap.inquiryNo],
        ['最少响应', snap.minResponse != null ? snap.minResponse + ' 家' : '-'],
        ['响应情况', snap.responseShortage ? UI.h('span', { class: 'tag red' }, '响应不足') : UI.h('span', { class: 'tag green' }, '满足')],
        ['揭示时间', UI.fmtDateTime(snap.revealedAt)],
      ]),
      UI.h('h3', { style: 'margin-top:12px' }, '比价表（按价格升序固化）'),
      UI.table([
        { key: 'seq', label: '序号', num: true },
        { key: 'unitPrice', label: '单价', num: true, render: (r) => UI.fmtMoney(r.unitPrice) },
        { key: 'quantity', label: '数量', num: true, render: (r) => UI.fmtMoney(r.quantity) },
        { key: 'responseRate', label: '响应率' },
        { key: 'deliveryDate', label: '到货日', render: (r) => UI.fmtDate(r.deliveryDate) },
        { key: 'payTerms', label: '付款条款' },
        { key: 'validUntil', label: '有效期至', render: (r) => UI.fmtDate(r.validUntil) },
        { label: '操作', render: (r) => UI.h('span', { class: 'inline-flex' },
          UI.h('button', { class: 'sm', onclick: () => bargainModal(iid, r.quoteId, r.unitPrice, onDone) }, '议价'),
          UI.h('button', { class: 'sm success', onclick: async () => {
            if (!(await UI.confirmBox('确认按该报价定标？其余报价将置为未中标。'))) return;
            const res = await API.post('/inquiries/' + iid + '/award', { quoteId: r.quoteId });
            UI.toast('定标成功，订单号 ' + (res.orderId || ''), 'ok');
            if (onDone) onDone();
          } }, '定标')) },
      ], snap.rows, '暂无报价行'));
    return body;
  }

  function failIt(iid, onDone) {
    const reason = UI.h('textarea', { rows: 2, style: 'width:100%', placeholder: '流标原因（必填）' });
    const m = UI.modal('流标（询价 ' + iid + '）', UI.h('div', {}, UI.formRow('流标原因', reason, true)), [
      UI.h('button', { class: 'danger', onclick: async () => {
        if (!reason.value.trim()) { UI.toast('请填写流标原因', 'err'); return; }
        await API.post('/inquiries/' + iid + '/fail', { reason: reason.value.trim() });
        m.close(); UI.toast('已流标，可询量已归还', 'ok'); if (onDone) onDone();
      } }, '确认流标'),
    ]);
  }

  /* -------- 钢厂：询价管理 -------- */
  Pages.inquiry = async function (page, user) {
    const isSteel = (user.roles || []).indexOf('STEEL_BUYER') >= 0;
    if (isSteel) return steelView(page);
    return supplierView(page, user);
  };

  async function steelView(page) {
    let status = '';
    let pageNo = 1;
    const SIZE = 10;
    const listCard = UI.h('div', { class: 'card' });
    const pagerBox = UI.h('div', {});
    page.appendChild(UI.h('div', { class: 'card' },
      UI.h('div', { class: 'toolbar' },
        UI.h('h3', { style: 'margin:0;border:none;padding:0' }, '询价单'),
        UI.h('div', { class: 'spacer' }),
        UI.statusFilter('INQUIRY', (v) => { status = v; pageNo = 1; load(); }),
        UI.h('button', { class: 'primary', onclick: () => newInquiry(() => load()) }, '新建询价'))));
    page.appendChild(listCard);
    page.appendChild(pagerBox);

    async function load() {
      const d = await API.get('/inquiries' + API.qs({ page: pageNo, size: SIZE, status }));
      listCard.innerHTML = '';
      listCard.appendChild(UI.table([
        { key: 'inquiry_no', label: '询价编号' },
        { key: 'varietyName', label: '品种' },
        { key: 'quantity', label: '数量(吨)', num: true, render: (r) => UI.fmtMoney(r.quantity) },
        { key: 'deadline', label: '报价截止', render: (r) => UI.fmtDateTime(r.deadline) },
        { key: 'status', label: '状态', render: (r) => UI.statusTag('INQUIRY', r.status) },
        { label: '邀请/响应', num: true, render: (r) => (r.inviteCount != null ? r.inviteCount : '-') + ' / ' + (r.quoteCount != null ? r.quoteCount : '-') },
        { key: 'created_at', label: '创建时间', render: (r) => UI.fmtDateTime(r.created_at) },
        { label: '操作', render: (r) => UI.h('button', { class: 'sm', onclick: () => detail(r.id, load) }, '详情') },
      ], d.list, '暂无询价单'));
      pagerBox.innerHTML = '';
      UI.pager(pagerBox, pageNo, SIZE, d.total, (p) => { pageNo = p; load(); });
    }

    async function detail(iid, onDone) {
      const d = await API.get('/inquiries/' + iid);
      const body = UI.h('div', {},
        UI.kv([
          ['询价编号', d.inquiry_no], ['状态', UI.statusTag('INQUIRY', d.status)],
          ['品种', d.varietyName], ['数量', UI.fmtMoney(d.quantity) + ' 吨'],
          ['报价截止', UI.fmtDateTime(d.deadline)],
          ['期望到货', UI.fmtDate(d.expect_arrive_date)],
          ['最少响应', d.min_response != null ? d.min_response + ' 家' : '-'],
          ['交货方式', d.delivery_type || '-'],
          ['交货地点', d.delivery_place || '-'],
          ['结算方式', SETTLE[d.settle_type] || d.settle_type || '-'],
          ['说明', d.inquiry_desc, true],
        ]),
        UI.h('h3', { style: 'margin-top:14px' }, '邀请供应商'),
        UI.table([
          { key: 'supplierName', label: '供应商' },
          { key: 'status', label: '邀请状态' },
          { key: 'quoteStatus', label: '报价状态', render: (r) => r.quoteStatus ? UI.statusTag('QUOTE', r.quoteStatus) : '-' },
        ], d.invites || []));
      const foot = [];
      if (d.status === 'DRAFT') {
        foot.push(UI.h('button', { class: 'primary', onclick: async () => {
          await API.post('/inquiries/' + iid + '/send');
          UI.toast('询价已发出', 'ok'); m.close(); onDone();
        } }, '发出询价'));
      }
      if (d.status === 'SENT' || d.status === 'QUOTING') {
        foot.push(UI.h('button', { class: 'primary', onclick: async () => {
          const snap = await API.post('/inquiries/' + iid + '/reveal');
          m.close();
          const m2 = UI.modal('比价快照', renderSnapshot(snap, iid, onDone), [], { wide: true });
          m2.mask.addEventListener('click', onDone);
        } }, '截止揭示'));
      }
      if (d.status === 'CLOSED' || d.status === 'BARGAINING') {
        foot.push(UI.h('button', { class: 'primary', onclick: async () => {
          const snap = await API.get('/inquiries/' + iid + '/quotes/reveal');
          m.close();
          const m2 = UI.modal('比价快照', renderSnapshot(snap, iid, onDone), [], { wide: true });
          m2.mask.addEventListener('click', onDone);
        } }, '查看比价'));
      }
      if (['DRAFT', 'SENT', 'QUOTING', 'CLOSED', 'BARGAINING'].indexOf(d.status) >= 0) {
        foot.push(UI.h('button', { class: 'danger', onclick: () => { failIt(iid, () => { m.close(); onDone(); }); } }, '流标'));
      }
      const m = UI.modal('询价详情', body, foot, { wide: true });
    }

    async function newInquiry(onDone) {
      const demands = (await API.get('/demands?size=100')).list
        .filter((r) => r.status === 'SUBMITTED' || r.status === 'INQUIRING');
      if (!demands.length) { UI.toast('没有可发起询价的需求单（需已提交且未关闭）', 'err'); return; }
      const demandSel = UI.selectField(demands.map((r) => [r.id, r.demand_no + ' ' + r.demand_name]), demands[0].id);
      const itemSel = UI.h('select', {});
      const qty = UI.input('number', '', { placeholder: '询价数量' });
      const arrive = UI.input('date', '', { placeholder: '期望到货日' });
      const deadline = UI.h('input', { type: 'datetime-local', placeholder: '报价截止时间' });
      const minResp = UI.input('number', '2', { placeholder: '最少响应家数（默认 2）' });
      const dType = UI.selectField([['', '跟随需求'], ['PORT_FOB', '港口FOB'], ['PORT_TRUCK', '港口汽运'], ['PLANT', '厂内自提']], '');
      const place = UI.input('text', '', { placeholder: '交货地点（选填）' });
      const settle = UI.selectField([['', '跟随需求']].concat(Object.entries(SETTLE)), '');
      const desc = UI.h('textarea', { rows: 2, style: 'width:100%', placeholder: '选填，询价补充说明' });
      const supBox = UI.h('div', { class: 'inline-flex', style: 'flex-wrap:wrap' });

      async function loadItems() {
        const d = await API.get('/demands/' + demandSel.value);
        const its = (d.items || []).filter((it) => Number(it.remainQty) > 0);
        itemSel.innerHTML = '';
        if (!its.length) { itemSel.appendChild(UI.h('option', { value: '' }, '该需求无剩余可询明细')); return; }
        its.forEach((it) => itemSel.appendChild(UI.h('option', {
          value: it.id, 'data-remain': it.remainQty,
        }, (it.varietyName || '-') + ' ' + (it.grade || '') + '（剩余可询 ' + it.remainQty + '）')));
      }
      demandSel.addEventListener('change', loadItems);
      await loadItems();

      const suppliers = (await API.get('/companies?type=SUPPLIER&size=100')).list || [];
      suppliers.forEach((s) => supBox.appendChild(UI.h('label', { class: 'field' },
        UI.h('input', { type: 'checkbox', value: s.id, style: 'width:auto' }), s.companyName)));

      // BUG-07 修复：弹窗内持久错误提示区。此前校验/保存失败仅提示约 3 秒即
      // 消失的 toast，弹窗保持打开且不显示失败原因，表现为"静默失败"。
      const errBox = UI.h('div', { class: 'hint', style: 'color:#c0392b;font-weight:600' });
      const m = UI.modal('新建询价', UI.h('form', { onsubmit: (e) => e.preventDefault() },
        UI.h('div', { class: 'form-grid' },
          UI.formRow('来源需求', demandSel, true),
          UI.formRow('需求明细', itemSel, true),
          UI.formRow('询价数量', qty, true, '不超过明细剩余可询量'),
          UI.formRow('期望到货日', arrive, true),
          UI.formRow('报价截止', deadline, true, '至少为当前时间 +2 小时，且不晚于到货日前 7 天'),
          UI.formRow('最少响应家数', minResp),
          UI.formRow('交货方式', dType),
          UI.formRow('交货地点', place),
          UI.formRow('结算方式', settle),
          UI.h('div', { class: 'form-row full' }, UI.h('label', {}, '询价说明'), desc),
          UI.h('div', { class: 'form-row full' }, UI.h('label', { class: 'req' }, '邀请供应商'), supBox)),
        UI.h('div', { class: 'hint' }, '保存后为草稿，可在详情中发出'),
        errBox), [
        UI.h('button', { class: 'primary', onclick: async () => {
          const fail = (msg) => { errBox.textContent = msg; if (errBox.scrollIntoView) errBox.scrollIntoView({ block: 'nearest' }); };
          const inviteIds = Array.from(supBox.querySelectorAll('input:checked')).map((i) => Number(i.value));
          if (!itemSel.value) { fail('请选择需求明细'); return; }
          if (!inviteIds.length) { fail('至少邀请一家供应商'); return; }
          const body = {
            demandId: Number(demandSel.value),
            demandItemId: Number(itemSel.value),
            quantity: Number(qty.value),
            arriveDate: arrive.value,
            deadline: deadline.value ? deadline.value.replace('T', ' ') + ':00' : '',
            inviteSupplierIds: inviteIds,
            minResponse: minResp.value ? Number(minResp.value) : 2,
          };
          if (!body.quantity || body.quantity <= 0) { fail('请填写询价数量'); return; }
          if (!body.arriveDate || !body.deadline) { fail('期望到货日与报价截止为必填'); return; }
          // 与服务端同规则的本地时间预校验（datetime-local 按浏览器本地时区解析）
          const dl = new Date(body.deadline.replace(' ', 'T'));
          if (dl.getTime() < Date.now() + 2 * 3600 * 1000) { fail('报价截止时间必须至少为当前时间 +2 小时'); return; }
          const arrDay = new Date(arrive.value + 'T00:00:00').getTime();
          if (new Date(dl.getFullYear(), dl.getMonth(), dl.getDate()).getTime() > arrDay - 7 * 86400000) {
            fail('报价截止时间不能晚于到货日期前 7 天'); return;
          }
          if (dType.value) body.deliveryType = dType.value;
          if (place.value.trim()) body.deliveryPlace = place.value.trim();
          if (settle.value) body.settleType = settle.value;
          if (desc.value.trim()) body.remark = desc.value.trim();
          try {
            await API.post('/inquiries', body);
            m.close(); UI.toast('询价草稿已创建', 'ok'); onDone();
          } catch (e) { fail('保存失败：' + (e.message || '请检查填写内容')); }
        } }, '保存草稿'),
      ], { wide: true });
    }

    await load();
  }

  /* -------- 供应商：询价列表 + 报价/改价 -------- */
  async function supplierView(page, user) {
    let pageNo = 1;
    const SIZE = 10;
    const listCard = UI.h('div', { class: 'card' });
    const pagerBox = UI.h('div', {});
    page.appendChild(UI.h('div', { class: 'card' },
      UI.h('div', { class: 'toolbar' },
        UI.h('h3', { style: 'margin:0;border:none;padding:0' }, '收到的询价'),
        UI.h('div', { class: 'spacer' }),
        UI.h('span', { class: 'hint' }, '密封报价：截止前任何人（含平台）都看不到他人价格'))));
    page.appendChild(listCard);
    page.appendChild(pagerBox);

    async function load() {
      const d = await API.get('/inquiries' + API.qs({ page: pageNo, size: SIZE }));
      listCard.innerHTML = '';
      listCard.appendChild(UI.table([
        { key: 'inquiryNo', label: '询价编号' },
        { key: 'varietyName', label: '品种' },
        { key: 'grade', label: '品位(%)' },
        { key: 'quantity', label: '数量(吨)', num: true, render: (r) => UI.fmtMoney(r.quantity) },
        { key: 'deliveryPlace', label: '交货地点' },
        { key: 'expectArriveDate', label: '期望到货', render: (r) => UI.fmtDate(r.expectArriveDate) },
        { key: 'settleType', label: '结算', render: (r) => SETTLE[r.settleType] || r.settleType || '-' },
        { key: 'deadline', label: '报价截止', render: (r) => UI.fmtDateTime(r.deadline) },
        { label: '我的报价', render: (r) => r.myQuoteStatus ? UI.statusTag('QUOTE', r.myQuoteStatus) : UI.h('span', { class: 'tag' }, '未报价') },
        { key: 'status', label: '询价状态', render: (r) => UI.statusTag('INQUIRY', r.status) },
        { label: '操作', render: (r) => acts(r) },
      ], d.list, '暂无询价'));
      pagerBox.innerHTML = '';
      UI.pager(pagerBox, pageNo, SIZE, d.total, (p) => { pageNo = p; load(); });
    }

    function acts(r) {
      const btns = [UI.h('button', { class: 'sm', onclick: () => sDetail(r.id) }, '详情')];
      if (!r.myQuoteId && (r.status === 'SENT' || r.status === 'QUOTING')) {
        btns.push(UI.h('button', { class: 'sm primary', onclick: () => quoteForm(r, null, load) }, '报价'));
      }
      if (r.myQuoteId && r.myQuoteStatus === 'SUBMITTED' && (r.status === 'SENT' || r.status === 'QUOTING')) {
        btns.push(UI.h('button', { class: 'sm', onclick: () => quoteForm(r, r.myQuoteId, load) }, '修改报价'));
      }
      return UI.h('span', { class: 'inline-flex' }, ...btns);
    }

    async function sDetail(iid) {
      const d = await API.get('/inquiries/' + iid);
      const body = UI.h('div', {},
        UI.kv([
          ['询价编号', d.inquiry_no], ['状态', UI.statusTag('INQUIRY', d.status)],
          ['品种', d.varietyName], ['数量', UI.fmtMoney(d.quantity) + ' 吨'],
          ['报价截止', UI.fmtDateTime(d.deadline)],
          ['期望到货', UI.fmtDate(d.expect_arrive_date)],
          ['交货地点', d.delivery_place || '-'],
          ['结算方式', SETTLE[d.settle_type] || d.settle_type || '-'],
          ['说明', d.inquiry_desc, true],
        ]),
        UI.h('h3', { style: 'margin-top:14px' }, '我的报价'),
        d.myQuote ? UI.table([
          { key: 'price', label: '单价', num: true, render: (r) => UI.fmtMoney(r.price) },
          { key: 'quantity', label: '数量', num: true, render: (r) => UI.fmtMoney(r.quantity) },
          { key: 'delivery_date', label: '到货日', render: (r) => UI.fmtDate(r.delivery_date) },
          { key: 'delivery_place', label: '交货地' },
          { key: 'pay_terms', label: '付款条款' },
          { key: 'quality_commit', label: '质量承诺' },
          { key: 'valid_until', label: '有效期至', render: (r) => UI.fmtDate(r.valid_until) },
          { key: 'version', label: '版本', num: true },
          { key: 'status', label: '状态', render: (r) => UI.statusTag('QUOTE', r.status) },
        ], [d.myQuote]) : UI.h('div', { class: 'empty' }, '尚未报价'));
      UI.modal('询价详情', body);
    }

    async function quoteForm(r, quoteId, onDone) {
      let q = null;
      if (quoteId) q = (await API.get('/quotes/' + quoteId));
      const price = UI.input('number', q ? q.price : '', { placeholder: '单价（元/吨）' });
      const qty = UI.input('number', q ? q.quantity : r.quantity, { placeholder: '数量' });
      const ddate = UI.input('date', q ? UI.fmtDate(q.delivery_date) : '', { placeholder: '到货日' });
      const place = UI.input('text', q ? q.delivery_place : '', { placeholder: '交货地（选填）' });
      const pay = UI.input('text', q ? q.pay_terms : '', { placeholder: '付款条款（选填）' });
      const quality = UI.h('textarea', { rows: 2, style: 'width:100%', placeholder: '质量承诺（选填）' });
      if (q) quality.value = q.quality_commit || '';
      const valid = UI.input('date', q ? UI.fmtDate(q.valid_until) : '', { placeholder: '报价有效期截止日' });
      const remark = UI.h('textarea', { rows: 2, style: 'width:100%', placeholder: '备注（数量低于询价量 80% 必填）' });
      if (q) remark.value = q.remark || '';
      const m = UI.modal(quoteId ? '修改报价（将留痕新版本）' : '密封报价', UI.h('form', { onsubmit: (e) => e.preventDefault() },
        UI.h('div', { class: 'form-grid' },
          UI.formRow('单价', price, true),
          UI.formRow('数量', qty, true),
          UI.formRow('到货日', ddate, true),
          UI.formRow('交货地', place),
          UI.formRow('付款条款', pay),
          UI.formRow('有效期至', valid),
          UI.h('div', { class: 'form-row full' }, UI.h('label', {}, '质量承诺'), quality),
          UI.h('div', { class: 'form-row full' }, UI.h('label', {}, '备注'), remark)),
        UI.h('div', { class: 'hint' }, '截止前可修改（新版本留痕）；截止后不可再报')), [
        UI.h('button', { class: 'primary', onclick: async () => {
          const body = {
            price: price.value, quantity: qty.value, deliveryDate: ddate.value,
          };
          if (!body.price || !body.quantity || !body.deliveryDate) { UI.toast('单价、数量、到货日为必填', 'err'); return; }
          if (place.value.trim()) body.deliveryPlace = place.value.trim();
          if (pay.value.trim()) body.paymentTerms = pay.value.trim();
          if (quality.value.trim()) body.qualityTerms = quality.value.trim();
          if (valid.value) body.validUntil = valid.value;
          if (remark.value.trim()) body.remark = remark.value.trim();
          try {
            if (quoteId) { await API.put('/quotes/' + quoteId, body); UI.toast('报价已更新', 'ok'); }
            else { await API.post('/inquiries/' + r.id + '/quotes', body); UI.toast('报价已提交（密封）', 'ok'); }
            m.close(); onDone();
          } catch (e) { /* toast 已提示 */ }
        } }, quoteId ? '更新报价' : '提交报价'),
      ], { wide: true });
    }

    await load();
  }

  /* -------- 议价工作台 -------- */
  Pages.bargain = async function (page, user) {
    const isSteel = (user.roles || []).indexOf('STEEL_BUYER') >= 0;
    if (isSteel) {
      page.appendChild(UI.h('div', { class: 'card' },
        UI.h('h3', { style: 'margin:0;border:none;padding:0' }, '议价中的询价'),
        UI.h('div', { class: 'hint' }, '在比价快照中选择报价行发起/继续议价')));
      const box = UI.h('div', { class: 'card' });
      page.appendChild(box);
      const d = await API.get('/inquiries?size=50&status=BARGAINING');
      box.appendChild(UI.table([
        { key: 'inquiry_no', label: '询价编号' },
        { key: 'varietyName', label: '品种' },
        { key: 'quantity', label: '数量', num: true, render: (r) => UI.fmtMoney(r.quantity) },
        { key: 'status', label: '状态', render: (r) => UI.statusTag('INQUIRY', r.status) },
        { label: '操作', render: (r) => UI.h('button', { class: 'sm primary', onclick: async () => {
          const snap = await API.get('/inquiries/' + r.id + '/quotes/reveal');
          const m = UI.modal('比价快照（询价 ' + r.inquiry_no + '）', renderSnapshot(snap, r.id, () => { m.close(); App.route(); }), [], { wide: true });
        } }, '比价/议价') },
      ], d.list, '暂无议价中询价'));
      return;
    }
    /* 供应商：已被揭示且可议价的报价 */
    page.appendChild(UI.h('div', { class: 'card' },
      UI.h('h3', { style: 'margin:0;border:none;padding:0' }, '我的议价'),
      UI.h('div', { class: 'hint' }, '仅显示已揭示/议价中/中标的报价')));
    const box = UI.h('div', {});
    page.appendChild(box);
    const d = await API.get('/inquiries?size=100');
    const rows = (d.list || []).filter((r) => r.myQuoteId &&
      ['REVEALED', 'BARGAINING', 'WIN'].indexOf(r.myQuoteStatus) >= 0);
    if (!rows.length) { box.appendChild(UI.h('div', { class: 'empty' }, '暂无可议价的报价')); return; }
    for (const r of rows) {
      const card = UI.h('div', { class: 'card' });
      card.appendChild(UI.h('h3', {}, r.inquiryNo + ' · ' + r.varietyName + ' ' + (r.grade || '') +
        '（' + UI.fmtMoney(r.quantity) + ' 吨）'));
      card.appendChild(UI.h('div', { class: 'inline-flex', style: 'margin-bottom:8px' },
        UI.h('span', {}, '询价状态 '), UI.statusTag('INQUIRY', r.status),
        UI.h('span', { style: 'margin-left:12px' }, '我的报价 '), UI.statusTag('QUOTE', r.myQuoteStatus)));
      card.appendChild(await contextPanel(r.id));
      card.appendChild(roundsPanel(r.myQuoteId, 'SUPPLIER', () => App.route()));
      card.appendChild(newRoundForm(r.myQuoteId, '', () => App.route()));
      box.appendChild(card);
    }
  };
})();
