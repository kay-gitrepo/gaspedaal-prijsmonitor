/* Statuschip van een auto op basis van geschiktheid en beschikbare advertentietekst. */
import {ELIGIBILITY} from './labels.js';
import {badge, statusBadge} from './ui.js';

export function hasText(x) {
  if (x.has_text !== undefined) return Boolean(x.has_text);
  return Boolean((x.description || '').trim());
}

/** "Geen advertentietekst" vervangt "Nog te controleren" als er niets te beoordelen valt. */
export function eligibilityBadge(x) {
  if (!hasText(x) && x.eligibility === 'UNVERIFIED') return badge('Geen advertentietekst', 'neutral');
  return statusBadge(ELIGIBILITY, x.eligibility);
}
