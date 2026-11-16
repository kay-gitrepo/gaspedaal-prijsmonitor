/* Beheerscherm: technische gegevens mogen hier zichtbaar zijn. */
import {api} from '../api.js';
import {esc, fmt, dt} from '../format.js';
import {DECISION} from '../labels.js';
import {$, card, dialogHead, icon, notice, openDialog, pageHead, skeletons, statusBadge, table} from '../ui.js';

export function skeleton() {
  return skeletons.head() + skeletons.rows(10);
}

function row(x) {
  return [
    `<a class="title-link" href="#/ai-analyse/${encodeURIComponent(x.id)}">${esc(x.title)}</a>
      <span class="sub">${dt(x.created_at)}</span>`,
    statusBadge(DECISION, x.decision),
    `${fmt(x.tokens_in)} / ${fmt(x.tokens_out)}`,
    esc(x.model_id || '—'),
  ];
}

export async function render() {
  const data = await api('/integrations');
  const columns = [{label: 'Auto', main: true}, {label: 'Uitkomst'}, {label: 'Tokens in / uit', num: true},
    {label: 'Model'}];
  $('#content').innerHTML = pageHead('AI-beoordeling',
    'Hoe de advertentieteksten zijn beoordeeld: zonder AI, met AI, of nog niet.')
    + notice('Alleen echte AI-aanroepen hebben verzonden tekst. Herkenning zonder AI en overgeslagen beoordelingen '
      + 'worden apart vastgelegd.')
    + card('Laatste 200 beoordelingen', table(columns, data.items.map(row), {empty: 'Nog geen beoordelingen.'}));
}

export async function showIntegration(id) {
  const x = await api('/integrations/' + encodeURIComponent(id));
  const request = x.request_json ? JSON.stringify(x.request_json, null, 2) : 'Geen AI-aanroep: zonder AI afgehandeld of overgeslagen.';
  const parsed = x.parsed_json ? JSON.stringify(x.parsed_json, null, 2) : 'Geen AI-resultaat.';
  const facts = [['Model', esc(x.model_id || '—')], ['Tokens in / uit', `${fmt(x.tokens_in)} / ${fmt(x.tokens_out)}`],
    ['Duur', x.duration_ms == null ? '—' : `${fmt(x.duration_ms)} ms`]];
  openDialog(dialogHead('AI-beoordeling', `${dt(x.created_at)} · ${x.id}`) + `
    <div class="detail-top">${statusBadge(DECISION, x.decision)}</div>
    ${x.error ? notice(esc(x.error), 'danger') : ''}
    ${card('Gegevens', `<dl class="facts">${facts.map(([k, v]) => `<div><dt>${k}</dt><dd>${v}</dd></div>`).join('')}</dl>`)}
    ${card('Gecontroleerd resultaat', `<pre class="json">${esc(parsed)}</pre>`)}
    <section class="card"><details class="disclosure"><summary>${icon('chevron-down')}Verzonden tekst en ruw antwoord
      </summary><pre class="json">${esc(request)}</pre><pre class="json">${esc(x.response_json || 'Geen antwoord.')}</pre>
    </details></section>`);
}
