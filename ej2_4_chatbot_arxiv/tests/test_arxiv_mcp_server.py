import asyncio
import unittest
from unittest.mock import patch

from ej2_4_chatbot_arxiv import arxiv_mcp_server


class TestArxivMCPServer(unittest.TestCase):
    def test_search_papers_mcp_usa_funcion_subyacente(self) -> None:
        async def _run() -> None:
            with patch.object(
                arxiv_mcp_server,
                "search_papers",
                return_value={"topic": "ai", "papers": []},
            ) as mocked:
                result = await arxiv_mcp_server.search_papers_mcp("ai", 3)

            mocked.assert_called_once_with(topic="ai", max_results=3)
            self.assertIn("topic", result)
            self.assertIn("papers", result)

        asyncio.run(_run())

    def test_extract_info_mcp_usa_funcion_subyacente(self) -> None:
        async def _run() -> None:
            fake_response = {"found": True, "paper": {"id": "1234.5678v1"}}
            with patch.object(
                arxiv_mcp_server, "extract_info", return_value=fake_response
            ) as mocked:
                result = await arxiv_mcp_server.extract_info_mcp("1234.5678v1")

            mocked.assert_called_once_with(paper_id="1234.5678v1")
            self.assertTrue(result["found"])
            self.assertEqual(result["paper"]["id"], "1234.5678v1")

        asyncio.run(_run())


if __name__ == "__main__":
    unittest.main()
