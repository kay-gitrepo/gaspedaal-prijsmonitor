/* Uitrusting van één auto: bevestigd, ontbreekt, onzeker; corrigeren; vragen aan de verkoper. */
import {api} from './api.js';
import {esc, fmt} from './format.js';
import {CLAIM_SOURCE, GROUP, label} from './labels.js';
import {badge, button, icon, segment, toast} from './ui.js';
import {wishName} from './status.js';

const OPTIONS = [['PRESENT', 'Aanwezig'], ['ABSENT', 'Afwezig'], ['UNKNOWN', 'Onbekend']];

export function certainty(confidence) {
  if (confidence >= 0.85) return 'zeker';
  if (confidence >= 0.6) return 'waarschijnlijk';
  return 'onzeker';
}

function origin(c) {
  if (c.not_assessed) return 'Nog niet beoordeeld';
  return label(CLAIM_SOURCE, c.source, 'Uit de advertentie');
}

function claimRow(id, c) {
  const manual = c.source === 'MANUAL_OVERRIDE';
  const quote = c.evidence ? `<p><mark>“${esc(c.evidence)}”</mark></p>` : '';
  const how = manual ? 'Door jou bevestigd' : `${origin(c)}${c.not_assessed ? '' : ` · ${certainty(c.confidence)}`}`;
  const value = OPTIONS.some(([v]) => v === c.status) ? c.status : 'UNKNOWN';
  const undo = manual ? button('Terug naar automatisch', {variant: 'text', size: 's', icon: 'refresh',
    action: 'undo-review', data: {id, key: c.criterion_key}}) : '';
  const note = manual ? `<form class="claim-note" data-submit="review-note" data-id="${esc(id)}"
      data-key="${esc(c.criterion_key)}" data-status="${esc(c.status)}">
      <input class="input" name="evidence" maxlength="400" value="${esc(c.evidence || '')}"
        aria-label="Notitie bij je oordeel over ${esc(c.label)}"
        placeholder="Bron, bijvoorbeeld: dealer bevestigd per mail op 14-11">
      ${button('Notitie opslaan', {type: 'submit', size: 's'})}</form>` : '';
  return `<div class="claim-row"><div><strong>${esc(c.label)}</strong>
    ${badge(label(GROUP, c.group_name), c.group_name === 'MUST_HAVE' ? 'info' : 'neutral')}${quote}
    <p>${esc(how)}</p></div>
    <div class="claim-edit">${segment(`claim-${c.criterion_key}`, OPTIONS, manual ? value : '',
      {label: `Jouw oordeel over ${c.label}`, data: {change: 'claim-status', id, key: c.criterion_key}})}${undo}</div>
    ${note}</div>`;
}

/** Drie groepen: Bevestigd · Ontbreekt · Onzeker. */
export function equipmentHtml(id, claims) {
  if (!claims.length) return '<p class="muted">Er zijn nog geen wensen ingesteld.</p>';
  const groups = [
    ['Bevestigd', 'check-circle', claims.filter(c => c.status === 'PRESENT')],
    ['Ontbreekt', 'x-circle', claims.filter(c => c.status === 'ABSENT')],
    ['Onzeker', 'help', claims.filter(c => c.status !== 'PRESENT' && c.status !== 'ABSENT')],
  ];
  return groups.filter(([, , items]) => items.length).map(([title, ic, items]) => `<section class="claim-group">
    <h4>${icon(ic)}${title} (${fmt(items.length)})</h4>${items.map(c => claimRow(id, c)).join('')}</section>`).join('')
    + '<p class="muted small">Kies Aanwezig, Afwezig of Onbekend om het oordeel zelf vast te leggen. '
    + 'Je eigen oordeel blijft staan bij volgende controles.</p>';
}

/** Onzekere wensen, must-haves eerst, daarna op gewicht. */
export function openQuestions(claims) {
  return claims.filter(c => c.status !== 'PRESENT' && c.status !== 'ABSENT')
    .sort((a, b) => (a.group_name === b.group_name ? b.weight - a.weight : a.group_name === 'MUST_HAVE' ? -1 : 1));
}

export function questionText(x, claims) {
  const qs = openQuestions(claims).map((c, i) => `${i + 1}. Heeft deze auto ${wishName(c.label)}? `
    + 'Kunt u dat bevestigen met een foto of de originele uitrustingslijst?');
  const car = [x.title, x.year, x.kilometers != null ? `${fmt(x.kilometers)} km` : null].filter(Boolean).join(', ');
  return `Goedendag,\n\nIk heb interesse in de ${car} die u te koop aanbiedt. Ik heb nog een paar vragen over de `
    + `uitrusting:\n\n${qs.join('\n')}\n\nAlvast bedankt voor uw reactie.\n\nMet vriendelijke groet,`;
}

export function questionsHtml(x, claims) {
  const open = openQuestions(claims);
  if (!open.length) return '<p class="muted">Alle wensen zijn bevestigd of uitgesloten.</p>';
  return `<ol class="steps">${open.map(c => `<li>Heeft deze auto ${esc(wishName(c.label))}? Kunt u dat bevestigen met
    een foto of de originele uitrustingslijst?</li>`).join('')}</ol>
    <div class="row">${button('Kopieer alle vragen', {variant: 'primary', icon: 'copy', action: 'copy-questions'})}</div>
    <label class="sr-only" for="questions-text">Bericht aan de verkoper</label>
    <textarea id="questions-text" class="input questions" readonly rows="8">${esc(questionText(x, claims))}</textarea>`;
}

async function copy(text) {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    const area = document.getElementById('questions-text');
    if (!area) return false;
    area.focus();
    area.select();
    try {
      return document.execCommand('copy');
    } catch {
      return false;
    }
  }
}

/** Acties; `reload(id)` tekent de auto opnieuw zonder paginawissel. */
export function equipmentActions(reload) {
  return {
    actions: {
      async 'undo-review'(el) {
        await api(`/listings/${encodeURIComponent(el.dataset.id)}/review/${encodeURIComponent(el.dataset.key)}`,
          {method: 'DELETE'});
        toast('Terug naar automatisch. Wordt bij de volgende controle opnieuw beoordeeld.');
        await reload(el.dataset.id);
      },
      async 'copy-questions'() {
        const text = document.getElementById('questions-text')?.value || '';
        toast(await copy(text) ? 'Vragen gekopieerd' : 'Kopiëren lukte niet; selecteer de tekst en kopieer zelf.',
          'info');
      },
    },
    changes: {
      async 'claim-status'(el) {
        const body = {criterion_key: el.dataset.key, status: el.value, evidence: null};
        await api(`/listings/${encodeURIComponent(el.dataset.id)}/review`, {method: 'POST', body});
        toast('Oordeel opgeslagen');
        await reload(el.dataset.id);
      },
    },
    submits: {
      async 'review-note'(form) {
        const evidence = new FormData(form).get('evidence') || null;
        const body = {criterion_key: form.dataset.key, status: form.dataset.status, evidence};
        await api(`/listings/${encodeURIComponent(form.dataset.id)}/review`, {method: 'POST', body});
        toast('Notitie opgeslagen');
        await reload(form.dataset.id);
      },
    },
  };
}
