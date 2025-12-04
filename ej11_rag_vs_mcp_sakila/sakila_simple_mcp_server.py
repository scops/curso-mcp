from __future__ import annotations

"""
Servidor MCP sencillo sobre la base de datos sakila.

La idea para el ejercicio 11 es usar este servidor como ejemplo de
"consulta dirigida y optimizada" frente a un enfoque RAG más flexible.

Aquí exponemos tools muy concretas (SQL directo) que devuelven justo
lo necesario para responder preguntas típicas sobre el catálogo.
"""

from typing import Any, Dict, List

from mcp.server.fastmcp import FastMCP

from ej8_sakila_streaming.sakila_db import fetch_all


mcp = FastMCP("sakila-simple")


@mcp.tool()
async def search_films_by_title(title_substring: str, limit: int = 10) -> Dict[str, Any]:
    """
    Busca películas cuyo título contenga el texto dado (case insensitive).

    Devuelve una lista acotada de películas con algunos campos básicos.
    Esta tool ilustra una consulta muy dirigida: el host debe saber qué
    quiere buscar y pasar un patrón concreto.
    """
    if limit < 1 or limit > 50:
        limit = 10

    rows = fetch_all(
        """
        SELECT film_id, title, release_year, rating, length
        FROM film
        WHERE title LIKE %s
        ORDER BY film_id DESC
        LIMIT %s
        """,
        params=[f"%{title_substring}%", limit],
    )

    items: List[Dict[str, Any]] = []
    for film_id, title, release_year, rating, length in rows:
        items.append(
            {
                "film_id": int(film_id),
                "title": str(title),
                "release_year": int(release_year) if release_year is not None else None,
                "rating": str(rating) if rating is not None else None,
                "length": int(length) if length is not None else None,
            }
        )

    return {"total": len(items), "items": items}


@mcp.tool()
async def get_films_by_category(category_name: str, limit: int = 10) -> Dict[str, Any]:
    """
    Devuelve películas de una categoría concreta (por nombre).

    Ejemplo de prompt al modelo:
    - "Quiero algunas películas de acción recientes."
    """
    if limit < 1 or limit > 50:
        limit = 10

    rows = fetch_all(
        """
        SELECT f.film_id, f.title, f.release_year, f.rating, c.name AS category
        FROM film AS f
        JOIN film_category AS fc ON fc.film_id = f.film_id
        JOIN category AS c ON c.category_id = fc.category_id
        WHERE c.name = %s
        ORDER BY f.release_year DESC, f.film_id DESC
        LIMIT %s
        """,
        params=[category_name, limit],
    )

    items: List[Dict[str, Any]] = []
    for film_id, title, release_year, rating, category in rows:
        items.append(
            {
                "film_id": int(film_id),
                "title": str(title),
                "release_year": int(release_year) if release_year is not None else None,
                "rating": str(rating) if rating is not None else None,
                "category": str(category),
            }
        )

    return {"total": len(items), "items": items}


@mcp.tool()
async def get_film_details(film_id: int) -> Dict[str, Any]:
    """
    Devuelve información detallada de una película concreta.
    """
    rows = fetch_all(
        """
        SELECT f.film_id,
               f.title,
               f.description,
               f.release_year,
               f.rating,
               f.length,
               l.name AS language,
               COUNT(r.rental_id) AS total_rentals
        FROM film AS f
        JOIN language AS l ON l.language_id = f.language_id
        LEFT JOIN inventory AS i ON i.film_id = f.film_id
        LEFT JOIN rental AS r ON r.inventory_id = i.inventory_id
        WHERE f.film_id = %s
        GROUP BY
            f.film_id,
            f.title,
            f.description,
            f.release_year,
            f.rating,
            f.length,
            l.name
        """,
        params=[film_id],
    )

    if not rows:
        return {"found": False}

    (
        film_id,
        title,
        description,
        release_year,
        rating,
        length,
        language,
        total_rentals,
    ) = rows[0]

    return {
        "found": True,
        "film_id": int(film_id),
        "title": str(title),
        "description": str(description) if description is not None else "",
        "release_year": int(release_year) if release_year is not None else None,
        "rating": str(rating) if rating is not None else None,
        "length": int(length) if length is not None else None,
        "language": str(language),
        "total_rentals": int(total_rentals),
    }


def main() -> None:
    """
    Lanza el servidor MCP por STDIO.
    """
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()

