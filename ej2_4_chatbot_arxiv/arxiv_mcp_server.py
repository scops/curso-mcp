from __future__ import annotations

from typing import Any, Dict

from mcp.server.fastmcp import FastMCP, Context
from mcp.server.elicitation import (
    AcceptedElicitation,
    CancelledElicitation,
    DeclinedElicitation,
)
from pydantic import BaseModel, Field
from mcp.server.fastmcp.prompts import base

from tools_arxiv import search_papers, extract_info

# Servidor MCP que expone las mismas herramientas que app.py,
# pero ahora como tools MCP reutilizables por cualquier cliente.

INSTRUCTIONS = """
Eres un asistente experto en buscar y leer artículos científicos en arxiv.org.

Tu objetivo es ayudar al usuario a:
- Encontrar los papers más relevantes para su consulta (tema, autores, año, etc.).
- Leer el resumen y la información clave de cada paper.
- Explicar en español, de forma clara y breve, por qué cada paper es relevante.

Cuándo usar las tools:
- Usa `search_papers_mcp` para localizar candidatos relevantes en arXiv.
- Usa `extract_info_mcp` cuando necesites más detalle de un paper concreto.

Al responder:
- Resume los resultados en lenguaje sencillo, como si hablaras con otra persona del curso.
- Si es posible, menciona título, año y enlace/arxiv_id.
- Indica qué papers parecen más importantes para la duda del usuario.
"""


mcp = FastMCP("arxiv-tools", instructions=INSTRUCTIONS)


@mcp.tool()
async def search_papers_mcp(topic: str, max_results: int = 5) -> Dict[str, Any]:
    """
    Versión MCP de search_papers.

    Internamente reutiliza la función Python local, pero se expone
    como herramienta MCP. De cara al modelo, la herramienta se
    descubre dinámicamente vía list_tools().
    """
    return search_papers(topic=topic, max_results=max_results)


@mcp.tool()
async def extract_info_mcp(paper_id: str) -> Dict[str, Any]:
    """
    Versión MCP de extract_info.

    Igual que la anterior, pero expuesta como tool MCP.
    """
    return extract_info(paper_id=paper_id)


def main() -> None:
    # Ejecutamos el servidor MCP usando transporte STDIO,
    # que es el modo estándar para integrarse con clientes MCP.
    mcp.run(transport="stdio")


@mcp.tool()
def server_info(ctx: Context) -> dict:
    """Get information about the current server."""
    return {
        "name": ctx.fastmcp.name,
        "instructions": ctx.fastmcp.instructions,
        "debug_mode": ctx.fastmcp.settings.debug,
        "log_level": ctx.fastmcp.settings.log_level,
        "host": ctx.fastmcp.settings.host,
        "port": ctx.fastmcp.settings.port,
    }


@mcp.tool()
def who_am_i(ctx: Context) -> dict:
    """
    Tool de introspección sencillo para mostrar el "estado" del servidor MCP.

    Útil en clase para que veas que el servidor tiene identidad propia
    (nombre, tipo de transporte, etc.) y que ese contexto se puede leer
    desde los tools.
    """
    return {
        "server_name": ctx.fastmcp.name,
        "transport": "stdio",
        "debug_mode": ctx.fastmcp.settings.debug,
        "log_level": ctx.fastmcp.settings.log_level,
    }


@mcp.prompt(title="general_arxiv_search")
def prompt_busqueda_general(tema: str) -> str:
    """
    Prompt de ejemplo para búsquedas generales en arXiv.

    El host puede recuperar esta plantilla para guiar al modelo
    cuando quiera hacer una consulta abierta sobre un tema.
    """
    return (
        "Eres un asistente experto en arXiv.\n\n"
        "El usuario quiere encontrar artículos sobre el siguiente tema:\n"
        f"{tema}\n\n"
        "Devuelve una lista breve de papers relevantes, explicando en español "
        "por qué cada uno es interesante."
    )


@mcp.prompt(title="detailed_paper_analysis")
def prompt_analisis_detallado(arxiv_id: str) -> list[base.Message]:
    """
    Prompt de ejemplo para análisis detallado de un único paper.

    Aquí devolvemos una lista de mensajes estructurados para mostrar
    que los prompts pueden ser algo más rico que un simple string.
    """
    return [
        base.UserMessage(
            "Quiero que analices en detalle el siguiente paper de arXiv:"
        ),
        base.UserMessage(f"arxiv_id: {arxiv_id}"),
        base.AssistantMessage(
            "Voy a leer el resumen, los objetivos y las conclusiones, "
            "y luego te devolveré un análisis claro en español."
        ),
    ]


@mcp.tool()
async def analyze_paper_with_confirmation(ctx: Context) -> Dict[str, Any]:
    """
    Ejemplo de elicitation con FastMCP.

    Flujo:
    - El servidor pide al usuario qué paper de arXiv analizar
      y si confirma el análisis.
    - El cliente (Inspector, Claude, Cursor...) mostrará el formulario
      en la zona de “When the server requests information from the user…”.
    """

    class PaperSelection(BaseModel):
        paper_id: str = Field(
            description="arxiv_id del paper que quieres analizar (ej. 2401.01234)"
        )
        confirm: bool = Field(
            description="Marca true si quieres lanzar el análisis detallado"
        )

    result = await ctx.elicit(
        message=(
            "Indica el arxiv_id del paper que quieres analizar "
            "y confirma que deseas lanzar el análisis."
        ),
        schema=PaperSelection,
    )

    match result:
        case AcceptedElicitation(data=data):
            if not data.confirm:
                return {
                    "status": "cancelled",
                    "reason": "user_did_not_confirm",
                    "paper_id": data.paper_id,
                }

            info = extract_info(paper_id=data.paper_id)
            return {
                "status": "ok",
                "paper_id": data.paper_id,
                "analysis": info,
            }

        case DeclinedElicitation():
            return {
                "status": "cancelled",
                "reason": "user_declined_elicitation",
            }

        case CancelledElicitation():
            return {
                "status": "cancelled",
                "reason": "user_cancelled_operation",
            }


if __name__ == "__main__":
    main()
