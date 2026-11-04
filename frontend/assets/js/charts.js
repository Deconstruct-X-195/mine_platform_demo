/* ============ 轻量 Canvas 图表（折线/柱状/饼图） ============ */
const Charts = {
  _prep(canvas) {
    const dpr = window.devicePixelRatio || 1;
    const rect = canvas.parentElement.getBoundingClientRect();
    canvas.width = rect.width * dpr;
    canvas.height = rect.height * dpr;
    canvas.style.width = rect.width + 'px';
    canvas.style.height = rect.height + 'px';
    const ctx = canvas.getContext('2d');
    ctx.scale(dpr, dpr);
    return { ctx, W: rect.width, H: rect.height };
  },

  /* series: [{name, color, data:[y...]}], labels: [x...] */
  line(canvas, labels, series, { unit = '' } = {}) {
    const { ctx, W, H } = this._prep(canvas);
    const pad = { l: 56, r: 16, t: 18, b: 34 };
    const all = series.flatMap(s => s.data).filter(v => v !== null && v !== undefined);
    if (!all.length || !labels.length) { this._empty(ctx, W, H); return; }
    let max = Math.max(...all), min = Math.min(0, ...all);
    if (max === min) max = min + 1;
    max += (max - min) * 0.12;
    const px = i => pad.l + (W - pad.l - pad.r) * (labels.length === 1 ? 0.5 : i / (labels.length - 1));
    const py = v => H - pad.b - (H - pad.t - pad.b) * (v - min) / (max - min);
    // 网格与Y轴
    ctx.font = '11px sans-serif'; ctx.fillStyle = '#86909c'; ctx.strokeStyle = 'rgba(29,33,41,.07)';
    for (let i = 0; i <= 4; i++) {
      const v = min + (max - min) * i / 4, y = py(v);
      ctx.beginPath(); ctx.moveTo(pad.l, y); ctx.lineTo(W - pad.r, y); ctx.stroke();
      ctx.textAlign = 'right';
      ctx.fillText(this._fmt(v) + unit, pad.l - 6, y + 4);
    }
    // X轴标签
    ctx.textAlign = 'center';
    const step = Math.ceil(labels.length / Math.max(1, Math.floor((W - pad.l - pad.r) / 64)));
    labels.forEach((lb, i) => {
      if (i % step === 0 || i === labels.length - 1) ctx.fillText(lb, px(i), H - pad.b + 18);
    });
    // 折线
    series.forEach(s => {
      ctx.strokeStyle = s.color; ctx.lineWidth = 2; ctx.lineJoin = 'round';
      ctx.beginPath();
      let started = false;
      s.data.forEach((v, i) => {
        if (v === null || v === undefined) { started = false; return; }
        if (!started) { ctx.moveTo(px(i), py(v)); started = true; }
        else ctx.lineTo(px(i), py(v));
      });
      ctx.stroke();
      // 数据点
      s.data.forEach((v, i) => {
        if (v === null || v === undefined) return;
        ctx.beginPath(); ctx.arc(px(i), py(v), 3, 0, 7);
        ctx.fillStyle = '#fff'; ctx.fill(); ctx.strokeStyle = s.color; ctx.lineWidth = 2; ctx.stroke();
      });
    });
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
