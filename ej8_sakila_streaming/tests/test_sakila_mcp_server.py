from __future__ import annotations

import unittest
from unittest.mock import patch

from ej8_sakila_streaming import sakila_mcp_server as server


class SakilaToolsTests(unittest.IsolatedAsyncioTestCase):
    async def test_get_latest_films_limits_results(self) -> None:
        rows = [
            (1, "ACADEMY DINOSAUR", 2006, "PG", 86),
            (2, "ACE GOLDFINGER", 2006, "G", 48),
        ]

        with patch.object(server, "fetch_all", return_value=rows):
            result = await server.get_latest_films(limit=5)

        self.assertEqual(result["total"], 2)
        self.assertEqual(result["items"][0]["title"], "ACADEMY DINOSAUR")
        self.assertEqual(result["items"][1]["rating"], "G")

    async def test_get_rating_distribution_formats_counts(self) -> None:
        rows = [
            ("G", 10),
            ("PG", 5),
        ]

        with patch.object(server, "fetch_all", return_value=rows):
            result = await server.get_rating_distribution()

        self.assertEqual(result["ratings"], ["G", "PG"])
        self.assertEqual(result["counts"], [10, 5])

    async def test_create_film_from_omdb_handles_search_error(self) -> None:
        async def fake_request(params: dict[str, str]) -> dict[str, str]:
            return {"error": "API key invalid"}

        with patch.object(server, "_omdb_request", fake_request):
            result = await server.create_film_from_omdb("Inception")

        self.assertIn("error", result)

    async def test_create_film_from_omdb_inserts_film(self) -> None:
        search_payload = {
            "Search": [
                {
                    "Title": "Inception",
                    "imdbID": "tt1375666",
                }
            ]
        }
        detail_payload = {
            "Title": "Inception",
            "Plot": "Dreams inside dreams.",
            "Year": "2010",
            "imdbID": "tt1375666",
        }

        async def fake_request(params: dict[str, str]) -> dict[str, object]:
            if "s" in params:
                return search_payload
            return detail_payload

        with patch.object(server, "_omdb_request", fake_request), patch.object(
            server, "execute_and_return_id", return_value=1234
        ) as exec_mock:
            result = await server.create_film_from_omdb("Inception")

        exec_mock.assert_called_once()
        self.assertEqual(result["film_id"], 1234)
        self.assertEqual(result["imdb_id"], "tt1375666")
