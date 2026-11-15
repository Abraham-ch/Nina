"""T2 · Validaciones de entrada — WORK_PLAN.md §10, spec S2.

Cada regla rechaza con `422`, cuerpo *problem+json* (`type`, `title`, `status`,
`code`, `detail`) y un `code` estable por regla. `detail` es siempre un string
en español: `web/src/api.ts` lo pinta tal cual, sin serializarlo.

"Terminado cuando": cada regla tiene una prueba que envía un valor inválido y
recibe su `code`.
"""

CONTRASENA = 'secreta-1234'


def admin(c):
    """El guard de rol corre antes que la validación: sin sesión nunca llegamos al 422."""
    r = c.post('/api/auth/register', json={'email': 'lead@uni.pe', 'password': CONTRASENA})
    assert r.status_code == 200, r.text
    return r.json()


def seleccion(**kw):
    base = {
        'year_start': 2018,
        'year_end': 2025,
        'selected_year': 2025,
        'selected_month': 9,
    }
    base.update(kw)
    return base


def rechazo(respuesta, code):
    """Devuelve el cuerpo de un 422 problem+json validado contra su `code`."""
    assert respuesta.status_code == 422, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo['status'] == 422, cuerpo
    assert cuerpo['type'], cuerpo
    assert cuerpo['title'], cuerpo
    assert cuerpo['code'] == code, cuerpo
    assert isinstance(cuerpo['detail'], str) and cuerpo['detail'].strip(), cuerpo
    assert cuerpo['detail'] != cuerpo['code'], cuerpo
    return cuerpo


def test_el_error_de_validacion_es_problem_json(client):
    c, _ = client
    cuerpo = rechazo(c.post('/api/analyses', json=seleccion(selected_month=13)), 'month_range')
    assert '12' in cuerpo['detail'], cuerpo


def test_el_mensaje_espanol_es_un_string_que_la_interfaz_puede_pintar(client):
    """`web/src/api.ts` hace `typeof body.detail === 'string' ? body.detail : stringify`."""
    c, _ = client
    cuerpo = rechazo(c.post('/api/analyses', json=seleccion(selected_month=0)), 'month_range')
    assert cuerpo['detail'] != 'undefined'
    assert any(caracter.isalpha() for caracter in cuerpo['detail'])


def test_un_rango_de_anios_invertido_devuelve_su_code(client):
    c, _ = client
    cuerpo = rechazo(
        c.post('/api/analyses', json=seleccion(year_start=2025, year_end=2018)),
        'year_range',
    )
    assert cuerpo['detail']


def test_un_anio_fuera_del_rango_devuelve_su_code(client):
    c, _ = client
    cuerpo = rechazo(c.post('/api/analyses', json=seleccion(year_start=1999)), 'year_bounds')
    assert cuerpo['detail']


def test_un_anio_fuera_del_intervalo_seleccionado_devuelve_su_code(client):
    c, _ = client
    cuerpo = rechazo(
        c.post('/api/analyses', json=seleccion(selected_year=2030, year_start=2018, year_end=2025)),
        'year_range',
    )
    assert cuerpo['detail']


def test_aqua_y_terra_solo_pueden_ir_con_modis(client):
    """§10 T2 · Coherencia de sensor: 'Aqua solo con MODIS'."""
    c, _ = client
    cuerpo = rechazo(
        c.post('/api/analyses', json=seleccion(source='viirs-jpss1', platform='Aqua')),
        'sensor_platform',
    )
    assert cuerpo['detail']
    # Un viirs con plataforma 'all' sigue siendo válido.
    respuesta = c.post('/api/analyses', json=seleccion(source='viirs-jpss1', platform='all'))
    assert respuesta.status_code in (200, 409), respuesta.text


def test_una_fecha_futura_se_rechaza(client):
    """§10 T2 · Fechas: 'nada en el futuro'."""
    c, _ = client
    admin(c)
    cuerpo = rechazo(
        c.post('/api/acquisitions', json={'start': '2030-01-01'}),
        'date_future',
    )
    assert cuerpo['detail']


def test_un_numero_de_dias_fuera_del_limite_devuelve_su_code(client):
    c, _ = client
    admin(c)
    cuerpo = rechazo(c.post('/api/sync', json={'start': '2026-01-01', 'days': 9}), 'days_range')
    assert cuerpo['detail']


def test_una_fecha_no_iso_se_rechaza(client):
    c, _ = client
    admin(c)
    assert c.post('/api/sync', json={'start': '01/01/2026'}).status_code == 422


def test_una_geometria_invalida_devuelve_su_code(client):
    c, _ = client
    cuerpo = rechazo(
        c.post(
            '/api/analyses',
            json=seleccion(scope='custom', geometry={'type': 'Point', 'coordinates': [0, 0]}),
        ),
        'geometry_invalid',
    )
    assert cuerpo['detail']


def test_una_peticion_rechazada_por_regla_tambien_es_problem_json(client):
    """El 422 manual de `/api/import` (geometría) debe seguir la misma forma."""
    c, _ = client
    admin(c)
    respuesta = c.post(
        '/api/import',
        files={'file': ('f.csv', b'latitude,longitude\n-9,-75\n', 'text/csv')},
        data={'source': 'modis', 'spatial_geometry': '{"type":"Point","coordinates":[0,0]}'},
    )
    cuerpo = rechazo(respuesta, 'invalid_input')
    assert cuerpo['detail']


def test_los_errores_que_no_son_de_validacion_conservan_su_status(client):
    """Regresión: los códigos existentes no cambian de significado."""
    c, _ = client
    assert c.get('/api/downloads').status_code == 401
    assert c.post('/api/auth/login', json={'email': 'x@y.pe', 'password': 'mala'}).status_code == 401
    assert c.get('/api/analyses/desconocido/exports/series').status_code == 401
    assert c.get('/api/analyses/desconocido').status_code == 404
    assert c.post('/api/sync', json={'start': '2026-01-01'}).status_code in (401, 409)


def test_openapi_documenta_el_422_como_problem_json():
    """El contrato dice `code`; el 422 por defecto de FastAPI decía `{detail: [...]}`."""
    import json
    from pathlib import Path

    espec = json.loads((Path(__file__).resolve().parent.parent / 'openapi.json').read_text('utf-8'))
    esquemas = espec['components']['schemas']
    assert 'Problem' in esquemas, 'falta el esquema Problem'
    assert {'type', 'title', 'status', 'code', 'detail'} <= set(esquemas['Problem']['properties'])
    for ruta, operaciones in espec['paths'].items():
        for metodo, operacion in operaciones.items():
            if not isinstance(operacion, dict):
                continue
            respuesta = (operacion.get('responses') or {}).get('422')
            if isinstance(respuesta, dict):
                esquema = respuesta.get('content', {}).get('application/json', {}).get('schema', {})
                assert esquema.get('$ref') == '#/components/schemas/Problem', f'{metodo} {ruta}'
