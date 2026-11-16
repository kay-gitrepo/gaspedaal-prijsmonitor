import {api} from '../api.js';
import {datum, esc, euro, fmt, relatief} from '../format.js';
import {chart} from '../charts.js';
import {RUN_STATE, TRIGGER, label} from '../labels.js';
import {eligibilityBadge, matchCell} from '../status.js';
import {$, button, card, icon, notice, pageHead, skeletons, stat, statusBadge, table} from '../ui.js';
import {allProfiles, profileQuery} from '../context.js';
import {failureNotice} from '../freshness.js';

export function skeleton() {
  return skeletons.head() + skeletons.stats() + skeletons.block() + skeletons.rows(4);
}

export function wishesSeen() {
  try {
    return localStorage.getItem('occasioniq.wensen-bekeken') === '1';
  } catch {
    return false;
  }
}

function runItem(x) {
  const found = x.summary.found ?? 0;
  return `<a class="list-item" href="#/controles/${encodeURIComponent(x.id)}"><div>
    <strong>${esc(relatief(x.created_at))}</strong>
    <p>${esc(label(TRIGGER, x.trigger_source))} · ${fmt(found)} auto's</p></div>${statusBadge(RUN_STATE, x.state)}</a>`;
}

function carRow(x) {
  return [
    `<a class="title-link" href="#/auto/${encodeURIComponent(x.id)}">${esc(x.title)}</a>
      <span class="sub">${esc(x.seller || 'Verkoper onbekend')}</span>`,
    euro(x.price_eur),
    fmt(x.kilometers),
    matchCell(x, {detail: false}),
    eligibilityBadge(x),
  ];
}

function step(done, title, text, actionHtml) {
  return `<li class="${done ? 'done' : ''}"><span class="step-dot">${done ? icon('check') : ''}</span>
    <div class="step-text"><strong>${esc(title)}</strong><p>${esc(text)}</p></div>
    ${done ? '<span class="badge badge-success">Klaar</span>' : actionHtml}</li>`;
}

function textCoverage(d) {
  if (!d.active_listings || d.with_text === d.active_listings) return '';
  return notice(`Advertentietekst beschikbaar voor <strong>${fmt(d.with_text)} van ${fmt(d.active_listings)}</strong>
    auto's. Zonder tekst kan de uitrusting niet worden beoordeeld.
    <a href="#/instellingen?deel=over-de-bron">Zo krijg je meer tekst</a>`, 'info');
}

/** Startlijst voor een nieuwe installatie: vier stappen met hun status. */
function startList(profiles, runs) {
  const checked = runs.some(r => ['COMPLETE', 'PARTIAL'].includes(r.state));
  const viaHa = runs.some(r => r.trigger_source === 'HOME_ASSISTANT');
  const first = profiles[0];
  return pageHead('Welkom bij OccasionIQ', 'Vier stappen naar je eerste overzicht van de markt.') + card('', `<ol class="checklist">
    ${step(profiles.length > 0, 'Zoekopdracht toevoegen', 'Plak de zoeklink van Gaspedaal met jouw filters.',
      button('Toevoegen', {variant: 'primary', href: '#/zoekopdrachten'}))}
    ${step(wishesSeen(), 'Wensen kiezen', 'Welke uitrusting moet de auto hebben, en wat is mooi meegenomen?',
      button('Wensen bekijken', {href: '#/wensen'}))}
    ${step(checked, 'Eerste controle', 'Haal de auto\'s en vraagprijzen van je zoekopdracht op.',
      first ? button('Nu controleren', {variant: 'primary', icon: 'refresh', action: 'refresh-all'}) : '')}
    ${step(viaHa, 'Automatisch laten controleren', 'Laat Home Assistant op vaste tijden een controle starten.',
      button('Zo stel je het in', {href: '#/instellingen'}))}</ol>`);
}

export async function render() {
  const q = profileQuery();
  const [d, l, r] = await Promise.all([api('/dashboard' + q), api('/listings' + q), api('/refresh-runs')]);
  const profiles = allProfiles();
  if (!profiles.length || !l.items.length) {
    $('#content').innerHTML = startList(profiles, r.items);
    return;
  }
  const active = l.items.filter(x => x.availability === 'ACTIVE');
  const best = active.slice(0, 6);
  const trend = d.price_trend.map(t => ({x: t.date, y: t.mean_asking}));
  const runs = r.items.slice(0, 5).map(runItem).join('');
  const columns = [{label: 'Auto', main: true}, {label: 'Vraagprijs', num: true}, {label: 'Km', num: true},
    {label: 'Match'}, {label: 'Status'}];
  $('#content').innerHTML = pageHead('Overzicht', 'Vraagprijzen, aanbod en je beste kandidaten in één oogopslag.',
    button('Naar het aanbod', {href: '#/aanbod', icon: 'car'})) + failureNotice() + `
    <div class="stats">
      ${stat('Te koop', fmt(d.active_listings), 'auto\'s in deze zoekopdracht', 'car')}
      ${stat('Mediane vraagprijs', euro(d.median_asking), 'vraagprijs, geen verkoopprijs', 'euro')}
      ${stat('Voldoet', fmt(d.matches), 'alle must-haves bevestigd', 'check-circle')}
      ${stat('Gemiddelde match', d.average_score == null ? '—' : fmt(d.average_score) + '%',
        `over ${fmt(d.with_text)} auto's met advertentietekst`, 'wensen')}
    </div>
    ${textCoverage(d)}
    <div class="grid grid-2">
      ${card('Gemiddelde vraagprijs per dag', chart({series: [{name: 'Gemiddelde', type: 'line', points: trend}],
        title: 'Gemiddelde vraagprijs'}),
        {sub: 'Niet gecorrigeerd voor wisselend aanbod'})}
      ${card('Laatste controles', runs ? `<div class="list">${runs}</div>` : '<p class="muted">Nog geen controle.</p>',
        {actionsHtml: button('Alle controles', {href: '#/controles', variant: 'text', size: 's'})})}
    </div>
    ${card('Beste kandidaten', table(columns, best.map(carRow), {empty: 'Nog geen auto\'s te koop.'}),
      {sub: 'Te koop, gesorteerd op match en vraagprijs'})}`;
}
