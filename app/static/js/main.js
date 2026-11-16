/* Opstart, inloggen, router en gedelegeerde gebeurtenissen. Geen framework, geen build-stap. */
import {api, setCsrf} from './api.js';
import {PAGES, parseHash, replace, setLastList} from './router.js';
import {$, $$, closeDialogView, dialogOpen, errorState, skeletons, toast} from './ui.js';
import {startRefresh, onRefreshFinished} from './refresh.js';
import {onProfileChange, refreshProfiles, selectProfile} from './context.js';
import * as overzicht from './pages/overzicht.js';
import * as aanbod from './pages/aanbod.js';
import * as auto from './pages/auto.js';
import * as wensen from './pages/wensen.js';
import * as zoekopdrachten from './pages/zoekopdrachten.js';
import * as controles from './pages/controles.js';
import * as aiAnalyse from './pages/ai-analyse.js';
import * as instellingen from './pages/instellingen.js';

const BASE = {overzicht, aanbod, auto, wensen, zoekopdrachten, controles, 'ai-analyse': aiAnalyse, instellingen};
/* Detailvensters op beheerschermen; de auto heeft een eigen pagina. */
const DETAIL = {controles: controles.showRun, 'ai-analyse': aiAnalyse.showIntegration};
const TITLES = {
  overzicht: 'Overzicht', aanbod: 'Aanbod', auto: 'Auto', wensen: 'Mijn wensen', zoekopdrachten: 'Zoekopdrachten',
  controles: 'Controles', 'ai-analyse': 'AI-beoordeling', instellingen: 'Instellingen',
};
const MODULES = Object.values(BASE);
const merged = kind => Object.assign({}, ...MODULES.map(m => m[kind] || {}));
const actions = merged('actions');
const submits = merged('submits');
const changes = merged('changes');
const inputs = merged('inputs');
const keydowns = merged('keydowns');

let renderedBase = null;
let renderedKey = '';
let previous = null;
let detailFromBase = false;
const scrollMemory = new Map();

/** Zoek de handler eerst op de huidige pagina, daarna globaal (zelfde naam op twee pagina's mag). */
function handlerFor(kind, all, name, el) {
  const inDialog = dialogOpen() && $('#dialog').contains(el);
  const own = inDialog ? {} : (BASE[renderedBase]?.[kind] || {});
  return own[name] || all[name];
}

function markNav(base, params) {
  const key = base === 'aanbod' && params.get('shortlist') ? 'shortlist' : base === 'auto' ? 'aanbod' : base;
  $$('.nav-link[data-nav]').forEach(a => {
    const active = a.dataset.nav === key;
    a.classList.toggle('active', active);
    if (active) a.setAttribute('aria-current', 'page');
    else a.removeAttribute('aria-current');
  });
}

export async function renderBase(base, params = parseHash().params, id = parseHash().id) {
  renderedBase = base;
  renderedKey = `${base}/${id || ''}?${params.toString()}`;
  if (['aanbod', 'overzicht'].includes(base)) setLastList(location.hash);
  markNav(base, params);
  closeMenu();
  document.title = `${TITLES[base]} · OccasionIQ`;
  const page = BASE[base];
  $('#content').innerHTML = page.skeleton ? page.skeleton() : skeletons.head() + skeletons.rows();
  try {
    await page.render(params, id);
  } catch (e) {
    $('#content').innerHTML = errorState(e.message);
  }
  window.scrollTo(0, scrollMemory.get(location.hash) || 0);
}

async function route() {
  const r = parseHash();
  if (!PAGES.includes(r.page) || (r.page === 'auto' && !r.id)) {
    replace(r.page === 'auto' ? 'aanbod' : 'overzicht');
    return;
  }
  const detail = r.id ? DETAIL[r.page] : null;
  detailFromBase = Boolean(detail && previous && !previous.id && previous.page === r.page);
  previous = r;
  const key = `${r.page}/${detail ? '' : r.id || ''}?${r.params.toString()}`;
  if (key !== renderedKey || (!detail && !dialogOpen())) {
    await renderBase(r.page, r.params, detail ? null : r.id);
  }
  if (!detail) {
    if (dialogOpen()) closeDialogView();
    return;
  }
  try {
    await detail(r.id);
  } catch (e) {
    closeDialogView();
    toast(e.message, 'error');
  }
}

/** Sluit een detailvenster via de route, zodat terugknop en herladen hetzelfde doen. */
function closeDetail() {
  if (!parseHash().id || !DETAIL[parseHash().page]) {
    closeDialogView();
  } else if (detailFromBase) {
    history.back();
  } else {
    replace(renderedBase || 'overzicht');
  }
}

function closeMenu() {
  $('#sidebar').classList.remove('show');
  $('#menu-toggle').setAttribute('aria-expanded', 'false');
}

async function showApp() {
  $('#login').classList.add('hidden');
  $('#shell').classList.remove('hidden');
  await refreshProfiles();
  await route();
}

async function initialize() {
  const sess = await api('/session');
  if (!sess.authenticated) {
    $('#login').classList.remove('hidden');
    $('#password').focus();
    return;
  }
  setCsrf(sess.csrf);
  await showApp();
}

actions['refresh-all'] = el => startRefresh('all', el);
actions.retry = () => renderBase(renderedBase || 'overzicht');
actions['close-menu'] = () => closeMenu();

async function run(handler, ...args) {
  try {
    await handler(...args);
  } catch (err) {
    toast(err.message, 'error');
  }
}

document.addEventListener('click', async e => {
  $$('details.menu[open]').forEach(m => {
    if (!m.contains(e.target)) m.removeAttribute('open');
  });
  if (e.target.closest('[data-close]')) {
    closeDetail();
    return;
  }
  const el = e.target.closest('[data-action]');
  if (!el) return;
  const handler = handlerFor('actions', actions, el.dataset.action, el);
  if (!handler) return;
  e.preventDefault();
  await run(handler, el, e);
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
      $('#login-error').textContent = err.status === 401 ? 'Dit wachtwoord klopt niet.' : err.message;
    }
    return;
  }
  const handler = handlerFor('submits', submits, form.dataset.submit, form);
  if (!handler) return;
  e.preventDefault();
  const submitter = e.submitter;
  submitter?.classList.add('loading');
  await run(handler, form, e);
  submitter?.classList.remove('loading');
});

document.addEventListener('input', e => {
  const handler = handlerFor('inputs', inputs, e.target.dataset?.input, e.target);
  if (handler) handler(e.target);
});

document.addEventListener('change', async e => {
  const handler = handlerFor('changes', changes, e.target.dataset?.change, e.target);
  if (handler) await run(handler, e.target);
});

const dialog = $('#dialog');
dialog.addEventListener('cancel', e => {
  e.preventDefault();
  closeDetail();
});
dialog.addEventListener('click', e => {
  if (e.target === dialog) closeDetail();
});
document.addEventListener('keydown', async e => {
  const keyHandler = handlerFor('keydowns', keydowns, e.target.dataset?.keydown, e.target);
  if (keyHandler) await run(keyHandler, e.target, e);
  if (e.key === 'Escape' && $('#sidebar').classList.contains('show')) closeMenu();
  if (e.key === 'Escape') $$('details.menu[open]').forEach(m => m.removeAttribute('open'));
});
$('#top-refresh').addEventListener('click', e => startRefresh('all', e.currentTarget));
$('#logout').addEventListener('click', async () => {
  try {
    await api('/logout', {method: 'POST'});
  } finally {
    location.reload();
  }
});
$('#menu-toggle').addEventListener('click', () => {
  const open = $('#sidebar').classList.toggle('show');
  $('#menu-toggle').setAttribute('aria-expanded', String(open));
  if (open) $('#sidebar .nav-link')?.focus();
});
window.addEventListener('hashchange', () => {
  if (!$('#shell').classList.contains('hidden')) route();
});
/* Een pagina die zijn adres bijwerkt (filters, sortering) zonder opnieuw te laden. */
window.addEventListener('occasioniq:query', () => {
  const r = parseHash();
  renderedKey = `${r.page}/${r.id || ''}?${r.params.toString()}`;
  if (r.page === 'aanbod') setLastList(location.hash);
});
let scrollTimer = null;
window.addEventListener('scroll', () => {
  clearTimeout(scrollTimer);
  scrollTimer = setTimeout(() => scrollMemory.set(location.hash, window.scrollY), 80);
}, {passive: true});
onRefreshFinished(async () => {
  await refreshProfiles();
  if (renderedBase && !dialogOpen()) await renderBase(renderedBase);
});
onProfileChange(() => {
  if (renderedBase && !dialogOpen()) renderBase(renderedBase);
});
$('#profile-select').addEventListener('change', e => selectProfile(e.target.value));

initialize().catch(e => {
  $('#login').classList.remove('hidden');
  $('#login-error').textContent = 'Kan de server niet bereiken: ' + e.message;
});
