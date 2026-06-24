import asyncio
import json
import os

import streamlit as st
from anthropic import Anthropic
from dotenv import load_dotenv
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

# ============================================================================
# VERSIÓN "CON CONTEXTO" (ctx) del cliente OMDb + MCP + LLM
# ----------------------------------------------------------------------------
# Diferencia respecto a omdb_llm_client.py:
#
#   - omdb_llm_client.py construía `messages = [...]` DESDE CERO en cada
#     pregunta. Resultado: Claude no recordaba nada del turno anterior, así
#     que ante "dame más info sobre la primera" no sabía a qué nos referíamos.
#
#   - Aquí mantenemos un HISTORIAL DE MENSAJES persistente (el "contexto"
#     conversacional, que llamamos `ctx`) en st.session_state. Ese ctx se le
#     pasa íntegro a Claude en cada turno, de modo que el modelo "recuerda"
#     títulos, búsquedas y resultados previos y puede resolver referencias
#     como "la primera", "esa serie", "la trilogía anterior", etc.
#
# Qué es `ctx` exactamente:
#   Es una lista de mensajes en el formato de la API de Anthropic:
#       [
#         {"role": "user",      "content": "..."},
#         {"role": "assistant", "content": [TextBlock | ToolUseBlock, ...]},
#         {"role": "user",      "content": [{"type": "tool_result", ...}]},
#         ...
#       ]
#   Incluye tanto el texto como los pasos de herramientas (tool_use /
#   tool_result), para que el modelo tenga memoria COMPLETA de la conversación.
# ============================================================================


# ----------------- Configuración -----------------

load_dotenv()

MCP_URL = os.getenv("OMDB_MCP_URL", "http://127.0.0.1:8000/mcp")

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
if not ANTHROPIC_API_KEY:
    raise RuntimeError("Falta ANTHROPIC_API_KEY en el entorno / .env")

ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")

llm_client = Anthropic(api_key=ANTHROPIC_API_KEY)

# MEJORA 1: las instrucciones del asistente van en `system`, NO dentro del
# primer mensaje de usuario. Así no se repiten en cada turno y no "ensucian"
# el contexto conversacional. Además le decimos explícitamente al modelo que
# use el historial para resolver referencias ambiguas.
SYSTEM_PROMPT = (
    "Eres un asistente experto en cine y series. "
    "Tienes acceso a herramientas que consultan la API de OMDb "
    "(search_movies, get_movie_detail). "
    "Cuando necesites datos concretos (títulos, años, reparto, sinopsis), "
    "usa esas herramientas y luego responde en español, de forma clara y breve.\n\n"
    "IMPORTANTE: mantén el hilo de la conversación. Si el usuario usa "
    "referencias como 'la primera', 'esa película', 'la trilogía anterior' o "
    "'el segundo resultado', interpreta a qué se refiere usando los mensajes "
    "y resultados ANTERIORES del historial, en lugar de volver a preguntar."
)

# MEJORA 2: límite opcional de memoria. El contexto crece turno a turno; si no
# lo acotamos, gastaremos cada vez más tokens (esto enlaza con el ejercicio
# ej12_mcp_token_optimization). Aquí guardamos como mucho los últimos N
# mensajes "crudos" de la conversación.
MAX_CTX_MESSAGES = int(os.getenv("MAX_CTX_MESSAGES", "20"))


# ----------------- Lógica MCP + LLM (con contexto) -----------------

async def ask_llm_with_ctx(ctx):
    """
    Orquesta una conversación con Claude usando los tools del servidor MCP OMDb,
    PERO conservando el contexto conversacional.

    Parámetros
    ----------
    ctx : list
        Historial de mensajes (formato API Anthropic) que YA incluye el nuevo
        mensaje del usuario al final. Esta lista representa la "memoria" de la
        conversación. Se MUTA in-place (se le añaden las respuestas del modelo
        y los resultados de las tools) y se devuelve para persistirla.

    Devuelve
    --------
    (final_text, ctx) : tuple[str, list]
        El texto final para mostrar y el contexto actualizado.

    Flujo:
      1) Conecta al servidor MCP por HTTP y descubre los tools.
      2) Llama a Claude pasándole TODO el ctx (no solo la última pregunta).
      3) Si Claude pide tool_use -> ejecuta el tool en MCP y añade el
         tool_result al ctx; repite hasta 3 vueltas.
      4) Devuelve la respuesta final y el ctx actualizado.
    """

    async with streamable_http_client(MCP_URL) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()

            # 1) Descubrimos tools en el servidor MCP
            tools_response = await session.list_tools()
            available_tools = [
                {
                    "name": tool.name,
                    "description": tool.description,
                    "input_schema": tool.inputSchema,
                }
                for tool in tools_response.tools
            ]

            # Bucle agéntico acotado a 3 vueltas de "el modelo pide tools ->
            # ejecutamos -> el modelo razona de nuevo". El tope evita bucles
            # infinitos y limita coste/latencia. 3 basta para el flujo típico:
            # buscar, (opcional) pedir el detalle de un resultado, y redactar
            # la respuesta final.
            for _ in range(3):
                # CLAVE DEL CONTEXTO: pasamos `ctx` completo, no un mensaje
                # nuevo aislado. Claude ve toda la conversación previa.
                response = llm_client.messages.create(
                    model=ANTHROPIC_MODEL,
                    max_tokens=800,
                    system=SYSTEM_PROMPT,
                    messages=ctx,
                    tools=available_tools,
                )

                tool_uses = [c for c in response.content if c.type == "tool_use"]
                text_blocks = [c for c in response.content if c.type == "text"]

                # 2) Si no hay tool_use, tenemos respuesta final.
                #    La guardamos en el ctx para que forme parte de la memoria.
                if not tool_uses:
                    final_text = "\n\n".join(tb.text for tb in text_blocks) if text_blocks else ""
                    if final_text:
                        ctx.append({"role": "assistant", "content": final_text})
                    return final_text, ctx

                # 3) Hay tool_use: añadimos al ctx el mensaje del assistant con
                #    esos bloques de herramienta (forma parte de la memoria).
                ctx.append({"role": "assistant", "content": response.content})

                # 4) Ejecutamos cada tool en el servidor MCP y añadimos su
                #    resultado al ctx como tool_result.
                for tu in tool_uses:
                    tool_result = await session.call_tool(tu.name, tu.input)

                    if hasattr(tool_result, "model_dump"):
                        tool_payload = tool_result.model_dump(mode="json")
                    else:
                        tool_payload = {"raw_result": str(tool_result)}

                    tool_result_text = json.dumps(
                        tool_payload, ensure_ascii=False, indent=2
                    )

                    ctx.append(
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "tool_result",
                                    "tool_use_id": tu.id,
                                    "content": tool_result_text,
                                }
                            ],
                        }
                    )

            # Demasiados pasos sin texto final claro
            fallback = (
                "He usado varias herramientas pero no he obtenido una respuesta "
                "clara. Intenta reformular tu pregunta."
            )
            ctx.append({"role": "assistant", "content": fallback})
            return fallback, ctx


def trim_ctx(ctx, max_messages=MAX_CTX_MESSAGES):
    """
    MEJORA 2 (gestión de memoria): recorta el contexto para que no crezca sin
    límite. Nos quedamos con los últimos `max_messages` mensajes.

    Nota didáctica: recortar "a lo bruto" puede dejar un tool_use sin su
    tool_result correspondiente, lo que la API rechaza. Por eso, si el primer
    mensaje que conservamos es un tool_result "huérfano", lo descartamos hasta
    empezar en un turno limpio de usuario/assistant.
    """
    if len(ctx) <= max_messages:
        return ctx

    recortado = ctx[-max_messages:]

    # Evitamos empezar con un tool_result sin su tool_use previo.
    while recortado:
        primero = recortado[0]
        content = primero.get("content")
        es_tool_result = (
            isinstance(content, list)
            and content
            and isinstance(content[0], dict)
            and content[0].get("type") == "tool_result"
        )
        if es_tool_result:
            recortado = recortado[1:]
        else:
            break

    return recortado


def ask_llm_with_ctx_sync(ctx):
    """Wrapper síncrono para usar desde Streamlit."""
    return asyncio.run(ask_llm_with_ctx(ctx))


# ----------------- UI Streamlit -----------------

st.set_page_config(page_title="Asistente de cine · OMDb + MCP + IA (con contexto)", layout="wide")

st.title("Asistente de cine · OMDb + MCP + IA (con contexto)")
st.caption(
    f"Servidor MCP: `{MCP_URL}` · Modelo: `{ANTHROPIC_MODEL}` · "
    f"Memoria: últimos {MAX_CTX_MESSAGES} mensajes"
)

st.markdown(
    """
Versión **con contexto conversacional (`ctx`)** del cliente OMDb + MCP + IA.

A diferencia de `omdb_llm_client.py`, aquí el modelo **recuerda** los turnos
anteriores:

1. Se conecta a un **servidor MCP** que expone tools (`search_movies`, `get_movie_detail`).
2. Mantiene el **historial completo** de la conversación (`ctx`) en `st.session_state`.
3. En cada pregunta le pasa a Claude **todo el `ctx`**, no solo la última frase.

Así puedes decir *"dame más info sobre la primera"* y el modelo sabrá a qué
te refieres a partir del listado anterior.
"""
)

# ctx = la memoria REAL que ve Claude (formato API). Persiste entre reruns de
# Streamlit gracias a st.session_state.
if "ctx" not in st.session_state:
    st.session_state.ctx = []

# Historial SOLO para pintar el chat (texto plano). Lo separamos del ctx porque
# el ctx contiene objetos de tool_use/tool_result que no queremos renderizar.
if "chat_view" not in st.session_state:
    st.session_state.chat_view = []

for msg in st.session_state.chat_view:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

user_input = st.chat_input("Pregunta algo sobre películas o series...")

if user_input:
    # 1) Añadimos la pregunta TANTO al ctx (memoria del modelo) como a la
    #    vista del chat (lo que ve el humano).
    st.session_state.ctx.append({"role": "user", "content": user_input})
    st.session_state.chat_view.append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.markdown(user_input)

    # 2) Llamamos a la IA pasándole el ctx completo.
    with st.chat_message("assistant"):
        with st.spinner("Consultando OMDb a través del servidor MCP (con memoria)..."):
            try:
                answer, ctx_actualizado = ask_llm_with_ctx_sync(st.session_state.ctx)
                # 3) Recortamos el ctx para no gastar tokens de más y lo
                #    guardamos de vuelta en la sesión.
                st.session_state.ctx = trim_ctx(ctx_actualizado)
            except Exception as e:
                answer = f"Ha ocurrido un error llamando a la IA con MCP: {e}"

        st.markdown(answer)

    st.session_state.chat_view.append({"role": "assistant", "content": answer})

# Sidebar
st.sidebar.header("Opciones")
st.sidebar.write("Este cliente usa MCP vía HTTP (streamable-http) **con contexto**.")
st.sidebar.metric("Mensajes en memoria (ctx)", len(st.session_state.ctx))

if st.sidebar.button("Borrar historial"):
    # IMPORTANTE: al borrar hay que limpiar AMBAS cosas: la vista y el ctx.
    # Si olvidas el ctx, el modelo seguiría "recordando" lo anterior.
    st.session_state.chat_view = []
    st.session_state.ctx = []
    st.sidebar.success("Historial y contexto borrados.")
