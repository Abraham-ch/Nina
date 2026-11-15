"""Contrato de errores — WORK_PLAN.md §10, T2 (spec S2).

Todo `422` sale como *problem+json* (`type`, `title`, `status`, `code`, `detail`)
con un `code` estable por regla y el mensaje en español, que `web/src/api.ts`
pinta tal cual. Las reglas propias suben su code con `PydanticCustomError`;
el resto traduce el `type` de Pydantic.
"""

import json
from datetime import date

from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from starlette.requests import Request
from starlette.responses import JSONResponse

TIPO = 'about:blank'

# Codes que este proyecto lanza a mano: su `type` ya es el `code`.
REGLAS = {
    'year_range',
    'year_bounds',
    'month_range',
    'sensor_platform',
    'geometry_invalid',
    'date_future',
    'days_range',
}

# `type` de Pydantic → code estable del proyecto.
CODIGOS = {
    'greater_than_equal': 'out_of_range',
    'less_than_equal': 'out_of_range',
    'greater_than': 'out_of_range',
    'less_than': 'out_of_range',
    'literal_error': 'not_allowed',
    'string_too_long': 'too_long',
    'string_too_short': 'too_short',
    'missing': 'required',
    'date_parsing': 'date_format',
    'date_from_datetime_parsing': 'date_format',
    'int_parsing': 'not_a_number',
    'int_type': 'not_a_number',
    'string_type': 'not_a_string',
    'dict_type': 'not_an_object',
    'model_attributes_type': 'not_an_object',
    'list_type': 'not_a_list',
    'json_invalid': 'malformed_body',
    'json_type': 'malformed_body',
    'extra_forbidden': 'unexpected_field',
    'model_type': 'not_an_object',
    'model_attributes_type': 'not_an_object',
}

# Mensajes en español; `{...}` se rellena con el `ctx` que Pydantic adjunta.
MENSAJES = {
    'greater_than_equal': 'Debe ser mayor o igual a {ge}.',
    'less_than_equal': 'Debe ser menor o igual a {le}.',
    'greater_than': 'Debe ser mayor que {gt}.',
    'less_than': 'Debe ser menor que {lt}.',
    'literal_error': 'Valor no permitido; se espera {expected}.',
    'string_too_long': 'El texto supera {max_length} caracteres.',
    'string_too_short': 'El texto necesita al menos {min_length} caracteres.',
    'missing': 'Falta un campo obligatorio.',
    'date_parsing': 'La fecha debe tener formato ISO AAAA-MM-DD.',
    'int_parsing': 'Se esperaba un número entero.',
    'int_type': 'Se esperaba un número entero.',
    'string_type': 'Se esperaba texto.',
    'dict_type': 'Se esperaba un objeto.',
    'model_attributes_type': 'Se esperaba un objeto.',
    'list_type': 'Se esperaba una lista.',
    'json_invalid': 'La petición no es JSON válido.',
}

TITULOS = {
    400: 'Petición inválida',
    401: 'Se requiere iniciar sesión',
    403: 'Operación no permitida',
    404: 'No encontrado',
    409: 'Conflicto',
    413: 'Demasiado grande',
    422: 'Entrada inválida',
    429: 'Límite alcanzado',
    500: 'Error interno',
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


def problema(status: int, code: str, detalle: str) -> dict:
    return {
        'type': TIPO,
        'title': TITULOS.get(status, 'Entrada inválida'),
        'status': status,
        'code': code,
        'detail': detalle,
    }


def desde_pydantic(error: dict) -> tuple[str, str]:
    """Convierte un error de validación de Pydantic en `(code, mensaje en español)`."""
    tipo = str(error.get('type', 'invalid'))
    if tipo in REGLAS:
        return tipo, str(error.get('msg') or 'Valor no válido')
    code = CODIGOS.get(tipo, tipo)
    plantilla = MENSAJES.get(tipo)
    if plantilla:
        try:
            return code, plantilla.format(**(error.get('ctx') or {}))
        except (KeyError, IndexError, ValueError):
            return code, plantilla.split('{')[0].rstrip()
    ubicacion = '.'.join(str(p) for p in error.get('loc', ()) if p != 'body')
    return code, f'Entrada inválida en {ubicacion}' if ubicacion else 'Entrada inválida'


def instalar(app: FastAPI) -> None:
    @app.exception_handler(RequestValidationError)
    async def _validacion(request: Request, exc: RequestValidationError):
        errores = exc.errors()
        code, detalle = desde_pydantic(errores[0]) if errores else ('invalid_input', 'Entrada inválida')
        return JSONResponse(status_code=422, content=problema(422, code, detalle))

    @app.exception_handler(HTTPException)
    async def _http(request: Request, exc: HTTPException):
        code = getattr(exc, 'code', None) or CODIGOS_HTTP.get(
            exc.status_code, f'http_{exc.status_code}'
        )
        detalle = exc.detail if isinstance(exc.detail, str) else json.dumps(exc.detail, ensure_ascii=False)
        return JSONResponse(
            status_code=exc.status_code,
            content=problema(exc.status_code, code, detalle),
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


def fecha_no_futura(valor: date | None, code: str = 'date_future') -> None:
    """Compartida por los modelos que aceptan fechas: nada en el futuro."""
    if valor is not None and valor > date.today():
        from pydantic_core import PydanticCustomError

        raise PydanticCustomError(code, 'La fecha no puede ser posterior a hoy')
