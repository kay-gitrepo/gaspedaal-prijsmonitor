"""Privacy-aware minimal ad text extraction and conservative deterministic wheel/towbar rules."""
from html import unescape
import re
import hashlib

EMAIL = re.compile(r'\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b', re.I)
PHONE = re.compile(r'(?<!\w)(?:\+31|0031|0)\s*[-(]?\d(?:[ \-()]?\d){7,12}(?!\w)')
TAG = re.compile(r'<[^>]+>')
WHEELS = re.compile(r"\b22\s*(?:[- ]?inch|[\"“”″]|'{2}|′′)\s*(?:lichtmetalen?\s*)?(?:velgen?|wielen?|alloy\s*wheels?|rims?)|(?:velgen?|wielen?|alloy\s*wheels?|rims?)\s*(?:van\s*)?22\s*(?:inch|[\"“”″]|'{2})", re.I)
TOWBAR = re.compile(r'\b(?:trekhaak|towbar|anh[aä]ngerkupplung)\b', re.I)
NEGATION = re.compile(r'\b(?:geen|zonder|ontbreekt|niet\s+(?:aanwezig|gemonteerd|inbegrepen)|no|without|ohne)\b', re.I)
HEDGED = re.compile(r'\b(?:optioneel|tegen\s+meerprijs|voorbereid|voorbereiding|optionally|mogelijk\s+tegen\s+meerprijs)\b', re.I)


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
    def rank(item):
        low = item.lower()
        return sum(4 for word in keywords if word in low) + (3 if re.search(r'\b(?:uitrusting|opties|inch|velgen|trekhaak)\b', low) else 0)
    # Always retain the title and sort the rest by relevance, not advertising boilerplate.
    ordered = lines[:1] + sorted(lines[1:], key=rank, reverse=True)
    return '\n'.join(ordered)[:limit]


def sha256(s):
    return hashlib.sha256(s.encode('utf-8')).hexdigest()


def local_claims(text):
    """Only classify unambiguous wheel/towbar mentions; leave everything else UNKNOWN."""
    result = {}
    for key, regex in [('wheels_22', WHEELS), ('towbar', TOWBAR)]:
        fragments = re.split(r'[\n.;]|(?<=[!?])\s+', text)
        hit = next((f.strip() for f in fragments if regex.search(f)), None)
        if not hit:
            continue
        if HEDGED.search(hit):
            status = 'UNKNOWN'
        elif NEGATION.search(hit):
            status = 'ABSENT'
        else:
            status = 'PRESENT'
        result[key] = {'criterion_key': key, 'status': status, 'evidence_quote': hit[:250] if status != 'UNKNOWN' else None,
                       'reason_short': 'Lokale expliciete advertentievermelding', 'confidence': 0.95 if status != 'UNKNOWN' else 0.2}
    return result


def evidence_is_real(quote, content):
    if not quote:
        return False
    normalize = lambda x: re.sub(r'\s+', ' ', x).strip().casefold()
    return normalize(quote) in normalize(content)
