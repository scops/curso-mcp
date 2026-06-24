"""
Benchmark de tokens: vanilla vs MCP-naive vs MCP-optimizado.

Lanza el MISMO conjunto de consultas con tres estrategias y mide los tokens
reales que consume el modelo (campo `usage` de la API de Anthropic):

  1. vanilla       → 2 tools escritas a mano (lo que necesitas y nada más).
  2. mcp_naive     → conecta al servidor MCP y vuelca TODAS las tools del
                     catálogo (14) en cada llamada al modelo. Patrón por defecto.
  3. mcp_optimized → mismo servidor MCP, pero el cliente filtra el catálogo y
                     solo envía las tools relevantes para la consulta
                     (tool retrieval / progressive disclosure).

La diferencia clave entre 2 y 3 es UNA sola variable: cuántas definiciones de
tools se envían al modelo. Eso aísla la lección: las definiciones de tools son
tokens, y se reenvían en cada turno.

Imprime una tabla local con los números (no necesita Langfuse) y, si hay claves
de Langfuse en el entorno, además sube las trazas para verlo en la UI.

Uso (desde la raíz del curso `mcp/`):

    uv run python ej12_mcp_token_optimization/benchmark_token_optimization.py
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import sys
from contextlib import AsyncExitStack
from pathlib import Path
from typing import Any, Callable, Dict, List, Tuple

from dotenv import load_dotenv

# 1. Entorno + Langfuse ANTES de importar Anthropic (para instrumentarlo).
load_dotenv()
from langfuse_setup import init_langfuse, observe, propagate_attributes  # noqa: E402

langfuse = init_langfuse(instrument_anthropic=True)

from anthropic import Anthropic  # noqa: E402
from mcp import ClientSession, StdioServerParameters  # noqa: E402
from mcp.client.stdio import stdio_client  # noqa: E402

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
if not ANTHROPIC_API_KEY:
    raise RuntimeError("Falta ANTHROPIC_API_KEY en el entorno / .env")

client = Anthropic(api_key=ANTHROPIC_API_KEY)
MODEL = os.getenv("MODEL", "claude-haiku-4-5")
MAX_TOKENS = int(os.getenv("ANTHROPIC_MAX_TOKENS", "600"))

SERVER_PATH = str(Path(__file__).parent / "many_tools_mcp_server.py")
OPTIMIZED_TOP_K = 3


# ---------------------------------------------------------------------------
# Consultas de prueba (deterministas, una tool por consulta)
# ---------------------------------------------------------------------------

QUERIES: List[Dict[str, str]] = [
    {
        "id": "q1-search",
        "text": (
            "Busca 3 artículos sobre 'retrieval augmented generation' "
            "y dame solo sus títulos."
        ),
    },
    {
        "id": "q2-detail",
        "text": (
            "Dame la información detallada del paper 2401.1001: "
            "título, autores y año."
        ),
    },
]


# ---------------------------------------------------------------------------
# Estrategia VANILLA: 2 tools escritas a mano + ejecución local sintética
# ---------------------------------------------------------------------------

VANILLA_TOOLS: List[Dict[str, Any]] = [
    {
        "name": "search_papers",
        "description": "Busca artículos en arXiv sobre un tema y devuelve sus metadatos.",
        "input_schema": {
            "type": "object",
            "properties": {
                "topic": {"type": "string", "description": "Tema de búsqueda."},
                "max_results": {"type": "integer", "default": 5},
            },
            "required": ["topic"],
        },
    },
    {
        "name": "extract_info",
        "description": "Devuelve información detallada de un paper concreto por su arxiv_id.",
        "input_schema": {
            "type": "object",
            "properties": {"paper_id": {"type": "string"}},
            "required": ["paper_id"],
        },
    },
]


def _local_search(topic: str, max_results: int = 5) -> Dict[str, Any]:
    papers = [
        {
            "arxiv_id": f"24{i:02d}.{1000 + i}",
            "title": f"Paper sintético #{i} sobre el tema solicitado",
            "year": 2024,
        }
        for i in range(1, max(1, min(max_results, 7)) + 1)
    ]
    return {"topic": topic, "count": len(papers), "papers": papers}


def _local_extract(paper_id: str) -> Dict[str, Any]:
    return {
        "arxiv_id": paper_id,
        "title": f"Detalle sintético del paper {paper_id}",
        "authors": ["A. Autor", "B. Coautora"],
        "year": 2024,
    }


async def _execute_vanilla(name: str, args: Dict[str, Any]) -> str:
    if name == "search_papers":
        result = _local_search(args.get("topic", ""), int(args.get("max_results", 5)))
    elif name == "extract_info":
        result = _local_extract(args.get("paper_id", ""))
    else:
        result = {"error": f"tool desconocida: {name}"}
    return json.dumps(result, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Selección de tools relevantes (la "optimización" de la variante 3)
# ---------------------------------------------------------------------------

_STOP = {
    "de", "la", "el", "los", "las", "un", "una", "y", "o", "sobre", "para",
    "con", "del", "me", "dame", "sus", "que", "mas", "más", "por", "su", "solo",
    "sólo", "the", "and",
}


def _tokenize(text: str) -> List[str]:
    words = re.findall(r"[a-záéíóúñ]+", text.lower())
    return [w for w in words if w not in _STOP and len(w) > 2]


def select_relevant_tools(
    query: str, tools: List[Dict[str, Any]], k: int = OPTIMIZED_TOP_K
) -> List[Dict[str, Any]]:
    """
    Tool retrieval simple por solapamiento de palabras entre la consulta y el
    (nombre + descripción) de cada tool. Devuelve las k mejores.

    Es deliberadamente sencillo y determinista: en producción aquí irían
    embeddings/recuperación semántica, pero la lección sobre tokens es idéntica.
    """
    q_tokens = set(_tokenize(query))

    def score(tool: Dict[str, Any]) -> int:
        text = f"{tool['name']} {tool.get('description') or ''}"
        t_tokens = set(_tokenize(text))
        return sum(1 for q in q_tokens if any(q == t or q in t or t in q for t in t_tokens))

    ranked = sorted(tools, key=score, reverse=True)
    return ranked[:k]


# ---------------------------------------------------------------------------
# Bucle de agente genérico (mide tokens vía usage de la API)
# ---------------------------------------------------------------------------


def _serialize_mcp(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [getattr(c, "text", str(c)) for c in content]
        return "\n".join(parts)
    return str(content)


@observe(name="agent-run")
async def run_agent(
    query: str,
    tools: List[Dict[str, Any]],
    execute_tool: Callable[[str, Dict[str, Any]], "asyncio.Future[str]"],
) -> Dict[str, Any]:
    messages: List[Dict[str, Any]] = [{"role": "user", "content": query}]
    total_in = total_out = 0
    first_call_in = 0
    model_calls = tool_calls = 0

    for _ in range(4):
        resp = client.messages.create(
            model=MODEL, max_tokens=MAX_TOKENS, tools=tools, messages=messages
        )
        model_calls += 1
        total_in += resp.usage.input_tokens
        total_out += resp.usage.output_tokens
        if model_calls == 1:
            first_call_in = resp.usage.input_tokens

        tool_uses = [c for c in resp.content if c.type == "tool_use"]
        if not tool_uses:
            text = "\n".join(c.text for c in resp.content if c.type == "text")
            return {
                "final_text": text,
                "input_tokens": total_in,
                "output_tokens": total_out,
                "total_tokens": total_in + total_out,
                "first_call_input_tokens": first_call_in,
                "model_calls": model_calls,
                "tool_calls": tool_calls,
            }

        messages.append({"role": "assistant", "content": resp.content})
        for tu in tool_uses:
            tool_calls += 1
            result = await execute_tool(tu.name, tu.input)
            messages.append(
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": tu.id,
                            "content": result,
                        }
                    ],
                }
            )

    return {
        "final_text": "(sin respuesta final tras 4 turnos)",
        "input_tokens": total_in,
        "output_tokens": total_out,
        "total_tokens": total_in + total_out,
        "first_call_input_tokens": first_call_in,
        "model_calls": model_calls,
        "tool_calls": tool_calls,
    }


# ---------------------------------------------------------------------------
# Orquestación del benchmark
# ---------------------------------------------------------------------------


async def main() -> None:
    exit_stack = AsyncExitStack()
    try:
        # Abrimos UNA sesión MCP y descubrimos el catálogo completo de tools.
        server_params = StdioServerParameters(
            command=os.getenv("PYTHON_EXECUTABLE", sys.executable),
            args=[SERVER_PATH],
            env=None,
        )
        stdio, write = await exit_stack.enter_async_context(stdio_client(server_params))
        session = await exit_stack.enter_async_context(ClientSession(stdio, write))
        await session.initialize()

        tools_response = await session.list_tools()
        all_mcp_tools = [
            {
                "name": t.name,
                "description": t.description,
                "input_schema": t.inputSchema,
            }
            for t in tools_response.tools
        ]

        async def execute_mcp(name: str, args: Dict[str, Any]) -> str:
            result = await session.call_tool(name, args)
            return _serialize_mcp(result.content)

        print(f"Catálogo MCP descubierto: {len(all_mcp_tools)} tools")
        print(f"Modelo: {MODEL}\n")

        # acumuladores por estrategia
        agg: Dict[str, Dict[str, Any]] = {}

        for q in QUERIES:
            strategies: List[Tuple[str, List[Dict[str, Any]], Any]] = [
                ("vanilla", VANILLA_TOOLS, _execute_vanilla),
                ("mcp_naive", all_mcp_tools, execute_mcp),
                (
                    "mcp_optimized",
                    select_relevant_tools(q["text"], all_mcp_tools, OPTIMIZED_TOP_K),
                    execute_mcp,
                ),
            ]

            for name, tools, executor in strategies:
                with propagate_attributes(
                    session_id="benchmark-token-optimization",
                    tags=["token-opt", name],
                    metadata={
                        "tool_mode": name,
                        "query_id": q["id"],
                        "tools_loaded": str(len(tools)),
                        "model": MODEL,
                    },
                ):
                    r = await run_agent(q["text"], tools, executor)

                selected = ", ".join(t["name"] for t in tools)
                print(
                    f"[{q['id']:>9} | {name:<13}] "
                    f"tools={len(tools):>2}  "
                    f"in={r['input_tokens']:>5}  out={r['output_tokens']:>4}  "
                    f"total={r['total_tokens']:>5}  "
                    f"(1ª llamada in={r['first_call_input_tokens']:>5})  "
                    f"tool_calls={r['tool_calls']}"
                )
                if name == "mcp_optimized":
                    print(f"            └─ tools enviadas: {selected}")

                acc = agg.setdefault(
                    name,
                    {"in": 0, "out": 0, "total": 0, "first": 0, "tools": 0, "n": 0},
                )
                acc["in"] += r["input_tokens"]
                acc["out"] += r["output_tokens"]
                acc["total"] += r["total_tokens"]
                acc["first"] += r["first_call_input_tokens"]
                acc["tools"] += len(tools)
                acc["n"] += 1

            print()

        _print_summary(agg)
    finally:
        await exit_stack.aclose()
        langfuse.flush()
        langfuse.shutdown()


def _print_summary(agg: Dict[str, Dict[str, Any]]) -> None:
    print("=" * 78)
    print("RESUMEN (suma sobre todas las consultas)")
    print("=" * 78)
    header = f"{'estrategia':<15}{'tools(avg)':>12}{'input':>10}{'output':>10}{'total':>10}"
    print(header)
    print("-" * 78)
    order = ["vanilla", "mcp_naive", "mcp_optimized"]
    for name in order:
        a = agg.get(name)
        if not a:
            continue
        print(
            f"{name:<15}{a['tools'] / a['n']:>12.1f}"
            f"{a['in']:>10}{a['out']:>10}{a['total']:>10}"
        )
    print("-" * 78)

    naive = agg.get("mcp_naive")
    opt = agg.get("mcp_optimized")
    van = agg.get("vanilla")
    if naive and opt and naive["in"]:
        saved = naive["in"] - opt["in"]
        pct = 100 * saved / naive["in"]
        print(
            f"Ahorro de input tokens optimizado vs naive: {saved} "
            f"({pct:.1f}% menos)"
        )
    if naive and van and naive["in"]:
        extra = naive["in"] - van["in"]
        pct = 100 * extra / van["in"]
        print(
            f"Sobrecoste de MCP-naive vs vanilla:         +{extra} "
            f"(+{pct:.1f}% sobre vanilla)"
        )
    print("=" * 78)


if __name__ == "__main__":
    asyncio.run(main())
