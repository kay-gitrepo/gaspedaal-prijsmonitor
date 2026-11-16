"""Deterministic score: 70% must-haves and 30% nice-to-haves; no LLM arithmetic."""

VALID_STATUSES = {'PRESENT', 'ABSENT', 'UNKNOWN', 'CONFLICT'}


UNCERTAIN = ('UNKNOWN', 'CONFLICT')


def calculate(criteria, claims):
    """Confirmed score (score_total), what is still possible (score_potential) and how much is known.

    score_total counts only PRESENT; score_potential also counts UNKNOWN and CONFLICT as present, so 100 % still
    means: everything demonstrably present. A wish without any claim counts as UNKNOWN.
    """
    active = [c for c in criteria if c.get('enabled', 1)]
    by_key = {c['criterion_key']: c['status'] for c in claims} if isinstance(claims, list) else claims
    status = {c['key']: by_key.get(c['key']) or 'UNKNOWN' for c in active}
    groups = {}
    for group in ('MUST_HAVE', 'NICE_TO_HAVE'):
        items = [c for c in active if c['group_name'] == group]
        weight = sum(c['weight'] for c in items)
        points = sum(c['weight'] for c in items if status[c['key']] == 'PRESENT')
        possible = sum(c['weight'] for c in items if status[c['key']] == 'PRESENT' or status[c['key']] in UNCERTAIN)
        groups[group] = {'percentage': round(points / weight * 100, 1) if weight else 100.0,
                         'potential': round(possible / weight * 100, 1) if weight else 100.0,
                         'present': sum(status[c['key']] == 'PRESENT' for c in items),
                         'count': len(items)}
    must, nice = groups['MUST_HAVE'], groups['NICE_TO_HAVE']
    coefficients = [(0.7, must)] if must['count'] else []
    if nice['count']:
        coefficients.append((0.3, nice))
    total_coeff = sum(coeff for coeff, _ in coefficients)
    def combine(field):
        return round(sum(coeff * g[field] for coeff, g in coefficients) / total_coeff, 1) if total_coeff else 100.0
    score = combine('percentage')
    total_weight = sum(c['weight'] for c in active)
    known = sum(c['weight'] for c in active if status[c['key']] in ('PRESENT', 'ABSENT'))
    must_items = [c for c in active if c['group_name'] == 'MUST_HAVE']
    reasons = {'absent': [c['key'] for c in must_items if status[c['key']] == 'ABSENT'],
               'unknown': [c['key'] for c in must_items if status[c['key']] in UNCERTAIN],
               'conflict': [c['key'] for c in active if status[c['key']] == 'CONFLICT']}
    extra = {'score_potential': combine('potential'),
             'evidence_coverage': round(known / total_weight * 100, 1) if total_weight else 100.0,
             'must_unknown': len(reasons['unknown']), 'must_absent': len(reasons['absent']),
             'status_keys': reasons}
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
            'nice_present': nice['present'], 'nice_count': nice['count'], **extra}

