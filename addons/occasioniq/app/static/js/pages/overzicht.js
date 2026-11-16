import {api} from '../api.js';
import {esc, euro, fmt, dt} from '../format.js';
import {chart} from '../charts.js';
import {$, eligibility, head, statusTag, table} from '../ui.js';

function stat(title, icon, value, bottom) {
  return `<div class="stat"><div class="stat-head">${title} <span class="stat-icon">${icon}</span></div>
    <div class="stat-value">${value}</div><div class="stat-bottom">${bottom}</div></div>`;
}

function runRow(x) {
  return `<a class="option-claim clickable" href="#/controles/${encodeURIComponent(x.id)}">
    <div><strong>${dt(x.created_at)}</strong><p class="micro">${esc(x.trigger_source)} · ${x.summary.found || 0} auto's</p>
    </div>${statusTag(x.state)}</a>`;
}

function carRow(x) {
  return `<tr class="clickable" data-href="#/auto/${encodeURIComponent(x.id)}">
    <td class="table-link">${esc(x.title)}<br><span class="micro">${esc(x.seller || 'Verkoper onbekend')}</span></td>
    <td>${euro(x.price_eur)}</td><td>${fmt(x.kilometers)}</td><td><strong>${fmt(x.score_total)}%</strong></td>
    <td>${eligibility(x.eligibility)}</td></tr>`;
}

export async function render() {
  const [d, l, r] = await Promise.all([api('/dashboard'), api('/listings'), api('/refresh-runs')]);
  const offers = l.items.slice(0, 6);
  const runs = r.items.length ? r.items.slice(0, 5).map(runRow).join('') : '<p class="muted">Nog geen refresh uitgevoerd.</p>';
  $('#content').innerHTML = head('MARKTINTELLIGENTIE', 'Marktoverzicht',
    'Inzicht in de vraagprijzen, jouw matches en het prijsgedrag van gevolgde auto’s.',
    '<a class="btn btn-secondary" href="#/aanbod">Bekijk alle auto’s →</a>') + `
    <div class="stats">
      ${stat('Actieve advertenties', '▤', fmt(d.active_listings), 'In jouw gemonitorde markt')}
      ${stat('Mediane vraagprijs', '€', euro(d.median_asking), 'Geen gerealiseerde verkoopprijzen')}
      ${stat('Bevestigde must-have matches', '✓', fmt(d.matches), '<strong>Geschikt op verplichte opties</strong>')}
      ${stat('Gem. uitrustingsmatch', '✦', fmt(d.average_score) + '%', '70% must-have · 30% nice-to-have')}
    </div>
    <div class="notice warn">ⓘ&nbsp; <span>${esc(d.limitations[0])}
      Alle statistieken zijn gebaseerd op daadwerkelijk verwerkte gegevens.</span></div>
    <div class="grid-two">
      <section class="card"><div class="card-head"><h3>Ontwikkeling gemiddelde vraagprijs</h3>
        <span class="micro">Per kalenderdag · niet gecorrigeerd voor wisselend aanbod</span></div>${chart(d.price_trend)}</section>
      <section class="card"><div class="card-head"><h3>Meest recente controles</h3>
        <a class="btn btn-sm" href="#/controles">Alle logs</a></div>${runs}</section>
    </div>
    <section class="card"><div class="card-head"><h3>Interessante auto's</h3>
      <span class="micro">Gerangschikt op matchscore en vraagprijs</span></div>
      ${table(['Auto', 'Vraagprijs', 'Km-stand', 'Match', 'Geschiktheid'], offers.map(carRow))}</section>`;
}
