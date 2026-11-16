import {api} from '../api.js';
import {datum, esc, euro, fmt, relatief} from '../format.js';
import {chart} from '../charts.js';
import {ELIGIBILITY, RUN_STATE, TRIGGER, label} from '../labels.js';
import {$, bar, button, card, emptyState, pageHead, skeletons, stat, statusBadge, table} from '../ui.js';

export function skeleton() {
  return skeletons.head() + skeletons.stats() + skeletons.block() + skeletons.rows(4);
}

function runItem(x) {
  const found = x.summary.found ?? 0;
  return `<a class="list-item" href="#/controles/${encodeURIComponent(x.id)}"><div>
    <strong>${esc(relatief(x.created_at))}</strong>
    <p>${esc(label(TRIGGER, x.trigger_source, 'Onbekend'))} · ${fmt(found)} auto's</p></div>
    ${statusBadge(RUN_STATE, x.state)}</a>`;
}

function carRow(x) {
  return [
    `<a class="title-link" href="#/auto/${encodeURIComponent(x.id)}">${esc(x.title)}</a>
      <span class="sub">${esc(x.seller || 'Verkoper onbekend')}</span>`,
    euro(x.price_eur),
    fmt(x.kilometers),
    `${fmt(x.score_total)}%${bar([[x.score_total, 'fill']], `Match ${fmt(x.score_total)} procent`)}`,
    statusBadge(ELIGIBILITY, x.eligibility),
  ];
}

export async function render() {
  const [d, l, r, p] = await Promise.all([api('/dashboard'), api('/listings'), api('/refresh-runs'), api('/profiles')]);
  if (!p.items.length) {
    $('#content').innerHTML = pageHead('Overzicht') + card('', emptyState({
      iconName: 'search', title: 'Nog geen zoekopdracht',
      text: 'Plak een zoeklink van Gaspedaal om te beginnen. Daarna volgt de app de vraagprijzen.',
      actionHtml: button('Zoekopdracht toevoegen', {variant: 'primary', icon: 'plus', href: '#/zoekopdrachten'}),
    }));
    return;
  }
  const active = l.items.filter(x => x.availability === 'ACTIVE');
  const best = active.slice(0, 6);
  const trend = d.price_trend.map(t => ({date: datum(t.date), value: t.mean_asking}));
  const runs = r.items.slice(0, 5).map(runItem).join('');
  const columns = [{label: 'Auto', main: true}, {label: 'Vraagprijs', num: true}, {label: 'Km', num: true},
    {label: 'Match'}, {label: 'Status'}];
  $('#content').innerHTML = pageHead('Overzicht', 'Vraagprijzen, aanbod en je beste kandidaten in één oogopslag.',
    button('Naar het aanbod', {href: '#/aanbod', icon: 'car'})) + `
    <div class="stats">
      ${stat('Te koop', fmt(d.active_listings), 'auto\'s in je zoekopdrachten', 'car')}
      ${stat('Mediane vraagprijs', euro(d.median_asking), 'vraagprijs, geen verkoopprijs', 'euro')}
      ${stat('Voldoet', fmt(d.matches), 'alle must-haves bevestigd', 'check-circle')}
      ${stat('Gemiddelde match', fmt(d.average_score) + '%', '70% must-haves · 30% nice-to-haves', 'wensen')}
    </div>
    <div class="grid grid-2">
      ${card('Gemiddelde vraagprijs per dag', chart(trend, {title: 'Gemiddelde vraagprijs'}),
        {sub: 'Niet gecorrigeerd voor wisselend aanbod'})}
      ${card('Laatste controles', runs ? `<div class="list">${runs}</div>` : '<p class="muted">Nog geen controle.</p>',
        {actionsHtml: button('Alle controles', {href: '#/controles', variant: 'text', size: 's'})})}
    </div>
    ${card('Beste kandidaten', table(columns, best.map(carRow), {empty: 'Nog geen auto\'s te koop.'}),
      {sub: 'Te koop, gesorteerd op match en vraagprijs'})}`;
}
