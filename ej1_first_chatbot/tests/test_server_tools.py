import asyncio
import os
import unittest
from pathlib import Path

from first_mcp_server import echo, sumar, chiste_de_padre, CHISTES_DE_PADRE
from first_mcp_client import MCPChatClient


class TestServerTools(unittest.TestCase):
    def test_echo_devuelve_lo_mismo(self) -> None:
        resultado = asyncio.run(echo("hola MCP"))
        self.assertEqual(resultado, "hola MCP")

    def test_sumar_mal_a_proposito(self) -> None:
        """Comprueba la lógica 'rota' intencionadamente: a + b * 0.5."""
        resultado = asyncio.run(sumar(2, 4))
        self.assertEqual(resultado, 2 + 4 * 0.5)

    def test_chiste_de_padre_devuelve_de_lista(self) -> None:
        resultado = asyncio.run(chiste_de_padre())
        self.assertTrue(resultado)
        self.assertIn(resultado, CHISTES_DE_PADRE)


class TestClientServerStartup(unittest.TestCase):
    def test_cliente_y_servidor_inician_sin_error(self) -> None:
        """
        Test de integración muy pequeño que comprueba que:
        - El cliente puede lanzar el servidor MCP.
        - La sesión MCP se inicializa y lista tools.
        - Todo se cierra sin lanzar excepciones.
        """

        async def _run() -> None:
            client = MCPChatClient()
            try:
                # Ruta al servidor relativa a la raíz del proyecto (mcp/)
                server_path = (
                    Path(__file__).resolve().parents[1] / "first_mcp_server.py"
                )
                await client.connect_to_server(str(server_path))
            finally:
                await client.cleanup()

        # Si algo va mal (por ejemplo, servidor no arranca),
        # asyncio.run lanzará una excepción y el test fallará.
        asyncio.run(_run())


if __name__ == "__main__":
    unittest.main()
