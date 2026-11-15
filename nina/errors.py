"""Contrato de errores — WORK_PLAN.md §10, T2 (spec S2).

Todo `422` sale como *problem+json* (`type`, `title`, `status`, `code`, `detail`)
con un `code` estable por regla. El spec pide que el mensaje esté **en el
idioma de la interfaz**: el cliente manda `Accept-Language` (lo añade
`web/src/api.ts` desde `i18n.ts`) y, si nadie lo manda, se responde en
inglés, que es el idioma con el que arranca la aplicación.

Las reglas propias suben su code con `PydanticCustomError`; el resto traduce
el `type` de Pydantic. Cada mensaje existe en los dos idiomas.
"""

import json

from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from starlette.requests import Request
from starlette.responses import JSONResponse

TIPO = 'about:blank'
INDICE_EN, INDICE_ES = 0, 1

# Codes que este proyecto lanza a mano: su `type` ya es el `code`.
REGLAS = {
    'year_range',
    'year_bounds',
    'month_range',
    'sensor_platform',
    'department_unknown',
    'scope_mismatch',
    'geometry_required',
    'geometry_invalid',
    'date_future',
    'days_range',
}

# code → (english, español)
REGLAS_MENSAJE = {
    'month_range': ('The month must be between 1 and 12', 'El mes debe estar entre 1 y 12'),
    'year_bounds': ('Years must be between 2000 and 2100', 'Los años deben estar entre 2000 y 2100'),
    'year_range': (
        'The selected year must be within the range',
        'El año seleccionado debe estar dentro del rango',
    ),
    'sensor_platform': (
        'Aqua and Terra only exist on MODIS; use platform "all" with VIIRS',
        'Aqua y Terra solo existen en MODIS; usa la plataforma "all" con VIIRS',
    ),
    'department_unknown': ('Unknown department', 'Departamento desconocido'),
    'scope_mismatch': (
        'Regional divisions belong to the Peruvian archive',
        'Las divisiones regionales corresponden al archivo peruano',
    ),
    'geometry_required': (
        'Select a geometry for this area',
        'Selecciona una geometría para esta área',
    ),
    'geometry_invalid': (
        'Invalid polygon; use WGS84 geographic coordinates',
        'Polígono inválido; utiliza coordenadas geográficas WGS84',
    ),
    'date_future': ('The date cannot be in the future', 'La fecha no puede ser posterior a hoy'),
    'days_range': ('Days must be between 1 and 5', 'El número de días debe estar entre 1 y 5'),
}

# `type` de Pydantic → (code del proyecto, plantilla en inglés, plantilla en español).
# `{...}` se rellena con el `ctx` que Pydantic adjunta.
PYDANTIC = {
    'greater_than_equal': ('out_of_range', 'Must be >= {ge}.', 'Debe ser mayor o igual a {ge}.'),
    'less_than_equal': ('out_of_range', 'Must be <= {le}.', 'Debe ser menor o igual a {le}.'),
    'greater_than': ('out_of_range', 'Must be > {gt}.', 'Debe ser mayor que {gt}.'),
    'less_than': ('out_of_range', 'Must be < {lt}.', 'Debe ser menor que {lt}.'),
    'literal_error': ('not_allowed', 'Not allowed; expected {expected}.', 'Valor no permitido; se espera {expected}.'),
    'string_too_long': (
        'too_long',
        'The text exceeds {max_length} characters.',
        'El texto supera {max_length} caracteres.',
    ),
    'string_too_short': (
        'too_short',
        'The text needs at least {min_length} characters.',
        'El texto necesita al menos {min_length} caracteres.',
    ),
    'missing': ('required', 'A required field is missing.', 'Falta un campo obligatorio.'),
    'date_parsing': (
        'date_format',
        'The date must be ISO YYYY-MM-DD.',
        'La fecha debe tener formato ISO AAAA-MM-DD.',
    ),
    'date_from_datetime_parsing': (
        'date_format',
        'The date must be ISO YYYY-MM-DD.',
        'La fecha debe tener formato ISO AAAA-MM-DD.',
    ),
    'int_parsing': ('not_a_number', 'Expected an integer.', 'Se esperaba un número entero.'),
    'int_type': ('not_a_number', 'Expected an integer.', 'Se esperaba un número entero.'),
    'int_from_float': (
        'not_an_integer',
        'Expected a whole number without decimals.',
        'Se esperaba un número entero sin decimales.',
    ),
    'string_type': ('not_a_string', 'Expected text.', 'Se esperaba texto.'),
    'dict_type': ('not_an_object', 'Expected an object.', 'Se esperaba un objeto.'),
    'model_attributes_type': ('not_an_object', 'Expected an object.', 'Se esperaba un objeto.'),
    'model_type': ('not_an_object', 'Expected an object.', 'Se esperaba un objeto.'),
    'list_type': ('not_a_list', 'Expected a list.', 'Se esperaba una lista.'),
    'json_invalid': ('malformed_body', 'The body is not valid JSON.', 'La petición no es JSON válido.'),
    'json_type': ('malformed_body', 'The body is not valid JSON.', 'La petición no es JSON válido.'),
    'extra_forbidden': (
        'unexpected_field',
        'Unexpected field.',
        'Campo no esperado.',
    ),
    'too_short': (
        'too_short',
        'The text needs at least {min_length} characters.',
        'El texto necesita al menos {min_length} caracteres.',
    ),
    'string_pattern_mismatch': (
        'pattern',
        'The value does not match the required format.',
        'El valor no cumple el formato requerido.',
    ),
}

GENERICO = (
    'Invalid input',
    'Entrada inválida',
)

TITULOS = {
    400: ('Bad request', 'Petición inválida'),
    401: ('Authentication required', 'Se requiere iniciar sesión'),
    403: ('Operation not allowed', 'Operación no permitida'),
    404: ('Not found', 'No encontrado'),
    409: ('Conflict', 'Conflicto'),
    413: ('Payload too large', 'Demasiado grande'),
    422: ('Invalid input', 'Entrada inválida'),
    429: ('Rate limit reached', 'Límite alcanzado'),
    500: ('Internal error', 'Error interno'),
}

CODIGOS_HTTP = {
    400: 'bad_request',
    401: 'unauthorized',
    403: 'forbidden',
    404: 'not_found',
    409: 'conflict',
    413: 'payload_too_large',
    422: 'invalid_input',
    429: 'too_many_requests',
    500: 'internal_error',
}


def idioma(request: Request | None) -> int:
    """Índice en la tupla (english, español). Sin cabecera → inglés, como i18n.ts."""
    if request is None:
        return INDICE_EN
    cabecera = (request.headers.get('accept-language') or '').lower()
    for parte in cabecera.split(','):
        codigo = parte.split(';')[0].strip()
        if codigo.startswith('es'):
            return INDICE_ES
        if codigo.startswith('en'):
            return INDICE_EN
    return INDICE_EN


def problema(status: int, code: str, detalle: str, indice: int = INDICE_EN) -> dict:
    titulo = TITULOS.get(status)
    return {
        'type': TIPO,
        'title': (titulo[0], titulo[1])[indice] if titulo else GENERICO[indice],
        'status': status,
        'code': code,
        'detail': detalle,
    }


def desde_pydantic(error: dict, indice: int = INDICE_EN) -> tuple[str, str]:
    """Convierte un error de validación de Pydantic en `(code, mensaje localizado)`."""
    tipo = str(error.get('type', 'invalid'))
    if tipo in REGLAS:
        par = REGLAS_MENSAJE.get(tipo)
        if par:
            return tipo, par[indice]
        # Una regla propia cuya traducción no esté en la tabla: usar el texto literal.
        return tipo, str(error.get('msg') or GENERICO[indice])
    entrada = PYDANTIC.get(tipo)
    if entrada:
        code, plantilla_en, plantilla_es = entrada
        plantilla = (plantilla_en, plantilla_es)[indice]
        try:
            return code, plantilla.format(**(error.get('ctx') or {}))
        except (KeyError, IndexError, ValueError):
            return code, plantilla.split('{')[0].rstrip(' .;') + '.' if '{' in plantilla else plantilla
    if tipo == 'value_error':
        # Un ValueError a secas: conservar su texto, quitando el prefijo de Pydantic.
        crudo = str(error.get('msg') or '')
        crudo = crudo.removeprefix('Value error,').strip()
        return 'value_error', crudo or GENERICO[indice]
    ubicacion = '.'.join(str(p) for p in error.get('loc', ()) if p != 'body')
    code = tipo
    return code, (f'Invalid input at {ubicacion}' if ubicacion else GENERICO[0]) if indice == INDICE_EN else (
        f'Entrada inválida en {ubicacion}' if ubicacion else GENERICO[1]
    )


def instalar(app: FastAPI) -> None:
    @app.exception_handler(RequestValidationError)
    async def _validacion(request: Request, exc: RequestValidationError):
        indice = idioma(request)
        errores = exc.errors()
        code, detalle = (
            desde_pydantic(errores[0], indice) if errores else ('invalid_input', GENERICO[indice])
        )
        return JSONResponse(status_code=422, content=problema(422, code, detalle, indice))

    @app.exception_handler(HTTPException)
    async def _http(request: Request, exc: HTTPException):
        indice = idioma(request)
        code = getattr(exc, 'code', None) or CODIGOS_HTTP.get(
            exc.status_code, f'http_{exc.status_code}'
        )
        detalle = exc.detail if isinstance(exc.detail, str) else json.dumps(exc.detail, ensure_ascii=False)
        return JSONResponse(
            status_code=exc.status_code,
            content=problema(exc.status_code, code, detalle, indice),
            headers=exc.headers,
        )

    _declarar_openapi(app)


def _esquema_problema() -> dict:
    return {
        'type': 'object',
        'required': ['type', 'title', 'status', 'code', 'detail'],
        'properties': {
            'type': {'type': 'string', 'example': TIPO},
            'title': {'type': 'string'},
            'status': {'type': 'integer'},
            'code': {'type': 'string', 'example': 'month_range'},
            'detail': {'type': 'string'},
        },
    }


def _declarar_openapi(app: FastAPI) -> None:
    """FastAPI documenta el 422 viejo (`{detail: [...]}`) aunque el manejador ya
    no lo emita; el contrato es `openapi.json`, así que se sobrescribe aquí."""

    original = app.openapi

    def openapi():
        documento = original()
        esquemas = documento.setdefault('components', {}).setdefault('schemas', {})
        esquemas['Problem'] = _esquema_problema()
        for operaciones in documento.get('paths', {}).values():
            for operacion in operaciones.values():
                if not isinstance(operacion, dict):
                    continue
                respuesta = (operacion.get('responses') or {}).get('422')
                if isinstance(respuesta, dict):
                    contenido = respuesta.setdefault('content', {}).setdefault(
                        'application/json', {}
                    )
                    contenido['schema'] = {'$ref': '#/components/schemas/Problem'}
        return documento

    app.openapi = openapi
    app.openapi_schema = None
