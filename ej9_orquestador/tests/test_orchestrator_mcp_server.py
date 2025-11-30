from __future__ import annotations

import unittest
from unittest.mock import patch

from ej9_orquestador import orchestrator_mcp_server as server


class OrchestratorToolsTests(unittest.IsolatedAsyncioTestCase):
    async def test_research_incident_with_papers_combines_payloads(self) -> None:
        async def fake_call(server_path, tool_name, arguments):
            if server_path == server.RAG_SERVER_PATH and tool_name == "rag_answer":
                return {
                    "answer": "Respuesta basada en tickets.",
                    "sources": [{"id": 1, "title": "Error 500"}],
                }
            if server_path == server.ARXIV_SERVER_PATH and tool_name == "search_papers_mcp":
                return {
                    "topic": arguments["topic"],
                    "papers": [{"id": "1234.5678v1", "title": "Paper de ejemplo"}],
                }
            return {}

        with patch.object(server, "_call_remote_tool_stdio", fake_call):
            result = await server.research_incident_with_papers(
                incident_question="Tenemos errores 500 en la API de usuarios",
                topic="database locks",
                max_papers=2,
                k=3,
            )

        self.assertEqual(result["incident_question"], "Tenemos errores 500 en la API de usuarios")
        self.assertEqual(result["incident_answer"], "Respuesta basada en tickets.")
        self.assertEqual(len(result["incident_sources"]), 1)
        self.assertEqual(result["arxiv_topic"], "database locks")
        self.assertEqual(result["arxiv_results"]["topic"], "database locks")
        self.assertEqual(result["arxiv_results"]["papers"][0]["id"], "1234.5678v1")

    async def test_list_orchestrated_servers_describes_expected_children(self) -> None:
        servers = await server.list_orchestrated_servers()
        names = {s["name"] for s in servers}
        self.assertIn("incidents-rag", names)
        self.assertIn("arxiv-tools", names)


if __name__ == "__main__":
    unittest.main()

