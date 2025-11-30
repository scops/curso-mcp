from __future__ import annotations

from typing import Any, Dict, List
from pathlib import Path
import json
from datetime import datetime, UTC

from mcp.server.fastmcp import FastMCP

import rag_local


BASE_DIR = Path(__file__).parent
FEEDBACK_PATH = BASE_DIR / "feedback.json"


mcp = FastMCP("incidents-rag")


@mcp.tool()
async def index_tickets() -> Dict[str, Any]:
    """
    Reconstruye el índice de embeddings desde la base de datos.
    """
    count = rag_local.build_index()
    return {"indexed_tickets": count}


@mcp.tool()
async def rag_answer(question: str, k: int = 5) -> Dict[str, Any]:
    """
    Ejecuta el pipeline RAG y devuelve la respuesta junto con las fuentes.
    """
    return rag_local.answer(question=question, k=k)


@mcp.resource("tickets/latest/{limit}")
def resource_latest_tickets(limit: int = 5) -> List[Dict[str, Any]]:
    """
    Resource MCP de solo lectura que devuelve los últimos tickets.

    A diferencia de rag_answer (tool), este recurso no ejecuta el pipeline RAG
    ni llama al modelo, solo expone datos de la base de conocimiento.
    """
    # Nos apoyamos en build_index() para asegurarnos de que hay tickets cargados.
    rag_local.build_index()

    # Accedemos a los tickets a través de la función privada de carga.
    # No recalculamos embeddings aquí: solo necesitamos los datos brutos.
    tickets = rag_local._load_tickets(rag_local.DB_PATH)  # type: ignore[attr-defined]
    limited = tickets[-max(1, limit) :]
    return [t.as_source() for t in limited]


@mcp.resource("tickets/{ticket_id}")
def resource_ticket_by_id(ticket_id: int) -> Dict[str, Any] | None:
    """
    Resource MCP para recuperar un ticket concreto por id.

    Devuelve el ticket como dict o None si no existe.
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

    Esto ilustra c_mem: memoria persistente sencilla almacenada en disco.
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
