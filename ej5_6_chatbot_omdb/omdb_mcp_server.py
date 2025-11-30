from __future__ import annotations

import os
import re
from typing import Any, Literal

import httpx
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

load_dotenv()

OMDB_API_KEY = os.getenv("OMDB_API_KEY")

if not OMDB_API_KEY:
    raise RuntimeError("Nos falta OMDB_API_KEY en el entorno / .env")

OMDB_BASE_URL = "https://www.omdbapi.com/"

# Servidor MCP para OMDb.
# En este ejercicio lo exponemos por HTTP para que puedas
# probarlo fácilmente en localhost:8000 (como lo tenías antes).
mcp = FastMCP(
    name="omdb-tools",
    host="0.0.0.0",
    port=8000,
)


async def _omdb_request(params: dict[str, Any]) -> dict[str, Any]:
    """
    Llama a la API de OMDb y devuelve el JSON ya parseado.

    Añade automáticamente el apiKey y fuerza formato JSON.
    Normaliza el caso de error para devolver siempre {"error": "..."}.
    """
    merged = dict(params)
    merged["apikey"] = OMDB_API_KEY  # nombre de parámetro correcto en OMDb
    merged.setdefault("r", "json")

    async with httpx.AsyncClient(
        timeout=15.0, follow_redirects=True
    ) as client:
        resp = await client.get(OMDB_BASE_URL, params=merged)
        resp.raise_for_status()
        data = resp.json()

    # OMDb indica fallo con Response == "False" y campo "Error"
    if isinstance(data, dict) and data.get("Response") == "False":
        return {"error": data.get("Error", "Error desconocido en OMDb")}

    return data


# format pelicula basic
def _format_basic_pelicula(pelicula: dict[str, Any]) -> dict[str, Any]:
    return {
        "title": pelicula.get("Title"),
        "year": pelicula.get("Year"),
        "imdb_id": pelicula.get("imdbID"),
        "type": pelicula.get("Type"),
        "poster": pelicula.get("Poster")
    }
        
#format pelicula advanced
def _format_detail_pelicula(pelicula: dict[str, Any]) -> dict[str, Any]:
    return {
        "title": pelicula.get("Title"),
        "year": pelicula.get("Year"),
        "rated": pelicula.get("Rated"),
        "released": pelicula.get("Released"),
        "runtime": pelicula.get("Runtime"),
        "genre": pelicula.get("Genre"),
        "director": pelicula.get("Director"),
        "writer": pelicula.get("Writer"),
        "actors": pelicula.get("Actors"),
        "plot": pelicula.get("Plot"),
        "language": pelicula.get("Language"),
        "country": pelicula.get("Country"),
        "awards": pelicula.get("Awards"),
        "poster": pelicula.get("Poster"),
        "ratings": pelicula.get("Ratings"),
        "metascore": pelicula.get("Metascore"),
        "imdb_rating": pelicula.get("imdbRating"),
        "imdb_votes": pelicula.get("imdbVotes"),
        "imdb_id": pelicula.get("imdbID"),
        "type": pelicula.get("Type"),
        "dvd": pelicula.get("DVD"),
        "box_office": pelicula.get("BoxOffice"),
        "production": pelicula.get("Production"),
        "website": pelicula.get("Website")
    }

# mcp tool search_movies
@mcp.tool()
async def search_movies( 
    query: str, 
    media_type: Literal["movie", "series", "episode", "all"] = "all",
    year: int | None = None,
    max_results: int = 5,
    ) -> dict[ str, Any]:
    # pasamos query y buscamos, devolvemos resultado.
    # saneamos la query para dejar sólo un posible nombre de película
    query = (query or "").strip()
    # permitimos letras (incluyendo acentos), números, espacios y puntuación común en títulos
    query = re.sub(r"[^A-Za-z0-9À-ÿ\u00f1\u00d1\s:.,'’\-\(\)&+]", "", query)
    # colapsar espacios
    query = re.sub(r"\s+", " ", query).strip()
    # eliminar palabras comunes que no forman parte del título (lista básica)
    query = re.sub(r"\b(pelicula|películas|serie|series|ver|buscar|quiero|quieres|donde|cuando|como|de|el|la|los|las)\b", "", query, flags=re.I)
    query = re.sub(r"\s+", " ", query).strip()

    if not query:
        raise ValueError("Consulta vacía tras saneamiento; proporciona el nombre de una película")
    
    if max_results < 1 or max_results > 10:
        return { "error": "sólo se pueden pedir entre 1 y diez resultados"}
    
    params: dict[str, Any] = {"s": query}
    
    if media_type != "all":
        params["type"] = media_type
    if year is not None:
        params["y"] = year
        
    data = await _omdb_request(params)
    if "error" in data:
        return {
            "query": query,
            "total": 0,
            "items": [],
            "note": data["error"],
        }
        
    search_items = data.get("Search", [])
    total_resp = int(data.get("totalResults", len(search_items))) if search_items else 0
    
    limited = search_items[:max_results]
    items = [_format_basic_pelicula(item) for item in limited]
    
    note = None
    if total_resp > len(items):
        note = (
            f"Se han encontrado { total_resp} resultados en OMDB"
            f"pero se devuelven sólo {len(items)} (max_results={max_results})"
        )
    return {
        "query":query,
        "total": len(items),
        "items": items,
        "note": note
    }
    
# mcp tool get movie details
@mcp.tool()
async def get_movie_detail(
    imdb_id: str,
    plot: Literal["short", "full"] = "short"
) -> dict[str, Any]:
    # pedimos por id y devolvemos result
    imdb_id_clean = (imdb_id or "").strip()
    # Validar que sea un ID de IMDB válido (formato: tt seguido de 7-10 dígitos)
    if not re.match(r'^tt\d{7,10}$', imdb_id_clean):
        raise ValueError("ID de IMDB inválido. Debe tener el formato 'ttXXXXXXX' (tt seguido de 7-10 dígitos)")
    
    params: dict[ str, Any] = {
        "i": imdb_id_clean,
        "plot": plot
    }
    data = await _omdb_request(params)
    if "error" in data:
        return {"imdb_id": imdb_id_clean, "error": data["error"]}
    
    return _format_detail_pelicula(data)

def main() -> None:
    # Aquí usamos transporte HTTP, que es lo que permite acceder
    # al servidor en http://localhost:8000 (por ejemplo, para
    # probar desde el navegador o herramientas HTTP).
    mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
