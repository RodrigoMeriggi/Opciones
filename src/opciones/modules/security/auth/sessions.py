"""Usuarios, hashing de contraseñas, sesiones y tokens."""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import uuid4

from opciones.modules.security.rbac.permissions import Permission, has_permission


def hash_password(password: str, *, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(16)
    dk = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt.encode("utf-8"),
        n=2**14,
        r=8,
        p=1,
        dklen=32,
    )
    return f"scrypt${salt}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, salt, digest = stored.split("$", 2)
        if algo != "scrypt":
            return False
        candidate = hash_password(password, salt=salt)
        return hmac.compare_digest(candidate, stored)
    except Exception:
        return False


@dataclass
class User:
    id: str
    username: str
    password_hash: str
    role: str
    active: bool = True
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class Session:
    id: str
    user_id: str
    username: str
    role: str
    refresh_token_hash: str
    created_at: float
    expires_at: float
    revoked: bool = False
    ip: str | None = None
    user_agent: str | None = None


@dataclass
class AccessToken:
    token: str
    expires_at: float
    session_id: str
    username: str
    role: str


class UserStore:
    def __init__(self) -> None:
        self.users: dict[str, User] = {}
        self.by_username: dict[str, str] = {}

    def create(self, username: str, password: str, role: str) -> User:
        if username in self.by_username:
            raise ValueError("Usuario ya existe")
        user = User(
            id=str(uuid4()),
            username=username,
            password_hash=hash_password(password),
            role=role,
        )
        self.users[user.id] = user
        self.by_username[username] = user.id
        return user

    def authenticate(self, username: str, password: str) -> User | None:
        uid = self.by_username.get(username)
        if not uid:
            return None
        user = self.users[uid]
        if not user.active or not verify_password(password, user.password_hash):
            return None
        return user


class SessionManager:
    def __init__(
        self,
        *,
        access_ttl: int = 900,
        refresh_ttl: int = 60 * 60 * 12,
        max_sessions_per_user: int = 5,
        secret: str | None = None,
    ) -> None:
        self.access_ttl = access_ttl
        self.refresh_ttl = refresh_ttl
        self.max_sessions_per_user = max_sessions_per_user
        self.secret = (secret or os.environ.get("DASHBOARD_JWT_SECRET", "dev-only-change-me")).encode()
        self.sessions: dict[str, Session] = {}
        self.failed_logins: dict[str, list[float]] = {}

    def _sign(self, body: str) -> str:
        return hmac.new(self.secret, body.encode(), hashlib.sha256).hexdigest()

    def create_session(
        self,
        user: User,
        *,
        ip: str | None = None,
        user_agent: str | None = None,
    ) -> tuple[AccessToken, str]:
        # límite de sesiones
        active = [s for s in self.sessions.values() if s.user_id == user.id and not s.revoked]
        active.sort(key=lambda s: s.created_at)
        while len(active) >= self.max_sessions_per_user:
            old = active.pop(0)
            old.revoked = True

        refresh = secrets.token_urlsafe(32)
        session = Session(
            id=str(uuid4()),
            user_id=user.id,
            username=user.username,
            role=user.role,
            refresh_token_hash=hashlib.sha256(refresh.encode()).hexdigest(),
            created_at=time.time(),
            expires_at=time.time() + self.refresh_ttl,
            ip=ip,
            user_agent=user_agent,
        )
        self.sessions[session.id] = session
        access = self._mint_access(session)
        return access, refresh

    def _mint_access(self, session: Session) -> AccessToken:
        exp = time.time() + self.access_ttl
        body = f"{session.username}|{session.role}|{exp}|{session.id}"
        token = f"{body}|{self._sign(body)}"
        return AccessToken(token=token, expires_at=exp, session_id=session.id, username=session.username, role=session.role)

    def parse_access(self, token: str) -> AccessToken:
        try:
            username, role, exp_s, sid, sig = token.split("|", 4)
            body = f"{username}|{role}|{exp_s}|{sid}"
            if not hmac.compare_digest(self._sign(body), sig):
                raise ValueError("bad sig")
            exp = float(exp_s)
            if time.time() > exp:
                raise ValueError("expired")
            session = self.sessions.get(sid)
            if session is None or session.revoked or time.time() > session.expires_at:
                raise ValueError("session revoked")
            return AccessToken(token=token, expires_at=exp, session_id=sid, username=username, role=role)
        except Exception as exc:
            raise PermissionError("Token inválido") from exc

    def refresh(self, refresh_token: str) -> tuple[AccessToken, str]:
        digest = hashlib.sha256(refresh_token.encode()).hexdigest()
        session = next((s for s in self.sessions.values() if s.refresh_token_hash == digest), None)
        if session is None or session.revoked or time.time() > session.expires_at:
            raise PermissionError("Refresh inválido")
        # rotación
        new_refresh = secrets.token_urlsafe(32)
        session.refresh_token_hash = hashlib.sha256(new_refresh.encode()).hexdigest()
        return self._mint_access(session), new_refresh

    def revoke(self, session_id: str) -> None:
        if session_id in self.sessions:
            self.sessions[session_id].revoked = True

    def revoke_all(self, user_id: str) -> int:
        n = 0
        for s in self.sessions.values():
            if s.user_id == user_id and not s.revoked:
                s.revoked = True
                n += 1
        return n

    def record_failed_login(self, username: str) -> int:
        now = time.time()
        bucket = self.failed_logins.setdefault(username, [])
        bucket.append(now)
        self.failed_logins[username] = [t for t in bucket if now - t < 900]
        return len(self.failed_logins[username])

    def require_permission(self, role: str, permission: Permission) -> None:
        if not has_permission(role, permission):
            raise PermissionError(f"Permiso denegado: {permission}")


def bootstrap_default_users(store: UserStore) -> None:
    if store.by_username:
        return
    store.create("admin", os.environ.get("ADMIN_PASSWORD", "admin-change-me"), "ADMIN")
    store.create("trader", os.environ.get("TRADER_PASSWORD", "trader-change-me"), "TRADER")
    store.create("viewer", os.environ.get("VIEWER_PASSWORD", "viewer-change-me"), "VIEWER")
