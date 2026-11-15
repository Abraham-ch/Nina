"""Autenticación, roles y sesiones — WORK_PLAN.md §10, tarea T1 (spec S1).

Contraseña con PBKDF2-SHA256 de la biblioteca estándar: no añade dependencias al
`requirements.txt`. La sesión vive en una cookie HttpOnly y también se acepta
`Authorization: Bearer`, para que la consola y los tests no dependan de cookies.

El primer usuario registrado siempre queda como `admin`, así el sistema nunca queda
sin una cuenta administrativa. A partir de ahí nadie puede auto-proclamarse admin.
"""

import hashlib
import json
import os
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import HTTPException, Request, Response
from pydantic import BaseModel, Field

from .store import database, now, rows

COOKIE = 'nina_session'
SESSION_DAYS = 30
MIN_PASSWORD = 8
_PBKDF2_ROUNDS = 600_000
DEFAULT_DOWNLOADS_PER_HOUR = 60
DEFAULT_EXPORT_ROWS = 1_000_000


class Register(BaseModel):
    email: str = Field(min_length=3, max_length=254, pattern=r'^[^@\s]+@[^@\s]+\.[^@\s]+$')
    password: str = Field(min_length=MIN_PASSWORD, max_length=200)
    role: Literal['visitante', 'analista', 'admin'] = 'analista'
    display_name: str | None = Field(default=None, max_length=80)


class Login(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=200)


def hash_password(password: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        'sha256', password.encode(), bytes.fromhex(salt), _PBKDF2_ROUNDS
    ).hex()
    return f'pbkdf2_sha256${_PBKDF2_ROUNDS}${salt}${digest}'


def verify_password(password: str, stored: str | None) -> bool:
    try:
        _, rounds, salt, digest = (stored or '').split('$')
        candidate = hashlib.pbkdf2_hmac(
            'sha256', password.encode(), bytes.fromhex(salt), int(rounds)
        ).hex()
    except (ValueError, TypeError):
        return False
    return secrets.compare_digest(candidate, digest)


def public(user: dict) -> dict:
    """Nunca se filtra el hash ni nada más allá del perfil."""
    return {
        'id': user['id'],
        'email': user['email'],
        'role': user['role'],
        'display_name': user.get('display_name'),
        'created_at': user.get('created_at'),
    }


def issue_token(connection, user_id: str) -> str:
    token = secrets.token_urlsafe(32)
    expires = (datetime.now(timezone.utc) + timedelta(days=SESSION_DAYS)).isoformat()
    connection.execute(
        'INSERT INTO sessions (token, user_id, created_at, expires_at) VALUES (?,?,?,?)',
        [token, user_id, now(), expires],
    )
    return token


def register(payload: Register) -> tuple[dict, str]:
    email = payload.email.strip().lower()
    with database() as c:
        total = c.execute('SELECT count(*) FROM users').fetchone()[0]
        if total == 0:
            role = 'admin'
        elif payload.role == 'admin':
            raise HTTPException(403, 'Solo el primer usuario se registra como administrador')
        else:
            role = payload.role
        if c.execute('SELECT 1 FROM users WHERE email=?', [email]).fetchone():
            raise HTTPException(409, 'Ese correo ya está registrado')
        identifier = uuid.uuid4().hex
        c.execute(
            'INSERT INTO users (id, email, password_hash, role, display_name, created_at) VALUES (?,?,?,?,?,?)',
            [identifier, email, hash_password(payload.password), role, payload.display_name, now()],
        )
        token = issue_token(c, identifier)
        user = rows(c, 'SELECT * FROM users WHERE id=?', [identifier])[0]
    return public(user), token


def login(payload: Login) -> tuple[dict, str]:
    email = payload.email.strip().lower()
    with database() as c:
        found = rows(c, 'SELECT * FROM users WHERE email=?', [email])
        if not found or not verify_password(payload.password, found[0]['password_hash']):
            raise HTTPException(401, 'Correo o contraseña incorrectos')
        token = issue_token(c, found[0]['id'])
        user = found[0]
    return public(user), token


def token_from(request: Request) -> str | None:
    token = request.cookies.get(COOKIE)
    if token:
        return token
    header = request.headers.get('authorization', '')
    return header[7:].strip() if header.lower().startswith('bearer ') else None


def current_user(request: Request) -> dict | None:
    token = token_from(request)
    if not token:
        return None
    with database() as c:
        found = rows(
            c,
            '''SELECT u.id, u.email, u.role, u.display_name, u.created_at
               FROM sessions s JOIN users u ON u.id = s.user_id
               WHERE s.token = ? AND s.expires_at > ?''',
            [token, now()],
        )
    return public(found[0]) if found else None


def clear_session(request: Request) -> None:
    token = token_from(request)
    if token:
        with database() as c:
            c.execute('DELETE FROM sessions WHERE token=?', [token])


def require(*roles: str):
    """Dependencia de autorización: sin sesión → 401; rol insuficiente → 403."""

    def dependency(request: Request) -> dict:
        user = current_user(request)
        if user is None:
            raise HTTPException(401, 'Se requiere iniciar sesión')
        if roles and user['role'] not in roles:
            raise HTTPException(403, 'Tu rol no permite esta operación')
        return user

    return dependency


def attach(response: Response, token: str, secure: bool = False) -> None:
    """`secure` sigue el esquema de la petición: en local por http sigue funcionando."""
    response.set_cookie(
        COOKIE,
        token,
        max_age=SESSION_DAYS * 86400,
        httponly=True,
        samesite='lax',
        path='/',
        secure=secure,
    )


def detach(response: Response) -> None:
    response.delete_cookie(COOKIE, path='/')


def optional():
    """Como `require()`, pero devuelve `None` en vez de 401.

    Los análisis se pueden crear sin sesión (son de consulta); cuando hay sesión, su
    autor queda guardado en `analyses.created_by`.
    """

    def dependency(request: Request) -> dict | None:
        return current_user(request)

    return dependency


def _env_int(name: str, default: int) -> int:
    """Un valor mal escrito en `.env` cae al predeterminado, nunca a un 500."""
    try:
        return max(1, int(os.getenv(name, str(default))))
    except (TypeError, ValueError):
        return default


def max_downloads_per_hour() -> int:
    return _env_int('MAX_DOWNLOADS_PER_HOUR', DEFAULT_DOWNLOADS_PER_HOUR)


def max_export_rows() -> int:
    return _env_int('MAX_EXPORT_ROWS', DEFAULT_EXPORT_ROWS)


def record_download(user_id, analysis_id, kind, count, filters, dataset_version) -> None:
    with database() as c:
        c.execute(
            'INSERT INTO downloads (id,user_id,analysis_id,kind,rows,filters,dataset_version,created_at) VALUES (?,?,?,?,?,?,?,?)',
            [uuid.uuid4().hex, user_id, analysis_id, kind, count,
             json.dumps(filters, ensure_ascii=False, default=str), dataset_version, now()],
        )


def downloads_for(user_id) -> list[dict]:
    with database() as c:
        return rows(c, 'SELECT * FROM downloads WHERE user_id=? ORDER BY created_at DESC LIMIT 200', [user_id])


def downloads_last_hour(user_id) -> int:
    desde = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    with database() as c:
        return c.execute(
            'SELECT count(*) FROM downloads WHERE user_id=? AND created_at>?', [user_id, desde]
        ).fetchone()[0]


def record_audit(user, action, target=None, detail=None) -> None:
    with database() as c:
        c.execute(
            'INSERT INTO audit_log (id,user_id,action,target,detail,created_at) VALUES (?,?,?,?,?,?)',
            [uuid.uuid4().hex, user['id'], action, target, detail, now()],
        )


def audit_entries() -> list[dict]:
    with database() as c:
        return rows(c, 'SELECT * FROM audit_log ORDER BY created_at DESC LIMIT 500')
