/* Aanbod: tabs, filters en sortering staan in het adres (#/aanbod?tab=voldoet&sort=prijs), zodat terugkeren
 * uit een auto dezelfde lijst geeft. Sorteren, filteren en zoeken gebeurt in de browser (maximaal 1000 rijen). */
import {api} from '../api.js';
import {datum, esc, euro, fmt, relatief} from '../format.js';
import {AVAILABILITY} from '../labels.js';
import {$, badge, button, card, emptyState, icon, notice, pageHead, skeletons, statusBadge, table, tabs} from '../ui.js';
import {profileId, profileQuery} from '../context.js';
import {matchCell, statusChip} from '../status.js';
import {failureNotice} from '../freshness.js';
import {marketCell} from '../negotiation.js';

let items = [];
let state = {};

const TABS = [
  {key: 'voldoet', label: 'Voldoet', test: x => x.availability === 'ACTIVE' && x.eligibility === 'MATCH', sort: 'markt'},
  {key: 'controleren', label: 'Nog te controleren', sort: 'potentie',
    test: x => x.availability === 'ACTIVE' && ['UNVERIFIED', 'REVIEW'].includes(x.eligibility)},
  {key: 'valtaf', label: 'Valt af', test: x => x.availability === 'ACTIVE' && x.eligibility === 'REJECTED', sort: 'prijs'},
  {key: 'verdwenen', label: 'Verdwenen', sort: 'laatstgezien',
    test: x => ['MISSING_UNCONFIRMED', 'OFF_MARKET'].includes(x.availability)},
  {key: 'alles', label: 'Alles', test: () => true, sort: 'prijs'},
];

const SORTS = {
  prijs: {get: x => x.price_eur, dir: 'op'},
  markt: {get: x => x.market_diff, dir: 'op'},
  km: {get: x => x.kilometers ?? Infinity, dir: 'op'},
  bouwjaar: {get: x => x.year ?? 0, dir: 'af'},
  potentie: {get: x => x.score_potential, dir: 'af'},
  match: {get: x => x.score_total, dir: 'af'},
  inbeeld: {get: x => x.days_tracked, dir: 'af'},
  laatstgezien: {get: x => new Date(x.last_seen).getTime(), dir: 'af'},
};

const FILTERS = {
  q: v => `Zoek: ${v}`, prijsvan: v => `Vanaf ${euro(Number(v))}`, prijstot: v => `Tot ${euro(Number(v))}`,
  kmtot: v => `Tot ${fmt(Number(v))} km`, jaarvan: v => `Bouwjaar vanaf ${v}`, verlaagd: () => 'Alleen prijsverlagingen',
  nieuw: () => 'Alleen nieuw', shortlist: () => 'Alleen shortlist',
};

export function skeleton() {
  return skeletons.head() + '<div class="skeleton sk-text"></div>' + skeletons.rows(8);
}

const tabOf = key => TABS.find(t => t.key === key) || TABS[0];
const daysAgo = (ts, days) => ts && Date.now() - new Date(ts).getTime() <= days * 86400000;

function readState(params) {
  const tab = params.get('tab') || (params.get('shortlist') ? 'alles' : 'voldoet');
  const sort = SORTS[params.get('sort')] ? params.get('sort') : tabOf(tab).sort;
  const dir = ['op', 'af'].includes(params.get('richting')) ? params.get('richting') : SORTS[sort].dir;
  const filters = {};
  for (const k of Object.keys(FILTERS)) if (params.get(k)) filters[k] = params.get(k);
  return {tab: tabOf(tab).key, sort, dir, filters};
}

function hashFor(s) {
  const p = new URLSearchParams({tab: s.tab});
  if (s.sort !== tabOf(s.tab).sort || s.dir !== SORTS[s.sort].dir) {
    p.set('sort', s.sort);
    p.set('richting', s.dir);
  }
  for (const [k, v] of Object.entries(s.filters)) p.set(k, v);
  return `#/aanbod?${p}`;
}

function passes(x, f) {
  if (f.q) {
    const hay = `${x.title} ${x.trim || ''} ${x.seller || ''}`.toLowerCase();
    if (!f.q.toLowerCase().split(/\s+/).every(w => hay.includes(w))) return false;
  }
  if (f.prijsvan && x.price_eur < Number(f.prijsvan)) return false;
  if (f.prijstot && x.price_eur > Number(f.prijstot)) return false;
  if (f.kmtot && (x.kilometers ?? Infinity) > Number(f.kmtot)) return false;
  if (f.jaarvan && (x.year ?? 0) < Number(f.jaarvan)) return false;
  if (f.verlaagd && !(x.price_change_total < 0)) return false;
  if (f.nieuw && !x.is_new) return false;
  if (f.shortlist && !x.favorite) return false;
  return true;
}

function thumb(x) {
  if (!x.photo) return `<div class="thumb thumb-empty">${icon('image')}</div>`;
  return `<img class="thumb" loading="lazy" referrerpolicy="no-referrer" src="${esc(x.photo)}" alt="">`;
}

function labels(x) {
  const out = [];
  if (x.is_new) out.push(badge('Nieuw', 'info'));
  if (daysAgo(x.last_drop_at, 7)) out.push(badge('Prijs verlaagd', 'success', 'trending-down'));
  if (x.reappeared_at && x.availability === 'ACTIVE') out.push(badge('Weer terug', 'info'));
  if (x.provider_count > 1) out.push(badge(`${x.provider_count} aanbieders`, 'neutral'));
  return out.length ? `<div class="row labels">${out.join('')}</div>` : '';
}

export function priceChange(x) {
  const d = x.price_change_total;
  if (!d) return '';
  const cls = d < 0 ? 'text-success' : 'text-danger';
  return `<span class="sub ${cls}">${icon(d < 0 ? 'trending-down' : 'trending-up', 'icon-sm')} ${euro(Math.abs(d))}
    sinds eerste prijs</span>`;
}

export function inView(x) {
  if (x.seen_since_start) {
    return `<span title="Stond al te koop toen het volgen begon; werkelijke looptijd is langer.">≥ ${fmt(x.days_tracked)}
      dagen</span>`;
  }
  return `${fmt(x.days_tracked)} ${x.days_tracked === 1 ? 'dag' : 'dagen'}`;
}

function star(x) {
  return `<button type="button" class="btn btn-text btn-icon btn-s star${x.favorite ? ' on' : ''}" data-action="star"
    data-id="${esc(x.id)}" aria-pressed="${x.favorite ? 'true' : 'false'}" title="${x.favorite ? 'Van shortlist halen'
    : 'Op shortlist zetten'}">${icon('star', x.favorite ? 'icon-fill' : '')}<span class="sr-only">Shortlist</span></button>`;
}

function titleCell(x) {
  const sub = [x.trim, x.seller].filter(Boolean).map(esc).join(' · ');
  return `<a class="title-link" href="#/auto/${encodeURIComponent(x.id)}">${esc(x.title)}</a>
    ${sub ? `<span class="sub">${sub}</span>` : ''}${labels(x)}`;
}

function status(x) {
  const chips = [statusChip(x)];
  if (x.availability !== 'ACTIVE') chips.push(statusBadge(AVAILABILITY, x.availability));
  return `<div class="row">${chips.join('')}</div>`;
}

function columns(gone) {
  const base = [{label: 'Foto', media: true}, {label: 'Auto', main: true},
    {label: 'Bouwjaar', num: true, sort: 'bouwjaar'}, {label: 'Km', num: true, sort: 'km'}];
  if (gone) {
    return base.concat([{label: 'Laatst bekende vraagprijs', num: true, sort: 'prijs'},
      {label: 'Laatst gezien', sort: 'laatstgezien'}, {label: 'In beeld', num: true, sort: 'inbeeld'},
      {label: 'Status'}, {label: 'Shortlist'}]);
  }
  return base.concat([{label: 'Vraagprijs', num: true, sort: 'prijs'}, {label: 't.o.v. markt', num: true, sort: 'markt'},
    {label: 'Match', sort: state.tab === 'controleren' ? 'potentie' : 'match'}, {label: 'In beeld', num: true, sort: 'inbeeld'},
    {label: 'Status'}, {label: 'Shortlist'}]);
}

function row(x, gone) {
  const head = [thumb(x), titleCell(x), esc(x.year || '—'), fmt(x.kilometers)];
  if (gone) {
    return head.concat([`<strong>${euro(x.price_eur)}</strong>`, `<div>${esc(datum(x.last_seen))}<span class="sub">
      ${esc(relatief(x.last_seen))}</span></div>`, inView(x), status(x), star(x)]);
  }
  return head.concat([`<div><strong>${euro(x.price_eur)}</strong>${priceChange(x)}</div>`, `<div>${marketCell(x)}</div>`,
    matchCell(x, {detail: false}) + (!profileId() && x.score_profile_title
      ? `<span class="sub">volgens ${esc(x.score_profile_title)}</span>` : ''),
    inView(x), status(x), star(x)]);
}

const EMPTY = {
  voldoet: ['Nog geen auto die aan al je must-haves voldoet',
    'Bekijk de auto\'s die nog te controleren zijn, of pas je wensen aan.', '#/aanbod?tab=controleren',
    'Naar Nog te controleren'],
  controleren: ['Niets meer te controleren', 'Alle auto\'s zijn beoordeeld.', '#/aanbod?tab=voldoet', 'Naar Voldoet'],
  valtaf: ['Er valt geen auto af', 'Geen enkele auto mist aantoonbaar een must-have.', '#/aanbod?tab=voldoet', 'Naar Voldoet'],
  verdwenen: ['Geen verdwenen auto\'s', 'Alle gevolgde auto\'s staan nog te koop.', '#/aanbod?tab=voldoet', 'Naar Voldoet'],
  alles: ['Nog geen auto\'s', 'Na de eerste controle van een zoekopdracht verschijnen hier de auto\'s.', '#/zoekopdrachten',
    'Naar zoekopdrachten'],
};

function chipsHtml() {
  return Object.entries(state.filters).map(([k, v]) => `<span class="chip">${esc(FILTERS[k](v))}<button type="button"
    data-action="clear-filter" data-key="${k}" aria-label="Filter ${esc(FILTERS[k](v))} verwijderen">${icon('x', 'icon-sm')}
    </button></span>`).join('');
}

function filterBar() {
  const f = state.filters;
  const val = k => esc(f[k] || '');
  const num = (id, key, text, step) => `<div class="field filter-num"><label for="${id}">${text}</label>
    <input id="${id}" type="number" inputmode="numeric" step="${step}" data-change="filter" data-key="${key}"
    value="${val(key)}"></div>`;
  const check = (k, text) => `<label class="check"><input type="checkbox" data-change="filter" data-key="${k}"
    ${f[k] ? 'checked' : ''}> ${text}</label>`;
  const n = Object.keys(f).length;
  const openAttr = window.matchMedia('(max-width: 760px)').matches && !n ? '' : ' open';
  return `<details class="disclosure filter-details"${openAttr}><summary>${icon('chevron-down')}Filters${n ? ` (${n} actief)`
    : ''}</summary><div class="filters"><div class="field filter-q"><label for="f-q">Zoeken</label>
      <input id="f-q" type="search" data-input="filter" data-key="q" value="${val('q')}" placeholder="Titel of verkoper">
    </div>${num('f-pv', 'prijsvan', 'Prijs vanaf', 1000)}${num('f-pt', 'prijstot', 'Prijs tot', 1000)}
    ${num('f-km', 'kmtot', 'Km tot', 5000)}${num('f-jr', 'jaarvan', 'Bouwjaar vanaf', 1)}</div>
    <div class="filters">${check('verlaagd', 'Alleen prijsverlagingen')}${check('nieuw', 'Alleen nieuw')}
    ${check('shortlist', 'Alleen shortlist')}</div></details>`;
}

function draw() {
  const tab = tabOf(state.tab);
  const gone = tab.key === 'verdwenen';
  const s = SORTS[state.sort];
  const filtered = items.filter(x => passes(x, state.filters));
  const cars = filtered.filter(tab.test).sort((a, b) => {
    const [va, vb] = [s.get(a), s.get(b)];
    if (va == null || vb == null) return (va == null) - (vb == null) || a.price_eur - b.price_eur;
    const d = va - vb;
    return (state.dir === 'op' ? d : -d) || a.price_eur - b.price_eur;
  });
  const tabItems = TABS.map(t => ({key: t.key, label: t.label, count: filtered.filter(t.test).length,
    href: hashFor({...state, tab: t.key, sort: t.sort, dir: SORTS[t.sort].dir})}));
  const [title, text, href, action] = EMPTY[tab.key];
  const filtersOn = Object.keys(state.filters).length;
  const body = cars.length ? table(columns(gone), cars.map(x => row(x, gone)),
    {sort: {key: state.sort, dir: state.dir === 'op' ? 'asc' : 'desc'}, caption: `Aanbod: ${tab.label}`})
    : emptyState({iconName: 'search', title: filtersOn ? 'Geen auto\'s met deze filters' : title,
      text: filtersOn ? 'Verwijder een filter om meer auto\'s te zien.' : text,
      actionHtml: filtersOn ? button('Filters wissen', {action: 'clear-filters'}) : button(action, {href})});
  $('#active-filters').innerHTML = chipsHtml();
  $('#offers').innerHTML = tabs(tabItems, tab.key, 'Aanbod')
    + (gone && cars.length ? notice('Laatst bekende vraagprijzen. Dit zijn geen verkoopprijzen en geen bewijs van '
      + 'verkoop.', 'warning') : '') + body;
  const nav = $('#offers .tabs');
  const active = $('#offers .tab[aria-current]');
  if (nav && active) nav.scrollLeft = Math.max(0, active.offsetLeft - nav.offsetLeft - 16);
}

/** Werk het adres bij zonder de pagina opnieuw te laden, en teken de lijst. */
function sync(redrawFilters = false) {
  history.replaceState(null, '', hashFor(state));
  window.dispatchEvent(new CustomEvent('occasioniq:query'));
  if (redrawFilters) $('#filter-bar').innerHTML = filterBar();
  draw();
}

export async function render(params = new URLSearchParams()) {
  const data = await api('/listings' + profileQuery());
  items = data.items;
  state = readState(params);
  const title = state.filters.shortlist ? 'Shortlist' : 'Aanbod';
  $('#content').innerHTML = pageHead(title, 'Alle gevolgde auto\'s met vraagprijs, prijsverloop, match en status.',
    button('Prijshistorie downloaden', {href: '/api/v1/export/observations.csv', icon: 'download'}))
    + failureNotice() + card('', `<div id="filter-bar">${filterBar()}</div><div class="chips active-filters" id="active-filters"
      aria-live="polite"></div><div id="offers"></div>`, {cls: 'offers-card'});
  draw();
}

let typing = null;

export const actions = {
  sort(el) {
    const key = el.dataset.key;
    state.dir = state.sort === key ? (state.dir === 'op' ? 'af' : 'op') : SORTS[key].dir;
    state.sort = key;
    sync();
    $(`#offers [data-key="${key}"]`)?.focus();
  },
  'clear-filter'(el) {
    delete state.filters[el.dataset.key];
    sync(true);
  },
  'clear-filters'() {
    state.filters = {};
    sync(true);
  },
  async star(el) {
    const r = await api('/listings/' + encodeURIComponent(el.dataset.id) + '/favorite', {method: 'POST'});
    const x = items.find(i => i.id === el.dataset.id);
    x.favorite = r.favorite ? 1 : 0;
    draw();
    $(`#offers [data-action="star"][data-id="${CSS.escape(x.id)}"]`)?.focus();
  },
};

export const changes = {
  filter(el) {
    const v = el.type === 'checkbox' ? (el.checked ? '1' : '') : el.value.trim();
    if (v) state.filters[el.dataset.key] = v;
    else delete state.filters[el.dataset.key];
    sync();
  },
};

export const inputs = {
  filter(el) {
    clearTimeout(typing);
    typing = setTimeout(() => {
      const v = el.value.trim();
      if (v) state.filters.q = v;
      else delete state.filters.q;
      sync();
    }, 250);
  },
};
