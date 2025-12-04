from __future__ import annotations

"""
Cliente RAG / agente SQL sobre Sakila usando LangChain.

En lugar de construir el contexto a mano, usamos el stack de LangChain
para que el modelo genere y ejecute consultas SQL sobre la base de
datos sakila (similar al ejemplo de SQL agent de LangGraph).

Esto representa el enfoque "RAG flexible/creativo" sobre la BD:
el modelo decide qué consultas lanzar y cómo combinarlas para
responder a la pregunta.
"""

import os
from typing import Any, Dict, List

from dotenv import load_dotenv
from langchain_core.language_models import ChatAnthropic
from langchain_community.agent_toolkits import (
    SQLDatabaseToolkit,
    create_sql_agent,
)
from langchain_community.utilities import SQLDatabase

from ej8_sakila_streaming.sakila_db import _get_mysql_config


load_dotenv()


MODEL = os.getenv("MODEL")
if not MODEL:
    raise RuntimeError(
        "La variable de entorno MODEL no está definida. "
        "Crea un archivo .env con una línea como: MODEL=claude-haiku-4-5-20251001"
    )

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
if not ANTHROPIC_API_KEY:
    raise RuntimeError("Falta ANTHROPIC_API_KEY en el entorno / .env")


def _build_sql_database() -> SQLDatabase:
    """
    Construye un SQLDatabase de LangChain a partir de la configuración
    de conexión usada en el ejercicio 8 (sakila).
    """
    cfg = _get_mysql_config()
    user = cfg["user"]
    password = cfg["password"]
    host = cfg["host"]
    port = cfg["port"]
    database = cfg["database"]

    uri = f"mysql+mysqlconnector://{user}:{password}@{host}:{port}/{database}"
    return SQLDatabase.from_uri(uri)


def rag_answer(question: str, k_films: int = 50) -> Dict[str, Any]:
    """
    Ejecuta un "SQL agent" al estilo LangChain sobre sakila:

    - Crea un SQLDatabase sobre sakila.
    - Construye un SQLDatabaseToolkit y un agente SQL (`create_sql_agent`).
    - Deja que el modelo genere y ejecute las consultas necesarias para
      responder a la pregunta.

    A diferencia del enfoque MCP/tool-driven, aquí el modelo ve bastante
    libertad para decidir qué consultas hacer y cómo combinarlas, a costa
    de más tokens y latencia.

    k_films se usa como `top_k` de la tool SQL (máximo de filas por consulta).
    """
    question = question.strip()
    if not question:
        raise ValueError("La pregunta no puede estar vacía.")

    db = _build_sql_database()

    llm = ChatAnthropic(model=MODEL)
    toolkit = SQLDatabaseToolkit(db=db, llm=llm)

    agent = create_sql_agent(
        llm=llm,
        toolkit=toolkit,
        agent_type="tool-calling",
        top_k=max(1, min(k_films, 200)),
        verbose=False,
    )

    result: Any = agent.invoke({"input": question})

    if isinstance(result, dict) and "output" in result:
        final_answer = str(result["output"])
    else:
        final_answer = str(result)

    return {
        "answer": final_answer,
        # Mantenemos la clave por compatibilidad, aunque el agente SQL
        # no expone directamente cuántas filas ha usado.
        "films_used": None,
    }


def main() -> None:
    """
    Pequeño CLI manual de prueba.
    """
    try:
        question = input(
            "Pregunta algo sobre el catálogo sakila (o vacío para salir):\n> "
        ).strip()
    except (EOFError, KeyboardInterrupt):
        print("\nSaliendo.")
        return

    if not question:
        print("Sin pregunta. Saliendo.")
        return

    result = rag_answer(question)
    print("\n=== Respuesta RAG ===\n")
    print(result["answer"])


if __name__ == "__main__":
    main()
