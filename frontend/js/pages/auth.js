/* 登录 / 注册（PRD 4.1/FR-01）：演示账号预填、企业注册（营业执照上传） */
(function () {
  window.Pages = window.Pages || {};

  Pages.login = function (box, _user) {
    const username = UI.input('text', '', { placeholder: '手机号 / 用户名' });
    const password = UI.input('password', '', { placeholder: '密码' });
    const submit = async () => {
      try {
        const data = await API.post('/auth/login', {
          username: username.value.trim(), password: password.value,
        });
        API.saveAuth(data.token, data.user);
        UI.toast('登录成功', 'ok');
        location.hash = App.homeFor(data.user);
        App.route();
      } catch (e) { /* toast 已提示 */ }
    };
    box.appendChild(UI.h('div', { class: 'auth-card' },
      UI.h('h1', {}, '大宗矿产集采平台'),
      UI.h('div', { class: 'sub' }, '一期演示环境 · PC 端'),
      username,
      password,
      UI.h('button', { class: 'primary', style: 'width:100%', onclick: submit }, '登 录'),
      UI.h('div', { class: 'switch' },
        '还没有账号？', UI.h('a', { href: '#/register' }, '企业注册')),
      UI.h('div', { class: 'hint', style: 'margin-top:14px' },
        '演示账号：供应商 13900000001 / 钢厂 13900000002 / 承运商 13900000003（密码 demo123456）；平台 13800000000 / admin123456')));
    password.addEventListener('keyup', (e) => { if (e.key === 'Enter') submit(); });
    username.addEventListener('keyup', (e) => { if (e.key === 'Enter') submit(); });
  };

  const TYPES = [['STEEL_BUYER', '钢厂（需方）'], ['SUPPLIER', '供应商（供方）'], ['LOGISTICS_CARRIER', '承运商']];
  const PROVINCES = ['河北', '山东', '辽宁', '江苏', '浙江', '广东', '福建', '广西', '上海', '天津', '其他'];

  Pages.register = function (box) {
    const f = {};
    const field = (key, label, props, required) => {
      f[key] = UI.input('text', '', Object.assign({ placeholder: label }, props || {}));
      return UI.formRow(label, f[key], required);
    };
    const typeBoxes = TYPES.map(([code, name]) =>
      UI.h('label', { class: 'field' },
        UI.h('input', { type: 'checkbox', value: code, style: 'width:auto' }), name));
    const license = UI.h('input', { type: 'file', accept: 'image/*,.pdf' });
    const form = UI.h('form', { onsubmit: (e) => e.preventDefault() },
      UI.h('div', { class: 'form-grid' },
        field('companyName', '企业名称', {}, true),
        field('creditCode', '统一社会信用代码', {}, true),
        UI.h('div', { class: 'form-row full' },
          UI.h('label', { class: 'req' }, '企业角色'), UI.h('div', { class: 'inline-flex' }, ...typeBoxes)),
        UI.h('div', { class: 'form-row' },
          UI.h('label', { class: 'req' }, '省份'),
          UI.selectField(PROVINCES.map((p) => [p, p]), '河北', { onchange: (e) => { f.province = e.target.value; } })),
        field('city', '城市', {}, true),
        field('address', '详细地址'),
        field('legalPerson', '法定代表人'),
        field('contactName', '联系人', {}, true),
        field('contactPhone', '联系电话', {}, true),
        field('contactEmail', '联系邮箱'),
        field('bankName', '开户银行'),
        field('bankAccount', '银行账号'),
        UI.h('div', { class: 'form-row full' },
          UI.h('label', {}, '经营范围'),
          UI.h('textarea', { rows: 2, style: 'width:100%', onchange: (e) => { f.businessScope = e.target.value; } })),
        field('username', '登录账号（11 位手机号）', {}, true),
        field('password', '密码（至少 8 位）', { type: 'password' }, true),
        UI.h('div', { class: 'form-row full' },
          UI.h('label', { class: 'req' }, '营业执照'),
          license, UI.h('div', { class: 'hint' }, '支持图片 / PDF'))));
    f.province = '河北';
    box.appendChild(UI.h('div', { class: 'auth-card', style: 'width:520px' },
      UI.h('h1', {}, '企业注册'),
      UI.h('div', { class: 'sub' }, '注册后需平台准入审核通过方可使用业务功能'),
      form,
      UI.h('button', {
        class: 'primary', style: 'width:100%',
        onclick: async () => {
          const body = {
            companyName: f.companyName.value.trim(),
            creditCode: f.creditCode.value.trim(),
            companyTypes: TYPES
              .map(([code], i) => (typeBoxes[i].querySelector('input').checked ? code : null))
              .filter(Boolean).join(','),
            province: f.province,
            city: f.city.value.trim(),
            address: f.address.value.trim(),
            legalPerson: f.legalPerson.value.trim(),
            contactName: f.contactName.value.trim(),
            contactPhone: f.contactPhone.value.trim(),
            contactEmail: f.contactEmail.value.trim(),
            bankName: f.bankName.value.trim(),
            bankAccount: f.bankAccount.value.trim(),
            businessScope: f.businessScope || '',
            username: f.username.value.trim(),
            password: f.password.value,
          };
          if (!body.companyName || !body.creditCode || !body.companyTypes) { UI.toast('企业名称、信用代码、企业角色为必填', 'err'); return; }
          if (!/^1\d{10}$/.test(body.username)) { UI.toast('登录账号必须为 11 位手机号', 'err'); return; }
          if (!body.password || body.password.length < 8) { UI.toast('密码至少 8 位', 'err'); return; }
          if (!body.contactName || !body.contactPhone) { UI.toast('联系人与联系电话为必填', 'err'); return; }
          if (!license.files || !license.files.length) { UI.toast('请上传营业执照', 'err'); return; }
          try {
            const up = await API.upload(license.files[0], '/auth/license');
            body.licenseFileId = up.fileId != null ? up.fileId : up.id;
            const res = await API.post('/auth/register', body);
            UI.toast('注册成功，等待平台审核（企业 ' + res.companyId + '）', 'ok');
            location.hash = '#/login';
            App.route();
          } catch (e) { /* toast 已提示 */ }
        },
      }, '提交注册'),
      UI.h('div', { class: 'switch' }, '已有账号？', UI.h('a', { href: '#/login' }, '去登录'))));
  };
})();
