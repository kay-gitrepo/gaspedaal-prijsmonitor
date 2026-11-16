/* Opmaakhulpjes. Alles wat uit de API komt gaat door esc() voordat het in HTML belandt. */
const TZ = 'Europe/Amsterdam';

export function fmt(n) {
  return n == null ? '—' : new Intl.NumberFormat('nl-NL').format(n);
}

export function euro(n) {
  if (n == null) return '—';
  return new Intl.NumberFormat('nl-NL', {style: 'currency', currency: 'EUR', maximumFractionDigits: 0}).format(n);
}

export function dt(s) {
  if (!s) return '—';
  const opts = {timeZone: TZ, day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit'};
  return new Date(s).toLocaleString('nl-NL', opts);
}

export function datum(s) {
  if (!s) return '—';
  return new Date(s).toLocaleDateString('nl-NL', {timeZone: TZ, day: 'numeric', month: 'short', year: 'numeric'});
}

const ESCAPES = {'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'};

export function esc(x) {
  return String(x ?? '').replace(/[&<>"']/g, c => ESCAPES[c]);
}

/** "2 uur geleden", "gisteren", "over 3 minuten". */
export function relatief(datumWaarde, nu = new Date()) {
  if (!datumWaarde) return '—';
  const sec = Math.round((new Date(datumWaarde) - nu) / 1000);
  const rtf = new Intl.RelativeTimeFormat('nl-NL', {numeric: 'auto'});
  const stappen = [[60, 'second'], [3600, 'minute'], [86400, 'hour'], [604800, 'day'], [2629800, 'week'],
    [31557600, 'month'], [Infinity, 'year']];
  const deler = {second: 1, minute: 60, hour: 3600, day: 86400, week: 604800, month: 2629800, year: 31557600};
  for (const [grens, eenheid] of stappen) {
    if (Math.abs(sec) < grens) {
      if (eenheid === 'second') return Math.abs(sec) < 45 ? 'zojuist' : rtf.format(Math.round(sec / 60), 'minute');
      return rtf.format(Math.round(sec / deler[eenheid]), eenheid);
    }
  }
  return datum(datumWaarde);
}
