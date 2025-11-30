# tools_arxiv.py
from __future__ import annotations

import json
import os
import re
from typing import List, Dict, Any

import arxiv

PAPER_DIR = "papers"


def _slugify_topic(topic: str) -> str:
    """Convierte el topic en un nombre de carpeta seguro."""
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "_", topic.strip().lower())
    return slug or "topic"


def search_papers(topic: str, max_results: int = 5) -> Dict[str, Any]:
    """
    Busca artículos en arXiv por tema y guarda un índice local con metadatos.

    Devuelve un dict con:
    - topic: tema buscado
    - dir: ruta del directorio donde se guarda la info
    - papers: lista de papers con id corto, título, autores, resumen y fecha
    """

    os.makedirs(PAPER_DIR, exist_ok=True)

    topic_slug = _slugify_topic(topic)
    topic_dir = os.path.join(PAPER_DIR, topic_slug)
    os.makedirs(topic_dir, exist_ok=True)

    file_path = os.path.join(topic_dir, "papers_info.json")

    # Cargamos índice previo si existe
    papers_info: Dict[str, Any] = {}
    if os.path.isfile(file_path):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                papers_info = json.load(f)
        except (json.JSONDecodeError, OSError):
            papers_info = {}

    # Configuramos búsqueda en arXiv
    client = arxiv.Client()  # estrategia de paginación / rate limit por defecto 

    search = arxiv.Search(
        query=topic,
        max_results=max_results,
        sort_by=arxiv.SortCriterion.Relevance,
    )

    results: List[Dict[str, Any]] = []

    for paper in client.results(search):
        short_id = paper.get_short_id()
        info = {
            "id": short_id,
            "title": paper.title,
            "authors": [author.name for author in paper.authors],
            "summary": paper.summary,
            "pdf_url": paper.pdf_url,
            "published": str(paper.published.date()) if paper.published else None,
            "primary_category": paper.primary_category,
        }
        papers_info[short_id] = info
        results.append(info)

    # Guardamos índice actualizado
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(papers_info, f, indent=2, ensure_ascii=False)

    return {
        "topic": topic,
        "topic_slug": topic_slug,
        "dir": topic_dir,
        "papers": results,
    }


def extract_info(paper_id: str) -> Dict[str, Any]:
    """
    Busca información de un paper por ID corto recorriendo todos los topics.

    paper_id: por ejemplo "2102.10073v1" o similar.
    """

    if not os.path.isdir(PAPER_DIR):
        return {
            "found": False,
            "message": f"No hay ningún índice local en '{PAPER_DIR}'. "
                       f"Primero ejecuta una búsqueda con search_papers.",
        }

    for entry in os.listdir(PAPER_DIR):
        topic_dir = os.path.join(PAPER_DIR, entry)
        if not os.path.isdir(topic_dir):
            continue

        file_path = os.path.join(topic_dir, "papers_info.json")
        if not os.path.isfile(file_path):
            continue

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                papers_info = json.load(f)
        except (json.JSONDecodeError, OSError):
            continue

        if paper_id in papers_info:
            return {
                "found": True,
                "topic_slug": entry,
                "paper": papers_info[paper_id],
            }

    return {
        "found": False,
        "message": f"No se ha encontrado información local para el paper '{paper_id}'. "
                   f"Asegúrate de haber ejecutado antes una búsqueda relacionada.",
    }
