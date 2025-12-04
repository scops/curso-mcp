from __future__ import annotations

"""
Cliente LangChain + MCP para sakila-simple.

Este módulo ilustra el enfoque "MCP tool-driven":

- Levanta el servidor MCP `sakila-simple` por STDIO.
- Usa `langchain-mcp` para exponer sus tools como herramientas de LangChain.
- Construye un agente que decide qué tool usar (por ejemplo, buscar por título
  o por categoría) y devuelve una respuesta al usuario.

En el benchmarking del ejercicio, compararemos este enfoque con el RAG de
`sakila_rag_client.rag_answer`.
"""

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from langchain_core.language_models import ChatAnthropic
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable, RunnablePassthrough
from langchain_mcp import MCPToolkit
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client


load_dotenv()


ROOT_DIR = Path(__file__).resolve().parents[1]


@asynccontextmanager
async def _sakila_session() -> ClientSession:
    """
    Crea una sesión MCP por STDIO levantando el servidor sakila-simple.
    """
    server_path = ROOT_DIR / "ej11_rag_vs_mcp_sakila" / "sakila_simple_mcp_server.py"

    async with stdio_client(
        StdioServerParameters(
            command="python",
            args=[str(server_path)],
            cwd=str(ROOT_DIR),
        )
    ) as (read_stream, write_stream):
        session = ClientSession(read_stream, write_stream)
        try:
            yield session
        finally:
            await session.close()


async def _build_agent() -> Runnable:
    """
    Construye un agente LangChain que utiliza las tools MCP de sakila-simple.
    """
    async with _sakila_session() as session:
        toolkit = MCPToolkit(session=session)
        await toolkit.initialize()
        tools = toolkit.get_tools()

    llm = ChatAnthropic(model="claude-3-5-haiku-latest")

    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                (
                    "Eres un asistente de recomendaciones de cine que usa herramientas MCP "
                    "para consultar la base de datos sakila.\n\n"
                    "Usa las herramientas disponibles para:\n"
                    "- Buscar películas por título parcial.\n"
                    "- Obtener películas por categoría.\n"
                    "- Consultar detalles de una película concreta.\n\n"
                    "Devuelve respuestas concisas y al grano, citando títulos y años "
                    "cuando sea relevante."
                ),
            ),
            ("human", "{input}"),
        ]
    )

    chain: Runnable = prompt | llm.bind_tools(tools)
    return chain


async def mcp_answer_async(question: str) -> str:
    """
    Ejecuta el agente MCP+LangChain para una pregunta concreta.
    """
    chain = await _build_agent()
    result = await chain.ainvoke({"input": question})
    return result.content if hasattr(result, "content") else str(result)


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

