import {api} from '../api.js';
import {esc, euro, fmt} from '../format.js';
import {AVAILABILITY, ELIGIBILITY} from '../labels.js';
import {$, bar, button, card, emptyState, icon, pageHead, skeletons, statusBadge, table} from '../ui.js';

let items = [];
let sort = {key: 'score', dir: 'desc'};
let shortlistOnly = false;

export function skeleton() {
  return skeletons.head() + skeletons.rows(8);
}

export function photosOf(x) {
  try {
    return JSON.parse(x.photos_json || '[]');
  } catch {
    return [];
  }
}

function thumb(x) {
  const p = photosOf(x)[0];
  if (!p) return `<div class="thumb thumb-empty">${icon('image')}</div>`;
  return `<img class="thumb" loading="lazy" referrerpolicy="no-referrer" src="${esc(p)}" alt="">`;
}

const SORTERS = {
  price: x => x.price_eur,
  km: x => x.kilometers ?? Infinity,
  year: x => x.year ?? 0,
  score: x => x.score_total,
};

function row(x) {
  const status = [statusBadge(ELIGIBILITY, x.eligibility)];
  if (x.availability !== 'ACTIVE') status.push(statusBadge(AVAILABILITY, x.availability));
  const star = x.favorite ? `<span class="badge badge-info">${icon('star')}Shortlist</span>` : '';
  const match = `${fmt(x.score_total)}%${bar([[x.score_must * .7, 'fill'], [x.score_nice * .3, 'fill-2']],
    `Match ${fmt(x.score_total)} procent`)}`;
  return [
    thumb(x),
    `<a class="title-link" href="#/auto/${encodeURIComponent(x.id)}">${esc(x.title)}</a>
      <span class="sub">${esc(x.seller || 'Verkoper onbekend')}</span>${star}`,
    esc(x.year || '—'),
    fmt(x.kilometers),
    `<strong>${euro(x.price_eur)}</strong>`,
    match,
    `<div class="row">${status.join('')}</div>`,
  ];
}

function draw() {
  const must = $('#only-matches').checked;
  shortlistOnly = $('#only-shortlist').checked;
  const fn = SORTERS[sort.key];
  const cars = items.filter(x => (!must || x.eligibility === 'MATCH') && (!shortlistOnly || x.favorite))
    .sort((a, b) => (fn(a) - fn(b)) * (sort.dir === 'asc' ? 1 : -1));
  const columns = [{label: 'Foto', media: true}, {label: 'Auto', main: true}, {label: 'Bouwjaar', num: true, sort: 'year'},
    {label: 'Km', num: true, sort: 'km'}, {label: 'Vraagprijs', num: true, sort: 'price'}, {label: 'Match', sort: 'score'},
    {label: 'Status'}];
  $('#offers-count').textContent = `${fmt(cars.length)} van ${fmt(items.length)} auto's`;
  $('#offers-table').innerHTML = cars.length ? table(columns, cars.map(row), {sort, caption: 'Aanbod'})
    : emptyState({iconName: 'search', title: 'Geen auto\'s met deze filters',
      text: 'Zet een filter uit om meer auto\'s te zien.'});
}

export async function render(params = new URLSearchParams()) {
  const data = await api('/listings');
  items = data.items;
  shortlistOnly = params.get('shortlist') === '1';
  const title = shortlistOnly ? 'Shortlist' : 'Aanbod';
  const intro = shortlistOnly ? 'De auto\'s die je hebt bewaard.' : 'Alle gevolgde auto\'s met vraagprijs, match en status.';
  if (!items.length) {
    $('#content').innerHTML = pageHead(title, intro) + card('', emptyState({iconName: 'car', title: 'Nog geen auto\'s',
      text: 'Na de eerste controle van een zoekopdracht verschijnen hier de auto\'s.',
      actionHtml: button('Naar zoekopdrachten', {variant: 'primary', href: '#/zoekopdrachten'})}));
    return;
  }
  $('#content').innerHTML = pageHead(title, intro,
    button('Prijshistorie downloaden', {href: '/api/v1/export/observations.csv', icon: 'download'})) + `
    <section class="card"><div class="filters">
      <label class="check"><input id="only-matches" type="checkbox" data-change="offers-filter"> Alleen auto's die voldoen</label>
      <label class="check"><input id="only-shortlist" type="checkbox" data-change="offers-filter"
        ${shortlistOnly ? 'checked' : ''}> Alleen shortlist</label>
      <span class="muted small" id="offers-count"></span></div><div id="offers-table"></div></section>`;
  draw();
}

export const actions = {
  sort(el) {
    if (!$('#offers-table')?.contains(el)) return;
    const key = el.dataset.key;
    sort = sort.key === key ? {key, dir: sort.dir === 'asc' ? 'desc' : 'asc'} : {key, dir: key === 'score' ? 'desc' : 'asc'};
    draw();
    $(`#offers-table [data-key="${key}"]`)?.focus();
  },
};

export const changes = {
  'offers-filter'() {
    draw();
  },
};
