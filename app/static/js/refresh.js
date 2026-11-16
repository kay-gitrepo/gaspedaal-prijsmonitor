/* Handmatig een controle starten. */
import {api} from './api.js';
import {toast} from './ui.js';

let afterRefresh = () => {};

export function onRefreshAccepted(fn) {
  afterRefresh = fn;
}

export async function startRefresh(scope = 'all') {
  try {
    const result = await api('/refresh-runs', {method: 'POST', body: {scope, reason: 'manual_ui'}});
    toast('Refresh geaccepteerd: ' + result.run_id);
    setTimeout(() => afterRefresh(result), 1400);
  } catch (e) {
    toast('Refresh niet gestart: ' + e.message);
  }
}
