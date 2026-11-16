import {api} from '../api.js';
import {esc, fmt, dt} from '../format.js';
import {$, head, modal, modalHead, statusTag, table} from '../ui.js';

function row(x) {
  const error = x.error ? `<br><span class="micro error-text">${esc(x.error)}</span>` : '';
  return `<tr><td>${dt(x.created_at)}</td><td>${esc(x.title)}</td><td>${statusTag(x.decision)}${error}</td>
    <td>${fmt(x.tokens_in)} / ${fmt(x.tokens_out)}</td><td class="micro">${esc(x.model_id)}</td>
    <td><a class="btn btn-sm" href="#/ai-analyse/${encodeURIComponent(x.id)}">Inspecteer</a></td></tr>`;
}

export async function render() {
  const data = await api('/integrations');
  const headers = ['Tijdstip', 'Auto', 'Beslissing', 'Tokens in / uit', 'Model', 'Details'];
  $('#content').innerHTML = head('AI-VERANTWOORDING', 'Gemini-integratielog',
    'Bekijk exact welke gesaniteerde advertentietekst is verzonden, het modelantwoord, tokenverbruik en fouten.') + `
    <div class="notice">ⓘ&nbsp; Alleen daadwerkelijke Gemini-verzoeken hebben een verzonden payload.
      Lokale classificaties en overgeslagen aanvragen worden apart geregistreerd.</div>
    <section class="card"><div class="card-head"><h3>Classificaties en aanroepen</h3><span class="micro">Laatste 200</span>
      </div>${table(headers, data.items.map(row))}</section>`;
}

export async function showIntegration(id) {
  const x = await api('/integrations/' + encodeURIComponent(id));
  const request = x.request_json ? JSON.stringify(x.request_json, null, 2)
    : 'Geen Gemini-aanroep: lokaal afgehandeld of overgeslagen.';
  const parsed = x.parsed_json ? JSON.stringify(x.parsed_json, null, 2) : 'Geen Gemini-resultaat';
  modal(modalHead('Gemini-integratie', `${x.listing_id} · ${dt(x.created_at)}`) + `
    <div class="inline-actions detail-actions">${statusTag(x.decision)}<span>Model: ${esc(x.model_id)}</span>
      <span>Tokens: ${fmt(x.tokens_in)} / ${fmt(x.tokens_out)}</span><span>${fmt(x.duration_ms)} ms</span></div>
    ${x.error ? `<div class="notice warn">${esc(x.error)}</div>` : ''}
    <section class="card"><h3>Exact verzonden, gesanitiseerde payload</h3><pre class="json">${esc(request)}</pre></section>
    <section class="card"><h3>Ruw modelantwoord</h3><pre class="json">${esc(x.response_json || 'Geen antwoord')}</pre>
    </section><section class="card"><h3>Gevalideerde resultaten</h3><pre class="json">${esc(parsed)}</pre></section>`);
}
