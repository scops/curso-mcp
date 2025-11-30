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
