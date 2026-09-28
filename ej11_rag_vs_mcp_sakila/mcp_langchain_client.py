from __future__ import annotations

"""
Cliente LangChain + MCP para sakila-simple.

Este módulo ilustra el enfoque "MCP tool-driven":

- Levanta el servidor MCP `sakila-simple` por STDIO.
- Usa `langchain.mcp.MCPAdapter` (integración MCP nueva de LangChain,
  BETA — requiere `langchain[mcp]>=1.4.0`) para exponer sus tools como
  herramientas de LangChain.
- Construye un agente (`create_agent`) que decide qué tool usar (por
  ejemplo, buscar por título o por categoría) y devuelve una respuesta
  al usuario.

NOTA (curso): este ejercicio es EXTRA/avanzado, no forma parte del temario
principal de protocolo MCP. `langchain.mcp` está en beta y su API puede
cambiar; revisa https://docs.langchain.com/oss/python/langchain/mcp antes
de cada edición del curso por si ha cambiado.

En el benchmarking del ejercicio, comparamos este enfoque con el RAG de
`sakila_rag_client.rag_answer`.
"""

import asyncio
import os
from pathlib import Path

from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain.mcp import MCPAdapter
from langchain_anthropic import ChatAnthropic


load_dotenv()

ROOT_DIR = Path(__file__).resolve().parents[1]
SERVER_PATH = ROOT_DIR / "ej11_rag_vs_mcp_sakila" / "sakila_simple_mcp_server.py"

MODEL = os.getenv("MODEL", "claude-haiku-4-5")

SYSTEM_PROMPT = (
    "Eres un asistente de recomendaciones de cine que usa herramientas MCP "
    "para consultar la base de datos sakila.\n\n"
    "Usa las herramientas disponibles para:\n"
    "- Buscar películas por título parcial.\n"
    "- Obtener películas por categoría.\n"
    "- Consultar detalles de una película concreta.\n\n"
    "Devuelve respuestas concisas y al grano, citando títulos y años "
    "cuando sea relevante."
)


async def mcp_answer_async(question: str) -> str:
    """
    Ejecuta el agente MCP+LangChain para una pregunta concreta.

    `MCPAdapter(Path(...))` lanza el servidor MCP como subproceso STDIO
    (usando el mismo intérprete Python, vía `sys.executable`), descubre
    sus tools con `list_tools()` y las adapta a tools de LangChain.
    """
    async with MCPAdapter(SERVER_PATH) as adapter:
        tools = await adapter.list_tools()

        llm = ChatAnthropic(model=MODEL)
        agent = create_agent(llm, tools, system_prompt=SYSTEM_PROMPT)

        result = await agent.ainvoke(
            {"messages": [{"role": "user", "content": question}]}
        )

    final_message = result["messages"][-1]
    return getattr(final_message, "content", str(final_message))


def mcp_answer(question: str) -> str:
    """
    Versión síncrona de conveniencia.
    """
    return asyncio.run(mcp_answer_async(question))


def main() -> None:
    """
    Pequeño CLI de prueba manual.
    """
    try:
        question = input(
            "Pregunta algo sobre el catálogo sakila (MCP/LangChain) "
            "(o vacío para salir):\n> "
        ).strip()
    except (EOFError, KeyboardInterrupt):
        print("\nSaliendo.")
        return

    if not question:
        print("Sin pregunta. Saliendo.")
        return

    answer = mcp_answer(question)
    print("\n=== Respuesta MCP+LangChain ===\n")
    print(answer)


if __name__ == "__main__":
    main()
