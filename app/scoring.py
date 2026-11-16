"""Deterministic score: 70% must-haves and 30% nice-to-haves; no LLM arithmetic."""
from statistics import median

VALID_STATUSES = {'PRESENT', 'ABSENT', 'UNKNOWN', 'CONFLICT'}


def calculate(criteria, claims):
    active = [c for c in criteria if c.get('enabled', 1)]
    by_key = {c['criterion_key']: c['status'] for c in claims} if isinstance(claims, list) else claims
    groups = {}
    for group in ('MUST_HAVE', 'NICE_TO_HAVE'):
        items = [c for c in active if c['group_name'] == group]
        weight = sum(c['weight'] for c in items)
        points = sum(c['weight'] for c in items if by_key.get(c['key']) == 'PRESENT')
        groups[group] = {'percentage': round(points / weight * 100, 1) if weight else 100.0,
                         'present': sum(by_key.get(c['key']) == 'PRESENT' for c in items),
                         'count': len(items)}
    must, nice = groups['MUST_HAVE'], groups['NICE_TO_HAVE']
    coefficients = [(0.7, must)] if must['count'] else []
    if nice['count']:
        coefficients.append((0.3, nice))
    total_coeff = sum(coeff for coeff, _ in coefficients)
    score = round(sum(coeff * group['percentage'] for coeff, group in coefficients) / total_coeff, 1) if total_coeff else 100.0
    must_items = [c for c in active if c['group_name'] == 'MUST_HAVE']
    if any(by_key.get(c['key']) == 'ABSENT' for c in must_items):
        eligibility = 'REJECTED'
    elif any(by_key.get(c['key']) != 'PRESENT' for c in must_items):
        eligibility = 'UNVERIFIED'
    elif any(by_key.get(c['key']) == 'CONFLICT' for c in active):
        eligibility = 'REVIEW'
    else:
        eligibility = 'MATCH'
    return {'score_total': score, 'score_must': must['percentage'], 'score_nice': nice['percentage'],
            'eligibility': eligibility, 'must_present': must['present'], 'must_count': must['count'],
            'nice_present': nice['present'], 'nice_count': nice['count']}


def negotiation_snapshot(listing, comparables):
    """Transparent descriptive guide; no assumed realised selling-price discount."""
    if not comparables:
        return {'sample_size': 0, 'assessment': 'Onvoldoende vergelijkbare advertenties'}
    asking = listing['price_eur']
    values = sorted(c['price_eur'] for c in comparables)
    n = len(values)
    low = values[max(0, int((n - 1) * 0.25))]
    med = round(median(values))
    def rounded(x): return round(x / 250) * 250
    return {
        'sample_size': n,
        'p25_asking': low,
        'median_asking': med,
        'difference_vs_median_eur': asking - med,
        'asking_vs_median_pct': round((asking / med - 1) * 100, 1) if med else None,
        'illustrative_opening_offer': rounded(min(asking, low) * 0.98) if n >= 5 else None,
        'illustrative_target': rounded(min(asking, med, low * 1.03)) if n >= 5 else None,
        'assessment': 'Indicatie op basis van actuele vraagprijzen, niet bewezen transactieprijzen. Meerwaarde opties en conditie niet volledig gecorrigeerd.',
    }
