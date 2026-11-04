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

    root.appendChild(el('div', { class: 'card', style: { background: 'linear-gradient(120deg,#0071e3 0%,#3b8de8 60%,#5ac8fa 135%)', color: '#fff', border: 'none' } }, [
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
    } catch (e) { /* 统计接口随后续模块开放 */ }

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

    if (cards.children.length) root.appendChild(cards);
    root.appendChild(mainCard);
  }
});
