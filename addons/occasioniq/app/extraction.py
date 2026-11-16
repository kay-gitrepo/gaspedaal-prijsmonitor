"""Privacy-aware minimal ad text extraction and conservative deterministic option rules."""
from html import unescape
import re
import hashlib

EMAIL = re.compile(r'\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b', re.I)
PHONE = re.compile(r'(?<!\w)(?:\+31|0031|0)\s*[-(]?\d(?:[ \-()]?\d){7,12}(?!\w)')
TAG = re.compile(r'<[^>]+>')
WHEELS = re.compile(r"\b22\s*(?:[- ]?inch|[\"“”″]|'{2}|′′)\s*(?:lichtmetalen?\s*)?(?:velgen?|wielen?|alloy\s*wheels?|rims?)|(?:velgen?|wielen?|alloy\s*wheels?|rims?)\s*(?:van\s*)?22\s*(?:inch|[\"“”″]|'{2})", re.I)
NEGATION = re.compile(r'\b(?:geen|zonder|ontbreekt|niet\s+(?:aanwezig|gemonteerd|inbegrepen)|no|without|ohne)\b', re.I)
HEDGED = re.compile(r'\b(?:optioneel|tegen\s+meerprijs|voorbereid|voorbereiding|optionally|mogelijk\s+tegen\s+meerprijs)\b', re.I)
# Clauses: a negation or hedge only applies to the clause it is in ("geen trekhaak, wel panoramadak").
CLAUSES = re.compile(r'[\n.;,:•·|]|(?<=[!?])\s+')
QUOTES = str.maketrans({'‘': "'", '’': "'", '´': "'", '`': "'", '“': '"', '”': '"', '„': '"', '″': '"'})
LOCAL_REASON = 'Lokale expliciete advertentievermelding'

# Unambiguous words or phrases that are safe to decide without AI. Loose words such as "velgen" or "wielen"
# deliberately do not appear: they would make "19 inch velgen" count as 22-inch wheels.
DEFAULT_MATCH_TERMS = {
    'towbar': ['trekhaak', 'towbar', 'anhängerkupplung', 'anhaengerkupplung'],
    'air_suspension': ['luchtvering', 'air suspension', 'luftfederung'],
    'pilot_assist': ['pilot assist'],
    'hud': ['head-up display', 'head-updisplay', 'headup display', 'hud'],
    'camera_360': ['360 camera', '360-camera', '360° camera', '360 graden camera', 'surround view camera'],
    'panoramic_roof': ['panoramadak', 'panoramic roof', 'panorama dak', 'panoramaschuifdak'],
    'premium_audio': ['bowers & wilkins', 'bowers and wilkins', 'bowers&wilkins', 'harman kardon', 'harman/kardon'],
    'ventilated_seats': ['stoelventilatie', 'geventileerde stoelen', 'geventileerde voorstoelen', 'ventilated seats'],
    'massage_seats': ['massagefunctie', 'massagestoelen', 'massage seats'],
}


def cleaned_text(title: str, description: str, criteria=None, limit=6500):
    source = f'{title}\n{description or ""}'
    source = re.sub(r'<(script|style|nav|footer|form)\b[^>]*>.*?</\1>', ' ', source, flags=re.I | re.S)
    source = re.sub(r'</(?:p|li|div|br|h[1-6])\s*>', '\n', source, flags=re.I)
    source = unescape(TAG.sub(' ', source))
    source = EMAIL.sub('[e-mail verwijderd]', PHONE.sub('[telefoon verwijderd]', source))
    lines = list(dict.fromkeys(re.sub(r'\s+', ' ', t).strip() for t in source.splitlines()))
    lines = [t for t in lines if len(t) >= 3]
    keywords = set()
    for c in (criteria or []):
        keywords.update(w.lower() for w in c.get('synonyms', []) if len(w) > 2)
        keywords.update(w.lower() for w in c.get('match_terms', []) if len(w) > 2)
    def rank(item):
        low = item.lower()
        return sum(4 for word in keywords if word in low) + (3 if re.search(r'\b(?:uitrusting|opties|inch|velgen|trekhaak)\b', low) else 0)
    # Always retain the title and sort the rest by relevance, not advertising boilerplate.
    ordered = lines[:1] + sorted(lines[1:], key=rank, reverse=True)
    return '\n'.join(ordered)[:limit]


def sha256(s):
    return hashlib.sha256(s.encode('utf-8')).hexdigest()


def term_pattern(term):
    """Whole-word, case-insensitive pattern; spaces and hyphens inside a term are interchangeable."""
    term = term.translate(QUOTES).strip().lower()
    parts = [re.escape(p) for p in re.split(r'[\s\-]+', term) if p]
    if not parts:
        return None
    body = r'[\s\-]*'.join(parts)
    return re.compile(r'(?<!\w)' + body + r'(?!\w)', re.I)


def _classify(fragment, key):
    if HEDGED.search(fragment):
        status = 'UNKNOWN'
    elif NEGATION.search(fragment):
        status = 'ABSENT'
    else:
        status = 'PRESENT'
    return {'criterion_key': key, 'status': status, 'evidence_quote': fragment[:250] if status != 'UNKNOWN' else None,
            'reason_short': LOCAL_REASON, 'confidence': 0.95 if status != 'UNKNOWN' else 0.2}


def local_claims(text, criteria=None):
    """Classify only unambiguous mentions per wish; everything else stays UNKNOWN (left to AI or the user).

    `criteria` are dicts with `key` and `match_terms`. Without criteria the default terms are used.
    The 22-inch regex remains a special case for key `wheels_22`.
    """
    if criteria is None:
        criteria = [{'key': k, 'match_terms': v} for k, v in DEFAULT_MATCH_TERMS.items()] + [{'key': 'wheels_22'}]
    fragments = [f.strip() for f in CLAUSES.split(text.translate(QUOTES)) if f and f.strip()]
    result = {}
    for c in criteria:
        key = c['key']
        if key == 'wheels_22':
            patterns = [WHEELS]
        else:
            patterns = [p for p in (term_pattern(t) for t in c.get('match_terms') or []) if p]
        if not patterns:
            continue
        hit = next((f for f in fragments if any(p.search(f) for p in patterns)), None)
        if hit:
            result[key] = _classify(hit, key)
    return result


def evidence_is_real(quote, content):
    if not quote:
        return False
    normalize = lambda x: re.sub(r'\s+', ' ', x).strip().casefold()
    return normalize(quote) in normalize(content)
