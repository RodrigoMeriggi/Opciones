"""Auth simple JWT para dashboard (paper). Credenciales solo vía env."""

from __future__ import annotations

import hashlib
import hmac
import os
import time
from typing import Annotated, Literal

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

Role = Literal["ADMIN", "TRADER", "VIEWER"]

security = HTTPBearer(auto_error=False)

# Usuarios demo — passwords hasheadas con secret de entorno (NO brokers)
_DEMO_USERS = {
    "admin": {"password": "admin-change-me", "role": "ADMIN"},
    "trader": {"password": "trader-change-me", "role": "TRADER"},
    "viewer": {"password": "viewer-change-me", "role": "VIEWER"},
}


class TokenPayload(BaseModel):
    sub: str
    role: Role
    exp: float


def _secret() -> bytes:
    return os.environ.get("DASHBOARD_JWT_SECRET", "dev-only-change-me").encode()


def _sign(msg: str) -> str:
    return hmac.new(_secret(), msg.encode(), hashlib.sha256).hexdigest()


def create_token(username: str, role: Role, ttl_seconds: int = 3600) -> str:
    exp = time.time() + ttl_seconds
    body = f"{username}|{role}|{exp}"
    return f"{body}|{_sign(body)}"


def parse_token(token: str) -> TokenPayload:
    try:
        username, role, exp_s, sig = token.split("|", 3)
        body = f"{username}|{role}|{exp_s}"
        if not hmac.compare_digest(_sign(body), sig):
            raise ValueError("bad sig")
        exp = float(exp_s)
        if time.time() > exp:
            raise ValueError("expired")
        return TokenPayload(sub=username, role=role, exp=exp)  # type: ignore[arg-type]
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token inválido") from exc


def authenticate(username: str, password: str) -> TokenPayload:
    user = _DEMO_USERS.get(username)
    if not user or user["password"] != password:
        raise HTTPException(status_code=401, detail="Credenciales inválidas")
    return TokenPayload(sub=username, role=user["role"], exp=time.time() + 3600)  # type: ignore[arg-type]


async def current_user(
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
) -> TokenPayload:
    if creds is None:
        raise HTTPException(status_code=401, detail="No autenticado")
    return parse_token(creds.credentials)


def require_roles(*roles: Role):
    async def _dep(user: Annotated[TokenPayload, Depends(current_user)]) -> TokenPayload:
        if user.role not in roles:
            raise HTTPException(status_code=403, detail="Rol insuficiente")
        return user

    return _dep
