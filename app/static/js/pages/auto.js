/* Autodetail als dialoog (#/auto/<id>). In WP-08 wordt dit een eigen pagina. */
import {api} from '../api.js';
import {datum, esc, euro, fmt, dt} from '../format.js';
import {chart} from '../charts.js';
import {AVAILABILITY, CLAIM, CLAIM_SOURCE, ELIGIBILITY, GROUP, label} from '../labels.js';
import {$, $$, button, card, dialogHead, field, icon, openDialog, segment, statusBadge, table, toast} from '../ui.js';
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

function claimItem(id, c) {
  const options = [['PRESENT', 'Aanwezig'], ['ABSENT', 'Afwezig'], ['UNKNOWN', 'Onbekend'], ['CONFLICT', 'Tegenstrijdig']];
  const quote = c.evidence ? `“${esc(c.evidence)}”` : esc(c.reason || 'Niet genoemd in de advertentie');
  return `<div class="list-item"><div><strong>${esc(c.label)}</strong>
    <span class="muted small"> · ${esc(label(GROUP, c.group_name))}</span>
    <p>${quote} · ${esc(label(CLAIM_SOURCE, c.source, 'Uit de advertentie'))}</p>
    <details class="disclosure"><summary>${icon('chevron-down')}Corrigeren</summary>
      <form class="claim-form" data-submit="review" data-id="${esc(id)}" data-key="${esc(c.criterion_key)}">
        ${segment('status', options, c.status, {label: `Oordeel over ${c.label}`})}
        <input class="input" name="evidence" maxlength="400" aria-label="Bron of toelichting"
          placeholder="Bron, bijvoorbeeld: dealer bevestigd per mail">
        ${button('Opslaan', {type: 'submit', variant: 'primary', size: 's'})}</form></details></div>
    ${statusBadge(CLAIM, c.status)}</div>`;
}

export async function showCar(id) {
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
      ${statusBadge(ELIGIBILITY, x.eligibility)}${statusBadge(AVAILABILITY, x.availability)}
      ${button(x.favorite ? 'Van shortlist halen' : 'Op shortlist', {icon: 'star', action: 'favorite',
        data: {id}, attrs: {'aria-pressed': x.favorite ? 'true' : 'false'}})}${adLink}</div>
    ${gallery(x)}
    <div class="detail-grid">
      ${card('Prijsverloop', chart(history, {title: 'Vraagprijs'}), {sub: `${fmt(x.history.length)} metingen`})}
      ${negotiation(x.negotiation)}
    </div>
    ${card('Aanbieders', sources.length ? table(sourceCols, sourceRows)
      : '<p class="muted">De bron gaf geen afzonderlijke aanbieders mee.</p>', {id: 'aanbieders'})}
    ${card('Uitrusting', claims.length ? `<div class="list">${claims.map(c => claimItem(id, c)).join('')}</div>`
      : '<p class="muted">Nog niet beoordeeld.</p>', {sub: `Match ${fmt(x.score_total)}%`})}
    ${card('Notities', `<form data-submit="note" data-id="${esc(id)}" class="form-grid">
      ${field({label: 'Bod (€)', name: 'offer_eur', type: 'number', attrs: {min: 0}})}
      ${field({label: 'Notitie', name: 'note', attrs: {required: true, placeholder: 'Bijvoorbeeld: dealer gebeld'}})}
      ${button('Notitie opslaan', {type: 'submit', variant: 'primary'})}</form>
      ${notes ? `<div class="list">${notes}</div>` : ''}`)}`);
}

export const actions = {
  async favorite(el) {
    await api('/listings/' + encodeURIComponent(el.dataset.id) + '/favorite', {method: 'POST'});
    await showCar(el.dataset.id);
  },
  photo(el) {
    const main = $('#gallery-main');
    if (main) main.src = el.dataset.photo;
    $$('.gallery-thumb').forEach(i => i.setAttribute('aria-current', String(i === el)));
  },
};

export const submits = {
  async review(form) {
    const d = Object.fromEntries(new FormData(form));
    const body = {criterion_key: form.dataset.key, status: d.status, evidence: d.evidence || null};
    await api('/listings/' + encodeURIComponent(form.dataset.id) + '/review', {method: 'POST', body});
    toast('Oordeel opgeslagen');
    await showCar(form.dataset.id);
  },
  async note(form) {
    const d = Object.fromEntries(new FormData(form));
    const body = {offer_eur: d.offer_eur ? Number(d.offer_eur) : null, note: d.note};
    await api('/listings/' + encodeURIComponent(form.dataset.id) + '/notes', {method: 'POST', body});
    toast('Notitie opgeslagen');
    await showCar(form.dataset.id);
  },
};
