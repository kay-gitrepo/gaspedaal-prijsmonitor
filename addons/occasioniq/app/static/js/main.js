/* Opstart, inloggen, router en gedelegeerde gebeurtenissen. Geen framework, geen build-stap. */
import {api, setCsrf} from './api.js';
import {PAGES, parseHash, replace} from './router.js';
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

const BASE = {overzicht, aanbod, wensen, zoekopdrachten, controles, 'ai-analyse': aiAnalyse, instellingen};
const DETAIL = {auto: auto.showCar, controles: controles.showRun, 'ai-analyse': aiAnalyse.showIntegration};
const TITLES = {
  overzicht: 'Overzicht', aanbod: 'Aanbod', wensen: 'Mijn wensen', zoekopdrachten: 'Zoekopdrachten',
  controles: 'Controles', 'ai-analyse': 'AI-beoordeling', instellingen: 'Instellingen',
};
const MODULES = Object.values(BASE).concat([auto]);
const actions = Object.assign({}, ...MODULES.map(m => m.actions || {}));
const submits = Object.assign({}, ...MODULES.map(m => m.submits || {}));
const changes = Object.assign({}, ...MODULES.map(m => m.changes || {}));
const inputs = Object.assign({}, ...MODULES.map(m => m.inputs || {}));

let renderedBase = null;
let renderedQuery = '';
let previous = null;
let detailFromBase = false;

function markNav(base, params) {
  const key = base === 'aanbod' && params.get('shortlist') ? 'shortlist' : base;
  $$('.nav-link[data-nav]').forEach(a => {
    const active = a.dataset.nav === key;
    a.classList.toggle('active', active);
    if (active) a.setAttribute('aria-current', 'page');
    else a.removeAttribute('aria-current');
  });
}

export async function renderBase(base, params = parseHash().params) {
  renderedBase = base;
  renderedQuery = params.toString();
  markNav(base, params);
  closeMenu();
  document.title = `${TITLES[base]} · OccasionIQ`;
  const page = BASE[base];
  $('#content').innerHTML = page.skeleton ? page.skeleton() : skeletons.head() + skeletons.rows();
  try {
    await page.render(params);
  } catch (e) {
    $('#content').innerHTML = errorState(e.message);
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
  detailFromBase = Boolean(detail && previous && !previous.id && (previous.page === base));
  previous = r;
  const query = r.page === 'auto' ? renderedQuery : r.params.toString();
  const sameBase = base === renderedBase && query === renderedQuery;
  if (!sameBase || (!detail && !dialogOpen())) {
    await renderBase(base, r.page === 'auto' ? new URLSearchParams(query) : r.params);
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
  if (!parseHash().id) {
    closeDialogView();
  } else if (detailFromBase) {
    history.back();
  } else {
    const params = renderedQuery ? Object.fromEntries(new URLSearchParams(renderedQuery)) : null;
    replace(renderedBase || 'overzicht', null, params);
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
  const own = dialogOpen() && $('#dialog').contains(el) ? {} : (BASE[renderedBase]?.actions || {});
  const handler = own[el.dataset.action] || actions[el.dataset.action];
  if (!handler) return;
  e.preventDefault();
  try {
    await handler(el, e);
  } catch (err) {
    toast(err.message, 'error');
  }
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
  const handler = submits[form.dataset.submit];
  if (!handler) return;
  e.preventDefault();
  const submitter = e.submitter;
  submitter?.classList.add('loading');
  try {
    await handler(form, e);
  } catch (err) {
    toast(err.message, 'error');
  } finally {
    submitter?.classList.remove('loading');
  }
});

document.addEventListener('input', e => {
  const handler = inputs[e.target.dataset?.input];
  if (handler) handler(e.target);
});

document.addEventListener('change', async e => {
  const handler = changes[e.target.dataset?.change];
  if (!handler) return;
  try {
    await handler(e.target);
  } catch (err) {
    toast(err.message, 'error');
  }
});

const dialog = $('#dialog');
dialog.addEventListener('cancel', e => {
  e.preventDefault();
  closeDetail();
});
dialog.addEventListener('click', e => {
  if (e.target === dialog) closeDetail();
});
document.addEventListener('keydown', e => {
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
