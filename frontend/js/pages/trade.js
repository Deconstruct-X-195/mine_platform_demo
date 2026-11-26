/* 询价报价议价（PRD 4.4/FR-04/FR-05/T08-T12）：密封报价、截止揭示比价、多轮议价、定标、流标 */
(function () {
  window.Pages = window.Pages || {};
  const SETTLE = { PREPAY: '现货现款', COD: '货到付款', CREDIT: '账期结算', INSTALLMENT: '分期付款' };
  const DELIVERY = { PORT_FOB: '港口离岸', PORT_TRUCK: '港口自提', PLANT: '场内自提', STATION_SELF: '到站自提' };
  const INVITE_STATUS = { INVITED: '已邀请', QUOTED: '已报价', DECLINED: '已婉拒', EXPIRED: '已失效' };

  /* 询价单状态中文（批量操作提示与导出用） */
  const STATUS_TXT = {
    DRAFT: '待提交', SENT: '已发出', AGGREGATED: '已归集', QUOTING: '报价中', CLOSED: '已截止', BARGAINING: '议价中',
    REVEALED: '已揭示', AWARDED: '已定标', FEEDBACK: '反馈待处理', FAILED: '已流标',
  };

  /* 议价对标面板：基准价 + 他人匿名价 + 近期成交均价 */
  async function contextPanel(iid) {
    const box = UI.h('div', { class: 'card', style: 'margin-bottom:12px' });
    try {
      const c = await API.get('/inquiries/' + iid + '/bargain-context');
      box.appendChild(UI.h('h3', {}, '议价对标'));
      box.appendChild(UI.kv([
        ['平台基准价', c.basePrice ? UI.fmtMoney(c.basePrice.price) + ' 元/湿吨（' + UI.fmtDate(c.basePrice.priceDate) + '，' + (c.basePrice.priceBasis === 'DRY' ? '干基' : '湿基') + '）' : '无'],
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
        { key: 'price', label: '价格(元/湿吨)', num: true, render: (r) => UI.fmtMoney(r.price) },
        { key: 'quantity', label: '数量(湿吨)', num: true, render: (r) => UI.fmtMoney(r.quantity) },
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
    const price = UI.input('number', (defaultPrice != null && defaultPrice !== '') ? Number(defaultPrice).toFixed(2) : '',
      { placeholder: '还价（元/湿吨）', step: '0.01' });
    const qty = UI.input('number', '', { placeholder: '数量（湿吨，选填）', step: '0.01' });
    const ddate = UI.input('date', '', { placeholder: '到货日（选填）' });
    const settle = UI.selectField([['', '结算不变']].concat(Object.entries(SETTLE)), '');
    const extra = UI.h('textarea', { rows: 2, style: 'width:100%', placeholder: '附加条款（选填）' });
    return UI.h('div', { class: 'card' },
      UI.h('h3', {}, '发起新一轮还价'),
      UI.h('div', { class: 'inline-flex', style: 'flex-wrap:wrap' },
        UI.h('label', { class: 'field' }, '价格（元/湿吨） ', price),
        UI.h('label', { class: 'field' }, '数量（湿吨） ', qty),
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
  async function renderSnapshot(snap, iid, onDone, after, inqStatus) {
    const split = !!snap.shareQty;
    const noBids = inqStatus === 'AWARDED' || inqStatus === 'FAILED';
    /* 单价按报价模式展示（港口现货价±上下浮）：比价表各报价共用询价单品种，取该品种现货价为基准 */
    let spotBase = null;
    try {
      const inq = await API.get('/inquiries/' + iid);
      spotBase = (await UI.spotPrices())[inq.varietyName] ?? null;
    } catch (e) { /* 无基准价时回退绝对单价 */ }
    const body = UI.h('div', {},
      UI.kv([
        ['询价编号', snap.inquiryNo],
        ['揭示时间', UI.fmtDateTime(snap.revealedAt)],
      ].concat(split ? [['本钢厂份额', UI.fmtMoney(snap.shareQty) + ' 湿吨']] : [])),
      UI.h('h3', { style: 'margin-top:12px' }, split ? '比价表（已按贵司需求份额拆分推送）' : '比价表（按价格升序固化）'),
      UI.table([
        { key: 'seq', label: '序号', num: true },
        { label: '单价(元/湿吨)', num: true,
          render: (r) => UI.spotShown(r.priceSign, r.priceFloat) || UI.spotDiff(spotBase, r.unitPrice) },
        { key: 'freightPrice', label: '运费(元/湿吨)', num: true, render: (r) => r.freightPrice != null ? UI.fmtMoney(r.freightPrice) : '-' },
        { label: '含税', render: (r) => ({ INC_TAX: '含税', EX_TAX: '不含税' }[r.taxType] || '-') },
        { key: 'quantity', label: '数量(湿吨)', num: true, render: (r) => UI.fmtMoney(r.quantity) },
        { label: '港口', render: (r) => r.deliveryPlace || '-' },
        { key: 'deliveryDate', label: '到货日', render: (r) => UI.fmtDate(r.deliveryDate) },
        { key: 'payTerms', label: '付款条款' },
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

  /* -------- 钢厂：询价管理（询价单由运营端汇集需求后生成，钢厂端只读） -------- */
  Pages.inquiry = async function (page, user) {
    const isSteel = (user.roles || []).indexOf('STEEL_BUYER') >= 0;
    if (isSteel) return steelView(page);
    return supplierView(page, user);
  };

  async function steelView(page) {
    let status = '';
    let pageNo = 1;
    const SIZE = 10;
    const selected = new Set();   // 勾选的询价单 id（供导出）
    const rowCache = new Map();   // id -> 行数据
    let pageRows = [];            // 当前页行
    const listCard = UI.h('div', { class: 'card' });
    const listBox = UI.h('div', { class: 'list-fixed' });   // 定高列表区（同运营端）：表头39px+10行，超出滚动
    const pagerBox = UI.h('div', {});
    /* 询价单由运营端汇集钢厂需求后生成：钢厂端只读查看，导出按钮位于「全部状态」筛选之后 */
    page.appendChild(UI.h('div', { class: 'card' },
      UI.h('div', { class: 'toolbar' },
        UI.h('h3', { style: 'margin:0;border:none;padding:0' }, '询价单'),
        UI.statusFilter('INQUIRY', (v) => { status = v; pageNo = 1; selected.clear(); load(); }),
        UI.h('button', { onclick: batchExport }, '导 出'))));
    page.appendChild(listCard);
    listCard.appendChild(listBox);    // 定高列表区：纵向超出滚动，横向滚动条固定在分页行上方
    listCard.appendChild(pagerBox);   // 分页条固定在面板右下角

    function selRows() {
      return [...selected].map((id) => rowCache.get(id)).filter(Boolean);
    }
    function batchExport() {
      const rows = selRows();
      if (!rows.length) { UI.toast('请先勾选询价单', 'err'); return; }
      UI.exportPreview({
        title: '导出预览 — 询价单',
        filename: '询价单导出_' + new Date().toISOString().slice(0, 10).replace(/-/g, '') + '.csv',
        head: ['询价编号', '品种', '数量(湿吨)', '期望到货', '状态', '创建时间'],
        rows: rows.map((r) => [
          r.inquiry_no,
          r.varietyName,
          r.quantity,
          UI.fmtDate(r.expect_arrive_date),
          STATUS_TXT[r.status] || r.status,
          UI.fmtDateTime(r.created_at),
        ]),
      });
    }

    function syncHead() {
      const hb = listCard.querySelector('thead input[type=checkbox]');
      if (hb) hb.checked = pageRows.length > 0 && pageRows.every((r) => selected.has(r.id));
    }

    let loadSeq = 0;
    async function load() {
      const seq = ++loadSeq;
      const d = await API.get('/inquiries' + API.qs({ page: pageNo, size: SIZE, status }));
      if (seq !== loadSeq) return;
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
        { key: 'inquiry_no', label: '询价编号' },
        { key: 'varietyName', label: '品种' },
        { key: 'quantity', label: '数量(湿吨)', num: true, render: (r) => UI.fmtMoney(r.quantity) },
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
          ['询价编号', UI.h('span', {}, d.inquiry_no)],
          ['状态', UI.statusTag('INQUIRY', d.status)],
          ['品种', d.varietyName],
          ['数量', UI.fmtMoney(showQty) + ' 湿吨' + (isAgg ? '（本钢厂份额）' : '')],
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
          m2 = UI.modal('比价快照', await renderSnapshot(snap, iid, onDone, () => { m2.close(); onDone(); }, d.status), [], { wide: true });
          m2.mask.addEventListener('click', onDone);
        } }, '截止揭示'));
      }
      if (d.status === 'CLOSED' || d.status === 'BARGAINING') {
        foot.push(UI.h('button', { class: 'primary', onclick: async () => {
          const snap = await API.get('/inquiries/' + iid + '/quotes/reveal');
          m.close();
          let m2;
          m2 = UI.modal('比价快照', await renderSnapshot(snap, iid, onDone, () => { m2.close(); onDone(); }, d.status), [], { wide: true });
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
    const selected = new Set();   // 勾选的询价 id
    const rowCache = new Map();   // id -> 行数据
    let pageRows = [];            // 当前页行
    const tabSel = UI.selectField([['', '全部'], ['pending', '待报价'], ['quoted', '已报价'], ['closed', '已截止']], '',
      { onchange: (e) => { tab = e.target.value; pageNo = 1; selected.clear(); load(); } });
    const listCard = UI.h('div', { class: 'card' });
    const listBox = UI.h('div', { class: 'list-fixed' });   // 定高列表区（同运营端）：表头39px+10行，超出滚动
    const pagerBox = UI.h('div', {});
    page.appendChild(UI.h('div', { class: 'card' },
      UI.h('div', { class: 'toolbar' },
        UI.h('h3', { style: 'margin:0;border:none;padding:0' }, '收到的询价'),
        UI.h('div', { class: 'spacer' }),
        tabSel,
        UI.h('span', { class: 'hint' }, '密封报价：揭示前任何人（含平台）都看不到他人价格'))));
    page.appendChild(listCard);
    listCard.appendChild(listBox);    // 定高列表区：纵向超出滚动，横向滚动条固定在分页行上方
    listCard.appendChild(pagerBox);   // 分页条固定在面板右下角

    function syncHead() {
      const hb = listCard.querySelector('thead input[type=checkbox]');
      if (hb) hb.checked = pageRows.length > 0 && pageRows.every((r) => selected.has(r.id));
    }

    let loadSeq = 0;
    async function load() {
      const seq = ++loadSeq;
      const d = await API.get('/inquiries' + API.qs({ page: pageNo, size: SIZE, tab }));
      if (seq !== loadSeq) return;
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
        { key: 'inquiryNo', label: '询价编号' },
        { key: 'varietyName', label: '品种' },
        { key: 'grade', label: '品位(%)' },
        { key: 'quantity', label: '数量(湿吨)', num: true, render: (r) => UI.fmtMoney(r.quantity) },
        { key: 'deliveryPlace', label: '交货地点' },
        { key: 'expectArriveDate', label: '期望到货', render: (r) => UI.fmtDate(r.expectArriveDate) },
        { key: 'settleType', label: '结算', render: (r) => SETTLE[r.settleType] || r.settleType || '-' },
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
      /* 我的报价单价按报价模式展示（品种港口现货价±上下浮） */
      const spotBase = (await UI.spotPrices())[d.varietyName] ?? null;
      const histBlock = hist.length ? [
        UI.h('div', { class: 'sec-title' }, '历史轮次参考（当前第 ' + (d.roundNo || '-') + ' 轮）'),
        UI.table([
          { label: '轮次', render: (r) => '第 ' + r.roundNo + ' 轮' },
          { key: 'inquiry_no', label: '询价单号' },
          { label: '我的上轮报价', num: true, render: (r) => r.quote_id
            ? UI.spotDiff(spotBase, r.price) + ' × ' + UI.fmtMoney(r.quantity) + ' 湿吨'
              + (r.freight_price != null ? '（运费 ' + UI.fmtMoney(r.freight_price) + ' 元/湿吨）' : '')
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
          ['品种', d.varietyName], ['数量', UI.fmtMoney(d.quantity) + ' 湿吨'],
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
            { key: 'price', label: '单价(元/湿吨)', num: true,
              render: (r) => UI.spotShown(r.price_sign, r.price_float) || UI.spotDiff(spotBase, r.price) },
            { label: '含税', render: (r) => ({ INC_TAX: '含税', EX_TAX: '不含税' }[r.tax_type] || '-') },
            { key: 'freight_price', label: '运费（元/湿吨）', num: true, render: (r) => r.freight_price != null ? UI.fmtMoney(r.freight_price) : '-' },
            { key: 'quantity', label: '可供数量(湿吨)', num: true, render: (r) => UI.fmtMoney(r.quantity) },
            { key: 'delivery_date', label: '预计到港时间', render: (r) => UI.fmtDate(r.delivery_date) },
            { key: 'delivery_place', label: '到货港口' },
            { key: 'quality_commit', label: '其他' },
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
      const DT = { PORT_FOB: '港口离岸', PORT_TRUCK: '港口自提', PLANT: '场内自提' };
      /* 采购需求细节（技术参数/质量要求/溢短装），取询价详情补充 */
      const det = await API.get('/inquiries/' + r.id).catch(() => null);
      const reqInfo = (det && det.requirement) || {};
      /* —— 上半：采购需求信息（只读，供应商不可修改） —— */
      const demandInfo = UI.kv([
        ['询价编号', r.inquiryNo],
        ['矿种', r.varietyName],
        ['品位(%)', r.grade == null ? '-' : String(r.grade)],
        ['采购数量', UI.fmtMoney(r.quantity) + ' 湿吨' + (reqInfo.moreLessRate != null ? '（溢短装 ±' + String(reqInfo.moreLessRate).replace(/\.?0+$/, '') + '%）' : '')],
        ['质量要求', reqInfo.qualityReq || '以询价说明为准'],
        ['交货地点', r.deliveryPlace || '-'],
        ['交货方式', DT[r.deliveryType] || r.deliveryType || '-'],
        ['期望到货', UI.fmtDate(r.expectArriveDate)],
        ['结算方式', SETTLE[r.settleType] || r.settleType || '-'],
      ]);
      /* —— 下半：可编辑报价表单 —— */
      /* 产品申报：矿种（默认询价单品种）/产地/品位，均必填——描述供应商实际所报货物 */
      const varieties = (await API.get('/base/varieties')).list;
      const vOpts = varieties.map((v) => [v.id, v.varietyName + '(' + v.varietyCode + ')']);
      const defaultVid = (varieties.find((v) => v.varietyName === r.varietyName) || {}).id;
      const varietySel = UI.selectField(vOpts,
        q ? (q.variety_id == null ? '' : String(q.variety_id)) : String(defaultVid == null ? '' : defaultVid));
      const originInput = UI.input('text', q ? (q.origin || '') : '', { placeholder: '产地，如 澳大利亚' });
      const gradeInput = UI.input('number', q && q.grade != null ? String(q.grade) : '',
        { placeholder: '品位%，如 62', step: '0.01' });
      /* 单价：「港口现货价格」仅为固定字样（不关联品种当日港口价格数据），
         供应商选择 +/- 方向并填写上下浮金额；落库单价=上下浮金额，方向存 price_sign */
      const priceSignSel = UI.selectField([['+', '+'], ['-', '-']], '+');
      const priceFloat = UI.input('number', '', { placeholder: '上下浮（元/湿吨）', step: '0.01', min: '0' });
      const priceBox = UI.h('span', { class: 'inline-flex', style: 'gap:8px;flex-wrap:nowrap;align-items:center' },
        UI.h('input', { value: '港口现货价格', disabled: true,
          style: 'width:110px;background:#f5f5f7;color:var(--label-2)' }),
        priceSignSel, priceFloat);
      /* 修改报价回填：直接使用上次报价存储的方向与上下浮金额（不关联当日港口价格数据） */
      if (q && q.price_sign) {
        priceSignSel.value = q.price_sign;
        priceFloat.value = q.price_float != null ? String(Math.abs(Math.round(Number(q.price_float) * 100) / 100)) : '';
      }
      const taxSel = UI.selectField([['INC_TAX', '含税'], ['EX_TAX', '不含税']],
        q ? (q.tax_type || 'INC_TAX') : 'INC_TAX');
      const freight = UI.input('number', (q && q.freight_price != null) ? Number(q.freight_price).toFixed(2) : '',
        { placeholder: '运费（元/湿吨）', step: '0.01' });
      const qtyVal = q ? q.quantity : r.quantity;
      const qty = UI.input('number', (qtyVal != null && qtyVal !== '') ? Number(qtyVal).toFixed(2) : '',
        { placeholder: '可供数量（湿吨）', step: '0.01' });
      const ddate = UI.input('date', q ? UI.fmtDate(q.delivery_date) : '', { placeholder: '预计到港时间' });
      /* 到货港口：可选黄骅港/天津港（交付信息由港口承载，替代原「交货方式 + 到货港口」两字段） */
      const portSel = UI.selectField([['黄骅港', '黄骅港'], ['天津港', '天津港']],
        q && ['黄骅港', '天津港'].indexOf(q.delivery_place) >= 0 ? q.delivery_place : '黄骅港');
      const pay = UI.input('text', q ? q.pay_terms : '', { placeholder: '付款条款（选填）' });
      const quality = UI.h('textarea', { rows: 2, style: 'width:100%', placeholder: '其他说明（选填）' });
      if (q) quality.value = q.quality_commit || '';
      /* 报价附件：矿石成分检测报告（pdf/jpg/png，≤20MB，最多 5 个；经通用 /files 上传后随报价关联） */
      const upFiles = q ? (q.files || []).map((f) => ({ fileId: f.fileId, fileName: f.fileName })) : [];
      const fileInput = UI.h('input', { type: 'file', accept: '.pdf,.jpg,.jpeg,.png', style: 'display:none' });
      const fileList = UI.h('div', { style: 'display:flex;flex-direction:column;gap:4px;margin-top:6px' });
      function renderFiles() {
        fileList.innerHTML = '';
        upFiles.forEach((f, i) => {
          fileList.appendChild(UI.h('div', { class: 'inline-flex', style: 'gap:8px;align-items:center' },
            UI.h('span', {}, f.fileName),
            UI.h('button', { class: 'sm', type: 'button', onclick: () => window.previewFile(f.fileId, f.fileName || '报价附件') }, '预览'),
            UI.h('button', { class: 'sm danger', type: 'button',
              onclick: () => { upFiles.splice(i, 1); renderFiles(); } }, '移除')));
        });
        if (!upFiles.length) fileList.appendChild(UI.h('span', { class: 'hint' }, '未上传附件'));
      }
      fileInput.addEventListener('change', async () => {
        const file = fileInput.files[0];
        if (!file) return;
        try {
          const up = await API.upload(file, '/files');
          upFiles.push({ fileId: up.fileId, fileName: up.fileName || file.name });
          renderFiles();
          UI.toast('附件已上传', 'ok');
        } catch (e) { /* toast 已提示 */ }
        fileInput.value = '';
      });
      renderFiles();
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
              ? UI.spotDiff(baseRow ? baseRow.price : null, r.price) + ' × ' + UI.fmtMoney(r.quantity) + ' 湿吨'
                + (r.freight_price != null ? '（运费 ' + UI.fmtMoney(r.freight_price) + ' 元/湿吨）' : '')
              : UI.h('span', { class: 'tag' }, '未报价') },
            { label: '钢厂反馈', render: (r) => r.fb_decision === 'REJECTED'
              ? UI.h('span', { class: 'tag red' }, '不认可：' + (r.fb_reason || ''))
              : r.fb_decision === 'ACCEPTED' ? UI.h('span', { class: 'tag green' }, '认可')
              : UI.h('span', { class: 'tag' }, '未反馈') },
          ], det.historyRounds))] : []),
        UI.h('div', { class: 'sec-title' }, '报价信息'),
        UI.h('div', { class: 'form-grid' },
          UI.formRow('矿种', varietySel, true),
          UI.formRow('产地', originInput, true),
          UI.formRow('品位(%)', gradeInput, true),
          UI.formRow('单价（元/湿吨）', priceBox, true),
          UI.formRow('含税/不含税', taxSel, true),
          UI.formRow('运费（元/湿吨）', freight, true),
          UI.formRow('可供数量（湿吨）', qty, true),
          UI.formRow('预计到港时间', ddate, true),
          UI.formRow('到货港口', portSel, true),
          UI.formRow('付款条款', pay),
          UI.h('div', { class: 'form-row full' }, UI.h('label', {}, '其他'), quality),
          UI.h('div', { class: 'form-row full' }, UI.h('label', {}, '矿石成分检测报告'),
            UI.h('span', { style: 'display:flex;flex-direction:column;gap:4px' },
              UI.h('span', { class: 'inline-flex', style: 'gap:8px;align-items:center' },
                UI.h('button', { class: 'sm', type: 'button', onclick: () => fileInput.click() }, '上传附件'),
                UI.h('span', { class: 'hint' }, '支持 pdf/jpg/png，≤20MB，最多 5 个')),
              fileList, fileInput))),
        UI.h('div', { class: 'hint' }, '修改报价将留痕新版本')), [
        UI.h('button', { class: 'primary', onclick: async () => {
          const body = {
            priceSign: priceSignSel.value, priceFloat: priceFloat.value,
            quantity: qty.value, deliveryDate: ddate.value,
            taxType: taxSel.value,
          };
          if (!varietySel.value) { UI.toast('请选择矿种', 'err'); return; }
          if (!originInput.value.trim()) { UI.toast('请填写产地', 'err'); return; }
          if (gradeInput.value === '') { UI.toast('请填写品位', 'err'); return; }
          if (body.priceFloat === '' || Number(body.priceFloat) < 0) { UI.toast('请填写上下浮价格（≥0）', 'err'); return; }
          if (!body.quantity || !body.deliveryDate) { UI.toast('上下浮价格、可供数量、预计到港时间为必填', 'err'); return; }
          if (!body.taxType) { UI.toast('请选择含税/不含税', 'err'); return; }
          if (freight.value === '') { UI.toast('请填写运费', 'err'); return; }
          body.varietyId = Number(varietySel.value);
          body.origin = originInput.value.trim();
          body.grade = gradeInput.value;
          body.fileIds = upFiles.map((f) => f.fileId);
          body.freightPrice = freight.value;
          body.deliveryPlace = portSel.value;  // 到货港口（黄骅港/天津港）
          if (pay.value.trim()) body.paymentTerms = pay.value.trim();
          if (quality.value.trim()) body.qualityTerms = quality.value.trim();
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
})();
