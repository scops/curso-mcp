from __future__ import annotations

"""
Benchmark sencillo RAG vs MCP sobre sakila.

Ejecuta la misma pregunta contra:
- RAG flexible: `sakila_rag_client.rag_answer`
- MCP + LangChain tool-driven: `mcp_langchain_client.mcp_answer`

Y mide el tiempo de respuesta de cada enfoque.
"""

import time
from typing import Any, Dict

from sakila_rag_client import rag_answer
from mcp_langchain_client import mcp_answer


def run_single_benchmark(question: str) -> Dict[str, Any]:
    """
    Ejecuta el benchmark para una sola pregunta.
    """
    # RAG
    t0 = time.perf_counter()
    rag_result = rag_answer(question)
    t1 = time.perf_counter()

    # MCP + LangChain
    t2 = time.perf_counter()
    mcp_result = mcp_answer(question)
    t3 = time.perf_counter()

    return {
        "question": question,
        "rag": {
            "seconds": t1 - t0,
            "answer_preview": rag_result["answer"][:400],
            "films_used": rag_result.get("films_used"),
        },
        "mcp": {
            "seconds": t3 - t2,
            "answer_preview": str(mcp_result)[:400],
        },
    }


def main() -> None:
    questions = [
        "Recomiéndame 3 películas de acción y dime por qué encajan.",
        "Quiero una película familiar con rating PG o G.",
        "Dame una película de comedia reciente y una breve sinopsis.",
    ]

    print("=== Benchmark RAG vs MCP (sakila) ===\n")

    for q in questions:
        print(f"Pregunta: {q}\n")
        result = run_single_benchmark(q)

        rag_info: Dict[str, Any] = result["rag"]
        mcp_info: Dict[str, Any] = result["mcp"]

        films_used = rag_info.get("films_used")
        context_str = (
            f"{films_used} películas en contexto"
            if isinstance(films_used, int)
            else "contexto vía agente SQL (no medido)"
        )

        print(
            f"- RAG  -> {rag_info['seconds']:.2f} s, {context_str}"
        )
        print(f"- MCP  -> {mcp_info['seconds']:.2f} s\n")

        print("Preview RAG:\n", rag_info["answer_preview"], "\n")
        print("Preview MCP:\n", mcp_info["answer_preview"], "\n")
        print("=" * 60, "\n")


if __name__ == "__main__":
    main()
