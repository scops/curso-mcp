from __future__ import annotations

import os
from typing import Any, Dict, List

import httpx
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

from .sakila_db import fetch_all, execute_and_return_id


load_dotenv()

OMDB_API_KEY = os.getenv("OMDB_API_KEY")
if not OMDB_API_KEY:
    raise RuntimeError("Falta OMDB_API_KEY en el entorno / .env")

OMDB_BASE_URL = "https://www.omdbapi.com/"

mcp = FastMCP("sakila-streaming")


async def _omdb_request(params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Llama a la API de OMDb y devuelve el JSON ya parseado.
    Normaliza el caso de error para devolver siempre {"error": "..."}.
    """
    merged = dict(params)
    merged["apikey"] = OMDB_API_KEY
    merged.setdefault("r", "json")

    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
        resp = await client.get(OMDB_BASE_URL, params=merged)
        resp.raise_for_status()
        data = resp.json()

    if isinstance(data, dict) and data.get("Response") == "False":
        return {"error": data.get("Error", "Error desconocido en OMDb")}

    return data


@mcp.tool()
async def get_latest_films(limit: int = 10) -> Dict[str, Any]:
    """
    Devuelve las últimas películas registradas en sakila.

    No usa datos de OMDb, solo la base de datos local.
    """
    if limit < 1 or limit > 50:
        limit = 10

    rows = fetch_all(
        """
        SELECT film_id, title, release_year, rating, length
        FROM film
        ORDER BY film_id DESC
        LIMIT %s
        """,
        params=[limit],
    )

    items: List[Dict[str, Any]] = []
    for film_id, title, release_year, rating, length in rows:
        items.append(
            {
                "film_id": film_id,
                "title": title,
                "release_year": int(release_year) if release_year is not None else None,
                "rating": rating,
                "length": int(length) if length is not None else None,
            }
        )

    return {
        "total": len(items),
        "items": items,
    }


@mcp.tool()
async def get_rating_distribution() -> Dict[str, Any]:
    """
    Devuelve el número de películas por rating (G, PG, PG-13, etc.).

    Esta salida es ideal para construir una visualización (p. ej. gráfico de barras)
    en el cliente Streamlit.
    """
    rows = fetch_all(
        """
        SELECT rating, COUNT(*) AS total
        FROM film
        GROUP BY rating
        ORDER BY rating
        """,
        params=None,
    )

    ratings: List[str] = []
    counts: List[int] = []

    for rating, total in rows:
        ratings.append(str(rating))
        counts.append(int(total))

    return {
        "ratings": ratings,
        "counts": counts,
    }


@mcp.tool()
async def create_film_from_omdb(title: str, year: int | None = None) -> Dict[str, Any]:
    """
    Busca una película en OMDb por título (y opcionalmente año),
    obtiene sus detalles y crea un registro en la tabla film de sakila.

    Esto demuestra que MCP no solo sirve para leer datos, sino también
    para escribir/editar registros en una base de datos.
    """
    search_params: Dict[str, Any] = {"s": title}
    if year is not None:
        search_params["y"] = year

    search_data = await _omdb_request(search_params)
    if "error" in search_data:
        return {"error": search_data["error"]}

    search_items = search_data.get("Search") or []
    if not search_items:
        return {"error": "No se han encontrado resultados en OMDb para ese título/año."}

    first = search_items[0]
    imdb_id = first.get("imdbID")
    if not imdb_id:
        return {"error": "El primer resultado de OMDb no tiene imdbID válido."}

    detail_data = await _omdb_request({"i": imdb_id, "plot": "short"})
    if "error" in detail_data:
        return {"error": detail_data["error"]}

    film_title = detail_data.get("Title") or title
    description = detail_data.get("Plot") or ""
    year_str = detail_data.get("Year") or ""

    try:
        release_year = int(year_str[:4]) if year_str else None
    except ValueError:
        release_year = None

    # Insertamos en la tabla film usando defaults para la mayoría de campos.
    # Suponemos que language_id=1 existe (inglés) en la base de datos sakila estándar.
    insert_sql = """
        INSERT INTO film (title, description, release_year, language_id)
        VALUES (%s, %s, %s, %s)
    """
    film_id = execute_and_return_id(
        insert_sql,
        params=[
            film_title,
            description,
            release_year,
            1,
        ],
    )

    return {
        "film_id": film_id,
        "title": film_title,
        "release_year": release_year,
        "imdb_id": imdb_id,
        "omdb_snapshot": detail_data,
        "note": (
            "Película creada en la tabla 'film' de sakila. "
            "Puedes usar otros tools para consultarla o incluirla en visualizaciones."
        ),
    }


def main() -> None:
    """
    Lanza el servidor MCP por STDIO.

    Este servidor combina dos fuentes:
    - Base de datos MySQL sakila (lectura y escritura).
    - API HTTP de OMDb para enriquecer y crear películas nuevas.
    """
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()

