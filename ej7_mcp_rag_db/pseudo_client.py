from __future__ import annotations

import asyncio
from contextlib import AsyncExitStack
import json
from pathlib import Path
from typing import Any, Dict

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


SERVER_PATH = str(Path(__file__).parent / "rag_mcp_server.py")


def _unwrap_rag_content(raw: Any) -> Dict[str, Any]:
    """
    Adapta el resultado de session.call_tool(...) al dict
    { "answer": ..., "sources": ... } que queremos mostrar.

    FastMCP suele devolver una lista de bloques de contenido
    (por ejemplo, TextContent con un JSON en .text), así que
    aquí manejamos los casos típicos.
    """
    # Caso ideal: ya es un dict con answer
    if isinstance(raw, dict) and "answer" in raw:
        return raw

    # Caso habitual en FastMCP: lista de contenidos
    if isinstance(raw, list) and raw:
        first = raw[0]

        # TextContent (objeto) o dict con clave "text"
        text = getattr(first, "text", None)
        if text is None and isinstance(first, dict):
            text = first.get("text")

        if isinstance(text, str):
            # Intentar parsear como JSON
            try:
                data = json.loads(text)
                if isinstance(data, dict):
                    return data
            except Exception:
                # Si no es JSON, lo tomamos como respuesta directa
                return {"answer": text, "sources": []}

    # Fallback: lo mostramos tal cual como texto
    return {"answer": str(raw), "sources": []}


async def run_single_query(question: str) -> Dict[str, Any]:
    """
    Cliente MCP minimal que:
    - Lanza el servidor RAG por STDIO.
    - Lista los tools disponibles.
    - Llama a index_tickets() y rag_answer().
    """
    exit_stack = AsyncExitStack()

    try:
        server_params = StdioServerParameters(
            command="python",
            args=[SERVER_PATH],
            env=None,
        )

        stdio_transport = await exit_stack.enter_async_context(
            stdio_client(server_params)
        )
        stdio, write = stdio_transport

        session = await exit_stack.enter_async_context(
            ClientSession(stdio, write)
        )
        await session.initialize()

        tools_resp = await session.list_tools()
        print("Tools disponibles en el servidor MCP:")
        for tool in tools_resp.tools:
            print(f"- {tool.name}: {tool.description}")

        # Además de tools, este servidor expone resources MCP
        # que sirven para inspeccionar la base de conocimiento.
        resources_resp = await session.list_resources()
        if resources_resp.resources:
            print("\nResources disponibles en el servidor MCP:")
            for res in resources_resp.resources:
                desc = res.description or ""
                print(f"- {res.uri}  {desc}")

            # Como ejemplo, leemos el primer resource y mostramos un resumen.
            first_res = resources_resp.resources[0]
            print(f"\nLeyendo el resource: {first_res.uri}")
            read_result = await session.read_resource(first_res.uri)
            if read_result.contents:
                first_content = read_result.contents[0]
                text = getattr(first_content, "text", None)
                if text is None and isinstance(first_content, dict):
                    text = first_content.get("text")
                snippet = text if isinstance(text, str) else str(first_content)
                if isinstance(snippet, str) and len(snippet) > 400:
                    snippet = snippet[:400] + "..."
                print("Contenido (resumen):")
                print(snippet)

        print("\nLlamando a index_tickets()...")
        index_result = await session.call_tool("index_tickets", {})
        print("Resultado index_tickets:", index_result.content)

        print("\nLlamando a rag_answer()...")
        rag_result = await session.call_tool(
            "rag_answer", {"question": question, "k": 5}
        )

        # Adaptamos el resultado al formato esperado
        return _unwrap_rag_content(rag_result.content)

    finally:
        await exit_stack.aclose()


def main() -> None:
    print("Cliente MCP minimal para el servidor RAG de incidencias.")
    print("Escribe 'salir' para terminar.\n")

    while True:
        try:
            question = input(
                "Pregunta sobre incidencias IT (o 'salir'): "
            ).strip()
        except (EOFError, KeyboardInterrupt):
            print("\nSaliendo.")
            break

        if question.lower() in {"salir", "exit", "quit"}:
            break

        if not question:
            print("Por favor, escribe una pregunta.\n")
            continue

        try:
            result = asyncio.run(run_single_query(question))
        except Exception as e:
            print(f"[ERROR llamando al servidor MCP] {e}")
            continue

        print("\n=== Respuesta del servidor MCP ===\n")
        answer = result.get("answer")
        sources = result.get("sources", [])

        print(answer)
        print("\nTickets usados como fuentes:")
        for src in sources:
            print(
                f"- ID {src.get('id')}: {src.get('title')} "
                f"(score={src.get('score'):.3f}, tags={src.get('tags')})"
            )
        print("\n" + "=" * 60 + "\n")


if __name__ == "__main__":
    main()
