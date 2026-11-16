import {api} from '../api.js';
import {esc, fmt} from '../format.js';
import {$, badge, card, pageHead, skeletons} from '../ui.js';

const REQUEST = `POST http://&lt;server-ip&gt;:8099/api/v1/refresh-runs
Authorization: Bearer &lt;HA_REFRESH_TOKEN&gt;
Content-Type: application/json

{"scope":"all","reason":"scheduled_ha"}`;

export function skeleton() {
  return skeletons.head() + skeletons.block() + skeletons.block();
}

function onOff(on, yes = 'Aan', no = 'Uit') {
  return on ? badge(yes, 'success') : badge(no, 'neutral');
}

export async function render() {
  const s = await api('/system');
  const hosts = s.detail_hosts.length ? s.detail_hosts.map(h => `<code>${esc(h)}</code>`).join(' ') : 'geen';
  const source = `<dl class="facts">
    <div><dt>Directe uitlezing Gaspedaal</dt><dd>${onOff(s.live_source)}</dd></div>
    <div><dt>Gaspedaal-koppeling (API)</dt><dd>${onOff(s.api_configured, 'Ingesteld', 'Niet ingesteld')}</dd></div>
    <div><dt>AI-beoordeling</dt><dd>${onOff(s.ai_enabled)}</dd></div>
    <div><dt>AI-aanroepen per controle</dt><dd>${fmt(s.max_ai_calls_per_run)}</dd></div>
    <div><dt>Advertentietekst ophalen bij</dt><dd class="small">${hosts}</dd></div>
    <div><dt>Advertentieteksten per controle</dt><dd>${fmt(s.max_detail_fetches_per_run)}</dd></div>
    <div><dt>Uit het aanbod na</dt><dd>${fmt(s.disappearance_days)} dagen niet gezien</dd></div>
    <div><dt>Versie</dt><dd>${esc(s.version)}</dd></div></dl>`;
  $('#content').innerHTML = pageHead('Instellingen', 'Koppeling met Home Assistant en de status van de gegevensbronnen.')
    + `<div class="grid grid-2-even">
    ${card('Home Assistant', `<p class="muted">Home Assistant bepaalt wanneer er wordt gecontroleerd; de app heeft
      geen eigen planning. Gebruik dit adres in een <code>rest_command</code> en bewaar het token als geheim.</p>
      <pre class="json">${REQUEST}</pre><p class="muted small">Antwoord: 202 als de controle is gestart, 409 als er al
      een controle loopt.</p>`, {actionsHtml: badge('Beveiligd met token', 'success')})}
    ${card('Installatie en beveiliging', `<ol class="steps">
      <li>Maak in Home Assistant onder <strong>Instellingen → Automatiseringen</strong> een schema.</li>
      <li>Bewaar <code>HA_REFRESH_TOKEN</code> als geheim; gebruik hetzelfde token in de app.</li>
      <li>Gebruik buiten je thuisnetwerk HTTPS via een beveiligde reverse proxy of VPN.</li>
      <li>Stel <code>GEMINI_API_KEY</code> in voor AI-beoordeling. Zonder sleutel werkt herkenning zonder AI.</li>
      <li>Kijk bij <strong>Controles</strong> of elke controle volledig is geslaagd.</li></ol>`)}
    </div>
    ${card('Gegevensbronnen', source, {sub: 'Wordt ingesteld via omgevingsvariabelen of de add-on-opties'})}
    ${card('Over de bron', `<p class="muted">De zoeklink van Gaspedaal wordt gelezen op gestructureerde advertentiegegevens.
      Per auto worden alle aanbieders met hun prijs vastgelegd. De oorspronkelijke advertentietekst wordt alleen opgehaald
      bij domeinen die je zelf toestaat (<code>ADVERTISER_DETAIL_HOSTS</code>), met een maximum per controle
      (<code>MAX_DETAIL_FETCHES_PER_RUN</code>). Een controle die niet volledig is, markeert nooit auto's als
      verdwenen.</p>`, {id: 'over-de-bron'})}`;
}
