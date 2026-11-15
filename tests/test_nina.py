import csv
import io
import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from nina import config,store,analytics,ingest,science,main,remote

@pytest.fixture()
def client(tmp_path,monkeypatch):
    for key in ['NINA_LLM_BASE_URL','NINA_LLM_API_KEY','NINA_LLM_MODEL']: monkeypatch.delenv(key,raising=False)
    for name in ['raw','processed','models','boundaries','jobs','exports']: (tmp_path/name).mkdir()
    for module in [config,store,analytics,ingest,science,main,remote]: monkeypatch.setattr(module,'DATA',tmp_path)
    for module in [config,ingest,main,remote]: monkeypatch.setattr(module,'RAW',tmp_path/'raw')
    country={'type':'FeatureCollection','features':[{'type':'Feature','properties':{'shapeID':'test-region','shapeName':'Región de prueba'},'geometry':{'type':'Polygon','coordinates':[[[-78,-12],[-72,-12],[-72,-7],[-78,-7],[-78,-12]]]}}]}
    (tmp_path/'boundaries'/'departments.geojson').write_text(json.dumps(country))
    store.boundaries.cache_clear()
    with TestClient(main.app) as c:
        # T1 (WORK_PLAN §10): importar, sincronizar, entrenar y exportar exigen sesión.
        # Los datos se prueban como administrador para que la lógica no dependa del auth.
        c.post('/api/auth/register', json={'email': 'operador@nina.local', 'password': 'secreta-1234'})
        yield c,tmp_path
    store.boundaries.cache_clear()

def fixture_csv(path,year,n=2,source='modis',version='61.03'):
    cols=['latitude','longitude','acq_date','acq_time','satellite','confidence','frp','version','daynight','type']
    rows=[[-9,-75-i*.001,f'{year}-09-03','0030','Aqua' if source=='modis' else 'N',90 if source=='modis' else 'n',2.5,version,'N',0] for i in range(n)]
    with path.open('w',newline='') as f:
        writer=csv.writer(f);writer.writerow(cols);writer.writerows(rows)
    return path

def seed(path):
    for year in range(2015,2026):
        p=fixture_csv(path/'raw'/f'{year}.csv',year,n=2 if year<2025 else 6)
        ingest.ingest_file(p,'modis','test_fixture',f'{year}-01-01',f'{year}-12-31','provider_annual_file')

def selection(**kw):
    return {'year_start':2018,'year_end':2025,'selected_year':2025,'selected_month':9,**kw}

def test_analysis_baseline_and_export_match(client):
    c,path=client;seed(path)
    a=c.post('/api/analyses',json=selection()).json()
    assert a['selected']['value']==6 and a['selected']['historical_median']==2
    assert a['selected']['historical_n']==10 and a['selected']['anomaly_percent']==200
    assert a['selected']['coverage_percent'] is None and a['selected']['interval'] is None
    points=c.get(f"/api/analyses/{a['id']}/points").json()
    assert points['total']==6 and len(points['features'])==6
    data=c.get(f"/api/analyses/{a['id']}/exports/detections")
    assert len(list(csv.DictReader(io.StringIO(data.text.lstrip('\ufeff')))))==6
    evidence=c.get(f"/api/analyses/{a['id']}/exports/manifest").json()
    assert evidence['analysis']['selected']==a['selected']

def test_missing_is_distinct_from_archive_zero(client):
    c,path=client;seed(path)
    a=c.post('/api/analyses',json=selection(source='viirs-jpss2',platform='all')).json()
    assert a['selected']['value'] is None
    b=c.post('/api/analyses',json=selection(selected_month=2)).json()
    assert b['selected']['value']==0 and b['selected']['coverage_percent'] is None
    assert b['selected']['anomaly_percent'] is None

def test_geometry_filter_and_invalid_input(client):
    c,path=client;seed(path)
    poly={'type':'Polygon','coordinates':[[[-76,-10],[-74,-10],[-74,-8],[-76,-8],[-76,-10]]]}
    assert c.post('/api/analyses',json=selection(geometry=poly)).json()['selected']['value']==6
    assert c.post('/api/analyses',json=selection(department="' OR 1=1 --")).status_code==422
    assert c.post('/api/analyses',json=selection(year_start=2026)).status_code==422
    assert c.post('/api/analyses',json=selection(geometry={'type':'Point','coordinates':[0,0]})).status_code==422

def test_idempotent_import_and_provenance(client):
    c,path=client;p=fixture_csv(path/'raw'/'a.csv',2024)
    first=ingest.ingest_file(p,'modis');second=ingest.ingest_file(p,'modis')
    assert first['rows_loaded']==2 and second['status']=='cached'
    assert store.status()['observations']==2

def test_nrt_does_not_duplicate_reprocessed_standard(client):
    c,path=client
    standard=fixture_csv(path/'raw'/'sp.csv',2024)
    ingest.ingest_file(standard,'modis','test', '2024-01-01','2024-12-31','provider_annual_file')
    nrt=fixture_csv(path/'raw'/'nrt.csv',2024,n=4,version='6.1NRT')
    ingest.ingest_file(nrt,'modis')
    assert store.status()['observations']==2

def test_stale_analysis_and_grounded_assistant(client):
    c,path=client;seed(path)
    a=c.post('/api/analyses',json=selection()).json()
    reply=c.post('/api/assistant',json={'analysis_id':a['id'],'question':'Predice el incendio de mañana'}).json()
    assert 'cannot confirm causes' in reply['answer'] and reply['engine']=='deterministic_evidence'
    assert reply['evidence'][1]['value']==6
    p=fixture_csv(path/'raw'/'extra.csv',2026);ingest.ingest_file(p,'modis')
    assert c.get(f"/api/analyses/{a['id']}/exports/series").status_code==409

def test_hostile_origin_and_missing_key(client,monkeypatch):
    c,path=client
    assert c.post('/api/models/train',headers={'Origin':'https://untrusted.example'}).status_code==403
    monkeypatch.delenv('FIRMS_MAP_KEY',raising=False)
    assert c.post('/api/sync',json={'start':'2026-11-01','days':1}).status_code==409

def test_background_model_job(client):
    import time
    c,path=client
    response=c.post('/api/models/train',json={})
    assert response.status_code==200
    identifier=response.json()['id']
    for _ in range(50):
        state=c.get('/api/jobs/'+identifier).json()
        if state['status'] in ['complete','failed']:break
        time.sleep(.02)
    assert state['status']=='complete'

def test_partial_period_never_claims_a_full_month_anomaly(client):
    c,path=client;seed(path)
    p=fixture_csv(path/'raw'/'recent.csv',2026,n=5,version='6.1NRT')
    ingest.ingest_file(p,'modis','NASA FIRMS Area API', '2026-09-03','2026-09-03','api_requested_window')
    a=c.post('/api/analyses',json=selection(year_end=2026,selected_year=2026)).json()
    assert a['selected']['value']==5
    assert a['selected']['status']=='partial_archive'
    assert a['selected']['anomaly_percent'] is None

def test_valid_empty_csv_is_recorded_without_fabricating_detections(client):
    c,path=client
    p=path/'raw'/'empty.csv';p.write_text('latitude,longitude,acq_date,acq_time,satellite,confidence,version\n')
    r=ingest.ingest_file(p,'modis','NASA FIRMS Area API','2026-09-03','2026-09-03','api_requested_window')
    assert r['rows_loaded']==0 and len(store.status()['batches'])==1

def test_llm_cannot_replace_verified_numbers(client,monkeypatch):
    from nina import assistant
    c,path=client;seed(path)
    a=c.post('/api/analyses',json=selection()).json()
    for key,value in [('NINA_LLM_BASE_URL','https://example.test/v1'),('NINA_LLM_API_KEY','test-not-a-real-key'),('NINA_LLM_MODEL','fixture')]:monkeypatch.setenv(key,value)
    class Response:
        def raise_for_status(self): pass
        def json(self):return {'choices':[{'message':{'content':json.dumps({'framing':'Hay 999999 incendios.'})}}]}
    monkeypatch.setattr(assistant.httpx,'post',lambda *a,**k:Response())
    r=c.post('/api/assistant',json={'analysis_id':a['id'],'question':'Compara el mes'}).json()
    assert r['engine']=='deterministic_evidence' and r['framing'] is None
    assert '999999' not in r['answer']

def test_standard_replaces_provisional_window_without_negative_counts(client):
    c,path=client
    p=fixture_csv(path/'raw'/'nrt.csv',2024,n=4,version='6.1NRT');ingest.ingest_file(p,'modis')
    q=fixture_csv(path/'raw'/'sp.csv',2024,n=2)
    r=ingest.ingest_file(q,'modis','test', '2024-01-01','2024-12-31','provider_annual_file')
    assert r['rows_loaded']==2 and store.status()['observations']==2 and r['duplicates']==0

def test_multipart_csv_import_completes_in_background(client):
    import time
    c,path=client;p=fixture_csv(path/'raw'/'fixture.csv',2024)
    response=c.post('/api/import',data={'source':'modis'},files={'file':('firms.csv',p.read_bytes(),'text/csv')})
    assert response.status_code==200
    for _ in range(100):
        job=c.get('/api/jobs/'+response.json()['id']).json()
        if job['status'] in ['complete','failed']:break
        time.sleep(.02)
    assert job['status']=='complete' and store.status()['observations']==2


def foreign_csv(path,year=2026,n=3):
    fixture_csv(path,year,n,version='6.1NRT')
    text=path.read_text();path.write_text(text.replace('-9,-75','-15,27'))
    return path


def test_world_keeps_foreign_data_and_peru_is_spatially_isolated(client):
    c,path=client;seed(path)
    p=foreign_csv(path/'raw'/'global.csv')
    ingest.ingest_file(p,'modis','NASA FIRMS Area API','2026-09-03','2026-09-03','api_requested_window',spatial_scope='world')
    world=c.post('/api/analyses',json=selection(scope='world',year_end=2026,selected_year=2026)).json()
    peru=c.post('/api/analyses',json=selection(year_end=2026,selected_year=2026)).json()
    assert world['selected']['value']==3 and peru['selected']['value']==0
    assert world['selected']['status']=='partial_archive' and world['selected']['anomaly_percent'] is None
    assert c.get(f"/api/analyses/{peru['id']}/points").json()['total']==0


def test_peru_archive_never_declares_worldwide_monthly_coverage(client):
    c,path=client;seed(path)
    world=c.post('/api/analyses',json=selection(scope='world')).json()
    assert world['selected']['value']==6
    assert world['selected']['status']=='partial_archive'
    assert world['selected']['historical_median'] is None
    assert world['archive_windows']==[]


def test_world_polygons_are_validated_and_exactly_filtered(client):
    c,path=client
    p=foreign_csv(path/'raw'/'africa.csv',n=1)
    ingest.ingest_file(p,'modis','NASA FIRMS Area API','2026-09-03','2026-09-03','api_requested_window',spatial_scope='world')
    geometry={'type':'Polygon','coordinates':[[[26,-16],[28,-16],[28,-14],[26,-14],[26,-16]]]}
    result=c.post('/api/analyses',json=selection(scope='custom',area_label='Caso África',geometry=geometry,year_end=2026,selected_year=2026))
    assert result.status_code==200 and result.json()['selected']['value']==1
    assert c.post('/api/analyses',json=selection(scope='custom')).status_code==422
    geometry['coordinates'][0][0][0]=181
    assert c.post('/api/analyses',json=selection(scope='custom',geometry=geometry)).status_code==422


def test_peru_standard_upgrade_does_not_delete_foreign_provisional_data(client):
    c,path=client
    p=foreign_csv(path/'raw'/'world-nrt.csv',2024,n=1)
    ingest.ingest_file(p,'modis','NASA FIRMS Area API','2024-09-03','2024-09-03','api_requested_window',spatial_scope='world')
    q=fixture_csv(path/'raw'/'peru-sp.csv',2024,n=2)
    ingest.ingest_file(q,'modis','test','2024-01-01','2024-12-31','provider_annual_file')
    assert store.status()['observations']==3


def test_identical_empty_responses_preserve_distinct_coverage_windows(client):
    c,path=client
    for start,end in [('2026-09-01','2026-09-15'),('2026-09-16','2026-09-30')]:
        p=path/'raw'/f'{start}.csv';p.write_text('latitude,longitude,acq_date,acq_time,satellite,confidence,version\n')
        ingest.ingest_file(p,'modis','NASA FIRMS Area API',start,end,'api_requested_window',spatial_scope='world')
    result=c.post('/api/analyses',json=selection(scope='world',year_end=2026,selected_year=2026)).json()
    assert result['selected']['value']==0 and result['selected']['status']=='archive_observed'
    assert len(result['archive_windows'])==2
    assert len(store.status()['batches'])==2


def test_partial_aoi_archive_does_not_claim_country_coverage(client):
    c,path=client
    geometry={'type':'Polygon','coordinates':[[[26,-16],[28,-16],[28,-14],[26,-14],[26,-16]]]}
    p=foreign_csv(path/'raw'/'aoi.csv',n=1)
    ingest.ingest_file(p,'modis','NASA FIRMS Area API','2026-09-01','2026-09-30','api_requested_window',spatial_scope='custom',spatial_geometry=geometry)
    local=c.post('/api/analyses',json=selection(scope='custom',geometry=geometry,year_end=2026,selected_year=2026)).json()
    world=c.post('/api/analyses',json=selection(scope='world',year_end=2026,selected_year=2026)).json()
    assert local['selected']['status']=='archive_observed'
    assert world['selected']['status']=='partial_archive'


def test_global_upload_retains_geography_and_exports_same_rows(client):
    import time
    c,path=client;p=foreign_csv(path/'raw'/'foreign.csv',n=1)
    response=c.post('/api/import',data={'source':'modis','spatial_scope':'world'},files={'file':('global.csv',p.read_bytes(),'text/csv')})
    for _ in range(100):
        job=c.get('/api/jobs/'+response.json()['id']).json()
        if job['status'] in ['complete','failed']:break
        time.sleep(.02)
    assert job['status']=='complete' and store.status()['observations']==1
    assert store.status()['batches'][0]['spatial_scope']=='world'


def test_standard_aoi_replaces_provisional_only_inside_requested_box(client):
    c,path=client
    p=foreign_csv(path/'raw'/'global-nrt.csv',2024,n=1)
    ingest.ingest_file(p,'modis','NASA FIRMS Area API','2024-09-03','2024-09-03','api_requested_window',spatial_scope='world')
    q=fixture_csv(path/'raw'/'peru-nrt.csv',2024,n=1,version='6.1NRT');ingest.ingest_file(q,'modis')
    empty=path/'raw'/'empty-sp.csv';empty.write_text('latitude,longitude,acq_date,acq_time,satellite,confidence,version\n')
    geometry={'type':'Polygon','coordinates':[[[26,-16],[28,-16],[28,-14],[26,-14],[26,-16]]],'bbox':[26,-16,28,-14]}
    ingest.ingest_file(empty,'modis','NASA FIRMS Area API','2024-09-01','2024-09-05','api_requested_window',spatial_scope='custom',spatial_geometry=geometry,processing_hint='SP')
    assert store.status()['observations']==1
    # A subsequent identical provisional detection cannot undo the standard window.
    other=foreign_csv(path/'raw'/'later-nrt.csv',2024,n=2)
    ingest.ingest_file(other,'modis','NASA FIRMS Area API','2024-09-03','2024-09-03','api_requested_window',spatial_scope='world')
    assert store.status()['observations']==1


def test_standard_upgrade_refreshes_measurements(client):
    c,path=client
    p=fixture_csv(path/'raw'/'nrt.csv',2024,n=1,version='6.1NRT');ingest.ingest_file(p,'modis')
    q=fixture_csv(path/'raw'/'sp.csv',2024,n=1);q.write_text(q.read_text().replace('2.5','17.5'))
    ingest.ingest_file(q,'modis')
    with store.database() as connection:
        assert connection.execute('SELECT frp,processing FROM observations').fetchone()==(17.5,'SP')


def test_role_guidance_changes_without_changing_evidence(client):
    c,path=client;seed(path)
    a=c.post('/api/analyses',json=selection()).json()
    scientist=c.post('/api/assistant',json={'analysis_id':a['id'],'question':'Describe el mes','role':'ciencia'}).json()
    communicator=c.post('/api/assistant',json={'analysis_id':a['id'],'question':'Describe el mes','role':'comunicacion'}).json()
    assert scientist['guidance']!=communicator['guidance']
    assert scientist['evidence']==communicator['evidence']
    assert scientist['evidence'][1]['value']==6
