/* Woordenlijst: interne codes → zichtbare Nederlandse tekst en kleurvariant. Nergens anders vertalen. */

export const RUN_STATE = {
  COMPLETE: ['Geslaagd', 'success'],
  PARTIAL: ['Gedeeltelijk', 'warning'],
  FAILED: ['Mislukt', 'danger'],
  RUNNING: ['Bezig', 'info'],
  QUEUED: ['Wacht', 'neutral'],
};

export const TRIGGER = {
  MANUAL_UI: 'Handmatig',
  HOME_ASSISTANT: 'Home Assistant',
  REANALYSIS: 'Herbeoordeling',
};

export const AVAILABILITY = {
  ACTIVE: ['Te koop', 'success'],
  MISSING_UNCONFIRMED: ['Niet meer gezien', 'warning'],
  OFF_MARKET: ['Uit het aanbod', 'neutral'],
  OUT_OF_SCOPE: ['Buiten huidige filters', 'neutral'],
};

export const ELIGIBILITY = {
  MATCH: ['Voldoet', 'success'],
  UNVERIFIED: ['Nog te controleren', 'warning'],
  REJECTED: ['Valt af', 'danger'],
  REVIEW: ['Tegenstrijdig', 'warning'],
};

export const CLAIM = {
  PRESENT: ['Aanwezig', 'success'],
  ABSENT: ['Afwezig', 'danger'],
  UNKNOWN: ['Onbekend', 'neutral'],
  CONFLICT: ['Tegenstrijdig', 'warning'],
};

export const CLAIM_SOURCE = {
  AD_TEXT: 'Uit de advertentie',
  MANUAL_OVERRIDE: 'Door jou bevestigd',
  LOCAL_RULE: 'Zonder AI herkend',
  GEMINI: 'AI-beoordeling',
  NOT_MENTIONED: 'Niet genoemd in de advertentie',
};

export const DECISION = {
  SUCCESS: ['AI-beoordeling', 'success'],
  ERROR: ['Mislukt', 'danger'],
  CACHE_HIT: ['Ongewijzigd', 'neutral'],
  LOCAL_ONLY: ['Zonder AI herkend', 'neutral'],
  SKIPPED_NO_KEY: ['AI staat uit', 'warning'],
  SKIPPED_BUDGET: ['Wacht op volgende controle', 'warning'],
};

export const EVENT = {
  FIRST_SEEN: 'Eerste keer gezien',
  PRICE_CHANGED: 'Prijs gewijzigd',
  MISSING_UNCONFIRMED: 'Niet meer gezien',
  OFF_MARKET: 'Uit het aanbod',
  REAPPEARED: 'Weer terug',
};

export const LEVEL = {INFO: 'Info', WARN: 'Waarschuwing', ERROR: 'Fout'};

export const GROUP = {MUST_HAVE: 'Must-have', NICE_TO_HAVE: 'Nice-to-have'};

/** Leesbare tekst voor een code; onbekende codes worden nooit rauw getoond. */
export function label(map, code, fallback = 'Onbekend') {
  const value = map[code];
  if (value === undefined) return fallback;
  return Array.isArray(value) ? value[0] : value;
}
