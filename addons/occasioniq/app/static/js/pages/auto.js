/* Autopagina (#/auto/<id>): het hele verhaal van één auto, met vaste kop en ankernavigatie. */
import {api} from '../api.js';
import {datum, dt, esc, euro, fmt} from '../format.js';
import {chart} from '../charts.js';
import {AVAILABILITY} from '../labels.js';
import {$, $$, badge, button, card, field, icon, menu, notice, skeletons, statusBadge, table, toast} from '../ui.js';
import {matchCell, statusChip} from '../status.js';
import {equipmentActions, equipmentHtml, openQuestions, questionsHtml} from '../equipment.js';
import {lastListHash} from '../router.js';
import {inView, priceChange} from './aanbod.js';
import {negotiationHtml, negotiationSubmits} from '../negotiation.js';
import {follow} from '../refresh.js';
import {profileId} from '../context.js';

let wantedProfile = '';

export function skeleton() {
  return '<div class="skeleton sk-title"></div><div class="skeleton sk-text"></div>'
    + '<div class="grid grid-2">' + skeletons.block() + skeletons.block() + '</div>' + skeletons.block();
}

function photos(x) {
  try {
    return JSON.parse(x.photos_json || '[]');
  } catch {
    return [];
  }
}

function gallery(x) {
  const ph = photos(x);
  if (!ph.length) {
    return `<div class="gallery-empty">${icon('image', 'icon-lg')}<p class="muted">De bron gaf geen foto's mee.</p></div>`;
  }
  const strip = ph.map((u, i) => `<button type="button" class="gallery-thumb" data-action="photo" data-photo="${esc(u)}"
    aria-label="Foto ${i + 1} tonen"${i ? '' : ' aria-current="true"'}><img loading="lazy" referrerpolicy="no-referrer"
    src="${esc(u)}" alt=""></button>`).join('');
  return `<img id="gallery-main" class="gallery-main" referrerpolicy="no-referrer" src="${esc(ph[0])}"
    alt="Foto van ${esc(x.title)}">${ph.length > 1 ? `<div class="gallery-strip">${strip}</div>` : ''}`;
}

function adButton(x) {
  const sources = (x.sources || []).filter(o => o.source_url || o.click_url);
  const ext = {target: '_blank', rel: 'noopener noreferrer'};
  if (sources.length > 1) {
    const items = [...sources].sort((a, b) => (a.price_eur ?? Infinity) - (b.price_eur ?? Infinity))
      .map(o => ({text: `${o.site}${o.price_eur ? ' · ' + euro(o.price_eur) : ''}`, href: o.source_url || o.click_url,
        icon: 'external', attrs: ext}));
    return menu('Bekijk advertentie', items, {text: 'Bekijk advertentie', icon: 'external'});
  }
  const href = sources[0] ? sources[0].source_url || sources[0].click_url : x.url;
  return href ? button('Bekijk advertentie', {href, icon: 'external', size: 's', attrs: ext}) : '';
}

function header(x) {
  const chips = [statusChip(x)];
  if (x.availability !== 'ACTIVE') chips.push(statusBadge(AVAILABILITY, x.availability));
  const sections = [['overzicht', 'Overzicht'], ['prijs', 'Prijs'], ['uitrusting', 'Uitrusting'],
    ['onderhandelen', 'Onderhandelen'], ['notities', 'Notities']];
  return `<div class="car-head"><div class="car-head-inner">
    ${button('Terug naar de lijst', {href: lastListHash(), icon: 'chevron-left', variant: 'text', size: 's'})}
    <div class="row-between"><div class="car-title"><h1>${esc(x.title)}</h1><div class="row car-meta">
      <span class="detail-price">${euro(x.price_eur)}</span>${priceChange(x)}
      <span class="muted small">${icon('clock', 'icon-sm')} in beeld ${inView(x)}</span>${chips.join('')}</div></div>
    <div class="row">${button(x.favorite ? 'Op je shortlist' : 'Op shortlist zetten', {icon: 'star', size: 's',
      action: 'favorite', data: {id: x.id}, cls: x.favorite ? 'star on' : 'star',
      attrs: {'aria-pressed': x.favorite ? 'true' : 'false'}})}${adButton(x)}</div></div>
    <nav class="anchor-nav" aria-label="Onderdelen">${sections.map(([id, t]) => `<button type="button" class="anchor"
      data-action="goto" data-target="${id}">${t}</button>`).join('')}</nav></div></div>`;
}

function goneBar(x) {
  if (['MISSING_UNCONFIRMED', 'OFF_MARKET'].includes(x.availability)) {
    return notice(`Sinds ${esc(datum(x.last_seen))} niet meer gezien. Laatst bekende vraagprijs ${euro(x.price_eur)}.
      Dit zegt niet of en voor welk bedrag de auto is verkocht.`, 'warning');
  }
  if (x.availability === 'OUT_OF_SCOPE') {
    return notice('Deze auto valt buiten de huidige filters van je zoekopdracht en wordt niet meer gevolgd.', 'info');
  }
  return '';
}

function facts(x) {
  const rows = [['Bouwjaar', esc(x.year || 'Onbekend')],
    ['Kilometerstand', x.kilometers != null ? `${fmt(x.kilometers)} km` : 'Onbekend'],
    ['Uitvoering', esc(x.trim || 'Onbekend')], ['Verkoper', esc(x.seller || 'Onbekend')],
    ['Eerste keer gezien', esc(datum(x.first_seen))], ['In beeld', inView(x)],
    ['Eerste vraagprijs', euro(x.first_price)], ['Aanbieders', fmt(x.provider_count)]];
  if (x.license_plate) rows.push(['Kenteken', esc(x.license_plate)]);
  const caveat = x.seen_since_start ? '<p class="muted small">Stond al te koop toen het volgen begon; werkelijke '
    + 'looptijd is langer.</p>' : '';
  return `<dl class="facts">${rows.map(([k, v]) => `<div><dt>${k}</dt><dd>${v}</dd></div>`).join('')}</dl>${caveat}
    <div class="detail-match">${matchCell(x)}</div>`;
}

/** Prijspunten voor de trapgrafiek: eerste waarneming, elke wijziging, niet meer gezien, weer terug. */
function priceSeries(x) {
  const events = [...(x.events || [])].reverse();
  let price = x.first_price;
  const points = [{x: x.first_seen, y: price, marker: 'first', label: 'eerste waarneming'}];
  for (const e of events) {
    if (e.event_type === 'PRICE_CHANGED') {
      price = e.new_price;
      points.push({x: e.created_at, y: price, marker: 'change', label: 'prijswijziging'});
    } else if (e.event_type === 'MISSING_UNCONFIRMED') {
      points.push({x: e.created_at, y: price, marker: 'missing', label: 'niet meer gezien'});
    } else if (e.event_type === 'REAPPEARED') {
      price = e.new_price ?? price;
      points.push({x: e.created_at, y: price, marker: 'back', label: 'weer terug'});
    }
  }
  return points;
}

function changesTable(x) {
  const changes = [...(x.events || [])].reverse().filter(e => e.event_type === 'PRICE_CHANGED');
  if (!changes.length) return '<p class="muted">De vraagprijs is sinds de eerste waarneming niet veranderd.</p>';
  let prevAt = x.first_seen;
  const rows = changes.map(e => {
    const diff = e.new_price - e.previous_price;
    const pct = e.previous_price ? diff / e.previous_price * 100 : 0;
    const days = Math.round((new Date(e.created_at) - new Date(prevAt)) / 86400000);
    prevAt = e.created_at;
    const cls = diff < 0 ? 'text-success' : 'text-danger';
    const sign = diff < 0 ? '−' : '+';
    return [esc(datum(e.created_at)), `${euro(e.previous_price)} → ${euro(e.new_price)}`,
      `<span class="${cls}">${sign} ${euro(Math.abs(diff))}</span>`,
      `<span class="${cls}">${sign}${fmt(Math.abs(Math.round(pct * 10) / 10))}%</span>`, fmt(days)];
  });
  return table([{label: 'Datum', main: true}, {label: 'Van → naar'}, {label: 'Verschil', num: true},
    {label: 'In %', num: true}, {label: 'Dagen sinds vorige', num: true}], rows, {caption: 'Prijswijzigingen'});
}

function providersTable(x) {
  const sources = x.sources || [];
  if (!sources.length) return '<p class="muted">De bron gaf geen afzonderlijke aanbieders mee.</p>';
  const prices = sources.map(o => o.price_eur).filter(v => v != null);
  const low = prices.length > 1 ? Math.min(...prices) : null;
  const ext = {target: '_blank', rel: 'noopener noreferrer'};
  const rows = sources.map(o => [`<strong>${esc(o.site)}</strong>`,
    `${euro(o.price_eur)}${o.price_eur === low ? ' ' + badge('Laagste', 'success') : ''}`,
    (o.source_url || o.click_url) ? button('Open', {href: o.source_url || o.click_url, size: 's', icon: 'external',
      attrs: ext}) : '<span class="muted">Geen link</span>', fmt(o.history.length)]);
  return table([{label: 'Aanbieder', main: true}, {label: 'Vraagprijs', num: true}, {label: 'Advertentie'},
    {label: 'Metingen', num: true}], rows, {caption: 'Prijzen per aanbieder'});
}

const TEXT_SOURCE = {
  SOURCE: 'Uit de zoekresultaten', DETAIL_PAGE: 'Van de oorspronkelijke advertentie', MANUAL: 'Door jou toegevoegd',
};

function textCard(x) {
  const text = (x.description || '').trim();
  const manual = x.description_source === 'MANUAL';
  const form = `<form data-submit="description" data-id="${esc(x.id)}" class="stack">
    ${field({label: 'Advertentietekst', name: 'text', type: 'textarea', value: manual ? text : '',
      hint: 'Plak de omschrijving of uitrustingslijst uit de advertentie. Wordt bij controles nooit overschreven.',
      attrs: {maxlength: 50000, placeholder: 'Bijvoorbeeld: Trekhaak elektrisch uitklapbaar, 22 inch velgen, …'}})}
    <div class="row">${button('Tekst opslaan', {type: 'submit', variant: 'primary'})}
      ${manual ? button('Tekst verwijderen', {variant: 'danger', action: 'clear-description', data: {id: x.id}}) : ''}
    </div></form>`;
  if (!text) {
    return card('Advertentietekst', `<p class="muted">Er is geen advertentietekst, dus de uitrusting kan niet worden
      beoordeeld. Plak de tekst uit de advertentie om dat wel te kunnen.</p>
      <details class="disclosure"><summary>${icon('plus')}Advertentietekst toevoegen</summary>${form}</details>`);
  }
  return card('Advertentietekst', `<details class="disclosure"><summary>${icon('chevron-down')}Tekst tonen
    (${fmt(text.length)} tekens)</summary><p class="pre-text">${esc(text)}</p></details>
    <details class="disclosure"><summary>${icon('pencil')}${manual ? 'Tekst aanpassen' : 'Eigen tekst gebruiken'}</summary>
    ${form}</details>`, {sub: TEXT_SOURCE[x.description_source] || 'Uit de bron'});
}

function notesCard(x) {
  const notes = x.notes.map(n => `<div class="list-item"><div><strong>${esc(n.note)}</strong>
    <p>${dt(n.created_at)}${n.offer_eur ? ' · bod ' + euro(n.offer_eur) : ''}</p></div></div>`).join('');
  return card('Notities', `<form data-submit="note" data-id="${esc(x.id)}" class="form-grid">
    ${field({label: 'Bod (€)', name: 'offer_eur', type: 'number', attrs: {min: 0, step: 250}})}
    ${field({label: 'Notitie', name: 'note', attrs: {required: true, maxlength: 2000,
      placeholder: 'Bijvoorbeeld: dealer gebeld, onderhoudshistorie compleet'}})}
    <div>${button('Notitie opslaan', {type: 'submit', variant: 'primary'})}</div></form>
    ${notes ? `<div class="list">${notes}</div>` : ''}`);
}

function page(x, v) {
  const until = x.availability === 'ACTIVE' ? new Date().toISOString() : x.last_seen;
  const chartHtml = chart({series: [{name: 'Vraagprijs', type: 'step', points: priceSeries(x)}], until,
    title: 'Vraagprijs', summary: `Vraagprijs van ${euro(x.first_price)} naar ${euro(x.price_eur)}; `
      + `${x.price_drop_count} keer verlaagd.`});
  const claims = x.claims || [];
  return header(x) + goneBar(x) + `
    <section id="overzicht" class="grid grid-2 car-section">${card('', gallery(x), {cls: 'gallery-card'})}
      ${card('Kerngegevens', facts(x))}</section>
    <section id="prijs" class="car-section">${card('Prijsverloop', `${chartHtml}
      <div class="legend"><span class="lg lg-first">Eerste waarneming</span><span class="lg lg-change">Prijswijziging</span>
      <span class="lg lg-missing">Niet meer gezien</span><span class="lg lg-back">Weer terug</span></div>`,
      {sub: `${fmt(x.observations)} metingen sinds ${datum(x.first_seen)}`})}
      ${card('Prijswijzigingen', changesTable(x))}${card('Prijzen per aanbieder', providersTable(x))}</section>
    <section id="uitrusting" class="car-section">${textCard(x)}
      ${card('Uitrusting', wishContext(x) + equipmentHtml(x.id, claims, {assessedText: x.assessed_text,
        profileId: x.score_profile_id}), {sub: `${fmt(x.score_total)}% bevestigd · tot `
        + `${fmt(x.score_potential)}% mogelijk · bewijs voor ${fmt(x.evidence_coverage)}% van het gewicht`})}
      ${card('Vragen aan de verkoper', questionsHtml(x, claims), {id: 'vragen',
        sub: openQuestions(claims).length ? 'Eén vraag per onzekere wens, must-haves eerst' : ''})}</section>
    <section id="onderhandelen" class="car-section">${card('Onderhandelen', negotiationHtml(x, v))}</section>
    <section id="notities" class="car-section">${notesCard(x)}</section>`;
}

function load(id) {
  const path = '/listings/' + encodeURIComponent(id);
  const q = wantedProfile ? `?profile_id=${encodeURIComponent(wantedProfile)}` : '';
  return Promise.all([api(path + q), api(path + '/valuation' + q)]);
}

/** Bij een auto in meer zoekopdrachten: welke wensen gelden er, en wisselen. */
function wishContext(x) {
  if (!x.score_profile_title) return '';
  const others = (x.profiles || []).filter(p => p.id !== x.score_profile_id);
  const links = others.map(p => `<a href="#/auto/${encodeURIComponent(x.id)}?zoekopdracht=${encodeURIComponent(p.id)}">
    ${esc(p.title)}</a>`).join(' · ');
  return `<p class="muted small wish-context">Beoordeeld volgens de wensen van <strong>${esc(x.score_profile_title)}</strong>
    ${links ? ` · ook in: ${links}` : ''}</p>`;
}

export async function render(params, id) {
  wantedProfile = params?.get('zoekopdracht') || profileId() || '';
  const [x, v] = await load(id);
  document.title = `${x.title} · OccasionIQ`;
  $('#content').innerHTML = page(x, v);
}

/** Opnieuw tekenen na een wijziging, zonder skelet en met behoud van de scrollpositie. */
async function reload(id) {
  const y = window.scrollY;
  const [x, v] = await load(id);
  $('#content').innerHTML = page(x, v);
  window.scrollTo(0, y);
}

const equipment = equipmentActions(reload);

export const actions = {
  ...equipment.actions,
  goto(el) {
    document.getElementById(el.dataset.target)?.scrollIntoView({block: 'start'});
  },
  photo(el) {
    const main = $('#gallery-main');
    if (main) main.src = el.dataset.photo;
    $$('.gallery-thumb').forEach(i => i.setAttribute('aria-current', String(i === el)));
  },
  async favorite(el) {
    const r = await api('/listings/' + encodeURIComponent(el.dataset.id) + '/favorite', {method: 'POST'});
    toast(r.favorite ? 'Op je shortlist gezet' : 'Van je shortlist gehaald');
    await reload(el.dataset.id);
  },
  async 'clear-description'(el) {
    const r = await api('/listings/' + encodeURIComponent(el.dataset.id) + '/description', {method: 'POST',
      body: {text: ''}});
    toast('Eigen tekst verwijderd');
    await reload(el.dataset.id);
    if (r.run_id) await follow(r.run_id);
  },
};

export const changes = {...equipment.changes};

export const submits = {
  ...equipment.submits,
  ...negotiationSubmits(reload),
  async description(form) {
    const text = new FormData(form).get('text') || '';
    const r = await api('/listings/' + encodeURIComponent(form.dataset.id) + '/description', {method: 'POST', body: {text}});
    toast('Tekst opgeslagen. De uitrusting wordt nu opnieuw beoordeeld.', 'info');
    await reload(form.dataset.id);
    if (r.run_id) await follow(r.run_id);
  },
  async note(form) {
    const d = Object.fromEntries(new FormData(form));
    const body = {offer_eur: d.offer_eur ? Number(d.offer_eur) : null, note: d.note};
    await api('/listings/' + encodeURIComponent(form.dataset.id) + '/notes', {method: 'POST', body});
    toast('Notitie opgeslagen');
    await reload(form.dataset.id);
  },
};
