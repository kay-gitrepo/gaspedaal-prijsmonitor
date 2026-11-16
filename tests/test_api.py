import time
from fastapi.testclient import TestClient
from app.main import app
from app.db import connect

FIXTURE={
  'complete':True,
  'listings':[
    {'external_id':'xc90-1','title':'XC90 T8 Ultra','price_eur':74950,'year':2025,'kilometers':28000,
     'trim':'Ultra','seller':'Autobedrijf A','description':'Elektrische trekhaak. 22 inch velgen. Pilot Assist',
     'portals':[{'portal_id':'dealer-100','site':'Dealersite','kind':'dealer','price_eur':74950,
                 'click_url':'https://api.gaspedaal.nl/redirect/vehicle/100'},
                {'portal_id':'autotrack-200','site':'AutoTrack','kind':'portal','price_eur':74950,
                 'source_url':'https://www.autotrack.nl/a/volvo/xc90/200'}]},
    {'external_id':'xc90-2','title':'XC90 T8 Ultra 2','price_eur':76950,'year':2025,'kilometers':32000,
     'trim':'Ultra','seller':'Autobedrijf B','description':'Geen trekhaak. 22 inch scherm.'},
  ]
}

def wait_run(client,run_id,timeout=8):
    end=time.monotonic()+timeout
    while time.monotonic()<end:
        r=client.get(f'/api/v1/refresh-runs/{run_id}').json()
        if r['state'] in ('COMPLETE','PARTIAL','FAILED'):return r
        time.sleep(0.1)
    assert False,'Worker did not complete'

def test_end_to_end_price_history_and_logs():
    with TestClient(app) as client:
        assert client.get('/api/v1/listings').status_code==401
        login=client.post('/api/v1/login',json={'password':'not-a-real-password'})
        assert login.status_code==200
        headers={'X-CSRF-Token':login.json()['csrf']}
        post=client.post('/api/v1/profiles',headers=headers,json={
            'title':'XC90 2025 test','search_url':'https://www.gaspedaal.nl/volvo/xc90/2025'})
        assert post.status_code==201,post.text
        pid=post.json()['id']
        assert client.post(f'/api/v1/profiles/{pid}/snapshot',json=FIXTURE,headers=headers).status_code==200
        ha_headers={'Authorization':'Bearer not-a-real-ha-refresh-token-for-tests','Idempotency-Key':'initial-run'}
        result=client.post('/api/v1/refresh-runs',headers=ha_headers,json={'scope':'all','reason':'scheduled_ha'})
        assert result.status_code==202,result.text
        rid=result.json()['run_id']
        again=client.post('/api/v1/refresh-runs',headers=ha_headers,json={'scope':'all','reason':'scheduled_ha'})
        assert again.status_code==200
        assert again.json()['run_id']==rid
        assert wait_run(client,rid)['state']=='COMPLETE'
        data=client.get('/api/v1/listings').json()['items']
        assert len(data)==2
        assert sum(row['score_total']>=70 for row in data)>=1
        assert data[0]['observations']==1
        assert client.get('/api/v1/integrations').json()['items']
        assert client.get('/api/v1/dashboard').json()['active_listings']==2
        # Same prices are recorded on a second, successful scan.
        second=client.post('/api/v1/refresh-runs',headers=headers,json={'scope':'all'})
        assert second.status_code==202
        assert wait_run(client,second.json()['run_id'])['state']=='COMPLETE'
        assert all(x['observations']==2 for x in client.get('/api/v1/listings').json()['items'])
        changed=dict(FIXTURE)
        changed['listings']=[dict(x) for x in FIXTURE['listings']]
        changed['listings'][0]['price_eur']=71950
        assert client.post(f'/api/v1/profiles/{pid}/snapshot',json=changed,headers=headers).status_code==200
        third=client.post('/api/v1/refresh-runs',headers=headers,json={'scope':'all'})
        out=wait_run(client,third.json()['run_id'])
        assert out['summary']['price_changes']==1
        listing=next(x for x in client.get('/api/v1/listings').json()['items'] if x['price_eur']==71950)
        detail=client.get(f'/api/v1/listings/{listing["id"]}').json()
        assert len(detail['history'])==3
        assert len(detail['sources'])==2
        assert {x['site'] for x in detail['sources']}=={'Dealersite','AutoTrack'}
        assert all(len(x['history'])==3 for x in detail['sources'])
        assert any(e['event_type']=='PRICE_CHANGED' for e in detail['events'])
        assert client.get('/api/v1/export/observations.csv').status_code==200


def test_no_false_disappearance_on_partial_scan():
    with TestClient(app) as client:
        login=client.post('/api/v1/login',json={'password':'not-a-real-password'})
        headers={'X-CSRF-Token':login.json()['csrf']}
        profiles=client.get('/api/v1/profiles').json()['items']
        pid=profiles[0]['id'] if profiles else client.post('/api/v1/profiles',json={
            'title':'XC90','search_url':'https://gaspedaal.nl/volvo/xc90'},headers=headers).json()['id']
        client.post(f'/api/v1/profiles/{pid}/snapshot',json={'complete':False,'listings':[]},headers=headers)
        refresh=client.post('/api/v1/refresh-runs',json={'scope':{'profile_ids':[pid]}},headers=headers)
        assert wait_run(client,refresh.json()['run_id'])['state']=='PARTIAL'
        assert not any(r['status']=='MISSING_UNCONFIRMED' for r in connect().execute('SELECT status FROM profile_listings'))

def test_frontend_assets_and_authentication():
    with TestClient(app) as client:
        assert client.get('/').status_code==200
        assert 'OccasionIQ' in client.get('/').text
        assert client.get('/static/js/main.js').status_code==200
        assert client.get('/health').json()['live_gaspedaal_configured'] is False
        assert client.post('/api/v1/refresh-runs',json={'scope':'all'}).status_code==401
        wrong=client.post('/api/v1/login',json={'password':'incorrect'})
        assert wrong.status_code==401
        ok=client.post('/api/v1/login',json={'password':'not-a-real-password'})
        assert ok.status_code==200
        assert client.post('/api/v1/profiles',json={'title':'Test','search_url':'https://gaspedaal.nl/volvo'}).status_code==403


def test_system_status_never_exposes_secrets():
    with TestClient(app) as client:
        assert client.get('/api/v1/system').status_code==401
        client.post('/api/v1/login',json={'password':'not-a-real-password'})
        data=client.get('/api/v1/system').json()
        assert data['live_source'] is False and data['ai_enabled'] is False
        text=str(data)
        for secret in ('not-a-real-password','not-a-real-secret','not-a-real-ha-refresh-token'):
            assert secret not in text
