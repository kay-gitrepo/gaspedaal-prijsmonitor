/* fetch-wrapper: sessiecookie + CSRF-header voor elke schrijfactie. Foutcodes worden nooit rauw getoond. */
let csrf = null;

export function setCsrf(token) {
  csrf = token;
}

const CODES = {
  RUN_ALREADY_ACTIVE: 'Er loopt al een controle.',
  IDEMPOTENCY_KEY_REUSED: 'Deze aanvraag is al eerder met andere gegevens gedaan.',
};

export class ApiError extends Error {
  constructor(message, status, detail) {
    super(message);
    this.status = status;
    this.detail = detail;
  }
}

function messageFor(status, d) {
  if (Array.isArray(d)) return 'Controleer de ingevulde gegevens.';
  if (d && typeof d === 'object') return d.message || CODES[d.code] || 'Er ging iets mis.';
  if (typeof d === 'string' && d) return d;
  if (status === 401) return 'Je bent niet (meer) ingelogd.';
  if (status >= 500) return 'Er ging iets mis op de server.';
  return 'Er ging iets mis.';
}

export async function api(path, {method = 'GET', body, headers = {}} = {}) {
  const opt = {method, credentials: 'same-origin', headers: {...headers}};
  if (body !== undefined) {
    opt.headers['Content-Type'] = 'application/json';
    opt.body = JSON.stringify(body);
  }
  if (!['GET', 'HEAD'].includes(method) && csrf) opt.headers['X-CSRF-Token'] = csrf;
  let r;
  try {
    r = await fetch('/api/v1' + path, opt);
  } catch {
    throw new ApiError('De server is niet bereikbaar.', 0, null);
  }
  let data;
  try {
    data = await r.json();
  } catch {
    data = {detail: null};
  }
  if (!r.ok) throw new ApiError(messageFor(r.status, data.detail), r.status, data.detail);
  return data;
}
