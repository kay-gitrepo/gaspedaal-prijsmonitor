/* Opstart, inloggen, router en gedelegeerde gebeurtenissen. Geen framework, geen build-stap. */
import {api, setCsrf} from './api.js';
import {esc} from './format.js';
import {PAGES, parseHash, replace} from './router.js';
import {$, $$, closeModalView, modalOpen, toast} from './ui.js';
import {onRefreshAccepted, startRefresh} from './refresh.js';
import * as overzicht from './pages/overzicht.js';
import * as aanbod from './pages/aanbod.js';
import * as auto from './pages/auto.js';
import * as wensen from './pages/wensen.js';
import * as zoekopdrachten from './pages/zoekopdrachten.js';
import * as controles from './pages/controles.js';
import * as aiAnalyse from './pages/ai-analyse.js';
import * as instellingen from './pages/instellingen.js';

const BASE = {overzicht, aanbod, wensen, zoekopdrachten, controles, 'ai-analyse': aiAnalyse, instellingen};
const DETAIL = {auto: auto.showCar, controles: controles.showRun, 'ai-analyse': aiAnalyse.showIntegration};
const LABELS = {
  overzicht: 'Marktoverzicht', aanbod: 'Autoaanbod', zoekopdrachten: 'Zoekprofielen', wensen: 'Optieprofiel',
  controles: 'Uitvoeringslog', 'ai-analyse': 'Gemini-integratie', instellingen: 'Home Assistant',
};
const MODULES = Object.values(BASE).concat([auto]);
const actions = Object.assign({}, ...MODULES.map(m => m.actions || {}));
const submits = Object.assign({}, ...MODULES.map(m => m.submits || {}));
const changes = Object.assign({}, ...MODULES.map(m => m.changes || {}));

let renderedBase = null;
let previous = null;
let detailFromBase = false;

async function renderBase(base) {
  renderedBase = base;
  $$('.nav-link').forEach(a => a.classList.toggle('active', a.dataset.nav === base));
  $('#crumb-active').textContent = LABELS[base];
  $('.sidebar').classList.remove('show');
  $('#content').innerHTML = '<div class="loading">Gegevens laden…</div>';
  try {
    await BASE[base].render();
  } catch (e) {
    $('#content').innerHTML = `<div class="notice warn">Laden mislukt: ${esc(e.message)}</div>`;
  }
}

async function route() {
  const r = parseHash();
  if (!PAGES.includes(r.page) || (r.page === 'auto' && !r.id)) {
    replace(r.page === 'auto' ? 'aanbod' : 'overzicht');
    return;
  }
  const detail = r.id ? DETAIL[r.page] : null;
  const base = r.page === 'auto' ? (renderedBase || 'aanbod') : r.page;
  detailFromBase = Boolean(detail && previous && !previous.id && previous.page === base);
  previous = r;
  if (base !== renderedBase || (!detail && !modalOpen())) await renderBase(base);
  if (!detail) {
    closeModalView();
    return;
  }
  try {
    await detail(r.id);
  } catch (e) {
    toast('Laden mislukt: ' + e.message);
  }
}

/** Sluit het detail via de route, zodat de terugknop en herladen hetzelfde doen. */
function closeDetail() {
  if (detailFromBase) {
    history.back();
  } else {
    replace(renderedBase || 'overzicht');
  }
}

async function showApp() {
  $('#login').classList.add('hidden');
  $('#shell').classList.remove('hidden');
  await route();
}

async function initialize() {
  const sess = await api('/session');
  if (!sess.authenticated) {
    $('#login').classList.remove('hidden');
    return;
  }
  setCsrf(sess.csrf);
  await showApp();
}

actions['refresh-all'] = () => startRefresh();

document.addEventListener('click', async e => {
  if (e.target.closest('[data-close]')) {
    closeDetail();
    return;
  }
  const el = e.target.closest('[data-action]');
  if (el && actions[el.dataset.action]) {
    e.preventDefault();
    try {
      await actions[el.dataset.action](el, e);
    } catch (err) {
      toast(err.message);
    }
    return;
  }
  const row = e.target.closest('tr[data-href]');
  if (row && !e.target.closest('a,button,input,select,summary')) location.hash = row.dataset.href;
});

document.addEventListener('submit', async e => {
  const form = e.target;
  if (form.id === 'login-form') {
    e.preventDefault();
    try {
      const r = await api('/login', {method: 'POST', body: {password: $('#password').value}});
      setCsrf(r.csrf);
      $('#login-error').textContent = '';
      await showApp();
    } catch (err) {
      $('#login-error').textContent = err.message;
    }
    return;
  }
  const handler = submits[form.dataset.submit];
  if (!handler) return;
  e.preventDefault();
  try {
    await handler(form);
  } catch (err) {
    toast(err.message);
  }
});

document.addEventListener('change', async e => {
  const handler = changes[e.target.dataset?.change];
  if (!handler) return;
  try {
    await handler(e.target);
  } catch (err) {
    toast(err.message);
  }
});

document.addEventListener('keydown', e => {
  if (e.key === 'Escape' && modalOpen()) closeDetail();
});

$('#modal-backdrop').addEventListener('click', e => {
  if (e.target.id === 'modal-backdrop') closeDetail();
});
$('#top-refresh').addEventListener('click', () => startRefresh());
$('#logout').addEventListener('click', async () => {
  try {
    await api('/logout', {method: 'POST'});
  } finally {
    location.reload();
  }
});
$('#menu-toggle').addEventListener('click', () => $('.sidebar').classList.toggle('show'));
window.addEventListener('hashchange', () => {
  if (!$('#shell').classList.contains('hidden')) route();
});
onRefreshAccepted(() => {
  if (['controles', 'overzicht'].includes(renderedBase) && !modalOpen()) renderBase(renderedBase);
});

initialize().catch(e => {
  $('#login').classList.remove('hidden');
  $('#login-error').textContent = 'Kan server niet bereiken: ' + e.message;
});
