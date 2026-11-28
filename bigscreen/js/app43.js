/* =============================================================================
 * 政府铁矿石集采平台 · 4:3 大屏主逻辑（Vue3 + DataV + ECharts）
 * -----------------------------------------------------------------------------
 * 结构：
 *   1) 4:3 舞台等比缩放适配（设计稿 1600×1200，居中缩放）
 *   2) Vue3 应用（DataV 组件注册 + 顶栏时钟 + 预警字幕滚动 + 在途清单看板）
 *   3) ECharts 四图：华北物流地图 / 矿价走势 / 采购结构 / 月度成交量
 * 数据来源：window.MOCK_DATA_43（js/data43.js，后续替换为后端接口）
 * ========================================================================== */

/* ---------- 1. 4:3 舞台缩放适配（设计稿 1600×1200，居中等比缩放） ---------- */
const STAGE_W = 1600, STAGE_H = 1200;
function fitStage() {
  const scale = Math.min(window.innerWidth / STAGE_W, window.innerHeight / STAGE_H);
  const stage = document.getElementById('stage');
  if (stage) stage.style.transform = 'scale(' + scale + ')';
}
window.addEventListener('resize', fitStage);

/* ---------- 2. Vue3 应用 ---------- */
const { createApp, reactive, ref, computed, onMounted, onBeforeUnmount } = Vue;
const DataV = window['@kjgl/datav-vue3'];

const app = createApp({
  setup() {
    /* ----- 顶栏实时系统时间（每秒刷新） ----- */
    const sysTime = ref('');
    let clockTimer = null;
    function tickClock() {
      const d = new Date();
      const pad = (n) => String(n).padStart(2, '0');
      const week = ['日', '一', '二', '三', '四', '五', '六'][d.getDay()];
      sysTime.value = d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate())
        + '  星期' + week + '  ' + pad(d.getHours()) + ':' + pad(d.getMinutes()) + ':' + pad(d.getSeconds());
    }

    /* ----- mock 数据（后续对接：替换为接口返回值，见 js/data43.js 顶部说明） ----- */
    const M = window.MOCK_DATA_43;
    const kpi = reactive(M.kpi);
    const flowNodes = reactive(M.flowNodes);

    /* ----- 流程链路蛇形排布：2 行 × 7 列（节点 + 箭头分隔符交替）
     * 第 1 行：节点 1→4 自左向右；第 2 行：节点 8←5 自左向右显示（流程 5→8 实为右→左）
     * 行内数组：name 节点对象 / null = 箭头分隔符（渲染为 → 或 ←） ----- */
    const flowRows = computed(() => {
      const tag = (n, i) => ({ ...n, seq: i + 1 });
      return [
        [tag(flowNodes[0], 0), null, tag(flowNodes[1], 1), null, tag(flowNodes[2], 2), null, tag(flowNodes[3], 3)],
        [tag(flowNodes[7], 7), null, tag(flowNodes[6], 6), null, tag(flowNodes[5], 5), null, tag(flowNodes[4], 4)],
      ];
    });

    /* ----- 预警字幕纵向滚动（列表首尾拼接实现无缝循环，行高 34px） ----- */
    const alerts = reactive(M.alerts);
    const doubledAlerts = computed(() => alerts.concat(alerts));
    const alertOffset = ref(0);
    let alertTimer = null;

    /* ----- 在途物资清单（DataV dv-scroll-board 配置，行数超出自动滚动） ----- */
    const transitConfig = reactive({
      header: M.inTransit.header,
      data: M.inTransit.rows,
      rowNum: 3,                // 可视行数
      headerBGC: 'rgba(36,104,187,.35)',
      oddRowBGC: 'rgba(15,40,80,.25)',
      evenRowBGC: 'rgba(15,40,80,.45)',
      headerHeight: 34,
      rowHeight: 28,
      align: ['center', 'center', 'center', 'center', 'center', 'center'],
    });

    /* ----- ECharts 实例句柄（resize 统一回收） ----- */
    const mapChart = ref(null), priceChart = ref(null), donutChart = ref(null), barChart = ref(null);
    let charts = [];
    let onResize = null;
    /* P3-16：tooltip 文案转义，防 HTML 注入（节点文案当前为本地静态数据，转义兜底） */
    const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

    /* ============ 图表 1：华北物流地图（河北+天津 geoJSON + 港口/钢厂 + 飞线） ============ */
    async function renderMap() {
      // 加载河北 + 天津边界（本地 geoJSON，见 assets/geo/，离线可用），
      // 合并为一张地图注册，保证两板块同投影无缝拼接
      const [hebei, tianjin] = await Promise.all([
        fetch('assets/geo/hebei.json').then((r) => r.json()),
        fetch('assets/geo/tianjin.json').then((r) => r.json()),
      ]);
      echarts.registerMap('hebei_tj', {
        type: 'FeatureCollection',
        features: [...hebei.features, ...tianjin.features],
      });

      const nodes = M.mapNodes, lines = M.mapLines;
      // 按名称索引坐标，生成飞线（起运港 → 收货地）
      const pos = {}; nodes.forEach((n) => { pos[n.name] = [n.lng, n.lat]; });
      const lineData = lines.map((l) => ({ coords: [pos[l.from], pos[l.to]] }));

      const chart = echarts.init(mapChart.value, null, { renderer: 'canvas' });
      chart.setOption({
        tooltip: {
          backgroundColor: 'rgba(8,22,48,.92)', borderColor: '#2468bb',
          textStyle: { color: '#d8e6ff', fontSize: 14, fontFamily: 'SimHei' },
          formatter: (p) => {
            const n = p.data.node; if (!n) return '';
            // P3-16：节点文案转义后拼接，杜绝后续数据接入 API 时的 HTML 注入
            return '<b style="color:#ffc837">' + esc(n.name) + '</b><br>' + esc(n.desc);
          },
        },
        geo: {
          map: 'hebei_tj', roam: false, zoom: 1.12, top: 16, bottom: 6,
          label: { show: true, color: '#5f7db3', fontSize: 13 },
          itemStyle: { areaColor: 'rgba(15,40,80,.75)', borderColor: '#2468bb', borderWidth: 1.2, shadowColor: 'rgba(36,104,187,.6)', shadowBlur: 16 },
          emphasis: { label: { color: '#cfe0ff' }, itemStyle: { areaColor: 'rgba(36,104,187,.75)' } },
        },
        series: [
          /* 货物流向飞线：浅青蓝流光（柔和流动，无花哨特效） */
          { type: 'lines', coordinateSystem: 'geo', zlevel: 2, effect: { show: true, period: 4.5, trailLength: .55, symbol: 'arrow', symbolSize: 7, color: '#32d0e8' },
            lineStyle: { color: '#32d0e8', width: 1.4, opacity: .45, curveness: .25 }, data: lineData },
          /* 普通港口节点 */
          { type: 'scatter', coordinateSystem: 'geo', zlevel: 3,
            symbolSize: (v) => 9 + (v[2] || 0) * .18,
            itemStyle: { color: '#32d0e8', shadowColor: '#32d0e8', shadowBlur: 10 },
            data: nodes.filter((n) => n.type === 'port').map((n) => ({ name: n.name, value: [n.lng, n.lat, n.value], node: n })) },
          /* 黄骅港重点高亮（金色涟漪 + 名称标注） */
          { type: 'effectScatter', coordinateSystem: 'geo', zlevel: 4, rippleEffect: { brushType: 'stroke', scale: 3.2 },
            symbolSize: 17, itemStyle: { color: '#ffc837', shadowColor: '#ffc837', shadowBlur: 16 },
            label: { show: true, formatter: '{b}', position: 'right', distance: 8, color: '#ffc837', fontSize: 14, fontWeight: 700, textShadowColor: 'rgba(8,22,48,.9)', textShadowBlur: 4 },
            data: nodes.filter((n) => n.name === '黄骅港').map((n) => ({ name: n.name, value: [n.lng, n.lat, n.value], node: n })) },
          /* 钢厂收货节点（菱形，金色，带名称标注便于远距离辨识） */
          { type: 'scatter', coordinateSystem: 'geo', zlevel: 3, symbol: 'diamond',
            symbolSize: (v) => 9 + (v[2] || 0) * .15,
            itemStyle: { color: '#ffc837', shadowColor: 'rgba(255,200,55,.8)', shadowBlur: 8 },
            label: { show: true, formatter: '{b}', position: 'right', distance: 8, color: '#ffd977', fontSize: 13, textShadowColor: 'rgba(8,22,48,.9)', textShadowBlur: 4 },
            data: nodes.filter((n) => n.type === 'mill').map((n) => ({ name: n.name, value: [n.lng, n.lat, n.value], node: n })) },
        ],
      });
      charts.push(chart);
    }

    /* ============ 图表 2：矿价走势折线（PB粉 vs 西芒杜粉） ============ */
    function renderPrice() {
      const chart = echarts.init(priceChart.value);
      chart.setOption({
        color: ['#32d0e8', '#ffc837'],
        tooltip: { trigger: 'axis', backgroundColor: 'rgba(8,22,48,.92)', borderColor: '#2468bb', textStyle: { color: '#d8e6ff', fontSize: 14, fontFamily: 'SimHei' } },
        legend: { top: 0, right: 10, textStyle: { color: '#9db8e8', fontSize: 14 }, itemWidth: 18, itemHeight: 3 },
        grid: { left: 10, right: 18, top: 32, bottom: 4, containLabel: true },
        xAxis: { type: 'category', boundaryGap: false, data: M.priceTrend.months, axisLine: { lineStyle: { color: '#2468bb' } }, axisLabel: { color: '#9db8e8', fontSize: 12 } },
        yAxis: { type: 'value', min: 'dataMin', max: 'dataMax', splitLine: { lineStyle: { color: 'rgba(36,104,187,.25)' } }, axisLabel: { color: '#9db8e8', fontSize: 12 } },
        series: [
          { name: 'PB粉', type: 'line', smooth: true, symbol: 'circle', symbolSize: 5, data: M.priceTrend.pb,
            lineStyle: { width: 2.5, shadowColor: 'rgba(50,208,232,.6)', shadowBlur: 8 }, areaStyle: { color: 'rgba(50,208,232,.12)' } },
          { name: '西芒杜粉', type: 'line', smooth: true, symbol: 'circle', symbolSize: 5, data: M.priceTrend.simandou,
            lineStyle: { width: 2.5, type: 'dashed', shadowColor: 'rgba(255,200,55,.5)', shadowBlur: 8 } },
        ],
        animationDuration: 1200, animationEasing: 'cubicOut',
      });
      charts.push(chart);
    }

    /* ============ 图表 3：矿种采购结构占比（环形图） ============ */
    function renderDonut() {
      const chart = echarts.init(donutChart.value);
      chart.setOption({
        color: ['#32d0e8', '#ffc837', '#2468bb', '#7fa8dd'],
        tooltip: { backgroundColor: 'rgba(8,22,48,.92)', borderColor: '#2468bb', textStyle: { color: '#d8e6ff', fontSize: 14, fontFamily: 'SimHei' }, formatter: '{b}：{c} 万吨（{d}%）' },
        legend: { orient: 'vertical', right: 6, top: 'middle', textStyle: { color: '#9db8e8', fontSize: 14 }, itemWidth: 14, itemHeight: 9 },
        series: [{
          type: 'pie', radius: ['52%', '74%'], center: ['40%', '52%'],
          label: { show: false }, labelLine: { show: false },
          itemStyle: { borderColor: '#081630', borderWidth: 3 },
          data: M.varietyDist,
          animationDuration: 1200, animationEasing: 'cubicOut',
        }],
      });
      charts.push(chart);
    }

    /* ============ 图表 4：月度集采成交量（柱状图，浅青蓝渐变） ============ */
    function renderBar() {
      const chart = echarts.init(barChart.value);
      chart.setOption({
        tooltip: { trigger: 'axis', backgroundColor: 'rgba(8,22,48,.92)', borderColor: '#2468bb', textStyle: { color: '#d8e6ff', fontSize: 14, fontFamily: 'SimHei' } },
        grid: { left: 10, right: 14, top: 18, bottom: 4, containLabel: true },
        xAxis: { type: 'category', data: M.monthlyQty.months, axisLine: { lineStyle: { color: '#2468bb' } }, axisLabel: { color: '#9db8e8', fontSize: 12 } },
        yAxis: { type: 'value', splitLine: { lineStyle: { color: 'rgba(36,104,187,.25)' } }, axisLabel: { color: '#9db8e8', fontSize: 12 } },
        series: [{
          type: 'bar', barWidth: 13, data: M.monthlyQty.values,
          itemStyle: { borderRadius: [4, 4, 0, 0], color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: '#32d0e8' }, { offset: 1, color: 'rgba(36,104,187,.35)' }]),
            shadowColor: 'rgba(50,208,232,.4)', shadowBlur: 6 },
        }],
        animationDuration: 1200, animationEasing: 'cubicOut',
      });
      charts.push(chart);
    }

    /* ----- ESC 退出大屏：返回运营看板 -----
     * 若大屏是 window.open 打开的标签页则直接关闭；
     * 直接输入网址打开的场景兜底跳转平台运营看板。 */
    function onKeydown(e) {
      if (e.key !== 'Escape') return;
      window.close();
      setTimeout(() => { location.href = '/#/dashboard'; }, 150);
    }

    /* ---------- 3. 生命周期 ---------- */
    onMounted(async () => {
      fitStage();
      tickClock();
      clockTimer = setInterval(tickClock, 1000);
      window.addEventListener('keydown', onKeydown);
      /* 预警字幕：每 3 秒滚动一行，行高 48px（P3-16：空列表不滚动、回卷定时只挂一次） */
      alertTimer = setInterval(() => {
        if (!alerts.length) { alertOffset.value = 0; return; }
        alertOffset.value += 1;
        if (alertOffset.value >= alerts.length) setTimeout(() => { alertOffset.value = 0; }, 700);
      }, 3000);

      renderPrice(); renderDonut(); renderBar();
      try { await renderMap(); } catch (e) { console.warn('地图加载失败：', e); }

      /* 窗口尺寸变化：重算舞台缩放 + 图表 resize（P3-16：具名监听，卸载时移除） */
      onResize = () => charts.forEach((c) => c.resize());
      window.addEventListener('resize', onResize);
    });
    /* P3-16：卸载清理——移除 resize 监听并 dispose 图表，防内存泄漏 */
    onBeforeUnmount(() => {
      clearInterval(clockTimer); clearInterval(alertTimer);
      window.removeEventListener('keydown', onKeydown);
      if (onResize) window.removeEventListener('resize', onResize);
      charts.forEach((c) => { try { c.dispose(); } catch (e) { /* 已释放则忽略 */ } });
    });

    return { sysTime, kpi, flowNodes, flowRows, doubledAlerts, alertOffset, transitConfig,
             mapChart, priceChart, donutChart, barChart };
  },
});

/* DataV 组件注册（UMD 全局名 "@kjgl/datav-vue3"，兼容 default 导出） */
app.use(DataV && (DataV.default || DataV));
app.mount('#app');
