# Curso MCP en Python – Guía general de ejercicios

Este repositorio `mcp/` agrupa todos los ejercicios prácticos del curso. Cada carpeta contiene su propio
`README.md` con las instrucciones detalladas; aquí tienes una guía rápida de qué hay en cada sitio y cómo
preparar el entorno común.

## Preparación rápida

1. Instala [uv](https://docs.astral.sh/uv/) una sola vez. En macOS/Linux:
   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```
   En Windows (PowerShell):
   ```powershell
   irm https://astral.sh/uv/install.ps1 | iex
   ```
2. Desde la raíz `mcp/` sincroniza dependencias y crea el entorno `.venv` compartido:
   ```bash
   uv sync
   ```
3. Añade un `.env` con las claves que usan los ejercicios (Anthropic, OpenAI, OMDb, credenciales de sakila, etc.).

A partir de ahí ejecuta siempre los ejemplos con `uv run …` desde la raíz del repo.

## Resumen de ejercicios

| Carpeta | Ejercicios | Qué construyes | Qué practicas en MCP |
| --- | --- | --- | --- |
| `ej1_first_chatbot/` | Ejercicio 1 | Cliente + servidor MCP mínimo por STDIO. | c_tools sencillos, c_state (cliente/servidor), tests básicos. |
| `ej2_4_chatbot_arxiv/` | Ejercicios 2-4 | Chatbot arXiv (versión sin MCP, con MCP y cliente OpenAI). | c_tools reales, c_instr (prompts MCP), uso de `ClientSession`. |
| `ej5_6_chatbot_omdb/` | Ejercicios 5-6 | Servidor MCP HTTP (OMDb) + cliente Streamlit/Inspector. | c_tools sobre APIs externas, c_query (streamable-http). |
| `ej7_mcp_rag_db/` | Ejercicio 7 | RAG sobre incidencias + servidor MCP con resources y memoria. | c_tools, c_know (resources), c_mem (feedback persistente). |
| `ej8_sakila_streaming/` | Ejercicio 8 | Agente de “plataforma de streaming” (sakila + OMDb). | c_tools de lectura/escritura, c_query mixto, MAS (multi-servidor). |
| `ej9_orquestador/` | Ejercicio 9 | Servidor MCP orquestador que llama a otros MCP. | c_tools de alto nivel, MAS/orquestación MCP→MCP. |

### Detalle rápido

#### `ej1_first_chatbot/`
- Punto de partida del curso. Servidor STDIO con tools `echo`, `sumar`, `chiste_de_padre` y cliente MCP en terminal.
- Practica añadir tu propia tool y ver cómo el LLM la descubre.
- Ejecuta:
  ```bash
  uv run python ej1_first_chatbot/first_mcp_client.py ej1_first_chatbot/first_mcp_server.py
  ```
- README completo en `ej1_first_chatbot/README.md`.

#### `ej2_4_chatbot_arxiv/`
- Evoluciona el chatbot para consultar arXiv: primero sin MCP, luego con MCP y prompts reutilizables, y finalmente con un cliente OpenAI.
- Practicas c_instr (prompts MCP), `session.get_prompt()`, Streamlit como host MCP y clientes alternativos.
- Ejemplos:
  ```bash
  uv run streamlit run ej2_4_chatbot_arxiv/app.py                  # versión sin MCP
  uv run streamlit run ej2_4_chatbot_arxiv/claude_mcp_client.py    # versión con MCP
  ```

#### `ej5_6_chatbot_omdb/`
- Servidor MCP “omdb-tools” expuesto por HTTP (`streamable-http`) y cliente LLM en Streamlit.
- Ideal para aprender a envolver una API existente y probarla con MCP Inspector.
- Lanza el servidor:
  ```bash
  uv run python ej5_6_chatbot_omdb/omdb_mcp_server.py
  ```
- Cliente Streamlit:
  ```bash
  uv run streamlit run ej5_6_chatbot_omdb/omdb_llm_client.py
  ```

#### `ej7_mcp_rag_db/`
- Pipeline RAG sobre `incidents.db` + servidor MCP con tools (`index_tickets`, `rag_answer`) y resources (`tickets/latest`, `tickets/{id}`).
- Añade también un pequeño almacén de feedback (`save_feedback`, `list_feedback`, `feedback/latest`).
- Pasos típicos:
  ```bash
  uv run python ej7_mcp_rag_db/seed_db.py
  uv run python ej7_mcp_rag_db/rag_local.py          # modo local
  uv run python ej7_mcp_rag_db/rag_mcp_server.py     # servidor MCP
  ```

#### `ej8_sakila_streaming/`
- Servidor MCP que combina sakila (MySQL) con OMDb y un cliente Streamlit que actúa como host.
- Incluye el ejercicio final de coordinar varios servidores MCP (sakila + OMDb) desde un mismo host.
- Comandos útiles:
  ```bash
  uv run python ej8_sakila_streaming/sakila_mcp_server.py
  uv run streamlit run ej8_sakila_streaming/streamlit_sakila_client.py
  ```

#### `ej9_orquestador/`
- Servidor MCP `orchestrator` que por dentro actúa como **cliente MCP** de otros servidores del curso.
- Ofrece tools de alto nivel como `research_incident_with_papers`, que:
  - llama al servidor RAG de incidencias (`ej7_mcp_rag_db`) y al servidor arXiv (`ej2_4_chatbot_arxiv`),
  - y devuelve una respuesta combinada (tickets internos + papers externos).
- Ideal para practicar patrones de orquestación MCP→MCP.
- Ejecución:
  ```bash
  uv run python ej9_orquestador/orchestrator_mcp_server.py
  ```

#### `ej10_reto/`
- Diseñar un **servidor MCP propio** para esa API, con la complejidad que tú quieras. La versión básica puede ser:

- Un servidor `FastMCP` con:
  - 1–2 tools de búsqueda/listado.
  - 1–2 tools de detalle (por id, por nombre, etc.).
A partir de ahí, puedes subir el nivel combinando ideas del curso:

## Tests

- Todos los tests del curso:
  ```bash
  uv run python -m unittest
  ```
- Tests por ejercicio:
  ```bash
  uv run python -m unittest ej1_first_chatbot.tests.test_server_tools
  uv run python -m unittest ej2_4_chatbot_arxiv.tests.test_tools_arxiv ej2_4_chatbot_arxiv.tests.test_arxiv_mcp_server
  uv run python -m unittest ej5_6_chatbot_omdb.tests.test_omdb_mcp_server
  uv run python -m unittest ej7_mcp_rag_db.tests.test_rag_mcp_server
  uv run python -m unittest ej8_sakila_streaming.tests.test_sakila_mcp_server
  uv run python -m unittest ej9_orquestador.tests.test_orchestrator_mcp_server
  ```

Recuerda que cada carpeta tiene su propio `README.md` con instrucciones detalladas, mini‑ejercicios y notas didácticas. Usa este documento solo como mapa general del curso.
