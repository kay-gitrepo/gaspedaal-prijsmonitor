import {$, head, tag} from '../ui.js';

const REQUEST = `POST http://&lt;server-ip&gt;:8099/api/v1/refresh-runs
Authorization: Bearer &lt;HA_REFRESH_TOKEN&gt;
Content-Type: application/json

{"scope":"all","reason":"scheduled_ha"}`;

export async function render() {
  $('#content').innerHTML = head('AUTOMATISERING', 'Home Assistant',
    'Home Assistant bepaalt wanneer de applicatie een refresh uitvoert. De app bevat geen eigen planning.') + `
    <div class="grid-two">
      <section class="card"><div class="card-head"><h3>Trigger-endpoint</h3>${tag('POST · beveiligd', 'green')}</div>
        <p class="subtitle">Gebruik dit endpoint in je Home Assistant <code>rest_command</code>.
          Stel de token in als secret in Home Assistant.</p><pre class="json">${REQUEST}</pre>
        <p class="micro">Antwoord: HTTP 202 met run-ID. Bij een lopende run HTTP 409.
          De volledige runhistorie staat in het uitvoeringslog.</p></section>
      <section class="card"><div class="card-head"><h3>Installatie en beveiliging</h3></div><div class="stack">
        <p>① Beheer het schema in <strong>Instellingen → Automatiseringen</strong> van Home Assistant.</p>
        <p>② Bewaar <code>HA_REFRESH_TOKEN</code> als geheim en gebruik dezelfde token in de app-container.</p>
        <p>③ Gebruik voor toegang buiten je LAN HTTPS via een beveiligde reverse proxy of VPN.</p>
        <p>④ Stel <code>GEMINI_API_KEY</code> in voor cloud-analyse. Zonder sleutel blijft lokale optieherkenning actief.</p>
        <p>⑤ Controleer via <strong>Uitvoeringslog</strong> of iedere scan volledig is geslaagd.</p></div></section>
    </div>
    <section class="card"><div class="card-head"><h3>Gegevensbronstatus</h3>
      ${tag('Directe URL-adapter experimenteel', 'amber')}</div>
      <p class="subtitle">De directe Gaspedaal-zoeklink wordt gelezen voor gestructureerde advertentiegegevens.
        Het parsergedrag moet met een echte live pagina worden gevalideerd. De aanbiederspop-up wordt als meerdere
        advertentiebronnen opgeslagen. Originele dealerpagina’s worden alleen opgehaald van expliciet toegestane
        domeinen; anders blijven deze als doorkliklink beschikbaar.</p></section>`;
}
