/* =============================================================================
 * 政府铁矿石集采平台 · 大屏主逻辑（Vue3 + DataV + ECharts）
 * -----------------------------------------------------------------------------
 * 结构：
 *   1) 21:9 舞台等比缩放适配
 *   2) Vue3 应用（DataV 组件注册 + 顶栏时钟 + 预警字幕滚动）
 *   3) ECharts 四图：华北物流地图 / 矿价走势 / 采购结构 / 月度成交量
 * 数据来源：window.MOCK_DATA（js/data.js，后续替换为后端接口）
 * ========================================================================== */

/* ---------- 1. 21:9 舞台缩放适配（设计稿 3440×1440，居中等比缩放） ---------- */
const STAGE_W = 3440, STAGE_H = 1440;
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

    /* ----- mock 数据（后续对接：替换为接口返回值，见 js/data.js 顶部说明） ----- */
    const M = window.MOCK_DATA;
    const kpi = reactive(M.kpi);
    const flowNodes = reactive(M.flowNodes);

    /* ----- 预警字幕纵向滚动（列表首尾拼接实现无缝循环） ----- */
    const alerts = reactive(M.alerts);
    const doubledAlerts = computed(() => alerts.concat(alerts));
    const alertOffset = ref(0);
    let alertTimer = null;

    /* ----- 在途物资清单（DataV dv-scroll-board 配置） ----- */
    const transitConfig = reactive({
      header: M.inTransit.header,
      data: M.inTransit.rows,
      rowNum: 3,                // 可视行数（超出自动滚动）
      headerBGC: 'rgba(36,104,187,.35)',
      oddRowBGC: 'rgba(15,40,80,.25)',
      evenRowBGC: 'rgba(15,40,80,.45)',
      headerHeight: 44,
      rowHeight: 38,
      align: ['center', 'center', 'center', 'center', 'center', 'center'],
    });

    /* ----- ECharts 实例句柄（resize 统一回收） ----- */
    const mapChart = ref(null), priceChart = ref(null), donutChart = ref(null), barChart = ref(null);
    let charts = [];
    let onResize = null;
    /* P3-16：tooltip 文案转义，防 HTML 注入（节点文案当前为本地静态数据，转义兜底） */
    const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

    /* ============ 图表 1：华北物流地图（河北 geoJSON + 港口/钢厂 + 飞线） ============ */
    async function renderMap() {
      // 加载河北地图边界（本地 geoJSON，见 assets/geo/hebei.json）
      const geo = await fetch('assets/geo/hebei.json').then((r) => r.json());
      echarts.registerMap('hebei', geo);

      const nodes = M.mapNodes, lines = M.mapLines;
      // 按名称索引坐标，生成飞线（起运港 → 收货地）
      const pos = {}; nodes.forEach((n) => { pos[n.name] = [n.lng, n.lat]; });
      const lineData = lines.map((l) => ({ coords: [pos[l.from], pos[l.to]] }));

      const chart = echarts.init(mapChart.value, null, { renderer: 'canvas' });
      chart.setOption({
        tooltip: {
          backgroundColor: 'rgba(8,22,48,.92)', borderColor: '#2468bb',
          textStyle: { color: '#d8e6ff', fontSize: 20, fontFamily: 'SimHei' },
          formatter: (p) => {
            const n = p.data.node; if (!n) return '';
            // P3-16：节点文案转义后拼接，杜绝后续数据接入 API 时的 HTML 注入
            return '<b style="color:#ffc837">' + esc(n.name) + '</b><br>' + esc(n.desc);
          },
        },
        geo: {
          map: 'hebei', roam: false, zoom: 1.12, top: 20, bottom: 8,
          label: { show: true, color: '#5f7db3', fontSize: 18 },
          itemStyle: { areaColor: 'rgba(15,40,80,.75)', borderColor: '#2468bb', borderWidth: 1.2, shadowColor: 'rgba(36,104,187,.6)', shadowBlur: 18 },
          emphasis: { label: { color: '#cfe0ff' }, itemStyle: { areaColor: 'rgba(36,104,187,.75)' } },
        },
        series: [
          /* 货物流向飞线：浅青蓝流光 */
          { type: 'lines', coordinateSystem: 'geo', zlevel: 2, effect: { show: true, period: 4.5, trailLength: .55, symbol: 'arrow', symbolSize: 9, color: '#32d0e8' },
            lineStyle: { color: '#32d0e8', width: 1.6, opacity: .45, curveness: .25 }, data: lineData },
          /* 普通港口节点 */
          { type: 'scatter', coordinateSystem: 'geo', zlevel: 3,
            symbolSize: (v) => 10 + (v[2] || 0) * .22,
            itemStyle: { color: '#32d0e8', shadowColor: '#32d0e8', shadowBlur: 12 },
            data: nodes.filter((n) => n.type === 'port').map((n) => ({ name: n.name, value: [n.lng, n.lat, n.value], node: n })) },
          /* 黄骅港重点高亮（金色涟漪） */
          { type: 'effectScatter', coordinateSystem: 'geo', zlevel: 4, rippleEffect: { brushType: 'stroke', scale: 3.2 },
            symbolSize: 20, itemStyle: { color: '#ffc837', shadowColor: '#ffc837', shadowBlur: 18 },
            data: nodes.filter((n) => n.name === '黄骅港').map((n) => ({ name: n.name, value: [n.lng, n.lat, n.value], node: n })) },
          /* 钢厂收货节点（菱形） */
          { type: 'scatter', coordinateSystem: 'geo', zlevel: 3, symbol: 'diamond',
            symbolSize: (v) => 10 + (v[2] || 0) * .18,
            itemStyle: { color: '#ffc837', shadowColor: 'rgba(255,200,55,.8)', shadowBlur: 10 },
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
        tooltip: { trigger: 'axis', backgroundColor: 'rgba(8,22,48,.92)', borderColor: '#2468bb', textStyle: { color: '#d8e6ff', fontSize: 20, fontFamily: 'SimHei' } },
        legend: { top: 0, right: 10, textStyle: { color: '#9db8e8', fontSize: 20 }, itemWidth: 22, itemHeight: 3 },
        grid: { left: 12, right: 20, top: 46, bottom: 6, containLabel: true },
        xAxis: { type: 'category', boundaryGap: false, data: M.priceTrend.months, axisLine: { lineStyle: { color: '#2468bb' } }, axisLabel: { color: '#9db8e8', fontSize: 18 } },
        yAxis: { type: 'value', min: 'dataMin', max: 'dataMax', splitLine: { lineStyle: { color: 'rgba(36,104,187,.25)' } }, axisLabel: { color: '#9db8e8', fontSize: 18 } },
        series: [
          { name: 'PB粉', type: 'line', smooth: true, symbol: 'circle', symbolSize: 6, data: M.priceTrend.pb,
            lineStyle: { width: 3, shadowColor: 'rgba(50,208,232,.6)', shadowBlur: 10 }, areaStyle: { color: 'rgba(50,208,232,.12)' } },
          { name: '西芒杜粉', type: 'line', smooth: true, symbol: 'circle', symbolSize: 6, data: M.priceTrend.simandou,
            lineStyle: { width: 3, type: 'dashed', shadowColor: 'rgba(255,200,55,.5)', shadowBlur: 10 } },
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
        tooltip: { backgroundColor: 'rgba(8,22,48,.92)', borderColor: '#2468bb', textStyle: { color: '#d8e6ff', fontSize: 20, fontFamily: 'SimHei' }, formatter: '{b}：{c} 万吨（{d}%）' },
        legend: { orient: 'vertical', right: 6, top: 'middle', textStyle: { color: '#9db8e8', fontSize: 20 }, itemWidth: 16, itemHeight: 10 },
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

    /* ============ 图表 4：月度集采成交量（柱状图） ============ */
    function renderBar() {
      const chart = echarts.init(barChart.value);
      chart.setOption({
        tooltip: { trigger: 'axis', backgroundColor: 'rgba(8,22,48,.92)', borderColor: '#2468bb', textStyle: { color: '#d8e6ff', fontSize: 20, fontFamily: 'SimHei' } },
        grid: { left: 12, right: 16, top: 24, bottom: 6, containLabel: true },
        xAxis: { type: 'category', data: M.monthlyQty.months, axisLine: { lineStyle: { color: '#2468bb' } }, axisLabel: { color: '#9db8e8', fontSize: 18 } },
        yAxis: { type: 'value', splitLine: { lineStyle: { color: 'rgba(36,104,187,.25)' } }, axisLabel: { color: '#9db8e8', fontSize: 18 } },
        series: [{
          type: 'bar', barWidth: 16, data: M.monthlyQty.values,
          itemStyle: { borderRadius: [4, 4, 0, 0], color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: '#32d0e8' }, { offset: 1, color: 'rgba(36,104,187,.35)' }]),
            shadowColor: 'rgba(50,208,232,.4)', shadowBlur: 8 },
        }],
        animationDuration: 1200, animationEasing: 'cubicOut',
      });
      charts.push(chart);
    }

    /* ---------- 3. 生命周期 ---------- */
    onMounted(async () => {
      fitStage();
      tickClock();
      clockTimer = setInterval(tickClock, 1000);
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
      if (onResize) window.removeEventListener('resize', onResize);
      charts.forEach((c) => { try { c.dispose(); } catch (e) { /* 已释放则忽略 */ } });
    });

    return { sysTime, kpi, flowNodes, doubledAlerts, alertOffset, transitConfig,
             mapChart, priceChart, donutChart, barChart };
  },
});

/* DataV 组件注册（UMD 全局名 "@kjgl/datav-vue3"，兼容 default 导出） */
app.use(DataV && (DataV.default || DataV));
app.mount('#app');
