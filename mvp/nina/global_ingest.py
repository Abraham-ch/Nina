"""Importación mundial acotada en memoria para el MVP de observaciones.

No armoniza instrumentos: conserva detecciones y audita cada descarte.
Los originales permanecen en el directorio suministrado por el usuario.
"""
import hashlib
import json
from pathlib import Path

import shapely

from .config import DATA
from .store import database, initialize, boundaries, now, rows

COLUMNS = ['id','source','platform','acquired','latitude','longitude','frp','confidence',
           'version','processing','daynight','fire_type','department','batch_id','scan','track']
RAW_COLUMNS = ['latitude','longitude','acq_date','acq_time','satellite','confidence','version',
               'daynight','type','frp','scan','track','instrument']


def literal(value):
    return "'" + str(value).replace("'", "''") + "'"


def source_for(path):
    name = path.name.upper()
    if '_LS_' in name:
        return None
    if 'J1V' in name: return 'viirs-jpss1'
    if 'J2V' in name: return 'viirs-jpss2'
    if 'SV-C' in name: return 'viirs-snpp'
    if 'M-C61' in name or 'MODIS' in name: return 'modis'
    raise ValueError(f'No se puede identificar el instrumento: {path.name}')


def file_hash(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        while chunk := stream.read(8 * 1024 * 1024): digest.update(chunk)
    return digest.hexdigest()


def reader_sql(path):
    if path.suffix.lower() == '.json':
        columns = '{' + ','.join(literal(k) + ":'VARCHAR'" for k in RAW_COLUMNS) + '}'
        return f"read_json({literal(path)}, format='array', columns={columns}, maximum_object_size=1048576)"
    # union_by_name and explicit NULLs below also accept the 7-day CSV without type/instrument.
    return f"read_csv({literal(path)}, header=true, all_varchar=true)"


def normalize_sql(connection, path, source, batch_id, year_start, year_end):
    reader = reader_sql(path)
    available = {x[0] for x in connection.execute(f'DESCRIBE SELECT * FROM {reader}').fetchall()}
    fields = ','.join(f'"{k}"' if k in available else f'NULL::VARCHAR AS "{k}"' for k in RAW_COLUMNS)
    processing = 'SP' if 'archive' in path.name.lower() else 'NRT'
    fixed = {'viirs-snpp':'S-NPP','viirs-jpss1':'NOAA-20','viirs-jpss2':'NOAA-21'}.get(source)
    platform = ("CASE lower(trim(satellite)) WHEN 'a' THEN 'Aqua' WHEN 'aqua' THEN 'Aqua' "
                "WHEN 't' THEN 'Terra' WHEN 'terra' THEN 'Terra' END") if source == 'modis' else literal(fixed)
    allowed = {'modis':['a','aqua','t','terra'], 'viirs-snpp':['n','npp','snpp','s-npp','suomi npp'],
               'viirs-jpss1':['n20','1','noaa-20','j1'], 'viirs-jpss2':['n21','2','noaa-21','j2']}[source]
    allowed_sql = ','.join(literal(s) for s in allowed)
    confidence_check = ("try_cast(confidence AS DOUBLE) BETWEEN 0 AND 100") if source == 'modis' else "lower(confidence) IN ('l','n','h','7','8','9')"
    return f'''CREATE OR REPLACE TABLE bulk_stage AS
    WITH raw AS (SELECT {fields} FROM {reader}), parsed AS (
        SELECT *, try_cast(latitude AS DOUBLE) AS lat, try_cast(longitude AS DOUBLE) AS lon,
        try_strptime(acq_date || ' ' || lpad(trim(acq_time),4,'0'), '%Y-%m-%d %H%M') AS stamp,
        {platform} AS plat, try_cast(frp AS DOUBLE) AS power,
        try_cast(scan AS DOUBLE) AS scan_value, try_cast(track AS DOUBLE) AS track_value,
        try_cast("type" AS INTEGER) AS kind FROM raw)
    SELECT substr(sha256({literal(source)} || '|' || plat || '|' || strftime(stamp,'%Y-%m-%dT%H:%M:%S')
        || '|' || printf('%.6f',lat) || '|' || printf('%.6f',lon)),1,32) AS id,
        {literal(source)} AS source, plat AS platform, stamp AS acquired,
        lat AS latitude, lon AS longitude, power AS frp, confidence,
        coalesce(version,'unknown') AS version, {literal(processing)} AS processing,
        upper(daynight) AS daynight, kind AS fire_type, NULL::VARCHAR AS department,
        {literal(batch_id)} AS batch_id, scan_value AS scan, track_value AS track,
        CASE WHEN lat IS NULL OR lon IS NULL OR NOT isfinite(lat) OR NOT isfinite(lon)
                  OR lat NOT BETWEEN -90 AND 90 OR lon NOT BETWEEN -180 AND 180 THEN 'invalid_coordinates'
             WHEN stamp IS NULL OR NOT regexp_full_match(trim(acq_time),'[0-9]{{1,4}}') THEN 'invalid_datetime'
             WHEN stamp::DATE > current_date THEN 'future_date'
             WHEN year(stamp) NOT BETWEEN {int(year_start)} AND {int(year_end)} THEN 'outside_period'
             WHEN lower(trim(satellite)) NOT IN ({allowed_sql}) OR satellite IS NULL THEN 'unknown_or_mismatched_satellite'
             WHEN NOT coalesce(({confidence_check}),false) THEN 'invalid_confidence'
             WHEN upper(daynight) NOT IN ('D','N') OR daynight IS NULL THEN 'invalid_daynight'
             WHEN nullif(frp,'') IS NOT NULL AND (power IS NULL OR NOT isfinite(power) OR power<0) THEN 'invalid_frp'
             WHEN nullif(scan,'') IS NOT NULL AND (scan_value IS NULL OR NOT isfinite(scan_value) OR scan_value<0) THEN 'invalid_scan'
             WHEN nullif(track,'') IS NOT NULL AND (track_value IS NULL OR NOT isfinite(track_value) OR track_value<0) THEN 'invalid_track'
             WHEN nullif("type",'') IS NOT NULL AND (kind IS NULL OR kind NOT BETWEEN 0 AND 3) THEN 'invalid_type'
             ELSE NULL END AS qa_reason
    FROM parsed'''


def assign_departments(connection):
    features = boundaries()['features']
    if not features: return
    geoms = [shapely.geometry.shape(f['geometry']) for f in features]
    tree = shapely.STRtree(geoms)
    # Only a small bounding-box subset can belong to Peru, regardless of world volume.
    records = connection.execute('''SELECT id,longitude,latitude FROM bulk_incoming
        WHERE longitude BETWEEN -82 AND -68 AND latitude BETWEEN -19 AND 1''').fetchall()
    matches = []
    for offset in range(0,len(records),8192):
        part = records[offset:offset+8192]
        points = shapely.points([r[1] for r in part],[r[2] for r in part])
        assigned = {}
        for pi,gi in zip(*tree.query(points,predicate='intersects')):
            assigned[part[int(pi)][0]] = features[int(gi)]['properties']['id']
        matches.extend(assigned.items())
    if matches:
        connection.execute('CREATE OR REPLACE TEMP TABLE bulk_departments(id VARCHAR,department VARCHAR)')
        connection.executemany('INSERT INTO bulk_departments VALUES (?,?)',matches)
        connection.execute('UPDATE bulk_incoming SET department=d.department FROM bulk_departments d WHERE bulk_incoming.id=d.id')


def import_global_file(path, year_start=2025, year_end=2026, progress=print):
    path = Path(path).resolve()
    source = source_for(path)
    digest = file_hash(path)
    identifier = hashlib.sha256(f'global-observed-v1|{digest}|{year_start}|{year_end}'.encode()).hexdigest()
    report_path = DATA/'processed'/f'{identifier}.json'
    with database() as c:
        if c.execute('SELECT 1 FROM batches WHERE id=?',[identifier]).fetchone():
            return json.loads(report_path.read_text(encoding='utf-8')) if report_path.exists() else {'filename':path.name,'status':'cached'}
        progress(json.dumps({'event':'normalizing','file':path.name},ensure_ascii=False))
        c.execute(normalize_sql(c,path,source,identifier,year_start,year_end))
        reasons = dict(c.execute('SELECT qa_reason,count(*) FROM bulk_stage GROUP BY qa_reason').fetchall())
        raw_count = sum(reasons.values())
        accepted = reasons.pop(None,0)
        invalid = sum(n for reason,n in reasons.items() if reason!='outside_period')
        if raw_count and invalid/raw_count > .01:
            error_report={'filename':path.name,'rows_read':raw_count,'qa_reasons':reasons,'status':'failed_quality_gate'}
            report_path.write_text(json.dumps(error_report,indent=2),encoding='utf-8')
            raise ValueError(f'{path.name}: más del 1% de filas inválidas; revisar reporte QA')
        dates = c.execute('SELECT min(acquired)::DATE,max(acquired)::DATE FROM bulk_stage WHERE qa_reason IS NULL').fetchone()
        periods = c.execute("SELECT DISTINCT date_trunc('month',acquired)::DATE FROM bulk_stage WHERE qa_reason IS NULL ORDER BY 1").fetchall()
        processing = 'SP' if 'archive' in path.name.lower() else 'NRT'
        inserted=duplicates=superseded=removed=0
        c.execute('BEGIN TRANSACTION')
        try:
            for (month,) in periods:
                columns = ','.join(COLUMNS)
                raw_month = c.execute("SELECT count(*) FROM bulk_stage WHERE qa_reason IS NULL AND date_trunc('month',acquired)=?",[month]).fetchone()[0]
                c.execute(f'''CREATE OR REPLACE TABLE bulk_incoming AS SELECT {columns} FROM bulk_stage
                    WHERE qa_reason IS NULL AND date_trunc('month',acquired)=?
                    QUALIFY row_number() OVER(PARTITION BY id ORDER BY acquired,frp NULLS LAST)=1''',[month])
                count = c.execute('SELECT count(*) FROM bulk_incoming').fetchone()[0]
                duplicates += raw_month-count
                assign_departments(c)
                if processing == 'SP':
                    # A full-world standard export takes precedence on observed platform/days.
                    c.execute('''CREATE OR REPLACE TEMP TABLE bulk_days AS
                        SELECT DISTINCT source,platform,acquired::DATE AS day FROM bulk_incoming''')
                    removed += c.execute('''SELECT count(*) FROM observations o WHERE processing<>'SP'
                        AND EXISTS(SELECT 1 FROM bulk_days i WHERE i.source=o.source
                        AND i.platform=o.platform AND i.day=o.acquired::DATE)''').fetchone()[0]
                    c.execute('''DELETE FROM observations o WHERE processing<>'SP' AND EXISTS(
                        SELECT 1 FROM bulk_days i WHERE i.source=o.source
                        AND i.platform=o.platform AND i.day=o.acquired::DATE)''')
                else:
                    # Worldwide SP files apply globally; regional SP applies only within its footprint.
                    c.execute('''DELETE FROM bulk_incoming i WHERE EXISTS(SELECT 1 FROM batches b
                        WHERE b.source=i.source AND b.processing='SP' AND i.acquired::DATE BETWEEN b.coverage_start AND b.coverage_end
                        AND ((b.spatial_scope='world' AND (b.coverage_basis<>'observed_dates_only'
                            OR EXISTS(SELECT 1 FROM observations sp WHERE sp.batch_id=b.id
                                AND sp.processing='SP' AND sp.platform=i.platform
                                AND sp.acquired::DATE=i.acquired::DATE)))
                        OR (b.spatial_scope='PER' AND i.department IS NOT NULL)
                        OR (b.spatial_scope='custom' AND i.longitude BETWEEN
                            try_cast(json_extract(b.spatial_geometry,'$.bbox[0]') AS DOUBLE) AND try_cast(json_extract(b.spatial_geometry,'$.bbox[2]') AS DOUBLE)
                            AND i.latitude BETWEEN try_cast(json_extract(b.spatial_geometry,'$.bbox[1]') AS DOUBLE) AND try_cast(json_extract(b.spatial_geometry,'$.bbox[3]') AS DOUBLE))))''')
                    left = c.execute('SELECT count(*) FROM bulk_incoming').fetchone()[0]
                    superseded += count-left
                    count = left
                # Restrict the anti-join to this source/month so memory doesn't scale with the archive.
                c.execute('''DELETE FROM bulk_incoming i WHERE EXISTS(SELECT 1 FROM observations o
                    WHERE o.source=? AND o.acquired>=? AND o.acquired<?::DATE+INTERVAL 1 MONTH AND o.id=i.id)''',[source,month,month])
                unique = c.execute('SELECT count(*) FROM bulk_incoming').fetchone()[0]
                duplicates += count-unique
                c.execute(f'INSERT INTO observations SELECT {columns} FROM bulk_incoming ORDER BY acquired')
                inserted += unique
                progress(json.dumps({'event':'month','file':path.name,'month':str(month),'inserted':unique},ensure_ascii=False))
            c.execute('''INSERT INTO batches(id,filename,source,sha256,bytes,rows_loaded,rejected,duplicates,url,imported_at,
                coverage_start,coverage_end,coverage_basis,processing,spatial_scope,spatial_geometry)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                [identifier,path.name,source,digest,path.stat().st_size,inserted,invalid,duplicates,
                 'Local NASA FIRMS global export; original in data_abraham',now(),dates[0],dates[1],
                 'observed_dates_only',processing,'world',None])
            c.execute('COMMIT')
        except Exception:
            c.execute('ROLLBACK')
            raise
        c.execute('DROP TABLE IF EXISTS bulk_incoming')
        c.execute('DROP TABLE bulk_stage')
        c.execute('CHECKPOINT')
    reasons.update({'duplicate':duplicates,'superseded_by_standard':superseded})
    report={'status':'imported','filename':path.name,'original_path':str(path),'sha256':digest,
            'bytes':path.stat().st_size,'source':source,'processing':processing,'spatial_scope':'world',
            'rows_read':raw_count,'rows_loaded':inserted,'qa_reasons':reasons,'rejected':invalid,
            'existing_provisional_rows_replaced':removed,'first_date':str(dates[0]),'last_date':str(dates[1]),
            'coverage_basis':'observed_dates_only','synthetic':False}
    if raw_count != inserted+sum(reasons.values()): raise RuntimeError('QA row accounting mismatch')
    report_path.write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
    return report


def prepare_bulk_table():
    """Elimina índices por fila en una base de staging, manteniendo unicidad por QA/ingesta."""
    initialize()
    with database() as c:
        constraints = c.execute("SELECT constraint_type FROM duckdb_constraints() WHERE table_name='observations'").fetchall()
        if any(t[0]=='PRIMARY KEY' for t in constraints):
            c.execute('BEGIN TRANSACTION')
            c.execute('CREATE TABLE observations_bulk AS SELECT * FROM observations ORDER BY source,acquired')
            c.execute('DROP TABLE observations')
            c.execute('ALTER TABLE observations_bulk RENAME TO observations')
            c.execute('COMMIT')
        for (index,) in c.execute("SELECT index_name FROM duckdb_indexes() WHERE table_name='observations'").fetchall():
            c.execute('DROP INDEX '+index)


def run(folder, year_start=2025, year_end=2026):
    if not 2000<=year_start<=year_end<=2100: raise ValueError('Rango inválido')
    prepare_bulk_table()
    paths = sorted([*Path(folder).glob('*.json'),*Path(folder).glob('*.csv')],key=lambda p:('archive' not in p.name,p.name))
    report={'created_at':now(),'status':'running','range_years':[year_start,year_end],'files':[],'excluded_files':[],
            'scientific_status':'observed_not_harmonized','synthetic':False}
    destination=DATA/'global-import.json'
    for path in paths:
        if source_for(path) is None:
            report['excluded_files'].append({'filename':path.name,'reason':'excluded_instrument_landsat'})
            continue
        report['files'].append(import_global_file(path,year_start,year_end))
        destination.write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
    with database() as c:
        report['observations']=c.execute('SELECT count(*) FROM observations').fetchone()[0]
        report['by_source']=rows(c,'SELECT source,platform,count(*) AS observations,min(acquired)::DATE AS first_date,max(acquired)::DATE AS last_date FROM observations GROUP BY source,platform ORDER BY source,platform')
    report['status']='complete';report['completed_at']=now()
    destination.write_text(json.dumps(report,indent=2,ensure_ascii=False,default=str),encoding='utf-8')
    print(json.dumps({'event':'complete','observations':report['observations']}),flush=True)
    return report
