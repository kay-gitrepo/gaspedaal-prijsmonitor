/* Hash-router: elk scherm een eigen adres, zodat herladen en de terugknop werken. */
export const PAGES = ['overzicht', 'aanbod', 'auto', 'wensen', 'zoekopdrachten', 'controles', 'ai-analyse',
  'instellingen'];

export function parseHash(hash = location.hash) {
  const raw = hash.replace(/^#\/?/, '');
  const [path, query = ''] = raw.split('?');
  const parts = path.split('/').filter(Boolean).map(decodeURIComponent);
  return {page: parts[0] || '', id: parts[1] || null, params: new URLSearchParams(query)};
}

export function href(page, id = null, params = null) {
  let out = `#/${page}`;
  if (id) out += '/' + encodeURIComponent(id);
  const q = params ? new URLSearchParams(params).toString() : '';
  return q ? `${out}?${q}` : out;
}

export function go(page, id = null, params = null) {
  location.hash = href(page, id, params);
}

let lastList = '#/aanbod';

/** Het adres van de laatst bekeken lijst, voor "Terug naar de lijst". */
export function lastListHash() {
  return lastList;
}

export function setLastList(hash) {
  lastList = hash || '#/aanbod';
}

export function replace(page, id = null, params = null) {
  history.replaceState(null, '', href(page, id, params));
  window.dispatchEvent(new HashChangeEvent('hashchange'));
}
