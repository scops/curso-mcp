import asyncio
import json
import unittest
from unittest.mock import patch

import mcp_types as types
from mcp import Client
from mcp.server.mcpserver import (
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


class _FakeMCPServer:
    name = "arxiv-tools"
    instructions = "instrucciones de prueba"
    settings = _FakeSettings()


class _FakeCtx:
    """Context mínimo: solo expone .mcp_server."""

    def __init__(self) -> None:
        self.mcp_server = _FakeMCPServer()


_PaperSelection = arxiv_mcp_server.PaperSelection


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
    """Con Resolve, la tool recibe la respuesta ya resuelta como argumento."""

    async def test_acepta_y_confirma_lanza_analisis(self) -> None:
        seleccion = AcceptedElicitation(
            data=_PaperSelection(paper_id="2401.01234", confirm=True)
        )
        with patch.object(
            arxiv_mcp_server, "extract_info", return_value={"found": True, "paper": {}}
        ) as mocked:
            result = await arxiv_mcp_server.analyze_paper_with_confirmation(seleccion)

        mocked.assert_called_once_with(paper_id="2401.01234")
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["paper_id"], "2401.01234")

    async def test_acepta_sin_confirmar_se_cancela(self) -> None:
        seleccion = AcceptedElicitation(
            data=_PaperSelection(paper_id="2401.01234", confirm=False)
        )
        result = await arxiv_mcp_server.analyze_paper_with_confirmation(seleccion)
        self.assertEqual(result["status"], "cancelled")
        self.assertEqual(result["reason"], "user_did_not_confirm")

    async def test_rechazo_se_cancela(self) -> None:
        result = await arxiv_mcp_server.analyze_paper_with_confirmation(
            DeclinedElicitation()
        )
        self.assertEqual(result["status"], "cancelled")
        self.assertEqual(result["reason"], "user_declined_elicitation")

    async def test_cancelacion_se_cancela(self) -> None:
        result = await arxiv_mcp_server.analyze_paper_with_confirmation(
            CancelledElicitation()
        )
        self.assertEqual(result["status"], "cancelled")
        self.assertEqual(result["reason"], "user_cancelled_operation")


class TestAnalyzePaperResolveExtremoAExtremo(unittest.IsolatedAsyncioTestCase):
    """Flujo real: cliente MCP en memoria, el resolver pregunta y el cliente contesta."""

    async def test_el_cliente_recibe_la_pregunta_y_la_tool_su_respuesta(self) -> None:
        preguntas = []

        async def responder(context, params: types.ElicitRequestParams) -> types.ElicitResult:
            preguntas.append(params.message)
            return types.ElicitResult(
                action="accept", content={"paper_id": "2401.01234", "confirm": True}
            )

        with patch.object(
            arxiv_mcp_server, "extract_info", return_value={"found": True, "paper": {}}
        ) as mocked:
            async with Client(arxiv_mcp_server.mcp, elicitation_callback=responder) as client:
                tools = await client.list_tools()
                tool = next(
                    t for t in tools.tools if t.name == "analyze_paper_with_confirmation"
                )
                # El parámetro resuelto no forma parte del schema que ve el modelo
                self.assertNotIn("seleccion", tool.input_schema.get("properties", {}))

                result = await client.call_tool("analyze_paper_with_confirmation", {})

        self.assertEqual(len(preguntas), 1)
        mocked.assert_called_once_with(paper_id="2401.01234")
        self.assertFalse(result.is_error)
        texto = next(c.text for c in result.content if isinstance(c, types.TextContent))
        self.assertEqual(json.loads(texto)["status"], "ok")


if __name__ == "__main__":
    unittest.main()
