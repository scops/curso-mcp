import asyncio
import unittest
from unittest.mock import patch

from pydantic import BaseModel

from mcp.server.elicitation import (
    AcceptedElicitation,
    CancelledElicitation,
    DeclinedElicitation,
)

from ej2_4_chatbot_arxiv import arxiv_mcp_server


class _FakeSettings:
    debug = False
    log_level = "INFO"
    host = "127.0.0.1"
    port = 8000


class _FakeFastMCP:
    name = "arxiv-tools"
    instructions = "instrucciones de prueba"
    settings = _FakeSettings()


class _FakeCtx:
    """Context mínimo: solo expone .fastmcp y un .elicit configurable."""

    def __init__(self, elicit_result=None) -> None:
        self.fastmcp = _FakeFastMCP()
        self._elicit_result = elicit_result

    async def elicit(self, message, schema):
        return self._elicit_result


class _PaperSelection(BaseModel):
    paper_id: str
    confirm: bool


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


class TestIntrospectionAndPrompts(unittest.TestCase):
    def test_server_info_devuelve_identidad(self) -> None:
        info = arxiv_mcp_server.server_info(_FakeCtx())
        self.assertEqual(info["name"], "arxiv-tools")
        self.assertEqual(info["log_level"], "INFO")
        self.assertEqual(info["port"], 8000)

    def test_who_am_i_devuelve_estado(self) -> None:
        identity = arxiv_mcp_server.who_am_i(_FakeCtx())
        self.assertEqual(identity["server_name"], "arxiv-tools")
        self.assertEqual(identity["transport"], "stdio")

    def test_prompt_busqueda_general_es_texto(self) -> None:
        prompt = arxiv_mcp_server.prompt_busqueda_general()
        self.assertIsInstance(prompt, str)
        self.assertIn("arXiv", prompt)

    def test_prompt_analisis_detallado_devuelve_mensajes(self) -> None:
        mensajes = arxiv_mcp_server.prompt_analisis_detallado()
        self.assertEqual(len(mensajes), 3)


class TestAnalyzePaperElicitation(unittest.IsolatedAsyncioTestCase):
    async def test_acepta_y_confirma_lanza_analisis(self) -> None:
        ctx = _FakeCtx(
            AcceptedElicitation(data=_PaperSelection(paper_id="2401.01234", confirm=True))
        )
        with patch.object(
            arxiv_mcp_server, "extract_info", return_value={"found": True, "paper": {}}
        ) as mocked:
            result = await arxiv_mcp_server.analyze_paper_with_confirmation(ctx)

        mocked.assert_called_once_with(paper_id="2401.01234")
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["paper_id"], "2401.01234")

    async def test_acepta_sin_confirmar_se_cancela(self) -> None:
        ctx = _FakeCtx(
            AcceptedElicitation(data=_PaperSelection(paper_id="2401.01234", confirm=False))
        )
        result = await arxiv_mcp_server.analyze_paper_with_confirmation(ctx)
        self.assertEqual(result["status"], "cancelled")
        self.assertEqual(result["reason"], "user_did_not_confirm")

    async def test_rechazo_se_cancela(self) -> None:
        ctx = _FakeCtx(DeclinedElicitation())
        result = await arxiv_mcp_server.analyze_paper_with_confirmation(ctx)
        self.assertEqual(result["status"], "cancelled")
        self.assertEqual(result["reason"], "user_declined_elicitation")

    async def test_cancelacion_se_cancela(self) -> None:
        ctx = _FakeCtx(CancelledElicitation())
        result = await arxiv_mcp_server.analyze_paper_with_confirmation(ctx)
        self.assertEqual(result["status"], "cancelled")
        self.assertEqual(result["reason"], "user_cancelled_operation")


if __name__ == "__main__":
    unittest.main()
