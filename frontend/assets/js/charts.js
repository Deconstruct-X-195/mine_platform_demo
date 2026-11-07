/* ============ 轻量 Canvas 图表（折线/柱状/饼图） ============ */
const Charts = {
  _prep(canvas) {
    const dpr = window.devicePixelRatio || 1;
    const rect = canvas.getBoundingClientRect(); // 测 canvas 自身（排除父容器 padding，避免溢出）
    canvas.width = rect.width * dpr;
    canvas.height = rect.height * dpr;
    canvas.style.width = rect.width + 'px';
    canvas.style.height = rect.height + 'px';
    const ctx = canvas.getContext('2d');
    ctx.scale(dpr, dpr);
    return { ctx, W: rect.width, H: rect.height };
  },

  /* series: [{name, color, data:[y...]}], labels: [x...]
     options: unit, area(渐变面积，默认关), smooth(平滑曲线), hover(悬停tooltip), animate(入场动画) */
  line(canvas, labels, series, { unit = '', area = false, smooth = true, hover = true, animate = true } = {}) {
    const chart = this._drawLine(canvas, labels, series, { unit, area, smooth }, 1);
    if (!chart) return;
    if (animate) {
      // 入场：线条从左到右展开（600ms）
      const start = performance.now();
      const dur = 600;
      const tick = now => {
        const p = Math.min(1, (now - start) / dur);
        const eased = 1 - Math.pow(1 - p, 3); // easeOutCubic
        this._drawLine(canvas, labels, series, { unit, area, smooth }, eased);
        if (p < 1) requestAnimationFrame(tick);
      };
      requestAnimationFrame(tick);
    }
    if (!hover) return;
    // 悬停：竖向参考线 + 高亮点 + tooltip
    canvas.onmousemove = e => {
      const rect = canvas.getBoundingClientRect();
      const mx = e.clientX - rect.left;
      const idx = chart.pxToIndex(mx);
      if (idx === null) { canvas.onmouseleave && canvas.onmouseleave(e); return; }
      this._drawLine(canvas, labels, series, { unit, area, smooth }, 1, idx);
    };
    canvas.onmouseleave = () => this._drawLine(canvas, labels, series, { unit, area, smooth }, 1);
  },

  /* 折线图核心绘制，progress: 0~1 展开进度，hoverIdx: 悬停索引 */
  _drawLine(canvas, labels, series, { unit, area, smooth }, progress, hoverIdx = null) {
    const { ctx, W, H } = this._prep(canvas);
    const pad = { l: 50, r: 24, t: 26, b: 30 };
    const all = series.flatMap(s => s.data).filter(v => v !== null && v !== undefined);
    if (!all.length || !labels.length) { this._empty(ctx, W, H); return null; }
    // Y轴范围：价格类数据不从0起，留 8% 上下边距
    let min = Math.min(...all), max = Math.max(...all);
    const span = (max - min) || Math.abs(max) || 1;
    min -= span * 0.08; max += span * 0.12;
    const plotW = W - pad.l - pad.r, plotH = H - pad.t - pad.b;
    const px = i => pad.l + plotW * (labels.length === 1 ? 0.5 : i / (labels.length - 1));
    const py = v => H - pad.b - plotH * (v - min) / (max - min);
    const pxToIndex = mx => {
      if (labels.length === 1) return mx >= pad.l - 20 && mx <= W - pad.r + 20 ? 0 : null;
      if (mx < pad.l - 20 || mx > W - pad.r + 20) return null;
      return Math.max(0, Math.min(labels.length - 1,
        Math.round((mx - pad.l) / plotW * (labels.length - 1))));
    };
    // 横向虚线网格 + Y轴刻度（5档，取整到刻度友好值）
    const rawStep = (max - min) / 5;
    const mag = Math.pow(10, Math.floor(Math.log10(rawStep)));
    const step = [1, 2, 2.5, 5, 10].map(m => m * mag).find(s => s >= rawStep) || rawStep * 2;
    const gMin = Math.floor(min / step) * step;
    ctx.font = '11px -apple-system, "Segoe UI", "Microsoft YaHei", sans-serif';
    for (let v = gMin; v <= max + step * 0.01; v += step) {
      const y = py(v);
      if (y > H - pad.b - 6) continue;   // 最下行刻度与横轴保持距离：不贴线、不压日期标签
      ctx.strokeStyle = 'rgba(29,33,41,.06)';
      ctx.setLineDash([4, 4]);
      ctx.beginPath(); ctx.moveTo(pad.l, y); ctx.lineTo(W - pad.r, y); ctx.stroke();
      ctx.setLineDash([]);
      ctx.fillStyle = '#86909c'; ctx.textAlign = 'right';
      ctx.fillText(this._fmt(v), pad.l - 8, y + 4);
    }
    // X轴标签（智能稀疏）
    ctx.textAlign = 'center';
    const stepX = Math.ceil(labels.length / Math.max(1, Math.floor(plotW / 64)));
    labels.forEach((lb, i) => {
      if (i % stepX === 0 || i === labels.length - 1) {
        ctx.fillStyle = '#86909c';
        ctx.fillText(lb, px(i), H - pad.b + 20);
      }
    });
    // 裁剪到绘图区（动画展开时使用）
    ctx.save();
    ctx.beginPath();
    if (progress < 1) ctx.rect(pad.l - 6, 0, (plotW + 12) * progress, H);
    else ctx.rect(pad.l - 6, 0, plotW + 12, H);
    ctx.clip();
    // 面积渐变 + 折线
    series.forEach(s => {
      const pts = [];
      s.data.forEach((v, i) => { if (v !== null && v !== undefined) pts.push([px(i), py(v), i]); });
      if (!pts.length) return;
      if (area) {
        const grad = ctx.createLinearGradient(0, pad.t, 0, H - pad.b);
        grad.addColorStop(0, s.color + '2e'); // ~18% 透明
        grad.addColorStop(1, s.color + '00');
        ctx.fillStyle = grad;
        ctx.beginPath();
        ctx.moveTo(pts[0][0], H - pad.b);
        this._trace(ctx, pts, smooth);
        ctx.lineTo(pts[pts.length - 1][0], H - pad.b);
        ctx.closePath(); ctx.fill();
      }
      ctx.strokeStyle = s.color; ctx.lineWidth = 2; ctx.lineJoin = 'round'; ctx.lineCap = 'round';
      ctx.shadowColor = s.color + '33'; ctx.shadowBlur = 6; ctx.shadowOffsetY = 2;
      ctx.beginPath();
      this._trace(ctx, pts, smooth);
      ctx.stroke();
      ctx.shadowColor = 'transparent'; ctx.shadowBlur = 0; ctx.shadowOffsetY = 0;
      // 常驻数据点不绘制（悬停时在参考线上高亮），保持曲线干净
    });
    ctx.restore();
    // 悬停：参考线 + tooltip
    if (hoverIdx !== null && hoverIdx >= 0 && hoverIdx < labels.length) {
      const hx = px(hoverIdx);
      ctx.strokeStyle = 'rgba(29,33,41,.18)'; ctx.lineWidth = 1; ctx.setLineDash([3, 3]);
      ctx.beginPath(); ctx.moveTo(hx, pad.t); ctx.lineTo(hx, H - pad.b); ctx.stroke();
      ctx.setLineDash([]);
      series.forEach(s => {
        const v = s.data[hoverIdx];
        if (v === null || v === undefined) return;
        ctx.beginPath(); ctx.arc(hx, py(v), 4.6, 0, 7);
        ctx.fillStyle = s.color + '2a'; ctx.fill();
        ctx.beginPath(); ctx.arc(hx, py(v), 3, 0, 7);
        ctx.fillStyle = s.color; ctx.fill();
        ctx.strokeStyle = '#fff'; ctx.lineWidth = 1.5; ctx.stroke();
      });
      // tooltip 内容行
      const rows = [labels[hoverIdx],
        ...series.map(s => {
          const v = s.data[hoverIdx];
          return { name: s.name, color: s.color, text: v === null || v === undefined ? '-' : this._fmt(v) + unit };
        })];
      const tw = Math.max(...rows.map((r, i) => i === 0 ? 0 : ctx.measureText(r.name + ' ' + r.text).width)) + 46;
      const th = 16 + rows.length * 18;
      let tx = hx + 12;
      if (tx + tw > W - 6) tx = hx - tw - 12;
      const ty = Math.max(6, Math.min(H - th - 6, pad.t + 4));
      ctx.save();
      ctx.shadowColor = 'rgba(29,33,41,.14)'; ctx.shadowBlur = 12; ctx.shadowOffsetY = 3;
      ctx.fillStyle = '#fff';
      ctx.beginPath(); ctx.roundRect(tx, ty, tw, th, 8); ctx.fill();
      ctx.restore();
      ctx.strokeStyle = 'rgba(29,33,41,.08)'; ctx.lineWidth = 1;
      ctx.beginPath(); ctx.roundRect(tx, ty, tw, th, 8); ctx.stroke();
      ctx.textAlign = 'left';
      ctx.fillStyle = '#1f2329'; ctx.font = 'bold 12px -apple-system, "Segoe UI", "Microsoft YaHei", sans-serif';
      ctx.fillText(rows[0], tx + 12, ty + 18);
      rows.slice(1).forEach((r, i) => {
        const ry = ty + 34 + i * 18;
        ctx.fillStyle = r.color;
        ctx.fillRect(tx + 12, ry - 7, 8, 3);
        ctx.fillStyle = '#4e5969'; ctx.font = '12px -apple-system, "Segoe UI", "Microsoft YaHei", sans-serif';
        ctx.fillText(r.name, tx + 24, ry - 1);
        ctx.fillStyle = '#1f2329'; ctx.font = 'bold 12px -apple-system, "Segoe UI", "Microsoft YaHei", sans-serif';
        ctx.textAlign = 'right';
        ctx.fillText(r.text, tx + tw - 10, ry - 1);
        ctx.textAlign = 'left';
      });
    }
    return { pxToIndex };
  },

  /* 路径描迹：smooth 时用相邻中点的二次贝塞尔（经典平滑），否则直线 */
  _trace(ctx, pts, smooth) {
    ctx.moveTo(pts[0][0], pts[0][1]);
    if (!smooth || pts.length < 3) {
      pts.slice(1).forEach(p => ctx.lineTo(p[0], p[1]));
      return;
    }
    for (let i = 1; i < pts.length - 1; i++) {
      const xc = (pts[i][0] + pts[i + 1][0]) / 2;
      const yc = (pts[i][1] + pts[i + 1][1]) / 2;
      ctx.quadraticCurveTo(pts[i][0], pts[i][1], xc, yc);
    }
    ctx.lineTo(pts[pts.length - 1][0], pts[pts.length - 1][1]);
  },

  bar(canvas, labels, series, { unit = '' } = {}) {
    const { ctx, W, H } = this._prep(canvas);
    const pad = { l: 56, r: 16, t: 18, b: 34 };
    const all = series.flatMap(s => s.data);
    if (!all.length) { this._empty(ctx, W, H); return; }
    const max = Math.max(...all, 1) * 1.15;
    const groupW = (W - pad.l - pad.r) / labels.length;
    const bw = Math.min(38, (groupW * 0.7) / series.length);
    ctx.font = '11px sans-serif'; ctx.fillStyle = '#86909c'; ctx.strokeStyle = 'rgba(29,33,41,.07)';
    for (let i = 0; i <= 4; i++) {
      const v = max * i / 4, y = H - pad.b - (H - pad.t - pad.b) * v / max;
      ctx.beginPath(); ctx.moveTo(pad.l, y); ctx.lineTo(W - pad.r, y); ctx.stroke();
      ctx.textAlign = 'right'; ctx.fillText(this._fmt(v) + unit, pad.l - 6, y + 4);
    }
    ctx.textAlign = 'center';
    labels.forEach((lb, i) => ctx.fillText(lb, pad.l + groupW * (i + 0.5), H - pad.b + 18));
    labels.forEach((_, i) => {
      series.forEach((s, si) => {
        const v = s.data[i] || 0;
        const x = pad.l + groupW * i + (groupW - bw * series.length) / 2 + bw * si;
        const y = H - pad.b - (H - pad.t - pad.b) * v / max;
        ctx.fillStyle = s.color;
        ctx.beginPath();
        ctx.roundRect(x, y, bw - 3, H - pad.b - y, [4, 4, 0, 0]);
        ctx.fill();
      });
    });
  },

  pie(canvas, items, { unit = '' } = {}) {
    const { ctx, W, H } = this._prep(canvas);
    const total = items.reduce((s, it) => s + it.value, 0);
    if (!total) { this._empty(ctx, W, H); return; }
    const cx = W / 2, cy = H / 2, r = Math.min(W, H) / 2 - 24;
    let angle = -Math.PI / 2;
    items.forEach(it => {
      const a = it.value / total * Math.PI * 2;
      ctx.beginPath();
      ctx.moveTo(cx, cy);
      ctx.arc(cx, cy, r, angle, angle + a);
      ctx.closePath();
      ctx.fillStyle = it.color;
      ctx.fill();
      const mid = angle + a / 2;
      if (a > 0.35) {
        ctx.fillStyle = '#fff'; ctx.font = 'bold 12px sans-serif'; ctx.textAlign = 'center';
        ctx.fillText(Math.round(it.value / total * 100) + '%', cx + Math.cos(mid) * r * 0.65, cy + Math.sin(mid) * r * 0.65 + 4);
      }
      angle += a;
    });
    // 中心留白
    ctx.beginPath(); ctx.arc(cx, cy, r * 0.55, 0, 7); ctx.fillStyle = '#fff'; ctx.fill();
    ctx.fillStyle = '#1f2329'; ctx.font = 'bold 15px sans-serif'; ctx.textAlign = 'center';
    ctx.fillText(this._fmt(total) + unit, cx, cy + 2);
  },

  _fmt(v) {
    if (Math.abs(v) >= 10000) return (v / 10000).toFixed(1) + 'w';
    return Number.isInteger(v) ? v : v.toFixed(2);
  },
  _empty(ctx, W, H) {
    ctx.fillStyle = '#86909c'; ctx.font = '13px sans-serif'; ctx.textAlign = 'center';
    ctx.fillText('暂无数据', W / 2, H / 2);
  }
};
