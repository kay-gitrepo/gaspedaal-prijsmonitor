/* AI-beoordeling: wat is beoordeeld, wat wacht nog, en per beoordeling een leesbare tabel. Beheerscherm. */
import {api} from '../api.js';
import {esc, fmt, dt} from '../format.js';
import {CLAIM, CLAIM_SOURCE, DECISION, GROUP, label} from '../labels.js';
import {$, button, card, icon, notice, pageHead, skeletons, stat, statusBadge, table, tabs, toast} from '../ui.js';
import {follow} from '../refresh.js';
import {certainty} from '../equipment.js';

const FILTERS = [['alles', 'Alles', () => true], ['ai', 'AI-beoordeling', x => x.decision === 'SUCCESS'],
  ['lokaal', 'Zonder AI herkend', x => x.decision === 'LOCAL_ONLY'], ['uit', 'AI staat uit', x => x.decision === 'SKIPPED_NO_KEY'],
  ['wacht', 'Wacht op volgende controle', x => x.decision === 'SKIPPED_BUDGET'],
  ['mislukt', 'Mislukt', x => x.decision === 'ERROR'], ['ongewijzigd', 'Ongewijzigd', x => x.decision === 'CACHE_HIT']];

export function skeleton() {
  return skeletons.head() + skeletons.stats() + skeletons.rows(8);
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

async function list(params) {
  const [data, s] = await Promise.all([api('/integrations'), api('/integrations/summary')]);
  const key = FILTERS.some(f => f[0] === params.get('uitkomst')) ? params.get('uitkomst') : 'alles';
  const active = FILTERS.find(f => f[0] === key);
  const items = data.items.filter(active[2]);
  const tabItems = FILTERS.map(([k, t, f]) => ({key: k, label: t, count: data.items.filter(f).length,
    href: k === 'alles' ? '#/ai-analyse' : `#/ai-analyse?uitkomst=${k}`})).filter(t => t.count || t.key === 'alles');
  const columns = [{label: 'Auto', main: true}, {label: 'Uitkomst'}, {label: 'Tokens in / uit', num: true},
    {label: 'Model'}];
  const queue = s.waiting ? button('Wachtrij nu verwerken', {variant: 'primary', icon: 'sparkles', action: 'process-queue'})
    : '';
  $('#content').innerHTML = pageHead('AI-beoordeling',
    'Hoe de advertentieteksten zijn beoordeeld: zonder AI, met AI, of nog niet.', queue)
    + `<div class="stats">${stat('Beoordeeld', fmt(s.assessed), 'auto\'s met een actuele beoordeling', 'check-circle')}
      ${stat('Wacht nog', fmt(s.waiting), `te koop, nog niet beoordeeld · maximaal ${fmt(s.max_per_run)} AI-aanroepen per `
        + 'controle', 'clock')}
      ${stat('Mislukt', fmt(s.failed), 'AI-aanroepen deze maand', 'alert')}
      ${stat('Tokens deze maand', fmt(s.tokens_month), s.ai_enabled ? 'in en uit samen' : 'AI staat uit', 'sparkles')}</div>`
    + (s.ai_enabled ? '' : notice('AI-beoordeling staat uit. Opties worden alleen herkend met de vaste zoekwoorden; '
      + 'de rest blijft onbekend. Stel <code>GEMINI_API_KEY</code> in om AI te gebruiken.'))
    + card('Laatste 200 beoordelingen', tabs(tabItems, key, 'Uitkomst') + table(columns, items.map(row),
      {empty: 'Geen beoordelingen met deze uitkomst.'}));
}

function verdictTable(claims) {
  if (!claims.length) return '<p class="muted">Geen oordelen bij deze beoordeling.</p>';
  const rows = claims.map(c => [`<strong>${esc(c.label)}</strong><span class="sub">${esc(label(GROUP, c.group_name))}</span>`,
    statusBadge(CLAIM, c.status), c.evidence ? `<mark>“${esc(c.evidence)}”</mark>` : `<span class="muted">${esc(c.reason
      || 'Geen citaat')}</span>`, esc(certainty(c.confidence)), esc(label(CLAIM_SOURCE, c.source, 'Uit de advertentie'))]);
  return table([{label: 'Wens', main: true}, {label: 'Oordeel'}, {label: 'Citaat'}, {label: 'Zekerheid'},
    {label: 'Herkomst'}], rows, {caption: 'Oordelen'});
}

async function detail(id) {
  const x = await api('/integrations/' + encodeURIComponent(id));
  document.title = `AI-beoordeling · OccasionIQ`;
  const request = x.request_json ? JSON.stringify(x.request_json, null, 2) : 'Geen AI-aanroep: zonder AI afgehandeld of '
    + 'overgeslagen.';
  const parsed = x.parsed_json ? JSON.stringify(x.parsed_json, null, 2) : 'Geen AI-resultaat.';
  const facts = [['Model', esc(x.model_id || '—')], ['Tokens in / uit', `${fmt(x.tokens_in)} / ${fmt(x.tokens_out)}`],
    ['Duur', x.duration_ms == null ? '—' : `${fmt(x.duration_ms)} ms`], ['Tijdstip', dt(x.created_at)]];
  $('#content').innerHTML = `<div class="row">${button('Alle beoordelingen', {href: '#/ai-analyse', icon: 'chevron-left',
    variant: 'text', size: 's'})}${x.title ? button('Naar de auto', {href: `#/auto/${encodeURIComponent(x.listing_id)}`,
    icon: 'car', variant: 'text', size: 's'}) : ''}</div>
    ${pageHead(x.title || 'AI-beoordeling', `Beoordeling van ${dt(x.created_at)}`, statusBadge(DECISION, x.decision))}
    ${x.error ? notice(esc(x.error), 'danger') : ''}
    ${card('Oordelen', verdictTable(x.claims || []), {sub: 'Zoals vastgelegd bij deze beoordeling'})}
    ${card('Gegevens', `<dl class="facts">${facts.map(([k, v]) => `<div><dt>${k}</dt><dd>${v}</dd></div>`).join('')}
      </dl><p class="muted small">Beoordeling-ID: <code>${esc(x.id)}</code> · controle <a href="#/controles/${
      encodeURIComponent(x.run_id)}">${esc(x.run_id)}</a></p>`)}
    <section class="card"><details class="disclosure"><summary>${icon('chevron-down')}Ruwe gegevens (verzonden tekst,
      antwoord en gecontroleerd resultaat)</summary><h4>Verzonden</h4><pre class="json">${esc(request)}</pre>
      <h4>Ruw antwoord</h4><pre class="json">${esc(x.response_json || 'Geen antwoord.')}</pre>
      <h4>Gecontroleerd resultaat</h4><pre class="json">${esc(parsed)}</pre></details></section>`;
}

export async function render(params, id) {
  if (id) return detail(id);
  return list(params || new URLSearchParams());
}

export const actions = {
  async 'process-queue'(el) {
    const r = await api('/integrations/process-queue', {method: 'POST'});
    toast(`${fmt(r.count)} auto's worden beoordeeld.`, 'info');
    el.classList.add('loading');
    await follow(r.run_id);
  },
};
