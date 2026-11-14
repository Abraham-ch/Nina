import csv
import hashlib
import json
import re
from datetime import datetime, date
from pathlib import Path
import numpy as np
import shapely
from .config import DATA
from .store import database, boundaries, now, initialize

def canonical_source(source):
    return {'viirs-noaa20':'viirs-jpss1','viirs-noaa21':'viirs-jpss2'}.get(source,source)

def parse_row(row, source, batch_id):
    lat,lon=float(row['latitude']),float(row['longitude'])
    if not(-90<=lat<=90 and -180<=lon<=180): raise ValueError('Coordinate out of range')
    if not np.isfinite(lat+lon): raise ValueError('Non-finite coordinate')
    clock = str(row['acq_time']).strip().zfill(4)
    stamp = datetime.strptime(row['acq_date']+' '+clock, '%Y-%m-%d %H%M')
    source=canonical_source(source)
    sat=row.get('satellite','').strip().lower()
    if source=='modis' and sat not in ['a','aqua','t','terra']: raise ValueError('Unknown MODIS platform')
    platform = ('Aqua' if sat in ['a','aqua'] else 'Terra') if source=='modis' else {'viirs-snpp':'S-NPP','viirs-jpss1':'NOAA-20','viirs-jpss2':'NOAA-21'}[source]
    known={'n':'viirs-snpp','snpp':'viirs-snpp','s-npp':'viirs-snpp','n20':'viirs-jpss1','noaa-20':'viirs-jpss1','n21':'viirs-jpss2','noaa-21':'viirs-jpss2'}
    if source!='modis' and sat in known and known[sat]!=source: raise ValueError('Platform does not match selected source')
    version=str(row.get('version','unknown'))
    processing='NRT' if any(x in version.upper() for x in ['NRT','URT','RT']) else 'SP'
    confidence=str(row.get('confidence',''))
    if source=='modis' and (not 0<=float(confidence)<=100): raise ValueError('MODIS confidence')
    if source!='modis' and confidence.lower() not in ['l','n','h','7','8','9']: raise ValueError('VIIRS confidence')
    def number(key):
        value=row.get(key,'')
        if value in ['',None]: return None
        result=float(value)
        if not np.isfinite(result): raise ValueError('Non-finite '+key)
        return result
    identity=f'{source}|{platform}|{stamp.isoformat()}|{lat:.6f}|{lon:.6f}'
    return [hashlib.sha256(identity.encode()).hexdigest()[:32], source, platform, stamp, lat, lon,
            number('frp'),confidence,version,processing,row.get('daynight',''),int(row['type']) if row.get('type','') else None,
            None,batch_id,number('scan'),number('track')]

def classify(values):
    if not values: return values
    features=boundaries()['features']
    if not features: return values
    geoms=[shapely.geometry.shape(f['geometry']) for f in features]
    tree=shapely.STRtree(geoms)
    points=shapely.points(np.array([r[5] for r in values]),np.array([r[4] for r in values]))
    pairs=tree.query(points,predicate='intersects')
    for pi,gi in zip(*pairs): values[int(pi)][12]=features[int(gi)]['properties']['id']
    return values

def ingest_file(path: Path, source, url='', coverage_start=None, coverage_end=None, coverage_basis='unknown', progress=None, spatial_scope='PER', spatial_geometry=None):
    initialize()
    if spatial_scope not in ['PER','world','custom']: raise ValueError('Ámbito geográfico desconocido')
    if spatial_scope=='custom' and not spatial_geometry: raise ValueError('El archivo por área requiere su geometría')
    source=canonical_source(source)
    digest=hashlib.sha256(path.read_bytes()).hexdigest()
    context=json.dumps([digest,source,spatial_scope,spatial_geometry,str(coverage_start),str(coverage_end),coverage_basis],sort_keys=True)
    identifier=digest if coverage_basis=='provider_annual_file' else hashlib.sha256(context.encode()).hexdigest()
    with database() as c:
        previous=c.execute('''SELECT rows_loaded FROM batches WHERE sha256=? AND source=? AND spatial_scope=?
            AND coverage_start IS NOT DISTINCT FROM CAST(? AS DATE) AND coverage_end IS NOT DISTINCT FROM CAST(? AS DATE)
            AND coverage_basis=? AND spatial_geometry IS NOT DISTINCT FROM ?''',
            [digest,source,spatial_scope,coverage_start,coverage_end,coverage_basis,json.dumps(spatial_geometry) if spatial_geometry else None]).fetchone()
        if previous: return {'status':'cached','rows_loaded':previous[0],'sha256':digest}
        if c.execute('SELECT 1 FROM batches WHERE id=?',[identifier]).fetchone(): identifier=hashlib.sha256(context.encode()).hexdigest()
    source=canonical_source(source)
    values=[];rejected=0;errors=[]
    with path.open(encoding='utf-8-sig',newline='') as stream:
        reader=csv.DictReader(stream)
        if not {'latitude','longitude','acq_date','acq_time'}<=set(reader.fieldnames or []): raise ValueError('CSV FIRMS inválido: faltan coordenadas/fecha/hora')
        for n,row in enumerate(reader,2):
            try: values.append(parse_row(row,source,identifier))
            except (ValueError,KeyError,TypeError) as error:
                rejected+=1
                if len(errors)<10: errors.append({'line':n,'reason':str(error)})
    if not values and rejected: raise ValueError('El archivo no contiene observaciones válidas')
    classify(values)
    excluded=0
    if spatial_scope=='PER' and coverage_basis!='provider_annual_file':
        excluded=sum(v[12] is None for v in values)
        values=[v for v in values if v[12] is not None]
    processing=('SP' if all(r[9]=='SP' for r in values) else 'NRT') if values else ('NRT' if 'Area API' in url else 'SP')
    normalized=DATA/'processed'/f'{identifier}.csv'
    with normalized.open('w',encoding='utf-8',newline='') as stream:
        writer=csv.writer(stream)
        writer.writerow(['id','source','platform','acquired','latitude','longitude','frp','confidence','version','processing','daynight','fire_type','department','batch_id','scan','track'])
        writer.writerows(values)
    with database() as c:
        before=c.execute('SELECT count(*) FROM observations').fetchone()[0]
        c.execute('BEGIN TRANSACTION')
        try:
            # A subsequent standard product upgrades an identical provisional detection.
            c.execute('CREATE TEMP TABLE incoming AS SELECT * FROM observations LIMIT 0')
            c.execute("COPY incoming FROM '"+str(normalized).replace("'","''")+"' (HEADER TRUE, NULLSTR '')")
            if processing!='SP':
                c.execute("DELETE FROM incoming WHERE EXISTS(SELECT 1 FROM batches b WHERE b.source=incoming.source AND b.processing='SP' AND b.coverage_start<=incoming.acquired::DATE AND b.coverage_end>=incoming.acquired::DATE AND b.coverage_basis='provider_annual_file' AND (b.spatial_scope='world' OR (b.spatial_scope='PER' AND incoming.department IS NOT NULL)))")
            elif coverage_start and coverage_end and coverage_basis=='provider_annual_file':
                scope_filter='' if spatial_scope=='world' else " AND (department IS NOT NULL OR batch_id IN (SELECT id FROM batches WHERE spatial_scope='PER'))"
                if spatial_scope!='custom':
                    c.execute("DELETE FROM observations WHERE source=? AND processing<>'SP' AND acquired::DATE BETWEEN ? AND ?"+scope_filter,[source,coverage_start,coverage_end])
            before=c.execute('SELECT count(*) FROM observations').fetchone()[0]
            c.execute('INSERT OR IGNORE INTO observations SELECT * FROM incoming')
            if processing=='SP':
                c.execute("UPDATE observations SET version=i.version,processing=i.processing,batch_id=i.batch_id FROM incoming i WHERE observations.id=i.id AND observations.processing<>'SP'")
            loaded=c.execute('SELECT count(*) FROM observations').fetchone()[0]-before
            c.execute('INSERT INTO batches VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',[identifier,path.name,source,digest,path.stat().st_size,loaded,rejected,len(values)-loaded,url,now(),coverage_start,coverage_end,coverage_basis,processing,spatial_scope,json.dumps(spatial_geometry) if spatial_geometry else None])
            c.execute('COMMIT')
        except Exception:
            c.execute('ROLLBACK');raise
    report={'status':'imported','filename':path.name,'rows_loaded':loaded,'rejected':rejected,'duplicates':len(values)-loaded,'sha256':digest,'sample_errors':errors,'unassigned':sum(v[12] is None for v in values),'excluded_outside_peru':excluded,'spatial_scope':spatial_scope}
    (DATA/'processed'/f'{identifier}.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    normalized.unlink(missing_ok=True)
    return report

def import_archive():
    inventory=json.loads((DATA/'inventory.json').read_text())
    results=[]
    for i,entry in enumerate(inventory['files']):
        path=DATA/'raw'/entry['filename']
        if not path.exists(): continue
        year=entry['year']; source=entry['source']
        start=f'{year}-01-01'
        if source=='modis' and year==2000: start='2000-11-01'
        if source=='viirs-snpp' and year==2012: start='2012-01-20'
        if source=='viirs-jpss1' and year==2018: start='2018-04-01'
        result=ingest_file(path,source,entry['url'],start,f'{year}-12-31','provider_annual_file')
        print(f"[{i+1}/{len(inventory['files'])}] {path.name}: {result['status']} {result['rows_loaded']}",flush=True)
        results.append(result)
    with database() as c:
        destination=str(DATA/'processed'/'observations.parquet').replace("'","''")
        c.execute(f"COPY observations TO '{destination}' (FORMAT PARQUET, COMPRESSION ZSTD)")
    return results

if __name__=='__main__': import_archive()
