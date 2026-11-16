/* Componentenbibliotheek. Functies die HTML teruggeven escapen zelf alle variabele tekst,
 * tenzij een parameter expliciet `html` heet (dan is het al veilig opgebouwde HTML). */
import {esc} from './format.js';

export const $ = (s, root = document) => root.querySelector(s);
export const $$ = (s, root = document) => [...root.querySelectorAll(s)];

/* ---------- Iconen ---------- */
export function icon(name, cls = '') {
  return `<svg class="icon ${cls}" aria-hidden="true" focusable="false"><use href="/static/icons.svg#${name}"/></svg>`;
}

/* ---------- Knoppen ---------- */
function attrs(map = {}) {
  return Object.entries(map)
    .filter(([, v]) => v !== undefined && v !== null && v !== false)
    .map(([k, v]) => (v === true ? ` ${k}` : ` ${k}="${esc(v)}"`)).join('');
}

/**
 * @param {string} text zichtbare tekst
 * @param {{variant?: string, size?: string, icon?: string, href?: string, action?: string,
 *   data?: object, attrs?: object, iconOnly?: boolean, type?: string}} opt
 */
export function button(text, opt = {}) {
  const cls = ['btn', opt.variant ? `btn-${opt.variant}` : '', opt.size === 's' ? 'btn-s' : '',
    opt.iconOnly ? 'btn-icon' : '', opt.cls || ''].filter(Boolean).join(' ');
  const data = Object.fromEntries(Object.entries(opt.data || {}).map(([k, v]) => [`data-${k}`, v]));
  if (opt.action) data['data-action'] = opt.action;
  const label = opt.iconOnly ? `<span class="sr-only">${esc(text)}</span>` : `<span class="btn-label">${esc(text)}</span>`;
  const inner = (opt.icon ? icon(opt.icon) : '') + label;
  const extra = {...data, ...(opt.attrs || {})};
  if (opt.iconOnly) extra.title = text;
  if (opt.href) return `<a class="${cls}" href="${esc(opt.href)}"${attrs(extra)}>${inner}</a>`;
  return `<button type="${opt.type || 'button'}" class="${cls}"${attrs(extra)}>${inner}</button>`;
}

/** Zet een knop in bezig-toestand; geeft een functie terug die de toestand opheft. */
export function busy(el) {
  if (!el) return () => {};
  el.classList.add('loading');
  el.setAttribute('aria-busy', 'true');
  el.disabled = true;
  return () => {
    el.classList.remove('loading');
    el.removeAttribute('aria-busy');
    el.disabled = false;
  };
}

/* ---------- Badges ---------- */
export function badge(text, variant = 'neutral', iconName = '') {
  return `<span class="badge badge-${variant}">${iconName ? icon(iconName) : ''}${esc(text)}</span>`;
}

/** Badge uit een woordenlijst-item [tekst, variant]. */
export function statusBadge(map, code, fallback = 'Onbekend') {
  const [text, variant] = map[code] || [fallback, 'neutral'];
  return badge(text, variant);
}

/* ---------- Paginakop, kaart, kerncijfer ---------- */
export function pageHead(title, description = '', actionsHtml = '') {
  return `<header class="page-head"><div><h1>${esc(title)}</h1>${description ? `<p>${esc(description)}</p>` : ''}</div>
    ${actionsHtml ? `<div class="actions">${actionsHtml}</div>` : ''}</header>`;
}

export function card(title, bodyHtml, {sub = '', actionsHtml = '', id = '', cls = ''} = {}) {
  const head = title || actionsHtml ? `<div class="card-head"><div><h3>${esc(title)}</h3>
    ${sub ? `<p>${esc(sub)}</p>` : ''}</div>${actionsHtml}</div>` : '';
  return `<section class="card ${cls}"${id ? ` id="${esc(id)}"` : ''}>${head}${bodyHtml}</section>`;
}

export function stat(labelText, valueHtml, note = '', iconName = '') {
  return `<div class="card stat"><div class="stat-label">${esc(labelText)}${iconName ? icon(iconName) : ''}</div>
    <div class="stat-value">${valueHtml}</div>${note ? `<div class="stat-note">${esc(note)}</div>` : ''}</div>`;
}

export function notice(html, variant = 'info') {
  const name = {info: 'info', warning: 'alert', danger: 'alert'}[variant] || 'info';
  return `<div class="notice notice-${variant}" role="${variant === 'danger' ? 'alert' : 'note'}">${icon(name)}
    <div>${html}</div></div>`;
}

/* ---------- Tabs en segmentkeuze ---------- */
export function tabs(items, active, label = 'Weergave') {
  const links = items.map(t => `<a class="tab" href="${esc(t.href)}"${t.key === active ? ' aria-current="page"' : ''}>
    ${esc(t.label)}${t.count !== undefined ? `<span class="count">${esc(t.count)}</span>` : ''}</a>`).join('');
  return `<nav class="tabs" aria-label="${esc(label)}">${links}</nav>`;
}

let segmentSeq = 0;

export function segment(name, options, value, {label = '', data = {}} = {}) {
  const group = `seg-${++segmentSeq}`;
  const dataAttrs = attrs(Object.fromEntries(Object.entries(data).map(([k, v]) => [`data-${k}`, v])));
  const inputs = options.map(([v, text], i) => `<input type="radio" id="${group}-${i}" name="${esc(name)}"
    value="${esc(v)}"${v === value ? ' checked' : ''}${dataAttrs}><label for="${group}-${i}">${esc(text)}</label>`);
  return `<div class="segment" role="radiogroup" aria-label="${esc(label)}">${inputs.join('')}</div>`;
}

/* ---------- Tabel ---------- */
/**
 * @param {{label: string, num?: boolean, sort?: string, main?: boolean, media?: boolean}[]} columns
 * @param {(string[]|{cells: string[], cls?: string})[]} rows celinhoud is veilige HTML
 * @param {{sort?: {key: string, dir: string}, empty?: string, caption?: string}} opt
 */
export function table(columns, rows, opt = {}) {
  const head = columns.map(c => {
    const cls = c.num ? ' class="num"' : '';
    if (!c.sort) return `<th scope="col"${cls}>${esc(c.label)}</th>`;
    const active = opt.sort && opt.sort.key === c.sort;
    const dir = active ? opt.sort.dir : null;
    const ariaSort = active ? ` aria-sort="${dir === 'asc' ? 'ascending' : 'descending'}"` : '';
    const ic = active ? (dir === 'asc' ? 'sort-up' : 'sort-down') : 'sort';
    return `<th scope="col"${cls}${ariaSort}><button type="button" class="sort-btn" data-action="sort"
      data-key="${esc(c.sort)}">${esc(c.label)}${icon(ic)}</button></th>`;
  }).join('');
  const body = rows.map(r => {
    const cells = Array.isArray(r) ? r : r.cells;
    const tds = cells.map((cell, i) => {
      const c = columns[i] || {};
      const cls = [c.num ? 'num' : '', c.main ? 'cell-main' : '', c.media ? 'cell-media' : ''].filter(Boolean).join(' ');
      return `<td data-label="${esc(c.label || '')}"${cls ? ` class="${cls}"` : ''}>${cell}</td>`;
    }).join('');
    return `<tr${r.cls ? ` class="${esc(r.cls)}"` : ''}>${tds}</tr>`;
  }).join('');
  const empty = `<tr><td colspan="${columns.length}" class="table-empty">${esc(opt.empty || 'Nog niets om te tonen.')}</td></tr>`;
  const caption = opt.caption ? `<caption class="sr-only">${esc(opt.caption)}</caption>` : '';
  return `<div class="table-wrap"><table class="responsive">${caption}<thead><tr>${head}</tr></thead>
    <tbody>${body || empty}</tbody></table></div>`;
}

/* ---------- Lege toestand, fout, skelet ---------- */
export function emptyState({iconName = 'info', title, text = '', actionHtml = ''}) {
  return `<div class="empty">${icon(iconName, 'icon-lg')}<h3>${esc(title)}</h3>${text ? `<p>${esc(text)}</p>` : ''}
    ${actionHtml}</div>`;
}

export function errorState(message) {
  return `<section class="card">${emptyState({iconName: 'alert', title: 'Dit scherm kon niet worden geladen',
    text: message || 'Er ging iets mis bij het ophalen van de gegevens.',
    actionHtml: button('Opnieuw proberen', {variant: 'primary', icon: 'refresh', action: 'retry'})})}</section>`;
}

export const skeletons = {
  stats: () => `<div class="stats">${'<div class="skeleton sk-stat"></div>'.repeat(4)}</div>`,
  head: () => '<div class="skeleton sk-title"></div><div class="skeleton sk-text"></div>',
  block: () => '<div class="skeleton sk-block"></div>',
  rows: (n = 6) => '<div class="card">' + '<div class="skeleton sk-row"></div>'.repeat(n) + '</div>',
  cards: (n = 3) => '<div class="skeleton sk-card"></div>'.repeat(n),
};

/* ---------- Formulierveld ---------- */
export function field({label, name, type = 'text', value = '', hint = '', error = '', id = '', attrs: extra = {}}) {
  const fid = id || `f-${name}`;
  const describedBy = [hint ? `${fid}-hint` : '', error ? `${fid}-error` : ''].filter(Boolean).join(' ');
  const common = `id="${esc(fid)}" name="${esc(name)}"${describedBy ? ` aria-describedby="${describedBy}"` : ''}`
    + `${error ? ' aria-invalid="true"' : ''}${attrs(extra)}`;
  const control = type === 'textarea' ? `<textarea ${common}>${esc(value)}</textarea>`
    : `<input type="${esc(type)}" ${common} value="${esc(value)}">`;
  return `<div class="field${error ? ' has-error' : ''}"><label for="${esc(fid)}">${esc(label)}</label>${control}
    ${hint ? `<span class="hint" id="${fid}-hint">${esc(hint)}</span>` : ''}
    <span class="error" id="${fid}-error"${error ? '' : ' hidden'}>${esc(error)}</span></div>`;
}

/** Toon een foutmelding onder een veld in een formulier. */
export function setFieldError(form, name, message) {
  const input = form.querySelector(`[name="${CSS.escape(name)}"]`);
  if (!input) return;
  const wrap = input.closest('.field');
  const el = wrap?.querySelector('.error');
  wrap?.classList.toggle('has-error', Boolean(message));
  input.toggleAttribute('aria-invalid', Boolean(message));
  if (el) {
    el.textContent = message || '';
    el.hidden = !message;
  }
  if (message) input.focus();
}

/* ---------- Meldingen ---------- */
export function toast(message, variant = 'success') {
  const host = $('#toasts');
  const el = document.createElement('div');
  el.className = `toast toast-${variant}`;
  el.setAttribute('role', variant === 'error' ? 'alert' : 'status');
  el.innerHTML = `${icon(variant === 'error' ? 'x-circle' : variant === 'info' ? 'info' : 'check-circle')}
    <div>${esc(message)}</div><button type="button" aria-label="Melding sluiten">${icon('x', 'icon-sm')}</button>`;
  el.querySelector('button').addEventListener('click', () => el.remove());
  host.append(el);
  setTimeout(() => el.remove(), variant === 'error' ? 8000 : 5000);
}

/* ---------- Dialoog (<dialog>: focus blijft binnen, Escape sluit, achtergrond scrolt niet) ---------- */
export function openDialog(html, labelledBy = 'dialog-title', {keepScroll = false} = {}) {
  const d = $('#dialog');
  const scroll = d.scrollTop;
  d.innerHTML = `<div class="dialog-body">${html}</div>`;
  d.setAttribute('aria-labelledby', labelledBy);
  if (!d.open) d.showModal();
  document.body.classList.add('no-scroll');
  d.scrollTop = keepScroll ? scroll : 0;
}

export function closeDialogView() {
  const d = $('#dialog');
  if (d.open) d.close();
  d.innerHTML = '';
  document.body.classList.remove('no-scroll');
}

export function dialogOpen() {
  return $('#dialog').open;
}

export function dialogHead(title, sub = '') {
  return `<div class="dialog-head"><div><h2 id="dialog-title">${esc(title)}</h2>${sub ? `<p>${esc(sub)}</p>` : ''}</div>
    ${button('Sluiten', {iconOnly: true, icon: 'x', attrs: {'data-close': true}})}</div>`;
}

/* ---------- Balk ---------- */
/** Horizontale balk zonder inline style: SVG met procentuele breedtes. */
export function bar(parts, label = '') {
  let x = 0;
  const rects = parts.map(([value, cls]) => {
    const w = Math.max(0, Math.min(100 - x, Number(value) || 0));
    const r = `<rect class="${cls}" x="${x}" y="0" width="${w}" height="6" rx="3"/>`;
    x += w;
    return r;
  }).join('');
  return `<svg class="bar" viewBox="0 0 100 6" preserveAspectRatio="none" role="img" aria-label="${esc(label)}">
    <rect class="track" x="0" y="0" width="100" height="6" rx="3"/>${rects}</svg>`;
}

/* ---------- Schakelaar en menu ---------- */
export function toggle(text, checked, opt = {}) {
  const data = Object.fromEntries(Object.entries(opt.data || {}).map(([k, v]) => [`data-${k}`, v]));
  if (opt.action) data['data-action'] = opt.action;
  return `<button type="button" class="switch" role="switch" aria-checked="${checked ? 'true' : 'false'}"${attrs(data)}>
    <span class="switch-track" aria-hidden="true"></span><span>${esc(text)}</span></button>`;
}

/** Uitklapmenu met knoppen; items: [{text, icon, action, data, variant, href}].
 * Zonder `text` is de knop alleen een icoon (drie puntjes). */
export function menu(label, items, {text = '', icon: iconName = 'more'} = {}) {
  const list = items.map(i => button(i.text, {...i, variant: i.variant || 'text', cls: 'menu-item'})).join('');
  const summary = text ? `<summary class="btn btn-s">${icon(iconName)}${esc(text)}${icon('chevron-down', 'icon-sm')}</summary>`
    : `<summary class="btn btn-s btn-icon" title="${esc(label)}">${icon(iconName)}
    <span class="sr-only">${esc(label)}</span></summary>`;
  return `<details class="menu">${summary}<div class="menu-list">${list}</div></details>`;
}
