from __future__ import annotations

import asyncio
import os
from contextlib import AsyncExitStack
from pathlib import Path
from typing import Any, Dict, List, Tuple

import streamlit as st
from anthropic import Anthropic
from dotenv import load_dotenv

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# -------------------------------------------------------------------
# Versión "con MCP" del chatbot arXiv.
#
# Diferencias clave respecto a app.py:
# - app.py llama a funciones Python locales (search_papers, extract_info).
# - app_con_mcp.py NO llama directamente a esas funciones.
#   En su lugar, habla con un servidor MCP (arxiv_mcp_server.py) que
#   expone esas mismas herramientas como tools MCP.
#
# Desde el punto de vista del modelo:
# - En app.py definimos a mano el JSON Schema de las tools.
# - Aquí dejamos que el cliente MCP descubra las tools del servidor
#   con list_tools(), y se las pasamos a Claude.
#
# Esto responde a la pregunta "¿qué gano con FastMCP si ya funcionaba
# el ejemplo anterior?":
# - Separas la lógica de tools en un servidor reutilizable.
# - Cualquier cliente MCP (no solo esta app) puede descubrir y usar
#   las mismas herramientas.
# - No duplicas a mano los esquemas de entrada/salida en cada cliente.
# -------------------------------------------------------------------


# -----------------------
# Configuración básica
# -----------------------

load_dotenv()

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
if not ANTHROPIC_API_KEY:
    raise RuntimeError("Falta ANTHROPIC_API_KEY en el entorno / .env")

client = Anthropic(api_key=ANTHROPIC_API_KEY)

DEFAULT_MODEL = os.getenv("MODEL", "claude-haiku-4-5-20251001")
DEFAULT_MAX_TOKENS = int(os.getenv("ANTHROPIC_MAX_TOKENS", "800"))


# -----------------------
# Helpers MCP (cliente)
# -----------------------

ARXIV_MCP_SERVER_PATH = str(Path(__file__).parent / "arxiv_mcp_server.py")


def _serialize_mcp_content(content: Any) -> str | list:
    """
    Convierte el contenido del SDK MCP a un formato serializable por Anthropic.

    El content puede ser:
    - Una cadena (caso simple)
    - Una lista de objetos TextContent, ImageContent, etc.
    - Otros tipos que necesitan conversión
    """
    if isinstance(content, str):
        return content

    if isinstance(content, list):
        # Lista de objetos de contenido del SDK MCP
        result = []
        for item in content:
            if hasattr(item, "text"):
                # TextContent o similar
                result.append(item.text)
            elif isinstance(item, str):
                result.append(item)
            else:
                # Fallback: convertir a string
                result.append(str(item))
        return "\n".join(result) if result else ""

    # Fallback para otros tipos
    if hasattr(content, "text"):
        return content.text

    return str(content)


async def _call_mcp_tools_for_query(
    user_query: str,
    model: str,
    max_tokens: int,
    *,
    prompt_name: str | None = None,
    prompt_args: Dict[str, str] | None = None,
) -> Tuple[str, List[Dict[str, Any]]]:
    """
    Abre una sesión MCP contra arxiv_mcp_server.py, descubre las tools,
    y ejecuta un pequeño bucle "Claude + tools", igual que en app.py,
    pero pidiendo al servidor MCP que ejecute las herramientas.
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

        # Descubrimos las tools MCP del servidor
        tools_response = await session.list_tools()
        mcp_tools = [
            {
                "name": tool.name,
                "description": tool.description,
                "input_schema": tool.inputSchema,
            }
            for tool in tools_response.tools
        ]

        messages: List[Dict[str, Any]] = []

        # Opcional: recuperar un prompt MCP del servidor para usarlo
        # como mensaje de sistema/inicio de la conversación.
        if prompt_name:
            try:
                prompt_result = await session.get_prompt(
                    name=prompt_name,
                    arguments=prompt_args or {},
                )
                # prompt_result.messages ya viene en el formato esperado
                # por Anthropic (lista de mensajes role/content).
                # Necesitamos serializar el content para que sea compatible con Anthropic
                messages.extend(
                    [
                        {
                            "role": msg.role,
                            "content": _serialize_mcp_content(msg.content),
                        }
                        for msg in prompt_result.messages
                    ]
                )
            except Exception as e:  # pragma: no cover - es puramente didáctico
                # Si algo va mal, seguimos sin prompt extra.
                messages.append(
                    {
                        "role": "assistant",
                        "content": f"(Aviso: no se ha podido recuperar el prompt '{prompt_name}' del servidor MCP: {e})",
                    }
                )

        # Mensaje del usuario
        messages.append(
            {
                "role": "user",
                "content": user_query,
            }
        )

        # Bucle similar al de app.py, pero delegando en MCP
        for _ in range(3):
            response = client.messages.create(
                model=model,
                max_tokens=max_tokens,
                tools=mcp_tools,
                messages=messages,
            )

            tool_uses = [c for c in response.content if c.type == "tool_use"]
            text_blocks = [c for c in response.content if c.type == "text"]

            if not tool_uses:
                final_text = (
                    "\n\n".join(block.text for block in text_blocks)
                    if text_blocks
                    else ""
                )
                if final_text:
                    messages.append(
                        {
                            "role": "assistant",
                            "content": final_text,
                        }
                    )
                return final_text, messages

            # Añadimos el paso de tool_use al historial
            messages.append(
                {
                    "role": "assistant",
                    "content": response.content,
                }
            )

            # Ejecutamos tools vía MCP
            for tool_call in tool_uses:
                tool_name = tool_call.name
                tool_input = tool_call.input
                tool_id = tool_call.id

                # Sesión MCP ejecuta el tool en el servidor
                result = await session.call_tool(tool_name, tool_input)

                # Pasamos el contenido serializado al modelo.
                # El result.content puede contener objetos del SDK MCP que necesitan conversión
                messages.append(
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": tool_id,
                                "content": _serialize_mcp_content(result.content),
                            }
                        ],
                    }
                )

        return (
            "He alcanzado el número máximo de pasos de herramientas sin una respuesta final clara.",
            messages,
        )
    finally:
        await exit_stack.aclose()


def run_claude_with_mcp_tools(
    user_query: str,
    model: str = DEFAULT_MODEL,
    max_tokens: int = DEFAULT_MAX_TOKENS,
) -> Tuple[str, List[Dict[str, Any]]]:
    """
    Envoltorio síncrono para Streamlit: por debajo crea una sesión MCP
    temporal para esta consulta y la cierra al terminar.

    Es menos eficiente que mantener la sesión abierta, pero simplifica
    mucho el ejemplo didáctico y evita pelearse con estados globales.
    """

    return asyncio.run(
        _call_mcp_tools_for_query(
            user_query=user_query,
            model=model,
            max_tokens=max_tokens,
            # Para mantener el ejemplo sencillo, usamos siempre
            # el prompt de búsqueda general en arXiv definido en
            # arxiv_mcp_server.py.
            prompt_name="general_arxiv_search",
            prompt_args={},
        )
    )


# -----------------------
# UI Streamlit (similar a app.py)
# -----------------------

st.set_page_config(page_title="Chatbot arXiv · Claude + MCP", page_icon="📚")

st.title("Chatbot arXiv · Claude + MCP")
st.markdown(
    """
Esta es la **versión MCP** del chatbot arXiv.

La interfaz es muy parecida a `app.py`, pero la diferencia importante es:

- En `app.py` las tools (`search_papers`, `extract_info`) son funciones locales.
- Aquí esas mismas tools viven en un **servidor MCP** (`arxiv_mcp_server.py`),
  y esta app se comporta como un **cliente MCP** que:
  - Descubre las tools con `list_tools()`.
  - Pide al servidor que ejecute las herramientas cuando Claude lo solicita.
"""
)

if "chat_history_mcp" not in st.session_state:
    st.session_state.chat_history_mcp = []

for msg in st.session_state.chat_history_mcp:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

user_input = st.chat_input(
    "Haz una pregunta sobre papers de arXiv (versión MCP)..."
)

if user_input:
    st.session_state.chat_history_mcp.append(
        {"role": "user", "content": user_input}
    )
    with st.chat_message("user"):
        st.markdown(user_input)

    with st.chat_message("assistant"):
        with st.spinner("Pensando con herramientas vía MCP..."):
            try:
                answer, _messages = run_claude_with_mcp_tools(user_input)
            except Exception as e:
                answer = f"Ha ocurrido un error llamando a Claude/MCP: {e}"

        st.markdown(answer)

    st.session_state.chat_history_mcp.append(
        {"role": "assistant", "content": answer}
    )

st.sidebar.header("Configuración (MCP)")
st.sidebar.write(f"Modelo Anthropic: `{DEFAULT_MODEL}`")
st.sidebar.write(f"Max output tokens: `{DEFAULT_MAX_TOKENS}`")
st.sidebar.markdown(
    """
**Diferencias con `app.py`:**

- Las tools ya no se definen a mano en el cliente.
- El cliente MCP descubre los tools del servidor con `list_tools()`.
- Cualquier otra herramienta (un editor compatible con MCP, otro script)
  podría reutilizar el mismo servidor `arxiv_mcp_server.py`.
"""
)

if st.sidebar.button("Borrar historial (MCP)"):
    st.session_state.chat_history_mcp = []
    st.sidebar.success("Historial MCP borrado.")
