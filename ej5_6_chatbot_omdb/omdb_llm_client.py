import asyncio
import json
import os

import streamlit as st
from anthropic import Anthropic
from dotenv import load_dotenv
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

# ----------------- Configuración -----------------

load_dotenv()

MCP_URL = os.getenv("OMDB_MCP_URL", "http://127.0.0.1:8000/mcp")

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
if not ANTHROPIC_API_KEY:
    raise RuntimeError("Falta ANTHROPIC_API_KEY en el entorno / .env")

ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-3-5-sonnet-latest")

llm_client = Anthropic(api_key=ANTHROPIC_API_KEY)


# ----------------- Lógica MCP + LLM -----------------

async def ask_llm_with_mcp(user_query):
    """
    Orquesta una conversación con Claude usando tools expuestos
    por el servidor MCP OMDb.

    Flujo:
    1) Conecta al servidor MCP por HTTP.
    2) Obtiene tools (search_movies, get_movie_details, ...).
    3) Llama a Claude con la pregunta + tools.
    4) Si Claude pide tool_use:
         - llama al tool en el servidor MCP
         - entrega tool_result de vuelta a Claude
       y repite hasta 3 pasos.
    5) Devuelve respuesta final en texto.
    """

    async with streamablehttp_client(MCP_URL) as (read, write, _get_session_id):
        async with ClientSession(read, write) as session:
            await session.initialize()

            # 1) Descubrimos tools en el servidor MCP
            tools_response = await session.list_tools()
            available_tools = []
            for tool in tools_response.tools:
                available_tools.append(
                    {
                        "name": tool.name,
                        "description": tool.description,
                        "input_schema": tool.inputSchema,
                    }
                )

            # 2) Mensajes iniciales para Claude
            messages = [
                {
                    "role": "user",
                    "content": (
                        "Eres un asistente experto en cine y series.\n"
                        "Tienes acceso a herramientas que consultan la API de OMDb.\n"
                        "Cuando necesites datos concretos (títulos, años, reparto, sinopsis), "
                        "usa esas herramientas y luego responde en español, "
                        "de forma clara y breve.\n\n"
                        f"Pregunta del usuario: {user_query}"
                    ),
                }
            ]

            # Bucle de hasta 3 pasos herramienta -> respuesta final
            for _ in range(3):
                response = llm_client.messages.create(
                    model=ANTHROPIC_MODEL,
                    max_tokens=800,
                    messages=messages,
                    tools=available_tools,
                )

                tool_uses = [c for c in response.content if c.type == "tool_use"]
                text_blocks = [c for c in response.content if c.type == "text"]

                # 3) Si no hay tool_use, devolvemos el texto directamente
                if not tool_uses:
                    final_text = "\n\n".join(tb.text for tb in text_blocks) if text_blocks else ""
                    if final_text:
                        messages.append({"role": "assistant", "content": final_text})
                    return final_text

                # 4) Hay tool_use: añadimos el mensaje del assistant con esos tool_use
                messages.append(
                    {
                        "role": "assistant",
                        "content": response.content,
                    }
                )

                # 5) Ejecutamos cada tool en el servidor MCP
                for tu in tool_uses:
                    tool_name = tu.name
                    tool_args = tu.input
                    tool_id = tu.id

                    # Llamada al servidor MCP
                    tool_result = await session.call_tool(tool_name, tool_args)

                    # Convertimos el resultado en JSON de texto para Claude
                    if hasattr(tool_result, "model_dump"):
                        tool_payload = tool_result.model_dump(mode="json")
                    else:
                        tool_payload = {"raw_result": str(tool_result)}

                    tool_result_text = json.dumps(
                        tool_payload, ensure_ascii=False, indent=2
                    )

                    # 6) Añadimos un mensaje de tipo tool_result para Claude
                    messages.append(
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "tool_result",
                                    "tool_use_id": tool_id,
                                    "content": tool_result_text,
                                }
                            ],
                        }
                    )

            # Si llega aquí, demasiados pasos sin texto final claro
            return "He usado varias herramientas pero no he obtenido una respuesta clara. Intenta reformular tu pregunta."


def ask_llm_with_mcp_sync(user_query):
    """
    Wrapper síncrono para usar desde Streamlit.
    """
    return asyncio.run(ask_llm_with_mcp(user_query))


# ----------------- UI Streamlit -----------------

st.set_page_config(page_title="Asistente de cine · OMDb + MCP + IA", layout="wide")

st.title("Asistente de cine · OMDb + MCP + IA")
st.caption(
    f"Servidor MCP: `{MCP_URL}` · Modelo: `{ANTHROPIC_MODEL}`"
)

st.markdown(
    """
Este cliente **no** llama directamente a la API de OMDb.

En su lugar:

1. Se conecta a un **servidor MCP** que expone tools (`search_movies`, `get_movie_details`).
2. Pasa la descripción de esos tools a un **LLM (Claude)**.
3. El LLM decide cuándo llamar a cada tool (via MCP) y construye la respuesta final.

Es decir, aquí estás viendo **la integración real LLM + MCP**, no solo un "Postman con UI".
"""
)

# Historial simple en sesión
if "history" not in st.session_state:
    st.session_state.history = []

for msg in st.session_state.history:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

user_input = st.chat_input("Pregunta algo sobre películas o series...")

if user_input:
    # Mostrar pregunta
    st.session_state.history.append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.markdown(user_input)

    # Llamar a la IA con MCP
    with st.chat_message("assistant"):
        with st.spinner("Consultando OMDb a través del servidor MCP..."):
            try:
                answer = ask_llm_with_mcp_sync(user_input)
            except Exception as e:
                answer = f"Ha ocurrido un error llamando a la IA con MCP: {e}"

        st.markdown(answer)

    st.session_state.history.append({"role": "assistant", "content": answer})

# Sidebar
st.sidebar.header("Opciones")
st.sidebar.write("Este cliente usa MCP vía HTTP (streamable-http).")

if st.sidebar.button("Borrar historial"):
    st.session_state.history = []
    st.sidebar.success("Historial borrado.")
