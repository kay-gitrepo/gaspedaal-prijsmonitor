import {api} from '../api.js';
import {esc, euro, fmt} from '../format.js';
import {$, eligibility, head, table} from '../ui.js';

export function photosOf(x) {
  try {
    return JSON.parse(x.photos_json || '[]');
  } catch {
    return [];
  }
}

function thumb(x) {
  const p = photosOf(x)[0];
  if (!p) return '<div class="thumb thumb-empty">Geen foto</div>';
  return `<img class="thumb" loading="lazy" referrerpolicy="no-referrer" src="${esc(p)}" alt="">`;
}

function row(x) {
  const must = Math.max(0, Math.min(100, x.score_must * .7));
  const nice = Math.max(0, Math.min(100, x.score_nice * .3));
  return `<tr class="clickable" data-href="#/auto/${encodeURIComponent(x.id)}"><td>${thumb(x)}</td>
    <td><strong>${esc(x.title)}</strong><br><span class="micro">${esc(x.seller || '—')} ${x.favorite ? ' ★' : ''}</span></td>
    <td>${esc(x.year || '—')}</td><td>${fmt(x.kilometers)}</td><td><strong>${euro(x.price_eur)}</strong></td>
    <td>${fmt(x.score_total)}%<div class="two-bars"><b data-w="${must}"></b><b class="nice" data-w="${nice}"></b></div></td>
    <td>${eligibility(x.eligibility)}</td></tr>`;
}

export async function render() {
  const data = await api('/listings');
  $('#content').innerHTML = head('SELECTIE', 'Autoaanbod', 'Bekijk individuele auto\'s, optieherkenning en vraagprijshistorie.',
    '<a class="btn" href="/api/v1/export/observations.csv">↓ Exporteer prijshistorie</a>') + `
    <section class="card"><div class="card-head"><h3>${fmt(data.items.length)} gevolgde auto's</h3>
      <div class="inline-actions">
        <label class="micro"><input id="only-matches" type="checkbox"> Alleen bevestigde must-haves</label>
        <label class="micro"><input id="only-favorites" type="checkbox"> Alleen favorieten</label>
      </div></div><div id="offers-table"></div></section>`;
  const draw = () => {
    const must = $('#only-matches').checked;
    const favorites = $('#only-favorites').checked;
    const cars = data.items.filter(x => (!must || x.eligibility === 'MATCH') && (!favorites || x.favorite));
    const headers = ['Foto', 'Voertuig', 'Bouwjaar', 'Kilometers', 'Vraagprijs', 'Uitrustingsscore', 'Status'];
    $('#offers-table').innerHTML = table(headers, cars.map(row));
    document.querySelectorAll('#offers-table [data-w]').forEach(b => {
      b.style.width = b.dataset.w + '%';
    });
  };
  draw();
  $('#only-matches').addEventListener('change', draw);
  $('#only-favorites').addEventListener('change', draw);
}
