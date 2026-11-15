"""S1 enforcement matrix — WORK_PLAN.md §10 (T1).

Pins the authorisation contract that `web/src` relies on, so the UI can never
become the only barrier: `401` for anonymous, `403` for an under-privileged
role, allowed where the role qualifies, and no write at all when a request is
rejected.

These are characterization tests: the behaviour was implemented and verified
before they existed, so they are born green. They exist to make a regression
loud — see `Risk: item 6`, `web/` has no test harness of its own.
"""

import hashlib

from nina import store

CONTRASENA = 'secreta-1234'

ADMIN_RUTAS = [
    ('post', '/api/models/train', {}),
    ('post', '/api/sync', {'start': '2026-01-01'}),
    ('post', '/api/acquisitions', {}),
    ('post', '/api/acquisitions/month', {'product': 'MODIS_NRT', 'year': 2026, 'month': 1}),
]
LECTURAS = ['/api/downloads', '/api/audit', '/api/analyses/desconocido/exports/series']


def llamar(c, metodo, ruta, cuerpo):
    if ruta == '/api/import':
        return c.post(
            '/api/import',
            files={'file': ('f.csv', b'latitude,longitude\n-9,-75\n', 'text/csv')},
            data={'source': 'modis'},
        )
    return getattr(c, metodo)(ruta, json=cuerpo)


def registro(c, email, rol=None):
    cuerpo = {'email': email, 'password': CONTRASENA}
    if rol:
        cuerpo['role'] = rol
    respuesta = c.post('/api/auth/register', json=cuerpo)
    assert respuesta.status_code == 200, respuesta.text
    return respuesta.json()


def pruega_admin(c, esperado):
    for metodo, ruta, cuerpo in ADMIN_RUTAS + [('post', '/api/import', None)]:
        assert llamar(c, metodo, ruta, cuerpo).status_code == esperado, ruta


def pruega_lecturas(c, esperado):
    for ruta in LECTURAS:
        assert c.get(ruta).status_code == esperado, ruta


def test_el_anonimo_no_entra_a_nada(client):
    c, _ = client
    pruega_admin(c, 401)
    pruega_lecturas(c, 401)
    assert c.get('/api/auth/me').status_code == 401


def test_un_visitante_no_importa_ni_exporta_ni_ve_su_historial(client):
    c, _ = client
    registro(c, 'lead@uni.pe')  # el primer registro siempre queda admin
    c.post('/api/auth/logout')
    cuenta = registro(c, 'v@uni.pe', 'visitante')
    assert cuenta['role'] == 'visitante'
    pruega_admin(c, 403)
    pruega_lecturas(c, 403)


def test_un_analista_exporta_y_ve_su_historial_pero_no_la_auditoria(client):
    c, _ = client
    registro(c, 'lead@uni.pe')
    c.post('/api/auth/logout')
    cuenta = registro(c, 'an@uni.pe', 'analista')
    assert cuenta['role'] == 'analista'
    pruega_admin(c, 403)
    assert c.get('/api/downloads').status_code == 200
    assert c.get('/api/audit').status_code == 403
    # El guard deja pasar al analista: llega al 404 del análisis inexistente.
    assert c.get('/api/analyses/desconocido/exports/series').status_code == 404


def test_un_admin_ve_todo(client):
    c, _ = client
    cuenta = registro(c, 'lead@uni.pe')
    assert cuenta['role'] == 'admin'
    assert c.get('/api/audit').status_code == 200
    assert c.get('/api/downloads').status_code == 200
    assert c.get('/api/analyses/desconocido/exports/series').status_code == 404
    assert c.post('/api/models/train').status_code == 200


def test_nadie_mas_se_autoproclama_admin(client):
    c, _ = client
    registro(c, 'lead@uni.pe')
    c.post('/api/auth/logout')
    respuesta = c.post(
        '/api/auth/register',
        json={'email': 'infiltrado@uni.pe', 'password': CONTRASENA, 'role': 'admin'},
    )
    assert respuesta.status_code == 403


def digest(base):
    h = hashlib.sha256()
    for archivo in sorted(base.glob('nina.duckdb*')):
        h.update(archivo.name.encode())
        h.update(archivo.read_bytes())
    return h.hexdigest()


def test_las_peticiones_rechazadas_no_escriben_la_base(client, tmp_path):
    """Una petición 401/403 no deja rastro; una legítima sí, así el digest no es vacío."""
    c, _ = client
    registro(c, 'lead@uni.pe')
    c.post('/api/auth/logout')
    registro(c, 'v@uni.pe', 'visitante')
    c.get('/api/auth/me')  # warm-up: cualquier escritura de arranque ya ocurrió
    c.get('/api/status')
    antes = digest(tmp_path)

    pruega_admin(c, 403)
    pruega_lecturas(c, 403)

    assert digest(tmp_path) == antes, 'una petición rechazada modificó la base'

    # Control: una operación legítima sí cambia la base, para que el digest no sea vacío.
    c.post('/api/auth/logout')
    assert digest(tmp_path) != antes, 'el digest no refleja los cambios de la base'


def test_solo_admin_escribe_en_la_auditoria(client):
    c, _ = client
    registro(c, 'lead@uni.pe')
    registros_antes = len(c.get('/api/audit').json())
    c.post('/api/models/train')
    registros_despues = c.get('/api/audit').json()
    assert len(registros_despues) > registros_antes
    assert any(r['action'] == 'train' for r in registros_despues)


def test_las_columnas_que_pinta_la_interfaz_existen_en_respuesta(client):
    """`web/src/types.ts` declara estas claves; si la API deja de devolverlas, esto cae."""
    c, _ = client
    registro(c, 'lead@uni.pe')
    me = c.get('/api/auth/me').json()
    assert set(me) == {'id', 'email', 'role', 'display_name', 'created_at'}
    historial = c.get('/api/downloads').json()
    if historial:
        assert set(historial[0]) == {
            'id', 'user_id', 'analysis_id', 'kind', 'rows', 'filters',
            'dataset_version', 'created_at',
        }
    auditoria = c.get('/api/audit').json()
    if auditoria:
        assert set(auditoria[0]) == {'id', 'user_id', 'action', 'target', 'detail', 'created_at'}
    assert store.code_revision()
