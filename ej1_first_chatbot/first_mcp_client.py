import asyncio
import sys
from typing import Optional, List, Dict
from contextlib import AsyncExitStack

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

import os
from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()  # carga ANTHROPIC_API_KEY y MODEL desde .env
MODEL = os.getenv("MODEL")
if not MODEL:
    raise RuntimeError(
        "La variable de entorno MODEL no está definida. "
        "Crea un archivo .env con una línea como: MODEL=claude-haiku-4-5-20251001"
    )



class MCPChatClient:
    """
    Cliente MCP sencillo:
    - Se conecta a un servidor MCP por STDIO.
    - Descubre los tools disponibles.
    - Usa Claude (Anthropic) para decidir qué tool usar.
    """

    def __init__(self) -> None:
        self.session: Optional[ClientSession] = None
        self.exit_stack = AsyncExitStack()
        # El SDK de Anthropic lee ANTHROPIC_API_KEY del entorno
        self.anthropic = Anthropic()

    async def connect_to_server(self, server_script_path: str) -> None:
        """
        Conecta con el servidor MCP indicado por ruta al script .py.
        Ejemplo: python first_mcp_client.py first_mcp_server.py
        """
        if not server_script_path.endswith(".py"):
            raise ValueError("El servidor debe ser un script .py")

        server_params = StdioServerParameters(
            command=sys.executable,
            args=[server_script_path],
            env=None,
        )

        # Abrimos transporte stdio → servidor MCP
        stdio_transport = await self.exit_stack.enter_async_context(
            stdio_client(server_params)
        )
        self.stdio, self.write = stdio_transport

        # Creamos sesión MCP
        self.session = await self.exit_stack.enter_async_context(
            ClientSession(self.stdio, self.write)
        )
        await self.session.initialize()

        # Listamos tools disponibles
        response = await self.session.list_tools()
        tools = response.tools
        print("\nConectado al servidor MCP con tools:")
        for tool in tools:
            print(f" - {tool.name}: {tool.description}")

    async def process_query(self, query: str) -> str:
        """
        Procesa una consulta usando Claude + tools MCP.
        """
        if self.session is None:
            raise RuntimeError("Sesión MCP no inicializada.")

        # Mensajes iniciales para el LLM
        messages: List[Dict] = [
            {
                "role": "user",
                "content": query,
            }
        ]

        # Obtenemos el catálogo de tools desde el servidor MCP
        tools_response = await self.session.list_tools()
        available_tools = [
            {
                "name": tool.name,
                "description": tool.description,
                "input_schema": tool.inputSchema,
            }
            for tool in tools_response.tools
        ]

        # Primera llamada a Claude con las tools disponibles
        response = self.anthropic.messages.create(
            model=MODEL,
            max_tokens=400,
            messages=messages,
            tools=available_tools,
        )

        final_text_parts: List[str] = []
        assistant_message_content: List[Dict] = []

        # Recorremos el contenido devuelto por Claude
        for content in response.content:
            if content.type == "text":
                final_text_parts.append(content.text)
                assistant_message_content.append(
                    {"type": "text", "text": content.text}
                )

            elif content.type == "tool_use":
                tool_name = content.name
                tool_args = content.input

                # Ejecutamos el tool en el servidor MCP
                result = await self.session.call_tool(tool_name, tool_args)

                # Añadimos trazas mínimas
                final_text_parts.append(
                    f"[Llamando al tool {tool_name} con args {tool_args}]"
                )

                # Construimos el flujo de mensajes para la siguiente llamada
                assistant_message_content.append(
                    {
                        "type": "tool_use",
                        "id": content.id,
                        "name": tool_name,
                        "input": tool_args,
                    }
                )
                messages.append(
                    {
                        "role": "assistant",
                        "content": assistant_message_content,
                    }
                )
                messages.append(
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": content.id,
                                "content": result.content,
                            }
                        ],
                    }
                )

                # Segunda llamada a Claude, ya con resultados del tool
                response = self.anthropic.messages.create(
                    model=MODEL,
                    max_tokens=400,
                    messages=messages,
                    tools=available_tools,
                )

                # Asumimos que ahora viene texto final
                for c2 in response.content:
                    if c2.type == "text":
                        final_text_parts.append(c2.text)

        if not final_text_parts:
            return "[Sin respuesta de Claude]"

        return "\n".join(final_text_parts)

    async def chat_loop(self) -> None:
        """
        Bucle interactivo en terminal.
        """
        print("\nCliente MCP iniciado.")
        print("Escribe tu consulta o 'salir' para terminar.")

        while True:
            try:
                query = await asyncio.to_thread(input, "\nTú: ")
                query = query.strip()
                if query.lower() in ("salir", "exit", "quit"):
                    break
                answer = await self.process_query(query)
                print("\nBot:\n" + answer)
            except Exception as e:
                print(f"\n[ERROR] {e}")

    async def cleanup(self) -> None:
        """Cierra correctamente conexiones y recursos."""
        await self.exit_stack.aclose()


async def main() -> None:
    if len(sys.argv) < 2:
        print("Uso: python first_mcp_client.py <ruta_a_first_mcp_server.py>")
        sys.exit(1)

    server_script = sys.argv[1]
    client = MCPChatClient()

    try:
        await client.connect_to_server(server_script)
        await client.chat_loop()
    finally:
        await client.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
