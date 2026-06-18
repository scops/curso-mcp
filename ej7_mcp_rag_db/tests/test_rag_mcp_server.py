from __future__ import annotations

from pathlib import Path
import unittest
from unittest.mock import patch

from ej7_mcp_rag_db import rag_mcp_server as server
from ej7_mcp_rag_db import rag_local


class TicketResourcesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.ticket1 = rag_local.Ticket(
            id=1,
            title="Error 500",
            body="Fallan los logins.",
            tags="login,error",
            created_at="2025-01-10T09:15:00Z",
        )
        self.ticket2 = rag_local.Ticket(
            id=2,
            title="Timeout panel",
            body="Panel se queda cargando.",
            tags="admin,timeout",
            created_at="2025-01-09T16:30:00Z",
        )

    def test_resource_latest_tickets_returns_limited_subset(self) -> None:
        with patch.object(server.rag_local, "build_index", return_value=2), patch.object(
            server.rag_local, "_load_tickets", return_value=[self.ticket1, self.ticket2]
        ):
            data = server.resource_latest_tickets(limit=1)

        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["id"], self.ticket2.id)
        self.assertIn("title", data[0])

    def test_resource_ticket_by_id(self) -> None:
        with patch.object(server.rag_local, "_load_tickets", return_value=[self.ticket1, self.ticket2]):
            data = server.resource_ticket_by_id(ticket_id=1)

        self.assertIsNotNone(data)
        assert data is not None
        self.assertEqual(data["title"], "Error 500")


class FeedbackToolsTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.temp_feedback = Path("ej7_mcp_rag_db/tests/tmp_feedback.json")
        if self.temp_feedback.exists():
            self.temp_feedback.unlink()
        server.FEEDBACK_PATH = self.temp_feedback

    def tearDown(self) -> None:
        if self.temp_feedback.exists():
            self.temp_feedback.unlink()

    async def test_save_and_list_feedback(self) -> None:
        result = await server.save_feedback("¿Qué pasó?", "Todo bien", True)
        self.assertTrue(result["saved"])
        self.assertEqual(result["total_feedback"], 1)

        entries = await server.list_feedback(limit=5)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["question"], "¿Qué pasó?")

        latest = server.resource_latest_feedback(limit=1)
        self.assertEqual(len(latest), 1)
        self.assertEqual(latest[0]["answer"], "Todo bien")


class RagAnswerTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.t1 = rag_local.Ticket(
            id=1,
            title="Error 500",
            body="Fallan los logins.",
            tags="login,error",
            created_at="2025-01-10T09:15:00Z",
        )
        self.t2 = rag_local.Ticket(
            id=2,
            title="Timeout panel",
            body="Panel se queda cargando.",
            tags="admin,timeout",
            created_at="2025-01-09T16:30:00Z",
        )
        # OJO: el server hace `import rag_local` (módulo top-level), que NO es el
        # mismo objeto que `ej7_mcp_rag_db.rag_local`. Hay que tocar el estado a
        # través de `server.rag_local` para que el código bajo prueba lo vea.
        # Forzamos índice vacío para ejercitar la rama de auto-indexado.
        server.rag_local._TICKETS = []
        server.rag_local._EMBEDDINGS = []

    async def test_embed_texts_vacio_devuelve_lista_vacia(self) -> None:
        self.assertEqual(await server._embed_texts([]), [])

    async def test_rag_answer_pregunta_vacia_lanza_error(self) -> None:
        with self.assertRaises(ValueError):
            await server.rag_answer("   ")

    async def test_rag_answer_autoindexa_y_combina_fuentes(self) -> None:
        async def fake_embed(texts):
            # Vector constante: basta para que _cosine_similarity no falle.
            return [[1.0, 0.0] for _ in texts]

        async def fake_anthropic(system, user_text):
            return "Respuesta basada en tickets."

        with patch.object(server, "_embed_texts", side_effect=fake_embed), patch.object(
            server, "_call_anthropic", side_effect=fake_anthropic
        ), patch.object(
            server.rag_local, "_load_tickets", return_value=[self.t1, self.t2]
        ), patch.object(
            server.rag_local, "_prepare_text", side_effect=lambda t: t.title
        ):
            result = await server.rag_answer("¿Por qué fallan los logins?", k=2)

        self.assertEqual(result["answer"], "Respuesta basada en tickets.")
        self.assertEqual(len(result["sources"]), 2)
        self.assertIn("score", result["sources"][0])
        self.assertIn("title", result["sources"][0])

    async def test_index_tickets_pobla_estado_global(self) -> None:
        async def fake_embed(texts):
            return [[0.1, 0.2] for _ in texts]

        with patch.object(server, "_embed_texts", side_effect=fake_embed), patch.object(
            server.rag_local, "_load_tickets", return_value=[self.t1, self.t2]
        ), patch.object(
            server.rag_local, "_prepare_text", side_effect=lambda t: t.title
        ):
            result = await server.index_tickets()

        self.assertEqual(result["indexed_tickets"], 2)
        self.assertEqual(len(server.rag_local._EMBEDDINGS), 2)
