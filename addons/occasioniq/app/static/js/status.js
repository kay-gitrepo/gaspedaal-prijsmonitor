/* Status en match van een auto: één plek voor de woorden en de balk. */
import {esc, fmt} from './format.js';
import {badge, bar} from './ui.js';

export function hasText(x) {
  if (x.has_text !== undefined) return Boolean(x.has_text);
  return Boolean((x.description || '').trim());
}

/** "Trekhaak" → "trekhaak", maar "Pilot Assist" blijft staan. */
export function wishName(labelText) {
  const t = String(labelText || '');
  return /[A-Z]/.test(t.slice(1)) ? t : t.charAt(0).toLowerCase() + t.slice(1);
}

function list(names) {
  const items = (names || []).map(wishName);
  if (items.length <= 2) return items.join(' en ');
  return `${items.slice(0, 2).join(', ')} en ${items.length - 2} meer`;
}

/** Statuschip met reden, bijvoorbeeld "Nog te controleren: trekhaak". */
export function statusChip(x) {
  const r = x.status_reason || {};
  if (x.eligibility === 'REJECTED') {
    return badge(r.absent?.length ? `Valt af: ${list(r.absent)} ontbreekt` : 'Valt af', 'danger');
  }
  if (!hasText(x) && x.eligibility !== 'MATCH') return badge('Geen advertentietekst', 'neutral');
  if (x.eligibility === 'MATCH') return badge('Voldoet', 'success');
  if (!x.analyzed_hash && x.analyzed_hash !== undefined) return badge('Nog niet beoordeeld', 'neutral');
  if (x.eligibility === 'REVIEW') {
    return badge(r.conflict?.length ? `Tegenstrijdig: ${list(r.conflict)}` : 'Tegenstrijdig', 'warning');
  }
  return badge(r.unknown?.length ? `Nog te controleren: ${list(r.unknown)}` : 'Nog te controleren', 'warning');
}

/** Compatibel met eerdere aanroepen. */
export const eligibilityBadge = statusChip;

/** "75% bevestigd · tot 100% mogelijk" met één balk: dicht = bevestigd, gearceerd = nog mogelijk. */
export function matchCell(x, {detail = true} = {}) {
  const confirmed = Number(x.score_total) || 0;
  const potential = Math.max(confirmed, Number(x.score_potential ?? confirmed) || 0);
  const text = `${fmt(confirmed)}% bevestigd · tot ${fmt(potential)}% mogelijk`;
  const musts = detail && x.must_count ? `<span class="sub">Must-haves ${fmt(x.must_present)} van ${fmt(x.must_count)}
    bevestigd</span>` : '';
  return `<div class="match"><span class="match-text">${esc(text)}</span>
    ${bar([[confirmed, 'fill'], [potential - confirmed, 'fill-potential']], text)}${musts}</div>`;
}
