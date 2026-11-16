/* Beheerscherm: technische ID's mogen hier zichtbaar zijn. */
import {api} from '../api.js';
import {esc, fmt, dt} from '../format.js';
import {DECISION, LEVEL, RUN_STATE, TRIGGER, label} from '../labels.js';
import {$, button, card, dialogHead, icon, notice, openDialog, pageHead, skeletons, statusBadge, table} from '../ui.js';

export function skeleton() {
  return skeletons.head() + skeletons.rows(10);
}

function summaryLine(s) {
  if (s.found === undefined) return '—';
  return `${fmt(s.found)} auto's · ${fmt(s.new)} nieuw · ${fmt(s.price_changes)} prijswijzigingen`;
}

function row(x) {
  return [
    `<a class="title-link" href="#/controles/${encodeURIComponent(x.id)}">${dt(x.created_at)}</a>`,
    esc(label(TRIGGER, x.trigger_source)),
    statusBadge(RUN_STATE, x.state),
    esc(summaryLine(x.summary)),
  ];
}

export async function render() {
  const data = await api('/refresh-runs');
  const columns = [{label: 'Gestart', main: true}, {label: 'Gestart door'}, {label: 'Uitkomst'}, {label: 'Samenvatting'}];
  $('#content').innerHTML = pageHead('Controles', 'Elke controle van je zoekopdrachten, met uitkomst en verloop.',
    button('Nu controleren', {variant: 'secondary', icon: 'refresh', action: 'refresh-all'}))
    + card('Laatste 100 controles', table(columns, data.items.map(row), {empty: 'Nog geen controle uitgevoerd.'}));
}

function eventItem(e) {
  const metrics = e.metrics_json && e.metrics_json !== '{}'
    ? `<details class="disclosure"><summary>${icon('chevron-down')}Technische gegevens</summary>
      <pre class="json">${esc(JSON.stringify(JSON.parse(e.metrics_json), null, 2))}</pre></details>` : '';
  return `<div class="timeline-item level-${esc(e.level)}"><strong>${dt(e.created_at)} · ${esc(label(LEVEL, e.level))}</strong>
    <span class="muted small"> · ${esc(e.stage)}</span><p>${esc(e.message)}</p>${metrics}</div>`;
}

export async function showRun(id) {
  const r = await api('/refresh-runs/' + encodeURIComponent(id));
  const s = r.summary;
  const facts = [['Auto\'s gevonden', s.found], ['Nieuw', s.new], ['Prijswijzigingen', s.price_changes],
    ['Niet meer gezien', s.missing_new], ['Weer terug', s.reappeared], ['Overgeslagen (prijs)', s.skipped_invalid]];
  const ai = r.gemini_requests.map(g => `<a class="list-item" href="#/ai-analyse/${encodeURIComponent(g.id)}">
    <span>${dt(g.created_at)}</span>${statusBadge(DECISION, g.decision)}</a>`).join('');
  openDialog(dialogHead(`Controle van ${dt(r.created_at)}`, `${label(TRIGGER, r.trigger_source)} · ${r.id}`) + `
    <div class="detail-top">${statusBadge(RUN_STATE, r.state)}</div>
    ${r.error ? notice(esc(r.error), 'danger') : ''}
    ${card('Resultaat', `<dl class="facts">${facts.map(([k, v]) => `<div><dt>${k}</dt><dd>${fmt(v ?? 0)}</dd></div>`)
      .join('')}</dl>`)}
    ${card('Verloop', r.events.map(eventItem).join('') || '<p class="muted">Geen gebeurtenissen.</p>')}
    ${card('AI-beoordelingen in deze controle', ai ? `<div class="list">${ai}</div>`
      : '<p class="muted">Geen beoordelingen in deze controle.</p>')}`);
}
