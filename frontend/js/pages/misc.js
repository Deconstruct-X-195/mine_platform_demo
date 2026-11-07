/* 企业信息维护（PRD T03/T04/Fr-01-06）+ 消息中心（PRD 4.10） */
(function () {
  window.Pages = window.Pages || {};

  /* -------- 企业信息维护 -------- */
  Pages.profile = async function (page, user) {
    const d = await API.get('/companies/me');
    const c = d.company;
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
      const companyName = UI.input('text', c.companyName || c.company_name || '');
      const creditCode = UI.input('text', c.creditCode || c.credit_code || '');
      const province = UI.input('text', c.province || '');
      const city = UI.input('text', c.city || '');
      const address = UI.input('text', c.address || '');
      const legalPerson = UI.input('text', c.legalPerson || c.legal_person || '');
      const contactName = UI.input('text', c.contactName || c.contact_name || '');
      const contactPhone = UI.input('text', c.contactPhone || c.contact_phone || '');
      const contactEmail = UI.input('text', c.contactEmail || c.contact_email || '');
      const bankName = UI.input('text', c.bankName || c.bank_name || '');
      const bankAccount = UI.input('text', c.bankAccount || c.bank_account || '');
      const businessScope = UI.h('textarea', { rows: 2, style: 'width:100%', placeholder: '经营范围' });
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
          if (!companyName.value.trim()) { UI.toast('请填写企业名称', 'err'); return; }
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
    page.appendChild(UI.h('div', { class: 'card' },
      UI.h('div', { class: 'toolbar' },
        UI.h('h3', { style: 'margin:0;border:none;padding:0' }, '消息中心'),
        UI.h('div', { class: 'spacer' }),
        UI.statusFilter('MSG', (v) => { isRead = v; pageNo = 1; load(); }))));
    page.appendChild(listCard);
    page.appendChild(pagerBox);
    await load();

    async function load() {
      const d = await API.get('/messages' + API.qs({ isRead, page: pageNo, size: SIZE }));
      listCard.innerHTML = '';
      listCard.appendChild(UI.table([
        { key: 'title', label: '标题' },
        { key: 'content', label: '内容', full: true },
        { key: 'bizType', label: '业务对象' },
        { key: 'isRead', label: '已读', render: (r) => r.isRead ? UI.h('span', { class: 'tag' }, '已读') : UI.h('span', { class: 'tag orange' }, '未读') },
        { key: 'createdAt', label: '时间', render: (r) => UI.fmtDateTime(r.createdAt) },
        { label: '操作', render: (r) => r.isRead ? '-' : UI.h('button', { class: 'sm', onclick: async () => {
          await API.put('/messages/' + r.id + '/read');
          UI.toast('已标记已读', 'ok'); load();
        } }, '标已读') },
      ], d.list, '暂无消息'));
      pagerBox.innerHTML = '';
      UI.pager(pagerBox, pageNo, SIZE, d.total, (p) => { pageNo = p; load(); });
    }
  };
})();
