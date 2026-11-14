"""T1 · Usuarios y gestión de descargas — WORK_PLAN.md §10, spec S1.

Cubre la celda B (autenticación, roles, tablas `users`/`downloads`/`audit_log`), la
protección de rutas y la regla de `nina/AGENTS.md`: el esquema nuevo nunca rompe una
base existente.
"""

from nina import store


def columnas(tabla):
    with store.database() as con:
        return {fila[0] for fila in con.execute(f'DESCRIBE {tabla}').fetchall()}


def test_store_crea_las_tablas_de_cuentas_descargas_y_auditoria(client):
    _, _ = client
    with store.database() as con:
        tablas = {
            fila[0]
            for fila in con.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_schema='main'"
            ).fetchall()
        }
    assert {'users', 'sessions', 'downloads', 'audit_log'} <= tablas


def test_lotes_y_analisis_admiten_un_autor(client):
    _, _ = client
    assert 'created_by' in columnas('batches')
    assert 'created_by' in columnas('analyses')


def test_actualizar_el_esquema_no_destruye_una_base_existente(client):
    """Una base creada con el esquema viejo se amplía conservando sus filas (nina/AGENTS)."""
    _, _ = client
    with store.database() as con:
        con.execute("INSERT INTO batches (id, filename, source) VALUES ('lote-viejo','f.csv','modis')")
        con.execute('ALTER TABLE batches DROP COLUMN created_by')
        con.execute(
            "INSERT INTO analyses (id, selection, result, created_at) "
            "VALUES ('analisis-viejo','{}','{}','2026-01-01')"
        )
        con.execute('ALTER TABLE analyses DROP COLUMN created_by')
    store.initialize()
    with store.database() as con:
        assert con.execute('SELECT count(*) FROM batches').fetchone()[0] == 1
        assert con.execute('SELECT count(*) FROM analyses').fetchone()[0] == 1
    assert 'created_by' in columnas('batches')
    assert 'created_by' in columnas('analyses')


def test_sin_cuentas_no_se_puede_importar_sincronizar_adquirir_ni_entrenar(client):
    c, _ = client
    objetivos = [
        ('post', '/api/models/train', {}),
        ('post', '/api/sync', {'start': '2026-01-01'}),
        ('post', '/api/acquisitions', {}),
        ('post', '/api/acquisitions/month', {'product': 'MODIS_NRT', 'year': 2026, 'month': 1}),
    ]
    for metodo, ruta, cuerpo in objetivos:
        respuesta = getattr(c, metodo)(ruta, json=cuerpo)
        assert respuesta.status_code == 401, ruta


def test_el_upload_de_importacion_tambien_esta_protegido(client):
    c, _ = client
    respuesta = c.post(
        '/api/import',
        files={'file': ('f.csv', b'latitude,longitude\n-9,-75\n', 'text/csv')},
        data={'source': 'modis'},
    )
    assert respuesta.status_code == 401


def test_exportar_requiere_una_sesion(client):
    c, _ = client
    assert c.get('/api/analyses/desconocido/exports/series').status_code == 401
    assert c.get('/api/analyses/desconocido/exports/detections').status_code == 401


def test_el_primer_registro_se_vuelve_admin_y_no_expone_el_hash(client):
    c, _ = client
    respuesta = c.post('/api/auth/register', json={'email': 'lead@uni.pe', 'password': 'secreta-1234'})
    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo['role'] == 'admin'
    assert 'password' not in cuerpo and 'password_hash' not in cuerpo
    assert c.get('/api/auth/me').json()['email'] == 'lead@uni.pe'


def test_nadie_mas_se_puede_autoproclamar_admin(client):
    c, _ = client
    c.post('/api/auth/register', json={'email': 'lead@uni.pe', 'password': 'secreta-1234'})
    respuesta = c.post(
        '/api/auth/register',
        json={'email': 'infiltrado@uni.pe', 'password': 'secreta-1234', 'role': 'admin'},
    )
    assert respuesta.status_code == 403


def test_un_visitante_no_puede_importar_ni_exportar(client):
    c, _ = client
    c.post('/api/auth/register', json={'email': 'lead@uni.pe', 'password': 'secreta-1234'})
    c.post('/api/auth/logout')
    c.post('/api/auth/register', json={'email': 'v@uni.pe', 'password': 'secreta-1234', 'role': 'visitante'})
    assert c.get('/api/auth/me').json()['role'] == 'visitante'
    assert c.post('/api/models/train').status_code == 403
    assert c.get('/api/analyses/desconocido/exports/series').status_code == 403


def test_un_analista_puede_exportar_pero_no_importar(client):
    c, _ = client
    c.post('/api/auth/register', json={'email': 'lead@uni.pe', 'password': 'secreta-1234'})
    c.post('/api/auth/logout')
    c.post('/api/auth/register', json={'email': 'an@uni.pe', 'password': 'secreta-1234', 'role': 'analista'})
    # El guard de exportación deja pasar al analista: llega al 404 del análisis inexistente.
    assert c.get('/api/analyses/desconocido/exports/series').status_code == 404
    assert c.post('/api/models/train').status_code == 403


def test_login_valida_la_contrasena_y_cierra_sesion(client):
    c, _ = client
    c.post('/api/auth/register', json={'email': 'a@uni.pe', 'password': 'secreta-1234'})
    assert c.post('/api/auth/login', json={'email': 'a@uni.pe', 'password': 'incorrecta-99'}).status_code == 401
    assert c.post('/api/auth/login', json={'email': 'nobody@uni.pe', 'password': 'secreta-1234'}).status_code == 401
    assert c.post('/api/auth/login', json={'email': 'a@uni.pe', 'password': 'secreta-1234'}).status_code == 200
    assert c.get('/api/auth/me').status_code == 200
    c.post('/api/auth/logout')
    assert c.get('/api/auth/me').status_code == 401


def test_un_contrasena_corta_se_rechaza(client):
    c, _ = client
    respuesta = c.post('/api/auth/register', json={'email': 'corto@uni.pe', 'password': '123'})
    assert respuesta.status_code == 422
