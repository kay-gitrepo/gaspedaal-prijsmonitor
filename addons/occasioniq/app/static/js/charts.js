/* Herbruikbare SVG-grafieken zonder bibliotheek: lijn, trap (prijzen veranderen in stappen) en puntenwolk.
 * Aanwijswaarden werken met muis, aanraking en toetsenbord (pijltjes) via gedelegeerde handlers;
 * de aanwijswaarde staat in de SVG zelf, zodat er geen inline stijl nodig is. */
import {datum, esc, euro, fmt} from './format.js';

const DAY = 86400000;

function niceStep(range, count) {
  const raw = range / Math.max(1, count);
  const mag = 10 ** Math.floor(Math.log10(raw || 1));
  const norm = raw / mag;
  return (norm <= 1 ? 1 : norm <= 2 ? 2 : norm <= 2.5 ? 2.5 : norm <= 5 ? 5 : 10) * mag;
}

function ticks(lo, hi, count) {
  if (hi === lo) return [lo];
  const step = niceStep(hi - lo, count);
  const out = [];
  for (let v = Math.ceil(lo / step) * step; v <= hi + step * 1e-9; v += step) out.push(Math.round(v * 100) / 100);
  return out;
}

const shortMoney = v => (Math.abs(v) >= 1000 ? `€ ${fmt(Math.round(v / 100) / 10)}k` : euro(v));

/**
 * @param {object} o
 *  series: [{name, points: [{x, y, label?, marker?, href?, cls?}], type: 'line'|'step'|'scatter', cls}]
 *  band: {points: [{x, lo, hi}]}   hlines: [{y, label, cls}]   until: datum waartoe een trap doorloopt
 *  xType: 'date' | 'number'   money: true   title   summary (tekst voor schermlezers)
 */
export function chart(o) {
  const series = (o.series || []).filter(s => s.points?.length);
  const all = series.flatMap(s => s.points);
  if (!all.length) return '<p class="muted">Nog geen metingen.</p>';
  const money = o.money !== false;
  const isDate = (o.xType || 'date') === 'date';
  const xv = p => (isDate ? new Date(p.x).getTime() : Number(p.x));
  const yFmt = v => (money ? euro(v) : fmt(v));
  const xFmt = v => (isDate ? datum(new Date(v).toISOString()) : fmt(v));
  if (all.length === 1 && !o.band && series[0].type !== 'scatter') {
    return `<div class="chart-single"><div class="stat-value">${yFmt(all[0].y)}</div>
      <p class="muted small">Eerste meting · ${esc(xFmt(xv(all[0])))}</p></div>`;
  }
  const narrow = window.matchMedia('(max-width: 760px)').matches;
  const w = narrow ? 360 : 720;
  const h = o.height || (narrow ? 220 : 260);
  const pad = {l: narrow ? 52 : 64, r: 12, t: 14, b: 30};
  const ys = all.map(p => p.y).concat((o.band?.points || []).flatMap(p => [p.lo, p.hi]))
    .concat((o.hlines || []).map(l => l.y)).filter(v => v != null && Number.isFinite(v));
  const xs = all.map(xv).concat((o.band?.points || []).map(xv));
  if (o.until) xs.push(new Date(o.until).getTime());
  let [ylo, yhi] = [Math.min(...ys), Math.max(...ys)];
  if (ylo === yhi) [ylo, yhi] = [ylo * 0.98, yhi * 1.02 || 1];
  const yPad = (yhi - ylo) * 0.08;
  ylo -= yPad;
  yhi += yPad;
  let [xlo, xhi] = [Math.min(...xs), Math.max(...xs)];
  if (xlo === xhi) [xlo, xhi] = [xlo - (isDate ? DAY : 1), xhi + (isDate ? DAY : 1)];
  const X = v => pad.l + (v - xlo) / (xhi - xlo) * (w - pad.l - pad.r);
  const Y = v => pad.t + (yhi - v) / (yhi - ylo) * (h - pad.t - pad.b);
  const yt = ticks(ylo, yhi, narrow ? 3 : 4).filter(v => v >= ylo && v <= yhi);
  const grid = yt.map(v => `<line class="grid-line" x1="${pad.l}" x2="${w - pad.r}" y1="${Y(v).toFixed(1)}"
    y2="${Y(v).toFixed(1)}"/><text x="${pad.l - 6}" y="${(Y(v) + 4).toFixed(1)}" text-anchor="end">${esc(money
    ? shortMoney(v) : fmt(v))}</text>`).join('');
  const xt = isDate ? [xlo, (xlo + xhi) / 2, xhi] : ticks(xlo, xhi, narrow ? 3 : 5).filter(v => v >= xlo && v <= xhi);
  const xlabels = xt.map((v, i) => {
    const anchor = isDate ? (i === 0 ? 'start' : i === xt.length - 1 ? 'end' : 'middle') : 'middle';
    return `<text x="${X(v).toFixed(1)}" y="${h - 8}" text-anchor="${anchor}">${esc(xFmt(v))}</text>`;
  }).join('');
  let body = '';
  if (o.band?.points?.length > 1) {
    const bp = [...o.band.points].sort((a, b) => xv(a) - xv(b));
    const top = bp.map(p => `${X(xv(p)).toFixed(1)},${Y(p.hi).toFixed(1)}`);
    const bottom = bp.slice().reverse().map(p => `${X(xv(p)).toFixed(1)},${Y(p.lo).toFixed(1)}`);
    body += `<polygon class="band" points="${top.concat(bottom).join(' ')}"/>`;
  }
  for (const l of o.hlines || []) {
    body += `<line class="hline ${esc(l.cls || '')}" x1="${pad.l}" x2="${w - pad.r}" y1="${Y(l.y).toFixed(1)}"
      y2="${Y(l.y).toFixed(1)}"/><text class="hline-label" x="${w - pad.r - 4}" y="${(Y(l.y) - 5).toFixed(1)}"
      text-anchor="end">${esc(l.label || '')}</text>`;
  }
  const hover = [];
  for (const s of series) {
    const pts = [...s.points].sort((a, b) => xv(a) - xv(b));
    const cls = esc(s.cls || '');
    if (s.type === 'scatter') {
      body += pts.map(p => {
        const dot = `<circle class="pt ${esc(p.cls || cls)}" cx="${X(xv(p)).toFixed(1)}" cy="${Y(p.y).toFixed(1)}" r="5"/>`;
        return p.href ? `<a href="${esc(p.href)}" aria-label="${esc(p.label || '')}">${dot}</a>` : dot;
      }).join('');
    } else {
      let d = '';
      pts.forEach((p, i) => {
        const x = X(xv(p)).toFixed(1);
        const y = Y(p.y).toFixed(1);
        if (i === 0) d += `M ${x} ${y}`;
        else if (s.type === 'step') d += ` H ${x} V ${y}`;
        else d += ` L ${x} ${y}`;
      });
      if (s.type === 'step' && o.until) d += ` H ${X(new Date(o.until).getTime()).toFixed(1)}`;
      body += `<path class="line ${cls}" d="${d}"/>`;
      body += pts.filter(p => p.marker).map(p => `<circle class="marker marker-${esc(p.marker)}"
        cx="${X(xv(p)).toFixed(1)}" cy="${Y(p.y).toFixed(1)}" r="4.5"/>`).join('');
    }
    pts.forEach(p => hover.push([Math.round(X(xv(p)) * 10) / 10, Math.round(Y(p.y) * 10) / 10,
      `${xFmt(xv(p))} · ${yFmt(p.y)}${p.label ? ' · ' + p.label : ''}${series.length > 1 && s.name ? ` (${s.name})` : ''}`]));
  }
  hover.sort((a, b) => a[0] - b[0]);
  const first = series[0].points;
  const summary = o.summary || `${o.title || 'Grafiek'}: ${first.length} metingen, van ${yFmt(first[0].y)} tot `
    + `${yFmt(first.at(-1).y)}; laagste ${yFmt(Math.min(...first.map(p => p.y)))}.`;
  return `<div class="chart-wrap" data-chart="${esc(JSON.stringify(hover))}" data-w="${w}" data-h="${h}" tabindex="0"
    role="img" aria-label="${esc(summary)}"><svg class="chart" viewBox="0 0 ${w} ${h}" aria-hidden="true">${grid}${body}
    ${xlabels}<line class="cursor" x1="0" x2="0" y1="${pad.t}" y2="${h - pad.b}" visibility="hidden"/>
    <circle class="cursor-dot" r="5" cx="0" cy="0" visibility="hidden"/>
    <g class="chart-tip" visibility="hidden"><rect rx="6" height="24"/><text y="16"></text></g></svg></div>`;
}

/* ---------- Aanwijswaarden ---------- */
function show(wrap, index) {
  const pts = JSON.parse(wrap.dataset.chart);
  if (!pts.length) return;
  const i = Math.max(0, Math.min(pts.length - 1, index));
  wrap.dataset.index = String(i);
  const [x, y, text] = pts[i];
  const svg = wrap.querySelector('svg');
  const w = Number(wrap.dataset.w);
  const line = svg.querySelector('.cursor');
  const dot = svg.querySelector('.cursor-dot');
  line.setAttribute('x1', x);
  line.setAttribute('x2', x);
  line.setAttribute('visibility', 'visible');
  dot.setAttribute('cx', x);
  dot.setAttribute('cy', y);
  dot.setAttribute('visibility', 'visible');
  const tip = svg.querySelector('.chart-tip');
  const label = tip.querySelector('text');
  const fs = Number(svg.getAttribute('font-size')) || 12;
  label.textContent = text;
  const tw = label.getComputedTextLength() + fs * 1.4;
  const th = fs * 2;
  const tx = Math.min(Math.max(2, x - tw / 2), w - tw - 2);
  const ty = Math.max(2, y - th - fs);
  tip.querySelector('rect').setAttribute('width', tw);
  tip.querySelector('rect').setAttribute('height', th);
  label.setAttribute('x', fs * 0.7);
  label.setAttribute('y', fs * 1.35);
  tip.setAttribute('transform', `translate(${tx.toFixed(1)} ${ty.toFixed(1)})`);
  tip.setAttribute('visibility', 'visible');
}

function hide(wrap) {
  wrap.querySelectorAll('.cursor,.cursor-dot,.chart-tip').forEach(el => el.setAttribute('visibility', 'hidden'));
}

function nearest(wrap, clientX) {
  const pts = JSON.parse(wrap.dataset.chart);
  const rect = wrap.querySelector('svg').getBoundingClientRect();
  const x = (clientX - rect.left) / rect.width * Number(wrap.dataset.w);
  let best = 0;
  pts.forEach((p, i) => {
    if (Math.abs(p[0] - x) < Math.abs(pts[best][0] - x)) best = i;
  });
  return best;
}

document.addEventListener('pointermove', e => {
  const wrap = e.target.closest?.('.chart-wrap');
  if (wrap) show(wrap, nearest(wrap, e.clientX));
});
document.addEventListener('pointerdown', e => {
  const wrap = e.target.closest?.('.chart-wrap');
  if (wrap && e.pointerType !== 'mouse') show(wrap, nearest(wrap, e.clientX));
});
document.addEventListener('pointerout', e => {
  const wrap = e.target.closest?.('.chart-wrap');
  if (wrap && !wrap.contains(e.relatedTarget)) hide(wrap);
});
document.addEventListener('keydown', e => {
  const wrap = e.target.closest?.('.chart-wrap');
  if (!wrap || !['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(e.key)) return;
  e.preventDefault();
  const n = JSON.parse(wrap.dataset.chart).length;
  const cur = Number(wrap.dataset.index ?? -1);
  const next = {ArrowLeft: cur - 1, ArrowRight: cur + 1, Home: 0, End: n - 1}[e.key];
  show(wrap, next < 0 ? 0 : next);
});
document.addEventListener('focusout', e => {
  const wrap = e.target.closest?.('.chart-wrap');
  if (wrap) hide(wrap);
});

/* ---------- Leesbare tekst bij elke breedte ----------
 * Een SVG met viewBox schaalt tekst mee. Na het tekenen zetten we de lettergrootte (als SVG-attribuut, geen stijl)
 * zo dat labels op het scherm ongeveer 12 px zijn, ook in een smalle kaart. */
export function fitCharts(root = document) {
  root.querySelectorAll('svg.chart, svg.band-chart, svg.flow').forEach(svg => {
    const box = svg.viewBox?.baseVal;
    const width = svg.getBoundingClientRect().width;
    if (!box || !box.width || !width) return;
    svg.setAttribute('font-size', (12 * box.width / width).toFixed(1));
  });
}

let fitTimer = null;
window.addEventListener('resize', () => {
  clearTimeout(fitTimer);
  fitTimer = setTimeout(() => fitCharts(), 120);
});
new MutationObserver(() => {
  clearTimeout(fitTimer);
  fitTimer = setTimeout(() => fitCharts(), 30);
}).observe(document.getElementById('content'), {childList: true, subtree: true});
