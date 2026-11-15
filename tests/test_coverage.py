"""T2 · Celda A — fechas de cobertura reales por sensor, desde la base.

WORK_PLAN §10, T2: nada anterior al primer dato del sensor; nada en el
futuro (incluida la cobertura declarada de una importación); rango máximo
configurable con `FIRMS_MAX_DAY_RANGE`.

El límite *posterior* al último día disponible pertenece a las consultas de
rango libre (T3), no a las descargas: pedir datos nuevos es justamente el
propósito de `/api/sync`.
"""

from nina import store
from test_nina import seed
from test_validation import admin, rechazo, seleccion

CONTRASENA = 'secreta-1234'


def observacion(source, cuando):
    """Una fila directa en la base.

    A la celda A le importa la cobertura que hay en la base, no la ingesta
    (que tiene sus propios tests): `fixture_csv` no produce un CSV que
    `ingest_file` acepte como VIIRS.
    """
    with store.database() as con:
        con.execute(
            'INSERT INTO observations (id, source, platform, acquired, latitude, longitude) '
            'VALUES (?,?,?,?,?,?)',
            [f'{source}-{cuando}', source, 'all', f'{cuando} 00:00:00', -9.0, -75.0],
        )


def subir(c, **datos):
    cuerpo = {'source': 'modis', **{k: v for k, v in datos.items() if v is not None}}
    return c.post(
        '/api/import',
        files={'file': ('f.csv', b'latitude,longitude\n-9,-75\n', 'text/csv')},
        data={k: str(v) for k, v in cuerpo.items()},
    )


def test_las_fechas_de_cobertura_se_calculan_desde_la_base(client):
    """Celda A: cobertura real por sensor, no fechas codificadas."""
    c, path = client
    seed(path)
    fuentes = c.get('/api/status').json()['sources']
    modis = [f for f in fuentes if f['source'] == 'modis']
    assert modis, 'el seed no trajo filas para modis'
    primera = min(f['first_date'] for f in modis)
    ultima = max(f['last_date'] for f in modis)
    assert str(primera).startswith('2015-09-03'), primera
    assert str(ultima).startswith('2025-09-03'), ultima

    cobertura = store.cobertura('modis')
    assert cobertura['first_date'] is not None
    assert str(cobertura['first_date'])[:10] == '2015-09-03'
    assert str(cobertura['last_date'])[:10] == '2025-09-03'


def test_un_sensor_sin_datos_no_tiene_cobertura(client):
    """Sin filas no hay contra qué acotar: la validación no debe reventar."""
    c, _ = client
    vacia = store.cobertura('viirs-jpss2')
    assert vacia == {'first_date': None, 'last_date': None}


def test_no_se_pide_un_sensor_anterior_a_su_primer_dato(client):
    """§10 T2/A: 'nada anterior al primer dato del sensor'."""
    c, path = client
    admin(c)
    seed(path)
    cuerpo = rechazo(
        c.post('/api/sync', json={'source': 'MODIS_NRT', 'start': '2010-01-01'}),
        'coverage_before_start',
    )
    assert cuerpo['detail']


def test_una_fecha_dentro_de_la_cobertura_pasa_la_validacion(client):
    c, path = client
    admin(c)
    seed(path)
    respuesta = c.post('/api/sync', json={'source': 'MODIS_NRT', 'start': '2020-01-01'})
    # La validación pasó: lo que frene después es la ausencia de FIRMS_MAP_KEY.
    assert respuesta.status_code in (200, 409), respuesta.text


def test_un_sensor_sin_filas_en_la_base_no_se_rechaza_por_cobertura(client):
    c, _ = client
    admin(c)
    respuesta = c.post('/api/sync', json={'source': 'VIIRS_NOAA21_NRT', 'start': '2026-01-01'})
    assert respuesta.status_code in (200, 409), respuesta.text


def test_no_se_pide_un_producto_de_un_sensor_anterior_a_su_cobertura(client):
    """§10 T2: 'NOAA-21 only from 2024' se deriva de su cobertura real."""
    c, _ = client
    admin(c)
    observacion('viirs-jpss2', '2024-09-03')
    assert str(store.cobertura('viirs-jpss2')['first_date']).startswith('2024-09-03')
    cuerpo = rechazo(
        c.post(
            '/api/acquisitions',
            json={'products': ['VIIRS_NOAA21_NRT'], 'start': '2020-01-01'},
        ),
        'coverage_before_start',
    )
    assert cuerpo['detail']
    # Dentro de la cobertura sí pasa la validación (lo que frene después es la clave).
    assert (
        c.post(
            '/api/acquisitions',
            json={'products': ['VIIRS_NOAA21_NRT'], 'start': '2026-01-01'},
        ).status_code
        in (200, 409)
    )


def test_no_se_pide_un_archivo_mensual_anterior_a_la_cobertura(client):
    c, path = client
    admin(c)
    seed(path)
    cuerpo = rechazo(
        c.post(
            '/api/acquisitions/month',
            json={'product': 'MODIS_NRT', 'year': 2005, 'month': 3},
        ),
        'coverage_before_start',
    )
    assert cuerpo['detail']


def test_la_cobertura_declarada_en_una_importacion_no_puede_ser_futura(client):
    """Gap detectado por el verificador: `coverage_start` futuro se aceptaba."""
    c, _ = client
    admin(c)
    cuerpo = rechazo(subir(c, coverage_start='2030-01-01'), 'date_future')
    assert cuerpo['detail']


def test_la_cobertura_declarada_con_rango_invertido_da_date_range(client):
    """§10 T2: 'start ≤ end' — única superficie con las dos fechas hoy."""
    c, _ = client
    admin(c)
    cuerpo = rechazo(
        subir(c, coverage_start='2026-05-01', coverage_end='2026-01-01'),
        'date_range',
    )
    assert cuerpo['detail']


def test_el_numero_maximo_de_dias_es_configurable(client, monkeypatch):
    """§10 T2: 'configurable maximum range' → `FIRMS_MAX_DAY_RANGE`."""
    from nina.errors import dias_maximos

    assert dias_maximos() == 5  # el valor de .env.example
    monkeypatch.setenv('FIRMS_MAX_DAY_RANGE', '3')
    assert dias_maximos() == 3

    c, _ = client
    admin(c)
    rechazo(c.post('/api/sync', json={'start': '2026-01-01', 'days': 5}), 'days_range')
    assert c.post('/api/sync', json={'start': '2026-01-01', 'days': 3}).status_code in (200, 409)

    monkeypatch.setenv('FIRMS_MAX_DAY_RANGE', 'abc')
    assert dias_maximos() == 5  # valor inválido → predeterminado, nunca un 500


def test_las_reglas_de_cobertura_dejan_el_resto_intacto(client):
    """Regresión: la matriz de roles y los códigos existentes no cambian."""
    c, _ = client
    assert c.get('/api/downloads').status_code == 401
    rechazo(c.post('/api/analyses', json=seleccion(selected_month=13)), 'month_range')
