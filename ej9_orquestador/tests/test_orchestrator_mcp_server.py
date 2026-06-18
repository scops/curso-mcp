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

    async def test_research_incident_propaga_errores_de_servidor_remoto(self) -> None:
        async def boom(server_path, tool_name, arguments):
            raise RuntimeError("servidor remoto caído")

        with patch.object(server, "_call_remote_tool_stdio", boom):
            result = await server.research_incident_with_papers(
                incident_question="errores 500",
                topic="db",
            )

        # _safe_call captura la excepción y devuelve un payload de error,
        # de modo que el orquestador sigue respondiendo.
        self.assertIsNone(result["incident_answer"])
        self.assertEqual(result["incident_sources"], [])
        self.assertEqual(result["arxiv_results"]["error"], "arxiv_error")


class ChooseArxivTopicTests(unittest.TestCase):
    def test_topic_explicito_se_respeta(self) -> None:
        self.assertEqual(
            server._choose_arxiv_topic("lo que sea", "database locks"),
            "database locks",
        )

    def test_timeout_mapea_a_topic_de_rendimiento(self) -> None:
        topic = server._choose_arxiv_topic("La API da timeout", None)
        self.assertIn("timeout", topic)
        self.assertIn("performance", topic)

    def test_error_500_mapea_a_topic_http(self) -> None:
        topic = server._choose_arxiv_topic("Tenemos un error 500", None)
        self.assertIn("500", topic)

    def test_sin_pista_usa_la_propia_pregunta(self) -> None:
        self.assertEqual(
            server._choose_arxiv_topic("algo raro pasa", None),
            "algo raro pasa",
        )


if __name__ == "__main__":
    unittest.main()

