/* ============ 采购商城（现货直购，类电商：商品卡片 → 详情页左图右介绍） ============ */
App.registerView('r1.mall', {
  title: '采购商城', roles: ['R1'],
  async render(root) {
    let detail = null;      // 详情商品对象（进入详情态）
    const container = el('div', null);

    function renderBody() {
      container.innerHTML = '';
      if (detail) { container.appendChild(renderDetail(detail)); return; }
      container.appendChild(renderGoods());
    }

    /* ---------- 商品卡片（照片 + 名称 + 市场价格，点击进详情） ---------- */
    function card(p) {
      const img = el('img', {
        src: p.image, alt: p.name,
        style: { width: '100%', height: '160px', objectFit: 'cover', display: 'block', background: 'linear-gradient(135deg,#f2ece4,#e4ddd2)' }
      });
      img.addEventListener('error', () => {   // 图片加载失败回退
        const ph = el('div', { style: { width: '100%', height: '160px', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '40px', background: 'linear-gradient(135deg,#f2ece4,#e4ddd2)' } }, '🪨');
        img.replaceWith(ph);
      });
      return el('div', {
        style: {
          margin: 0, background: '#fff', border: '1px solid var(--border, #e5e6eb)', borderRadius: '10px',
          overflow: 'hidden', cursor: 'pointer', transition: 'box-shadow .15s, transform .15s',
        },
        onmouseenter: e => { e.currentTarget.style.boxShadow = '0 6px 18px rgba(0,0,0,.10)'; e.currentTarget.style.transform = 'translateY(-2px)'; },
        onmouseleave: e => { e.currentTarget.style.boxShadow = 'none'; e.currentTarget.style.transform = 'none'; },
        onclick: () => { detail = p; renderBody(); window.scrollTo(0, 0); }
      }, [
        img,
        el('div', { style: { padding: '10px 12px 4px', fontSize: '13.5px', fontWeight: 600, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' } },
          `${p.name} ${p.spec} · ${p.origin}`),
        el('div', { style: { padding: '0 12px 12px', display: 'flex', alignItems: 'baseline', gap: '5px' } }, [
          el('span', { style: { color: '#e03e3e', fontWeight: 700, fontSize: '17px' } }, `¥${p.market_price}`),
          el('span', { style: { color: 'var(--text-3)', fontSize: '12px' } }, '/吨')
        ])
      ]);
    }

    /* ---------- 商品浏览 ---------- */
    function renderGoods() {
      const fstate = { keyword: '', ore_category: '', ore_type: '' };
      // 品类↔矿种级联（与价格看板同款映射，后续品类扩展矿种只需在此登记）
      const SUB_TYPE_MAP = { IRON: 'IRON_ORE_TYPE' };
      const catList = App.dict('ORE_CATEGORY');
      const kwIn = el('input', { type: 'text', placeholder: '搜索商品 / 产地 / 规格', style: {
        width: '360px', height: '35px', padding: '0 16px', border: '1px solid var(--border-2, #d8d9dc)', borderRadius: '6px',
        fontSize: '13px', color: 'var(--text-1)', background: 'var(--panel, #fff)', outline: 'none',
        boxSizing: 'border-box', transition: 'border-color .15s ease' } });
      kwIn.addEventListener('focus', () => { kwIn.style.borderColor = 'var(--primary, #0071e3)'; });
      kwIn.addEventListener('blur', () => { kwIn.style.borderColor = 'var(--border-2, #d8d9dc)'; });
      kwIn.addEventListener('input', debounce(() => { fstate.keyword = kwIn.value.trim(); loadGoods(); }, 300));

      /* 级联下拉：一级品类（点击筛选）→ 悬停浮出二级矿种（点击筛选） */
      let curCat = '', curType = '';
      const cascLabel = el('span', null, '全部品类');
      const panel = el('div', {
        style: {
          position: 'absolute', top: 'calc(100% + 4px)', left: 0, zIndex: 60, display: 'none',
          minWidth: '180px', background: '#fff', border: '1px solid var(--border, #e5e6eb)',
          borderRadius: '8px', boxShadow: '0 8px 24px rgba(0,0,0,.12)', padding: '6px'
        }
      });
      const cascader = el('div', { style: { position: 'relative' } }, [
        el('button', {
          class: 'btn', style: { display: 'flex', alignItems: 'center', gap: '6px' },
          onclick: e => {
            e.stopPropagation();
            panel.style.display = panel.style.display === 'none' ? 'block' : 'none';
          }
        }, [cascLabel, el('span', { style: { color: 'var(--text-3)', fontSize: '10px' } }, '▼')]),
        panel
      ]);
      document.addEventListener('click', () => { panel.style.display = 'none'; });
      panel.addEventListener('click', e => e.stopPropagation());

      function cascItem(text, active, onclick, arrow) {
        const it = el('div', {
          style: {
            padding: '8px 12px', borderRadius: '6px', fontSize: '13.5px', cursor: 'pointer',
            display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '8px',
            background: active ? 'var(--blue-bg, #eef4ff)' : 'transparent',
            color: active ? 'var(--blue, #2563eb)' : 'var(--text-1)', whiteSpace: 'nowrap',
            position: 'relative'
          },
          onmouseenter: () => { it.style.background = active ? 'var(--blue-bg, #eef4ff)' : '#f5f6f7'; },
          onmouseleave: () => { it.style.background = active ? 'var(--blue-bg, #eef4ff)' : 'transparent'; },
          onclick
        }, [el('span', null, text), arrow ? el('span', { style: { color: 'var(--text-3)', fontSize: '11px' } }, '›') : null]);
        return it;
      }

      function refreshLabel() {
        cascLabel.textContent = !curCat ? '全部品类'
          : dictName(catList, curCat) + (curType ? ' · ' + dictName(App.dict(SUB_TYPE_MAP[curCat] || ''), curType) : '');
      }

      function select(cat, type) {
        curCat = cat; curType = type;
        fstate.ore_category = cat; fstate.ore_type = type;
        refreshLabel();
        panel.style.display = 'none';
        loadGoods();
      }

      function buildPanel() {
        panel.innerHTML = '';
        panel.appendChild(cascItem('全部品类', !curCat && !curType, () => select('', '')));
        catList.forEach(c => {
          const subs = (SUB_TYPE_MAP[c.item_code] ? App.dict(SUB_TYPE_MAP[c.item_code]) : []);
          const row = cascItem(dictName(catList, c.item_code), curCat === c.item_code && !curType,
            () => select(c.item_code, ''), subs.length);
          if (subs.length) {
            const sub = el('div', {
              style: {
                position: 'absolute', left: '100%', top: '-6px', display: 'none',
                minWidth: '150px', maxHeight: '320px', overflowY: 'auto',
                background: '#fff', border: '1px solid var(--border, #e5e6eb)',
                borderRadius: '8px', boxShadow: '0 8px 24px rgba(0,0,0,.12)', padding: '6px'
              }
            }, subs.map(s => cascItem(s.item_name, curType === s.item_code,
              e => { e.stopPropagation(); select(c.item_code, s.item_code); })));   // 阻止冒泡到一级行，避免矿种筛选被重置
            row.appendChild(sub);
            row.addEventListener('mouseenter', () => { sub.style.display = 'block'; });
            row.addEventListener('mouseleave', () => { sub.style.display = 'none'; });
          }
          panel.appendChild(row);
        });
      }
      buildPanel();
      refreshLabel();
      const cnt = el('span', { class: 'hint', style: { margin: '0 0 0 auto' } });

      const grid = el('div', { style: { display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(210px, 1fr))', gap: '14px', marginTop: '12px' } });

      async function loadGoods() {
        const res = await API.get('/api/mall/products', fstate);
        cnt.textContent = `共 ${res.total} 件商品`;
        grid.innerHTML = '';
        if (!res.list.length) {
          grid.appendChild(el('div', { class: 'empty', style: { gridColumn: '1/-1' } },
            [el('div', { class: 'e-icon' }, '◌'), el('div', null, '没有匹配的商品')]));
          return;
        }
        res.list.forEach(p => grid.appendChild(card(p)));
      }
      loadGoods();   // 默认展示全部在售商品

      return el('div', null, [
        el('div', { class: 'card', style: { marginBottom: '12px' } },
          el('div', { style: { display: 'flex', gap: '10px', alignItems: 'center', flexWrap: 'wrap' } }, [kwIn, cascader, cnt])),
        grid
      ]);
    }

    /* ---------- 商品详情：左侧照片，右侧介绍 + 下单 ---------- */
    function renderDetail(p) {
      const img = el('img', {
        src: p.image, alt: p.name,
        style: { width: '100%', height: '380px', objectFit: 'cover', display: 'block', borderRadius: '10px', border: '1px solid var(--border, #e5e6eb)', background: 'linear-gradient(135deg,#f2ece4,#e4ddd2)' }
      });
      img.addEventListener('error', () => {
        const ph = el('div', { style: { width: '100%', height: '380px', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '72px', borderRadius: '10px', border: '1px solid var(--border, #e5e6eb)', background: 'linear-gradient(135deg,#f2ece4,#e4ddd2)' } }, '🪨');
        img.replaceWith(ph);
      });

      /* 数量步进 */
      const qtyIn = el('input', { type: 'number', min: '1', step: '0.01', value: '1000', style: {
        width: '120px', height: '35px', textAlign: 'center', padding: '0 10px',
        border: '1px solid var(--border-2, #d8d9dc)', borderRadius: '6px', fontSize: '13px',
        color: 'var(--text-1)', background: 'var(--panel, #fff)', outline: 'none', boxSizing: 'border-box',
        transition: 'border-color .15s ease' } });
      qtyIn.addEventListener('focus', () => { qtyIn.style.borderColor = 'var(--primary, #0071e3)'; });
      qtyIn.addEventListener('blur', () => { qtyIn.style.borderColor = 'var(--border-2, #d8d9dc)'; });
      const amountEl = el('span', { style: { fontSize: '18px', fontWeight: 700, color: '#e03e3e' } }, '-');
      const calc = () => {
        const q = parseFloat(qtyIn.value) || 0;
        amountEl.textContent = q > 0 ? `¥${(q * p.price).toLocaleString('zh-CN', { maximumFractionDigits: 2 })}` : '-';
      };
      const stepQty = d => { const q = Math.max(1, (parseFloat(qtyIn.value) || 0) + d); qtyIn.value = q; calc(); };
      qtyIn.addEventListener('input', calc);
      calc();

      const portSel = el('select', { style: { width: '260px', height: '35px', padding: '0 12px',
        border: '1px solid var(--border-2, #d8d9dc)', borderRadius: '6px', fontSize: '13px',
        color: 'var(--text-1)', background: 'var(--panel, #fff)', outline: 'none', boxSizing: 'border-box',
        transition: 'border-color .15s ease' } }, [el('option', { value: '' }, '请选择目的港'),
        ...App.dict('PORT').map(d => el('option', { value: d.item_code }, d.item_name))]);
      portSel.addEventListener('focus', () => { portSel.style.borderColor = 'var(--primary, #0071e3)'; });
      portSel.addEventListener('blur', () => { portSel.style.borderColor = 'var(--border-2, #d8d9dc)'; });
      const isR1 = App.user.role_code === 'R1';

      const paramRow = (label, value) => el('div', { style: { display: 'flex', gap: '10px', fontSize: '13px', padding: '5px 0' } }, [
        el('span', { style: { color: 'var(--text-3)', flex: 'none', width: '72px' } }, label),
        el('span', { style: { color: 'var(--text-1)' } }, value)
      ]);

      /* 集采预购：方框按钮，点击弹出信息填写栏
         申报周期=两个日期用横杠相连；品位要求=TFe 固定前缀 + 运算符(=、≥) + 百分比 */
      const buyBtn = el('button', {
        class: 'btn btn-primary', style: { background: '#e03e3e', borderColor: '#e03e3e', padding: '10px 42px', fontSize: '15px', borderRadius: '0' },
        onclick: () => {
          if (!isR1) { Toast.info('商城下单仅面向下游需求企业（R1）'); return; }

          const field = (labelText, ctrl, hint) => {
            const wrap = el('div', { class: 'field' }, [el('label', null, [labelText, el('span', { class: 'req' }, '*')]), ctrl]);
            if (hint) wrap.appendChild(el('div', { class: 'hint' }, hint));
            return wrap;
          };
          /* 申报周期：年份 + 类型（月度/季度）联动——月度选1-12月，季度选一~四季度，
             周期值与采购需求申报格式一致（2026-11 / 2026-Q4） */
          const Y = new Date().getFullYear();
          /* 年份可选范围：近5年 ~ 未来10年（同日期控件可自由选年），显示格式统一“2026年” */
          const yearSel = el('select', null,
            Array.from({ length: 16 }, (_, i) => Y - 5 + i).map(y => el('option', { value: String(y) }, `${y}年`)));
          yearSel.value = String(Y);
          const periodTypeSel = el('select', null, [el('option', { value: '' }, '请选择'),
            ...App.dict('PERIOD_TYPE').map(d => el('option', { value: d.item_code }, d.item_name))]);
          periodTypeSel.value = 'MONTH';
          const periodIn2 = el('select', null, []);
          function rebuildPeriod() {
            periodIn2.innerHTML = '';
            const y = yearSel.value;
            if (periodTypeSel.value === 'MONTH') {
              periodIn2.appendChild(el('option', { value: '' }, '请选择月份'));
              for (let m = 1; m <= 12; m++) {
                const v = `${y}-${String(m).padStart(2, '0')}`;
                periodIn2.appendChild(el('option', { value: v }, v));
              }
            } else if (periodTypeSel.value === 'QUARTER') {
              periodIn2.appendChild(el('option', { value: '' }, '请选择季度'));
              ['一', '二', '三', '四'].forEach((c, i) => {
                const v = `${y}-Q${i + 1}`;
                periodIn2.appendChild(el('option', { value: v }, v));
              });
            } else {
              periodIn2.appendChild(el('option', { value: '' }, '请先选择周期类型'));
            }
          }
          rebuildPeriod();
          yearSel.addEventListener('change', rebuildPeriod);
          periodTypeSel.addEventListener('change', rebuildPeriod);
          const periodWrap = el('div', { style: { display: 'flex', gap: '8px' } }, [yearSel, periodIn2]);
          /* 品位要求：TFe ≥ 固定 + 百分比 */
          const gradeVal = el('input', { type: 'number', placeholder: '如 62', min: '0', max: '100', step: '0.1', style: { flex: 1 } });
          const gradeRow = el('div', { style: { display: 'flex', alignItems: 'center', gap: '8px' } }, [
            el('span', { style: { flex: 'none', fontSize: '13px', fontWeight: 600, color: 'var(--text-2)' } }, 'TFe'),
            el('span', { style: { flex: 'none', fontSize: '13px', color: 'var(--text-2)' } }, '≥'),
            gradeVal,
            el('span', { style: { flex: 'none', color: 'var(--text-3)', fontSize: '13px' } }, '%')
          ]);
          const priceIn = el('input', { type: 'number', value: p.price, min: '0' });
          const qtyIn2 = el('input', { type: 'number', value: qtyIn.value, min: '1' });
          /* 预采购总价：数量×单价自动计算（只读展示） */
          const totalIn = el('input', { type: 'text', readOnly: true, style: { background: 'var(--bg-2, #f7f8fa)', color: '#e03e3e', fontWeight: 700 } });
          const calcTotal = () => {
            const q = parseFloat(qtyIn2.value) || 0, pr = parseFloat(priceIn.value) || 0;
            totalIn.value = q && pr ? fmtQty(q * pr) + ' 元' : '';
          };
          qtyIn2.addEventListener('input', calcTotal);
          priceIn.addEventListener('input', calcTotal);
          calcTotal();
          const arriveIn = el('input', { type: 'date' });
          const addrIn = el('input', { type: 'text', placeholder: '请填写交货地址' });
          const contactIn = el('input', { type: 'text', placeholder: '请填写联系人姓名' });
          const phoneIn = el('input', { type: 'text', placeholder: '请填写手机号', maxlength: 20 });
          /* 备注：非必填，大文本框 */
          const remarkIn = el('textarea', { placeholder: '选填，可填写运输、包装、验收等特殊要求',
            style: { width: '100%', minHeight: '88px', padding: '9px 14px', border: '1px solid var(--border-2, #d8d9dc)',
              borderRadius: '6px', fontSize: '13px', color: 'var(--text-1)', background: 'var(--panel, #fff)',
              outline: 'none', boxSizing: 'border-box', resize: 'vertical', lineHeight: '1.6', fontFamily: 'inherit',
              transition: 'border-color .15s ease' } });
          remarkIn.addEventListener('focus', () => { remarkIn.style.borderColor = 'var(--primary, #0071e3)'; });
          remarkIn.addEventListener('blur', () => { remarkIn.style.borderColor = 'var(--border-2, #d8d9dc)'; });

          const addrField = field('交货地点', addrIn);
          addrField.classList.add('full');   // 独占整行，与右侧对齐
          const contactField = field('联系人', contactIn);
          const phoneField = field('联系方式', phoneIn);
          const remarkField = el('div', { class: 'field' }, [
            el('label', null, '备注'), remarkIn
          ]);
          remarkField.classList.add('full');

          const body = el('div', null, el('div', { class: 'form-grid' }, [
            field('申报周期类型', periodTypeSel),
            field('申报周期', periodWrap),
            field('品位要求', gradeRow),
            field('预采购单价（元/吨）', priceIn),
            field('预采购数量（吨）', qtyIn2),
            field('预采购总价', totalIn),
            field('预到货日期', arriveIn),
            addrField,
            contactField,
            phoneField,
            remarkField
          ]));

          openModal({
            title: `集采预购 · ${p.name}`,
            body,
            footer: close => [
              el('button', { class: 'btn', onclick: close }, '取消'),
              el('button', {
                class: 'btn btn-primary',
                onclick: async () => {
                  const q = parseFloat(qtyIn2.value), pr = parseFloat(priceIn.value), gv = parseFloat(gradeVal.value);
                  let ok = true;
                  const need = inp => { if (!inp.value) { inp.closest('.field').classList.add('invalid'); ok = false; } };
                  [periodTypeSel, periodIn2, arriveIn, addrIn, contactIn, phoneIn].forEach(need);
                  if (!gv && gv !== 0) { gradeVal.closest('.field').classList.add('invalid'); ok = false; }
                  if (!pr || pr <= 0) { priceIn.closest('.field').classList.add('invalid'); ok = false; }
                  if (!q || q <= 0) { qtyIn2.closest('.field').classList.add('invalid'); ok = false; }
                  if (!ok) { Toast.error('请填写完整必填项'); return; }
                  try {
                    await API.post('/api/mall/order', { product_id: p.id, qty: q, dest_port: addrIn.value,
                      period_type: periodTypeSel.value, period: periodIn2.value,
                      grade_req: `TFe≥${gv}%`,
                      pre_price: pr, expected_arrival: arriveIn.value, remark: remarkIn.value,
                      contact_name: contactIn.value, contact_phone: phoneIn.value });
                    close();   // 提交成功后关闭弹窗
                    Toast.success('预购提交成功，已进入需求申报列表');
                    location.hash = '#/r1.demand';
                  } catch (e) { /* toast 已提示 */ }
                }
              }, '提交预购')
            ]
          });
        }
      }, '集采预购');

      return el('div', null, [
        /* 面包屑 */
        el('div', { style: { display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '12px', fontSize: '13px', color: 'var(--text-2)' } }, [
          el('span', { style: { cursor: 'pointer', color: 'var(--blue, #2563eb)' }, onclick: () => { detail = null; renderBody(); } }, '采购商城'),
          el('span', null, '›'),
          el('span', null, `${p.name}（${p.spec}）`),
          el('button', { class: 'btn btn-sm', style: { marginLeft: 'auto' }, onclick: () => { detail = null; renderBody(); } }, '← 返回商品列表')
        ]),
        el('div', { class: 'card', style: { padding: '20px', display: 'flex', gap: '24px', flexWrap: 'wrap' } }, [
          /* 左：照片 */
          el('div', { style: { width: '400px', flex: 'none' } }, [img]),
          /* 右：介绍 + 购买 */
          el('div', { style: { flex: 1, minWidth: '320px', display: 'grid', gap: '12px', alignContent: 'start' } }, [
            el('div', { style: { display: 'flex', gap: '8px', alignItems: 'center', flexWrap: 'wrap' } }, [
              el('span', { style: { fontSize: '17px', fontWeight: 700 } }, p.name)
            ]),
            /* 价格区 */
            el('div', { style: { background: 'var(--bg-2, #f7f8fa)', borderRadius: '8px', padding: '12px 16px', display: 'flex', alignItems: 'baseline', gap: '14px' } }, [
              el('span', { style: { fontSize: '13px', color: 'var(--text-2)' } }, '参考价'),
              el('span', { style: { color: '#e03e3e', fontWeight: 700, fontSize: '24px' } }, `¥${p.price}`),
              el('span', { style: { color: 'var(--text-3)', fontSize: '12px' } }, '/吨')
            ]),
            /* 参数表 */
            el('div', { style: { display: 'grid', gridTemplateColumns: '1fr 1fr', columnGap: '32px', borderTop: '1px dashed var(--border, #e5e6eb)', paddingTop: '10px' } }, [
              paramRow('品牌', p.brand), paramRow('商品编号', `MD${String(p.id).padStart(6, '0')}`),
              paramRow('产地', p.origin),
              paramRow('矿种', dictName(App.dict('IRON_ORE_TYPE'), p.ore_type))
            ]),
            /* 购买区 */
            el('div', { style: { borderTop: '1px dashed var(--border, #e5e6eb)', paddingTop: '12px', display: 'grid', gap: '10px' } }, [
              el('div', { style: { display: 'flex', alignItems: 'center', gap: '10px' } }, [
                el('span', { style: { fontSize: '13px', color: 'var(--text-2)' } }, '配送至'), portSel
              ]),
              el('div', { style: { display: 'flex', alignItems: 'center', gap: '10px' } }, [
                el('span', { style: { fontSize: '13px', color: 'var(--text-2)' } }, '数　量'),
                el('div', { style: { display: 'flex', gap: '4px' } }, [
                  el('button', { class: 'btn btn-sm', onclick: () => stepQty(-100) }, '−'),
                  qtyIn,
                  el('button', { class: 'btn btn-sm', onclick: () => stepQty(100) }, '+')
                ]),
                el('span', { style: { fontSize: '12.5px', color: 'var(--text-3)' } }, '吨（±100 步进）')
              ]),
              el('div', { style: { display: 'flex', alignItems: 'center', gap: '12px' } }, [
                el('span', { style: { fontSize: '13px', color: 'var(--text-2)' } }, '预估金额'), amountEl,
                buyBtn,
                !isR1 ? el('span', { class: 'hint', style: { margin: 0 } }, '（仅下游企业可下单）') : null
              ])
            ])
          ])
        ])
      ]);
    }

    renderBody();
    root.appendChild(container);
  }
});
