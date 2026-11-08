/* 登录 / 注册（PRD 4.1/FR-01）：演示账号预填、企业注册（角色严格单选 + 省份搜索选择 + 宽卡布局） */
(function () {
  window.Pages = window.Pages || {};

  Pages.login = function (box, _user) {
    const username = UI.input('text', '', { placeholder: '请输入 11 位手机号' });
    const password = UI.input('password', '', { placeholder: '请输入登录密码' });
    const submit = async () => {
      if (submitBtn.disabled) return; /* 防重复提交 */
      submitBtn.disabled = true;
      submitBtn.textContent = '登录中…';
      try {
        const data = await API.post('/auth/login', {
          username: username.value.trim(), password: password.value,
        });
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

  const TYPES = [['STEEL_BUYER', '钢厂（需方）'], ['SUPPLIER', '供应商（供方）'], ['LOGISTICS_CARRIER', '承运商']];
  const ROLE_DESC = {
    STEEL_BUYER: '采购铁矿石等大宗原料，发起需求与询价',
    SUPPLIER: '参与密封报价、议价与合同签订',
    LOGISTICS_CARRIER: '承接物流方案与运单作业',
  };
  /* 全国 34 个省级行政区（六大区 + 港澳台标准排序），末位保留兼容项“其他” */
  const PROVINCE_GROUPS = [
    ['华北地区', ['北京', '天津', '河北', '山西', '内蒙古']],
    ['东北地区', ['辽宁', '吉林', '黑龙江']],
    ['华东地区', ['上海', '江苏', '浙江', '安徽', '福建', '江西', '山东']],
    ['中南地区', ['河南', '湖北', '湖南', '广东', '广西', '海南']],
    ['西南地区', ['重庆', '四川', '贵州', '云南', '西藏']],
    ['西北地区', ['陕西', '甘肃', '青海', '宁夏', '新疆']],
    ['港澳台', ['香港', '澳门', '台湾']],
  ];

  /* 省份搜索选择器：聚焦展开并清空输入、实时过滤、Enter 选首项、Esc/失焦还原 */
  function provincePicker(initial, onPick) {
    const ALL = [];
    PROVINCE_GROUPS.forEach(([g, list]) => list.forEach((n) => ALL.push([g, n])));
    ALL.push(['', '其他']);
    let value = initial;
    const panel = UI.h('div', { class: 'prov-panel', style: 'display:none' });
    const input = UI.h('input', { type: 'text', autocomplete: 'off', placeholder: '搜索或选择省份' });
    const wrap = UI.h('div', { class: 'prov' }, input, panel);

    const pick = (n) => {
      value = n;
      input.value = n;
      panel.style.display = 'none';
      onPick(n);
    };
    const render = () => {
      const kw = input.value.trim();
      panel.innerHTML = '';
      const items = kw ? ALL.filter(([, n]) => n.indexOf(kw) >= 0) : ALL;
      if (!items.length) {
        panel.appendChild(UI.h('div', { class: 'prov-empty' }, '未找到匹配省份'));
        return;
      }
      let lastG = null;
      items.forEach(([g, n]) => {
        if (!kw && g && g !== lastG) { panel.appendChild(UI.h('div', { class: 'prov-group' }, g)); lastG = g; }
        const it = UI.h('div', { class: 'prov-item' + (n === value ? ' on' : ''), 'data-v': n },
          UI.h('span', {}, n),
          n === value ? UI.h('span', { class: 'prov-check' }, '✓') : null);
        it.addEventListener('mousedown', (e) => { e.preventDefault(); pick(n); });
        panel.appendChild(it);
      });
    };
    input.addEventListener('focus', () => { input.value = ''; render(); panel.style.display = ''; });
    /* 已聚焦时再次点击（面板已收起）应重新展开 */
    input.addEventListener('click', () => {
      if (panel.style.display === 'none') { input.value = ''; render(); panel.style.display = ''; }
    });
    input.addEventListener('input', render);
    input.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        e.preventDefault();
        const first = panel.style.display !== 'none' && panel.querySelector('.prov-item');
        if (first) pick(first.getAttribute('data-v'));
      } else if (e.key === 'Escape') {
        input.value = value;
        panel.style.display = 'none';
        input.blur();
      }
    });
    input.addEventListener('blur', () => {
      setTimeout(() => { panel.style.display = 'none'; input.value = value; }, 120);
    });
    input.value = value;
    return wrap;
  }

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

    /* 省份：34 省级行政区（标准排序）+ 兼容“其他”，支持搜索过滤 */
    f.province = '河北';
    const provEl = provincePicker('河北', (v) => { f.province = v; });

    const license = UI.h('input', { type: 'file', accept: 'image/*,.pdf' });
    const form = UI.h('form', { onsubmit: (e) => e.preventDefault() },
      UI.h('div', { class: 'sec' }, '企业信息'),
      UI.h('div', { class: 'form-grid' },
        field('companyName', '企业名称', { placeholder: '请输入工商注册全称' }, true),
        field('creditCode', '统一社会信用代码', { placeholder: '18 位字母数字，如 91130000XXXXXXXXXX' }, true),
        UI.h('div', { class: 'form-row full' },
          UI.h('label', { class: 'req' }, '企业角色（仅可选择一个）'),
          UI.h('div', { class: 'role-grid' }, ...roleCards)),
        UI.h('div', { class: 'form-row' },
          UI.h('label', { class: 'req' }, '省份'), provEl),
        field('city', '城市', { placeholder: '如：邯郸市' }, true),
        field('legalPerson', '法定代表人', { placeholder: '选填' }),
        field('address', '详细地址', { placeholder: '选填，省/市之后的具体地址' }),
        UI.h('div', { class: 'form-row full' },
          UI.h('label', {}, '经营范围'),
          UI.h('textarea', { rows: 2, style: 'width:100%', placeholder: '选填，如：铁矿石进口、销售', onchange: (e) => { f.businessScope = e.target.value; } }))),
      UI.h('div', { class: 'sec' }, '联系与结算信息'),
      UI.h('div', { class: 'form-grid' },
        field('contactName', '联系人', { placeholder: '请输入联系人姓名' }, true),
        field('contactPhone', '联系电话', { placeholder: '11 位手机号' }, true),
        field('contactEmail', '联系邮箱', { placeholder: '选填，如 name@company.com' }),
        field('bankName', '开户银行', { placeholder: '选填，如：工商银行邯郸分行' }),
        field('bankAccount', '银行账号', { placeholder: '选填，对公账户号码' })),
      UI.h('div', { class: 'sec' }, '账号与营业执照'),
      UI.h('div', { class: 'form-grid' },
        field('username', '登录账号（11 位手机号）', { placeholder: '设置登录手机号，11 位' }, true),
        field('password', '密码（至少 8 位）', { type: 'password', placeholder: '至少 8 位，建议字母与数字组合' }, true),
        UI.h('div', { class: 'form-row full' },
          UI.h('label', { class: 'req' }, '营业执照'),
          license, UI.h('div', { class: 'hint' }, '支持图片 / PDF'))));

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
          if (!body.companyName || !body.creditCode || !body.companyTypes) {
            UI.toast('企业名称、信用代码、企业角色为必填（角色仅可选择一个）', 'err');
            return;
          }
          if (!/^[0-9A-Z]{15,18}$/.test(body.creditCode)) { UI.toast('统一社会信用代码应为 15~18 位大写字母或数字', 'err'); return; }
          if (!/^1\d{10}$/.test(body.username)) { UI.toast('登录账号必须为 11 位手机号', 'err'); return; }
          if (!body.password || body.password.length < 8) { UI.toast('密码至少 8 位', 'err'); return; }
          if (!body.contactName || !body.contactPhone) { UI.toast('联系人与联系电话为必填', 'err'); return; }
          if (!/^1\d{10}$/.test(body.contactPhone)) { UI.toast('联系电话应为 11 位手机号', 'err'); return; }
          if (body.contactEmail && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(body.contactEmail)) { UI.toast('联系邮箱格式不正确，如 name@company.com', 'err'); return; }
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
