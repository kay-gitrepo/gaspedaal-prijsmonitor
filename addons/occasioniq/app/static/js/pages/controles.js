import {api} from '../api.js';
import {esc, fmt, dt} from '../format.js';
import {$, head, modal, modalHead, statusTag, table} from '../ui.js';

function row(x) {
  const s = x.summary;
  return `<tr><td>${dt(x.created_at)}</td><td>${esc(x.trigger_source)}</td><td>${statusTag(x.state)}</td>
    <td>${fmt(s.found)}</td><td>${fmt(s.new)}</td><td>${fmt(s.price_changes)}</td><td>${fmt(s.gemini_calls)}</td>
    <td><a class="btn btn-sm" href="#/controles/${encodeURIComponent(x.id)}">Details</a></td></tr>`;
}

export async function render() {
  const data = await api('/refresh-runs');
  const headers = ['Gestart', 'Trigger', 'Uitkomst', 'Advertenties', 'Nieuw', 'Prijswijzigingen', 'Gemini', 'Actie'];
  $('#content').innerHTML = head('AUDIT & UITVOERING', 'Uitvoeringslog',
    'Iedere geplande of handmatige refresh, inclusief aantallen, processtappen en foutmeldingen.',
    '<button class="btn btn-secondary" data-action="refresh-all">↻ Handmatig starten</button>') + `
    <section class="card"><div class="card-head"><h3>Alle refresh-runs</h3>
      <span class="micro">Laatste 100 · klik voor tijdlijn</span></div>${table(headers, data.items.map(row))}</section>`;
}

function eventRow(e) {
  const metrics = e.metrics_json && e.metrics_json !== '{}'
    ? `<details><summary>Technische gegevens</summary>
      <pre class="json">${esc(JSON.stringify(JSON.parse(e.metrics_json), null, 2))}</pre></details>` : '';
  return `<div class="run-event ${esc(e.level)}"><strong>${dt(e.created_at)} · ${esc(e.stage)} · ${esc(e.level)}</strong>
    <p class="event-message">${esc(e.message)}</p>${metrics}</div>`;
}

export async function showRun(id) {
  const r = await api('/refresh-runs/' + encodeURIComponent(id));
  const s = r.summary;
  const gemini = r.gemini_requests.map(g => `<div class="option-claim"><span>${dt(g.created_at)} ·
    ${statusTag(g.decision)}</span><a class="btn btn-sm" href="#/ai-analyse/${encodeURIComponent(g.id)}">Bekijk</a></div>`);
  modal(modalHead('Run ' + r.id, `${r.trigger_source} · ${dt(r.created_at)}`) + `
    <div class="inline-actions detail-actions">${statusTag(r.state)}<strong>Gevonden: ${fmt(s.found)}</strong>
      <span>Nieuw: ${fmt(s.new)}</span><span>Prijswijzigingen: ${fmt(s.price_changes)}</span>
      <span>Aanbieders: ${fmt(s.portals)}</span><span>Portalprijswijzigingen: ${fmt(s.portal_price_changes)}</span></div>
    ${r.error ? `<div class="notice warn">${esc(r.error)}</div>` : ''}
    <section class="card"><h3>Verwerkingstijdlijn</h3>${r.events.map(eventRow).join('')}</section>
    <section class="card"><h3>Gemini-integraties in deze run</h3>
      ${gemini.join('') || '<p class="muted">Geen integratieverzoeken in deze run</p>'}</section>`);
}
