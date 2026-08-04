"""Backend registry — the pluggable seam. Resolve a backend by name (env or arg), or pass an
instance. Built-ins (null, procedural) self-register on first use; adding a backend = write a class
and call register() (typically from backends/__init__ or the backend module itself)."""
from __future__ import annotations

import os

_BACKENDS: dict = {}
_ENV_VAR = "BTSGEN_IMAGE_BACKEND"


def register(backend) -> None:
    """Register a backend instance under its .name (idempotent; last registration wins)."""
    _BACKENDS[backend.name] = backend


def available_backends() -> list[str]:
    _ensure_builtins()
    return sorted(_BACKENDS)


def get_backend(backend=None):
    """Resolve a backend. `backend` may be an ImageBackend instance (used as-is), a name string, or
    None (-> $BTSGEN_IMAGE_BACKEND, else 'null'). Raises KeyError on an unknown name."""
    _ensure_builtins()
    if backend is not None and not isinstance(backend, str):
        return backend  # already a backend instance
    name = backend or os.environ.get(_ENV_VAR) or "null"
    try:
        return _BACKENDS[name]
    except KeyError:
        raise KeyError(f"unknown image backend '{name}'; known: {sorted(_BACKENDS)}") from None


def _ensure_builtins() -> None:
    # Deferred so importing registry doesn't import the backends (avoids a cycle and keeps cloud
    # backends' optional deps from loading until actually selected).
    if not _BACKENDS:
        from . import backends  # noqa: F401  (import side-effect registers null + procedural)
