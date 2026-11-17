/* Onderhandelingsdossier (WP-14C): alles over één auto als Markdown, om te kopiëren naar notities of een mail. */
import {datum, dt, euro, fmt} from './format.js';
import {AVAILABILITY, label} from './labels.js';
import {button, dialogHead, openDialog, toast} from './ui.js';
import {openQuestions} from './equipment.js';
import {wishName} from './status.js';

const ORIGIN = {known: 'bekend', estimate: 'schatting', own: 'jouw keuze'};
const md = text => String(text ?? '').replace(/([\\`*_[\]|])/g, '\\$1').replace(/\s+/g, ' ').trim();

function appLink(id) {
  return `${location.origin}/#/auto/${encodeURIComponent(id)}`;
}

function inViewText(x) {
  const days = `${fmt(x.days_tracked)} ${x.days_tracked === 1 ? 'dag' : 'dagen'}`;
  return x.seen_since_start ? `minstens ${days} (stond al te koop toen het volgen begon)` : days;
}

function priceHistory(x) {
  const changes = [...(x.events || [])].reverse().filter(e => e.event_type === 'PRICE_CHANGED');
  if (!changes.length) return [`Niet veranderd sinds de eerste waarneming op ${datum(x.first_seen)} (${euro(x.first_price)}).`];
  const rows = ['| Datum | Van | Naar | Verschil |', '|---|---:|---:|---:|'];
  for (const e of changes) {
    const d = e.new_price - e.previous_price;
    rows.push(`| ${datum(e.created_at)} | ${euro(e.previous_price)} | ${euro(e.new_price)} | ${d < 0 ? '−' : '+'} `
      + `${euro(Math.abs(d))} |`);
  }
  return [`Eerste waarneming ${datum(x.first_seen)}: ${euro(x.first_price)}.`, '', ...rows];
}

function market(x, v) {
  const lines = [];
  if (v.band) {
    const d = Math.round(v.difference / 50) * 50;
    const where = d === 0 ? 'gelijk aan' : `${euro(Math.abs(d))} ${d > 0 ? 'boven' : 'onder'}`;
    lines.push(`Vraagprijs ${euro(x.price_eur)} ligt ${where} wat vergelijkbare auto's vragen (schatting, n = ${v.n}, `
      + `${v.certainty === 'redelijk' ? 'redelijke' : 'lage'} zekerheid).`);
    lines.push(`Band P25–P75: ${euro(v.band.p25)} – ${euro(v.band.p75)}, middenwaarde ${euro(v.band.median)}.`);
  } else {
    lines.push(v.message);
  }
  if (v.budget) lines.push(`Budget: ${euro(v.budget)}.`);
  lines.push('');
  for (const [key, text] of [['opening', 'Openingsbod'], ['target', 'Streefprijs'], ['limit', 'Grens']]) {
    const a = v.amounts[key];
    lines.push(`- ${text}: ${a.value == null ? 'geen voorstel' : `${euro(a.value)} (${ORIGIN[a.source] || 'voorstel'})`}`);
  }
  if (v.note) lines.push('', v.note);
  return lines;
}

function comparables(v) {
  if (!v.comparables.length) return ['Geen vergelijkbare auto\'s in dezelfde zoekopdracht.'];
  const rows = [`Vergelijkbaar op: ${v.level_reason}.`, '',
    `| Auto | Vraagprijs |${v.corrected ? ' Gecorrigeerd voor km |' : ''} Km | Bouwjaar | Match | Verschil |`,
    `|---|---:|${v.corrected ? '---:|' : ''}---:|---:|---:|---|`];
  for (const c of v.comparables) {
    rows.push(`| [${md(c.title)}](${appLink(c.id)}) | ${euro(c.price_eur)} |${v.corrected
      ? ` ${c.corrected_price == null ? '—' : euro(c.corrected_price)} |` : ''} ${fmt(c.kilometers)} | ${c.year || '—'} | `
      + `${fmt(c.score_total)}% | ${md(c.differences.join(', ') || 'gelijk')} |`);
  }
  return rows;
}

/** Het dossier als Markdown-tekst. `x` = autodetail, `v` = waardering. */
export function dossierMarkdown(x, v) {
  const sources = (x.sources || []).filter(o => o.source_url || o.click_url)
    .map(o => `[${md(o.site)}${o.price_eur ? ` (${euro(o.price_eur)})` : ''}](${o.source_url || o.click_url})`);
  const claims = x.claims || [];
  const missing = claims.filter(c => c.status === 'ABSENT').map(c => wishName(c.label));
  const present = claims.filter(c => c.status === 'PRESENT').map(c => wishName(c.label));
  const questions = openQuestions(claims).map((c, i) => `${i + 1}. Heeft deze auto ${wishName(c.label)}? Kunt u dat `
    + 'bevestigen met een foto of de originele uitrustingslijst?');
  const status = [label(AVAILABILITY, x.availability), x.eligibility ? `match ${fmt(x.score_total)}% bevestigd, tot `
    + `${fmt(x.score_potential)}% mogelijk` : ''].filter(Boolean).join(' · ');
  const lines = [
    `# ${md(x.title)}`, '',
    `Dossier van ${datum(new Date().toISOString())}, gemaakt met OccasionIQ. Alle bedragen zijn vraagprijzen, geen `
      + 'verkoopprijzen.', '',
    '## Kerngegevens', '',
    `- Vraagprijs: ${euro(x.price_eur)}${x.price_change_total ? ` (${x.price_change_total < 0 ? '−' : '+'} `
      + `${euro(Math.abs(x.price_change_total))} sinds eerste prijs)` : ''}`,
    `- Bouwjaar: ${x.year || 'onbekend'} · Kilometerstand: ${x.kilometers != null ? `${fmt(x.kilometers)} km` : 'onbekend'}`,
    `- Uitvoering: ${md(x.trim || 'onbekend')} · Verkoper: ${md(x.seller || 'onbekend')}`,
    `- In beeld: ${inViewText(x)}`,
    `- Status: ${status}${x.score_profile_title ? ` (wensen van ${md(x.score_profile_title)})` : ''}`,
    `- Uitrusting bevestigd: ${present.join(', ') || 'niets'}${missing.length ? ` · ontbreekt: ${missing.join(', ')}` : ''}`,
    `- Advertentie: ${sources.join(' · ') || (x.url ? `<${x.url}>` : 'geen link')}`,
    `- In OccasionIQ: <${appLink(x.id)}>`, '',
    '## Prijsgeschiedenis', '', ...priceHistory(x), '',
    '## Marktpositie en bedragen', '', ...market(x, v), '',
    '## Argumenten', '', ...(v.arguments.length ? v.arguments.map(a => `- ${md(a.text)} _(${md(a.source)})_`)
      : ['Geen.']), '',
    '## Vergelijkbare auto\'s', '', ...comparables(v), '',
    '## Open vragen aan de verkoper', '', ...(questions.length ? questions
      : ['Alle wensen zijn bevestigd of uitgesloten.']), '',
    '## Eigen notities', '', ...((x.notes || []).length ? x.notes.map(n => `- ${dt(n.created_at)}`
      + `${n.offer_eur ? ` · bod ${euro(n.offer_eur)}` : ''}: ${md(n.note)}`) : ['Nog geen notities.']), '',
    '_Gebaseerd op vraagprijzen van auto\'s die te koop staan. Werkelijke verkoopprijzen zijn niet bekend. Een '
      + 'verdwenen advertentie is geen bewijs van verkoop._',
  ];
  return lines.join('\n');
}

async function copy(text) {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    return false;
  }
}

/** Kopieer het dossier; lukt dat niet (bijvoorbeeld via http op het thuisnetwerk), toon het om zelf te kopiëren. */
export async function copyDossier(x, v) {
  const text = dossierMarkdown(x, v);
  if (await copy(text)) {
    toast('Dossier gekopieerd (Markdown)');
    return;
  }
  openDialog(dialogHead('Dossier', 'Kopiëren lukte niet automatisch. Selecteer de tekst en kopieer hem zelf.')
    + `<section class="card stack"><label class="sr-only" for="dossier-text">Dossier</label>
      <textarea id="dossier-text" class="input questions dossier" readonly rows="18"></textarea>
      <div class="row">${button('Sluiten', {attrs: {'data-close': true}})}</div></section>`);
  const area = document.getElementById('dossier-text');
  area.value = text;
  area.focus();
  area.select();
}

