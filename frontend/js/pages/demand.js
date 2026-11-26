/* 需求管理（PRD 4.2/FR-02/T06-T07）：钢厂需求单 CRUD/提交/撤回/关闭 */
(function () {
  window.Pages = window.Pages || {};
  const DELIVERY = { PLANT: '到场', STATION_SELF: '到站自提', PORT_FOB: '港口FOB', PORT_TRUCK: '港口自提' };
  const SETTLE = { PREPAY: '现货现款', COD: '货到付款', CREDIT: '账期结算', INSTALLMENT: '分期付款' };

  /* 采购周期文案：MONTH→「2026年11月」，QUARTER→「2026年第4季度」，ONE_TIME→「一次性订单（2026年12月）」，无值→「—」 */
  function cycleText(type, year, value) {
    if (type === 'ONE_TIME') {
      return (year && value) ? '一次性订单（' + year + '年' + value + '月）' : '一次性订单';
    }
    if (!type || !year || !value) return '—';
    return year + '年' + (type === 'QUARTER' ? '第' + value + '季度' : value + '月');
  }

  /* 周期类型文案（配合独立「周期类型」列）：MONTH→月度，QUARTER→季度，ONE_TIME→一次性订单 */
  function cycleTypeText(type) {
    return ({ MONTH: '月度', QUARTER: '季度', ONE_TIME: '一次性订单' }[type]) || '—';
  }

  /* 申报周期值文案（不含类型前缀，配合独立「周期类型」列） */
  function cycleValueText(type, year, value) {
    if (!type || !year || !value) return '—';
    return year + '年' + (type === 'QUARTER' ? '第' + value + '季度' : value + '月');
  }

  /* -------- 钢厂：需求单列表 -------- */
  Pages.demand = async function (page, user) {
    let status = '';
    let pageNo = 1;
    const SIZE = 10;
    const selected = new Set();   // 勾选的需求单 id（跨页保留）
    const rowCache = new Map();   // id -> 行数据（供批量操作）
    let pageRows = [];            // 当前页行数据
    const listCard = UI.h('div', { class: 'card' });
    const pagerBox = UI.h('div', {});
    const contentBox = UI.h('div', {});   // 表格+分页容器（load 时清空重建）
    const listBox = UI.h('div', { class: 'list-fixed' });   // 定高列表区（同运营端）：表头39px+10行，超出滚动
    /* 面板一：标题行（状态筛选紧跟标题）→ 批量按钮行；面板二：表格 + 分页 */
    const btnBar = UI.h('div', { class: 'batch-bar' },
      UI.h('button', { class: 'primary', onclick: () => editForm(null, () => load()) }, '新建需求'),
      UI.h('button', { onclick: batchEdit }, '更 改'),
      UI.h('button', { class: 'danger', onclick: batchDelete }, '删 除'),
      UI.h('button', { onclick: batchExport }, '导 出'));
    page.appendChild(UI.h('div', { class: 'card' },
      UI.h('div', { class: 'toolbar' },
        UI.h('h3', { style: 'margin:0;border:none;padding:0' }, '需求单'),
        UI.statusFilter('DEMAND', (v) => { status = v; pageNo = 1; selected.clear(); load(); })),
      btnBar));
    page.appendChild(listCard);
    listCard.appendChild(contentBox);   // 表格+分页容器必须挂进表格面板，否则 load 渲染进孤儿节点导致页面空白
    contentBox.appendChild(listBox);    // 定高列表区：纵向超出滚动，横向滚动条固定在分页行上方
    contentBox.appendChild(pagerBox);   // 分页条固定在面板右下角

    function selRows() {
      return [...selected].map((id) => rowCache.get(id)).filter(Boolean);
    }
    function syncHead() {
      const hb = listCard.querySelector('thead input[type=checkbox]');
      if (hb) hb.checked = pageRows.length > 0 && pageRows.every((r) => selected.has(r.id));
    }
    function blockedStatus(r) {
      if (['DEALT', 'CLOSED'].indexOf(r.status) >= 0) {
        return '需求单已进入' + ({ DEALT: '成交', CLOSED: '关闭' }[r.status]) + '流程，不可操作';
      }
      if (r.status === 'DELETE_AUDIT') {
        return '删除申请待运营端审核，暂不可操作';
      }
      /* 已归集未询价（归集单 OPEN）的需求仍可提交变更申请 */
      if (r.status === 'INQUIRING' && !r.aggOpen) {
        return '需求单已进入询价流程，不可操作';
      }
      return '';
    }
    function batchEdit() {
      if (selected.size !== 1) { UI.toast('请勾选一条需求单', 'err'); return; }
      const r = selRows()[0];
      if (!r) { UI.toast('请勾选一条需求单', 'err'); return; }
      const blocked = blockedStatus(r);
      if (blocked) { UI.toast(blocked, 'err'); return; }
      /* 更改直接进入信息表单：变更理由作为表单末尾字段填写，保存本地暂存（待提交），点「提交」后推送运营端 */
      editForm(r, () => load());
    }
    async function batchDelete() {
      const rows = selRows();
      if (!rows.length) { UI.toast('请先勾选需求单', 'err'); return; }
      /* 仅「已关闭」的需求单钢厂可自行删除（直接删除）；其他状态不可删除 */
      const closable = rows.filter((r) => r.status === 'CLOSED');
      if (closable.length !== rows.length) {
        UI.toast('仅「已关闭」状态的需求单可自行删除，其他状态不可删除，请重新勾选', 'err');
        return;
      }
      if (!(await UI.confirmBox('确认删除选中的 ' + closable.length + ' 条已关闭需求单？删除后不可恢复。'))) return;
      for (const r of closable) await API.del('/demands/' + r.id);
      UI.toast('已删除 ' + closable.length + ' 条需求单', 'ok');
      selected.clear();
      load();
    }
    function batchExport() {
      const rows = selRows();
      if (!rows.length) { UI.toast('请先勾选需求单', 'err'); return; }
      const PRINT_STATUS = { DRAFT: '待提交', SUBMITTED: '已提交', AGGREGATED: '已归集', TO_INQUIRY: '待询价', WITHDRAWN: '待提交', PENDING_DELETE: '待提交', DELETE_AUDIT: '删除待审核', CLOSED: '已关闭', INQUIRING: '询价中', DEALT: '已成交' };
      UI.exportPreview({
        title: '导出预览 — 需求单',
        filename: '需求单导出_' + new Date().toISOString().slice(0, 10).replace(/-/g, '') + '.csv',
        head: ['需求编号', '产品名称', '品位(%)', '采购周期', '数量(湿吨)', '溢短装(%)', '交货方式', '交货地点', '期望到货时间', '结算方式', '状态', '创建时间'],
        rows: rows.map((r) => {
          const it = (r.items && r.items[0]) || {};
          return [
            r.demand_no,
            it.varietyName || r.demand_name,
            it.grade,
            cycleText(it.cycleType, it.cycleYear, it.cycleValue),
            it.quantity,
            it.moreLessRate == null ? 5 : it.moreLessRate,
            DELIVERY[r.delivery_type] || r.delivery_type,
            r.delivery_place || '—',
            UI.fmtDate(r.expect_arrive_start) + ' ~ ' + UI.fmtDate(r.expect_arrive_end),
            (SETTLE[r.settle_type] || r.settle_type || '-') + (r.settle_days ? ' ' + r.settle_days + '天' : ''),
            PRINT_STATUS[r.status] || r.status,
            UI.fmtDateTime(r.created_at),
          ];
        }),
      });
    }

    let loadSeq = 0;
    async function load() {
      /* 请求序号守卫：并发/连点触发的过期响应直接丢弃，避免重复表格 */
      const seq = ++loadSeq;
      const d = await API.get('/demands' + API.qs({ page: pageNo, size: SIZE, status }));
      if (seq !== loadSeq) return;
      pageRows = d.list || [];
      pageRows.forEach((r) => rowCache.set(r.id, r));
      listBox.innerHTML = '';
      /* 表头全选框 + 行勾选框 */
      const headBox = UI.h('input', {
        type: 'checkbox',
        checked: pageRows.length > 0 && pageRows.every((r) => selected.has(r.id)),
      });
      headBox.addEventListener('change', () => {
        pageRows.forEach((r) => { if (headBox.checked) selected.add(r.id); else selected.delete(r.id); });
        load();
      });
      listBox.appendChild(UI.table([
        {
          cls: 'sel-col', label: headBox,
          render: (r) => UI.h('input', {
            type: 'checkbox', checked: selected.has(r.id),
            onchange: (e) => { if (e.target.checked) selected.add(r.id); else selected.delete(r.id); syncHead(); },
          }),
        },
        { key: 'demand_no', label: '需求编号' },
        { label: '产品名称', render: (r) => (r.items && r.items[0] && r.items[0].varietyName) || r.demand_name || '-' },
        { label: '吨数（湿吨）', num: true, render: (r) => (r.items && r.items[0] && r.items[0].quantity != null ? UI.fmtQty(r.items[0].quantity) : '-') },
        { key: 'delivery_type', label: '交货方式', render: (r) => DELIVERY[r.delivery_type] || r.delivery_type || '-' },
        { label: '周期类型', render: (r) => cycleTypeText(r.items && r.items[0] ? r.items[0].cycleType : null) },
        { label: '申报周期', render: (r) => (r.items && r.items[0] ? cycleValueText(r.items[0].cycleType, r.items[0].cycleYear, r.items[0].cycleValue) : '—') },
        { label: '结算方式', render: (r) => (SETTLE[r.settle_type] || r.settle_type || '-') + (r.settle_days ? ' ' + r.settle_days + '天' : '') },
        { key: 'status', label: '状态', render: (r) => UI.h('span', { class: 'inline-flex' },
          UI.statusTag('DEMAND', r.status),
          r.changePending ? UI.h('span', { class: 'tag orange', title: '变更申请待运营端审核' }, '变更审核中') : null,
          r.lastChangeStatus === 'REJECTED'
            ? UI.h('span', { class: 'tag red', style: 'margin-left:4px',
                title: '驳回原因：' + (r.lastChangeRemark || '无') }, '已驳回')
            : null,
          r.lastChangeStatus === 'REJECTED' && r.lastChangeRemark
            ? UI.h('span', { class: 'muted', style: 'font-size:12px;margin-left:6px',
                title: '驳回原因：' + r.lastChangeRemark }, '原因：' + r.lastChangeRemark)
            : null) },
        { key: 'created_at', label: '创建时间', render: (r) => UI.fmtDateTime(r.created_at) },
        { label: '操作', render: (r) => acts(r) },
      ], d.list, '暂无需求单'));
      pagerBox.innerHTML = '';
      UI.pager(pagerBox, pageNo, SIZE, d.total, (p) => { pageNo = p; load(); });
    }

    function acts(r) {
      const btns = [UI.h('button', { class: 'sm', onclick: () => detail(r.id) }, '详情')];
      /* 已关闭的需求钢厂可自行删除（直接删除，不走删除审核流程） */
      if (r.status === 'CLOSED') {
        btns.push(UI.h('button', { class: 'sm', onclick: async () => {
          if (!(await UI.confirmBox('确认删除已关闭的需求单 ' + (r.demand_no || '') + '？删除后不可恢复。'))) return;
          await API.del('/demands/' + r.id);
          UI.toast('已删除', 'ok');
          load();
        } }, '删除'));
      }
      return UI.h('span', { class: 'inline-flex' }, ...btns);
    }

    async function detail(did) {
      const d = await API.get('/demands/' + did);
      const body = UI.h('div', {},
        UI.kv([
          ['需求编号', d.demand_no], ['状态', UI.statusTag('DEMAND', d.status)],
          ['交货方式', DELIVERY[d.delivery_type] || d.delivery_type],
          ['交货地点', d.delivery_place || '-'],
          ['申报周期', d.items && d.items[0] ? cycleText(d.items[0].cycleType, d.items[0].cycleYear, d.items[0].cycleValue) : '—'],
          ['期望到货', UI.fmtDate(d.expect_arrive_start) + ' ~ ' + UI.fmtDate(d.expect_arrive_end)],
          ['结算方式', (SETTLE[d.settle_type] || d.settle_type || '-') + (d.settle_days ? ' ' + d.settle_days + '天' : '')],
          ['质量要求', d.quality_req, true],
        ]),
        UI.h('h3', { style: 'margin-top:14px' }, '需求明细'),
        /* 明细仅展示填写内容：品种/品位/采购周期/数量(湿吨) */
        UI.table([
          { key: 'varietyName', label: '品种' },
          { key: 'grade', label: '品位(%)' },
          { label: '采购周期', render: (r) => cycleText(r.cycleType, r.cycleYear, r.cycleValue) },
          { key: 'quantity', label: '数量(湿吨)', num: true, render: (r) => UI.fmtMoney(r.quantity) },
        ], d.items));
      UI.modal('需求单 ' + (d.demand_no || ''), body);
    }

    function closeForm(r, onDone) {
      const reason = UI.h('textarea', { rows: 2, style: 'width:100%', placeholder: '关闭原因（必填）' });
      const m = UI.modal('关闭需求单 ' + r.demand_no, UI.h('div', {}, UI.formRow('关闭原因', reason, true)), [
        UI.h('button', { class: 'primary', onclick: async () => {
          if (!reason.value.trim()) { UI.toast('请填写关闭原因', 'err'); return; }
          await API.post('/demands/' + r.id + '/close', { reason: reason.value.trim() });
          m.close(); UI.toast('已关闭', 'ok'); onDone();
        } }, '确认关闭'),
      ]);
    }

    /* -------- 新建/编辑（精简表单：产品名称/交货方式/到货日期/结算账期/质量要求） -------- */
    async function editForm(row, onDone) {
      let existing = null;
      if (row) existing = await API.get('/demands/' + row.id);
      const allVarieties = (await API.get('/base/varieties')).list;
      /* 需求产品限定：PB粉 / 中华混一号 / 其它（其它仅做需求归集，不形成实际订单） */
      const ALLOWED_VARIETIES = ['PB粉', '中华混一号', '其它'];
      const varieties = allVarieties.filter((v) => ALLOWED_VARIETIES.indexOf(v.varietyName) >= 0);
      const otherVariety = varieties.find((v) => v.varietyCode === 'OTHER') || null;
      /* 「其它」固定排在选项末尾，避免空值时被浏览器默认选中 */
      const vOpts = varieties.filter((v) => v !== otherVariety)
        .map((v) => [v.id, v.varietyName + '(' + v.varietyCode + ')']);
      if (otherVariety) vOpts.push([otherVariety.id, otherVariety.varietyName + '(' + otherVariety.varietyCode + ')']);
      const firstItem = (existing && existing.items && existing.items[0]) || {};
      /* 采购周期：品位之后新增「周期类型」+「周期」（两个框）。
         月度 → 周期显示 年 + 月份；季度 → 周期显示 年 + 季度 */
      const CYCLE_MONTHS = Array.from({ length: 12 }, (_, i) => [String(i + 1), (i + 1) + '月']);
      const CYCLE_QUARTERS = [['1', '第1季度'], ['2', '第2季度'], ['3', '第3季度'], ['4', '第4季度']];
      const CYCLE_NOW_YEAR = new Date().getFullYear();
      const CYCLE_YEARS = [];
      for (let y = CYCLE_NOW_YEAR - 1; y <= CYCLE_NOW_YEAR + 3; y++) CYCLE_YEARS.push([String(y), y + '年']);
      let cycleType = firstItem.cycleType || 'MONTH';
      let cycleYear = String(firstItem.cycleYear || CYCLE_NOW_YEAR);
      let cycleValue = String(firstItem.cycleValue || (cycleType === 'QUARTER' ? 1 : new Date().getMonth() + 1));
      const cycleTypeSel = UI.selectField([['MONTH', '月度'], ['QUARTER', '季度'], ['ONE_TIME', '一次性订单']], cycleType, {
        onchange: () => {
          cycleType = cycleTypeSel.value;
          cycleValue = cycleType === 'QUARTER' ? '1' : String(new Date().getMonth() + 1);
          renderCycle();
        },
      });
      const cycleBox = UI.h('span', { class: 'cycle-duo' });
      function renderCycle() {
        cycleBox.innerHTML = '';
        /* 一次性订单与月度一致：同样选择年 + 月 */
        const ySel = UI.selectField(CYCLE_YEARS, cycleYear, { onchange: () => { cycleYear = ySel.value; } });
        const vSel = UI.selectField(cycleType === 'QUARTER' ? CYCLE_QUARTERS : CYCLE_MONTHS, cycleValue,
          { onchange: () => { cycleValue = vSel.value; } });
        cycleBox.appendChild(ySel);
        cycleBox.appendChild(vSel);
      }
      renderCycle();
      /* 交货地点联动交货方式：到场/到站自提 → 固定地点下拉；港口自提 → 港口由供应商报价时确定，无需填写 */
      const PLACE_OPTIONS = {
        PLANT: ['河北陆港保税', '南洋移山', '华增达'],
        STATION_SELF: ['武安站', '康城站', '曹庄镇站'],
      };
      const savedPlace = existing ? (existing.delivery_place || '') : '';
      let placeVal = '';
      const deliveryTypeSel = UI.selectField(
        [['PLANT', DELIVERY.PLANT], ['STATION_SELF', DELIVERY.STATION_SELF], ['PORT_TRUCK', '港口自提']],
        existing ? existing.delivery_type : 'PLANT');
      const placeWrap = UI.h('span', {});
      function renderPlace() {
        const opts = PLACE_OPTIONS[deliveryTypeSel.value];
        placeWrap.innerHTML = '';
        if (opts) {
          const list = opts.slice();
          if (savedPlace && list.indexOf(savedPlace) < 0) list.unshift(savedPlace); // 编辑旧数据：保留原地点
          placeVal = (placeVal && list.indexOf(placeVal) >= 0) ? placeVal : savedPlace;
          if (list.indexOf(placeVal) < 0) placeVal = list[0];
          const sel = UI.selectField(list.map((p) => [p, p]), placeVal,
            { onchange: () => { placeVal = sel.value; } });
          placeWrap.appendChild(sel);
        } else {
          placeVal = '';
          placeWrap.appendChild(UI.h('div', { class: 'hint', style: 'padding:8px 0' }, '—'));
        }
      }
      deliveryTypeSel.addEventListener('change', renderPlace);
      renderPlace();
      const isOtherSel = (val) => !!(otherVariety && String(val) === String(otherVariety.id));
      const f = {
        variety: UI.selectField(vOpts, firstItem.varietyId == null ? '' : String(firstItem.varietyId)),
        /* 「其它」产品名称：编辑已有「其它」需求时回填（存于需求名称） */
        otherName: UI.input('text',
          (existing && isOtherSel(firstItem.varietyId)) ? (existing.demand_name || '') : '',
          { placeholder: '请输入其它产品名称' }),
        grade: UI.input('number', firstItem.grade == null ? '' : String(firstItem.grade), { placeholder: '品位%，如 62' }),
        quantity: UI.input('number', firstItem.quantity == null ? '' : Number(firstItem.quantity).toFixed(2),
          { placeholder: '数量（湿吨）', step: '0.01' }),
        deliveryType: deliveryTypeSel,
        place: placeWrap,
        expectStart: UI.input('date', existing ? UI.fmtDate(existing.expect_arrive_start) : ''),
        expectEnd: UI.input('date', existing ? UI.fmtDate(existing.expect_arrive_end) : ''),
        settleType: UI.selectField(Object.entries(SETTLE), existing ? existing.settle_type : 'COD'),
        settleDays: UI.input('number', existing && existing.settle_days ? String(existing.settle_days) : '',
          { placeholder: '账期天数，如 30' }),
        qualityReq: UI.h('textarea', { rows: 4, style: 'width:100%',
          placeholder: '如：Fe≥62%，水分≤8%；其他补充说明（备注）' }),
      };
      if (existing) f.qualityReq.value = existing.quality_req || '';
      /* 账期结算时账期天数必填：结算方式切换同步红星标记 */
      const settleDaysRow = UI.formRow('账期天数', f.settleDays);
      function updateSettleReq() {
        settleDaysRow.querySelector('label').classList.toggle('req', f.settleType.value === 'CREDIT');
      }
      f.settleType.addEventListener('change', updateSettleReq);
      updateSettleReq();

      /* 「其它」品种模式：仅 产品名称/其它产品名称/品位/周期类型/周期/数量 必填，
         交货、到货、结算等字段转为选填；切换产品名称时同步红星标记 */
      const otherNameRow = UI.formRow('其它产品名称', f.otherName, true,
        '此产品暂只做需求归集，不形成实际订单');
      const deliveryRow = UI.h('div', { class: 'form-row' },
        UI.h('label', { class: 'req' }, '交货方式'), f.deliveryType);
      const placeRow = UI.h('div', { class: 'form-row' },
        UI.h('label', { class: 'req' }, '交货地点'), f.place);
      const expectStartRow = UI.formRow('期望到货起', f.expectStart, true);
      const expectEndRow = UI.formRow('期望到货止', f.expectEnd, true);
      const settleRow = UI.formRow('结算方式', f.settleType, true);
      const otherMode = () => isOtherSel(f.variety.value);
      function updateOtherMode() {
        const other = otherMode();
        otherNameRow.style.display = other ? '' : 'none';
        [deliveryRow, placeRow, expectStartRow, expectEndRow, settleRow].forEach((r) => {
          const lab = r.querySelector('label');
          if (lab) lab.classList.toggle('req', !other);
        });
      }
      f.variety.addEventListener('change', updateOtherMode);
      updateOtherMode();

      /* 变更申请（已提交/待询价/已归集未询价）：先填信息后写理由——变更理由字段置于表单末尾，保存一次性提交 */
      const isChange = row && (row.status === 'SUBMITTED' || row.status === 'TO_INQUIRY' || row.status === 'AGGREGATED'
        || (row.status === 'INQUIRING' && row.aggOpen));
      if (isChange) {
        f.changeReason = UI.h('textarea', { rows: 3, style: 'width:100%',
          placeholder: '请填写变更理由（必填），保存后推送运营端审核' });
      }

      const body = UI.h('form', { onsubmit: (e) => e.preventDefault() },
        UI.h('div', { class: 'hint', style: 'grid-column: 1 / -1; margin-bottom: 8px' },
          '若提报需求，周期类型请选择“月度”、“季度”；若进行实际订单询价，周期类型请选择“一次性订单”。'),
        UI.h('div', { class: 'form-grid' },
          UI.formRow('产品名称', f.variety, true),
          UI.formRow('品位(%)', f.grade, true),
          otherNameRow,
          UI.formRow('周期类型', cycleTypeSel, true),
          UI.formRow('周期', cycleBox, true),
          UI.formRow('数量(湿吨)', f.quantity, true),
          UI.h('div', { class: 'form-duo' }, deliveryRow, placeRow),
          expectStartRow,
          expectEndRow,
          settleRow,
          settleDaysRow,
          UI.h('div', { class: 'form-row full' }, UI.h('label', {}, '质量要求（含备注）'), f.qualityReq),
          isChange ? UI.h('div', { class: 'form-row full' }, UI.h('label', { class: 'req' }, '变更理由'), f.changeReason) : null));

      /* 保存 → 提交 两步合一：首次点击「保 存」（新建/编辑/变更暂存），成功后锁定表单并变「提 交」，
         再次点击推送运营端；已归集/待询价的变更申请保存即直接推送（无需两步） */
      let savedId = null;           // 保存成功后的需求单 id（新建时取自响应）
      const mainBtn = UI.h('button', {
        class: 'primary',
        onclick: async () => {
          if (savedId) {
            /* 第二次点击「提 交」：推送运营端 */
            try {
              await API.post('/demands/' + savedId + '/submit');
              UI.toast('已提交，推送运营端', 'ok');
              m.close(); onDone();
            } catch (e) { /* toast 已提示 */ }
            return;
          }
          if (!f.variety.value) { UI.toast('请选择产品名称', 'err'); return; }
            if (!f.grade.value || !f.quantity.value) { UI.toast('品位、数量为必填', 'err'); return; }
            /* 「其它」品种：其它产品名称必填，交货/到货信息选填 */
            if (otherMode() && !String(f.otherName.value || '').trim()) { UI.toast('请填写其它产品名称', 'err'); return; }
            if (!otherMode()) {
              if (PLACE_OPTIONS[deliveryTypeSel.value] && !placeVal) { UI.toast('请选择交货地点', 'err'); return; }
              if (!f.expectStart.value || !f.expectEnd.value) { UI.toast('期望到货日期为必填', 'err'); return; }
              if (f.expectEnd.value < f.expectStart.value) { UI.toast('期望到货截止日不能早于起始日', 'err'); return; }
            }
            if (f.settleType.value === 'CREDIT' && !f.settleDays.value) { UI.toast('选择账期结算必须填写账期天数', 'err'); return; }
            const vName = (varieties.find((v) => String(v.id) === f.variety.value) || {}).varietyName || '矿产品';
            const payload = {
              /* 变更/编辑保留原需求名称；「其它」品种以填写的其它产品名称作为需求名称 */
              demandName: otherMode()
                ? (String(f.otherName.value || '').trim() || '其它采购需求')
                : ((row && existing && existing.demand_name) || (vName + '采购需求')),
              deliveryType: deliveryTypeSel.value,
              deliveryPlace: placeVal || null,
              expectArriveStart: f.expectStart.value || null,
              expectArriveEnd: f.expectEnd.value || null,
              settleType: f.settleType.value,
              settleDays: f.settleDays.value ? Number(f.settleDays.value) : null,
              qualityReq: f.qualityReq.value,
              items: [{
                varietyId: Number(f.variety.value),
                grade: f.grade.value,
                quantity: Number(f.quantity.value),
                moreLessRate: firstItem.moreLessRate == null ? 5 : Number(firstItem.moreLessRate),
                cycleType: cycleTypeSel.value,
                cycleYear: Number(cycleYear),
                cycleValue: Number(cycleValue),
              }],
            };
            try {
              if (row) {
                const reason = isChange ? String(f.changeReason.value || '').trim() : '';
                if (isChange && !reason) { UI.toast('请填写变更理由', 'err'); return; }
                if ((row.status === 'INQUIRING' && row.aggOpen) || row.status === 'TO_INQUIRY' || row.status === 'AGGREGATED') {
                  /* 已归集（待询价/已归集/询价中未推送）：需求已锁定归集（无本地暂存态），变更申请直接推送运营端审核 */
                  await API.post('/demands/' + row.id + '/change-request',
                    Object.assign(payload, { changeReason: reason }));
                  UI.toast('变更申请已提交运营端审核，审核通过后自动变更', 'ok');
                  m.close(); onDone();
                  return;
                }
                /* 新建草稿/编辑/变更暂存：先保存，按钮转「提 交」后再推送运营端 */
                await API.put('/demands/' + row.id, isChange ? Object.assign(payload, { changeReason: reason }) : payload);
                savedId = row.id;
              }
              else {
                const d = await API.post('/demands', payload);
                savedId = d.id;
              }
              /* 保存成功：锁定表单，按钮变「提 交」 */
              body.querySelectorAll('input,select,textarea').forEach((el) => { el.disabled = true; });
              mainBtn.textContent = '提 交';
              UI.toast('已保存，点击「提交」推送运营端', 'ok');
            } catch (e) { /* toast 已提示 */ }
          },
        }, '保 存');
      const m = UI.modal(isChange ? ('变更申请 · ' + row.demand_no) : (row ? '编辑需求单' : '新建需求单'), body, [mainBtn]);
    }

    await load();
  };

  /* -------- 供应商端：需求归集（运营平台推送的月度/季度计划归集，采购参考，非询价） -------- */
  Pages.demand_group_sup = async function (page) {
    const CYCLE_TYPE = { MONTH: '月度', QUARTER: '季度', ONE_TIME: '一次性订单' };
    const cycleVal = (r) => (r.cycleType && r.cycleYear && r.cycleValue)
      ? r.cycleYear + '年' + (r.cycleType === 'QUARTER' ? '第' + r.cycleValue + '季度' : r.cycleValue + '月') : '—';
    const arriveRange = (m) => (m.expectArriveStart
      ? UI.fmtDate(m.expectArriveStart) + ' ~ ' + UI.fmtDate(m.expectArriveEnd) : '—');

    async function detail(aid) {
      try {
        const d = await API.get('/demand-groups/' + aid);
        const o = d.order;
        UI.modal('需求归集详情 · ' + o.aggNo, UI.h('div', {},
          UI.kv([
            ['归集单号', o.aggNo],
            ['矿种', o.varietyName || '-'],
            ['品位(%)', o.grade == null ? '-' : String(o.grade)],
            ['总吨数(湿吨)', UI.fmtMoney(o.totalQty)],
            ['周期类型', CYCLE_TYPE[o.cycleType] || '—'],
            ['申报周期', cycleVal(o)],
            ['归集时间', UI.fmtDateTime(o.createdAt)],
            ['推送时间', UI.fmtDateTime(o.pushedAt)],
          ]),
          UI.h('h3', { style: 'margin:14px 0 8px' }, '参与明细'),
          UI.table([
            { key: 'companyName', label: '钢厂' },
            { key: 'varietyName', label: '矿种' },
            { key: 'grade', label: '品位(%)', num: true },
            { key: 'quantity', label: '数量(湿吨)', num: true, render: (r) => UI.fmtMoney(r.quantity) },
            { label: '预期到货时间', render: arriveRange },
          ], d.members || [], '暂无参与钢厂')));
      } catch (e) { /* toast 已提示 */ }
    }

    /* 面板结构同「收到的询价」：工具栏提示 + 定高列表区（list-fixed）+ 右下角分页条 */
    const SIZE = 10;
    let pageNo = 1;
    const listCard = UI.h('div', { class: 'card' });
    const listBox = UI.h('div', { class: 'list-fixed' });
    const pagerBox = UI.h('div', {});
    page.appendChild(UI.h('div', { class: 'card' },
      UI.h('div', { class: 'toolbar' },
        UI.h('h3', { style: 'margin:0;border:none;padding:0' }, '需求归集'),
        UI.h('div', { class: 'spacer' }),
        UI.h('span', { class: 'hint' }, '运营平台推送的需求归集信息（月度/季度采购计划），可作为本司采购参考，不用于询价'))));
    page.appendChild(listCard);
    listCard.appendChild(listBox);
    listCard.appendChild(pagerBox);

    async function load() {
      const d = await API.get('/demand-groups' + API.qs({ page: pageNo, size: SIZE }));
      const rows = d.list || [];
      listBox.innerHTML = '';
      listBox.appendChild(UI.table([
        { label: '序号', render: (r) => String(rows.indexOf(r) + 1) },
        { label: '归集单号', render: (r) => UI.h('a', { href: 'javascript:;', style: 'color:#1a5cb0', onclick: () => detail(r.id) }, r.aggNo) },
        { key: 'varietyName', label: '矿种' },
        { key: 'grade', label: '品位(%)', num: true },
        { key: 'totalQty', label: '总吨数(湿吨)', num: true, render: (r) => UI.fmtMoney(r.totalQty) },
        { label: '参与钢厂', render: (r) => UI.h('div', { class: 'cell-xscroll', title: r.companyNames || '' }, r.companyNames || '-') },
        { key: 'memberCount', label: '钢厂数', num: true },
        { label: '周期类型', render: (r) => CYCLE_TYPE[r.cycleType] || '—' },
        { label: '申报周期', render: cycleVal },
        { label: '归集时间', render: (r) => UI.fmtDateTime(r.createdAt) },
        { label: '推送时间', render: (r) => UI.fmtDateTime(r.pushedAt) },
        { label: '操作', render: (r) => UI.h('button', { class: 'sm', onclick: () => detail(r.id) }, '详情') },
      ], rows, '暂无推送的需求归集'));
      pagerBox.innerHTML = '';
      UI.pager(pagerBox, pageNo, SIZE, d.total, (p) => { pageNo = p; load(); });
    }
    await load();
  };

})();
