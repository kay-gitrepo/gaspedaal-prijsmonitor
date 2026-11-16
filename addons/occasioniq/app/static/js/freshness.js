/* Actualiteit: hoe vers zijn de gegevens? Chip in de bovenbalk en een balk na een mislukte controle. */
import {api} from './api.js';
import {esc, relatief, wanneer} from './format.js';
import {$, icon, notice} from './ui.js';
import {follow, isFollowing} from './refresh.js';

let status = null;

export function lastStatus() {
  return status;
}

function chip(s) {
  const success = s.last_success;
  const last = s.last_run;
  if (s.running) return ['info', 'refresh', 'Bezig met controleren'];
  if (!last) return ['neutral', 'clock', 'Nog niet gecontroleerd'];
  if (last.state === 'FAILED') {
    return ['danger', 'alert', success ? `Laatste controle mislukt, gegevens van ${wanneer(success.finished_at)}`
      : 'Laatste controle mislukt'];
  }
  const age = success ? (Date.now() - new Date(success.finished_at).getTime()) / 3600000 : Infinity;
  if (age > s.stale_after_hours) return ['warning', 'clock', `Meer dan ${s.stale_after_hours} uur niet gecontroleerd`];
  if (last.state === 'PARTIAL') return ['warning', 'alert', `Laatste controle gedeeltelijk, ${relatief(last.finished_at)}`];
  return ['success', 'check-circle', `Bijgewerkt ${relatief(success.finished_at)}`];
}

/** Haal de status op, werk de chip bij en volg een lopende controle (bijvoorbeeld gestart door Home Assistant). */
export async function refreshStatus() {
  try {
    status = await api('/status');
  } catch {
    return null;
  }
  const [variant, ic, text] = chip(status);
  const el = $('#freshness');
  el.className = `freshness badge badge-${variant}`;
  el.innerHTML = `${icon(ic)}<span class="freshness-text">${esc(text)}</span>`;
  el.title = text;
  if (status.running && !isFollowing()) follow(status.running.id);
  return status;
}

/** Balk voor Overzicht en Aanbod als de laatste controle is mislukt. */
export function failureNotice() {
  const s = status;
  if (!s?.last_run || s.last_run.state !== 'FAILED') return '';
  const since = s.last_success ? ` Je ziet de stand van ${esc(wanneer(s.last_success.finished_at))}.` : '';
  return notice(`De laatste controle is mislukt.${since} Er zijn geen auto's als verdwenen gemarkeerd.
    <a href="#/controles/${encodeURIComponent(s.last_run.id)}">Bekijk wat er misging</a>`, 'danger');
}

setInterval(() => {
  if (!document.hidden && !$('#shell').classList.contains('hidden')) refreshStatus();
}, 60000);
