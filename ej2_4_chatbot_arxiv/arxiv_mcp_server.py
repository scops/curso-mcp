from __future__ import annotations

import logging
from typing import Annotated, Any, Dict

from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

from mcp.server.mcpserver import (  # noqa: E402
    AcceptedElicitation,
    CancelledElicitation,
    Context,
    DeclinedElicitation,
    Elicit,
    ElicitationResult,
    MCPServer,
    Resolve,
)
from pydantic import BaseModel, Field  # noqa: E402
from mcp.server.mcpserver.prompts import base  # noqa: E402

from tools_arxiv import search_papers, extract_info  # noqa: E402

# Configurar logging para verificar que el MCP está siendo usado
logging.basicConfig(
    level=logging.INFO,
    format='[MCP-ARXIV] %(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

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


mcp = MCPServer("arxiv-tools", instructions=INSTRUCTIONS)


@mcp.tool()
async def search_papers_mcp(topic: str, max_results: int = 5) -> Dict[str, Any]:
    """
    Versión MCP de search_papers.

    Internamente reutiliza la función Python local, pero se expone
    como herramienta MCP. De cara al modelo, la herramienta se
    descubre dinámicamente vía list_tools().
    """
    logger.info(f"🔍 SEARCH_PAPERS_MCP llamada - topic: '{topic}', max_results: {max_results}")
    result = search_papers(topic=topic, max_results=max_results)
    logger.info(f"✅ SEARCH_PAPERS_MCP completada - {len(result.get('papers', []))} papers encontrados")
    return result


@mcp.tool()
async def extract_info_mcp(paper_id: str) -> Dict[str, Any]:
    """
    Versión MCP de extract_info.

    Igual que la anterior, pero expuesta como tool MCP.
    """
    logger.info(f"📄 EXTRACT_INFO_MCP llamada - paper_id: '{paper_id}'")
    result = extract_info(paper_id=paper_id)
    logger.info(f"✅ EXTRACT_INFO_MCP completada - información extraída para {paper_id}")
    return result


def main() -> None:
    # Ejecutamos el servidor MCP usando transporte STDIO,
    # que es el modo estándar para integrarse con clientes MCP.
    logger.info("🚀 Iniciando servidor MCP ARXIV...")
    logger.info("📡 Transporte: STDIO (stdin/stdout para protocolo MCP, logs en stderr)")
    logger.info("🔧 Tools disponibles: search_papers_mcp, extract_info_mcp, server_info, who_am_i, analyze_paper_with_confirmation")
    mcp.run(transport="stdio")
    logger.info("🛑 Servidor MCP ARXIV detenido")


@mcp.tool()
def server_info(ctx: Context) -> dict:
    """Get information about the current server."""
    logger.info("ℹ️  SERVER_INFO llamada")
    info = {
        "name": ctx.mcp_server.name,
        "instructions": ctx.mcp_server.instructions,
        "debug_mode": ctx.mcp_server.settings.debug,
        "log_level": ctx.mcp_server.settings.log_level,
        "host": ctx.mcp_server.settings.host,
        "port": ctx.mcp_server.settings.port,
    }
    logger.info(f"✅ SERVER_INFO completada - servidor: {info['name']}")
    return info


@mcp.tool()
def who_am_i(ctx: Context) -> dict:
    """
    Tool de introspección sencillo para mostrar el "estado" del servidor MCP.

    Útil en clase para que veas que el servidor tiene identidad propia
    (nombre, tipo de transporte, etc.) y que ese contexto se puede leer
    desde los tools.
    """
    logger.info("👤 WHO_AM_I llamada")
    identity = {
        "server_name": ctx.mcp_server.name,
        "transport": "stdio",
        "debug_mode": ctx.mcp_server.settings.debug,
        "log_level": ctx.mcp_server.settings.log_level,
    }
    logger.info(f"✅ WHO_AM_I completada - servidor: {identity['server_name']}")
    return identity


@mcp.prompt(name="general_arxiv_search")
def prompt_busqueda_general() -> str:
    """
    Prompt de ejemplo para búsquedas generales en arXiv.

    El host puede recuperar esta plantilla para guiar al modelo
    cuando quiera hacer una consulta abierta sobre un tema.
    """
    return (
        "Eres un asistente experto en arXiv.\n\n"
        "El usuario quiere encontrar artículos científicos relevantes.\n\n"
        "Devuelve una lista breve de papers relevantes, explicando en español "
        "por qué cada uno es interesante para el tema consultado."
    )


@mcp.prompt(name="detailed_paper_analysis")
def prompt_analisis_detallado() -> list[base.Message]:
    """
    Prompt de ejemplo para análisis detallado de un único paper.

    Aquí devolvemos una lista de mensajes estructurados para mostrar
    que los prompts pueden ser algo más rico que un simple string.
    """
    return [
        base.UserMessage(
            "Quiero que analices en detalle un paper de arXiv."
        ),
        base.UserMessage(
            "Por favor, extrae la información del paper usando extract_info_mcp "
            "y luego analiza el resumen, los objetivos y las conclusiones."
        ),
        base.AssistantMessage(
            "Voy a leer el resumen, los objetivos y las conclusiones, "
            "y luego te devolveré un análisis claro en español."
        ),
    ]


# ---------------------------------------------------------------------------
# Elicitation con ctx.elicit frente a Resolve + Elicit
# ---------------------------------------------------------------------------
# La elicitation es el mecanismo con el que el servidor pide un dato al usuario
# en mitad de una tool (el host le muestra un pequeño formulario y nos devuelve
# lo que haya contestado).
#
# Hasta la spec 2025-11-25 la escribíamos con `await ctx.elicit(...)` dentro de
# la tool. Esa llamada abre una petición del servidor hacia el cliente y deja la
# tool esperando la respuesta, algo que solo es posible si la conexión tiene un
# canal de vuelta y una sesión viva entre ambos.
#
# La spec 2026-07-28 elimina ese canal de vuelta para que los servidores puedan
# ser stateless (sin sesión, de modo que cualquier réplica atiende cualquier
# petición). Con un cliente moderno, `ctx.elicit` lanza NoBackChannelError; solo
# sigue funcionando con clientes antiguos.
#
# El SDK v2 nos da una vía que funciona en las dos épocas. Declaramos el dato que
# necesitamos como un parámetro anotado con `Resolve(funcion)`. Antes de ejecutar
# la tool, el SDK llama a esa función, a la que llamamos resolver, y si devuelve
# `Elicit(mensaje, Modelo)` se encarga de preguntar al usuario por nosotros:
#   - con un cliente 2026-07-28, la tool contesta "me falta este dato"
#     (InputRequiredResult) y el cliente repite la llamada adjuntando la respuesta;
#   - con un cliente antiguo, envía la petición clásica en mitad de la llamada.
# Nuestra tool recibe la respuesta ya resuelta y no necesita saber qué camino se
# ha seguido.
#
# Tres detalles que conviene tener presentes.
#   - El tipo del parámetro decide qué recibimos. Con `ElicitationResult[Modelo]`
#     llega el resultado completo (aceptar, rechazar o cancelar) y lo repartimos
#     con `match`. Con `Modelo` a secas llegan solo los datos, y un rechazo
#     aborta la tool antes de entrar en ella.
#   - El resolver puede ejecutarse más de una vez, una por cada vuelta del
#     cliente. Por eso debe hacer siempre la misma pregunta y no tener efectos
#     secundarios (nada de escribir en disco ni llamar a APIs antes del
#     `return Elicit(...)`).
#   - El parámetro resuelto no aparece en el schema de la tool, así que el modelo
#     no puede rellenarlo ni inventárselo.
# ---------------------------------------------------------------------------


class PaperSelection(BaseModel):
    paper_id: str = Field(
        description="arxiv_id del paper que quieres analizar (ej. 2401.01234)"
    )
    confirm: bool = Field(
        description="Marca true si quieres lanzar el análisis detallado"
    )


def pedir_paper() -> Elicit[PaperSelection]:
    """Resolver: pregunta al usuario qué paper analizar y si lo confirma."""
    return Elicit(
        "Indica el arxiv_id del paper que quieres analizar "
        "y confirma que deseas lanzar el análisis.",
        PaperSelection,
    )


@mcp.tool()
async def analyze_paper_with_confirmation(
    seleccion: Annotated[ElicitationResult[PaperSelection], Resolve(pedir_paper)],
) -> Dict[str, Any]:
    """
    Ejemplo de elicitation con el SDK MCP v2 (Resolve + Elicit).

    Flujo:
    - Antes de entrar en la tool, el resolver `pedir_paper` pide al usuario
      qué paper de arXiv analizar y si confirma el análisis.
    - El cliente (Inspector, Claude, Cursor...) mostrará el formulario
      en la zona de "When the server requests information from the user…".
    - La tool recibe en `seleccion` la respuesta ya resuelta.
    """
    logger.info("🔬 ANALYZE_PAPER_WITH_CONFIRMATION llamada con la respuesta del usuario")

    match seleccion:
        case AcceptedElicitation(data=data):
            if not data.confirm:
                logger.info(f"⚠️  Usuario no confirmó análisis para {data.paper_id}")
                return {
                    "status": "cancelled",
                    "reason": "user_did_not_confirm",
                    "paper_id": data.paper_id,
                }

            logger.info(f"📊 Analizando paper {data.paper_id}...")
            info = extract_info(paper_id=data.paper_id)
            logger.info(f"✅ Análisis completado para {data.paper_id}")
            return {
                "status": "ok",
                "paper_id": data.paper_id,
                "analysis": info,
            }

        case DeclinedElicitation():
            logger.info("❌ Usuario rechazó la solicitud de análisis")
            return {
                "status": "cancelled",
                "reason": "user_declined_elicitation",
            }

        case CancelledElicitation():
            logger.info("⛔ Operación cancelada por el usuario")
            return {
                "status": "cancelled",
                "reason": "user_cancelled_operation",
            }


if __name__ == "__main__":
    main()
