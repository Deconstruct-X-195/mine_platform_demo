/* 企业信息维护（PRD T03/T04/Fr-01-06）+ 消息中心（PRD 4.10） */
(function () {
  window.Pages = window.Pages || {};

  /* -------- 企业信息维护 -------- */
  Pages.profile = async function (page, user) {
    const d = await API.get('/companies/me');
    // BUG-05 修复：后端 /companies/me 对企业用户返回平铺企业字段（顶层，另附
    // qualifications 列表），对平台管理员返回 {company: null, qualifications: []}。
    // 此前只读 d.company 嵌套结构，导致所有企业用户误判为"平台管理员无企业档案"。
    const c = d.company || (d.companyName || d.company_name ? d : null);
    if (!c) {
      page.appendChild(UI.h('div', { class: 'card' },
        UI.h('div', { class: 'empty' }, '平台管理员无企业档案，仅可使用运营后台功能')));
      return;
    }
    const qualCard = UI.h('div', { class: 'card' });
    page.appendChild(UI.h('div', { class: 'card' },
      UI.h('div', { class: 'toolbar' },
        UI.h('h3', { style: 'margin:0;border:none;padding:0' }, '企业信息'),
        UI.h('div', { class: 'spacer' }),
        UI.h('button', { class: 'primary', onclick: editForm }, '信息维护'))));
    page.appendChild(qualCard);
    page.appendChild(UI.h('div', { class: 'card' },
      UI.h('h3', {}, '资质证照'),
      UI.table([
        { key: 'fileName', label: '文件名称' },
        { key: 'fileType', label: '类型' },
        { key: 'createdAt', label: '上传时间', render: (r) => UI.fmtDateTime(r.createdAt) },
        { label: '操作', render: (r) => r.fileId ? UI.h('a', { href: 'javascript:;', onclick: () => API.downloadFile(r.fileId, r.fileName || '资质文件') }, '下载') : '-' },
      ], d.qualifications || [], '暂无资质文件')));
    await load();

    async function load() {
      qualCard.innerHTML = '';
      qualCard.appendChild(UI.h('h3', {}, '基本信息'));
      qualCard.appendChild(UI.kv([
        ['企业名称', c.companyName || c.company_name],
        ['统一社会信用代码', c.creditCode || c.credit_code],
        ['企业角色', c.companyTypes || c.company_types],
        ['审核状态', UI.statusTag('AUDIT', c.auditStatus || c.audit_status)],
        ['账号状态', c.status],
        ['所在省市', (c.province || c.province || '') + ' ' + (c.city || '')],
        ['法定代表人', c.legalPerson || c.legal_person],
        ['联系人', c.contactName || c.contact_name],
        ['联系电话', c.contactPhone || c.contact_phone],
        ['联系邮箱', c.contactEmail || c.contact_email],
        ['开户银行', c.bankName || c.bank_name],
        ['银行账户', c.bankAccount || c.bank_account],
        ['经营地址', c.address, true],
        ['经营范围', c.businessScope || c.business_scope, true],
      ]));
    }

    function editForm() {
      const companyName = UI.input('text', c.companyName || c.company_name || '', { placeholder: '请输入工商注册全称' });
      const creditCode = UI.input('text', c.creditCode || c.credit_code || '', { placeholder: '18 位字母数字，如 91130000XXXXXXXXXX' });
      const province = UI.input('text', c.province || '', { placeholder: '如：河北' });
      const city = UI.input('text', c.city || '', { placeholder: '如：邯郸市' });
      const address = UI.input('text', c.address || '', { placeholder: '省/市之后的具体经营地址' });
      const legalPerson = UI.input('text', c.legalPerson || c.legal_person || '', { placeholder: '选填' });
      const contactName = UI.input('text', c.contactName || c.contact_name || '', { placeholder: '请输入联系人姓名' });
      const contactPhone = UI.input('text', c.contactPhone || c.contact_phone || '', { placeholder: '11 位手机号' });
      const contactEmail = UI.input('text', c.contactEmail || c.contact_email || '', { placeholder: '如 name@company.com' });
      const bankName = UI.input('text', c.bankName || c.bank_name || '', { placeholder: '开户银行全称' });
      const bankAccount = UI.input('text', c.bankAccount || c.bank_account || '', { placeholder: '对公账户号码' });
      const businessScope = UI.h('textarea', { rows: 2, style: 'width:100%', placeholder: '如：铁矿石进口、销售' });
      const m = UI.modal('企业信息维护', UI.h('form', { onsubmit: (e) => e.preventDefault() },
        UI.h('div', { class: 'form-grid' },
          UI.formRow('企业名称', companyName, true),
          UI.formRow('统一社会信用代码', creditCode, true),
          UI.formRow('所在省份', province),
          UI.formRow('所在城市', city),
          UI.h('div', { class: 'form-row full' }, UI.h('label', {}, '经营地址'), address),
          UI.formRow('法定代表人', legalPerson),
          UI.formRow('联系人', contactName, true),
          UI.formRow('联系电话', contactPhone, true),
          UI.formRow('联系邮箱', contactEmail),
          UI.formRow('开户银行', bankName),
          UI.formRow('银行账户', bankAccount),
          UI.h('div', { class: 'form-row full' }, UI.h('label', {}, '经营范围'), businessScope))), [
        UI.h('button', { class: 'primary', onclick: async () => {
          const phone = contactPhone.value.trim();
          const email = contactEmail.value.trim();
          const code = creditCode.value.trim();
          if (!companyName.value.trim()) { UI.toast('请填写企业名称', 'err'); return; }
          if (code && !/^[0-9A-Z]{15,18}$/.test(code)) { UI.toast('统一社会信用代码应为 15~18 位大写字母或数字', 'err'); return; }
          if (phone && !/^1\d{10}$/.test(phone)) { UI.toast('联系电话应为 11 位手机号', 'err'); return; }
          if (email && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) { UI.toast('联系邮箱格式不正确，如 name@company.com', 'err'); return; }
          if (!contactName.value.trim()) { UI.toast('请填写联系人', 'err'); return; }
          try {
            const r = await API.put('/companies/me', {
              companyName: companyName.value.trim(), creditCode: creditCode.value.trim(),
              province: province.value.trim(), city: city.value.trim(), address: address.value.trim(),
              legalPerson: legalPerson.value.trim(), contactName: contactName.value.trim(),
              contactPhone: contactPhone.value.trim(), contactEmail: contactEmail.value.trim(),
              bankName: bankName.value.trim(), bankAccount: bankAccount.value.trim(),
              businessScope: businessScope.value.trim(),
            });
            m.close();
            if (r.keyChanged) {
              UI.toast('关键信息已变更，企业重新进入待审核', 'ok');
            } else {
              UI.toast('信息已保存', 'ok');
            }
            Object.assign(c, { companyName: c.companyName || c.company_name });
            setTimeout(() => location.reload(), 1200);
          } catch (e) { /* toast 已提示 */ }
        } }, '保 存'),
      ]);
    }
  };

  /* -------- 消息中心 -------- */
  Pages.messages = async function (page) {
    let pageNo = 1;
    const SIZE = 10;
    let isRead = '';
    const listCard = UI.h('div', { class: 'card' });
    const pagerBox = UI.h('div', {});
    /* 读取状态筛选：全部 / 未读 / 已读 */
    const readFilter = UI.h('select', { onchange: (e) => { isRead = e.target.value; pageNo = 1; load(); } },
      UI.h('option', { value: '' }, '全部'),
      UI.h('option', { value: '0' }, '未读'),
      UI.h('option', { value: '1' }, '已读'));
    /* 一键全读：当前企业全部未读消息批量标记为已读 */
    const readAllBtn = UI.h('button', { onclick: async () => {
      try {
        const r = await API.put('/messages/read-all');
        const n = r && r.updated != null ? Number(r.updated) : 0;
        UI.toast(n > 0 ? ('已将 ' + n + ' 条未读消息全部标记为已读') : '当前没有未读消息', 'ok');
        App.refreshMsgBadge();
        load();
      } catch (e) { /* toast 已提示 */ }
    } }, '一键全读');
    page.appendChild(UI.h('div', { class: 'card' },
      UI.h('div', { class: 'toolbar' },
        UI.h('h3', { style: 'margin:0;border:none;padding:0' }, '消息中心'),
        UI.h('div', { class: 'spacer' }),
        UI.h('label', { class: 'field' }, '状态', readFilter),
        readAllBtn)));
    page.appendChild(listCard);
    page.appendChild(pagerBox);
    await load();

    /* 消息表样式：仅标题+内容两列，宽度自适应面板，长内容自动换行 */
    if (!document.getElementById('msg-table-style')) {
      document.head.appendChild(UI.h('style', { id: 'msg-table-style' }, `
        table.msg-table { width: 100%; }
        table.msg-table th, table.msg-table td { white-space: normal; overflow-wrap: anywhere; }
        table.msg-table td.msg-title { width: 260px; }
        table.msg-table tbody tr { cursor: pointer; }
        table.msg-table tr.unread td.msg-title { font-weight: 700; }
        table.msg-table tr.unread td.msg-title::before { content: '●'; color: #e6a23c; margin-right: 6px; font-size: 10px; vertical-align: 2px; }
        table.msg-table td.msg-content { color: var(--label-2, #6e6e73); }
      `));
    }

    /* 按业务类型 + 当前角色跳转对应页面 */
    function jumpTarget(r) {
      const user = API.currentUser() || {};
      const roles = user.roles || [];
      const isPlat = roles.indexOf('PLAT_ADMIN') >= 0;
      const isCarrier = roles.indexOf('LOGISTICS_CARRIER') >= 0;
      const isSupplier = roles.indexOf('SUPPLIER') >= 0;
      const map = {
        COMPANY: isPlat ? '#/admin-companies' : '#/profile',
        DEMAND: isPlat ? '#/demand-pool' : (isSupplier ? '#/pool' : '#/demand'),
        INQUIRY: '#/inquiry',
        CONTRACT: isPlat ? '#/contract-admin' : '#/contract',
        ORDER: isPlat ? '#/logistics-dispatch' : '#/order',
        WAYBILL: isCarrier ? '#/waybill' : (isPlat ? '#/logistics-dispatch' : '#/track'),
      };
      return map[r.bizType] || '';
    }

    async function load() {
      const d = await API.get('/messages' + API.qs({ isRead, page: pageNo, size: SIZE }));
      listCard.innerHTML = '';
      const tbl = UI.table([
        { key: 'title', label: '标题', render: (r) => UI.h('span', { class: 'msg-title' }, r.title || '-') },
        { key: 'content', label: '内容', render: (r) => UI.h('span', { class: 'msg-content' }, r.content || '-') },
      ], d.list, '暂无消息');
      tbl.classList.add('msg-table');
      /* 点击消息：未读则标记已读（角标自动减少），并跳转对应页面 */
      tbl.querySelectorAll('tbody tr').forEach((tr, i) => {
        const r = d.list[i];
        if (!r) return;
        if (!r.isRead) tr.classList.add('unread');
        tr.title = '点击查看';
        tr.addEventListener('click', async () => {
          try {
            if (!r.isRead) {
              await API.put('/messages/' + r.id + '/read');
              r.isRead = 1;
              App.refreshMsgBadge();
            }
            const t = jumpTarget(r);
            if (t && t !== location.hash) location.hash = t;
          } catch (e) { /* toast 已提示 */ }
        });
      });
      listCard.appendChild(tbl);
      pagerBox.innerHTML = '';
      UI.pager(pagerBox, pageNo, SIZE, d.total, (p) => { pageNo = p; load(); });
    }
  };
})();
