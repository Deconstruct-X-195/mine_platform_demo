/* 询价报价议价（PRD 4.4/FR-04/FR-05/T08-T12）：密封报价、截止揭示比价、多轮议价、定标、流标 */
(function () {
  window.Pages = window.Pages || {};
  const SETTLE = { PREPAY: '预付款', COD: '货到付款', CREDIT: '账期' };
  const DELIVERY = { PORT_FOB: '港口离岸', PORT_TRUCK: '港口汽运', PLANT: '厂内自提', STATION_SELF: '到站自提' };
  const INVITE_STATUS = { INVITED: '已邀请', QUOTED: '已报价', DECLINED: '已婉拒', EXPIRED: '已失效' };

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

  /* 比价快照渲染（议价/定标入口）。snap.shareQty 存在 = 归集拆分推送（钢厂视角，仅看报价不可议价/定标）
     after：钢厂反馈（确认/不认可）提交成功后的回调（用于关闭弹窗回到列表）
     inqStatus：询价当前状态——AWARDED/FAILED 时隐藏议价与定标操作（后端同样拦截） */
  function renderSnapshot(snap, iid, onDone, after, inqStatus) {
    const split = !!snap.shareQty;
    const noBids = inqStatus === 'AWARDED' || inqStatus === 'FAILED';
    const body = UI.h('div', {},
      UI.kv([
        ['询价编号', snap.inquiryNo],
        ['响应情况', snap.responseShortage ? UI.h('span', { class: 'tag red' }, '响应不足') : UI.h('span', { class: 'tag green' }, '满足')],
        ['揭示时间', UI.fmtDateTime(snap.revealedAt)],
      ].concat(split ? [['本钢厂份额', UI.fmtMoney(snap.shareQty) + ' 吨']] : [])),
      UI.h('h3', { style: 'margin-top:12px' }, split ? '比价表（已按贵司需求份额拆分推送）' : '比价表（按价格升序固化）'),
      UI.table([
        { key: 'seq', label: '序号', num: true },
        { key: 'unitPrice', label: '单价', num: true, render: (r) => UI.fmtMoney(r.unitPrice) },
        { label: '运价', num: true, render: (r) => r.freightPrice != null ? UI.fmtMoney(r.freightPrice) : '-' },
        { key: 'quantity', label: '数量', num: true, render: (r) => UI.fmtMoney(r.quantity) },
        { label: '含税', render: (r) => ({ INC_TAX: '含税', EX_TAX: '不含税' }[r.taxType] || '-') },
        { key: 'deliveryDate', label: '到货日', render: (r) => UI.fmtDate(r.deliveryDate) },
        { key: 'payTerms', label: '付款条款' },
        { key: 'validUntil', label: '有效期至', render: (r) => UI.fmtDate(r.validUntil) },
      ].concat(split ? [] : noBids ? [] : [{ label: '操作', render: (r) => UI.h('span', { class: 'inline-flex' },
          UI.h('button', { class: 'sm', onclick: () => bargainModal(iid, r.quoteId, r.unitPrice, onDone) }, '议价'),
          UI.h('button', { class: 'sm success', onclick: async () => {
            if (!(await UI.confirmBox('确认按该报价定标？定标即锁货锁价：生成正式订单（供应商 48 小时内确认），其余报价置为未中标，未决议价轮次自动失效。'))) return;
            const res = await API.post('/inquiries/' + iid + '/award', { quoteId: r.quoteId });
            UI.toast('定标成功，订单已生成，供应商 48 小时内确认', 'ok');
            if (onDone) onDone();
          } }, '定标')) }]),
      snap.rows, '暂无报价行'));
    // 拆分推送视角：钢厂对整体比价结果表态（结果推送运营端）；已定标/已反馈后不再重复表态
    if (split && !noBids && inqStatus !== 'FEEDBACK') {
      body.appendChild(UI.h('div', { style: 'margin-top:14px;display:flex;gap:8px;justify-content:flex-end' },
        UI.h('button', { class: 'primary', onclick: async () => {
          if (!(await UI.confirmBox('确认认可该比价结果？全部钢厂认可后将自动锁货锁价生成采购订单。'))) return;
          const res = await API.post('/inquiries/' + iid + '/feedback', { decision: 'ACCEPTED' });
          UI.toast(res && res.autoAward
            ? '全员认可，已自动锁货锁价生成订单，请到「订单」页提交提货计划'
            : '已反馈运营平台：认可比价结果（待全部钢厂认可后自动成单）', 'ok');
          if (after) after();
          if (onDone) onDone();
        } }, '确认报价'),
        UI.h('button', { class: 'danger', onclick: () => {
          const ta = UI.h('textarea', { rows: 3, placeholder: '请填写不认可原因（必填）', style: 'width:100%' });
          UI.modal('不认可报价', UI.h('div', {},
            UI.h('div', { class: 'hint' }, '提交后原因将推送运营平台，由平台决定是否重新发起询价'), ta), [
            UI.h('button', { class: 'primary', onclick: async () => {
              const reason = (ta.value || '').trim();
              if (!reason) { UI.toast('请填写不认可原因', 'err'); return; }
              await API.post('/inquiries/' + iid + '/feedback', { decision: 'REJECTED', reason });
              UI.toast('已反馈运营平台：不认可该报价', 'ok');
              if (after) after();
              if (onDone) onDone();
            } }, '提交反馈'),
          ]);
        } }, '不认可')));
    }
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
        UI.h('span', { class: 'hint' }, '询价由运营平台归集需求后统一发起，供应商报价与反馈在此查看'),
        UI.statusFilter('INQUIRY', (v) => { status = v; pageNo = 1; load(); }))));
    page.appendChild(listCard);
    page.appendChild(pagerBox);

    async function load() {
      const d = await API.get('/inquiries' + API.qs({ page: pageNo, size: SIZE, status }));
      listCard.innerHTML = '';
      listCard.appendChild(UI.table([
        { label: '询价编号', render: (r) => UI.h('span', {}, r.inquiry_no,
            r.agg_id ? UI.h('span', { class: 'tag', style: 'margin-left:6px' }, '归集') : null) },
        { key: 'varietyName', label: '品种' },
        { key: 'quantity', label: '数量(吨)', num: true, render: (r) => UI.fmtMoney(r.quantity) },
        { key: 'deadline', label: '报价截止', render: (r) => UI.fmtDateTime(r.deadline) },
        { key: 'status', label: '状态', render: (r) => UI.statusTag('INQUIRY', r.status) },
        { key: 'created_at', label: '创建时间', render: (r) => UI.fmtDateTime(r.created_at) },
        { label: '操作', render: (r) => UI.h('button', { class: 'sm', onclick: () => detail(r.id, load) }, '详情') },
      ], d.list, '暂无询价单'));
      pagerBox.innerHTML = '';
      UI.pager(pagerBox, pageNo, SIZE, d.total, (p) => { pageNo = p; load(); });
    }

    async function detail(iid, onDone) {
      const d = await API.get('/inquiries/' + iid);
      const isAgg = !!d.aggView; // 归集询价：钢厂只看自己的份额与报价，不显示汇集信息
      const showQty = isAgg && d.shareQty != null ? d.shareQty : d.quantity;
      const body = UI.h('div', {},
        UI.kv([
          ['询价编号', UI.h('span', {}, d.inquiry_no,
              isAgg ? UI.h('span', { class: 'tag', style: 'margin-left:6px' }, '归集') : null)],
          ['状态', UI.statusTag('INQUIRY', d.status)],
          ['品种', d.varietyName],
          ['数量', UI.fmtMoney(showQty) + ' 吨' + (isAgg ? '（本钢厂份额）' : '')],
          ['报价截止', UI.fmtDateTime(d.deadline)],
          ['期望到货', UI.fmtDate(d.expect_arrive_date)],
          ['交货方式', DELIVERY[d.delivery_type] || d.delivery_type || '-'],
          ['交货地点', d.delivery_place || '-'],
          ['结算方式', SETTLE[d.settle_type] || d.settle_type || '-'],
          ['说明', d.inquiry_desc, true],
        ]),
        isAgg ? UI.h('div', {},
          UI.h('h3', { style: 'margin-top:14px' }, '报价供应商'),
          UI.table([
            { key: 'supplierName', label: '供应商' },
            { key: 'quoteStatus', label: '报价状态', render: (r) => r.quoteStatus ? UI.statusTag('QUOTE', r.quoteStatus) : '-' },
            { key: 'quotedAt', label: '报价时间', render: (r) => UI.fmtDateTime(r.quotedAt) },
          ], d.quoteSuppliers || [], '暂无供应商报价')) : UI.h('div', {},
          UI.h('h3', { style: 'margin-top:14px' }, '邀请供应商'),
          UI.table([
            { key: 'supplierName', label: '供应商' },
            { key: 'status', label: '邀请状态', render: (r) => INVITE_STATUS[r.status] || r.status || '-' },
            { key: 'quoteStatus', label: '报价状态', render: (r) => r.quoteStatus ? UI.statusTag('QUOTE', r.quoteStatus) : '-' },
          ], d.invites || [])));
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
          let m2;
          m2 = UI.modal('比价快照', renderSnapshot(snap, iid, onDone, () => { m2.close(); onDone(); }, d.status), [], { wide: true });
          m2.mask.addEventListener('click', onDone);
        } }, '截止揭示'));
      }
      if (d.status === 'CLOSED' || d.status === 'BARGAINING') {
        foot.push(UI.h('button', { class: 'primary', onclick: async () => {
          const snap = await API.get('/inquiries/' + iid + '/quotes/reveal');
          m.close();
          let m2;
          m2 = UI.modal('比价快照', renderSnapshot(snap, iid, onDone, () => { m2.close(); onDone(); }, d.status), [], { wide: true });
          m2.mask.addEventListener('click', onDone);
        } }, '查看比价'));
      }
      if (!isAgg && ['DRAFT', 'SENT', 'QUOTING', 'CLOSED', 'BARGAINING'].indexOf(d.status) >= 0) {
        foot.push(UI.h('button', { class: 'danger', onclick: () => { failIt(iid, () => { m.close(); onDone(); }); } }, '流标'));
      }
      const m = UI.modal('询价详情', body, foot, { wide: true });
    }

    await load();
  }

  /* -------- 供应商：询价列表 + 报价/改价 -------- */
  async function supplierView(page, user) {
    let pageNo = 1;
    let tab = '';
    const SIZE = 10;
    /* 报价状态筛选：全部 / 待报价 / 已报价 / 已截止（后端 tab 参数过滤） */
    const tabSel = UI.selectField([['', '全部'], ['pending', '待报价'], ['quoted', '已报价'], ['closed', '已截止']], '',
      { onchange: (e) => { tab = e.target.value; pageNo = 1; load(); } });
    const listCard = UI.h('div', { class: 'card' });
    const pagerBox = UI.h('div', {});
    page.appendChild(UI.h('div', { class: 'card' },
      UI.h('div', { class: 'toolbar' },
        UI.h('h3', { style: 'margin:0;border:none;padding:0' }, '收到的询价'),
        UI.h('div', { class: 'spacer' }),
        tabSel,
        UI.h('span', { class: 'hint' }, '密封报价：截止前任何人（含平台）都看不到他人价格'))));
    page.appendChild(listCard);
    page.appendChild(pagerBox);

    async function load() {
      const d = await API.get('/inquiries' + API.qs({ page: pageNo, size: SIZE, tab }));
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
      const req = d.requirement || {};
      const hist = d.historyRounds || [];
      const histBlock = hist.length ? [
        UI.h('div', { class: 'sec-title' }, '历史轮次参考（当前第 ' + (d.roundNo || '-') + ' 轮）'),
        UI.table([
          { label: '轮次', render: (r) => '第 ' + r.roundNo + ' 轮' },
          { key: 'inquiry_no', label: '询价单号' },
          { label: '我的上轮报价', num: true, render: (r) => r.quote_id
            ? UI.fmtMoney(r.price) + ' 元/吨 × ' + UI.fmtMoney(r.quantity) + ' 吨'
              + (r.freight_price != null ? '（运价 ' + UI.fmtMoney(r.freight_price) + '）' : '')
            : UI.h('span', { class: 'tag' }, '未报价') },
          { label: '钢厂反馈', render: (r) => r.fb_decision === 'REJECTED'
            ? UI.h('span', { class: 'tag red' }, '不认可：' + (r.fb_reason || ''))
            : r.fb_decision === 'ACCEPTED' ? UI.h('span', { class: 'tag green' }, '认可')
            : UI.h('span', { class: 'tag' }, '未反馈') },
        ], hist),
      ] : [];
      const body = UI.h('div', {},
        ...(histBlock.length ? histBlock : []),
        UI.h('div', { class: 'sec-title' }, '采购需求'),
        UI.kv([
          ['询价编号', d.inquiry_no], ['状态', UI.statusTag('INQUIRY', d.status)],
          ['品种', d.varietyName], ['数量', UI.fmtMoney(d.quantity) + ' 吨'],
          ['溢短装', req.moreLessRate != null ? '±' + String(req.moreLessRate).replace(/\.?0+$/, '') + '%' : '-'],
          ['报价截止', UI.fmtDateTime(d.deadline)],
          ['期望到货', UI.fmtDate(d.expect_arrive_date)],
        ]),
        UI.h('div', { class: 'sec-title' }, '技术参数与质量要求'),
        UI.kv([
          ['品位要求', d.grade == null ? '-' : String(d.grade) + '%'],
          ['质量要求', req.qualityReq || '以询价说明为准'],
          ['需求概要', req.demandName || '-'],
        ]),
        UI.h('div', { class: 'sec-title' }, '交货与结算要求'),
        UI.kv([
          ['交货方式', DELIVERY[d.delivery_type] || d.delivery_type || '-'],
          ['交货地点', d.delivery_place || '-'],
          ['结算方式', SETTLE[d.settle_type] || d.settle_type || '-'],
          ['询价说明', d.inquiry_desc, true],
        ]),
        UI.h('div', { class: 'sec-title' }, '我的报价'),
        d.myQuote ? UI.h('div', {},
          UI.table([
            { key: 'price', label: '单价', num: true, render: (r) => UI.fmtMoney(r.price) },
            { label: '含税', render: (r) => ({ INC_TAX: '含税', EX_TAX: '不含税' }[r.tax_type] || '-') },
            { key: 'freight_price', label: '运价', num: true, render: (r) => r.freight_price != null ? UI.fmtMoney(r.freight_price) : '-' },
            { key: 'quantity', label: '可供数量', num: true, render: (r) => UI.fmtMoney(r.quantity) },
            { key: 'delivery_date', label: '交货时间', render: (r) => UI.fmtDate(r.delivery_date) },
            { label: '交货方式', render: (r) => ({ PORT_FOB: '港口离岸', PORT_TRUCK: '港口自提', PLANT: '厂内自提' }[r.delivery_type] || '-') },
            { key: 'delivery_place', label: '交货地' },
            { key: 'pay_terms', label: '付款条款' },
            { key: 'quality_commit', label: '质量承诺' },
            { key: 'valid_until', label: '有效期至', render: (r) => UI.fmtDate(r.valid_until) },
            { key: 'version', label: '版本', num: true },
            { key: 'status', label: '状态', render: (r) => UI.statusTag('QUOTE', r.status) },
          ], [d.myQuote]),
          UI.h('div', { class: 'sec-title' }, '报价附件'),
          (d.myQuote.files || []).length ? UI.table([
            { key: 'fileName', label: '文件名' },
            { label: '操作', render: (f) => UI.h('span', { class: 'inline-flex' },
                UI.h('button', { class: 'sm', onclick: () => window.previewFile(f.fileId, f.fileName || '报价附件') }, '预览'),
                UI.h('button', { class: 'sm', onclick: () => API.downloadFile(f.fileId, f.fileName || '报价附件') }, '下载')) },
          ], d.myQuote.files) : UI.h('div', { class: 'empty' }, '无附件'))
        : UI.h('div', { class: 'empty' }, '尚未报价'));
      UI.modal('询价详情 · 报价响应', body, [], { wide: true });
    }

    async function quoteForm(r, quoteId, onDone) {
      const q = quoteId ? (await API.get('/quotes/' + quoteId)) : null;
      const DT = { PORT_FOB: '港口离岸', PORT_TRUCK: '港口自提', PLANT: '厂内自提' };
      /* 采购需求细节（技术参数/质量要求/溢短装），取询价详情补充 */
      const det = await API.get('/inquiries/' + r.id).catch(() => null);
      const reqInfo = (det && det.requirement) || {};
      /* 附件资料：经通用 /files 上传（PDF/JPG/PNG ≤20MB，最多 5 个），修改报价时预填已传附件 */
      let fileIds = ((q && q.files) || []).map((f) => f.fileId);
      const fileInput = UI.h('input', { type: 'file', multiple: true, accept: '.pdf,.jpg,.jpeg,.png' });
      const fileList = UI.h('div', { class: 'hint', style: 'margin-top:4px' });
      function renderFiles() {
        const names = ((q && q.files) || []).filter((f) => fileIds.indexOf(f.fileId) >= 0)
          .map((f) => f.fileName || f.fileId)
          .concat(Array.from(fileInput.files || []).map((f) => f.name));
        fileList.textContent = names.length ? '已选附件：' + names.join('、') : '未选择附件';
      }
      fileInput.addEventListener('change', () => {
        if ((fileInput.files || []).length + fileIds.length > 5) { UI.toast('附件最多 5 个', 'err'); fileInput.value = ''; }
        renderFiles();
      });
      renderFiles();
      /* —— 上半：采购需求信息（只读，供应商不可修改） —— */
      const demandInfo = UI.kv([
        ['询价编号', r.inquiryNo],
        ['矿种', r.varietyName],
        ['品位(%)', r.grade == null ? '-' : String(r.grade)],
        ['采购数量', UI.fmtMoney(r.quantity) + ' 吨' + (reqInfo.moreLessRate != null ? '（溢短装 ±' + String(reqInfo.moreLessRate).replace(/\.?0+$/, '') + '%）' : '')],
        ['质量要求', reqInfo.qualityReq || '以询价说明为准'],
        ['交货地点', r.deliveryPlace || '-'],
        ['交货方式', DT[r.deliveryType] || r.deliveryType || '-'],
        ['期望到货', UI.fmtDate(r.expectArriveDate)],
        ['结算方式', SETTLE[r.settleType] || r.settleType || '-'],
        ['报价截止', UI.fmtDateTime(r.deadline)],
      ]);
      /* —— 下半：可编辑报价表单 —— */
      const price = UI.input('number', q ? q.price : '', { placeholder: '单价（元/吨）' });
      const taxSel = UI.selectField([['INC_TAX', '含税'], ['EX_TAX', '不含税']],
        q ? (q.tax_type || 'INC_TAX') : 'INC_TAX');
      const freight = UI.input('number', (q && q.freight_price != null) ? q.freight_price : '',
        { placeholder: '运价（元/吨）', step: '0.01' });
      const qty = UI.input('number', q ? q.quantity : r.quantity, { placeholder: '可供数量（吨）' });
      const ddate = UI.input('date', q ? UI.fmtDate(q.delivery_date) : '', { placeholder: '交货时间' });
      const dtSel = UI.selectField([['PORT_FOB', '港口离岸'], ['PORT_TRUCK', '港口自提'], ['PLANT', '厂内自提']],
        q ? (q.delivery_type || (r.deliveryType || '')) : (r.deliveryType || ''));
      const place = UI.input('text', q ? q.delivery_place : '', { placeholder: '到货港口（选填）' });
      const pay = UI.input('text', q ? q.pay_terms : '', { placeholder: '付款条款（选填）' });
      const quality = UI.h('textarea', { rows: 2, style: 'width:100%', placeholder: '质量承诺（选填）' });
      if (q) quality.value = q.quality_commit || '';
      const remark = UI.h('textarea', { rows: 2, style: 'width:100%', placeholder: '备注（可供数量低于询价量 80% 必填）' });
      if (q) remark.value = q.remark || '';
      const m = UI.modal(quoteId ? '修改报价（将留痕新版本）' : '密封报价', UI.h('form', { onsubmit: (e) => e.preventDefault() },
        UI.h('div', { class: 'sec-title' }, '采购需求信息'),
        demandInfo,
        ...(((det && det.historyRounds) || []).length ? [UI.h('div',
          { style: 'margin:8px 0;padding:8px 12px;background:#fff7ed;border-radius:6px' },
          UI.h('div', { style: 'font-weight:600;color:#c2410c;margin-bottom:6px' },
            '历史轮次参考：贵司曾参与本需求历史轮次询价'
            + (det.roundNo ? '，当前为第 ' + det.roundNo + ' 轮' : '')),
          UI.table([
            { label: '轮次', render: (r) => '第 ' + r.roundNo + ' 轮' },
            { key: 'inquiry_no', label: '询价单号' },
            { label: '我的上轮报价', num: true, render: (r) => r.quote_id
              ? UI.fmtMoney(r.price) + ' 元/吨 × ' + UI.fmtMoney(r.quantity) + ' 吨'
                + (r.freight_price != null ? '（运价 ' + UI.fmtMoney(r.freight_price) + '）' : '')
              : UI.h('span', { class: 'tag' }, '未报价') },
            { label: '钢厂反馈', render: (r) => r.fb_decision === 'REJECTED'
              ? UI.h('span', { class: 'tag red' }, '不认可：' + (r.fb_reason || ''))
              : r.fb_decision === 'ACCEPTED' ? UI.h('span', { class: 'tag green' }, '认可')
              : UI.h('span', { class: 'tag' }, '未反馈') },
          ], det.historyRounds))] : []),
        UI.h('div', { class: 'sec-title' }, '报价信息'),
        UI.h('div', { class: 'form-grid' },
          UI.formRow('单价', price, true),
          UI.formRow('含税/不含税', taxSel, true),
          UI.formRow('运价', freight, true),
          UI.formRow('可供数量', qty, true),
          UI.formRow('交货时间', ddate, true),
          UI.formRow('交货方式', dtSel, true),
          UI.formRow('到货港口', place),
          UI.formRow('付款条款', pay),
          UI.h('div', { class: 'form-row full' }, UI.h('label', {}, '质量承诺'), quality),
          UI.h('div', { class: 'form-row full' }, UI.h('label', {}, '备注'), remark)),
        UI.h('div', { class: 'sec-title' }, '附件资料（选填，PDF/JPG/PNG ≤20MB，最多 5 个）'),
        UI.h('div', { class: 'form-row full' }, fileInput),
        fileList,
        UI.h('div', { class: 'hint' }, '截止前可修改（新版本留痕）；截止后不可再报')), [
        UI.h('button', { class: 'primary', onclick: async () => {
          /* 附件：先逐个经 /files 上传，再与已有附件合并关联到本次报价 */
          const fids = fileIds.slice();
          try {
            for (const f of Array.from(fileInput.files || [])) {
              const up = await API.upload(f, '/files');
              fids.push(up.fileId);
            }
          } catch (e) { return; }
          if (fids.length > 5) { UI.toast('附件最多 5 个', 'err'); return; }
          const body = {
            price: price.value, quantity: qty.value, deliveryDate: ddate.value,
            taxType: taxSel.value, deliveryType: dtSel.value,
          };
          if (!body.price || !body.quantity || !body.deliveryDate) { UI.toast('单价、可供数量、交货时间为必填', 'err'); return; }
          if (!body.taxType) { UI.toast('请选择含税/不含税', 'err'); return; }
          if (!body.deliveryType) { UI.toast('请选择交货方式', 'err'); return; }
          if (freight.value === '') { UI.toast('请填写运价', 'err'); return; }
          body.freightPrice = freight.value;
          if (place.value.trim()) body.deliveryPlace = place.value.trim();
          if (pay.value.trim()) body.paymentTerms = pay.value.trim();
          if (quality.value.trim()) body.qualityTerms = quality.value.trim();
          if (remark.value.trim()) body.remark = remark.value.trim();
          if (fids.length) body.fileIds = fids;
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

  /* -------- 议价定标（钢厂）：揭示 → 议价 → 定标 → 订单 四阶段工作台 -------- */
  const BARGAIN_STAGES = [
    ['CLOSED', '已揭示待议价'],
    ['BARGAINING', '议价中'],
    ['AWARDED', '已定标'],
    ['FEEDBACK', '反馈待处理'],
  ];
  const STAGE_TIPS = {
    CLOSED: '比价已揭示：可发起议价，或对最优报价直接定标',
    BARGAINING: '多轮密封还价中：一方接受后其余在途轮次自动失效',
    AWARDED: '已锁货锁价生成订单：供应商 48 小时内确认',
    FEEDBACK: '归集询价已反馈不认可：待运营平台重新处理',
  };

  Pages.bargain = async function (page, user) {
    const isSteel = (user.roles || []).indexOf('STEEL_BUYER') >= 0;
    if (isSteel) return steelBargainView(page);
    /* 议价定标仅保留钢厂端，供应商端已下线，直达总览 */
    location.hash = '#/overview';
  };

  /* 钢厂议价定标工作台：流程步骤条（点击筛选）+ 全阶段询价列表 + 议价/定标弹窗 */
  async function steelBargainView(page) {
    let status = '';
    const stepsBox = UI.h('div', { class: 'flow-steps' });
    const listCard = UI.h('div', { class: 'card' });

    page.appendChild(UI.h('div', { class: 'card' },
      UI.h('h3', { class: 'bar-title' }, '议价定标流程'),
      stepsBox,
      UI.h('div', { class: 'hint' },
        '自发询价：比价揭示后可发起议价（一方接受后其余轮次自动失效），仅已接受轮次可定标；定标即锁货锁价生成订单，供应商 48 小时内确认。'
        + '归集询价：钢厂仅对比价结果认可 / 不认可，定标由运营平台执行。')));
    page.appendChild(listCard);

    async function load() {
      const d = await API.get('/inquiries' + API.qs({ size: 100 }));
      const all = (d.list || []).filter((r) => BARGAIN_STAGES.some(([c]) => c === r.status));

      /* 流程步骤条：圆形内为各阶段数量，点击筛选 / 再点取消 */
      const counts = {};
      BARGAIN_STAGES.forEach(([c]) => { counts[c] = all.filter((r) => r.status === c).length; });
      stepsBox.innerHTML = '';
      BARGAIN_STAGES.forEach(([code, name], i) => {
        if (i) stepsBox.appendChild(UI.h('span', { class: 'flow-arrow' }, '→'));
        stepsBox.appendChild(UI.h('a', {
          class: 'flow-step' + (status === code ? ' active' : ''),
          href: 'javascript:;', title: STAGE_TIPS[code],
          onclick: () => { status = status === code ? '' : code; load(); },
        },
          UI.h('span', { class: 'flow-circle flow-num' }, String(counts[code])),
          UI.h('div', { class: 'flow-name' }, name)));
      });

      const rows = status ? all.filter((r) => r.status === status) : all;
      listCard.innerHTML = '';
      listCard.appendChild(UI.h('div', { class: 'toolbar' },
        UI.h('h3', { style: 'margin:0;border:none;padding:0' }, '议价定标列表'),
        UI.h('div', { class: 'spacer' }),
        UI.h('span', { class: 'hint' }, status ? '再次点击上方阶段可取消筛选' : '点击上方阶段图标可按阶段筛选')));
      listCard.appendChild(UI.table([
        { label: '询价编号', render: (r) => UI.h('span', {}, r.inquiry_no,
            r.agg_id ? UI.h('span', { class: 'tag', style: 'margin-left:6px' }, '归集') : null) },
        { key: 'varietyName', label: '品种' },
        { key: 'quantity', label: '数量(吨)', num: true, render: (r) => UI.fmtQty(r.quantity) },
        { key: 'deadline', label: '报价截止', render: (r) => UI.fmtDateTime(r.deadline) },
        { key: 'status', label: '状态', render: (r) => UI.statusTag('INQUIRY', r.status) },
        { label: '操作', render: (r) => {
          const isAgg = !!r.agg_id;
          const btns = [UI.h('button', { class: 'sm', onclick: () => workspace(r) },
            isAgg ? '查看比价' : '议价 / 定标')];
          if (r.status === 'AWARDED') {
            btns.push(UI.h('button', { class: 'sm primary', onclick: () => { location.hash = '#/order'; } }, '查看订单'));
          }
          return UI.h('span', { class: 'inline-flex' }, ...btns);
        } },
      ], rows, '暂无相关询价'));

      async function workspace(r) {
        const snap = await API.get('/inquiries/' + r.id + '/quotes/reveal');
        let m;
        m = UI.modal('议价定标工作台（' + r.inquiry_no + '）',
          renderSnapshot(snap, r.id, () => { m.close(); load(); }, () => { m.close(); load(); }, r.status),
          [], { wide: true });
      }
    }

    await load();
  }
})();
