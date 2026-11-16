/* Autodetail (in WP-01 nog als modaal venster, geopend via #/auto/<id>). */
import {api} from '../api.js';
import {esc, euro, fmt, dt} from '../format.js';
import {chart} from '../charts.js';
import {$, $$, eligibility, modal, modalHead, table, tag, toast} from '../ui.js';
import {photosOf} from './aanbod.js';

const CLAIM_LABEL = {PRESENT: 'Aanwezig', ABSENT: 'Afwezig', UNKNOWN: 'Onbekend', CONFLICT: 'Tegenstrijdig'};
const CLAIM_TYPE = {PRESENT: 'green', ABSENT: 'red', UNKNOWN: 'grey', CONFLICT: 'amber'};

function gallery(x) {
  const ph = photosOf(x);
  if (!ph.length) return '<p class="micro">Geen foto’s beschikbaar in de bron.</p>';
  const strip = ph.map((u, i) => `<img class="gallery-thumb${i ? '' : ' active'}" data-action="photo"
    data-photo="${esc(u)}" loading="lazy" referrerpolicy="no-referrer" src="${esc(u)}" alt="Foto ${i + 1}">`).join('');
  return `<section class="card gallery"><img id="gallery-main" class="gallery-main" referrerpolicy="no-referrer"
    src="${esc(ph[0])}" alt="">${ph.length > 1 ? `<div class="gallery-strip">${strip}</div>` : ''}
    <p class="micro">${ph.length} foto${ph.length === 1 ? '' : '’s'}</p></section>`;
}

function sourceLinks(o) {
  const l = [];
  if (o.source_url) {
    l.push(`<a class="btn btn-sm" target="_blank" rel="noopener noreferrer" href="${esc(o.source_url)}">
      Advertentie bij ${esc(o.site)} ↗</a>`);
  }
  if (o.click_url && o.click_url !== o.source_url) {
    const label = o.source_url ? 'Via Gaspedaal' : 'Bekijk bij ' + esc(o.site);
    l.push(`<a class="btn btn-sm" target="_blank" rel="noopener noreferrer" href="${esc(o.click_url)}">${label} ↗</a>`);
  }
  return l.join(' ') || 'Onbekend';
}

function negotiation(neg) {
  const cell = (label, value) => `<div><div class="micro">${label}</div><h3>${euro(value)}</h3></div>`;
  return `<section class="card"><div class="card-head"><h3>Onderhandelingsinformatie</h3>
    ${tag(neg.sample_size + ' vergelijkbare auto\'s', 'grey')}</div>
    <div class="stats stats-compact">${cell('Mediaan aanbod', neg.median_asking)}
    ${cell('Verschil mediaan', neg.difference_vs_median_eur)}
    ${cell('Indicatief openingsbod', neg.illustrative_opening_offer)}
    ${cell('Indicatieve streefprijs', neg.illustrative_target)}</div><p class="micro">${esc(neg.assessment)}</p></section>`;
}

function claimRow(id, c) {
  const options = Object.entries(CLAIM_LABEL).map(([v, l]) => `<option value="${v}">${l}</option>`).join('');
  return `<div class="option-claim"><div><strong>${esc(c.label)}</strong>
    <span class="micro">${c.group_name === 'MUST_HAVE' ? 'VERPLICHT' : 'NICE-TO-HAVE'}</span>
    <p class="micro">${esc(c.evidence || c.reason || 'Geen expliciete vermelding')} · ${esc(c.source)}</p></div>
    <div class="inline-actions">${tag(CLAIM_LABEL[c.status], CLAIM_TYPE[c.status])}
    <details class="review"><summary class="btn btn-sm">Corrigeer</summary>
      <form data-submit="review" data-id="${esc(id)}" data-key="${esc(c.criterion_key)}" class="review-form">
        <select name="status" aria-label="Status">${options}</select>
        <input name="evidence" placeholder="Bewijs of dealerbevestiging (optioneel)" maxlength="400">
        <button class="btn btn-sm btn-primary">Opslaan</button></form></details></div></div>`;
}

export async function showCar(id) {
  const x = await api('/listings/' + encodeURIComponent(id));
  const claims = x.claims || [];
  const sources = x.sources || [];
  const sub = `${x.year || '—'} · ${fmt(x.kilometers)} km · ${x.seller || 'Onbekende verkoper'}`;
  const history = x.history.map(o => ({...o, date: dt(o.observed_at), mean_asking: o.price_eur}));
  const sourceRows = sources.map(o => `<tr><td><strong>${esc(o.site)}</strong><br>
    <span class="micro">${esc(o.kind || 'Aanbieder')}</span></td><td>${euro(o.price_eur)}</td>
    <td>${sourceLinks(o)}</td><td>${fmt(o.history.length)}</td></tr>`);
  const fetches = (x.detail_fetches || []).map(d => `<p class="micro">${dt(d.created_at)} · ${esc(d.status)} ·
    ${fmt(d.text_length)} tekens · ${esc(d.error || '')}</p>`).join('');
  const notes = x.notes.map(n => `<p class="micro">${dt(n.created_at)} · ${euro(n.offer_eur)} · ${esc(n.note)}</p>`);
  modal(modalHead(x.title, sub) + `
    <div class="inline-actions detail-actions"><strong class="detail-price">${euro(x.price_eur)}</strong>
      ${eligibility(x.eligibility)}
      <button class="btn btn-sm" data-action="favorite" data-id="${esc(id)}">
        ${x.favorite ? '★ Verwijder favoriet' : '☆ Favoriet'}</button>
      <button class="btn btn-sm" data-action="goto" data-target="aanbieders">
        Bekijk advertentie bij ${sources.length || 'alle'} aanbieders ↓</button></div>
    ${gallery(x)}
    <div class="detail-grid"><section class="card"><div class="card-head"><h3>Prijsgeschiedenis</h3>
      <span class="micro">${x.history.length} metingen</span></div>${chart(history)}</section>
      ${negotiation(x.negotiation)}</div>
    <section class="card" id="aanbieders"><div class="card-head"><h3>Alle aanbieders van deze auto</h3>
      <span class="micro">${sources.length} aanbieders</span></div>
      ${sources.length ? table(['Aanbieder', 'Vraagprijs', 'Links', 'Prijsmetingen'], sourceRows)
        : '<p class="muted">Deze gegevensbron heeft geen individuele aanbieders meegegeven.</p>'}
      ${fetches ? `<details><summary class="micro">Log originele advertentietekst</summary>${fetches}</details>` : ''}
    </section>
    <section class="card"><div class="card-head"><h3>Uitrusting en AI-bewijs</h3>
      <span class="micro">Matchscore: ${fmt(x.score_total)}%</span></div>
      ${claims.map(c => claimRow(id, c)).join('') || '<p class="muted">Nog niet beoordeeld.</p>'}</section>
    <section class="card"><div class="card-head"><h3>Onderhandelingsnotities</h3></div>
      <form data-submit="note" data-id="${esc(id)}" class="form-grid note-form">
        <div class="field"><label>Bod (€)</label><input name="offer_eur" type="number" min="0"></div>
        <div class="field"><label>Notitie</label>
          <input name="note" required placeholder="Dealer gesproken, voorwaarden, voorstel…"></div>
        <button class="btn btn-primary">Opslaan</button></form>
      ${notes.join('')}
    </section>`);
  $$('.review-form select').forEach((s, i) => {
    s.value = claims[i].status;
  });
}

export const actions = {
  async favorite(el) {
    await api('/listings/' + encodeURIComponent(el.dataset.id) + '/favorite', {method: 'POST'});
    await showCar(el.dataset.id);
  },
  photo(el) {
    const main = $('#gallery-main');
    if (main) main.src = el.dataset.photo;
    $$('.gallery-thumb').forEach(i => i.classList.toggle('active', i === el));
  },
  goto(el) {
    document.getElementById(el.dataset.target)?.scrollIntoView({behavior: 'smooth', block: 'start'});
  },
};

export const submits = {
  async review(form) {
    const d = Object.fromEntries(new FormData(form));
    const body = {criterion_key: form.dataset.key, status: d.status, evidence: d.evidence || null};
    await api('/listings/' + encodeURIComponent(form.dataset.id) + '/review', {method: 'POST', body});
    toast('Correctie opgeslagen');
    await showCar(form.dataset.id);
  },
  async note(form) {
    const d = Object.fromEntries(new FormData(form));
    const body = {offer_eur: d.offer_eur ? Number(d.offer_eur) : null, note: d.note};
    await api('/listings/' + encodeURIComponent(form.dataset.id) + '/notes', {method: 'POST', body});
    await showCar(form.dataset.id);
  },
};
