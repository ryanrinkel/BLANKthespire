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
    """Resolve ONE backend — the first of resolve_backends(). `backend` may be an ImageBackend
    instance (used as-is), a name string, or None (-> $BTSGEN_IMAGE_BACKEND, else 'null'). Raises
    KeyError on an unknown name."""
    return resolve_backends(backend)[0]


def resolve_backends(backend=None) -> list:
    """The ORDERED fallback chain. `backend` may be an instance, a name, a COMMA LIST
    ('openrouter,openai' — also the accepted $BTSGEN_IMAGE_BACKEND form), a list/tuple of either, or
    None. The caller (art/splash.py::_forge_asset) tries each in order and keeps the first ok result,
    so a rate-limited or down vendor costs a retry, not the class's art. Raises KeyError naming the
    first unknown entry (a typo in the env must be loud, not silently 'no art')."""
    _ensure_builtins()
    if backend is not None and not isinstance(backend, str):
        if isinstance(backend, (list, tuple)):
            out: list = []
            for item in backend:
                out.extend(resolve_backends(item))
            return out
        return [backend]  # already a backend instance
    raw = backend or os.environ.get(_ENV_VAR) or "null"
    names = [n.strip() for n in str(raw).split(",") if n.strip()] or ["null"]
    chain = []
    for name in names:
        try:
            chain.append(_BACKENDS[name])
        except KeyError:
            raise KeyError(f"unknown image backend '{name}'; known: {sorted(_BACKENDS)}") from None
    return chain


def _ensure_builtins() -> None:
    # Deferred so importing registry doesn't import the backends (avoids a cycle and keeps cloud
    # backends' optional deps from loading until actually selected).
    if not _BACKENDS:
        from . import backends  # noqa: F401  (import side-effect registers null + procedural)
