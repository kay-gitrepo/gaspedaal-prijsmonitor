/* Overzicht: beantwoordt de zeven marktvragen per zoekopdracht, met periodekeuze 30 dagen · 90 dagen · alles. */
import {api} from '../api.js';
import {datum, esc, euro, fmt, relatief} from '../format.js';
import {chart} from '../charts.js';
import {$, badge, button, card, icon, notice, pageHead, skeletons, stat, table} from '../ui.js';
import {allProfiles, currentProfile, profileQuery} from '../context.js';
import {failureNotice} from '../freshness.js';
import {statusChip} from '../status.js';
import {marketCell} from '../negotiation.js';
import {changesHtml} from './controles.js';

const PERIODS = [['30', '30 dagen'], ['90', '90 dagen'], ['', 'Alles']];

export function skeleton() {
  return skeletons.head() + skeletons.stats() + '<div class="grid grid-2">' + skeletons.block() + skeletons.block()
    + '</div>' + skeletons.block();
}

export function wishesSeen() {
  try {
    return localStorage.getItem('occasioniq.wensen-bekeken') === '1';
  } catch {
    return false;
  }
}

const tooFew = n => `te weinig data (n = ${fmt(n)})`;

function step(done, title, text, actionHtml) {
  return `<li class="${done ? 'done' : ''}"><span class="step-dot">${done ? icon('check') : ''}</span>
    <div class="step-text"><strong>${esc(title)}</strong><p>${esc(text)}</p></div>
    ${done ? '<span class="badge badge-success">Klaar</span>' : actionHtml}</li>`;
}

/** Startlijst voor een nieuwe installatie: vier stappen met hun status. */
function startList(profiles, runs) {
  const checked = runs.some(r => ['COMPLETE', 'PARTIAL'].includes(r.state));
  const viaHa = runs.some(r => r.trigger_source === 'HOME_ASSISTANT');
  return pageHead('Welkom bij OccasionIQ', 'Vier stappen naar je eerste overzicht van de markt.') + card('', `<ol class="checklist">
    ${step(profiles.length > 0, 'Zoekopdracht toevoegen', 'Plak de zoeklink van Gaspedaal met jouw filters.',
      button('Toevoegen', {variant: 'primary', href: '#/zoekopdrachten'}))}
    ${step(wishesSeen(), 'Wensen kiezen', 'Welke uitrusting moet de auto hebben, en wat is mooi meegenomen?',
      button('Wensen bekijken', {href: '#/wensen'}))}
    ${step(checked, 'Eerste controle', 'Haal de auto\'s en vraagprijzen van je zoekopdracht op.',
      profiles.length ? button('Nu controleren', {variant: 'primary', icon: 'refresh', action: 'refresh-all'}) : '')}
    ${step(viaHa, 'Automatisch laten controleren', 'Laat Home Assistant op vaste tijden een controle starten.',
      button('Zo stel je het in', {href: '#/instellingen'}))}</ol>`);
}

function periodLinks(period) {
  const links = PERIODS.map(([v, t]) => {
    const active = period === v;
    return `<a class="period${active ? ' active' : ''}" href="#/overzicht${v ? `?periode=${v}` : ''}"
      ${active ? 'aria-current="page"' : ''}>${t}</a>`;
  });
  return `<nav class="periods" aria-label="Periode">${links.join('')}</nav>`;
}

function sparkline(series) {
  if (!series || series.length < 2) return '';
  const w = 160;
  const h = 32;
  const max = Math.max(...series.map(s => s.count), 1);
  const pts = series.map((s, i) => `${(i / (series.length - 1) * w).toFixed(1)},${(h - 2 - s.count / max * (h - 4)).toFixed(1)}`);
  const text = `Binnen budget door de tijd: van ${series[0].count} naar ${series.at(-1).count} auto's`;
  return `<svg class="sparkline" viewBox="0 0 ${w} ${h}" role="img" aria-label="${esc(text)}">
    <polyline points="${pts.join(' ')}"/></svg>`;
}

function kpis(m) {
  const a = m.asking;
  const asking = a.median == null ? stat('Gangbare vraagprijs', '—', tooFew(a.n), 'euro')
    : stat('Gangbare vraagprijs', euro(a.median), `P25–P75 ${euro(a.p25)} – ${euro(a.p75)} · n = ${fmt(a.n)}`, 'euro');
  const w = m.within_budget;
  const budget = w ? `<div class="card stat"><div class="stat-label">Binnen budget${icon('wensen')}</div>
      <div class="stat-value">${fmt(w.count)} <span class="stat-of">van ${fmt(w.n)}</span></div>
      <div class="stat-note">waarvan ${fmt(w.match)} voldoen · budget ${euro(w.budget)}</div>${sparkline(w.series)}</div>`
    : `<div class="card stat"><div class="stat-label">Binnen budget${icon('wensen')}</div><div class="stat-value">—</div>
      <div class="stat-note">${m.profile_id ? '<a href="#/zoekopdrachten">Stel een budget in</a> bij de zoekopdracht'
        : 'Kies een zoekopdracht met een budget'}</div></div>`;
  const av = m.in_view.active;
  const gv = m.in_view.gone;
  const view = stat('Tijd in beeld', av.value == null ? '—' : `${fmt(Math.round(av.value))} dagen`,
    `mediaan tot nu toe (n = ${fmt(av.n)})${gv.value == null ? '' : ` · verdwenen: ${fmt(Math.round(gv.value))} dagen`}`,
    'clock');
  return `<div class="stats">${stat('Aanbod', fmt(m.for_sale), `te koop · ${fmt(m.matches)} voldoen`, 'car')}
    ${asking}${budget}${view}</div>`;
}

function opportunities(m) {
  if (!m.opportunities.length) return '<p class="muted">Nog geen auto\'s die voldoen of nog te controleren zijn.</p>';
  return `<div class="list">${m.opportunities.map(o => `<a class="list-item opp" href="#/auto/${encodeURIComponent(o.id)}">
    <div><strong>${esc(o.title)}</strong><p>${euro(o.price_eur)} · ${fmt(o.kilometers)} km ${o.within_budget
      ? badge('binnen budget', 'success') : ''}</p></div>
    <div class="opp-side"><div class="num">${marketCell(o)}</div>${statusChip(o)}</div></a>`).join('')}</div>
    <p class="muted small">Voldoet of nog te controleren, gesorteerd op verschil met vergelijkbare auto's${m.budget
      ? '; binnen budget eerst' : ''}.</p>`;
}

function timeline(m) {
  const t = m.timeline;
  const days = t.days.filter(d => d.median != null);
  if (!days.length) return `<p class="muted">${esc(t.sentence)}</p>`;
  const start = days[0].median;
  const index = t.index.filter(p => days.some(d => d.date === p.date));
  const series = [{name: 'Mediane vraagprijs', type: 'line', points: days.map(d => ({x: d.date, y: d.median,
    label: `n = ${d.n}`}))},
  {name: 'Dezelfde auto\'s', type: 'line', cls: 'secondary', points: index.map(p => ({x: p.date,
    y: Math.round(start * p.index / 100), label: `index ${fmt(p.index)}`}))}];
  const band = {points: days.map(d => ({x: d.date, lo: d.p25, hi: d.p75}))};
  const hlines = m.budget ? [{y: m.budget, label: `budget ${euro(m.budget)}`}] : [];
  const html = chart({series, band, hlines, title: 'Markt door de tijd',
    summary: `Mediane vraagprijs van ${euro(days[0].median)} naar ${euro(days.at(-1).median)}; prijsindex van dezelfde `
      + `auto's ${fmt(index.at(-1)?.index ?? 100)}. ${t.sentence}`});
  return `${html}<div class="legend"><span class="lg lg-median">Mediane vraagprijs</span><span class="lg lg-band">P25–P75</span>
    <span class="lg lg-index">Dezelfde auto's (index, herschaald)</span>${m.budget ? '<span class="lg lg-budget">Budget</span>'
    : ''}</div><p class="lead trend">${esc(t.sentence)}</p>
    <p class="muted small">De mediaan verandert ook als er andere auto's te koop komen. De tweede lijn beweegt alleen als
    dezelfde advertenties van prijs veranderen (index 100 = begin van de periode).</p>`;
}

function scatter(m) {
  if (!m.scatter.length) return '<p class="muted">Nog geen auto\'s met een bekende kilometerstand.</p>';
  const cls = {MATCH: 'pt-match', REJECTED: 'pt-reject'};
  const points = m.scatter.map(s => ({x: s.kilometers, y: s.price_eur, cls: cls[s.eligibility] || 'pt-check',
    href: `#/auto/${encodeURIComponent(s.id)}`, label: s.title}));
  const html = chart({series: [{name: 'Auto\'s', type: 'scatter', points}], xType: 'number', title: 'Prijs tegen km',
    hlines: m.budget ? [{y: m.budget, label: `budget ${euro(m.budget)}`}] : [],
    summary: `${m.scatter.length} auto's te koop, prijs tegen kilometerstand.`});
  const rows = m.km_classes.map(k => [esc(k.label), k.median == null ? `<span class="muted">${tooFew(k.n)}</span>`
    : euro(k.median), fmt(k.n)]);
  return `${html}<div class="legend"><span class="lg lg-match">Voldoet</span><span class="lg lg-check">Nog te controleren
    </span><span class="lg lg-reject">Valt af</span></div><p class="muted small">Klik op een punt om de auto te openen.</p>
    ${table([{label: 'Kilometerstand', main: true}, {label: 'Mediane vraagprijs', num: true}, {label: 'n', num: true}],
      rows, {caption: 'Mediane vraagprijs per kilometerklasse'})}`;
}

function flowBars(flow) {
  if (!flow.length) return '';
  const w = Math.max(320, flow.length * 36);
  const h = 140;
  const max = Math.max(1, ...flow.map(f => Math.max(f.new, f.gone)));
  const mid = h / 2;
  const scale = (h / 2 - 18) / max;
  const bw = Math.min(14, w / flow.length / 3);
  const bars = flow.map((f, i) => {
    const x = 40 + i * (w - 60) / Math.max(1, flow.length - 1);
    const label = `Week van ${datum(f.week)}: ${f.new} nieuw, ${f.gone} niet meer gezien`;
    return `<g><title>${esc(label)}</title><rect class="bar-new" x="${(x - bw).toFixed(1)}"
      y="${(mid - f.new * scale).toFixed(1)}" width="${bw}" height="${(f.new * scale).toFixed(1)}"/>
      <rect class="bar-gone" x="${x.toFixed(1)}" y="${mid}" width="${bw}" height="${(f.gone * scale).toFixed(1)}"/></g>`;
  }).join('');
  const total = flow.reduce((a, f) => [a[0] + f.new, a[1] + f.gone], [0, 0]);
  const text = `In- en uitstroom per week: samen ${total[0]} nieuw en ${total[1]} niet meer gezien`;
  return `<svg class="flow" viewBox="0 0 ${w} ${h}" role="img" aria-label="${esc(text)}">
    <line class="grid-line" x1="0" x2="${w}" y1="${mid}" y2="${mid}"/>${bars}</svg>`;
}

function drops(m) {
  const d = m.drops;
  const share = d.share == null ? tooFew(d.n_cars) : `${fmt(d.share)}%`;
  const eur = d.median_drop_eur.value == null ? tooFew(d.median_drop_eur.n) : euro(d.median_drop_eur.value);
  const pct = d.median_drop_pct.value == null ? '' : `${fmt(d.median_drop_pct.value)}% · `;
  const first = d.median_days_to_first.value == null ? tooFew(d.median_days_to_first.n)
    : `${fmt(Math.round(d.median_days_to_first.value))} dagen`;
  return `<dl class="facts">
    <div><dt>Auto's met minstens één verlaging</dt><dd>${share}</dd><dd class="small muted">${fmt(d.with_drop)} van
      ${fmt(d.n_cars)} auto's</dd></div>
    <div><dt>Mediane verlaging</dt><dd>${eur}</dd><dd class="small muted">${pct}n = ${fmt(d.median_drop_eur.n)}</dd></div>
    <div><dt>Mediane tijd tot eerste verlaging</dt><dd>${first}</dd><dd class="small muted">alleen auto's die na de start
      van het volgen verschenen</dd></div></dl>
    <h4 class="sub-head">In- en uitstroom per week</h4>${flowBars(m.flow)}
    <div class="legend"><span class="lg lg-new">Nieuw</span><span class="lg lg-gone">Niet meer gezien</span></div>`;
}

function textCoverage(m) {
  if (!m.for_sale || m.with_text === m.for_sale) return '';
  return notice(`Advertentietekst beschikbaar voor <strong>${fmt(m.with_text)} van ${fmt(m.for_sale)}</strong>
    auto's. Zonder tekst kan de uitrusting niet worden beoordeeld.
    <a href="#/instellingen?deel=over-de-bron">Zo krijg je meer tekst</a>`, 'info');
}

export async function render(params = new URLSearchParams()) {
  const period = ['30', '90'].includes(params.get('periode')) ? params.get('periode') : '';
  const q = profileQuery();
  const marketQuery = q + (period ? `${q ? '&' : '?'}days=${period}` : '');
  const [m, r, c] = await Promise.all([api('/market' + marketQuery), api('/refresh-runs'), api('/changes' + q)]);
  const profiles = allProfiles();
  if (!profiles.length || (!m.for_sale && !m.tracking_since)) {
    $('#content').innerHTML = startList(profiles, r.items);
    return;
  }
  const profile = currentProfile();
  const sub = `${profile ? profile.title : 'Alle zoekopdrachten'}${m.tracking_since
    ? ` · gevolgd sinds ${datum(m.tracking_since)}` : ''}`;
  const at = c.run ? c.run.finished_at || c.run.created_at : null;
  const since = at ? `Controle van ${datum(at)} (${relatief(at)})` : '';
  const details = c.run ? button('Details', {href: `#/controles/${encodeURIComponent(c.run.id)}`, variant: 'text',
    size: 's'}) : '';
  $('#content').innerHTML = pageHead('Overzicht', sub, periodLinks(period)) + failureNotice() + textCoverage(m) + kpis(m)
    + `<div class="grid grid-2-even">
      ${card('Sinds de vorige controle', c.run ? changesHtml(c.groups, {limit: 4})
        : '<p class="muted">Nog geen geslaagde controle.</p>', {sub: since, actionsHtml: details})}
      ${card('Kansen', opportunities(m), {sub: 'De vijf aantrekkelijkste aanbiedingen'})}</div>
    ${card('Markt door de tijd', timeline(m), {sub: `${fmt(m.timeline.measuring_days)} meetdagen in deze periode · `
      + 'vraagprijzen, geen verkoopprijzen'})}
    <div class="grid grid-2-even">${card('Prijs tegen kilometerstand', scatter(m))}
      ${card('Prijsverlagingen', drops(m), {sub: 'In de gekozen periode'})}</div>`;
}
