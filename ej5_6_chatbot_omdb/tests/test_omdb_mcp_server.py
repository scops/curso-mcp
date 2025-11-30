import asyncio
import unittest
from unittest.mock import patch

from ej5_6_chatbot_omdb import omdb_mcp_server as server


class SearchMoviesTests(unittest.IsolatedAsyncioTestCase):
    async def test_search_movies_rejects_empty_query_after_sanitizing(self) -> None:
        with self.assertRaises(ValueError):
            await server.search_movies("")

    async def test_search_movies_formats_items_and_note(self) -> None:
        fake_response = {
            "Search": [
                {
                    "Title": "Inception",
                    "Year": "2010",
                    "imdbID": "tt1375666",
                    "Type": "movie",
                    "Poster": "https://example.com/inception.jpg",
                },
                {
                    "Title": "Inception 2",
                    "Year": "2015",
                    "imdbID": "tt9999999",
                    "Type": "movie",
                    "Poster": "https://example.com/inception2.jpg",
                },
                {
                    "Title": "Inception 3",
                    "Year": "2018",
                    "imdbID": "tt8888888",
                    "Type": "movie",
                    "Poster": "https://example.com/inception3.jpg",
                },
            ],
            "totalResults": "5",
        }

        async def fake_request(params: dict[str, str]) -> dict[str, object]:
            return fake_response

        with patch.object(server, "_omdb_request", fake_request):
            result = await server.search_movies("  Ver la película Inception   ", max_results=2)

        self.assertIn("Inception", result["query"])
        self.assertEqual(result["total"], 2)
        self.assertEqual(len(result["items"]), 2)
        self.assertIsNotNone(result["note"])
        self.assertEqual(result["items"][0]["title"], "Inception")
        self.assertEqual(result["items"][0]["imdb_id"], "tt1375666")


class GetMovieDetailTests(unittest.IsolatedAsyncioTestCase):
    async def test_get_movie_detail_validates_imdb_id(self) -> None:
        with self.assertRaises(ValueError):
            await server.get_movie_detail("invalid-id")

    async def test_get_movie_detail_returns_formatted_payload(self) -> None:
        fake_detail = {
            "Title": "Inception",
            "Year": "2010",
            "Rated": "PG-13",
            "Released": "2010",
            "Runtime": "148 min",
            "Genre": "Action",
            "Director": "Christopher Nolan",
            "Writer": "Christopher Nolan",
            "Actors": "Leonardo DiCaprio",
            "Plot": "Dreams within dreams.",
            "Language": "English",
            "Country": "USA",
            "Awards": "Oscar",
            "Poster": "https://example.com/inception.jpg",
            "Ratings": [],
            "Metascore": "74",
            "imdbRating": "8.8",
            "imdbVotes": "2,000,000",
            "imdbID": "tt1375666",
            "Type": "movie",
            "DVD": "2010",
            "BoxOffice": "$100M",
            "Production": "WB",
            "Website": "https://example.com",
        }

        async def fake_request(params: dict[str, str]) -> dict[str, object]:
            self.assertEqual(params["i"], "tt1375666")
            self.assertEqual(params["plot"], "full")
            return fake_detail

        with patch.object(server, "_omdb_request", fake_request):
            result = await server.get_movie_detail("tt1375666", plot="full")

        self.assertEqual(result["title"], "Inception")
        self.assertEqual(result["imdb_id"], "tt1375666")
        self.assertEqual(result["box_office"], "$100M")
