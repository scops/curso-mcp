from __future__ import annotations

import unittest
from unittest.mock import patch

from ej11_rag_vs_mcp_sakila import sakila_simple_mcp_server as server


class SearchFilmsByTitleTests(unittest.IsolatedAsyncioTestCase):
    async def test_formatea_items(self) -> None:
        rows = [
            (1, "ACADEMY DINOSAUR", 2006, "PG", 86),
            (2, "ACE GOLDFINGER", 2006, "G", None),
        ]
        with patch.object(server, "fetch_all", return_value=rows):
            result = await server.search_films_by_title("aca", limit=10)

        self.assertEqual(result["total"], 2)
        self.assertEqual(result["items"][0]["film_id"], 1)
        self.assertEqual(result["items"][0]["title"], "ACADEMY DINOSAUR")
        # Campos opcionales nulos se preservan como None.
        self.assertIsNone(result["items"][1]["length"])

    async def test_limit_fuera_de_rango_se_normaliza_a_10(self) -> None:
        captured: dict = {}

        def fake_fetch(query, params=None):
            captured["params"] = params
            return []

        with patch.object(server, "fetch_all", fake_fetch):
            await server.search_films_by_title("x", limit=999)

        # El último parámetro es el LIMIT y debe quedar saneado a 10.
        self.assertEqual(captured["params"][-1], 10)


class GetFilmsByCategoryTests(unittest.IsolatedAsyncioTestCase):
    async def test_formatea_items(self) -> None:
        rows = [(5, "AFRICAN EGG", 2006, "G", "Documentary")]
        with patch.object(server, "fetch_all", return_value=rows):
            result = await server.get_films_by_category("Documentary", limit=5)

        self.assertEqual(result["total"], 1)
        self.assertEqual(result["items"][0]["category"], "Documentary")
        self.assertEqual(result["items"][0]["film_id"], 5)


class GetFilmDetailsTests(unittest.IsolatedAsyncioTestCase):
    async def test_pelicula_existente(self) -> None:
        rows = [(1, "ACADEMY DINOSAUR", "Una épica", 2006, "PG", 86, "English", 23)]
        with patch.object(server, "fetch_all", return_value=rows):
            result = await server.get_film_details(1)

        self.assertTrue(result["found"])
        self.assertEqual(result["title"], "ACADEMY DINOSAUR")
        self.assertEqual(result["language"], "English")
        self.assertEqual(result["total_rentals"], 23)

    async def test_pelicula_inexistente(self) -> None:
        with patch.object(server, "fetch_all", return_value=[]):
            result = await server.get_film_details(999999)

        self.assertFalse(result["found"])


if __name__ == "__main__":
    unittest.main()
