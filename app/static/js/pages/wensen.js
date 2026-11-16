import {api} from '../api.js';
import {esc} from '../format.js';
import {$, head, toast} from '../ui.js';

let criteria = [];

function row(x) {
  const opt = (v, l) => `<option value="${v}" ${x.group_name === v ? 'selected' : ''}>${l}</option>`;
  return `<div class="option-row"><div><strong>${esc(x.label)}</strong><small>${esc(x.description)}</small></div>
    <select data-criterion-group="${esc(x.key)}">${opt('MUST_HAVE', 'Must-have')}${opt('NICE_TO_HAVE', 'Nice-to-have')}
    </select><input type="number" min="1" max="5" value="${esc(x.weight)}" data-criterion-weight="${esc(x.key)}"
    aria-label="Gewicht"><button class="btn btn-sm btn-secondary" data-action="save-criterion"
    data-key="${esc(x.key)}">Opslaan</button></div>`;
}

export async function render() {
  const data = await api('/criteria');
  criteria = data.items;
  $('#content').innerHTML = head('UITRUSTING', 'Mijn opties',
    'Bepaal welke accessoires verplicht zijn en welke extra punten opleveren. '
    + 'Wijzigingen worden bij de volgende refresh verwerkt.') + `
    <div class="notice">✦&nbsp; Een ontbrekende vermelding betekent <strong>onbekend</strong>, niet automatisch afwezig.
      De score is 70% must-haves en 30% nice-to-haves; een expliciet ontbrekende must-have leidt altijd tot afwijzing.</div>
    <section class="card"><div class="card-head"><h3>Optieprofiel</h3><span class="micro">Gewicht 1–5 per optie</span></div>
      ${data.items.map(row).join('')}</section>`;
}

export const actions = {
  async 'save-criterion'(el) {
    const c = criteria.find(x => x.key === el.dataset.key);
    const group = $(`[data-criterion-group="${CSS.escape(c.key)}"]`).value;
    const weight = Number($(`[data-criterion-weight="${CSS.escape(c.key)}"]`).value);
    const body = {label: c.label, group_name: group, weight, description: c.description, synonyms: c.synonyms,
      enabled: !!c.enabled};
    await api('/criteria/' + encodeURIComponent(c.key), {method: 'PUT', body});
    toast('Optie gewijzigd. Nieuwe beoordeling bij volgende refresh.');
    await render();
  },
};
