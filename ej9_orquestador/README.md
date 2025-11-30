# Ejercicio 9 – Servidor MCP orquestador (MCP sobre MCP)

En este ejercicio creas un **servidor MCP que actúa como cliente de otros servidores MCP del curso**.
La idea es practicar un patrón que todavía no habíamos tocado: un servidor que no tiene lógica de
negocio propia, sino que **orquesta** otros servidores MCP por ti.

---

## 1. Idea general

El servidor `orchestrator_mcp_server.py`:

- Se expone como servidor MCP por STDIO (`FastMCP("orchestrator")`).
- Cuando le llamas a ciertos tools:
  - Lanza el servidor RAG de incidencias (`ej7_mcp_rag_db/rag_mcp_server.py`) vía STDIO.
  - Lanza el servidor de arXiv (`ej2_4_chatbot_arxiv/arxiv_mcp_server.py`) vía STDIO.
  - Usa `ClientSession` para llamar a sus tools (`rag_answer`, `search_papers_mcp`) y combina los resultados.

Así practicas **MCP “sobre MCP”**: un servidor que internamente es también un cliente MCP.

---

## 2. Tools del orquestador

Archivo principal: `ej9_orquestador/orchestrator_mcp_server.py`.

### 2.1. `research_incident_with_papers`

```python
@mcp.tool()
async def research_incident_with_papers(
    incident_question: str,
    topic: str | None = None,
    max_papers: int = 3,
    k: int = 5,
) -> Dict[str, Any]:
    ...
```

Qué hace:

- Llama al servidor RAG de incidencias (`ej7_mcp_rag_db/rag_mcp_server.py`) usando:
  - Tool `rag_answer(question, k)` → devuelve `answer` + `sources`.
- Llama al servidor de arXiv (`ej2_4_chatbot_arxiv/arxiv_mcp_server.py`) usando:
  - Tool `search_papers_mcp(topic, max_results)` → devuelve papers relevantes.

La respuesta que devuelve el orquestador incluye, en un solo dict:

- `incident_question` → la pregunta original.
- `incident_answer` → la respuesta del servidor RAG.
- `incident_sources` → tickets usados como contexto.
- `arxiv_topic` → tema usado para buscar en arXiv (por defecto la propia pregunta).
- `arxiv_results` → resultado devuelto por `search_papers_mcp`.

Es decir: **una llamada a un tool de alto nivel** que por debajo coordina **dos servidores MCP distintos**.

### 2.2. `list_orchestrated_servers`

```python
@mcp.tool()
async def list_orchestrated_servers() -> List[Dict[str, Any]]:
    ...
```

No llama a nada externo; simplemente devuelve un resumen de los servidores que el orquestador
espera usar:

- `incidents-rag` → `ej7_mcp_rag_db/rag_mcp_server.py`
- `arxiv-tools` → `ej2_4_chatbot_arxiv/arxiv_mcp_server.py`

Sirve como documentación viva: puedes pedirle al orquestador que te cuente qué otros servidores
usa por debajo.

---

## 3. Cómo ejecutar el orquestador

Como siempre, desde la raíz `mcp/` y tras haber hecho `uv sync`:

```bash
uv run python ej9_orquestador/orchestrator_mcp_server.py
```

Esto lanza el servidor MCP `orchestrator` por STDIO.  
No necesitas levantar manualmente los otros servidores: cada vez que el orquestador tenga que
llamar a RAG o arXiv, lanzará sus scripts correspondientes como procesos MCP independientes
por STDIO.

Si quieres ver qué está pasando por dentro, puedes:

- Configurar el orquestador como servidor MCP en un host (Claude Desktop, ChatGPT con MCP, etc.).
- Llamar a `list_tools()` desde el host para ver:
  - `research_incident_with_papers`
  - `list_orchestrated_servers`

---

## 4. Ejemplos de uso

Desde un host MCP o cliente propio:

- Preguntas tipo soporte + documentación:

  - “Tengo errores 500 intermitentes en la API de usuarios (database is locked).  
     Usa tus herramientas para analizar incidencias y recomendarme papers de arXiv
     que me ayuden a entender el problema.”

  - “Tenemos timeouts en el panel de administración tras un despliegue.  
     Investiga con las incidencias internas y sugiéreme 2-3 papers relevantes de arXiv
     sobre latencia en microservicios.”

En ambos casos, el host solo ve un tool `research_incident_with_papers`, pero por debajo:

- El servidor RAG responde con ejemplos de tickets similares.
- El servidor de arXiv aporta contexto externo (papers) sobre el tema.

---

## 5. Qué practicas en este ejercicio

Encaje en el esquema del curso:

- **c_tools**: tools de alto nivel que no hablan directamente con APIs o BDs, sino con otros servidores MCP.
- **c_state / MAS**: un servidor que coordina a otros servidores MCP, actuando como “agente orquestador”.

Primitivos MCP/FastMCP que aparecen:

- Uso de `ClientSession` y `stdio_client` dentro de un servidor MCP.
- Llamadas `session.initialize()` y `session.call_tool(...)` a servidores hijos.
- Tools MCP que agregan resultados de varias fuentes en una sola respuesta estructurada.

Este ejercicio es un buen cierre para ver cómo MCP no solo sirve para “hacer tools”, sino también para
componer y orquestar servicios entre sí.

