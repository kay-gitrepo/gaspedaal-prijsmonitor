import {api} from '../api.js';
import {esc} from '../format.js';
import {$, badge, button, card, closeDialogView, dialogHead, emptyState, field, icon, notice, openDialog, pageHead,
  skeletons, toast} from '../ui.js';
import {startRefresh} from '../refresh.js';
import {refreshProfileLabel} from '../context.js';

export function skeleton() {
  return skeletons.head() + skeletons.block() + skeletons.cards(2);
}

function sourceBadge(x) {
  if (x.provider === 'gaspedaal_site') return badge('Live via zoeklink', 'success');
  if (x.provider === 'gaspedaal') return badge('Live via koppeling', 'success');
  return x.has_snapshot ? badge('Eigen import', 'info') : badge('Nog geen gegevens', 'warning');
}

function profileCard(x, data) {
  const sel = v => (x.provider === v ? ' selected' : '');
  const options = [`<option value="fixture"${sel('fixture')}>Eigen import (JSON)</option>`];
  if (data.gaspedaal_site_available) options.push(`<option value="gaspedaal_site"${sel('gaspedaal_site')}>Zoeklink</option>`);
  if (data.gaspedaal_api_configured) options.push(`<option value="gaspedaal"${sel('gaspedaal')}>Koppeling</option>`);
  return `<section class="card"><div class="row-between"><div><h3>${esc(x.title)}</h3>
    <a class="small" href="${esc(x.search_url)}" target="_blank" rel="noopener noreferrer">Open op Gaspedaal
    ${icon('external', 'icon-sm')}</a></div><div class="row">${sourceBadge(x)}
    ${button('Nu controleren', {icon: 'refresh', size: 's', action: 'refresh-profile', data: {id: x.id}})}</div></div>
    <details class="disclosure"><summary>${icon('chevron-down')}Geavanceerd</summary><div class="form-grid">
      <div class="field"><label for="src-${esc(x.id)}">Gegevensbron</label>
        <select id="src-${esc(x.id)}" data-change="source" data-id="${esc(x.id)}">${options.join('')}</select></div>
      <div>${button('Gegevens importeren', {icon: 'download', action: 'import', data: {id: x.id}})}</div>
    </div></details></section>`;
}

export async function render() {
  const data = await api('/profiles');
  const live = data.gaspedaal_site_available;
  const form = `<form data-submit="create-profile" class="form-grid" novalidate>
    ${field({label: 'Naam', name: 'title', attrs: {required: true, minlength: 2, placeholder: 'Volvo XC90 vanaf 2025'}})}
    ${field({label: 'Zoeklink van Gaspedaal', name: 'search_url', type: 'url',
      attrs: {required: true, placeholder: 'https://www.gaspedaal.nl/…'}})}
    <div>${button('Zoekopdracht toevoegen', {type: 'submit', variant: 'primary', icon: 'plus'})}</div></form>`;
  const list = data.items.length ? data.items.map(x => profileCard(x, data)).join('')
    : card('', emptyState({iconName: 'search', title: 'Nog geen zoekopdracht',
      text: 'Voeg hierboven je eerste zoeklink toe.'}));
  $('#content').innerHTML = pageHead('Zoekopdrachten', 'Welke markt volg je? Plak de zoeklink van Gaspedaal met je filters.')
    + (live ? '' : notice('Directe uitlezing van Gaspedaal staat uit. Je kunt zoekopdrachten toevoegen en gegevens '
      + 'importeren; zie Instellingen.', 'warning'))
    + card('Nieuwe zoekopdracht', form) + `<div class="stack">${list}</div>`;
}

function importDialog(id) {
  const example = '{"complete":true,"listings":[{"external_id":"…","title":"…","price_eur":75000}]}';
  openDialog(dialogHead('Gegevens importeren', 'Advertenties uit een JSON-bestand; ze worden bij de volgende controle verwerkt.')
    + notice('Geef met <code>"complete": true</code> aan dat dit het volledige aanbod is. Dan mogen auto\'s die '
      + 'ontbreken als niet meer gezien worden gemarkeerd. Bij twijfel: <code>"complete": false</code>.', 'warning')
    + `<form data-submit="import" data-id="${esc(id)}" class="stack">
      <div class="field"><label for="json-file">JSON-bestand</label>
        <input id="json-file" type="file" accept="application/json,.json" data-change="json-file"></div>
      ${field({label: 'Of plak de inhoud', name: 'json', type: 'textarea', id: 'json-text', attrs: {placeholder: example}})}
      <div>${button('Importeren', {type: 'submit', variant: 'primary'})}</div></form>`);
}

export const actions = {
  import(el) {
    importDialog(el.dataset.id);
  },
  'refresh-profile'(el) {
    return startRefresh({profile_ids: [el.dataset.id]}, el);
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
    toast(r.provider === 'gaspedaal_site' ? 'Zoekopdracht toegevoegd. Start een controle om de auto\'s op te halen.'
      : 'Zoekopdracht toegevoegd. Importeer nu gegevens via Geavanceerd.');
    refreshProfileLabel();
    await render();
  },
  async import(form) {
    let obj;
    try {
      obj = JSON.parse($('#json-text').value);
    } catch {
      throw new Error('De inhoud is geen geldige JSON.');
    }
    const r = await api('/profiles/' + encodeURIComponent(form.dataset.id) + '/snapshot', {method: 'POST', body: obj});
    toast(`${r.imported} advertenties geïmporteerd. Start een controle om ze te verwerken.`);
    closeDialogView();
    await render();
  },
};
