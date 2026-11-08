/* 结算管理（PRD 4.8/FR-09-10/T17-T19）：质检录入/结算双向确认/付款登记/归档导出 */
(function () {
  window.Pages = window.Pages || {};

  /* -------- 钢厂：结算工作台 -------- */
  Pages.settlement = async function (page, user) {
    const isSteel = (user.roles || []).indexOf('STEEL_BUYER') >= 0;
    const isSupplier = (user.roles || []).indexOf('SUPPLIER') >= 0;

    if (isSteel) {
      const orders = (await API.get('/orders?size=100&status=PERFORMING')).list || [];
      if (!orders.length) { page.appendChild(UI.h('div', { class: 'card' }, UI.h('div', { class: 'empty' }, '暂无履约中订单'))); return; }
      const orderSel = UI.selectField(orders.map((o) => [o.id, o.order_no + '（' + (o.varietyName || '') + '）']), orders[0].id);
      const qcCard = UI.h('div', { class: 'card' });
      const settleCard = UI.h('div', { class: 'card' });
      page.appendChild(UI.h('div', { class: 'card' },
        UI.h('div', { class: 'toolbar' },
          UI.h('h3', { style: 'margin:0;border:none;padding:0' }, '结算工作台'),
          UI.h('label', { class: 'field' }, '选择订单 ', orderSel))));
      page.appendChild(qcCard);
      page.appendChild(settleCard);
      orderSel.addEventListener('change', load);
      await load();

      async function load() {
        const oid = orderSel.value;
        const checks = await API.get('/orders/' + oid + '/quality-checks');
        qcCard.innerHTML = '';
        qcCard.appendChild(UI.h('h3', {}, '质检记录'));
        qcCard.appendChild(UI.table([
          { key: 'checkNo', label: '质检编号' },
          { key: 'arrivedQty', label: '实收数量', num: true, render: (r) => UI.fmtMoney(r.arrivedQty) },
          { key: 'indicators', label: '指标' },
          { key: 'checkDesc', label: '说明' },
          { key: 'conclusion', label: '结论', render: (r) => UI.h('span', { class: 'tag ' + (r.conclusion === 'ACCEPT' ? 'green' : 'red') }, r.conclusion === 'ACCEPT' ? '合格' : '拒收') },
          { label: '附件', render: (r) => r.fileUrl ? UI.h('a', { href: 'javascript:;', onclick: () => API.downloadFile(r.fileUrl, '质检附件-' + r.fileUrl) }, '附件') : '-' },
          { key: 'createdAt', label: '时间', render: (r) => UI.fmtDateTime(r.createdAt) },
        ], checks.list || checks, '暂无质检记录'));
        qcCard.appendChild(UI.h('button', { class: 'primary', style: 'margin-top:10px', onclick: () => qcForm(oid, load) }, '质检录入'));

        const sList = (await API.get('/settlements' + API.qs({ orderId: oid, size: 1 }))).list || [];
        const settle = sList[0];
        settleCard.innerHTML = '';
        settleCard.appendChild(UI.h('h3', {}, '结算处理'));
        if (!settle || !settle.id) {
          settleCard.appendChild(UI.h('div', { class: 'hint' }, '暂无结算单。可先录入质检，再点击"生成结算"（金额由系统按 单价×数量−扣罚 计算）'));
          settleCard.appendChild(UI.h('button', { class: 'primary', style: 'margin-top:10px', onclick: () => settleForm(oid, load) }, '生成结算'));
          return;
        }
        settleCard.appendChild(UI.kv([
          ['结算编号', settle.settleNo],
          ['状态', UI.statusTag('SETTLEMENT', settle.status)],
          ['结算数量', UI.fmtMoney(settle.settleQty) + ' 吨'],
          ['调价金额', UI.fmtMoney(settle.adjustAmount)],
          ['扣罚金额', UI.fmtMoney(settle.deductAmount)],
          ['结算总额', UI.h('b', {}, UI.fmtMoney(settle.totalAmount) + ' 元')],
          ['供应商确认', UI.fmtDateTime(settle.supplierConfirmAt)],
          ['需方确认', UI.fmtDateTime(settle.buyerConfirmAt)],
          ['结算说明', settle.settleDesc, true],
        ]));
        const foot = [];
        if (isSteel && settle.status === 'PENDING_CONFIRM_BUYER') {
          foot.push(UI.h('button', { class: 'primary', onclick: async () => {
            if (!(await UI.confirmBox('确认需方结算？'))) return;
            await API.put('/settlements/' + settle.id + '/confirm');
            UI.toast('需方已确认', 'ok'); load();
          } }, '需方确认'));
        }
        if (isSteel && (settle.status === 'CONFIRMED' || settle.status === 'COMPLETED')) {
          foot.push(UI.h('button', { class: 'primary', onclick: () => payModal(settle, load) }, '付款登记'));
        }
        if (isSteel && settle.status === 'COMPLETED') {
          foot.push(UI.h('button', { class: 'primary', onclick: () => archiveOrder(oid) }, '归档导出'));
        }
        settleCard.appendChild(UI.h('div', { style: 'margin-top:12px' }, ...foot));
      }

      async function settleForm(oid, onDone) {
        const qty = UI.input('number', '', { placeholder: '结算数量（默认最近合格质检实收）' });
        const adjust = UI.input('number', '0', { placeholder: '质量调价 元/吨，可为负' });
        const deduct = UI.input('number', '0', { placeholder: '扣罚金额' });
        const desc = UI.h('textarea', { rows: 2, style: 'width:100%', placeholder: '结算说明' });
        const m = UI.modal('生成结算单', UI.h('form', { onsubmit: (e) => e.preventDefault() },
          UI.h('div', { class: 'form-grid' },
            UI.formRow('结算数量', qty),
            UI.formRow('质量调价', adjust),
            UI.formRow('扣罚金额', deduct),
            UI.h('div', { class: 'form-row full' }, UI.h('label', {}, '结算说明'), desc))), [
        UI.h('button', { class: 'primary', onclick: async () => {
          const body = {};
          if (qty.value) body.settleQty = qty.value;
          if (adjust.value) body.adjustAmount = adjust.value;
          if (deduct.value) body.deductAmount = deduct.value;
          if (desc.value.trim()) body.settleDesc = desc.value.trim();
          try {
            await API.post('/orders/' + oid + '/settlements', body);
            m.close(); UI.toast('结算单已生成', 'ok'); onDone();
          } catch (e) { /* toast 已提示 */ }
        } }, '生 成'),
        ], { wide: true });
      }

      async function archiveOrder(oid) {
        if (!(await UI.confirmBox('确认归档？须全部运单已签收、结算已完成、无未关闭预警'))) return;
        try {
          await API.post('/orders/' + oid + '/archive');
          UI.toast('订单已归档', 'ok');
          API.download('/orders/' + oid + '/archive/export', '订单归档-' + oid + '.zip');
          load();
        } catch (e) { /* toast 已提示 */ }
      }

      function qcForm(oid, onDone) {
        const arrived = UI.input('number', '', { placeholder: '实收数量（吨）' });
        const conclusion = UI.selectField([['ACCEPT', '合格'], ['REJECT', '拒收']], 'ACCEPT');
        const indicators = UI.h('textarea', { rows: 2, style: 'width:100%', placeholder: '检验指标（如 Fe≥62%，水分≤8%）' });
        const desc = UI.h('textarea', { rows: 2, style: 'width:100%', placeholder: '质检说明' });
        const file = UI.h('input', { type: 'file', accept: 'image/*,.pdf' });
        const m = UI.modal('质检录入', UI.h('form', { onsubmit: (e) => e.preventDefault() },
          UI.h('div', { class: 'form-grid' },
            UI.formRow('实收数量', arrived, true),
            UI.formRow('结论', conclusion, true),
            UI.h('div', { class: 'form-row full' }, UI.h('label', {}, '检验指标'), indicators),
            UI.h('div', { class: 'form-row full' }, UI.h('label', {}, '质检说明'), desc),
            UI.h('div', { class: 'form-row full' }, UI.h('label', {}, '附件'), file)),
          UI.h('div', { class: 'hint' }, '实收数量与订单数量偏差将计入结算；拒收将触发预警')), [
        UI.h('button', { class: 'primary', onclick: async () => {
          if (!arrived.value) { UI.toast('请填写实收数量', 'err'); return; }
          const body = { arrivedQty: arrived.value, conclusion: conclusion.value };
          if (indicators.value.trim()) body.indicators = indicators.value.trim();
          if (desc.value.trim()) body.checkDesc = desc.value.trim();
          try {
            if (file.files && file.files.length) {
              const up = await API.upload(file.files[0]);
              body.fileId = up.fileId != null ? up.fileId : up.id;
            }
            await API.post('/orders/' + oid + '/quality-check', body);
            m.close(); UI.toast('质检记录已保存', 'ok'); onDone();
          } catch (e) { /* toast 已提示 */ }
        } }, '保 存'),
        ], { wide: true });
      }

      function payModal(settle, onDone) {
        const amount = UI.input('number', settle.totalAmount, { placeholder: '付款金额' });
        const payDate = UI.input('date', new Date().toISOString().slice(0, 10));
        const desc = UI.h('textarea', { rows: 2, style: 'width:100%', placeholder: '付款说明' });
        const file = UI.h('input', { type: 'file', accept: 'image/*,.pdf' });
        const m = UI.modal('付款登记 · ' + (settle.settleNo || ''), UI.h('form', { onsubmit: (e) => e.preventDefault() },
          UI.h('div', { class: 'form-grid' },
            UI.formRow('付款金额', amount, true),
            UI.formRow('付款日期', payDate, true),
            UI.h('div', { class: 'form-row full' }, UI.h('label', {}, '付款说明'), desc),
            UI.h('div', { class: 'form-row full' }, UI.h('label', {}, '付款凭证'), file))), [
        UI.h('button', { class: 'primary', onclick: async () => {
          if (!amount.value) { UI.toast('请填写付款金额', 'err'); return; }
          const body = { amount: amount.value, payDate: payDate.value };
          if (desc.value.trim()) body.payDesc = desc.value.trim();
          try {
            if (file.files && file.files.length) {
              const up = await API.upload(file.files[0]);
              body.fileId = up.fileId != null ? up.fileId : up.id;
            }
            await API.post('/settlements/' + settle.id + '/payments', body);
            m.close(); UI.toast('付款已登记', 'ok'); onDone();
          } catch (e) { /* toast 已提示 */ }
        } }, '登 记'),
        ], { wide: true });
      }
      return;
    }

    /* -------- 供应商/双方：结算列表 -------- */
    let pageNo = 1;
    const SIZE = 10;
    const listCard = UI.h('div', { class: 'card' });
    const pagerBox = UI.h('div', {});
    page.appendChild(UI.h('div', { class: 'card' },
      UI.h('div', { class: 'toolbar' },
        UI.h('h3', { style: 'margin:0;border:none;padding:0' }, '结算单'),
        UI.h('div', { class: 'spacer' }),
        isSupplier ? UI.h('span', { class: 'hint' }, '待确认的结算请及时确认') : UI.h('span', {}))));
    page.appendChild(listCard);
    page.appendChild(pagerBox);

    async function load() {
      const d = await API.get('/settlements' + API.qs({ page: pageNo, size: SIZE }));
      listCard.innerHTML = '';
      listCard.appendChild(UI.table([
        { key: 'settleNo', label: '结算编号' },
        { key: 'orderNo', label: '订单号' },
        { key: 'settleQty', label: '结算数量', num: true, render: (r) => UI.fmtMoney(r.settleQty) },
        { key: 'totalAmount', label: '结算总额', num: true, render: (r) => UI.fmtMoney(r.totalAmount) },
        { key: 'status', label: '状态', render: (r) => UI.statusTag('SETTLEMENT', r.status) },
        { key: 'createdAt', label: '创建时间', render: (r) => UI.fmtDateTime(r.createdAt) },
        { label: '操作', render: (r) => acts(r) },
      ], d.list, '暂无结算单'));
      pagerBox.innerHTML = '';
      UI.pager(pagerBox, pageNo, SIZE, d.total, (p) => { pageNo = p; load(); });
    }

    function acts(r) {
      const btns = [UI.h('button', { class: 'sm', onclick: () => detail(r.id) }, '详情')];
      if (isSupplier && r.status === 'PENDING_CONFIRM_SUPPLIER') {
        btns.push(UI.h('button', { class: 'sm success', onclick: async () => {
          if (!(await UI.confirmBox('确认该结算单？'))) return;
          await API.put('/settlements/' + r.id + '/confirm');
          UI.toast('已确认', 'ok'); load();
        } }, '供应商确认'));
      }
      return UI.h('span', { class: 'inline-flex' }, ...btns);
    }

    async function detail(sid) {
      const d = await API.get('/settlements/' + sid);
      const s = d.settlement || d;
      const body = UI.h('div', {},
        UI.kv([
          ['结算编号', s.settle_no], ['状态', UI.statusTag('SETTLEMENT', s.status)],
          ['结算数量', UI.fmtMoney(s.settle_qty) + ' 吨'],
          ['调价金额', UI.fmtMoney(s.adjust_amount)],
          ['扣罚金额', UI.fmtMoney(s.deduct_amount)],
          ['结算总额', UI.h('b', {}, UI.fmtMoney(s.total_amount) + ' 元')],
          ['供应商确认', UI.fmtDateTime(s.supplier_confirm_at)],
          ['需方确认', UI.fmtDateTime(s.buyer_confirm_at)],
          ['结算说明', s.settle_desc, true],
        ]),
        UI.h('h3', { style: 'margin-top:14px' }, '付款记录'),
        UI.table([
          { key: 'paymentNo', label: '付款编号' },
          { key: 'amount', label: '金额', num: true, render: (r) => UI.fmtMoney(r.amount) },
          { key: 'payDate', label: '付款日期', render: (r) => UI.fmtDate(r.payDate) },
          { key: 'payDesc', label: '说明' },
          { label: '凭证', render: (r) => r.fileUrl ? UI.h('a', { href: 'javascript:;', onclick: () => API.downloadFile(r.fileUrl, '付款凭证-' + r.paymentNo) }, '附件') : '-' },
        ], d.payments || []));
      UI.modal('结算详情', body);
    }

    await load();
  };
})();
