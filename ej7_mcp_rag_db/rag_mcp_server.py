from __future__ import annotations

from typing import Any, Dict, List
from pathlib import Path
import json
from datetime import datetime, UTC

import httpx
from mcp.server.fastmcp import FastMCP

import rag_local


BASE_DIR = Path(__file__).parent
FEEDBACK_PATH = BASE_DIR / "feedback.json"

mcp = FastMCP("incidents-rag")


async def _embed_texts(texts: List[str]) -> List[List[float]]:
    """
    Calls the OpenAI embeddings API using plain httpx.
    (The openai SDK hangs on Windows ProactorEventLoop after response processing.)
    """
    if not texts:
        return []
    async with httpx.AsyncClient() as client:
        r = await client.post(
            "https://api.openai.com/v1/embeddings",
            headers={
                "Authorization": f"Bearer {rag_local.OPENAI_API_KEY}",
                "Content-Type": "application/json",
            },
            json={"model": rag_local.EMBEDDING_MODEL, "input": texts},
            timeout=60.0,
        )
        r.raise_for_status()
        data = r.json()
    return [item["embedding"] for item in data["data"]]


async def _call_anthropic(system: str, user_text: str) -> str:
    """
    Calls the Anthropic messages API using plain httpx.
    """
    async with httpx.AsyncClient() as client:
        r = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": rag_local.ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
            json={
                "model": rag_local.MODEL,
                "max_tokens": 600,
                "system": system,
                "messages": [
                    {"role": "user", "content": [{"type": "text", "text": user_text}]}
                ],
            },
            timeout=120.0,
        )
        r.raise_for_status()
        data = r.json()
    return data["content"][0]["text"]


@mcp.tool()
async def index_tickets() -> Dict[str, Any]:
    """
    Reconstruye el índice de embeddings desde la base de datos.
    """
    tickets = rag_local._load_tickets(rag_local.DB_PATH)  # type: ignore[attr-defined]
    texts = [rag_local._prepare_text(t) for t in tickets]  # type: ignore[attr-defined]
    embeddings = await _embed_texts(texts)
    rag_local._TICKETS = tickets  # type: ignore[attr-defined]
    rag_local._EMBEDDINGS = embeddings  # type: ignore[attr-defined]
    return {"indexed_tickets": len(tickets)}


@mcp.tool()
async def rag_answer(question: str, k: int = 5) -> Dict[str, Any]:
    """
    Ejecuta el pipeline RAG y devuelve la respuesta junto con las fuentes.
    """
    question = question.strip()
    if not question:
        raise ValueError("La pregunta no puede estar vacía.")

    # Ensure the index is populated.
    if not rag_local._TICKETS or not rag_local._EMBEDDINGS:  # type: ignore[attr-defined]
        await index_tickets()

    # Embed the question.
    q_embeddings = await _embed_texts([question])
    if not q_embeddings:
        return {"answer": "No he podido generar el embedding de la pregunta.", "sources": []}
    q_embedding = q_embeddings[0]

    # Semantic search.
    scored: List[tuple] = []
    for ticket, emb in zip(
        rag_local._TICKETS, rag_local._EMBEDDINGS  # type: ignore[attr-defined]
    ):
        score = rag_local._cosine_similarity(q_embedding, emb)  # type: ignore[attr-defined]
        scored.append((ticket, score))
    scored.sort(key=lambda x: x[1], reverse=True)
    candidates = scored[: max(1, k)]

    if not candidates:
        return {
            "answer": "No he encontrado tickets relevantes para tu pregunta.",
            "sources": [],
        }

    # Build prompt and call the LLM.
    context = rag_local._build_context(question, candidates)  # type: ignore[attr-defined]

    answer_text = await _call_anthropic(
        system=(
            "Eres un asistente de soporte técnico que responde solo con la "
            "información proporcionada en los tickets de incidencias."
        ),
        user_text=context,
    )

    sources = [
        {**ticket.as_source(), "score": score}
        for ticket, score in candidates
    ]

    return {"answer": answer_text, "sources": sources}


@mcp.resource("tickets/latest/{limit}")
def resource_latest_tickets(limit: int = 5) -> List[Dict[str, Any]]:
    """
    Resource MCP de solo lectura que devuelve los últimos tickets.
    """
    tickets = rag_local._load_tickets(rag_local.DB_PATH)  # type: ignore[attr-defined]
    limited = tickets[-max(1, limit) :]
    return [t.as_source() for t in limited]


@mcp.resource("tickets/{ticket_id}")
def resource_ticket_by_id(ticket_id: int) -> Dict[str, Any] | None:
    """
    Resource MCP para recuperar un ticket concreto por id.
    """
    tickets = rag_local._load_tickets(rag_local.DB_PATH)  # type: ignore[attr-defined]
    for t in tickets:
        if t.id == ticket_id:
            return t.as_source()
    return None


@mcp.tool()
async def save_feedback(question: str, answer: str, helpful: bool) -> Dict[str, Any]:
    """
    Guarda feedback de un usuario sobre una respuesta RAG.
    """
    entry = {
        "timestamp": datetime.now(UTC).isoformat(),
        "question": question,
        "answer": answer,
        "helpful": bool(helpful),
    }

    data: List[Dict[str, Any]] = []
    if FEEDBACK_PATH.exists():
        try:
            data = json.loads(FEEDBACK_PATH.read_text(encoding="utf-8"))
        except Exception:
            data = []

    data.append(entry)
    FEEDBACK_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    return {"saved": True, "total_feedback": len(data)}


@mcp.tool()
async def list_feedback(limit: int = 10) -> List[Dict[str, Any]]:
    """
    Devuelve las últimas entradas de feedback guardadas.
    """
    if not FEEDBACK_PATH.exists():
        return []

    try:
        data = json.loads(FEEDBACK_PATH.read_text(encoding="utf-8"))
    except Exception:
        return []

    return list(data[-max(1, limit) :])


@mcp.resource("feedback/latest/{limit}")
def resource_latest_feedback(limit: int = 5) -> List[Dict[str, Any]]:
    """
    Resource MCP para leer feedback reciente sin modificar el estado.
    """
    if not FEEDBACK_PATH.exists():
        return []

    try:
        data = json.loads(FEEDBACK_PATH.read_text(encoding="utf-8"))
    except Exception:
        return []

    return list(data[-max(1, limit) :])


def main() -> None:
    """
    Lanza el servidor MCP por STDIO.
    """
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
