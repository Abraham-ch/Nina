import json
import threading
import hashlib
import os
from pathlib import Path
from contextlib import contextmanager
from datetime import datetime, timezone
from functools import lru_cache,wraps
import duckdb
from .config import DATA

LOCK = threading.RLock()

def atomic_read(function):
    """Keep an analysis/revision/export consistent with local ingestion commits."""
    @wraps(function)
    def wrapped(*args,**kwargs):
        with LOCK: return function(*args,**kwargs)
    return wrapped
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
        con.execute('SET memory_limit = ?', [os.getenv('NINA_DUCKDB_MEMORY_LIMIT','2GB')])
        con.execute('SET threads = ?', [int(os.getenv('NINA_DUCKDB_THREADS','2'))])
        con.execute('SET preserve_insertion_order = false')
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
        # T1 · cuentas y gestión de descargas (WORK_PLAN.md §10). Solo se añaden tablas y
        # columnas: una base creada con el esquema anterior se amplía sin perder filas.
        c.execute('''CREATE TABLE IF NOT EXISTS users(
            id VARCHAR PRIMARY KEY, email VARCHAR UNIQUE NOT NULL, password_hash VARCHAR NOT NULL,
            role VARCHAR NOT NULL, display_name VARCHAR, created_at VARCHAR)''')
        c.execute('''CREATE TABLE IF NOT EXISTS sessions(
            token VARCHAR PRIMARY KEY, user_id VARCHAR NOT NULL, created_at VARCHAR, expires_at VARCHAR)''')
        c.execute('''CREATE TABLE IF NOT EXISTS downloads(
            id VARCHAR PRIMARY KEY, user_id VARCHAR, analysis_id VARCHAR, kind VARCHAR,
            rows BIGINT, filters VARCHAR, dataset_version VARCHAR, created_at VARCHAR)''')
        c.execute('''CREATE TABLE IF NOT EXISTS audit_log(
            id VARCHAR PRIMARY KEY, user_id VARCHAR, action VARCHAR, target VARCHAR,
            detail VARCHAR, created_at VARCHAR)''')
        c.execute('ALTER TABLE batches ADD COLUMN IF NOT EXISTS created_by VARCHAR')
        c.execute('ALTER TABLE analyses ADD COLUMN IF NOT EXISTS created_by VARCHAR')
        # Columnar scans and bounded ingestion avoid row indexes proportional to world volume.

def rows(c, sql, args=None):
    cur = c.execute(sql, args or [])
    columns = [d[0] for d in cur.description]
    return [dict(zip(columns, row)) for row in cur.fetchall()]

def cobertura(source):
    """Fechas reales de un sensor en la base — WORK_PLAN §10, T2 celda A.

    No se codifican fechas: lo que existe es `min/max(acquired)`. Sin filas
    devuelve fechas nulas y quien valida no acota nada.
    """
    with database() as c:
        return rows(
            c,
            '''SELECT min(acquired)::DATE AS first_date, max(acquired)::DATE AS last_date
               FROM observations WHERE source=?''',
            [source],
        )[0]

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
        # `created_by` no se expone: `/api/status` es anónimo. Se comprueba la columna
        # antes, porque `scripts/check_release.py` llama a `status()` sin pasar por
        # `initialize()` y una base anterior a T1 no la tendría (nina/AGENTS.md: nunca
        # romper bases existentes).
        tiene_autor=c.execute("SELECT count(*) FROM information_schema.columns WHERE table_name='batches' AND column_name='created_by'").fetchone()[0]
        proyeccion='* EXCLUDE (created_by)' if tiene_autor else '*'
        batches = rows(c, f'SELECT {proyeccion} FROM batches ORDER BY source,coverage_start')
    inventory_path = DATA / 'inventory.json'
    inventory = json.loads(inventory_path.read_text()) if inventory_path.exists() else None
    return {**total, 'sources':sources,'batches':batches,'inventory':inventory,
            'database_bytes': (DATA/'nina.duckdb').stat().st_size if (DATA/'nina.duckdb').exists() else 0}
