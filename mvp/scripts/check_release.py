"""Reconcile shipped scientific artifacts against immutable source manifests."""
import hashlib
import json
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
from nina.config import DATA
from nina.store import database,status,now

def main():
    inv=json.loads((DATA/'inventory.json').read_text())
    total=0
    for entry in inv['files']:
        p=DATA/'raw'/entry['filename'];payload=p.read_bytes()
        assert len(payload)==entry['expected_bytes'],entry['filename']
        assert hashlib.sha256(payload).hexdigest()==entry['sha256'],entry['filename']
        total+=len(payload)
    st=status()
    with database() as c:
        parquet_rows=c.execute('SELECT count(*) FROM read_parquet(?)',[str(DATA/'processed'/'observations.parquet')]).fetchone()[0]
        duplicates,rejected=c.execute('SELECT sum(duplicates),sum(rejected) FROM batches').fetchone()
    assert parquet_rows==st['observations']
    assert total==inv['total_expected_bytes']
    sources=[{'source':r['source'],'platform':r['platform'],'count':r['count']} for r in st['sources']]
    code=hashlib.sha256()
    for p in sorted((ROOT/'nina').glob('*.py')):code.update(p.name.encode());code.update(p.read_bytes())
    output={'version':'0.1.0','verified_at':now(),'scope':'PER','raw_csv_files':len(inv['files']),
        'raw_csv_bytes':total,'observations':st['observations'],'sources':sources,'parquet_rows':parquet_rows,
        'parquet_bytes':(DATA/'processed'/'observations.parquet').stat().st_size,'database_bytes':st['database_bytes'],
        'duplicates_removed':duplicates,'rejected_rows':rejected,'unassigned_department':st['unassigned_department'],
        'backend_code_sha256':code.hexdigest(),'scientific_status':'observed_archive_and_exploratory_count_calibration; L2 opportunities pending',
        'synthetic':False}
    (DATA/'release-v0.1.json').write_text(json.dumps(output,indent=2),encoding='utf-8')
    print(json.dumps(output,indent=2))

if __name__=='__main__':main()
