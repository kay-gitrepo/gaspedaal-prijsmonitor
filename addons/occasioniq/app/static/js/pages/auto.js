/* Autodetail als dialoog (#/auto/<id>). In WP-08 wordt dit een eigen pagina. */
import {api} from '../api.js';
import {datum, esc, euro, fmt, dt} from '../format.js';
import {chart} from '../charts.js';
import {AVAILABILITY} from '../labels.js';
import {matchCell, statusChip} from '../status.js';
import {$, $$, button, card, dialogHead, field, icon, openDialog, statusBadge, table, toast} from '../ui.js';
import {equipmentActions, equipmentHtml, openQuestions, questionsHtml} from '../equipment.js';
import {photosOf} from './aanbod.js';

function gallery(x) {
  const ph = photosOf(x);
  if (!ph.length) return '';
  const strip = ph.map((u, i) => `<button type="button" class="gallery-thumb" data-action="photo" data-photo="${esc(u)}"
    aria-label="Foto ${i + 1} tonen"${i ? '' : ' aria-current="true"'}><img loading="lazy" referrerpolicy="no-referrer"
    src="${esc(u)}" alt=""></button>`).join('');
  return card('', `<img id="gallery-main" class="gallery-main" referrerpolicy="no-referrer" src="${esc(ph[0])}"
    alt="Foto van ${esc(x.title)}">${ph.length > 1 ? `<div class="gallery-strip">${strip}</div>` : ''}`);
}

function sourceLinks(o) {
  const links = [];
  if (o.source_url) {
    links.push(button(`Bij ${o.site}`, {href: o.source_url, size: 's', icon: 'external',
      attrs: {target: '_blank', rel: 'noopener noreferrer'}}));
  }
  if (o.click_url && o.click_url !== o.source_url) {
    links.push(button(o.source_url ? 'Via Gaspedaal' : `Bij ${o.site}`, {href: o.click_url, size: 's', icon: 'external',
      attrs: {target: '_blank', rel: 'noopener noreferrer'}}));
  }
  return `<div class="row">${links.join('') || '<span class="muted">Geen link</span>'}</div>`;
}

function negotiation(neg) {
  if (!neg.sample_size) {
    return card('Onderhandelen', '<p class="muted">Te weinig vergelijkbare auto\'s voor een indicatie.</p>');
  }
  const facts = [['Mediane vraagprijs vergelijkbaar', euro(neg.median_asking)],
    ['Verschil met mediaan', euro(neg.difference_vs_median_eur)],
    ['Openingsbod (indicatie)', euro(neg.illustrative_opening_offer)],
    ['Streefprijs (indicatie)', euro(neg.illustrative_target)]];
  return card('Onderhandelen', `<dl class="facts">${facts.map(([k, v]) => `<div><dt>${k}</dt><dd>${v}</dd></div>`).join('')}
    </dl><p class="muted small">Indicatie op basis van vraagprijzen van ${fmt(neg.sample_size)} vergelijkbare auto's
    (n = ${fmt(neg.sample_size)}). Geen verkoopprijzen.</p>`);
}

const TEXT_SOURCE = {
  SOURCE: 'Uit de zoekresultaten', DETAIL_PAGE: 'Van de oorspronkelijke advertentie', MANUAL: 'Door jou toegevoegd',
};

function textCard(x, id) {
  const text = (x.description || '').trim();
  const form = `<form data-submit="description" data-id="${esc(id)}" class="stack">
    ${field({label: 'Advertentietekst', name: 'text', type: 'textarea', value: x.description_source === 'MANUAL' ? text : '',
      hint: 'Plak de omschrijving of uitrustingslijst uit de advertentie. Wordt bij controles nooit overschreven.',
      attrs: {maxlength: 50000, placeholder: 'Bijvoorbeeld: Trekhaak elektrisch uitklapbaar, 22 inch velgen, …'}})}
    <div class="row">${button('Tekst opslaan', {type: 'submit', variant: 'primary'})}
      ${x.description_source === 'MANUAL' ? button('Tekst verwijderen', {variant: 'danger', action: 'clear-description',
        data: {id}}) : ''}</div></form>`;
  if (!text) {
    return card('Advertentietekst', `<p class="muted">Er is geen advertentietekst, dus de uitrusting kan niet worden
      beoordeeld. Plak de tekst uit de advertentie om dat wel te kunnen.</p>
      <details class="disclosure"><summary>${icon('plus')}Advertentietekst toevoegen</summary>${form}</details>`);
  }
  const source = TEXT_SOURCE[x.description_source] || 'Uit de bron';
  return card('Advertentietekst', `<details class="disclosure"><summary>${icon('chevron-down')}Tekst tonen
    (${fmt(text.length)} tekens)</summary><p class="pre-text">${esc(text)}</p></details>
    <details class="disclosure"><summary>${icon('pencil')}${x.description_source === 'MANUAL' ? 'Tekst aanpassen'
      : 'Eigen tekst gebruiken'}</summary>${form}</details>`, {sub: source});
}

export async function showCar(id, {keepScroll = false} = {}) {
  const x = await api('/listings/' + encodeURIComponent(id));
  const claims = x.claims || [];
  const sources = x.sources || [];
  const sub = `${x.year || 'Bouwjaar onbekend'} · ${fmt(x.kilometers)} km · ${x.seller || 'Verkoper onbekend'}`;
  const history = x.history.map(o => ({date: datum(o.observed_at), value: o.price_eur}));
  const sourceRows = sources.map(o => [`<strong>${esc(o.site)}</strong>`, euro(o.price_eur), sourceLinks(o),
    fmt(o.history.length)]);
  const sourceCols = [{label: 'Aanbieder', main: true}, {label: 'Vraagprijs', num: true}, {label: 'Advertentie'},
    {label: 'Metingen', num: true}];
  const notes = x.notes.map(n => `<div class="list-item"><div><strong>${esc(n.note)}</strong>
    <p>${dt(n.created_at)}${n.offer_eur ? ' · bod ' + euro(n.offer_eur) : ''}</p></div></div>`).join('');
  const firstLink = sources.find(o => o.source_url || o.click_url);
  const adLink = firstLink ? button('Bekijk advertentie', {href: firstLink.source_url || firstLink.click_url,
    icon: 'external', attrs: {target: '_blank', rel: 'noopener noreferrer'}}) : '';
  openDialog(dialogHead(x.title, sub) + `
    <div class="detail-top"><span class="detail-price">${euro(x.price_eur)}</span>
      ${statusChip(x)}${statusBadge(AVAILABILITY, x.availability)}
      ${button(x.favorite ? 'Van shortlist halen' : 'Op shortlist zetten', {icon: 'star', action: 'favorite',
        data: {id}, attrs: {'aria-pressed': x.favorite ? 'true' : 'false'}})}${adLink}</div>
    <div class="detail-match">${matchCell(x)}</div>
    ${gallery(x)}
    <div class="detail-grid">
      ${card('Prijsverloop', chart(history, {title: 'Vraagprijs'}), {sub: `${fmt(x.history.length)} metingen`})}
      ${negotiation(x.negotiation)}
    </div>
    ${card('Aanbieders', sources.length ? table(sourceCols, sourceRows)
      : '<p class="muted">De bron gaf geen afzonderlijke aanbieders mee.</p>', {id: 'aanbieders'})}
    ${textCard(x, id)}
    ${card('Uitrusting', equipmentHtml(id, claims), {id: 'uitrusting',
      sub: `${fmt(x.score_total)}% bevestigd · tot ${fmt(x.score_potential)}% mogelijk · `
        + `bewijs voor ${fmt(x.evidence_coverage)}% van het gewicht`})}
    ${card('Vragen aan de verkoper', questionsHtml(x, claims), {id: 'vragen',
      sub: openQuestions(claims).length ? 'Eén vraag per onzekere wens, must-haves eerst' : ''})}
    ${card('Notities', `<form data-submit="note" data-id="${esc(id)}" class="form-grid">
      ${field({label: 'Bod (€)', name: 'offer_eur', type: 'number', attrs: {min: 0}})}
      ${field({label: 'Notitie', name: 'note', attrs: {required: true, placeholder: 'Bijvoorbeeld: dealer gebeld'}})}
      ${button('Notitie opslaan', {type: 'submit', variant: 'primary'})}</form>
      ${notes ? `<div class="list">${notes}</div>` : ''}`)}`, 'dialog-title', {keepScroll});
}

const reload = id => showCar(id, {keepScroll: true});
const equipment = equipmentActions(reload);

export const actions = {
  ...equipment.actions,
  async 'clear-description'(el) {
    await api('/listings/' + encodeURIComponent(el.dataset.id) + '/description', {method: 'POST', body: {text: ''}});
    toast('Eigen tekst verwijderd');
    await reload(el.dataset.id);
  },
  async favorite(el) {
    await api('/listings/' + encodeURIComponent(el.dataset.id) + '/favorite', {method: 'POST'});
    await reload(el.dataset.id);
  },
  photo(el) {
    const main = $('#gallery-main');
    if (main) main.src = el.dataset.photo;
    $$('.gallery-thumb').forEach(i => i.setAttribute('aria-current', String(i === el)));
  },
};

export const changes = {...equipment.changes};

export const submits = {
  ...equipment.submits,
  async description(form) {
    const text = new FormData(form).get('text') || '';
    await api('/listings/' + encodeURIComponent(form.dataset.id) + '/description', {method: 'POST', body: {text}});
    toast('Tekst opgeslagen. De uitrusting wordt bij de volgende controle opnieuw beoordeeld.');
    await reload(form.dataset.id);
  },
  async note(form) {
    const d = Object.fromEntries(new FormData(form));
    const body = {offer_eur: d.offer_eur ? Number(d.offer_eur) : null, note: d.note};
    await api('/listings/' + encodeURIComponent(form.dataset.id) + '/notes', {method: 'POST', body});
    toast('Notitie opgeslagen');
    await reload(form.dataset.id);
  },
};
