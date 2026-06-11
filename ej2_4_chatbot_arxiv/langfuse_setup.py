"""
Configuración centralizada de Langfuse para el ejercicio 2-4.

Langfuse (y los instrumentors de OpenTelemetry) SOLO se activan si hay
credenciales en el entorno: LANGFUSE_PUBLIC_KEY y LANGFUSE_SECRET_KEY.

Sin esas claves, este módulo expone versiones no-op de `observe`,
`propagate_attributes` y del cliente (`flush()`, `shutdown()`, ...), de modo
que el resto del código no cambia y el curso se ejecuta sin ruido: ni el
warning "Client will be disabled" ni los "Failed to export span batch 404"
que aparecen cuando no hay una instancia de Langfuse escuchando.

Los módulos del ejercicio deben importar `observe` / `propagate_attributes`
desde aquí (no desde `langfuse`) y crear el cliente con `init_langfuse()`.
"""
from __future__ import annotations

import os


def langfuse_enabled() -> bool:
    """True si hay credenciales de Langfuse en el entorno."""
    return bool(os.getenv("LANGFUSE_PUBLIC_KEY") and os.getenv("LANGFUSE_SECRET_KEY"))


_ENABLED = langfuse_enabled()


if _ENABLED:
    # Langfuse activo: usamos las funciones reales.
    from langfuse import observe, get_client, propagate_attributes  # type: ignore
else:
    # Langfuse desactivado: no importamos el cliente real (evita el warning
    # de autenticación) y damos no-ops con la misma firma de uso.
    from contextlib import contextmanager

    def observe(*args, **kwargs):  # type: ignore[misc]
        """No-op de @observe y @observe(name=...)."""
        if len(args) == 1 and callable(args[0]) and not kwargs:
            return args[0]  # uso sin paréntesis: @observe

        def _decorator(func):
            return func

        return _decorator

    @contextmanager
    def propagate_attributes(*args, **kwargs):  # type: ignore[misc]
        """No-op del context manager de propagación de atributos."""
        yield

    class _NoOpLangfuse:
        """Cliente vacío: cualquier método (flush, shutdown, ...) es no-op."""

        def __getattr__(self, _name):
            return lambda *a, **k: None

    def get_client():  # type: ignore[misc]
        return _NoOpLangfuse()


def init_langfuse(*, instrument_anthropic: bool = False):
    """
    Devuelve el cliente Langfuse: real si hay credenciales, no-op si no.

    Con `instrument_anthropic=True` y Langfuse activo, parchea el SDK de
    Anthropic (AnthropicInstrumentor) para trazar automáticamente las
    llamadas a la API. Debe llamarse ANTES de importar/instanciar Anthropic.
    """
    if _ENABLED and instrument_anthropic:
        from opentelemetry.instrumentation.anthropic import AnthropicInstrumentor

        AnthropicInstrumentor().instrument()

    return get_client()
