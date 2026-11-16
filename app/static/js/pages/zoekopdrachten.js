import {api} from '../api.js';
import {esc, euro, fmt, relatief} from '../format.js';
import {RUN_STATE} from '../labels.js';
import {$, badge, button, card, closeDialogView, dialogHead, emptyState, field, icon, menu, notice, openDialog,
  pageHead, setFieldError, skeletons, statusBadge, toast, toggle} from '../ui.js';
import {startRefresh} from '../refresh.js';
import {refreshProfiles} from '../context.js';

let data = {items: []};

export function skeleton() {
  return skeletons.head() + skeletons.block() + skeletons.cards(2);
}

/** Naamvoorstel uit het pad van de zoeklink: /volvo/xc90/2025 → "Volvo XC90". */
export function suggestName(url) {
  let path;
  try {
    path = new URL(url).pathname;
  } catch {
    return '';
  }
  const parts = path.split('/').filter(p => p && !/^\d+$/.test(p) && !p.includes('=')).slice(0, 2);
  const brands = {bmw: 'BMW', vw: 'VW', mg: 'MG', ds: 'DS', byd: 'BYD', mini: 'MINI', gmc: 'GMC'};
  const word = w => brands[w.toLowerCase()]
    || (/\d/.test(w) ? w.toUpperCase() : w.charAt(0).toUpperCase() + w.slice(1));
  const fmtPart = p => decodeURIComponent(p).split('-').map(word).join(' ');
  return parts.map(fmtPart).join(' ').trim();
}

function sourceBadge(x) {
  if (x.provider === 'gaspedaal_site' || (x.provider === 'fixture' && !x.has_snapshot && data.gaspedaal_site_available)) {
    return '';
  }
  if (x.provider === 'gaspedaal') return badge('Via koppeling', 'info');
  return x.has_snapshot ? badge('Eigen import', 'info') : badge('Nog geen gegevens', 'warning');
}

function lastRun(x) {
  if (!x.last_run) return '<span>Nog niet gecontroleerd</span>';
  return `<span>Laatste controle <strong>${esc(relatief(x.last_run.at))}</strong></span>
    ${statusBadge(RUN_STATE, x.last_run.state)}`;
}

function profileCard(x) {
  const items = [
    {text: 'Bewerken', icon: 'pencil', action: 'edit-profile', data: {id: x.id}},
    {text: 'Nu controleren', icon: 'refresh', action: 'refresh-profile', data: {id: x.id}},
    {text: 'Archiveren', icon: 'archive', action: 'archive-profile', data: {id: x.id}, variant: 'danger'},
  ];
  const scope = x.scope_changed_at ? notice('De filters zijn gewijzigd. Bij de volgende volledige controle worden auto\'s '
    + 'buiten de nieuwe filters bewaard, maar niet meer gevolgd.', 'info') : '';
  return `<section class="card profile-card"><div class="row-between"><div><h3>${esc(x.title)}</h3>
    <a class="small" href="${esc(x.search_url)}" target="_blank" rel="noopener noreferrer">Open op Gaspedaal
    ${icon('external', 'icon-sm')}</a></div><div class="actions">${sourceBadge(x)}
    ${toggle(x.enabled ? 'Actief' : 'Gepauzeerd', Boolean(x.enabled), {action: 'toggle-profile', data: {id: x.id}})}
    ${menu(`Acties voor ${x.title}`, items)}</div></div>
    <div class="meta"><span><strong>${fmt(x.listings_active)}</strong> te koop</span>
      <span><strong>${fmt(x.listings_match)}</strong> voldoen</span>
      <span>Budget <strong>${x.budget_eur ? euro(x.budget_eur) : 'niet ingesteld'}</strong></span>${lastRun(x)}</div>
    ${scope}</section>`;
}

export async function render() {
  data = await api('/profiles');
  const live = data.gaspedaal_site_available;
  const form = `<form data-submit="create-profile" class="form-grid" novalidate>
    ${field({label: 'Zoeklink van Gaspedaal', name: 'search_url', type: 'url', id: 'new-url',
      hint: 'Stel je filters in op gaspedaal.nl en plak hier de link uit de adresbalk.',
      attrs: {required: true, placeholder: 'https://www.gaspedaal.nl/volvo/xc90?…', 'data-input': 'suggest-name'}})}
    ${field({label: 'Naam', name: 'title', id: 'new-title', hint: 'Voorstel uit de link; pas gerust aan.',
      attrs: {required: true, minlength: 2}})}
    <div>${button('Toevoegen', {type: 'submit', variant: 'primary', icon: 'plus'})}</div></form>`;
  const list = data.items.length ? data.items.map(profileCard).join('')
    : card('', emptyState({iconName: 'search', title: 'Nog geen zoekopdracht', text: 'Voeg hierboven je eerste zoeklink toe.'}));
  $('#content').innerHTML = pageHead('Zoekopdrachten', 'Welke markt volg je? Elke zoekopdracht is een zoeklink van Gaspedaal.')
    + (live ? '' : notice('Directe uitlezing van Gaspedaal staat uit. Na het toevoegen importeer je gegevens via '
      + '<strong>Bewerken → Geavanceerd</strong>; zie ook Instellingen.', 'warning'))
    + card('Zoekopdracht toevoegen', form) + `<div class="stack">${list}</div>`;
}

function editDialog(x) {
  const sel = v => (x.provider === v ? ' selected' : '');
  const options = [`<option value="fixture"${sel('fixture')}>Eigen import (JSON)</option>`];
  if (data.gaspedaal_site_available) options.push(`<option value="gaspedaal_site"${sel('gaspedaal_site')}>Zoeklink</option>`);
  if (data.gaspedaal_api_configured) options.push(`<option value="gaspedaal"${sel('gaspedaal')}>Koppeling</option>`);
  openDialog(dialogHead('Zoekopdracht bewerken', x.title) + `<section class="card">
    <form data-submit="edit-profile" data-id="${esc(x.id)}" class="stack" novalidate>
      ${field({label: 'Naam', name: 'title', value: x.title, attrs: {required: true, minlength: 2}})}
      ${field({label: 'Zoeklink van Gaspedaal', name: 'search_url', type: 'url', value: x.search_url,
        attrs: {required: true, 'data-input': 'url-changed', 'data-original': x.search_url}})}
      <div id="url-warning" hidden>${notice('Auto\'s die buiten de nieuwe filters vallen blijven bewaard, maar worden '
        + 'niet meer gevolgd.', 'warning')}</div>
      ${field({label: 'Budget (€)', name: 'budget_eur', type: 'number', value: x.budget_eur ?? '',
        hint: 'Je maximale aankoopbedrag. Leeg laten als je (nog) geen budget hebt.', attrs: {min: 1000, step: 250}})}
      <details class="disclosure"><summary>${icon('chevron-down')}Geavanceerd</summary><div class="stack">
        <div class="field"><label for="edit-source">Gegevensbron</label>
          <select id="edit-source" name="provider">${options.join('')}</select></div>
        <div>${button('Gegevens importeren (JSON)', {icon: 'download', action: 'import', data: {id: x.id}})}</div>
      </div></details>
      <div class="row">${button('Opslaan', {type: 'submit', variant: 'primary'})}
        ${button('Annuleren', {attrs: {'data-close': true}})}</div></form></section>`);
}

function importDialog(id) {
  const example = '{"complete":true,"listings":[{"external_id":"…","title":"…","price_eur":75000}]}';
  openDialog(dialogHead('Gegevens importeren', 'Advertenties uit een JSON-bestand; ze worden bij de volgende controle verwerkt.')
    + notice('Geef met <code>"complete": true</code> aan dat dit het volledige aanbod is. Dan mogen auto\'s die '
      + 'ontbreken als niet meer gezien worden gemarkeerd. Bij twijfel: <code>"complete": false</code>.', 'warning')
    + `<section class="card"><form data-submit="import" data-id="${esc(id)}" class="stack">
      <div class="field"><label for="json-file">JSON-bestand</label>
        <input id="json-file" type="file" accept="application/json,.json" data-change="json-file"></div>
      ${field({label: 'Of plak de inhoud', name: 'json', type: 'textarea', id: 'json-text', attrs: {placeholder: example}})}
      <div>${button('Importeren', {type: 'submit', variant: 'primary'})}</div></form></section>`);
}

function archiveDialog(x) {
  openDialog(dialogHead('Zoekopdracht archiveren?', x.title) + `<section class="card stack">
    <p>De auto's en de prijshistorie blijven bewaard. Deze zoekopdracht wordt niet meer gecontroleerd en verdwijnt uit de
    keuzelijst.</p><div class="row">${button('Archiveren', {variant: 'danger', icon: 'archive', action: 'confirm-archive',
      data: {id: x.id}})}${button('Annuleren', {attrs: {'data-close': true}})}</div></section>`);
}

const byId = id => data.items.find(p => p.id === id);

async function afterChange() {
  await refreshProfiles();
  await render();
}

export const actions = {
  'edit-profile'(el) {
    el.closest('details.menu')?.removeAttribute('open');
    editDialog(byId(el.dataset.id));
  },
  'archive-profile'(el) {
    el.closest('details.menu')?.removeAttribute('open');
    archiveDialog(byId(el.dataset.id));
  },
  async 'confirm-archive'(el) {
    await api('/profiles/' + encodeURIComponent(el.dataset.id) + '/archive', {method: 'POST'});
    closeDialogView();
    toast('Zoekopdracht gearchiveerd');
    await afterChange();
  },
  async 'toggle-profile'(el) {
    const x = byId(el.dataset.id);
    await api('/profiles/' + encodeURIComponent(x.id), {method: 'PATCH', body: {enabled: !x.enabled}});
    toast(x.enabled ? 'Zoekopdracht gepauzeerd: wordt niet meer gecontroleerd' : 'Zoekopdracht weer actief');
    await afterChange();
  },
  import(el) {
    importDialog(el.dataset.id);
  },
  async 'refresh-profile'(el) {
    el.closest('details.menu')?.removeAttribute('open');
    await startRefresh({profile_ids: [el.dataset.id]}, el);
  },
};

export const inputs = {
  'suggest-name'(el) {
    const title = $('#new-title');
    const suggestion = suggestName(el.value.trim());
    if (suggestion && (!title.value || title.dataset.auto === '1')) {
      title.value = suggestion;
      title.dataset.auto = '1';
    }
  },
  'url-changed'(el) {
    $('#url-warning').hidden = el.value.trim() === el.dataset.original;
  },
};

export const changes = {
  async 'json-file'(el) {
    if (el.files[0]) $('#json-text').value = await el.files[0].text();
  },
};

export const submits = {
  async 'create-profile'(form) {
    const body = Object.fromEntries(new FormData(form));
    if (!/^https:\/\/(www\.)?gaspedaal\.nl\//.test(body.search_url.trim())) {
      setFieldError(form, 'search_url', 'Plak een link die begint met https://www.gaspedaal.nl/');
      return;
    }
    setFieldError(form, 'search_url', '');
    if (!body.title || body.title.trim().length < 2) {
      setFieldError(form, 'title', 'Geef de zoekopdracht een naam van minstens twee tekens.');
      return;
    }
    let r;
    try {
      r = await api('/profiles', {method: 'POST', body});
    } catch (e) {
      setFieldError(form, 'search_url', e.message);
      return;
    }
    await afterChange();
    if (r.provider === 'gaspedaal_site') {
      toast('Zoekopdracht toegevoegd. De eerste controle start nu.');
      await startRefresh({profile_ids: [r.id]});
      await afterChange();
    } else {
      toast('Zoekopdracht toegevoegd. Importeer nu gegevens via Bewerken → Geavanceerd.', 'info');
    }
  },
  async 'edit-profile'(form) {
    const d = Object.fromEntries(new FormData(form));
    const id = form.dataset.id;
    const x = byId(id);
    const body = {title: d.title.trim(), search_url: d.search_url.trim(), budget_eur: d.budget_eur ? Number(d.budget_eur) : null};
    try {
      await api('/profiles/' + encodeURIComponent(id), {method: 'PATCH', body});
    } catch (e) {
      setFieldError(form, 'search_url', e.message);
      return;
    }
    if (d.provider && d.provider !== x.provider) {
      await api('/profiles/' + encodeURIComponent(id) + '/source', {method: 'PUT', body: {provider: d.provider}});
    }
    closeDialogView();
    toast('Zoekopdracht opgeslagen');
    await afterChange();
  },
  async import(form) {
    let obj;
    try {
      obj = JSON.parse($('#json-text').value);
    } catch {
      setFieldError(form, 'json', 'De inhoud is geen geldige JSON.');
      return;
    }
    const r = await api('/profiles/' + encodeURIComponent(form.dataset.id) + '/snapshot', {method: 'POST', body: obj});
    toast(`${fmt(r.imported)} advertenties geïmporteerd. Start een controle om ze te verwerken.`);
    closeDialogView();
    await afterChange();
  },
};
