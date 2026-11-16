/* Herbruikbare UI-bouwstenen. Functies die HTML teruggeven escapen zelf alle variabele tekst. */
import {esc} from './format.js';

export const $ = (s, root = document) => root.querySelector(s);
export const $$ = (s, root = document) => [...root.querySelectorAll(s)];

export function tag(text, type) {
  return `<span class="pill ${type}">${esc(text)}</span>`;
}

const ELIGIBILITY = {
  MATCH: ['Alle must-haves ✓', 'green'],
  REJECTED: ['Must-have ontbreekt', 'red'],
  UNVERIFIED: ['Nog onzeker', 'amber'],
  REVIEW: ['Controle nodig', 'amber'],
};

export function eligibility(status) {
  const [text, type] = ELIGIBILITY[status] || [status, 'grey'];
  return tag(text, type);
}

const STATUS = {
  COMPLETE: ['Geslaagd', 'green'], PARTIAL: ['Gedeeltelijk', 'amber'], FAILED: ['Mislukt', 'red'],
  RUNNING: ['Bezig', 'amber'], QUEUED: ['In wachtrij', 'grey'], SUCCESS: ['Gemini OK', 'green'],
  ERROR: ['Gemini fout', 'red'], CACHE_HIT: ['Cachehit', 'grey'], LOCAL_ONLY: ['Lokaal', 'grey'],
  SKIPPED_NO_KEY: ['Gemini uit', 'amber'], SKIPPED_BUDGET: ['Budgetlimiet', 'amber'],
};

export function statusTag(s) {
  const [text, type] = STATUS[s] || [s || '—', 'grey'];
  return tag(text, type);
}

export function head(kicker, title, description, actions = '') {
  return `<div class="page-heading"><div><p class="eyebrow">${kicker}</p><h1>${title}</h1>
    <p class="subtitle">${description}</p></div><div class="inline-actions">${actions}</div></div>`;
}

export function table(headers, rows) {
  const body = rows.join('') || `<tr><td colspan="${headers.length}" class="muted">Nog geen resultaten</td></tr>`;
  return `<div class="table-wrap"><table><thead><tr>${headers.map(t => `<th>${t}</th>`).join('')}</tr></thead>
    <tbody>${body}</tbody></table></div>`;
}

let toastTimer = null;

export function toast(message) {
  const el = $('#toast');
  el.textContent = message;
  el.classList.remove('hidden');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.add('hidden'), 4800);
}

export function modal(html) {
  $('#modal').innerHTML = html;
  $('#modal-backdrop').classList.remove('hidden');
}

export function closeModalView() {
  $('#modal-backdrop').classList.add('hidden');
  $('#modal').innerHTML = '';
}

export function modalOpen() {
  return !$('#modal-backdrop').classList.contains('hidden');
}

export function modalHead(title, sub = '') {
  return `<div class="modal-head"><div><h2>${esc(title)}</h2><p class="subtitle">${esc(sub)}</p></div>
    <button class="modal-close" data-close aria-label="Sluiten">×</button></div>`;
}
