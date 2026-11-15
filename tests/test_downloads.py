"""T1 · autoría, historial de descargas y auditoría — WORK_PLAN.md §10, spec S1.

Cubre las celdas A y B de T1: registrar el autor en importaciones y lotes, asociar los
análisis a su autor, el historial `downloads` (una pantalla "Mis descargas" lo consume)
y el `audit_log` de quién importó o sincronizó, visible solo para `admin`.
"""

import time

from nina import ingest, store

# Helpers ya existentes: no se reimplementan, se reutilizan.
from test_nina import fixture_csv, seed, selection

CONTRASENA = 'secreta-1234'


def cuenta(c, email, rol='analista'):
    """El primer registro de la base siempre sale como `admin` (bootstrap de `nina/auth.py`)."""
    return c.post(
        '/api/auth/register', json={'email': email, 'password': CONTRASENA, 'role': rol}
    ).json()


def importar(c, path, nombre):
    archivo = fixture_csv(path / 'raw' / nombre, 2024)
    respuesta = c.post(
        '/api/import',
        files={'file': (nombre, archivo.read_bytes(), 'text/csv')},
        data={'source': 'modis', 'coverage_start': '2024-01-01', 'coverage_end': '2024-12-31'},
    )
    assert respuesta.status_code == 200, respuesta.text
    identificador = respuesta.json()['id']
    for _ in range(400):
        estado = c.get(f'/api/jobs/{identificador}').json()
        if estado['status'] in ('complete', 'failed'):
            break
        time.sleep(0.02)
    assert estado['status'] == 'complete', estado
    return estado


def ultima(columna, tabla):
    with store.database() as con:
        return con.execute(f'SELECT {columna} FROM {tabla} ORDER BY rowid DESC LIMIT 1').fetchone()[0]


def test_el_lote_guarda_a_quien_lo_importo(client):
    c, path = client
    user = cuenta(c, 'lead@uni.pe')
    archivo = fixture_csv(path / 'raw' / 'lote.csv', 2024)
    ingest.ingest_file(
        archivo, 'modis', 'test', '2024-01-01', '2024-12-31', 'provider_annual_file',
        created_by=user['id'],
    )
    assert ultima('created_by', 'batches') == user['id']


def test_importar_por_http_asocia_al_usuario_autenticado(client):
    c, path = client
    user = cuenta(c, 'lead@uni.pe')
    importar(c, path, 'http.csv')
    assert ultima('created_by', 'batches') == user['id']


def test_el_analisis_se_asocia_a_su_autor(client):
    c, path = client
    user = cuenta(c, 'lead@uni.pe')
    analisis = c.post('/api/analyses', json=selection()).json()
    with store.database() as con:
        autor = con.execute('SELECT created_by FROM analyses WHERE id=?', [analisis['id']]).fetchone()[0]
    assert autor == user['id']


def test_exportar_registra_la_descarga(client):
    c, path = client
    user = cuenta(c, 'lead@uni.pe')
    seed(path)
    analisis = c.post('/api/analyses', json=selection()).json()
    assert c.get(f"/api/analyses/{analisis['id']}/exports/series").status_code == 200
    historial = c.get('/api/downloads').json()
    assert len(historial) == 1
    assert historial[0]['user_id'] == user['id']
    assert historial[0]['analysis_id'] == analisis['id']
    assert historial[0]['kind'] == 'series'
    assert historial[0]['rows'] >= 0


def test_el_historial_de_descargas_es_por_usuario(client):
    c, path = client
    cuenta(c, 'lead@uni.pe')
    c.post('/api/auth/logout')
    cuenta(c, 'otro@uni.pe', 'analista')
    seed(path)
    analisis = c.post('/api/analyses', json=selection()).json()
    c.get(f"/api/analyses/{analisis['id']}/exports/series")
    assert len(c.get('/api/downloads').json()) == 1
    c.post('/api/auth/logout')
    c.post('/api/auth/login', json={'email': 'lead@uni.pe', 'password': CONTRASENA})
    assert c.get('/api/downloads').json() == []


def test_el_historial_de_descargas_requiere_sesion(client):
    c, _ = client
    assert c.get('/api/downloads').status_code == 401


def test_la_auditoria_registra_quien_importo(client):
    c, path = client
    user = cuenta(c, 'lead@uni.pe')
    importar(c, path, 'audit.csv')
    registros = c.get('/api/audit').json()
    assert any(f['action'] == 'import' and f['user_id'] == user['id'] for f in registros)
    assert all(f['created_at'] for f in registros)


def test_la_auditoria_registra_quien_entreno(client):
    c, _ = client
    user = cuenta(c, 'lead@uni.pe')
    # `/api/models/train` no necesita claves ni red: sirve para probar la auditoría de acciones.
    c.post('/api/models/train')
    registros = c.get('/api/audit').json()
    assert any(f['action'] == 'train' and f['user_id'] == user['id'] for f in registros)


def test_la_auditoria_solo_es_visible_para_admin(client):
    c, _ = client
    cuenta(c, 'lead@uni.pe')
    c.post('/api/auth/logout')
    cuenta(c, 'an@uni.pe', 'analista')
    assert c.get('/api/audit').status_code == 403


def test_el_historial_de_descargas_requiere_sesion_de_analista(client):
    c, _ = client
    cuenta(c, 'lead@uni.pe')
    c.post('/api/auth/logout')
    cuenta(c, 'v@uni.pe', 'visitante')
    assert c.get('/api/downloads').status_code == 403


def test_no_se_puede_exceder_el_tope_de_descargas_por_hora(client, monkeypatch):
    monkeypatch.setenv('MAX_DOWNLOADS_PER_HOUR', '1')
    c, path = client
    cuenta(c, 'lead@uni.pe')
    seed(path)
    analisis = c.post('/api/analyses', json=selection()).json()
    url = f"/api/analyses/{analisis['id']}/exports/series"
    assert c.get(url).status_code == 200
    segunda = c.get(url)
    assert segunda.status_code == 429
    assert 'hora' in segunda.json()['detail'].lower()


def test_las_exportaciones_no_superan_el_tope_de_filas(client, monkeypatch):
    """WORK_PLAN §10, T1: 'máximo de filas por exportación', con mensaje claro."""
    monkeypatch.setenv('MAX_EXPORT_ROWS', '2')
    c, path = client
    cuenta(c, 'lead@uni.pe')
    seed(path)
    analisis = c.post('/api/analyses', json=selection()).json()
    respuesta = c.get(f"/api/analyses/{analisis['id']}/exports/detections")
    assert respuesta.status_code == 413
    detalle = respuesta.json()['detail']
    assert '2' in detalle and 'fila' in detalle.lower()
    # Una exportación rechazada no debe aparecer en el historial.
    assert c.get('/api/downloads').json() == []


def test_el_tope_de_filas_no_afecta_por_debajo_del_limite(client):
    c, path = client
    cuenta(c, 'lead@uni.pe')
    seed(path)
    analisis = c.post('/api/analyses', json=selection()).json()
    assert c.get(f"/api/analyses/{analisis['id']}/exports/detections").status_code == 200
    assert len(c.get('/api/downloads').json()) == 1
