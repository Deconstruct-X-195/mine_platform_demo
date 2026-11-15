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
    const name = c.companyName || c.company_name || '-';
    const code = c.creditCode || c.credit_code || '-';
    const audit = c.auditStatus || c.audit_status;
    /* 英文词段转中文：企业角色（支持多角色逗号分隔）与账号状态 */
    const ROLE_CN = { STEEL: '钢厂', SUPPLIER: '供应商', CARRIER: '承运商', PLAT_ADMIN: '平台管理员', PLATFORM: '平台管理员' };
    /* 资质类型中文名 */
    const QUAL_CN = { BUSINESS_LICENSE: '营业执照', OTHER: '其他资质' };
    const roleText = String(c.companyTypes || c.company_types || '').split(',')
      .map((s) => ROLE_CN[s.trim()] || s.trim()).filter(Boolean).join('、') || '-';
    const entTag = UI.statusTag('ENT', c.status);

    /* 顶部企业身份横幅：名称 + 信用代码 + 状态 tag + 信息维护入口 */
    page.appendChild(UI.h('div', { class: 'card profile-hero' },
      UI.h('div', {},
        UI.h('div', { class: 'profile-hero-name' }, name),
        UI.h('div', { class: 'profile-hero-meta' },
          UI.h('span', { class: 'wb-k' }, '统一社会信用代码 '),
          UI.h('span', { class: 'wb-v' }, code),
          UI.h('span', { class: 'wb-k' }, '企业角色 '),
          UI.h('span', { class: 'wb-v' }, roleText),
          UI.h('span', { class: 'wb-k' }, '账号状态 '),
          entTag)),
      UI.h('div', { class: 'spacer' }),
      UI.statusTag('AUDIT', audit),
      UI.h('button', { class: 'primary', onclick: editForm }, '信息维护')));

    /* 审核状态提示条：信息变更审核中显示专属文案 */
    const tips = {
      APPROVED: ['ok', '企业已通过准入审核，可正常参与平台业务。'],
      PENDING: ['warn', '企业准入审核中，审核通过前暂无法参与询价报价等业务。'],
      REJECTED: ['err', '准入审核未通过，请点击右上角「信息维护」完善企业信息后重新提交审核。'],
    };
    const pendingCh = d.pendingChanges || d.pending_changes;
    if (audit === 'PENDING' && pendingCh && Object.keys(pendingCh).length) {
      page.appendChild(UI.h('div', { class: 'banner warn' },
        '您提交的信息变更正在运营端审核中，当前展示的是变更前信息，审核通过后企业信息将自动更新。'));
    } else if (tips[audit]) {
      page.appendChild(UI.h('div', { class: 'banner ' + tips[audit][0] }, tips[audit][1]));
    }

    const infoCard = UI.h('div', { class: 'card' });
    page.appendChild(infoCard);
    const qualCard = UI.h('div', { class: 'card' });
    page.appendChild(qualCard);
    await load();
    await loadQual();

    async function loadQual() {
      qualCard.innerHTML = '';
      /* 面板内嵌自行上传：资质类型 + 文件选择 + 上传按钮，无需跳转其他页面 */
      const ftype = UI.selectField([['BUSINESS_LICENSE', '营业执照'], ['OTHER', '其他资质文件']], 'BUSINESS_LICENSE');
      const file = UI.h('input', { type: 'file', accept: '.pdf,.jpg,.jpeg,.png' });
      const fname = UI.h('span', { class: 'hint' }, '未选择文件');
      file.addEventListener('change', () => {
        const f = (file.files || [])[0];
        fname.textContent = f ? f.name + '（' + Math.max(1, Math.ceil(f.size / 1024)) + ' KB）' : '未选择文件';
      });
      const upBtn = UI.h('button', { class: 'primary', onclick: async () => {
        if (!file.files || !file.files[0]) { UI.toast('请选择要上传的文件', 'err'); return; }
        upBtn.disabled = true;
        try {
          const up = await API.upload(file.files[0], '/files');
          await API.post('/companies/me/qualifications', { fileId: up.fileId, fileType: ftype.value });
          file.value = '';
          fname.textContent = '未选择文件';
          UI.toast('资质文件已上传', 'ok');
          const fresh = await API.get('/companies/me');
          d.qualifications = fresh.qualifications || [];
          await loadQual();
        } catch (e) { /* toast 已提示 */ }
        upBtn.disabled = false;
      } }, '上传');
      qualCard.appendChild(UI.h('div', { class: 'toolbar' },
        UI.h('h3', { style: 'margin:0;border:none;padding:0' }, '资质证照')));
      qualCard.appendChild(UI.h('div', { class: 'inline-flex', style: 'gap:10px;flex-wrap:wrap;align-items:center' },
        UI.h('span', { class: 'wb-k' }, '资质类型'), ftype,
        file, fname, UI.h('span', { class: 'spacer' }), upBtn));
      qualCard.appendChild(UI.table([
        { key: 'fileName', label: '文件名称' },
        { label: '类型', render: (r) => QUAL_CN[r.fileType] || r.fileType || '-' },
        { key: 'createdAt', label: '上传时间', render: (r) => UI.fmtDateTime(r.createdAt) },
        { label: '操作', render: (r) => r.fileId ? UI.h('span', {},
          UI.h('a', { href: 'javascript:;', onclick: () => window.previewFile(r.fileId, r.fileName || '资质文件') }, '预览'),
          ' / ',
          UI.h('a', { href: 'javascript:;', onclick: () => API.downloadFile(r.fileId, r.fileName || '资质文件') }, '下载')) : '-' },
      ], d.qualifications || [], '暂无资质文件（在上方选择文件并点击「上传」提交营业执照等证照）'));
    }

    async function load() {
      infoCard.innerHTML = '';
      infoCard.appendChild(UI.h('h3', {}, '基本信息'));
      infoCard.appendChild(UI.h('div', { class: 'sec-title' }, '注册信息'));
      infoCard.appendChild(UI.kv([
        ['企业角色', roleText],
        ['审核状态', UI.statusTag('AUDIT', audit)],
        ['账号状态', entTag],
        ['所在省市', (c.province || '') + ' ' + (c.city || '')],
      ]));
      infoCard.appendChild(UI.h('div', { class: 'sec-title' }, '联系信息'));
      infoCard.appendChild(UI.kv([
        ['法定代表人', c.legalPerson || c.legal_person],
        ['联系人', c.contactName || c.contact_name],
        ['联系电话', c.contactPhone || c.contact_phone],
        ['联系邮箱', c.contactEmail || c.contact_email],
        ['经营地址', c.address, true],
      ]));
      infoCard.appendChild(UI.h('div', { class: 'sec-title' }, '银行与经营'));
      infoCard.appendChild(UI.kv([
        ['开户银行', c.bankName || c.bank_name],
        ['银行账户', c.bankAccount || c.bank_account],
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
      businessScope.value = c.businessScope || c.business_scope || '';
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
            if (r.changePending) {
              UI.toast('信息变更已提交运营端，审核通过后自动更新', 'ok');
            } else if (r.keyChanged) {
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

  /* -------- 消息中心（左侧栏：任务=待办任务；消息=全部/通知/预警/公告/活动信息） -------- */
  /* 按业务类型 + 当前角色跳转对应页面（抽屉与消息中心共用） */
  window.msgJumpTarget = function (r) {
    const user = API.currentUser() || {};
    const roles = user.roles || [];
    const isPlat = roles.indexOf('PLAT_ADMIN') >= 0;
    const isSupplier = roles.indexOf('SUPPLIER') >= 0;
    const map = {
      COMPANY: isPlat ? '#/admin-companies' : '#/profile',
      DEMAND: isPlat ? '#/demand-pool' : (isSupplier ? '#/inquiry' : '#/demand'),
      INQUIRY: '#/inquiry',
      /* 合同面板已下线，合同类消息均跳转至订单相关页面 */
      CONTRACT: isPlat ? '#/logistics-dispatch' : '#/order',
      ORDER: isPlat ? '#/logistics-dispatch' : '#/order',
      WAYBILL: isPlat ? '#/logistics-dispatch' : '#/track',
    };
    return map[r.bizType] || '';
  };
  const MSG_CAT_LABEL = { NOTICE: '通知', WARN: '预警', ANNOUNCE: '公告', ACTIVITY: '活动' };
  const TASK_TYPE_LABEL = {
    CONTRACT: '合同', COMPANY: '企业准入', WAYBILL: '运单',
    ORDER: '订单', SETTLEMENT: '结算', INQUIRY: '询价',
    DEMAND: '需求', ALERT: '预警',
  };

  Pages.messages = async function (page) {
    let pageNo = 1;
    const SIZE = 10;
    let section = 'task';            // 'task' 或 'msg:分类'（空=全部）
    let taskBox = 'todo';            // todo 待办 / done 已办 / doing 在办申请 / applied 已办申请
    const TASK_BOXES = [['todo', '待办任务'], ['done', '已办任务'], ['doing', '在办申请'], ['applied', '已办申请']];
    const TASK_BOX_TITLE = { todo: '待办任务', done: '已办任务', doing: '在办申请', applied: '已办申请' };
    const side = UI.h('div', { class: 'msg-side' });
    const main = UI.h('div', { class: 'msg-main' });
    /* 左侧栏顶部：任务 / 消息 页签（与分类列表同卡片） */
    const tabBtnTask = UI.h('button', { class: 'msg-tab active', 'data-mtab': 'task', onclick: () => pick('task') }, '任务');
    const tabBtnMsg = UI.h('button', { class: 'msg-tab', 'data-mtab': 'msg', onclick: () => pick('msg:') }, '消息');
    const sideGroups = UI.h('div', { class: 'msg-side-groups' });
    side.appendChild(UI.h('div', { class: 'msg-tabs' }, tabBtnTask, tabBtnMsg));
    side.appendChild(sideGroups);
    page.appendChild(UI.h('div', { class: 'msg-center' }, side, main));

    /* 消息表样式：仅标题+内容两列，宽度自适应面板，长内容自动换行；内容左对齐（仅消息中心） */
    if (!document.getElementById('msg-table-style')) {
      document.head.appendChild(UI.h('style', { id: 'msg-table-style' }, `
        table.msg-table { width: 100%; }
        table.msg-table th, table.msg-table td { white-space: normal; overflow-wrap: anywhere; text-align: left; }
        .msg-main table.grid th, .msg-main table.grid td { text-align: left; line-height: 1.8; }
        table.msg-table td.msg-title { width: 260px; }
        table.msg-table tbody tr { cursor: pointer; }
        table.msg-table tr.unread td.msg-title { font-weight: 700; }
        table.msg-table tr.unread td.msg-title::before { content: '●'; color: #e6a23c; margin-right: 6px; font-size: 10px; vertical-align: 2px; }
        table.msg-table td.msg-content { color: var(--label-2, #6e6e73); line-height: 1.9; }
      `));
    }

    function buildSide() {
      sideGroups.innerHTML = '';
      if (section === 'task') {
        /* 任务页签：待办任务 / 已办任务 / 在办申请 / 已办申请 */
        sideGroups.appendChild(UI.h('div', { class: 'msg-side-group' },
          UI.h('div', { class: 'msg-side-title' }, '任务办理'),
          TASK_BOXES.map(([val, label]) => UI.h('div', {
            class: 'msg-side-item' + (taskBox === val ? ' active' : ''),
            onclick: () => { taskBox = val; pageNo = 1; buildSide(); renderTasks(); },
          }, label))));
      } else {
        const cats = [['', '全部消息'], ['NOTICE', '通知'], ['WARN', '预警'], ['ANNOUNCE', '公告'], ['ACTIVITY', '活动信息']];
        sideGroups.appendChild(UI.h('div', { class: 'msg-side-group' },
          UI.h('div', { class: 'msg-side-title' }, '消息分类'),
          cats.map(([val, label]) => UI.h('div', {
            class: 'msg-side-item' + (section === 'msg:' + val ? ' active' : ''),
            onclick: () => pick('msg:' + val),
          }, label))));
      }
    }

    function pick(s) {
      section = s;
      pageNo = 1;
      /* 页签高亮 + 侧栏内容随页签切换 */
      const isTask = s === 'task';
      tabBtnTask.classList.toggle('active', isTask);
      tabBtnMsg.classList.toggle('active', !isTask);
      buildSide();
      if (isTask) renderTasks();
      else renderMessages();
    }

    /* ---- 任务（待办/已办/在办申请/已办申请） ---- */
    const TASK_SIZE = 10;
    async function renderTasks() {
      main.innerHTML = '';
      const listCard = UI.h('div', { class: 'card msg-fill' });
      main.appendChild(UI.h('div', { class: 'card' },
        UI.h('div', { class: 'toolbar' },
          UI.h('h3', { style: 'margin:0;border:none;padding:0' }, TASK_BOX_TITLE[taskBox] || '任务'))));
      main.appendChild(listCard);
      listCard.innerHTML = '<div class="empty">加载中…</div>';
      try {
        const d = await API.get('/tasks/todos' + API.qs({ box: taskBox }));
        const list = d.list || [];
        /* 客户端分页：每页 10 条，分页条贴卡片底部（与消息列表一致） */
        const render = () => {
          listCard.innerHTML = '';
          const start = (pageNo - 1) * TASK_SIZE;
          const tbl = UI.table([
            { key: 'title', label: '事项' },
            { label: '业务类型', render: (r) => TASK_TYPE_LABEL[r.bizType] || r.bizType || '-' },
            { key: 'createdAt', label: '时间', render: (r) => UI.fmtDateTime(r.createdAt) },
            { label: '操作', render: (r) => r.hash ? UI.h('button', {
                class: 'sm',
                onclick: () => { if (r.hash !== location.hash) location.hash = r.hash; },
              }, taskBox === 'todo' ? '去处理' : '查看') : '-' },
          ], list.slice(start, start + TASK_SIZE), '暂无数据');
          listCard.appendChild(tbl);
          const pagerBox = UI.h('div', { style: 'margin-top:auto;padding-top:10px' });
          UI.pager(pagerBox, pageNo, TASK_SIZE, list.length, (p) => { pageNo = p; render(); });
          listCard.appendChild(pagerBox);
        };
        render();
      } catch (e) {
        listCard.innerHTML = '';
        listCard.appendChild(UI.h('div', { class: 'empty' }, '加载失败：' + (e.message || e)));
      }
    }

    /* ---- 消息列表（按分类） ---- */
    async function renderMessages() {
      const cat = section.slice(4);           // 'msg:' 之后的分类值
      const catLabel = cat ? MSG_CAT_LABEL[cat] : '全部消息';
      const listCard = UI.h('div', { class: 'card msg-fill' });
      main.innerHTML = '';
      main.appendChild(UI.h('div', { class: 'card' },
        UI.h('div', { class: 'toolbar' },
          UI.h('h3', { style: 'margin:0;border:none;padding:0' }, catLabel))));
      main.appendChild(listCard);
      await load();

      async function load() {
        const d = await API.get('/messages' + API.qs({ category: cat, page: pageNo, size: SIZE }));
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
              const t = window.msgJumpTarget(r);
              if (t && t !== location.hash) location.hash = t;
            } catch (e) { /* toast 已提示 */ }
          });
        });
        listCard.appendChild(tbl);
        /* 分页条放入列表卡片底部：卡片底边与面板底边保持对齐 */
        const pagerBox = UI.h('div', { style: 'margin-top:auto;padding-top:10px' });
        UI.pager(pagerBox, pageNo, SIZE, d.total, (p) => { pageNo = p; load(); });
        listCard.appendChild(pagerBox);
      }
    }

    buildSide();
    await pick(section);
  };
})();
