import {api} from '../api.js';
import {esc} from '../format.js';
import {$, button, card, notice, pageHead, skeletons, toast} from '../ui.js';

let criteria = [];

export function skeleton() {
  return skeletons.head() + skeletons.rows(8);
}

function row(x) {
  const k = esc(x.key);
  const groups = [['MUST_HAVE', 'Must-have'], ['NICE_TO_HAVE', 'Nice-to-have']]
    .map(([v, l]) => `<option value="${v}"${x.group_name === v ? ' selected' : ''}>${l}</option>`).join('');
  const weights = [1, 2, 3, 4, 5].map(w => `<option value="${w}"${x.weight === w ? ' selected' : ''}>${w}</option>`).join('');
  return `<div class="list-item criterion"><div><strong>${esc(x.label)}</strong><p>${esc(x.description)}</p></div>
    <select class="input" data-criterion-group="${k}" aria-label="Soort wens voor ${esc(x.label)}">${groups}</select>
    <select class="input" data-criterion-weight="${k}" aria-label="Belang van ${esc(x.label)}">${weights}</select>
    ${button('Opslaan', {variant: 'secondary', size: 's', action: 'save-criterion', data: {key: x.key}})}</div>`;
}

export async function render() {
  const data = await api('/criteria');
  criteria = data.items;
  $('#content').innerHTML = pageHead('Mijn wensen',
    'Bepaal welke uitrusting je echt wilt (must-have) en wat extra punten oplevert (nice-to-have).')
    + notice('Staat een optie niet in de advertentie, dan geldt die als <strong>onbekend</strong>, niet als afwezig. '
      + 'De match telt must-haves voor 70% en nice-to-haves voor 30%. Een must-have die aantoonbaar ontbreekt, laat de auto '
      + 'altijd afvallen.')
    + card('Wensen', `<div class="list">${criteria.map(row).join('')}</div>`, {sub: 'Belang van 1 (laag) tot 5 (hoog)'});
}

export const actions = {
  async 'save-criterion'(el) {
    const c = criteria.find(x => x.key === el.dataset.key);
    const group = $(`[data-criterion-group="${CSS.escape(c.key)}"]`).value;
    const weight = Number($(`[data-criterion-weight="${CSS.escape(c.key)}"]`).value);
    const body = {label: c.label, group_name: group, weight, description: c.description, synonyms: c.synonyms,
      enabled: !!c.enabled};
    await api('/criteria/' + encodeURIComponent(c.key), {method: 'PUT', body});
    toast('Wens opgeslagen. De beoordeling wordt bij de volgende controle bijgewerkt.');
    await render();
  },
};
