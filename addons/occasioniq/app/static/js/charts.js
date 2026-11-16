/* Eenvoudige SVG-lijngrafiek zonder externe bibliotheek. Kleuren komen uit de CSS-klassen. */
import {esc, euro, fmt} from './format.js';

export function chart(points, {key = 'value', label = 'date', title = 'Grafiek', money = true} = {}) {
  if (!points?.length) return '<p class="muted">Nog geen metingen.</p>';
  const values = points.map(p => Number(p[key] || 0));
  if (points.length === 1) {
    return `<div class="stat-value">${money ? euro(values[0]) : fmt(values[0])}</div>
      <p class="muted small">Eerste meting (${esc(points[0][label])})</p>`;
  }
  const lo = Math.min(...values);
  const hi = Math.max(...values);
  const range = Math.max(hi - lo, 1);
  const narrow = window.matchMedia('(max-width: 760px)').matches;
  const w = narrow ? 360 : 720;
  const h = narrow ? 200 : 230;
  const left = narrow ? 72 : 64;
  const right = 16;
  const top = 16;
  const usableW = w - left - right;
  const usableH = h - 52;
  const xy = values.map((n, i) => ({
    x: left + i * usableW / (points.length - 1),
    y: hi > lo ? top + (hi - n) / range * usableH : top + usableH / 2,
  }));
  const path = xy.map((p, i) => `${i ? 'L' : 'M'} ${p.x.toFixed(1)} ${p.y.toFixed(1)}`).join(' ');
  const grid = (hi > lo ? [0, .5, 1] : [.5]).map(f => {
    const y = top + usableH * f;
    const v = Math.round(hi - (hi - lo) * f);
    return `<line class="grid-line" x1="${left}" x2="${w - right}" y1="${y}" y2="${y}"/>
      <text x="${left - 8}" y="${y + 4}" text-anchor="end">${money ? euro(v) : fmt(v)}</text>`;
  }).join('');
  const ticks = [0, Math.floor((points.length - 1) / 2), points.length - 1];
  const anchor = i => (i === 0 ? 'start' : i === points.length - 1 ? 'end' : 'middle');
  const labels = ticks.map(i => `<text x="${xy[i].x}" y="${h - 8}" text-anchor="${anchor(i)}">${esc(points[i][label])}</text>`);
  const dots = points.length <= 60 ? xy.map(p => `<circle class="dot" cx="${p.x}" cy="${p.y}" r="3"/>`).join('') : '';
  const summary = `${title}: van ${money ? euro(values[0]) : fmt(values[0])} naar `
    + `${money ? euro(values.at(-1)) : fmt(values.at(-1))}, ${points.length} metingen.`;
  return `<svg class="chart" viewBox="0 0 ${w} ${h}" role="img" aria-label="${esc(summary)}">${grid}
    <path class="line" d="${path}"/>${dots}${labels.join('')}</svg>`;
}
