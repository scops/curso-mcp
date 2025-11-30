# app.py
from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Tuple

import streamlit as st
from anthropic import Anthropic
from dotenv import load_dotenv

from tools_arxiv import search_papers, extract_info

# -----------------------
# Configuración básica
# -----------------------

load_dotenv()

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
if not ANTHROPIC_API_KEY:
    raise RuntimeError("Falta ANTHROPIC_API_KEY en el entorno / .env")

client = Anthropic(api_key=ANTHROPIC_API_KEY)

DEFAULT_MODEL = os.getenv("MODEL", "claude-haiku-4-5-20251001")  # alias estable 
DEFAULT_MAX_TOKENS = int(os.getenv("ANTHROPIC_MAX_TOKENS", "800"))


# -----------------------
# Definición de tools para Claude
# -----------------------

TOOLS: List[Dict[str, Any]] = [
    {
        "name": "search_papers",
        "description": (
            "Busca artículos en arXiv sobre un tema y guarda un índice local "
            "con los metadatos de los artículos encontrados."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "topic": {
                    "type": "string",
                    "description": "Tema de la búsqueda. Ejemplo: 'quantum computing'",
                },
                "max_results": {
                    "type": "integer",
                    "description": "Número máximo de resultados a recuperar (1-20).",
                    "default": 5,
                    "minimum": 1,
                    "maximum": 20,
                },
            },
            "required": ["topic"],
        },
    },
    {
        "name": "extract_info",
        "description": (
            "Busca información detallada de un artículo concreto de arXiv, "
            "usando el índice local generado por búsquedas anteriores."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "paper_id": {
                    "type": "string",
                    "description": "ID corto del paper, por ejemplo '2102.10073v1'.",
                }
            },
            "required": ["paper_id"],
        },
    },
]


# -----------------------
# Ejecutor local de tools
# -----------------------

def execute_tool_locally(name: str, args: Dict[str, Any]) -> str:
    """
    Ejecuta la herramienta Python correspondiente y devuelve
    una cadena JSON para pasársela a Claude como tool_result.
    """
    if name == "search_papers":
        topic = args.get("topic", "")
        max_results = int(args.get("max_results", 5))
        result = search_papers(topic=topic, max_results=max_results)
        return json.dumps(result, ensure_ascii=False, indent=2)

    if name == "extract_info":
        paper_id = args.get("paper_id", "")
        result = extract_info(paper_id=paper_id)
        return json.dumps(result, ensure_ascii=False, indent=2)

    # Tool desconocido
    return json.dumps(
        {
            "error": f"Herramienta desconocida: {name}",
            "args": args,
        },
        ensure_ascii=False,
        indent=2,
    )


# -----------------------
# Orquestación: Claude + tools
# -----------------------

def run_claude_with_tools(
    user_query: str,
    model: str = DEFAULT_MODEL,
    max_tokens: int = DEFAULT_MAX_TOKENS,
) -> Tuple[str, List[Dict[str, Any]]]:
    """
    Ejecuta una interacción con Claude usando herramientas.

    Hace lo siguiente:
    1. Envía la consulta del usuario + tools.
    2. Si Claude decide usar tools (tool_use), ejecuta los tools locales.
    3. Envía los resultados (tool_result) a Claude.
    4. Devuelve el texto final y la lista de mensajes que se podrían usar como historial.
    """

    messages: List[Dict[str, Any]] = [
        {
            "role": "user",
            "content": user_query,
        }
    ]

    # Bucle simple: como máximo 3 rondas de tool_use → respuesta final
    for _ in range(3):
        response = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            tools=TOOLS,
            messages=messages,
        )

        tool_uses = [c for c in response.content if c.type == "tool_use"]
        text_blocks = [c for c in response.content if c.type == "text"]

        # Si no hay tool_use, devolvemos la respuesta textual directamente
        if not tool_uses:
            final_text = "\n\n".join(block.text for block in text_blocks) if text_blocks else ""
            # Añadimos como mensaje assistant al historial
            if final_text:
                messages.append(
                    {
                        "role": "assistant",
                        "content": final_text,
                    }
                )
            return final_text, messages

        # Si hay tool_use, añadimos este paso como salida del assistant
        messages.append(
            {
                "role": "assistant",
                "content": response.content,
            }
        )

        # Ejecutamos cada tool y añadimos su resultado
        for tool_call in tool_uses:
            tool_name = tool_call.name
            tool_input = tool_call.input
            tool_id = tool_call.id

            result_str = execute_tool_locally(tool_name, tool_input)

            # Enviamos el resultado a Claude como mensaje de tipo tool_result
            messages.append(
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": tool_id,
                            "content": result_str,
                        }
                    ],
                }
            )

    # Si llegamos aquí es que hemos dado demasiadas vueltas
    return "He alcanzado el número máximo de pasos de herramientas sin una respuesta final clara.", messages


# -----------------------
# UI Streamlit
# -----------------------

st.set_page_config(page_title="Chatbot arXiv · Claude + Tools", page_icon="📚")

st.title("Chatbot arXiv · Claude + Tools")
st.markdown(
    """
Este ejemplo muestra cómo un **LLM con herramientas** puede:

- Buscar artículos en **arXiv** sobre un tema (`search_papers`).
- Consultar detalles de un paper concreto a partir de su ID (`extract_info`).

Todo el código corre **en local** y puedes inspeccionar tanto las funciones
Python como las llamadas a la API de Anthropic.
"""
)

# Inicializar historial de chat en sesión
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []

# Mostrar historial
for msg in st.session_state.chat_history:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# Entrada del usuario
user_input = st.chat_input("Haz una pregunta sobre papers de arXiv...")

if user_input:
    # Mostrar mensaje del usuario
    st.session_state.chat_history.append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.markdown(user_input)

    # Llamar a Claude con tools
    with st.chat_message("assistant"):
        with st.spinner("Pensando con herramientas..."):
            try:
                answer, _messages = run_claude_with_tools(user_input)
            except Exception as e:
                answer = f"Ha ocurrido un error llamando a Claude: {e}"

        st.markdown(answer)

    st.session_state.chat_history.append({"role": "assistant", "content": answer})

# Panel lateral
st.sidebar.header("Configuración")
st.sidebar.write(f"Modelo Anthropic: `{DEFAULT_MODEL}`")
st.sidebar.write(f"Max output tokens: `{DEFAULT_MAX_TOKENS}`")
st.sidebar.markdown(
    """
**Tips de uso:**

- Pregunta: *"Búscame 3 artículos recientes sobre 'large language models' y dime sus títulos."*  
- Luego: *"Dame más detalles del primer paper, usando su ID."*  
"""
)

if st.sidebar.button("Borrar historial"):
    st.session_state.chat_history = []
    st.sidebar.success("Historial borrado.")
