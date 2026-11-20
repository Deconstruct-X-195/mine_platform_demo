/* 登录 / 注册（PRD 4.1/FR-01）：演示账号预填、企业注册（角色严格单选 + 省份搜索选择 + 宽卡布局） */
(function () {
  window.Pages = window.Pages || {};

  Pages.login = function (box, _user) {
    /* 浏览器自动记录上次登录的手机号：再次进入登录页自动回填，密码仍需手动输入 */
    const username = UI.input('text', localStorage.getItem('mine_last_username') || '',
      { placeholder: '请输入 11 位手机号' });
    const password = UI.input('password', '', { placeholder: '请输入登录密码' });
    const submit = async () => {
      if (submitBtn.disabled) return; /* 防重复提交 */
      submitBtn.disabled = true;
      submitBtn.textContent = '登录中…';
      try {
        const data = await API.post('/auth/login', {
          username: username.value.trim(), password: password.value,
        });
        localStorage.setItem('mine_last_username', username.value.trim());
        API.saveAuth(data.token, data.user);
        UI.toast('登录成功', 'ok');
        location.hash = App.homeFor(data.user);
        App.route();
      } catch (e) { /* toast 已提示 */
      } finally {
        submitBtn.disabled = false;
        submitBtn.textContent = '登 录';
      }
    };
    const submitBtn = UI.h('button', { class: 'primary', style: 'width:100%', onclick: submit }, '登 录');
    box.appendChild(UI.h('div', { class: 'auth-card' },
      UI.h('div', { class: 'auth-brand' },
        UI.h('div', { class: 'auth-mark', 'aria-hidden': 'true' }),
        UI.h('h1', {}, '大宗矿产集采平台')),
      UI.h('label', { class: 'auth-field' },
        UI.h('span', { class: 'auth-label' }, '手机号'), username),
      UI.h('label', { class: 'auth-field' },
        UI.h('span', { class: 'auth-label' }, '密码'), password),
      submitBtn,
      UI.h('div', { class: 'switch' },
        '还没有账号？', UI.h('a', { href: '#/register' }, '企业注册'))));
    password.addEventListener('keyup', (e) => { if (e.key === 'Enter') submit(); });
    username.addEventListener('keyup', (e) => { if (e.key === 'Enter') submit(); });
  };

  const TYPES = [['STEEL_BUYER', '钢铁企业（需方）'], ['SUPPLIER', '供应商（供方）']];
  const ROLE_DESC = {
    STEEL_BUYER: '采购铁矿石等大宗原料，发起需求与询价',
    SUPPLIER: '参与密封报价、议价与合同签订',
  };
  Pages.register = function (box) {
    const f = {};
    const field = (key, label, props, required) => {
      f[key] = UI.input('text', '', Object.assign({ placeholder: label }, props || {}));
      return UI.formRow(label, f[key], required);
    };

    /* 企业角色：radio 严格单选——原生 radio 天然互斥，选中态加 .on 视觉反馈 */
    const roleCards = TYPES.map(([code, name]) => {
      const radio = UI.h('input', { type: 'radio', name: 'companyType', value: code });
      const card = UI.h('label', { class: 'role-card', 'data-code': code },
        UI.h('span', { class: 'role-name' }, name),
        UI.h('span', { class: 'role-desc' }, ROLE_DESC[code]),
        UI.h('span', { class: 'role-check' }, '✓'),
        radio);
      /* 不依赖事件顺序：change 后按各 radio 实际 checked 状态同步高亮（radio 切换时新旧两个
         change 的触发次序因浏览器而异，逐个按 checked 状态刷新可保证最终态永远正确） */
      radio.addEventListener('change', () => {
        roleCards.forEach((c) => {
          const r = c.querySelector('input');
          if (r.checked) { c.classList.add('on'); } else { c.classList.remove('on'); }
        });
      });
      return card;
    });

    /* 营业执照：选择后进入下方文件框，可删除、点击文件名预览；再次选择替换当前文件 */
    let licenseFile = null;
    const license = UI.h('input', { type: 'file', accept: 'image/*,.pdf' });
    const uploadBox = UI.h('div', { class: 'upload-box', style: 'display:none' });
    const fmtSize = (n) => (n >= 1024 * 1024 ? (n / 1024 / 1024).toFixed(1) + ' MB' : Math.max(1, Math.round(n / 1024)) + ' KB');
    const previewLicense = (file) => {
      const url = URL.createObjectURL(file);
      const isPdf = file.type === 'application/pdf' || /\.pdf$/i.test(file.name);
      const body = isPdf
        ? UI.h('iframe', { src: url, style: 'width:100%;height:70vh;border:1px solid var(--separator);background:#fff' })
        : UI.h('img', { src: url, style: 'max-width:100%;max-height:70vh;display:block;margin:0 auto' });
      UI.modal('营业执照预览 · ' + file.name, body, null, { wide: true });
      setTimeout(() => URL.revokeObjectURL(url), 10 * 60 * 1000); // 兜底回收预览 URL
    };
    const renderUpload = () => {
      uploadBox.innerHTML = '';
      if (!licenseFile) { uploadBox.style.display = 'none'; return; }
      uploadBox.style.display = '';
      uploadBox.appendChild(UI.h('div', { class: 'upload-item' },
        UI.h('a', { class: 'upload-name', title: '点击预览', href: 'javascript:;', onclick: () => previewLicense(licenseFile) }, licenseFile.name),
        UI.h('span', { class: 'upload-size' }, fmtSize(licenseFile.size)),
        UI.h('a', { class: 'upload-del', href: 'javascript:;', onclick: () => { licenseFile = null; renderUpload(); } }, '删除')));
    };
    license.addEventListener('change', () => {
      const file = license.files && license.files[0];
      if (!file) return;
      licenseFile = file;
      renderUpload();
      license.value = ''; // 允许再次选择同一文件替换
    });
    const form = UI.h('form', { onsubmit: (e) => e.preventDefault() },
      UI.h('div', { class: 'sec' }, '企业信息'),
      UI.h('div', { class: 'form-grid' },
        field('companyName', '企业名称', { placeholder: '请输入工商注册全称' }, true),
        field('creditCode', '统一社会信用代码', { placeholder: '18 位字母数字，如 91130000XXXXXXXXXX' }, true),
        UI.h('div', { class: 'form-row full' },
          UI.h('label', { class: 'req' }, '企业角色（仅可选择一个）'),
          UI.h('div', { class: 'role-grid' }, ...roleCards)),
        field('legalPerson', '法定代表人', { placeholder: '请输入法定代表人姓名' }, true),
        field('address', '注册地址', { placeholder: '请输入注册详细地址' }, true),
        UI.h('div', { class: 'form-row full' },
          UI.h('label', {}, '经营范围'),
          UI.h('textarea', { rows: 2, style: 'width:100%', placeholder: '选填，如：铁矿石进口、销售', onchange: (e) => { f.businessScope = e.target.value; } }))),
      UI.h('div', { class: 'sec' }, '联系信息'),
      UI.h('div', { class: 'form-grid' },
        field('contactName', '联系人', { placeholder: '请输入联系人姓名' }, true),
        field('contactPhone', '联系电话', { placeholder: '11 位手机号' }, true),
        field('contactEmail', '联系邮箱', { placeholder: '选填，如 name@company.com' })),
      UI.h('div', { class: 'sec' }, '账号与营业执照'),
      UI.h('div', { class: 'form-grid' },
        field('username', '登录账号（11 位手机号）', { placeholder: '设置登录手机号，11 位' }, true),
        field('password', '密码（至少 8 位）', { type: 'password', placeholder: '至少 8 位，建议字母与数字组合' }, true),
        UI.h('div', { class: 'form-row full' },
          UI.h('label', { class: 'req' }, '营业执照'),
          license, UI.h('div', { class: 'hint' }, '支持图片 / PDF，选择后可在下方查看文件'),
          uploadBox)));

    box.appendChild(UI.h('div', { class: 'auth-card wide' },
      UI.h('div', { class: 'auth-brand' },
        UI.h('div', { class: 'auth-mark', 'aria-hidden': 'true' }),
        UI.h('div', {},
          UI.h('h1', {}, '企业注册'),
          UI.h('p', { class: 'auth-tagline' }, '注册后需平台准入审核通过方可使用业务功能'))),
      form,
      UI.h('button', {
        class: 'primary', style: 'width:100%',
        onclick: async () => {
          /* 提交时直接以 DOM 勾选态为准（原生 radio :checked 单一真源，杜绝闭包与事件时序偏差） */
          const checkedRole = form.querySelector('input[name="companyType"]:checked');
          const body = {
            companyName: f.companyName.value.trim(),
            creditCode: f.creditCode.value.trim(),
            companyTypes: checkedRole ? checkedRole.value : '',
            address: f.address.value.trim(),
            legalPerson: f.legalPerson.value.trim(),
            contactName: f.contactName.value.trim(),
            contactPhone: f.contactPhone.value.trim(),
            contactEmail: f.contactEmail.value.trim(),
            businessScope: f.businessScope || '',
            username: f.username.value.trim(),
            password: f.password.value,
          };
          if (!body.companyName || !body.creditCode || !body.companyTypes || !body.address || !body.legalPerson) {
            UI.toast('企业名称、信用代码、企业角色、注册地址、法定代表人为必填（角色仅可选择一个）', 'err');
            return;
          }
          if (!/^[0-9A-Z]{15,18}$/.test(body.creditCode)) { UI.toast('统一社会信用代码应为 15~18 位大写字母或数字', 'err'); return; }
          if (!/^1\d{10}$/.test(body.username)) { UI.toast('登录账号必须为 11 位手机号', 'err'); return; }
          if (!body.password || body.password.length < 8) { UI.toast('密码至少 8 位', 'err'); return; }
          if (!body.contactName || !body.contactPhone) { UI.toast('联系人与联系电话为必填', 'err'); return; }
          if (!/^1\d{10}$/.test(body.contactPhone)) { UI.toast('联系电话应为 11 位手机号', 'err'); return; }
          if (body.contactEmail && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(body.contactEmail)) { UI.toast('联系邮箱格式不正确，如 name@company.com', 'err'); return; }
          if (!licenseFile) { UI.toast('请上传营业执照', 'err'); return; }
          try {
            const up = await API.upload(licenseFile, '/auth/license');
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
