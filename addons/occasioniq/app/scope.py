"""Scores per zoekopdracht (WP-13): welke score hoort bij een auto in een lijst?

Met een gekozen zoekopdracht: de score volgens die wensen. Bij "Alle zoekopdrachten": de score van de zoekopdracht
waarin de auto het eerst werd gezien, met de naam van die zoekopdracht erbij.
"""
PL_SCORES = ('score_total', 'score_must', 'score_nice', 'eligibility', 'score_potential', 'evidence_coverage',
             'must_present', 'must_count', 'must_unknown', 'must_absent', 'status_keys_json', 'analyzed_hash')


def home_profiles(con):
    """Per auto de zoekopdracht van de eerste prijswaarneming."""
    home = {}
    for lid, pid in con.execute('SELECT listing_id,profile_id FROM price_observations ORDER BY observed_at,id'):
        home.setdefault(lid, pid)
    return home


def profile_titles(con):
    return {r[0]: r[1] for r in con.execute('SELECT id,title FROM search_profiles')}


def scored_listings(con, listing_columns, profile_id=None):
    """Auto's met de scorevelden van de juiste zoekopdracht; `availability` volgt de gekozen zoekopdracht."""
    pl_cols = ','.join(f'pl.{c}' for c in PL_SCORES)
    if profile_id:
        rows = con.execute(f'''SELECT {listing_columns},{pl_cols},pl.profile_id AS score_profile_id,
            pl.status AS profile_status FROM listings l JOIN profile_listings pl ON pl.listing_id=l.id
            WHERE pl.profile_id=?''', (profile_id,))
        items = []
        for r in rows:
            item = dict(r)
            item['availability'] = item.pop('profile_status')
            items.append(item)
    else:
        home = home_profiles(con)
        chosen = {}
        for r in con.execute(f'''SELECT {listing_columns},{pl_cols},pl.profile_id AS score_profile_id FROM listings l
                                 JOIN profile_listings pl ON pl.listing_id=l.id ORDER BY pl.profile_id'''):
            item = dict(r)
            lid = item['id']
            if lid not in chosen or item['score_profile_id'] == home.get(lid):
                chosen[lid] = item
        items = list(chosen.values())
    titles = profile_titles(con)
    for item in items:
        item['score_profile_title'] = titles.get(item['score_profile_id'])
    return items


def context_profile(con, listing_id, wanted=None):
    """De zoekopdracht waarvan de wensen gelden voor deze auto: de gevraagde als de auto erin zit, anders de eerste."""
    members = [r[0] for r in con.execute('SELECT profile_id FROM profile_listings WHERE listing_id=? ORDER BY profile_id',
                                         (listing_id,))]
    if wanted in members:
        return wanted
    if not members:
        return None
    first = con.execute('''SELECT profile_id FROM price_observations WHERE listing_id=? ORDER BY observed_at,id LIMIT 1''',
                        (listing_id,)).fetchone()
    return first[0] if first and first[0] in members else members[0]


def criteria_labels(con, profile_id=None):
    if profile_id:
        return {r[0]: r[1] for r in con.execute('SELECT key,label FROM criteria WHERE profile_id=?', (profile_id,))}
    return {(r[0], r[1]): r[2] for r in con.execute('SELECT profile_id,key,label FROM criteria')}
