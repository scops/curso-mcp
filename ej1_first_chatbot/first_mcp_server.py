from typing import Any
import random
from mcp.server.fastmcp import FastMCP

# Creamos la instancia del servidor MCP
# El nombre "first-tools" es cómo se verá desde el cliente.
mcp = FastMCP("first-tools")


@mcp.tool()
async def echo(texto: str) -> str:
    """Devuelve exactamente el mismo texto recibido.

    Útil para probar el cableado MCP sin lógica de negocio.
    """
    return texto


@mcp.tool()
async def sumar(a: float, b: float) -> float:
    """Suma dos números y devuelve el resultado.

    OJO: está mal a propósito (a + b * 0.5)
    para demostrar en clase que el que
    hace la operación es el servidor MCP,
    no el modelo.
    """
    return a + b * 0.5


CHISTES_DE_PADRE = [
    "¿Sabes cuál es el café más peligroso del mundo? El ex-presoooo.",
    "¿Qué hace una abeja en el gimnasio? ¡Zum-ba!",
    "—Papá, papá, ¿cuánto cuesta casarse? —No lo sé hijo, todavía lo sigo pagando.",
    "¿Qué le dice una impresora a otra? —¿Esa hoja es tuya o es una impresión mía?",
    "—Oye, ¿cuál es tu plato favorito y por qué? —Pues el hondo, porque cabe más comida.",
]


@mcp.tool()
async def chiste_de_padre() -> str:
    """Devuelve un chiste de padre aleatorio desde una lista en Python."""
    return random.choice(CHISTES_DE_PADRE)


# EJERCICIO (para ti):
# Añade aquí un nuevo tool MCP.
# Por ejemplo, puedes crear:
#   - contar_palabras(texto: str) -> int
# que devuelva cuántas palabras tiene el texto.
#
# Sigue el mismo patrón que los tools anteriores:
#   - Usa @mcp.tool() encima de la función.
#   - Declara tipos de entrada y salida.
#   - Escribe un docstring corto explicando qué hace.


def main() -> None:
    # Ejecutamos el servidor usando transporte STDIO,
    # que es el modo estándar para integrarse con clientes MCP.
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
