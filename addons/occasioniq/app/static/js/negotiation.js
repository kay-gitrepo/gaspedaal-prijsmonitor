/* Onderhandelen op de autopagina: elk getal laat zien of het bekend, geschat of zelf gekozen is. */
import {api} from './api.js';
import {esc, euro, fmt} from './format.js';
import {badge, button, icon, notice, table, toast} from './ui.js';

const r50 = value => Math.round(value / 50) * 50;

const ORIGIN = {known: ['Bekend', 'neutral'], estimate: ['Schatting', 'info'], own: ['Jouw keuze', 'success']};

export function originBadge(source) {
  const [text, variant] = ORIGIN[source] || ['Geen voorstel', 'neutral'];
  return badge(text, variant);
}

function headline(x, v) {
  if (!v.band) return `<p class="lead">${esc(v.message)}</p>`;
  const d = Math.round(v.difference / 50) * 50;
  const sure = v.certainty === 'redelijk' ? 'redelijke zekerheid' : 'lage zekerheid';
  const where = d === 0 ? 'is gelijk aan wat vergelijkbare auto\'s vragen'
    : `ligt ${euro(Math.abs(d))} ${d > 0 ? 'boven' : 'onder'} wat vergelijkbare auto's vragen`;
  return `<p class="lead">Vraagprijs ${euro(x.price_eur)} ${where} <span class="muted">(schatting, n = ${fmt(v.n)},
    ${sure})</span>.</p>`;
}

/** Horizontale band P25–mediaan–P75 met de vraagprijs als markering en het budget als dat er is. */
function bandSvg(x, v) {
  if (!v.band) return '';
  const {p25, median, p75} = v.band;
  const values = [p25, p75, x.price_eur].concat(v.budget ? [v.budget] : []);
  let lo = Math.min(...values);
  let hi = Math.max(...values);
  const pad = Math.max((hi - lo) * 0.12, 500);
  lo -= pad;
  hi += pad;
  const w = window.matchMedia('(max-width: 760px)').matches ? 340 : 640;
  const X = val => 16 + (val - lo) / (hi - lo) * (w - 32);
  const tick = (val, y, text, anchor = 'middle') => `<text x="${X(val).toFixed(1)}" y="${y}" text-anchor="${anchor}">${esc(text)}</text>`;
  const budget = v.budget ? `<line class="band-budget" x1="${X(v.budget).toFixed(1)}" x2="${X(v.budget).toFixed(1)}" y1="24"
    y2="62"/>${tick(v.budget, 86, 'budget')}` : '';
  const summary = `Band van ${euro(p25)} tot ${euro(p75)}, middenwaarde ${euro(median)}, vraagprijs ${euro(x.price_eur)}`
    + (v.budget ? `, budget ${euro(v.budget)}` : '');
  return `<svg class="band-chart" viewBox="0 0 ${w} 96" role="img" aria-label="${esc(summary)}">
    <line class="band-axis" x1="16" x2="${w - 16}" y1="40" y2="40"/>
    <rect class="band-range" x="${X(p25).toFixed(1)}" y="28" width="${(X(p75) - X(p25)).toFixed(1)}" height="24" rx="4"/>
    <line class="band-median" x1="${X(median).toFixed(1)}" x2="${X(median).toFixed(1)}" y1="24" y2="56"/>
    ${budget}
    <path class="band-asking" d="M ${X(x.price_eur).toFixed(1)} 58 l -7 12 h 14 z"/>
    ${tick(p25, 20, 'P25', 'end')}${tick(p75, 20, 'P75', 'start')}<text class="band-asking-label"
      x="${X(x.price_eur).toFixed(1)}" y="86" text-anchor="middle">vraagprijs</text></svg>`;
}

function amountField(key, labelText, help, a, name) {
  const suggested = a.suggested == null ? 'geen voorstel' : euro(a.suggested);
  const own = a.source === 'own';
  return `<div class="amount"><div class="row-between"><label for="amt-${key}"><strong>${labelText}</strong></label>
    ${originBadge(a.value == null ? null : a.source)}</div>
    <div class="amount-value">${a.value == null ? '—' : euro(a.value)}</div>
    <p class="muted small">${esc(help)} Voorstel: ${esc(suggested)}.</p>
    <div class="field"><input id="amt-${key}" class="input" name="${name}" type="number" min="1000" step="250"
      inputmode="numeric" value="${own ? esc(a.value) : ''}" placeholder="Eigen bedrag (leeg = voorstel)"></div></div>`;
}

function argumentsList(v) {
  if (!v.arguments.length) return '';
  const items = v.arguments.map(a => {
    const links = a.links?.length ? `<ul class="arg-links">${a.links.map(l => `<li><a href="#/auto/${encodeURIComponent(l.id)}">
      ${esc(l.title)}</a> · ${euro(l.price_eur)}</li>`).join('')}</ul>` : '';
    return `<li><span>${esc(a.text)}</span> <span class="muted small">· ${esc(a.source)}</span>${links}</li>`;
  }).join('');
  return `<h4>Argumenten</h4><ul class="arguments">${items}</ul>`;
}

function premiums(v) {
  const rows = v.option_premiums.filter(p => p.n_with || p.n_without);
  if (!rows.length) return '';
  const body = rows.map(p => [esc(p.label), `${fmt(p.n_with)} / ${fmt(p.n_without)}`,
    p.premium == null ? '<span class="muted">onvoldoende data</span>'
      : `${p.premium >= 0 ? '+' : '−'} ${euro(Math.abs(p.premium))} <span class="muted small">indicatie, n = ${fmt(p.n_with)}
        / ${fmt(p.n_without)}</span>`]);
  return `<details class="disclosure"><summary>${icon('chevron-down')}Meerprijs van uitrusting (indicatie)</summary>
    <p class="muted small">Mediaan van vergelijkbare auto's mét min zónder de optie; alleen bij minstens 5 en 5 auto's.
    Uitrusting wordt niet verrekend in de bedragen hierboven.</p>
    ${table([{label: 'Wens', main: true}, {label: 'Mét / zónder', num: true}, {label: 'Verschil', num: true}], body)}
    </details>`;
}

function comparables(v) {
  if (!v.comparables.length) return '<p class="muted">Geen vergelijkbare auto\'s in dezelfde zoekopdracht.</p>';
  const columns = [{label: 'Auto', main: true}, {label: 'Vraagprijs', num: true}];
  if (v.corrected) columns.push({label: 'Gecorrigeerd voor km', num: true});
  columns.push({label: 'Km', num: true}, {label: 'Bouwjaar', num: true}, {label: 'Match', num: true},
    {label: 'In beeld', num: true}, {label: 'Verschil'});
  const rows = v.comparables.map(c => {
    const cells = [`<a class="title-link" href="#/auto/${encodeURIComponent(c.id)}">${esc(c.title)}</a>
      ${c.trim ? `<span class="sub">${esc(c.trim)}</span>` : ''}`, euro(c.price_eur)];
    if (v.corrected) cells.push(c.corrected_price == null ? '—' : euro(c.corrected_price));
    cells.push(fmt(c.kilometers), esc(c.year || '—'), `${fmt(c.score_total)}%`, `${fmt(c.days_tracked)} d`,
      esc(c.differences.join(', ') || 'gelijk'));
    return cells;
  });
  return table(columns, rows, {caption: 'Vergelijkbare auto\'s'});
}

export function negotiationHtml(x, v) {
  const slope = v.corrected && v.slope ? `<p class="muted small">Kilometercorrectie: ${euro(Math.abs(v.slope) * 1000)}
    per 1.000 km (Theil–Sen, schatting).</p>` : '';
  return `<div class="stack">${headline(x, v)}${bandSvg(x, v)}
    <div class="known-row"><span>Vraagprijs ${euro(x.price_eur)} ${originBadge('known')}</span>
      ${v.band ? `<span>Band ${euro(r50(v.band.p25))} – ${euro(r50(v.band.p75))}, middenwaarde
        ${euro(r50(v.band.median))} ${originBadge('estimate')}</span>` : ''}
      ${v.budget ? `<span>Budget ${euro(v.budget)} ${originBadge('known')}</span>` : ''}</div>
    ${v.note ? notice(esc(v.note), 'info') : ''}
    <form data-submit="amounts" data-id="${esc(x.id)}" class="amounts">
      ${amountField('opening', 'Openingsbod', 'Laagste van vraagprijs en P25.', v.amounts.opening, 'my_opening')}
      ${amountField('target', 'Streefprijs', 'Laagste van vraagprijs en mediaan.', v.amounts.target, 'my_target')}
      ${amountField('limit', 'Grens', v.budget ? 'Laagste van je budget en P75.' : 'P75 (stel een budget in bij de '
        + 'zoekopdracht).', v.amounts.limit, 'my_max')}
      <div class="row amounts-actions">${button('Bedragen opslaan', {type: 'submit', variant: 'primary'})}
        <span class="muted small">Leeg laten = het voorstel geldt. Bedragen zijn afgerond op € 250.</span></div></form>
    ${argumentsList(v)}${premiums(v)}
    <h4>Vergelijkbare auto's <span class="muted small">(${fmt(v.n)} · ${esc(v.level_reason)})</span></h4>
    ${slope}${comparables(v)}
    <p class="muted small">Gebaseerd op vraagprijzen van auto's die nu te koop staan. Werkelijke verkoopprijzen zijn
    niet bekend.</p></div>`;
}

/** "€ 1.600 onder" (groen) of "€ 2.100 boven"; "—" bij te weinig vergelijkbare auto's. */
export function marketCell(x) {
  if (x.market_diff == null) {
    return `<span class="muted" title="Te weinig vergelijkbare auto's (n = ${fmt(x.market_n ?? 0)})">—</span>`;
  }
  const d = Math.round(x.market_diff / 50) * 50;
  if (d === 0) return '<span>gelijk</span><span class="sub">schatting, n = ' + fmt(x.market_n) + '</span>';
  return `<span class="${d < 0 ? 'text-success' : ''}">${euro(Math.abs(d))} ${d < 0 ? 'onder' : 'boven'}</span>
    <span class="sub">schatting, n = ${fmt(x.market_n)}</span>`;
}

export function negotiationSubmits(reload) {
  return {
    async amounts(form) {
      const d = Object.fromEntries(new FormData(form));
      const num = v => (v ? Number(v) : null);
      const body = {my_opening: num(d.my_opening), my_target: num(d.my_target), my_max: num(d.my_max)};
      await api(`/listings/${encodeURIComponent(form.dataset.id)}/negotiation`, {method: 'PUT', body});
      toast('Bedragen opgeslagen');
      await reload(form.dataset.id);
    },
  };
}
