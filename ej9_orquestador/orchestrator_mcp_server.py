from __future__ import annotations

from contextlib import AsyncExitStack
from pathlib import Path
from typing import Any, Dict, List

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.server.fastmcp import FastMCP


BASE_DIR = Path(__file__).resolve().parent.parent

ARXIV_SERVER_PATH = BASE_DIR / "ej2_4_chatbot_arxiv" / "arxiv_mcp_server.py"
RAG_SERVER_PATH = BASE_DIR / "ej7_mcp_rag_db" / "rag_mcp_server.py"


mcp = FastMCP("orchestrator")


async def _call_remote_tool_stdio(
    server_path: Path,
    tool_name: str,
    arguments: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Lanza un servidor MCP por STDIO y llama a uno de sus tools.

    Devuelve el `structuredContent` del CallToolResult, o un dict vacío
    si no hubiera contenido estructurado.
    """
    exit_stack = AsyncExitStack()

    try:
        params = StdioServerParameters(
            command="python",
            args=[str(server_path)],
            env=None,
        )
        transport = await exit_stack.enter_async_context(stdio_client(params))
        stdio, write = transport

        session = await exit_stack.enter_async_context(ClientSession(stdio, write))
        await session.initialize()

        result = await session.call_tool(tool_name, arguments)
        return result.structuredContent or {}
    finally:
        await exit_stack.aclose()


@mcp.tool()
async def research_incident_with_papers(
    incident_question: str,
    topic: str | None = None,
    max_papers: int = 3,
    k: int = 5,
) -> Dict[str, Any]:
    """
    Tool de orquestación que combina dos servidores MCP del curso:

    - Servidor RAG de incidencias (ej7_mcp_rag_db/rag_mcp_server.py)
    - Servidor arXiv (ej2_4_chatbot_arxiv/arxiv_mcp_server.py)

    Flujo:
    - Pregunta al servidor RAG para obtener una respuesta basada en tickets internos.
    - Usa arXiv para buscar papers relevantes sobre el mismo tema.
    """
    # 1) RAG local de incidencias
    rag_payload = await _call_remote_tool_stdio(
        RAG_SERVER_PATH,
        "rag_answer",
        {"question": incident_question, "k": k},
    )

    # 2) Búsqueda de papers en arXiv. Si no se pasa topic, usamos la propia pregunta.
    search_topic = topic or incident_question
    arxiv_payload = await _call_remote_tool_stdio(
        ARXIV_SERVER_PATH,
        "search_papers_mcp",
        {"topic": search_topic, "max_results": max_papers},
    )

    return {
        "incident_question": incident_question,
        "incident_answer": rag_payload.get("answer"),
        "incident_sources": rag_payload.get("sources", []),
        "arxiv_topic": search_topic,
        "arxiv_results": arxiv_payload,
    }


@mcp.tool()
async def list_orchestrated_servers() -> List[Dict[str, Any]]:
    """
    Devuelve una descripción sencilla de los servidores que este orquestador usa.

    No llama a los servidores, solo documenta la topología que se espera.
    """
    return [
        {
            "name": "incidents-rag",
            "path": str(RAG_SERVER_PATH),
            "description": "Servidor MCP de RAG sobre incidencias IT (ej7_mcp_rag_db).",
            "tools_expected": ["index_tickets", "rag_answer"],
        },
        {
            "name": "arxiv-tools",
            "path": str(ARXIV_SERVER_PATH),
            "description": "Servidor MCP de arXiv (ejercicios 2-4, ej2_4_chatbot_arxiv).",
            "tools_expected": ["search_papers_mcp", "extract_info_mcp"],
        },
    ]


def main() -> None:
    """
    Lanza el servidor MCP orquestador por STDIO.
    """
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()

