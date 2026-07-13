"""Secretos — nunca en logs ni frontend."""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from typing import Any


class SecretProvider(ABC):
    @abstractmethod
    def get(self, name: str) -> str | None:
        ...

    @abstractmethod
    def set(self, name: str, value: str) -> None:
        ...

    @abstractmethod
    def delete(self, name: str) -> None:
        ...

    def require(self, name: str) -> str:
        value = self.get(name)
        if not value:
            raise KeyError(f"Secreto no disponible: {name}")
        return value


class EnvironmentSecretProvider(SecretProvider):
    def get(self, name: str) -> str | None:
        return os.environ.get(name)

    def set(self, name: str, value: str) -> None:
        os.environ[name] = value

    def delete(self, name: str) -> None:
        os.environ.pop(name, None)


class LocalDevelopmentSecretProvider(SecretProvider):
    """Solo desarrollo local en memoria — no persistir a disco."""

    def __init__(self) -> None:
        self._store: dict[str, str] = {}

    def get(self, name: str) -> str | None:
        return self._store.get(name) or os.environ.get(name)

    def set(self, name: str, value: str) -> None:
        self._store[name] = value

    def delete(self, name: str) -> None:
        self._store.pop(name, None)


class CloudSecretProvider(SecretProvider):
    """
    Interfaz pendiente — AWS Secrets Manager / similar.
    DOCUMENTACIÓN/credenciales cloud se configuran en infra, no aquí.
    """

    def get(self, name: str) -> str | None:
        raise NotImplementedError(
            "CloudSecretProvider pendiente: configurar AWS Secrets Manager en Terraform"
        )

    def set(self, name: str, value: str) -> None:
        raise NotImplementedError("CloudSecretProvider pendiente")

    def delete(self, name: str) -> None:
        raise NotImplementedError("CloudSecretProvider pendiente")


def redact(value: Any) -> str:
    return "***REDACTED***"
