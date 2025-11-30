from __future__ import annotations

import math
import os
from typing import Any, Dict, List, Tuple

from anthropic import Anthropic
from dotenv import load_dotenv
from openai import OpenAI


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


TICKETS: List[Dict[str, Any]] = [
    {
        "id": 1,
        "title": "Error 500 en la API de usuarios",
        "body": (
            "Los usuarios reportan errores 500 al iniciar sesión. "
            "En los logs aparece `database is locked` al acceder a la tabla "
            "`sessions`."
        ),
        "tags": "api,login,error-500,sqlite,lock",
        "created_at": "2025-01-10T09:15:00Z",
    },
    {
        "id": 2,
        "title": "Timeout en panel de administración",
        "body": (
            "El panel /admin/ tarda más de 60 segundos y a veces devuelve 504. "
            "Ocurre desde el despliegue de la versión 2.3.0."
        ),
        "tags": "admin,timeout,nginx,504,deploy",
        "created_at": "2025-01-09T16:30:00Z",
    },
    {
        "id": 3,
        "title": "Problemas con restablecimiento de contraseña",
        "body": (
            "Los correos de reset de contraseña no llegan. "
            "En el servicio SMTP se observan errores de autenticación."
        ),
        "tags": "password-reset,email,smtp,auth",
        "created_at": "2025-01-08T11:05:00Z",
    },
]


def _prepare_text(ticket: Dict[str, Any]) -> str:
    parts = [
        f"[{ticket['id']}] {ticket['title']}",
        ticket["body"],
    ]
    if ticket.get("tags"):
        parts.append(f"Tags: {ticket['tags']}")
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
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def _search_similar(
    question: str, k: int = 5
) -> List[Tuple[Dict[str, Any], float]]:
    ticket_texts = [_prepare_text(t) for t in TICKETS]
    ticket_embs = _embed_texts(ticket_texts)
    question_emb_list = _embed_texts([question])

    if not question_emb_list or not ticket_embs:
        return []

    q_emb = question_emb_list[0]
    scored: List[Tuple[Dict[str, Any], float]] = []
    for ticket, emb in zip(TICKETS, ticket_embs):
        score = _cosine_similarity(q_emb, emb)
        scored.append((ticket, score))

    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[: max(1, k)]


def _build_context(
    question: str, candidates: List[Tuple[Dict[str, Any], float]]
) -> str:
    lines: List[str] = []
    lines.append(
        "Eres un asistente de soporte técnico. "
        "Responde usando únicamente la información de los tickets."
    )
    lines.append("")
    lines.append("TICKETS RELEVANTES:")

    for ticket, score in candidates:
        lines.append(
            f"\n---\nID: {ticket['id']}\nTítulo: {ticket['title']}\nTags: {ticket.get('tags', '')}\n"
            f"Relevancia aproximada: {score:.3f}\n"
            f"Cuerpo:\n{ticket['body']}\n"
        )

    lines.append(
        "\nInstrucciones:\n"
        "- No inventes datos fuera de lo que dicen los tickets.\n"
        "- Si no hay información suficiente, dilo explícitamente.\n"
    )

    lines.append(f"\nPregunta del usuario:\n{question}")
    return "\n".join(lines)


def answer(question: str, k: int = 5) -> Dict[str, Any]:
    """
    Versión mínima del pipeline RAG:

    - Tickets en memoria (sin base de datos).
    - Embeddings vía OpenAI.
    - Similitud coseno implementada a mano.
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
            "información de los tickets proporcionados."
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
            **ticket,
            "score": score,
        }
        for ticket, score in candidates
    ]

    return {
        "answer": final_answer,
        "sources": sources,
    }


def main() -> None:
    print("Ejemplo mínimo de RAG sin base de datos ni MCP.")

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
        result = answer(question, k=3)
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

