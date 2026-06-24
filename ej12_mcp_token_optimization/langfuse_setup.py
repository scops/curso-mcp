"""
Configuración centralizada de Langfuse para el ejercicio 12.

Langfuse (y el instrumentor de Anthropic) SOLO se activan si hay credenciales
en el entorno: LANGFUSE_PUBLIC_KEY y LANGFUSE_SECRET_KEY.

Sin esas claves, este módulo expone versiones no-op de `observe`,
`propagate_attributes` y del cliente (`flush()`, `shutdown()`, ...), de modo
que el benchmark se ejecuta igual y solo imprime la tabla local de tokens,
sin warnings ni intentos de exportación fallidos.
"""
from __future__ import annotations

import os


def langfuse_enabled() -> bool:
    """True si hay credenciales de Langfuse en el entorno."""
    return bool(os.getenv("LANGFUSE_PUBLIC_KEY") and os.getenv("LANGFUSE_SECRET_KEY"))


_ENABLED = langfuse_enabled()


if _ENABLED:
    from langfuse import observe, get_client, propagate_attributes  # type: ignore
else:
    from contextlib import contextmanager

    def observe(*args, **kwargs):  # type: ignore[misc]
        """No-op de @observe y @observe(name=...)."""
        if len(args) == 1 and callable(args[0]) and not kwargs:
            return args[0]

        def _decorator(func):
            return func

        return _decorator

    @contextmanager
    def propagate_attributes(*args, **kwargs):  # type: ignore[misc]
        """No-op del context manager de propagación de atributos."""
        yield

    class _NoOpLangfuse:
        def __getattr__(self, _name):
            return lambda *a, **k: None

    def get_client():  # type: ignore[misc]
        return _NoOpLangfuse()


def init_langfuse(*, instrument_anthropic: bool = False):
    """
    Devuelve el cliente Langfuse: real si hay credenciales, no-op si no.

    Con `instrument_anthropic=True` y Langfuse activo, parchea el SDK de
    Anthropic (AnthropicInstrumentor) para trazar automáticamente las llamadas
    a la API (modelo, tokens, latencia). Debe llamarse ANTES de instanciar
    Anthropic.
    """
    if _ENABLED and instrument_anthropic:
        from opentelemetry.instrumentation.anthropic import AnthropicInstrumentor

        AnthropicInstrumentor().instrument()

    return get_client()
