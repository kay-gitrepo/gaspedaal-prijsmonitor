/* Een controle starten en volgen tot hij klaar is. Geen technische ID's in meldingen. */
import {api} from './api.js';
import {fmt} from './format.js';
import {$, toast} from './ui.js';

const FINAL = ['COMPLETE', 'PARTIAL', 'FAILED'];
let afterRefresh = () => {};
let following = null;

export function onRefreshFinished(fn) {
  afterRefresh = fn;
}

export function isFollowing() {
  return following !== null;
}

/** Zin in gewone taal over de uitkomst van een controle. */
export function outcomeSentence(run) {
  const s = run.summary || {};
  const parts = [`${fmt(s.found ?? 0)} auto's`];
  if (s.new) parts.push(`${fmt(s.new)} nieuw`);
  if (s.price_changes) parts.push(`${fmt(s.price_changes)} ${s.price_changes === 1 ? 'prijswijziging' : 'prijswijzigingen'}`);
  if (s.missing_new) parts.push(`${fmt(s.missing_new)} niet meer gezien`);
  if (s.reappeared) parts.push(`${fmt(s.reappeared)} weer terug`);
  if (s.out_of_scope_new) parts.push(`${fmt(s.out_of_scope_new)} buiten de nieuwe filters`);
  if (run.state === 'COMPLETE') return `Controle geslaagd: ${parts.join(', ')}.`;
  if (run.state === 'PARTIAL') return `Controle gedeeltelijk gelukt: ${parts.join(', ')}. Er is niets als verdwenen gemarkeerd.`;
  return 'Controle mislukt. Er zijn geen auto\'s als verdwenen gemarkeerd.';
}

function setBusy(on) {
  const btn = $('#top-refresh');
  btn.classList.toggle('loading', on);
  btn.setAttribute('aria-busy', String(on));
  btn.disabled = on;
  btn.querySelector('.btn-label').textContent = on ? 'Bezig met controleren' : 'Nu controleren';
}

const sleep = ms => new Promise(r => setTimeout(r, ms));

/** Volg een lopende controle (elke 2 s) tot de status eindigt. */
export async function follow(runId) {
  if (following === runId) return null;
  following = runId;
  setBusy(true);
  try {
    for (;;) {
      await sleep(2000);
      const run = await api('/refresh-runs/' + encodeURIComponent(runId));
      if (FINAL.includes(run.state)) {
        toast(outcomeSentence(run), run.state === 'FAILED' ? 'error' : run.state === 'PARTIAL' ? 'info' : 'success');
        await afterRefresh(run);
        return run;
      }
    }
  } catch (e) {
    toast('De voortgang van de controle kon niet worden gevolgd: ' + e.message, 'error');
    return null;
  } finally {
    following = null;
    setBusy(false);
  }
}

export async function startRefresh(scope = 'all', buttonEl = null) {
  if (buttonEl && buttonEl.id !== 'top-refresh') buttonEl.classList.add('loading');
  try {
    const result = await api('/refresh-runs', {method: 'POST', body: {scope, reason: 'manual_ui'}});
    toast('Controle gestart.', 'info');
    window.dispatchEvent(new CustomEvent('occasioniq:run-started'));
    return await follow(result.run_id);
  } catch (e) {
    if (e.status === 409 && e.detail?.active_run_id) {
      toast('Er loopt al een controle; die wordt nu gevolgd.', 'info');
      return await follow(e.detail.active_run_id);
    }
    toast('Controle niet gestart: ' + e.message, 'error');
    return null;
  } finally {
    buttonEl?.classList.remove('loading');
  }
}
