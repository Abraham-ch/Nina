"""Verifica el archivo mundial incorporado, sus originales y consultas fuera de Perú."""
import argparse
import hashlib
import json
import os
import sys
import time
import uuid
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
WORKSPACE=ROOT.parent
sys.path.insert(0,str(ROOT))
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--data-dir',type=Path)
parser.add_argument('--refresh-parquet',action='store_true')
args=parser.parse_args()
if args.data_dir:os.environ['NINA_DATA_DIR']=str(args.data_dir.resolve())
from nina.config import DATA
from nina.store import database,now,rows,code_revision
from nina.analytics import Selection,analyze,points_for_analysis

manifest=json.loads((DATA/'global-import.json').read_text(encoding='utf-8'))
if manifest.get('status')!='complete':raise RuntimeError('La importación mundial debe estar completa')
verified=[]
for batch in manifest['files']:
    path=Path(batch['original_path'])
    digest=hashlib.sha256()
    with path.open('rb') as stream:
        while chunk:=stream.read(8*1024*1024):digest.update(chunk)
    assert digest.hexdigest()==batch['sha256'],path.name
    assert path.stat().st_size==batch['bytes'],path.name
    assert batch['rows_read']==batch['rows_loaded']+sum(batch['qa_reasons'].values()),path.name
    verified.append(path.name)
    print(json.dumps({'verified_original':path.name}),flush=True)

with database() as c:
    total=c.execute('SELECT count(*) FROM observations').fetchone()[0]
    sources=rows(c,'''SELECT source,platform,processing,count(*) AS observations,
        min(acquired)::DATE AS first_date,max(acquired)::DATE AS last_date
        FROM observations GROUP BY source,platform,processing ORDER BY source,platform,processing''')
    period_start=min(f['first_date'] for f in manifest['files'])
    period_end=max(f['last_date'] for f in manifest['files'])
    world_sources=rows(c,'''SELECT source,platform,processing,count(*) AS observations,
        min(acquired)::DATE AS first_date,max(acquired)::DATE AS last_date
        FROM observations WHERE acquired::DATE BETWEEN ? AND ?
        GROUP BY source,platform,processing ORDER BY source,platform,processing''',[period_start,period_end])
    # Una consulta exacta; DuckDB puede derramar a disco si supera la memoria fijada.
    duplicate=c.execute('SELECT id FROM observations GROUP BY id HAVING count(*)>1 LIMIT 1').fetchone()
    assert duplicate is None,'Hay identidades duplicadas en la base'
    parquet=DATA/'processed'/'observations.parquet'
    if args.refresh_parquet:
        temporary=parquet.with_name(f'observations.{uuid.uuid4().hex}.parquet')
        c.execute('COPY observations TO ? (FORMAT PARQUET, COMPRESSION ZSTD)',[str(temporary)])
        temporary.replace(parquet)
    parquet_rows=c.execute('SELECT count(*) FROM read_parquet(?)',[str(parquet)]).fetchone()[0] if parquet.exists() else None
    if args.refresh_parquet:assert parquet_rows==total
    continents=rows(c,'''SELECT CASE WHEN longitude < -30 THEN 'Americas'
        WHEN latitude < -10 AND longitude > 110 THEN 'Oceania'
        WHEN longitude > 50 THEN 'Asia' WHEN latitude>35 THEN 'Europe'
        ELSE 'Africa_and_adjacent_areas' END AS reference_zone,count(*) AS observations
        FROM observations WHERE acquired>='2025-11-05' GROUP BY 1 ORDER BY 1''')

countries=json.loads((ROOT/'web/public/assets/countries.geojson').read_text())['features']
checks=[]
for name in ['Brazil','Australia','Indonesia','United States of America','Dem. Rep. Congo']:
    country=next(f for f in countries if f['properties']['name']==name)
    chosen=Selection(scope='custom',area_label=name,geometry=country['geometry'],
        source='viirs-jpss1',platform='all',year_start=2025,year_end=2026,
        selected_year=2026,selected_month=7)
    started=time.perf_counter();analysis=analyze(chosen)
    points=points_for_analysis(analysis,limit=7)
    assert analysis['selected']['value']>0,name
    assert points['total']==analysis['selected']['value'],name
    assert points['shown']==7,name
    checks.append({'country':name,'source':'VIIRS NOAA-20','month':'2026-07',
        'observations':points['total'],'map_sample':points['shown'],
        'seconds':round(time.perf_counter()-started,3),'analysis_id':analysis['id']})
    print(json.dumps({'verified_query':checks[-1]}),flush=True)

report={'version':'0.3.0','verified_at':now(),'period_years':[2025,2026],
    'period_start':period_start,'period_end':period_end,
    'observations':total,'global_files_verified':verified,
    'global_original_bytes':sum(f['bytes'] for f in manifest['files']),
    'global_rows_read':sum(f['rows_read'] for f in manifest['files']),
    'global_rows_added':sum(f['rows_loaded'] for f in manifest['files']),
    'duplicates_removed':sum(f['qa_reasons'].get('duplicate',0) for f in manifest['files']),
    'superseded_nrt':sum(f['qa_reasons'].get('superseded_by_standard',0) for f in manifest['files']),
    'rejected_rows':sum(f['rejected'] for f in manifest['files']),
    'database_bytes':(DATA/'nina.duckdb').stat().st_size,
    'parquet_rows':parquet_rows,'parquet_bytes':parquet.stat().st_size if parquet.exists() else None,
    'sources':sources,'global_period_sources':world_sources,'reference_zones':continents,'country_checks':checks,
    'backend_code_sha256':code_revision(),'synthetic':False,
    'scientific_status':'observed_not_harmonized; L2 opportunities and multi-year global baseline pending'}
destination=DATA/'release-world-v0.3.json'
destination.write_text(json.dumps(report,indent=2,ensure_ascii=False,default=str),encoding='utf-8')
print(json.dumps({'report':str(destination),'observations':total}),flush=True)
