/* Mijn wensen: must-haves en nice-to-haves, automatisch opslaan, direct herrekende telling. */
import {api} from '../api.js';
import {esc, fmt} from '../format.js';
import {$, $$, button, closeDialogView, dialogHead, field, icon, menu, notice, openDialog, pageHead, segment,
  skeletons, toast} from '../ui.js';
import {allProfiles, profileId} from '../context.js';
import {follow} from '../refresh.js';
import {hasText} from '../status.js';

let criteria = [];
let profile = null;
const open = new Set();
const q = () => `profile_id=${encodeURIComponent(profile)}`;
const GROUPS = [['MUST_HAVE', 'Must-haves', 'Ontbreekt er één aantoonbaar, dan valt de auto af.'],
  ['NICE_TO_HAVE', 'Nice-to-haves', 'Leveren extra punten op in de match.']];
const EMPTY_COLUMN = '<p class="muted">Sleep een wens hierheen, of kies “Verplaats naar” in het menu van een wens.</p>';
const WEIGHTS = [1, 2, 3, 4, 5].map(w => [String(w), String(w)]);

export function skeleton() {
  return skeletons.head() + '<div class="grid grid-2-even">' + skeletons.block() + skeletons.block() + '</div>';
}

function chips(c, list, labelText, hint) {
  const items = (c[list] || []).map(v => `<span class="chip">${esc(v)}<button type="button" data-action="remove-chip"
    data-key="${esc(c.key)}" data-list="${list}" data-value="${esc(v)}" aria-label="${esc(v)} verwijderen">
    ${icon('x', 'icon-sm')}</button></span>`).join('');
  const id = `add-${list}-${c.key}`;
  return `<div class="field"><span class="label">${esc(labelText)}</span><div class="chips">${items
    || '<span class="muted small">Nog geen</span>'}</div>
    <label class="sr-only" for="${esc(id)}">${esc(labelText)} toevoegen</label>
    <input class="input" id="${esc(id)}" data-keydown="add-chip" data-key="${esc(c.key)}" data-list="${list}"
      placeholder="Typ en druk op Enter"><span class="hint">${esc(hint)}</span></div>`;
}

function wishCard(c) {
  const other = c.group_name === 'MUST_HAVE' ? ['NICE_TO_HAVE', 'nice-to-have'] : ['MUST_HAVE', 'must-have'];
  const items = [
    {text: `Verplaats naar ${other[1]}`, icon: 'chevron-right', action: 'move-wish', data: {key: c.key, group: other[0]}},
    {text: 'Verwijderen', icon: 'trash', action: 'delete-wish', data: {key: c.key}, variant: 'danger'},
  ];
  return `<article class="wish" draggable="true" data-wish="${esc(c.key)}" aria-label="${esc(c.label)}">
    <div class="row-between"><div class="row">${icon('menu', 'drag-handle')}<strong>${esc(c.label)}</strong></div>
      ${menu(`Acties voor ${c.label}`, items)}</div>
    <div class="wish-weight"><span class="small muted">Belang</span>
      ${segment(`weight-${c.key}`, WEIGHTS, String(c.weight), {label: `Belang van ${c.label}`,
        data: {change: 'wish-weight', key: c.key}})}</div>
    <details class="disclosure" data-wish-details="${esc(c.key)}"${open.has(c.key) ? ' open' : ''}>
      <summary>${icon('chevron-down')}Omschrijving en zoekwoorden</summary><div class="stack">
      ${field({label: 'Omschrijving', name: 'description', type: 'textarea', id: `desc-${c.key}`, value: c.description,
        hint: 'Wat telt als aanwezig? Bijvoorbeeld: niet alleen voorbereiding.',
        attrs: {'data-change': 'wish-description', 'data-key': c.key, maxlength: 350, rows: 2}})}
      ${chips(c, 'synonyms', 'Zoekwoorden', 'Hoe advertenties dit noemen (NL, EN, DE). Helpt de AI en de volgorde.')}
      ${chips(c, 'match_terms', 'Zeker herkennen zonder AI',
        'Alleen woorden die ondubbelzinnig deze optie betekenen; "geen …" en "tegen meerprijs" worden herkend.')}
    </div></details></article>`;
}

function board() {
  return GROUPS.map(([group, title, text]) => {
    const list = criteria.filter(c => c.group_name === group).sort((a, b) => b.weight - a.weight);
    return `<section class="card wish-column" data-drop-group="${group}" aria-labelledby="col-${group}">
      <div class="card-head"><div><h3 id="col-${group}">${title}</h3><p>${text}</p></div>
      <span class="badge badge-neutral">${fmt(list.length)}</span></div>
      <div class="stack">${list.map(wishCard).join('') || EMPTY_COLUMN}</div></section>`;
  }).join('');
}

async function updateCounts() {
  const el = $('#wish-counts');
  if (!el) return;
  const items = (await api('/listings?' + q())).items.filter(x => x.availability === 'ACTIVE');
  const count = f => items.filter(f).length;
  const noText = count(x => !hasText(x) && x.eligibility === 'UNVERIFIED');
  const parts = [`<strong>${fmt(count(x => x.eligibility === 'MATCH'))}</strong> voldoen`,
    `<strong>${fmt(count(x => ['UNVERIFIED', 'REVIEW'].includes(x.eligibility)) - noText)}</strong> nog te controleren`,
    `<strong>${fmt(count(x => x.eligibility === 'REJECTED'))}</strong> vallen af`];
  if (noText) parts.push(`<strong>${fmt(noText)}</strong> zonder advertentietekst`);
  el.innerHTML = `Met deze wensen: ${parts.join(' · ')} <span class="muted">(van ${fmt(items.length)} te koop)</span>`;
}

function drawBoard() {
  $$('[data-wish-details]').forEach(d => (d.open ? open.add(d.dataset.wishDetails) : open.delete(d.dataset.wishDetails)));
  $('#wish-board').innerHTML = board();
}

function profilePicker(profiles) {
  const options = profiles.map(p => `<option value="${esc(p.id)}"${p.id === profile ? ' selected' : ''}>${esc(p.title)}
    </option>`).join('');
  const copy = profiles.length > 1 ? button('Wensen kopiëren van …', {icon: 'copy', action: 'copy-wishes'}) : '';
  return `<div class="wish-profile"><div class="field"><label for="wish-profile">Wensen voor zoekopdracht</label>
    <select id="wish-profile" class="input" data-change="wish-profile">${options}</select></div>${copy}</div>`;
}

export async function render(params = new URLSearchParams()) {
  const profiles = allProfiles();
  if (!profiles.length) {
    $('#content').innerHTML = pageHead('Mijn wensen') + `<section class="card">${'<p class="muted">Voeg eerst een '
      + 'zoekopdracht toe; wensen horen bij een zoekopdracht.</p>'}${button('Naar zoekopdrachten',
      {href: '#/zoekopdrachten', variant: 'primary'})}</section>`;
    return;
  }
  const wanted = params.get('zoekopdracht') || profileId();
  profile = profiles.some(p => p.id === wanted) ? wanted : profiles[0].id;
  criteria = (await api('/criteria?' + q())).items;
  try {
    localStorage.setItem('occasioniq.wensen-bekeken', '1');
  } catch {
    /* opslag niet beschikbaar */
  }
  $('#content').innerHTML = pageHead('Mijn wensen', 'Welke uitrusting moet de auto hebben, en wat is mooi meegenomen?',
    button('Wens toevoegen', {variant: 'primary', icon: 'plus', action: 'add-wish'}))
    + profilePicker(profiles) + notice('Staat een optie niet in de advertentie, dan geldt die als onbekend, niet als afwezig.')
    + `<p class="wish-counts" id="wish-counts" aria-live="polite">&nbsp;</p>
    <div class="grid grid-2-even" id="wish-board">${board()}</div>
    <p class="muted small">Wijzigingen worden direct opgeslagen. De match telt must-haves voor 70% en nice-to-haves voor
    30%. Belang en indeling herrekenen de scores meteen; een andere omschrijving of andere zoekwoorden worden bij de
    volgende controle opnieuw beoordeeld.</p>`;
  await updateCounts();
}

const find = key => criteria.find(c => c.key === key);

async function save(c, message = 'Opgeslagen') {
  const body = {label: c.label, group_name: c.group_name, weight: Number(c.weight), description: c.description,
    synonyms: c.synonyms, match_terms: c.match_terms, enabled: true};
  const r = await api(`/criteria/${encodeURIComponent(c.key)}?${q()}`, {method: 'PUT', body});
  toast(r.reassess ? `${message}. Wordt bij de volgende controle opnieuw beoordeeld.` : message);
  await updateCounts();
}

async function move(key, group) {
  const c = find(key);
  if (!c || c.group_name === group) return;
  c.group_name = group;
  drawBoard();
  await save(c, group === 'MUST_HAVE' ? `${c.label} is nu een must-have` : `${c.label} is nu een nice-to-have`);
  $(`[data-wish="${CSS.escape(key)}"] summary`)?.focus();
}

/* ---------- Wens toevoegen ---------- */
function addDialog() {
  openDialog(dialogHead('Wens toevoegen', 'Typ de naam van de optie; je krijgt een voorstel voor omschrijving en zoekwoorden.')
    + `<section class="card"><form data-submit="suggest-wish" class="stack" novalidate>
      ${field({label: 'Naam van de wens', name: 'label', attrs: {required: true, minlength: 2, maxlength: 90,
        placeholder: 'Bijvoorbeeld: Elektrische achterklep'}})}
      <div>${button('Voorstel maken', {type: 'submit', variant: 'primary', icon: 'sparkles'})}</div></form>
      <div id="wish-draft"></div></section>`);
  $('#dialog [name=label]')?.focus();
}

let draft = null;

/** Neem de keuzes uit het conceptformulier over voordat het opnieuw wordt getekend. */
function syncDraft() {
  const form = $('#wish-draft form');
  if (!form || !draft) return;
  const d = new FormData(form);
  draft.group_name = d.get('group_name') || draft.group_name;
  draft.weight = Number(d.get('weight') || draft.weight);
  draft.description = d.get('description') ?? draft.description;
}

function drawDraft(s) {
  const letOp = s.let_op?.length ? notice('<strong>Let op:</strong> ' + s.let_op.map(esc).join(' · '), 'warning') : '';
  const info = s.ai_beschikbaar === false ? notice('Zonder AI kun je zelf zoekwoorden toevoegen.')
    : s.fout ? notice(esc(s.fout), 'warning') : '';
  $('#wish-draft').innerHTML = `<form data-submit="create-wish" class="stack">${info}${letOp}
    <div class="field"><span class="label">Soort wens</span>${segment('group_name',
      [['MUST_HAVE', 'Must-have'], ['NICE_TO_HAVE', 'Nice-to-have']], draft.group_name, {label: 'Soort wens'})}</div>
    <div class="field"><span class="label">Belang</span>${segment('weight', WEIGHTS, String(draft.weight), {label: 'Belang'})}</div>
    ${field({label: 'Omschrijving', name: 'description', type: 'textarea', value: draft.description,
      attrs: {maxlength: 350, rows: 2}})}
    ${chips(draft, 'synonyms', 'Zoekwoorden', 'Hoe advertenties dit noemen (NL, EN, DE).')}
    ${chips(draft, 'match_terms', 'Zeker herkennen zonder AI', 'Alleen ondubbelzinnige woorden.')}
    <div class="row">${button('Wens opslaan', {type: 'submit', variant: 'primary'})}
      ${button('Annuleren', {attrs: {'data-close': true}})}</div></form>`;
}

function copyDialog() {
  const others = allProfiles().filter(p => p.id !== profile);
  const current = allProfiles().find(p => p.id === profile);
  const options = others.map(p => `<option value="${esc(p.id)}">${esc(p.title)}</option>`).join('');
  openDialog(dialogHead('Wensen kopiëren', `Naar: ${current?.title || ''}`) + `<section class="card">
    <form data-submit="copy-wishes" class="stack"><div class="field"><label for="copy-from">Kopiëren van</label>
      <select id="copy-from" name="from" class="input">${options}</select></div>
      ${notice('De wensen van deze zoekopdracht worden vervangen door die van de gekozen zoekopdracht. Wensen die daar '
        + 'niet in staan worden uitgezet; je eigen correcties blijven bewaard. Daarna worden de auto\'s opnieuw '
        + 'beoordeeld.', 'warning')}
      <div class="row">${button('Kopiëren', {type: 'submit', variant: 'primary', icon: 'copy'})}
        ${button('Annuleren', {attrs: {'data-close': true}})}</div></form></section>`);
}

export const actions = {
  'copy-wishes'() {
    copyDialog();
  },
  'add-wish'() {
    draft = null;
    addDialog();
  },
  async 'move-wish'(el) {
    el.closest('details.menu')?.removeAttribute('open');
    await move(el.dataset.key, el.dataset.group);
  },
  'delete-wish'(el) {
    el.closest('details.menu')?.removeAttribute('open');
    const c = find(el.dataset.key);
    openDialog(dialogHead('Wens verwijderen?', c.label) + `<section class="card stack"><p>De wens telt niet meer mee in de
      match. Beoordelingen en je eigen correcties blijven bewaard.</p><div class="row">
      ${button('Verwijderen', {variant: 'danger', icon: 'trash', action: 'confirm-delete-wish', data: {key: c.key}})}
      ${button('Annuleren', {attrs: {'data-close': true}})}</div></section>`);
  },
  async 'confirm-delete-wish'(el) {
    await api(`/criteria/${encodeURIComponent(el.dataset.key)}?${q()}`, {method: 'DELETE'});
    closeDialogView();
    toast('Wens verwijderd');
    await render(new URLSearchParams({zoekopdracht: profile}));
  },
  async 'remove-chip'(el) {
    const target = draft && $('#dialog')?.contains(el) ? draft : find(el.dataset.key);
    target[el.dataset.list] = target[el.dataset.list].filter(v => v !== el.dataset.value);
    if (target === draft) {
      syncDraft();
      drawDraft(draft.suggestion);
      return;
    }
    drawBoard();
    await save(target);
  },
};

export const keydowns = {
  async 'add-chip'(el, e) {
    if (e.key !== 'Enter') return;
    e.preventDefault();
    const value = el.value.trim().replace(/\s+/g, ' ');
    if (!value) return;
    const target = draft && $('#dialog')?.contains(el) ? draft : find(el.dataset.key);
    const list = el.dataset.list;
    if (!target[list].some(v => v.toLowerCase() === value.toLowerCase())) target[list] = [...target[list], value];
    if (target === draft) {
      syncDraft();
      drawDraft(draft.suggestion);
      $(`#dialog [data-list="${list}"][data-keydown]`)?.focus();
      return;
    }
    drawBoard();
    $(`#add-${list}-${CSS.escape(target.key)}`)?.focus();
    await save(target);
  },
};

export const changes = {
  'wish-profile'(el) {
    location.hash = `#/wensen?zoekopdracht=${encodeURIComponent(el.value)}`;
  },
  async 'wish-weight'(el) {
    const c = find(el.dataset.key);
    c.weight = Number(el.value);
    await save(c, `Belang van ${c.label}: ${c.weight}`);
  },
  async 'wish-description'(el) {
    const c = find(el.dataset.key);
    c.description = el.value.trim();
    await save(c);
  },
};

export const submits = {
  async 'copy-wishes'(form) {
    const from = new FormData(form).get('from');
    const r = await api('/criteria/copy', {method: 'POST', body: {from_profile_id: from, to_profile_id: profile}});
    closeDialogView();
    toast(`${r.copied} wensen gekopieerd`);
    await render(new URLSearchParams({zoekopdracht: profile}));
    if (r.run_id) await follow(r.run_id);
  },
  async 'suggest-wish'(form) {
    const label = new FormData(form).get('label').trim();
    if (label.length < 2) return;
    const s = await api('/criteria/suggest', {method: 'POST', body: {label}});
    const fallback = s.ai_beschikbaar === false || s.fout;
    draft = {key: '', label, group_name: 'NICE_TO_HAVE', weight: 3, description: s.description || '',
      synonyms: s.synonyms?.length ? s.synonyms : (fallback ? [label.toLowerCase()] : []),
      match_terms: s.match_terms || [], suggestion: s};
    drawDraft(s);
  },
  async 'create-wish'(form) {
    const d = Object.fromEntries(new FormData(form));
    const body = {profile_id: profile, label: draft.label, group_name: d.group_name, weight: Number(d.weight),
      description: d.description || '',
      synonyms: draft.synonyms, match_terms: draft.match_terms};
    await api('/criteria', {method: 'POST', body});
    closeDialogView();
    toast(`Wens "${draft.label}" toegevoegd`);
    draft = null;
    await render(new URLSearchParams({zoekopdracht: profile}));
  },
};

/* ---------- Slepen tussen de kolommen ---------- */
document.addEventListener('dragstart', e => {
  const w = e.target.closest?.('[data-wish]');
  if (!w) return;
  e.dataTransfer.setData('text/plain', w.dataset.wish);
  e.dataTransfer.effectAllowed = 'move';
  w.classList.add('dragging');
});
document.addEventListener('dragend', e => e.target.closest?.('[data-wish]')?.classList.remove('dragging'));
document.addEventListener('dragover', e => {
  const col = e.target.closest?.('[data-drop-group]');
  if (!col) return;
  e.preventDefault();
  $$('[data-drop-group]').forEach(c => c.classList.toggle('drop-target', c === col));
});
document.addEventListener('drop', async e => {
  const col = e.target.closest?.('[data-drop-group]');
  $$('[data-drop-group]').forEach(c => c.classList.remove('drop-target'));
  if (!col) return;
  e.preventDefault();
  try {
    await move(e.dataTransfer.getData('text/plain'), col.dataset.dropGroup);
  } catch (err) {
    toast(err.message, 'error');
  }
});
