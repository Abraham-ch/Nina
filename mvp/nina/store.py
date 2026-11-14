import json
import threading
import hashlib
from pathlib import Path
from contextlib import contextmanager
from datetime import datetime, timezone
from functools import lru_cache
import duckdb
from .config import DATA

LOCK = threading.RLock()
def now(): return datetime.now(timezone.utc).isoformat()

@lru_cache(maxsize=1)
def code_revision():
    digest=hashlib.sha256()
    for p in sorted(Path(__file__).parent.glob('*.py')):
        digest.update(p.name.encode());digest.update(p.read_bytes())
    return digest.hexdigest()

@contextmanager
def database():
    with LOCK:
        con = duckdb.connect(str(DATA / 'nina.duckdb'))
        try: yield con
        finally: con.close()

def initialize():
    with database() as c:
        c.execute('''CREATE TABLE IF NOT EXISTS observations(
            id VARCHAR PRIMARY KEY, source VARCHAR, platform VARCHAR, acquired TIMESTAMP,
            latitude DOUBLE, longitude DOUBLE, frp DOUBLE, confidence VARCHAR,
            version VARCHAR, processing VARCHAR, daynight VARCHAR, fire_type INTEGER,
            department VARCHAR, batch_id VARCHAR, scan DOUBLE, track DOUBLE)''')
        c.execute('''CREATE TABLE IF NOT EXISTS batches(
            id VARCHAR PRIMARY KEY, filename VARCHAR, source VARCHAR, sha256 VARCHAR,
            bytes BIGINT, rows_loaded BIGINT, rejected BIGINT, duplicates BIGINT,
            url VARCHAR, imported_at VARCHAR, coverage_start DATE, coverage_end DATE,
            coverage_basis VARCHAR, processing VARCHAR)''')
        c.execute("ALTER TABLE batches ADD COLUMN IF NOT EXISTS spatial_scope VARCHAR DEFAULT 'PER'")
        c.execute('ALTER TABLE batches ADD COLUMN IF NOT EXISTS spatial_geometry VARCHAR')
        c.execute("UPDATE batches SET spatial_scope='PER' WHERE spatial_scope IS NULL")
        c.execute('CREATE TABLE IF NOT EXISTS analyses(id VARCHAR PRIMARY KEY, selection VARCHAR, result VARCHAR, created_at VARCHAR)')
        c.execute('CREATE TABLE IF NOT EXISTS jobs(id VARCHAR PRIMARY KEY, kind VARCHAR, status VARCHAR, progress DOUBLE, message VARCHAR, result VARCHAR, updated_at VARCHAR)')
        c.execute('CREATE INDEX IF NOT EXISTS observations_time ON observations(acquired)')
        c.execute('CREATE INDEX IF NOT EXISTS observations_department ON observations(department)')
        c.execute('CREATE INDEX IF NOT EXISTS observations_source_time ON observations(source,acquired)')

def rows(c, sql, args=None):
    cur = c.execute(sql, args or [])
    columns = [d[0] for d in cur.description]
    return [dict(zip(columns, row)) for row in cur.fetchall()]

@lru_cache(maxsize=1)
def boundaries():
    path = DATA / 'boundaries' / 'departments.geojson'
    if not path.exists(): return {'type':'FeatureCollection','features':[]}
    data = json.loads(path.read_text(encoding='utf-8'))
    for i,f in enumerate(data['features']):
        f['properties'] = {'id': f['properties'].get('shapeID', str(i)), 'name': f['properties'].get('shapeName', str(i))}
    return data

def status():
    with database() as c:
        total = rows(c, 'SELECT count(*) AS observations, min(acquired) AS first_date, max(acquired) AS last_date, count(*) FILTER(WHERE department IS NULL) AS unassigned_department FROM observations')[0]
        sources = rows(c, '''SELECT source, platform, count(*) AS count, min(acquired)::DATE AS first_date,
            max(acquired)::DATE AS last_date FROM observations GROUP BY source,platform ORDER BY source,platform''')
        batches = rows(c, 'SELECT * FROM batches ORDER BY source,coverage_start')
    inventory_path = DATA / 'inventory.json'
    inventory = json.loads(inventory_path.read_text()) if inventory_path.exists() else None
    return {**total, 'sources':sources,'batches':batches,'inventory':inventory,
            'database_bytes': (DATA/'nina.duckdb').stat().st_size if (DATA/'nina.duckdb').exists() else 0}
