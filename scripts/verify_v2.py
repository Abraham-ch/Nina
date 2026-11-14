"""Verify incorporated source files and optionally refresh the analytic snapshot."""
import argparse
import hashlib
import json
import sys
import uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
from nina.config import DATA, RAW
from nina.store import database,initialize,status,now,code_revision

parser=argparse.ArgumentParser()
parser.add_argument('--refresh-parquet',action='store_true')
args=parser.parse_args()
initialize()
with database() as connection:
    batches=connection.execute('SELECT filename,sha256,bytes,spatial_scope FROM batches').fetchall()
    raw_bytes=0
    for filename,digest,size,scope in batches:
        path=RAW/filename
        assert path.resolve().parent==RAW.resolve()
        content=path.read_bytes()
        assert len(content)==size and hashlib.sha256(content).hexdigest()==digest,filename
        raw_bytes+=size
    parquet=DATA/'processed'/'observations.parquet'
    if args.refresh_parquet:
        temporary=parquet.with_name(f'observations.{uuid.uuid4().hex}.parquet')
        escaped=str(temporary).replace("'","''")
        connection.execute(f"COPY observations TO '{escaped}' (FORMAT PARQUET, COMPRESSION ZSTD)")
        temporary.replace(parquet)
    parquet_rows=connection.execute('SELECT count(*) FROM read_parquet(?)',[str(parquet)]).fetchone()[0]
    count=connection.execute('SELECT count(*) FROM observations').fetchone()[0]
    assert parquet_rows==count,'Actualiza el snapshot con --refresh-parquet tras detener el servicio'
    scopes=connection.execute('SELECT spatial_scope,count(*),sum(bytes),sum(rows_loaded) FROM batches GROUP BY spatial_scope').fetchall()
    duplicates,rejected=connection.execute('SELECT sum(duplicates),sum(rejected) FROM batches').fetchone()
data_status=status()
countries=json.loads((ROOT/'web/public/assets/countries.geojson').read_text())
from nina.analytics import Selection
for country in countries['features']: Selection(scope='custom',geometry=country['geometry'])
report={'version':'0.2.0','verified_at':now(),'scope':'world_with_explicit_archive_windows','observations':count,
        'raw_csv_files':len(batches),'raw_csv_bytes':raw_bytes,'parquet_rows':parquet_rows,'parquet_bytes':parquet.stat().st_size,
        'database_bytes':data_status['database_bytes'],'sources':data_status['sources'],
        'scopes':[{'scope':s,'files':n,'csv_bytes':b,'rows_loaded':r} for s,n,b,r in scopes],
        'country_reference_geometries':len(countries['features']),'duplicates_removed':duplicates,'rejected_rows':rejected,
        'backend_code_sha256':code_revision(),'scientific_status':'observed_archive; exploratory_count_model_PER; L2 opportunities pending',
        'synthetic':False}
(DATA/'release-v0.2.json').write_text(json.dumps(report,default=str,indent=2),encoding='utf-8')
print(json.dumps(report,default=str,indent=2))
