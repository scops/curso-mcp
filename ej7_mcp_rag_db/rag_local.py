from __future__ import annotations

import math
import os
import sqlite3
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, List, Tuple

from anthropic import Anthropic
from dotenv import load_dotenv
from openai import OpenAI


BASE_DIR = Path(__file__).parent
DB_PATH = BASE_DIR / "incidents.db"

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

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise RuntimeError("Falta OPENAI_API_KEY en el entorno / .env para embeddings")

EMBEDDING_MODEL = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")

anthropic_client = Anthropic(api_key=ANTHROPIC_API_KEY)
openai_client = OpenAI(api_key=OPENAI_API_KEY)


@dataclass
class Ticket:
    id: int
    title: str
    body: str
    tags: str
    created_at: str

    def as_source(self) -> Dict[str, Any]:
        return asdict(self)


_TICKETS: List[Ticket] = []
_EMBEDDINGS: List[List[float]] = []


def _load_tickets(db_path: Path | str = DB_PATH) -> List[Ticket]:
    path = Path(db_path)
    if not path.exists():
        raise RuntimeError(
            f"No se ha encontrado la base de datos {path}. "
            "Ejecuta primero ej7_mcp_rag_db/seed_db.py."
        )

    conn = sqlite3.connect(path)
    try:
        cur = conn.execute(
            "SELECT id, title, body, tags, created_at FROM tickets ORDER BY id"
        )
        rows = cur.fetchall()
    finally:
        conn.close()

    tickets = [
        Ticket(
            id=row[0],
            title=row[1],
            body=row[2],
            tags=row[3] or "",
            created_at=row[4],
        )
        for row in rows
    ]
    return tickets


def _prepare_text(ticket: Ticket) -> str:
    parts = [
        f"[{ticket.id}] {ticket.title}",
        ticket.body,
    ]
    if ticket.tags:
        parts.append(f"Tags: {ticket.tags}")
    return "\n\n".join(parts)


def _embed_texts(texts: List[str]) -> List[List[float]]:
    if not texts:
        return []

    response = openai_client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=texts,
    )
    return [item.embedding for item in response.data]


def _cosine_similarity(a: List[float], b: List[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a < 1e-10 or norm_b < 1e-10:
        return 0.0
    return dot / (norm_a * norm_b)


def build_index(db_path: Path | str = DB_PATH) -> int:
    """
    Carga los tickets desde la base de datos y construye
    el índice de embeddings en memoria.
    """
    global _TICKETS, _EMBEDDINGS

    tickets = _load_tickets(db_path)
    texts = [_prepare_text(t) for t in tickets]
    embeddings = _embed_texts(texts)

    _TICKETS = tickets
    _EMBEDDINGS = embeddings

    return len(_TICKETS)


def _ensure_index() -> None:
    if not _TICKETS or not _EMBEDDINGS:
        build_index(DB_PATH)


def _search_similar(
    question: str, k: int = 5
) -> List[Tuple[Ticket, float]]:
    _ensure_index()

    question_embedding_list = _embed_texts([question])
    if not question_embedding_list:
        return []
    question_embedding = question_embedding_list[0]

    scored: List[Tuple[Ticket, float]] = []
    for ticket, emb in zip(_TICKETS, _EMBEDDINGS):
        score = _cosine_similarity(question_embedding, emb)
        scored.append((ticket, score))

    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[: max(1, k)]


def _build_context(
    question: str, candidates: List[Tuple[Ticket, float]]
) -> str:
    lines: List[str] = []
    lines.append(
        "Eres un asistente de soporte técnico interno. "
        "Debes responder usando exclusivamente la información de los tickets "
        "de incidencias que se muestran a continuación."
    )
    lines.append("")
    lines.append("TICKETS RELEVANTES:")
    for ticket, score in candidates:
        lines.append(
            f"\n---\nID: {ticket.id}\nTítulo: {ticket.title}\nTags: {ticket.tags}\n"
            f"Relevancia aproximada: {score:.3f}\n"
            f"Cuerpo:\n{ticket.body}\n"
        )

    lines.append(
        "\nInstrucciones:\n"
        "- Usa solo los datos de estos tickets para contestar.\n"
        "- Si la información no es suficiente, indica claramente que no puedes "
        "responder con seguridad.\n"
        "- Si procede, propone pasos concretos de diagnóstico o solución.\n"
    )

    lines.append(f"\nPregunta del usuario:\n{question}")
    return "\n".join(lines)


def answer(question: str, k: int = 5) -> Dict[str, Any]:
    """
    Implementa el pipeline RAG local:

    - Embedding de la pregunta.
    - Búsqueda semántica sobre los tickets.
    - Construcción de contexto.
    - Llamada al modelo de chat (Anthropic).

    Devuelve un dict con:
    - 'answer': respuesta generada por el modelo.
    - 'sources': lista de tickets usados como contexto.
    """
    question = question.strip()
    if not question:
        raise ValueError("La pregunta no puede estar vacía.")

    candidates = _search_similar(question, k=k)
    if not candidates:
        return {
            "answer": "No he encontrado tickets relevantes para tu pregunta.",
            "sources": [],
        }

    context = _build_context(question, candidates)

    response = anthropic_client.messages.create(
        model=MODEL,
        max_tokens=600,
        system=(
            "Eres un asistente de soporte técnico que responde solo con la "
            "información proporcionada en los tickets de incidencias."
        ),
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": context,
                    }
                ],
            }
        ],
    )

    text_parts = [
        block.text for block in response.content if block.type == "text"
    ]
    final_answer = "\n\n".join(text_parts).strip() or (
        "No he podido generar una respuesta clara a partir de los tickets."
    )

    sources = [
        {
            **ticket.as_source(),
            "score": score,
        }
        for ticket, score in candidates
    ]

    return {
        "answer": final_answer,
        "sources": sources,
    }


def main() -> None:
    """
    Pequeño CLI para probar el RAG local sin MCP.
    """
    print("Construyendo índice de tickets desde incidents.db...")
    count = build_index(DB_PATH)
    print(f"Índice construido con {count} tickets.")

    try:
        question = input(
            "\nEscribe una pregunta sobre incidencias IT (o deja vacío para salir):\n> "
        ).strip()
    except (EOFError, KeyboardInterrupt):
        print("\nSaliendo.")
        return

    if not question:
        print("Sin pregunta. Saliendo.")
        return

    try:
        result = answer(question, k=5)
    except Exception as e:
        print(f"\n[ERROR] {e}")
        return

    print("\n=== Respuesta ===\n")
    print(result["answer"])

    print("\n=== Tickets usados como fuentes ===\n")
    for src in result["sources"]:
        print(
            f"- ID {src['id']}: {src['title']} "
            f"(score={src['score']:.3f}, tags={src['tags']})"
        )


if __name__ == "__main__":
    main()

