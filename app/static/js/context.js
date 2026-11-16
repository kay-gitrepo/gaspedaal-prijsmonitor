/* Gedeelde context in de bovenbalk: de gekozen zoekopdracht. */
import {api} from './api.js';
import {$} from './ui.js';

export async function refreshProfileLabel() {
  try {
    const data = await api('/profiles');
    const active = data.items.filter(p => p.enabled);
    let text = 'Nog geen zoekopdracht';
    if (active.length === 1) text = active[0].title;
    else if (active.length > 1) text = `Alle zoekopdrachten (${active.length})`;
    $('#current-profile').textContent = text;
  } catch {
    $('#current-profile').textContent = '—';
  }
}
