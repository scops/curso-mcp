from __future__ import annotations

import asyncio
from contextlib import AsyncExitStack
from pathlib import Path
from typing import Any, Dict, List

import streamlit as st
from anthropic import Anthropic
from dotenv import load_dotenv
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


load_dotenv()

ANTHROPIC_API_KEY = st.secrets.get("ANTHROPIC_API_KEY") or None
if not ANTHROPIC_API_KEY:
    import os

    ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
if not ANTHROPIC_API_KEY:
    raise RuntimeError("Falta ANTHROPIC_API_KEY en el entorno / .env")

MODEL = st.secrets.get("MODEL") or None
if not MODEL:
    import os

    MODEL = os.getenv("MODEL", "claude-haiku-4-5-20251001")

anthropic_client = Anthropic(api_key=ANTHROPIC_API_KEY)

SERVER_PATH = str(Path(__file__).parent / "sakila_mcp_server.py")


async def _open_mcp_session(exit_stack: AsyncExitStack) -> ClientSession:
    server_params = StdioServerParameters(
        command="python",
        args=[SERVER_PATH],
        env=None,
    )
    stdio_transport = await exit_stack.enter_async_context(stdio_client(server_params))
    stdio, write = stdio_transport

    session = await exit_stack.enter_async_context(ClientSession(stdio, write))
    await session.initialize()
    return session


async def ask_llm_with_mcp(user_query: str) -> str:
    """
    Cliente LLM + MCP para el ejercicio 8.

    - Lanza el servidor MCP de sakila+OMDb.
    - Descubre los tools disponibles.
    - Pasa esos tools a Claude.
    - Cuando el modelo pide usar tools, los ejecuta vía MCP.
    """
    exit_stack = AsyncExitStack()

    try:
        session = await _open_mcp_session(exit_stack)

        tools_response = await session.list_tools()
        available_tools: List[Dict[str, Any]] = [
            {
                "name": tool.name,
                "description": tool.description,
                "input_schema": tool.inputSchema,
            }
            for tool in tools_response.tools
        ]

        messages: List[Dict[str, Any]] = [
            {
                "role": "user",
                "content": user_query,
            }
        ]

        for _ in range(3):
            response = anthropic_client.messages.create(
                model=MODEL,
                max_tokens=800,
                tools=available_tools,
                messages=messages,
            )

            tool_uses = [c for c in response.content if c.type == "tool_use"]
            text_blocks = [c for c in response.content if c.type == "text"]

            if not tool_uses:
                final_text = "\n\n".join(tb.text for tb in text_blocks) if text_blocks else ""
                if final_text:
                    messages.append({"role": "assistant", "content": final_text})
                return final_text

            # Añadimos el mensaje del assistant con los tool_use
            messages.append({"role": "assistant", "content": response.content})

            # Ejecutamos cada tool en el servidor MCP
            for tool_call in tool_uses:
                tool_name = tool_call.name
                tool_args = tool_call.input
                tool_id = tool_call.id

                result = await session.call_tool(tool_name, tool_args)

                # Para simplificar, convertimos el resultado en string para el modelo.
                if hasattr(result, "model_dump"):
                    payload = result.model_dump(mode="json")
                else:
                    payload = {"raw_result": str(result)}

                messages.append(
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": tool_id,
                                "content": payload,
                            }
                        ],
                    }
                )

        return "He usado varias herramientas pero no he obtenido una respuesta clara. Intenta reformular tu pregunta."

    finally:
        await exit_stack.aclose()


def ask_llm_with_mcp_sync(user_query: str) -> str:
    return asyncio.run(ask_llm_with_mcp(user_query))


def main() -> None:
    st.set_page_config(
        page_title="Plataforma streaming · sakila + OMDb + MCP",
        layout="wide",
    )

    st.title("Plataforma streaming · sakila + OMDb + MCP")
    st.markdown(
        """
Ejercicio 8: combinamos **base de datos sakila (MySQL)** con la API de **OMDb**
expuesta como tools MCP, para emular un backend de plataforma de streaming.

El agente puede:

- Consultar las últimas películas de la base de datos (`get_latest_films`).
- Ver la distribución de películas por rating (`get_rating_distribution`).
- Crear nuevas películas en sakila a partir de OMDb (`create_film_from_omdb`).

La parte de visualizaciones (gráficos, métricas) se puede construir encima
de los resultados de estos tools en clase.
"""
    )

    if "history" not in st.session_state:
        st.session_state.history = []

    # Historial de chat
    for msg in st.session_state.history:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    user_input = st.chat_input("Pregunta algo sobre tu catálogo de streaming...")

    if user_input:
        st.session_state.history.append({"role": "user", "content": user_input})
        with st.chat_message("user"):
            st.markdown(user_input)

        with st.chat_message("assistant"):
            with st.spinner("Consultando sakila + OMDb vía MCP..."):
                try:
                    answer = ask_llm_with_mcp_sync(user_input)
                except Exception as e:
                    answer = f"Ha ocurrido un error llamando al LLM/MCP: {e}"
            st.markdown(answer)

        st.session_state.history.append({"role": "assistant", "content": answer})

    # Panel lateral para lanzar alguna consulta directa a MCP (ideal para visualizaciones)
    st.sidebar.header("Exploración directa de la base de datos")
    st.sidebar.write(
        "Estos botones llaman directamente a tools MCP, sin pasar por el LLM."
    )

    if st.sidebar.button("Ver distribución de rating (para graficar)"):
        # Llamada simple al tool get_rating_distribution para usar los datos en un gráfico.
        async def _fetch_rating_data() -> Dict[str, Any]:
            exit_stack = AsyncExitStack()
            try:
                session = await _open_mcp_session(exit_stack)
                result = await session.call_tool("get_rating_distribution", {})
                # result.content suele ser un dict ya serializable
                content = getattr(result, "content", result)
                return content  # type: ignore[no-any-return]
            finally:
                await exit_stack.aclose()

        try:
            data = asyncio.run(_fetch_rating_data())
            ratings = data.get("ratings", [])
            counts = data.get("counts", [])
            st.sidebar.bar_chart(
                {"rating": ratings, "count": counts},
                x="rating",
                y="count",
            )
        except Exception as e:
            st.sidebar.error(f"Error obteniendo datos de rating: {e}")


if __name__ == "__main__":
    main()

