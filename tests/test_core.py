from app.extraction import local_claims, cleaned_text, evidence_is_real
from app.scoring import calculate
from app.provider import validate_search_url
import pytest

@pytest.mark.parametrize('text', ['22 inch velgen', '22 inch wielen', "22'' wielen", '22" velgen', '22-inch alloy wheels'])
def test_22_inch_variants(text):
    assert local_claims(text)['wheels_22']['status']=='PRESENT'

def test_22_inch_screen_is_not_wheels():
    assert 'wheels_22' not in local_claims('22 inch scherm')

def test_explicit_absent_and_optional():
    assert local_claims('geen 22 inch wielen')['wheels_22']['status']=='ABSENT'
    assert local_claims('22 inch velgen tegen meerprijs')['wheels_22']['status']=='UNKNOWN'

def test_negation_towbar():
    assert local_claims('zonder trekhaak')['towbar']['status']=='ABSENT'

def test_missing_is_unknown():
    assert 'towbar' not in local_claims('Mooi onderhouden auto')

def test_privacy_redaction():
    cleaned=cleaned_text('XC90', 'Dealer info hans@example.nl en 0612345678')
    assert 'hans@example.nl' not in cleaned
    assert '0612345678' not in cleaned

def test_quote_validation():
    assert evidence_is_real('22 inch velgen','XC90 met 22 inch velgen aanwezig')
    assert not evidence_is_real('Bowers en Wilkins','XC90 met 22 inch velgen aanwezig')

def test_scoring_complete_and_missing_must():
    criteria=[{'key':'towbar','group_name':'MUST_HAVE','weight':5,'enabled':1},
              {'key':'wheels_22','group_name':'NICE_TO_HAVE','weight':5,'enabled':1}]
    assert calculate(criteria,{'towbar':'PRESENT','wheels_22':'PRESENT'})['score_total']==100
    out=calculate(criteria,{'towbar':'ABSENT','wheels_22':'PRESENT'})
    assert out['score_total']==30
    assert out['eligibility']=='REJECTED'
    assert calculate(criteria,{'towbar':'UNKNOWN','wheels_22':'PRESENT'})['eligibility']=='UNVERIFIED'

def test_profile_url_ssrf():
    for bad in ['http://www.gaspedaal.nl/volvo/xc90','https://example.com/',
                'https://www.gaspedaal.nl.evil.com/a', 'https://user:password@gaspedaal.nl/a']:
        with pytest.raises(ValueError):validate_search_url(bad)
    assert validate_search_url('https://www.gaspedaal.nl/volvo/xc90/2025')
