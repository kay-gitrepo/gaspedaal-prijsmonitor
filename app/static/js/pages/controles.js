/* Controles: lijst en detailpagina (#/controles/<id>). Beheerscherm: technische ID's mogen hier zichtbaar zijn. */
import {api} from '../api.js';
import {esc, euro, fmt, dt} from '../format.js';
import {DECISION, LEVEL, RUN_STATE, TRIGGER, label} from '../labels.js';
import {$, button, card, icon, notice, pageHead, skeletons, statusBadge, table} from '../ui.js';

export function skeleton() {
  return skeletons.head() + skeletons.rows(10);
}

export function duration(r) {
  if (!r.started_at || !r.finished_at) return '—';
  const s = Math.max(0, Math.round((new Date(r.finished_at) - new Date(r.started_at)) / 1000));
  return s < 90 ? `${s} s` : `${Math.round(s / 60)} min`;
}

/** Eén zin over een controle, zonder technische codes. */
export function summarySentence(r) {
  const s = r.summary || {};
  if (s.analyzed !== undefined) return `${fmt(s.analyzed)} ${s.analyzed === 1 ? 'auto' : 'auto\'s'} opnieuw beoordeeld`;
  if (r.state === 'FAILED') return 'Mislukt; er is niets als verdwenen gemarkeerd.';
  if (['QUEUED', 'RUNNING'].includes(r.state)) return 'Bezig…';
  const parts = [`${fmt(s.found ?? 0)} auto's`];
  if (s.new) parts.push(`${fmt(s.new)} nieuw`);
  if (s.price_changes) parts.push(`${fmt(s.price_changes)} ${s.price_changes === 1 ? 'prijswijziging' : 'prijswijzigingen'}`);
  if (s.missing_new) parts.push(`${fmt(s.missing_new)} niet meer gezien`);
  if (s.reappeared) parts.push(`${fmt(s.reappeared)} weer terug`);
  if (s.out_of_scope_new) parts.push(`${fmt(s.out_of_scope_new)} buiten de filters`);
  return parts.join(', ');
}

function row(x) {
  return [
    `<a class="title-link" href="#/controles/${encodeURIComponent(x.id)}">${dt(x.created_at)}</a>`,
    esc(label(TRIGGER, x.trigger_source)),
    esc(duration(x)),
    statusBadge(RUN_STATE, x.state),
    esc(summarySentence(x)),
  ];
}

async function list() {
  const data = await api('/refresh-runs');
  const columns = [{label: 'Gestart', main: true}, {label: 'Gestart door'}, {label: 'Duur', num: true},
    {label: 'Uitkomst'}, {label: 'Samenvatting'}];
  $('#content').innerHTML = pageHead('Controles', 'Elke controle van je zoekopdrachten: wanneer, door wie, hoe lang en '
    + 'met welk resultaat.', button('Nu controleren', {variant: 'secondary', icon: 'refresh', action: 'refresh-all'}))
    + card('Laatste 100 controles', table(columns, data.items.map(row), {empty: 'Nog geen controle uitgevoerd.'}));
}

const GROUPS = [['new', 'Nieuw', 'plus'], ['price_down', 'Prijs omlaag', 'trending-down'],
  ['price_up', 'Prijs omhoog', 'trending-up'], ['missing', 'Niet meer gezien', 'alert'],
  ['off_market', 'Uit het aanbod', 'archive'], ['reappeared', 'Weer terug', 'refresh']];

/** Lijsten met wat er veranderde; ook gebruikt op Overzicht. */
export function changesHtml(groups, {limit = 0} = {}) {
  const blocks = GROUPS.filter(([k]) => groups[k]?.length).map(([k, title, ic]) => {
    const items = limit ? groups[k].slice(0, limit) : groups[k];
    const more = limit && groups[k].length > limit ? `<p class="muted small">en ${fmt(groups[k].length - limit)} meer</p>` : '';
    const rows = items.map(x => {
      const amount = ['price_down', 'price_up'].includes(k)
        ? `${euro(x.previous_price)} → <strong>${euro(x.new_price)}</strong>`
        : k === 'new' || k === 'reappeared' ? `<strong>${euro(x.new_price ?? x.price_eur)}</strong>`
          : `laatst ${euro(x.price_eur)}`;
      return `<a class="list-item" href="#/auto/${encodeURIComponent(x.listing_id)}"><span>${esc(x.title)}</span>
        <span class="nowrap">${amount}</span></a>`;
    }).join('');
    return `<section class="change-group"><h4>${icon(ic)}${title} (${fmt(groups[k].length)})</h4>
      <div class="list">${rows}</div>${more}</section>`;
  });
  return blocks.join('') || '<p class="muted">Geen veranderingen gevonden.</p>';
}

function completeness(p) {
  if (p.state === 'FAILED') return 'Mislukt; niets als verdwenen gemarkeerd';
  const parts = [];
  if (p.pages) parts.push(`${fmt(p.pages)} ${p.pages === 1 ? 'pagina' : 'pagina\'s'}`);
  if (p.expected != null) parts.push(`${fmt(p.found)} van ${fmt(p.expected)} verwacht`);
  else parts.push(`${fmt(p.found)} auto's${p.complete ? ', volledig volgens de bron' : ''}`);
  if (p.skipped_invalid) parts.push(`${fmt(p.skipped_invalid)} overgeslagen om een onwaarschijnlijke prijs`);
  return parts.join(', ');
}

function eventItem(e) {
  const metrics = e.metrics_json && e.metrics_json !== '{}'
    ? `<details class="disclosure"><summary>${icon('chevron-down')}Gegevens</summary>
      <pre class="json">${esc(JSON.stringify(JSON.parse(e.metrics_json), null, 2))}</pre></details>` : '';
  return `<div class="timeline-item level-${esc(e.level)}"><strong>${dt(e.created_at)} · ${esc(label(LEVEL, e.level))}</strong>
    <span class="muted small"> · ${esc(e.stage)}</span><p>${esc(e.message)}</p>${metrics}</div>`;
}

async function detail(id) {
  const r = await api('/refresh-runs/' + encodeURIComponent(id));
  document.title = `Controle van ${dt(r.created_at)} · OccasionIQ`;
  const profiles = (r.profiles || []).map(p => [`<strong>${esc(p.title)}</strong>`, statusBadge(RUN_STATE, p.state),
    esc(completeness(p))]);
  const ai = r.gemini_requests.map(g => `<a class="list-item" href="#/ai-analyse/${encodeURIComponent(g.id)}">
    <span>${dt(g.created_at)}</span>${statusBadge(DECISION, g.decision)}</a>`).join('');
  $('#content').innerHTML = `${button('Alle controles', {href: '#/controles', icon: 'chevron-left', variant: 'text',
    size: 's'})}${pageHead(`Controle van ${dt(r.created_at)}`, `${label(TRIGGER, r.trigger_source)} · duur ${duration(r)}`,
    statusBadge(RUN_STATE, r.state))}
    ${r.state === 'FAILED' ? notice('Deze controle is mislukt. Bestaande gegevens zijn ongewijzigd gebleven en er is '
      + 'niets als verdwenen gemarkeerd.', 'danger') : ''}
    ${card('Wat is er gevonden', `<p class="muted">${esc(summarySentence(r))}</p>${changesHtml(r.changes || {})}`)}
    ${card('Per zoekopdracht', profiles.length ? table([{label: 'Zoekopdracht', main: true}, {label: 'Uitkomst'},
      {label: 'Volledigheid'}], profiles) : '<p class="muted">Geen gegevens per zoekopdracht vastgelegd.</p>')}
    <section class="card"><details class="disclosure"><summary>${icon('chevron-down')}Technisch verloop
      (${fmt(r.events.length)} stappen)</summary>
      ${r.error ? notice(`<code>${esc(r.error)}</code>`, 'danger') : ''}
      <p class="muted small">Controle-ID: <code>${esc(r.id)}</code></p>${r.events.map(eventItem).join('')}
      <h4>AI-beoordelingen in deze controle</h4>${ai ? `<div class="list">${ai}</div>` : '<p class="muted">Geen.</p>'}
    </details></section>`;
}

export async function render(params, id) {
  if (id) return detail(id);
  return list();
}
