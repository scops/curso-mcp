"""
Servidor MCP con MUCHAS tools — base para la demo de optimización de tokens.

La gracia de este servidor es que expone un catálogo grande de herramientas
(14 tools) con descripciones y esquemas realistas, como tendría un servidor
MCP "de verdad" (o el conjunto de varios servidores conectados a la vez).

Solo dos tools (`search_papers` y `extract_info`) hacen algo útil para la
demo; el resto son *stubs* deterministas cuyo único papel es **ocupar sitio en
el catálogo**. Eso es justo lo que queremos medir: cuántos tokens cuesta enviar
al modelo definiciones de tools que no se van a usar.

Datos sintéticos a propósito: nada de red. Así el benchmark es reproducible,
gratis y rápido (los tokens de las definiciones de tools no dependen de si
arXiv responde o no).

Transporte STDIO, como cualquier servidor MCP del curso.
"""
from __future__ import annotations

from typing import Any, Dict, List

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("arxiv-suite")


# ---------------------------------------------------------------------------
# Datos sintéticos deterministas
# ---------------------------------------------------------------------------

_FAKE_PAPERS: List[Dict[str, Any]] = [
    {
        "arxiv_id": f"24{idx:02d}.{1000 + idx}",
        "title": f"Paper sintético #{idx} sobre el tema solicitado",
        "authors": ["A. Autor", "B. Coautora"],
        "year": 2024,
        "summary": (
            "Resumen de ejemplo, fijo y determinista, usado para que la demo "
            "no dependa de la red ni introduzca ruido en la medición de tokens."
        ),
    }
    for idx in range(1, 8)
]


# ---------------------------------------------------------------------------
# Tools ÚTILES para la demo (devuelven datos sintéticos)
# ---------------------------------------------------------------------------


@mcp.tool()
def search_papers(topic: str, max_results: int = 5) -> Dict[str, Any]:
    """
    Busca artículos científicos en arXiv sobre un tema y devuelve una lista
    con sus metadatos básicos (arxiv_id, título, autores, año y resumen).
    Úsala como primer paso cuando el usuario pide encontrar papers sobre un
    tema, autor o área de investigación.
    """
    papers = _FAKE_PAPERS[: max(1, min(max_results, len(_FAKE_PAPERS)))]
    return {"topic": topic, "count": len(papers), "papers": papers}


@mcp.tool()
def extract_info(paper_id: str) -> Dict[str, Any]:
    """
    Devuelve la información detallada de un artículo concreto de arXiv a partir
    de su identificador (arxiv_id), incluyendo título, autores, año y un
    resumen ampliado. Úsala cuando el usuario quiera profundizar en un paper
    concreto que ya conoce por su id.
    """
    return {
        "arxiv_id": paper_id,
        "title": f"Detalle sintético del paper {paper_id}",
        "authors": ["A. Autor", "B. Coautora"],
        "year": 2024,
        "summary": (
            "Información detallada de ejemplo para el paper solicitado. "
            "Determinista, sin acceso a red."
        ),
    }


# ---------------------------------------------------------------------------
# Tools "de relleno": stubs realistas que SOLO existen para engordar el
# catálogo. Representan un servidor MCP grande y capaz. No se llaman en la demo.
# ---------------------------------------------------------------------------


def _stub(name: str) -> Dict[str, Any]:
    return {"status": "demo_stub", "tool": name}


@mcp.tool()
def summarize_paper(paper_id: str, max_words: int = 150) -> Dict[str, Any]:
    """Genera un resumen en lenguaje llano de un paper de arXiv dado su id,
    con una longitud máxima configurable en palabras."""
    return _stub("summarize_paper")


@mcp.tool()
def translate_text(text: str, target_lang: str = "en") -> Dict[str, Any]:
    """Traduce un texto (por ejemplo, el resumen de un paper) al idioma destino
    indicado mediante su código ISO (en, es, fr, de, ...)."""
    return _stub("translate_text")


@mcp.tool()
def format_citation(paper_id: str, style: str = "APA") -> Dict[str, Any]:
    """Devuelve la cita bibliográfica de un paper en el estilo solicitado
    (APA, MLA, Chicago, IEEE), lista para pegar en un documento."""
    return _stub("format_citation")


@mcp.tool()
def export_bibtex(paper_ids: List[str]) -> Dict[str, Any]:
    """Exporta una o varias referencias de arXiv a formato BibTeX para
    gestores bibliográficos como Zotero, Mendeley o LaTeX."""
    return _stub("export_bibtex")


@mcp.tool()
def find_related_papers(paper_id: str, max_results: int = 5) -> Dict[str, Any]:
    """Encuentra papers relacionados con uno dado, usando similitud de tema y
    de citas, y devuelve la lista de candidatos más cercanos."""
    return _stub("find_related_papers")


@mcp.tool()
def get_author_profile(author_name: str) -> Dict[str, Any]:
    """Recupera el perfil de un autor (afiliación, número de publicaciones,
    áreas principales y papers más citados) a partir de su nombre."""
    return _stub("get_author_profile")


@mcp.tool()
def list_categories() -> Dict[str, Any]:
    """Lista las categorías y subcategorías temáticas de arXiv (cs.AI, cs.CL,
    stat.ML, ...) con una breve descripción de cada una."""
    return _stub("list_categories")


@mcp.tool()
def get_trending_topics(category: str, period: str = "month") -> Dict[str, Any]:
    """Devuelve los temas en tendencia dentro de una categoría de arXiv para el
    periodo indicado (week, month, year), ordenados por volumen de publicación."""
    return _stub("get_trending_topics")


@mcp.tool()
def download_pdf(paper_id: str) -> Dict[str, Any]:
    """Descarga el PDF de un paper de arXiv dado su id y devuelve la ruta local
    del archivo guardado."""
    return _stub("download_pdf")


@mcp.tool()
def compare_papers(paper_id_a: str, paper_id_b: str) -> Dict[str, Any]:
    """Compara dos papers de arXiv y resume sus similitudes, diferencias
    metodológicas y contribuciones relativas."""
    return _stub("compare_papers")


@mcp.tool()
def extract_figures(paper_id: str) -> Dict[str, Any]:
    """Extrae las figuras y tablas de un paper de arXiv y devuelve sus
    leyendas junto con las URLs de las imágenes."""
    return _stub("extract_figures")


@mcp.tool()
def get_citation_count(paper_id: str) -> Dict[str, Any]:
    """Devuelve el número de citas que ha recibido un paper y su evolución
    aproximada por año."""
    return _stub("get_citation_count")


if __name__ == "__main__":
    mcp.run(transport="stdio")
