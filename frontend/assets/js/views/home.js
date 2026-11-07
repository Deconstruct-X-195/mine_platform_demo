/* ============ 各角色工作台首页 ============ */
/* 快捷入口箭头：SVG 渲染 + flex 居中（字体"→"字形基线偏上会视觉不居中，故弃用字符箭头） */
const ARR_SVG = '<svg viewBox="0 0 12 12" width="11" height="11"><path d="M4.2 2.6 L7.6 6 L4.2 9.4" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>';

App.registerView('home', {
  title: '工作台', roles: ['R1', 'R2', 'R3', 'R4'],
  async render(root) {
    const u = App.user;
    const greeting = u.real_name || u.username;
    const cards = el('div', { class: 'stat-grid' });
    const mainCard = el('div', { class: 'card' });

    root.appendChild(el('div', { class: 'card', style: { position: 'relative', background: 'linear-gradient(120deg,#0071e3 0%,#3b8de8 60%,#5ac8fa 135%)', color: '#fff', border: 'none' } }, [
      el('div', { style: { fontSize: '18px', fontWeight: '700', marginBottom: '6px' } }, `你好，${greeting}`),
      el('div', { style: { fontSize: '13px', opacity: '.85' } },
        u.company ? `${u.company.company_name} · ${TAG_MAP[u.role_code] ? TAG_MAP[u.role_code][0] : u.role_code}`
                  : '平台集采中枢 · 统筹需求归集、询价锁货、物流分拨与对账归档')
    ]));

    const roleCfg = {
      R1: {
        desc: '下游需求企业：按月/季度申报采购需求，接收分拨到货并完成对账。',
        stats: [
          ['我的申报需求', 'demand_mine', '条'], ['待确认分拨单', 'alloc_wait', '单'],
          ['待确认账单', 'bill_wait', '张']
        ],
        tips: [['采购需求管理', 'r1.demand'], ['我的分拨单', 'r1.alloc']]
      },
      R2: {
        desc: '上游供给方：维护货源档案，接收平台集采询价并参与报价。',
        stats: [
          ['我的货源', 'res_mine', '条'], ['待报价询价', 'inq_wait', '个']
        ],
        tips: [['货源管理', 'r2.resource'], ['集采询价任务', 'r2.inquiry']]
      },
      R3: {
        desc: '履约配套方：领取物流任务，更新港口/仓储/运输节点并上传单据。',
        stats: [['我的物流任务', 'logi_mine', '个']],
        tips: [['我的物流任务', 'r3.logistics']]
      },
      R4: {
        desc: '平台集采管理员：归集需求、询价锁货、统筹物流、按需分拨、对账归档。',
        stats: [
          ['企业总数', 'comp_total', '家'], ['待审核企业', 'comp_pending', '家'],
          ['申报需求', 'demand_total', '条'], ['集采订单', 'order_total', '单']
        ],
        tips: [['需求归集', 'r4.demand'], ['集采交易', 'r4.trade'], ['物流看板', 'r4.logistics']]
      }
    }[u.role_code] || { desc: '', stats: [], tips: [] };

    // 统计数据（后端汇总接口；模块未开放时静默忽略）
    try {
      const s = await API.get('/api/dashboard/workbench');
      roleCfg.stats.forEach(([label, key, unit]) => {
        cards.appendChild(el('div', { class: 'stat-card' }, [
          el('div', { class: 's-label' }, label),
          el('div', { class: 's-value' }, String(s[key] ?? 0), el('small', null, unit))
        ]));
      });
      // R1：统计卡等分铺满整行（左贴内容左缘、右贴内容右缘）；其他角色保持默认布局
      if (u.role_code === 'R1' && roleCfg.stats.length)
        cards.style.gridTemplateColumns = `repeat(${roleCfg.stats.length}, 1fr)`;
    } catch (e) { /* 统计接口随后续模块开放 */ }

    if (cards.children.length) root.appendChild(cards);
    // R1 工作台：价格指数 + 我的订单 双栏（替代原"当前角色职能"卡）；其他角色保留职能卡
    if (u.role_code === 'R1') {
      root.appendChild(buildR1Panel());
    } else {
      mainCard.appendChild(el('div', { class: 'card-title' }, '当前角色职能'));
      mainCard.appendChild(el('div', { style: { color: 'var(--text-2)', fontSize: '13.5px', lineHeight: '1.8' } }, roleCfg.desc));
      if (roleCfg.tips.length) {
        const tipBox = el('div', { style: { display: 'flex', gap: '10px', marginTop: '14px', flexWrap: 'wrap' } });
        roleCfg.tips.forEach(([t, k]) => {
          if (App.views[k]) tipBox.appendChild(el('button', { class: 'btn', onclick: () => location.hash = '#/' + k },
            [t, el('span', { class: 'btn-arr', html: ARR_SVG })]));
        });
        mainCard.appendChild(tipBox);
      }
      root.appendChild(mainCard);
    }
    App._refreshMsgBadge?.();   // 工作台徽标立即同步未读数

    /* R1 双栏：左=价格指数（近30日铁矿石市场参考价）右=我的订单（最近商城订单） */
    function buildR1Panel() {
      const grid = el('div', { style: { display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(360px, 1fr))', gap: '12px' } });
      const priceBox = el('div', { class: 'card', style: { margin: 0, height: '357px' } });
      const orderBox = el('div', { class: 'card', style: { margin: 0, height: '357px', display: 'flex', flexDirection: 'column' } });
      grid.appendChild(priceBox);
      grid.appendChild(orderBox);

      const boxHead = (title, hint, linkText, onLink) => el('div', { style: { display: 'flex', alignItems: 'center', gap: '8px' } }, [
        el('div', { class: 'card-title', style: { margin: 0 } }, title),
        el('span', { class: 'hint', style: { margin: 0 } }, hint),
        linkText ? el('button', { class: 'btn btn-sm btn-link', style: { marginLeft: 'auto' }, onclick: onLink }, linkText) : null
      ]);
      const emptyBox = text => el('div', { style: { padding: '22px 0', textAlign: 'center', color: 'var(--text-3)', fontSize: '13px' } }, text);

      /* 左：价格指数 */
      (async () => {
        const to = new Date().toISOString().slice(0, 10);
        const from = new Date(Date.now() - 29 * 864e5).toISOString().slice(0, 10);
        let list = [];
        try {
          const res = await API.get('/api/company/price/trend', { ore_category: 'IRON', date_from: from, date_to: to, page: 1, page_size: 60 });
          list = res.list || [];
        } catch (e) { /* 静默 */ }
        priceBox.appendChild(boxHead('价格指数', '铁矿石 · 近30日市场参考价', '更多 ›', () => location.hash = '#/r1.market'));
        const asc = [...list].reverse();
        if (!asc.length) { priceBox.appendChild(emptyBox('暂无行情数据')); return; }
        const chartBox = el('div', { style: { height: '290px', marginTop: '8px' } },
          el('canvas', { style: { width: '100%', height: '100%' } }));
        priceBox.appendChild(chartBox);
        Charts.line(chartBox.querySelector('canvas'), asc.map(t => t.quote_date.slice(5)),
          [{ name: '市场参考价', color: '#2563eb', data: asc.map(t => t.market_price) }], { unit: '元' });
      })();

      /* 右：我的订单 */
      (async () => {
        let list = [];
        try {
          const res = await API.get('/api/mall/orders', { page: 1, page_size: 5 });
          list = res.list || [];
        } catch (e) { /* 静默 */ }
        orderBox.appendChild(boxHead('我的订单', '商城最近下单', '查看全部 ›',
          () => { sessionStorage.setItem('r1.demand.tab', 'orders'); location.hash = '#/r1.demand'; }));
        if (!list.length) {
          orderBox.appendChild(el('div', { style: { padding: '16px 0', textAlign: 'center', color: 'var(--text-3)', fontSize: '13px' } }, [
            el('div', { style: { marginBottom: '8px', fontSize: '22px' } }, '◌'),
            el('div', { style: { marginBottom: '10px' } }, '暂无商城订单'),
            el('button', { class: 'btn btn-primary btn-sm', onclick: () => location.hash = '#/r1.mall' }, '去商城逛逛')
          ]));
          return;
        }
        // 行高自然：订单少时面板下方留空，新订单按序向下填充；订单多时表格区滚动
        const tb = el('table', { class: 'tb' }, [
          el('thead', null, el('tr', null, ['订单号', '商品', '数量', '总金额', '状态'].map(h => el('th', null, h)))),
          el('tbody', null, list.map(r => el('tr', null, [
            el('td', { class: 'strong' }, r.order_no || '-'),
            el('td', null, `${r.product_name}（${r.spec || '-'}）`),
            el('td', { class: 'num' }, fmtQty(r.qty) + ' 吨'),
            el('td', { class: 'num' }, '¥' + fmtQty(r.total_amount)),
            el('td', null, tag(r.status))
          ])))
        ]);
        // 表格撑满卡片剩余高度：与标题行留 10px 间距，表底随面板底部收齐（留卡片内边距）
        orderBox.appendChild(el('div', { class: 'table-wrap', style: { flex: 1, marginTop: '10px', display: 'flex', flexDirection: 'column', overflowY: 'auto' } }, tb));
      })();

      return grid;
    }
  }
});
