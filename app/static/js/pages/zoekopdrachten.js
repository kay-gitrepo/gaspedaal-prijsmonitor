import {api} from '../api.js';
import {esc} from '../format.js';
import {$, closeModalView, head, modal, modalHead, tag, toast} from '../ui.js';
import {startRefresh} from '../refresh.js';

function sourceLabel(x) {
  if (x.provider === 'gaspedaal_site') return 'Gaspedaal zoeklink';
  if (x.provider === 'gaspedaal') return 'JSON API';
  return x.has_snapshot ? 'JSON snapshot' : 'Nog geen invoer';
}

function profileCard(x, data) {
  const sel = v => (x.provider === v ? 'selected' : '');
  const options = ['<option value="fixture" ' + sel('fixture') + '>JSON import</option>'];
  if (data.gaspedaal_site_available) {
    options.push(`<option value="gaspedaal_site" ${sel('gaspedaal_site')}>Gaspedaal zoeklink</option>`);
  }
  if (data.gaspedaal_api_configured) options.push(`<option value="gaspedaal" ${sel('gaspedaal')}>JSON API</option>`);
  const ok = x.provider !== 'fixture' || x.has_snapshot;
  return `<div class="profile-card"><div class="profile-icon">⌕</div><div class="profile-info">
    <strong>${esc(x.title)}</strong><small>${esc(x.search_url)}</small></div>${tag(sourceLabel(x), ok ? 'green' : 'amber')}
    <button class="btn btn-sm" data-action="import" data-id="${esc(x.id)}">JSON importeren</button>
    <select data-change="source" data-id="${esc(x.id)}" aria-label="Gegevensbron">${options.join('')}</select>
    <button class="btn btn-secondary btn-sm" data-action="refresh-profile" data-id="${esc(x.id)}"
      aria-label="Controleer deze zoekopdracht">↻</button></div>`;
}

export async function render() {
  const data = await api('/profiles');
  const live = data.gaspedaal_site_available;
  $('#content').innerHTML = head('BRONBEHEER', 'Zoekprofielen',
    'Plak de zoeklink van Gaspedaal. Experimentele directe uitlezing, een ingestelde JSON-API of handmatige JSON-import.')
    + `<section class="card"><div class="card-head"><h3>Nieuw zoekprofiel</h3>
      ${tag(live ? 'Directe URL-uitlezing ingeschakeld' : 'JSON-importmodus', live ? 'green' : 'amber')}</div>
      <form data-submit="create-profile" class="form-grid">
        <div class="field"><label for="p-title">Naam</label>
          <input id="p-title" name="title" placeholder="XC90 Ultra 2025+" required minlength="2"></div>
        <div class="field"><label for="p-url">Gaspedaal-zoek-URL</label>
          <input id="p-url" name="search_url" type="url" placeholder="https://www.gaspedaal.nl/…" required></div>
        <button class="btn btn-primary">Opslaan</button></form></section>
    <section class="card"><div class="card-head"><h3>Opgeslagen zoekprofielen</h3>
      <span class="micro">${data.items.length} profielen</span></div><div class="stack">
      ${data.items.map(x => profileCard(x, data)).join('')
        || '<p class="muted">Nog geen profiel. Voeg eerst een zoeklink toe.</p>'}</div></section>`;
}

function importModal(id) {
  const example = '{"complete":true,"listings":[{"external_id":"...","title":"...","price_eur":75000}]}';
  modal(modalHead('Importeer JSON-snapshot', 'Alle advertenties uit deze invoer worden bij de volgende refresh verwerkt.')
    + `<div class="notice warn">Een volledige snapshot met <code>complete:true</code> mag eerder aanwezige auto's als
      verdwenen markeren. Gebruik <code>complete:false</code> voor onvolledige imports.</div>
    <form data-submit="import" data-id="${esc(id)}" class="stack">
      <div class="field"><label for="json-file">JSON-bestand</label>
        <input id="json-file" type="file" accept="application/json,.json" data-change="json-file"></div>
      <div class="field"><label for="json-text">JSON-inhoud</label>
        <textarea id="json-text" rows="11" placeholder="${esc(example)}"></textarea></div>
      <button class="btn btn-primary">Snapshot bewaren</button></form>`);
}

export const actions = {
  import(el) {
    importModal(el.dataset.id);
  },
  'refresh-profile'(el) {
    return startRefresh({profile_ids: [el.dataset.id]});
  },
};

export const changes = {
  async source(el) {
    await api('/profiles/' + encodeURIComponent(el.dataset.id) + '/source', {method: 'PUT', body: {provider: el.value}});
    toast('Gegevensbron aangepast');
    await render();
  },
  async 'json-file'(el) {
    if (el.files[0]) $('#json-text').value = await el.files[0].text();
  },
};

export const submits = {
  async 'create-profile'(form) {
    const body = Object.fromEntries(new FormData(form));
    const r = await api('/profiles', {method: 'POST', body});
    toast(r.provider === 'gaspedaal_site' ? 'Zoeklink toegevoegd; controleer de eerste run op brondekking.'
      : 'Zoekprofiel toegevoegd. Importeer nu een snapshot.');
    await render();
  },
  async import(form) {
    let obj;
    try {
      obj = JSON.parse($('#json-text').value);
    } catch {
      throw new Error('JSON is ongeldig');
    }
    const r = await api('/profiles/' + encodeURIComponent(form.dataset.id) + '/snapshot', {method: 'POST', body: obj});
    toast(`${r.imported} advertenties geïmporteerd`);
    closeModalView();
    await render();
  },
};
