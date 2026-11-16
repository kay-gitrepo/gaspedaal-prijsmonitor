/* Gedeelde context: de gekozen zoekopdracht in de bovenbalk (bewaard in localStorage). */
import {api} from './api.js';
import {esc} from './format.js';
import {$} from './ui.js';

const KEY = 'occasioniq.profile';
let profiles = [];
let onChange = () => {};

function load() {
  try {
    return localStorage.getItem(KEY) || '';
  } catch {
    return '';
  }
}

function save(value) {
  try {
    localStorage.setItem(KEY, value);
  } catch {
    /* privévenster of geblokkeerde opslag: keuze geldt alleen voor deze sessie */
  }
}

let selected = load();

/** Gekozen zoekopdracht-ID, of '' voor alle zoekopdrachten. */
export function profileId() {
  return profiles.some(p => p.id === selected) ? selected : (profiles.length === 1 ? profiles[0].id : '');
}

export function currentProfile() {
  return profiles.find(p => p.id === profileId()) || null;
}

export function allProfiles() {
  return profiles;
}

/** Querystring-deel voor API-aanroepen, bijvoorbeeld `?profile_id=sp_1`. */
export function profileQuery(prefix = '?') {
  const id = profileId();
  return id ? `${prefix}profile_id=${encodeURIComponent(id)}` : '';
}

export function onProfileChange(fn) {
  onChange = fn;
}

export async function refreshProfiles() {
  try {
    profiles = (await api('/profiles')).items;
  } catch {
    profiles = [];
  }
  const select = $('#profile-select');
  const current = profileId();
  const options = profiles.map(p => `<option value="${esc(p.id)}"${p.id === current ? ' selected' : ''}>
    ${esc(p.title)}${p.enabled ? '' : ' (gepauzeerd)'}</option>`);
  if (profiles.length !== 1) options.unshift(`<option value=""${current ? '' : ' selected'}>Alle zoekopdrachten</option>`);
  if (!profiles.length) options.splice(0, 1, '<option value="">Nog geen zoekopdracht</option>');
  select.innerHTML = options.join('');
  select.disabled = profiles.length < 2;
  return profiles;
}

export function selectProfile(value) {
  selected = value;
  save(value);
  onChange(value);
}
