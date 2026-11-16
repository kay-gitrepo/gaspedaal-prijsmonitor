/* Handmatig een controle starten. Geen technische ID's in meldingen. */
import {api} from './api.js';
import {busy, toast} from './ui.js';

let afterRefresh = () => {};

export function onRefreshAccepted(fn) {
  afterRefresh = fn;
}

export async function startRefresh(scope = 'all', buttonEl = null) {
  const done = busy(buttonEl);
  try {
    const result = await api('/refresh-runs', {method: 'POST', body: {scope, reason: 'manual_ui'}});
    toast('Controle gestart. Het resultaat staat zo bij Controles.', 'info');
    setTimeout(() => afterRefresh(result), 1400);
  } catch (e) {
    toast('Controle niet gestart: ' + e.message, 'error');
  } finally {
    done();
  }
}
