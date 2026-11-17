/* Shortlist (#/shortlist): alle bewaarde auto's, ook verdwenen; tot vier naast elkaar vergelijken.
 * De keuze staat in het adres (#/shortlist?vergelijk=id1,id2). */
import {api} from '../api.js';
import {esc, euro, fmt} from '../format.js';
import {AVAILABILITY, CLAIM, GROUP, label} from '../labels.js';
import {$, button, card, emptyState, icon, notice, pageHead, skeletons, statusBadge} from '../ui.js';
import {profileId} from '../context.js';
import {matchCell, statusChip} from '../status.js';
import {marketCell} from '../negotiation.js';
import {inView, priceChange} from './aanbod.js';

const MAX = 4;
let items = [];
let chosen = [];

export function skeleton() {
  return skeletons.head() + skeletons.rows(4) + skeletons.block();
}

function thumb(x, cls = 'thumb') {
  if (!x.photo) return `<div class="${cls} thumb-empty">${icon('image')}</div>`;
  return `<img class="${cls}" loading="lazy" referrerpolicy="no-referrer" src="${esc(x.photo)}" alt="">`;
}

function pick(x) {
  const on = chosen.includes(x.id);
  const full = !on && chosen.length >= MAX;
  return `<label class="check pick"><input type="checkbox" data-change="compare" data-id="${esc(x.id)}"
    ${on ? 'checked' : ''}${full ? ' disabled' : ''}> Vergelijken</label>`;
}

function listItem(x) {
  const chips = [statusChip(x)];
  if (x.availability !== 'ACTIVE') chips.push(statusBadge(AVAILABILITY, x.availability));
  return `<article class="short-item${chosen.includes(x.id) ? ' chosen' : ''}">${thumb(x)}
    <div class="short-main"><a class="title-link" href="#/auto/${encodeURIComponent(x.id)}">${esc(x.title)}</a>
      <span class="sub">${esc([x.year, x.kilometers != null ? `${fmt(x.kilometers)} km` : null].filter(Boolean)
        .join(' · '))}</span><div class="row">${chips.join('')}</div></div>
    <div class="short-price"><strong>${euro(x.price_eur)}</strong>${priceChange(x)}<div class="small">${marketCell(x)}</div>
    </div><div class="short-pick">${pick(x)}</div></article>`;
}

/** Klein prijsverloop (trap) voor de vergelijking. */
function sparkline(history) {
  const pts = history.map(h => h.price_eur);
  if (pts.length < 2 || Math.min(...pts) === Math.max(...pts)) {
    return `<span class="muted small">${pts.length ? 'onveranderd' : 'geen metingen'}</span>`;
  }
  const w = 140;
  const h = 36;
  const lo = Math.min(...pts);
  const hi = Math.max(...pts);
  const y = v => (h - 3 - (v - lo) / (hi - lo) * (h - 6)).toFixed(1);
  let d = `M 0 ${y(pts[0])}`;
  pts.forEach((v, i) => {
    if (i) d += ` H ${(i / (pts.length - 1) * w).toFixed(1)} V ${y(v)}`;
  });
  const text = `Van ${euro(pts[0])} naar ${euro(pts.at(-1))}`;
  return `<svg class="sparkline step" viewBox="0 0 ${w} ${h}" role="img" aria-label="${esc(text)}"><path d="${d}"/></svg>`;
}

function comparison(cars) {
  const head = cars.map(c => `<th scope="col">${thumb(c.list, 'compare-photo')}
    <a class="title-link" href="#/auto/${encodeURIComponent(c.id)}">${esc(c.detail.title)}</a>
    <button type="button" class="btn btn-text btn-s" data-action="uncompare" data-id="${esc(c.id)}">${icon('x', 'icon-sm')}
      Uit vergelijking</button></th>`).join('');
  const row = (title, cell) => `<tr><th scope="row">${title}</th>${cars.map(c => `<td>${cell(c)}</td>`).join('')}</tr>`;
  const wishes = [];
  for (const c of cars) {
    for (const w of c.detail.claims || []) {
      if (!wishes.some(x => x.key === w.criterion_key)) {
        wishes.push({key: w.criterion_key, label: w.label, group: w.group_name, weight: w.weight});
      }
    }
  }
  wishes.sort((a, b) => (a.group === b.group ? b.weight - a.weight : a.group === 'MUST_HAVE' ? -1 : 1));
  const claimOf = (c, key) => (c.detail.claims || []).find(w => w.criterion_key === key);
  const rows = [
    row('Vraagprijs', c => `<strong>${euro(c.detail.price_eur)}</strong>${priceChange(c.detail)}`),
    row('Prijsverloop', c => sparkline(c.detail.history || [])),
    row('Kilometerstand', c => (c.detail.kilometers != null ? `${fmt(c.detail.kilometers)} km` : 'onbekend')),
    row('Bouwjaar', c => esc(c.detail.year || 'onbekend')),
    row('T.o.v. markt', c => marketCell(c.list)),
    row('Match', c => matchCell(c.detail)),
    row('Status', c => `<div class="row">${statusChip(c.detail)}${c.detail.availability !== 'ACTIVE'
      ? statusBadge(AVAILABILITY, c.detail.availability) : ''}</div>`),
    row('In beeld', c => inView(c.detail)),
    `<tr class="group-row"><th scope="rowgroup" colspan="${cars.length + 1}">Wensen</th></tr>`,
    ...wishes.map(w => row(`${esc(w.label)}<span class="sub">${esc(label(GROUP, w.group))}</span>`, c => {
      const claim = claimOf(c, w.key);
      return claim ? statusBadge(CLAIM, claim.status) : '<span class="muted small">geen wens hier</span>';
    })),
  ];
  const profiles = [...new Set(cars.map(c => c.detail.score_profile_title).filter(Boolean))];
  const note = profiles.length > 1 ? notice(`Deze auto's zijn beoordeeld volgens de wensen van verschillende
    zoekopdrachten (${profiles.map(esc).join(', ')}).`, 'info') : '';
  return `${note}<div class="compare-wrap"><table class="compare"><thead><tr><th scope="col"><span class="sr-only">Kenmerk
    </span></th>${head}</tr></thead><tbody>${rows.join('')}</tbody></table></div>
    <p class="muted small">Vraagprijzen, geen verkoopprijzen. "T.o.v. markt" is een schatting op basis van vergelijkbare
    auto's.</p>`;
}

async function drawComparison() {
  const el = $('#compare');
  if (!el) return;
  if (chosen.length < 2) {
    el.innerHTML = `<p class="muted">Vink twee tot vier auto's aan om ze naast elkaar te zien.</p>`;
    return;
  }
  const q = profileId() ? `?profile_id=${encodeURIComponent(profileId())}` : '';
  const details = await Promise.all(chosen.map(id => api(`/listings/${encodeURIComponent(id)}${q}`)));
  const cars = chosen.map((id, i) => ({id, detail: details[i], list: items.find(x => x.id === id) || details[i]}));
  el.innerHTML = comparison(cars);
}

function drawList() {
  $('#short-list').innerHTML = items.map(listItem).join('');
  $('#compare-count').textContent = `${fmt(chosen.length)} van maximaal ${MAX} gekozen`;
}

function sync() {
  const hash = chosen.length ? `#/shortlist?vergelijk=${chosen.map(encodeURIComponent).join(',')}` : '#/shortlist';
  history.replaceState(null, '', hash);
  window.dispatchEvent(new CustomEvent('occasioniq:query'));
}

export async function render(params = new URLSearchParams()) {
  items = (await api('/listings')).items.filter(x => x.favorite)
    .sort((a, b) => (a.availability !== 'ACTIVE') - (b.availability !== 'ACTIVE') || a.price_eur - b.price_eur);
  const wanted = (params.get('vergelijk') || '').split(',').filter(Boolean);
  chosen = wanted.filter(id => items.some(x => x.id === id)).slice(0, MAX);
  if (!items.length) {
    $('#content').innerHTML = pageHead('Shortlist') + card('', emptyState({iconName: 'star', title: 'Nog niets bewaard',
      text: 'Zet auto\'s op je shortlist met de ster in het aanbod of op de pagina van een auto.',
      actionHtml: button('Naar het aanbod', {variant: 'primary', href: '#/aanbod'})}));
    return;
  }
  const gone = items.filter(x => x.availability !== 'ACTIVE').length;
  $('#content').innerHTML = pageHead('Shortlist', `Je bewaarde auto's${gone ? `, waarvan ${fmt(gone)} niet meer te koop`
    : ''}. Vink er tot vier aan om ze te vergelijken.`)
    + card('Bewaarde auto\'s', `<div class="short-list" id="short-list"></div>`,
      {sub: `${fmt(items.length)} auto's`, actionsHtml: `<span class="badge badge-neutral" id="compare-count"></span>`})
    + card('Vergelijking', '<div id="compare"></div>', {id: 'vergelijking'});
  drawList();
  await drawComparison();
}

export const changes = {
  async compare(el) {
    if (el.checked && !chosen.includes(el.dataset.id)) chosen.push(el.dataset.id);
    if (!el.checked) chosen = chosen.filter(id => id !== el.dataset.id);
    chosen = chosen.slice(0, MAX);
    sync();
    drawList();
    $(`[data-change="compare"][data-id="${CSS.escape(el.dataset.id)}"]`)?.focus();
    await drawComparison();
  },
};

export const actions = {
  async uncompare(el) {
    chosen = chosen.filter(id => id !== el.dataset.id);
    sync();
    drawList();
    await drawComparison();
  },
};

