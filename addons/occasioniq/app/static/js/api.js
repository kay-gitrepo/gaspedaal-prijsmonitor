/* fetch-wrapper: sessiecookie + CSRF-header voor elke schrijfactie. */
let csrf = null;

export function setCsrf(token) {
  csrf = token;
}

export class ApiError extends Error {
  constructor(message, status, detail) {
    super(message);
    this.status = status;
    this.detail = detail;
  }
}

export async function api(path, {method = 'GET', body, headers = {}} = {}) {
  const opt = {method, credentials: 'same-origin', headers: {...headers}};
  if (body !== undefined) {
    opt.headers['Content-Type'] = 'application/json';
    opt.body = JSON.stringify(body);
  }
  if (!['GET', 'HEAD'].includes(method) && csrf) opt.headers['X-CSRF-Token'] = csrf;
  const r = await fetch('/api/v1' + path, opt);
  let data;
  try {
    data = await r.json();
  } catch {
    data = {detail: r.statusText};
  }
  if (!r.ok) {
    const d = data.detail;
    const message = typeof d === 'object' && d !== null ? (d.message || d.code || JSON.stringify(d)) : (d || r.statusText);
    throw new ApiError(message, r.status, d);
  }
  return data;
}
