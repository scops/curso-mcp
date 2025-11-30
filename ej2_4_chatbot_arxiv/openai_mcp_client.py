from __future__ import annotations

import asyncio
import json
import os
from contextlib import AsyncExitStack
from pathlib import Path
from typing import Any, Dict, List

from dotenv import load_dotenv
from openai import OpenAI

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


"""
Ejercicio 4: Cliente OpenAI + MCP
---------------------------------

Objetivo didáctico:

- Reutilizar el mismo servidor MCP de arXiv (`arxiv_mcp_server.py`).
- Cambiar el modelo de lenguaje: ahora usamos OpenAI (por ejemplo, `gpt5-nano`).
- Ver claramente que, gracias a MCP, el servidor de tools **no depende**
  del modelo: solo cambiamos el cliente/orquestador.

Requisitos de entorno (.env):

- OPENAI_API_KEY=tu_api_key_de_openai
- OPENAI_MODEL=gpt5-nano   (o el modelo que quieras usar)
"""


load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise RuntimeError("Falta OPENAI_API_KEY en el entorno / .env")

OPENAI_MODEL = os.getenv("OPENAI_MODEL")
if not OPENAI_MODEL:
    raise RuntimeError("Falta OPENAI_MODEL en el entorno / .env")

client = OpenAI(api_key=OPENAI_API_KEY)


ARXIV_MCP_SERVER_PATH = str(Path(__file__).parent / "arxiv_mcp_server.py")


async def run_single_query_with_openai_and_mcp(query: str) -> str:
    """
    Ejecuta una consulta usando:
    - OpenAI Chat Completions con tools.
    - El servidor MCP de arXiv como proveedor de herramientas.

    Flujo:
    1. Se conecta al servidor MCP (arxiv_mcp_server.py) por STDIO.
    2. Descubre las tools MCP y las adapta al formato de tools de OpenAI.
    3. Llama al modelo OpenAI con la pregunta del usuario y las tools.
    4. Si el modelo decide usar tools, las ejecuta vía MCP y vuelve a
       llamar al modelo con los resultados.
    """
    exit_stack = AsyncExitStack()

    try:
        server_params = StdioServerParameters(
            command=os.getenv("PYTHON_EXECUTABLE", "python"),
            args=[ARXIV_MCP_SERVER_PATH],
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

        # 1) Descubrir tools MCP y adaptarlas al formato de OpenAI
        tools_response = await session.list_tools()

        openai_tools: List[Dict[str, Any]] = [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.inputSchema,
                },
            }
            for tool in tools_response.tools
        ]

        messages: List[Dict[str, Any]] = [
            {
                "role": "user",
                "content": query,
            }
        ]

        # 2) Primera llamada al modelo con tools
        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=messages,
            tools=openai_tools,
            tool_choice="auto",
        )

        msg = response.choices[0].message

        # Si el modelo no pide tools, devolvemos la respuesta tal cual
        if not msg.tool_calls:
            return msg.content or ""

        # 3) El modelo ha pedido llamar a una o varias tools
        tool_calls = msg.tool_calls or []

        # Añadimos el mensaje del assistant con los tool_calls al historial
        messages.append(
            {
                "role": msg.role,
                "content": msg.content or "",
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": tc.type,
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in tool_calls
                ],
            }
        )

        # Ejecutamos cada tool via MCP y añadimos mensajes de rol "tool"
        for tc in tool_calls:
            tool_name = tc.function.name
            try:
                tool_args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                tool_args = {}

            # Llamamos al servidor MCP
            result = await session.call_tool(tool_name, tool_args)

            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": json.dumps(
                        result.content, ensure_ascii=False, indent=2
                    ),
                }
            )

        # 4) Segunda llamada: ahora el modelo tiene resultados de tools
        second_response = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=messages,
        )

        return second_response.choices[0].message.content or ""

    finally:
        await exit_stack.aclose()


def main() -> None:
    """
    Pequeño CLI interactivo:
    - Escribe preguntas sobre arXiv.
    - Usa OpenAI + MCP para responder.
    """
    print("Cliente OpenAI + MCP (arxiv). Escribe 'salir' para terminar.")

    while True:
        try:
            query = input("\nTú: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nSaliendo.")
            break

        if query.lower() in {"salir", "exit", "quit"}:
            break

        try:
            answer = asyncio.run(
                run_single_query_with_openai_and_mcp(query)
            )
        except Exception as e:
            answer = f"[ERROR llamando a OpenAI/MCP] {e}"

        print("\nBot (OpenAI + MCP):\n")
        print(answer)


if __name__ == "__main__":
    main()

