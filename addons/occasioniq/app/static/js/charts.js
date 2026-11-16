/* Eenvoudige SVG-lijngrafiek zonder externe bibliotheek. */
import {esc, fmt, dt} from './format.js';

export function chart(points, {key = 'mean_asking'} = {}) {
  if (!points?.length) return '<div class="chart-empty">Nog geen historische data. Voer een eerste refresh uit.</div>';
  const values = points.map(p => Number(p[key] || 0));
  const lo = Math.min(...values);
  const hi = Math.max(...values);
  const range = Math.max(hi - lo, 1);
  const w = 720;
  const h = 230;
  const pad = 40;
  const usableW = w - pad * 2;
  const usableH = h - 55;
  const xy = values.map((n, i) => ({
    x: pad + (points.length === 1 ? usableW / 2 : i * usableW / (points.length - 1)),
    y: 20 + (hi - n) / range * usableH,
  }));
  const path = xy.map((p, i) => `${i ? 'L' : 'M'} ${p.x.toFixed(1)} ${p.y.toFixed(1)}`).join(' ');
  const grid = [0, .25, .5, .75, 1].map(f => {
    const y = 20 + usableH * f;
    return `<line x1="${pad}" x2="${w - pad}" y1="${y}" y2="${y}" stroke="#edf1f6"/>
      <text x="${pad - 6}" y="${y + 3}" text-anchor="end">${fmt(Math.round(hi - (hi - lo) * f))}</text>`;
  }).join('');
  const ticks = points.length > 1 ? [0, Math.floor((points.length - 1) / 2), points.length - 1] : [0];
  const dots = xy.map(p => `<circle cx="${p.x}" cy="${p.y}" r="3.3" fill="#fff" stroke="#21b5a4" stroke-width="2"/>`);
  const labels = ticks.map(i => {
    const label = points[i].date || dt(points[i].observed_at);
    return `<text x="${xy[i].x}" y="${h - 8}" text-anchor="middle">${esc(label)}</text>`;
  });
  return `<svg class="chart" viewBox="0 0 ${w} ${h}" role="img" aria-label="Historische prijsontwikkeling">${grid}
    <path d="${path}" fill="none" stroke="#21b5a4" stroke-width="3.5" stroke-linecap="round" stroke-linejoin="round"/>
    ${dots.join('')}${labels.join('')}</svg>`;
}
