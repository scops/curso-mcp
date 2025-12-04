## Ejercicio 11 – RAG vs MCP sobre Sakila con LangChain

En este ejercicio comparamos dos enfoques sobre la misma base de datos **sakila** (MySQL):

- **RAG flexible/creativo**: mucho contexto, el modelo razona y combina información.
- **MCP tool‑driven (con LangChain)**: tools muy concretas, consultas dirigidas y rápidas.

### 1. Requisitos previos

- Tener configurada la base de datos `sakila` como en el ejercicio 8.
- Variables de entorno en `.env` (en la raíz `mcp/`):

```env
ANTHROPIC_API_KEY=tu_api_key_de_anthropic
MODEL=claude-haiku-4-5-20251001

SAKILA_HOST=127.0.0.1
SAKILA_PORT=3306
SAKILA_USER=...
SAKILA_PASSWORD=...
SAKILA_DB=sakila
```

### 2. Componentes

- `sakila_simple_mcp_server.py`  
  Servidor MCP minimalista con tools muy dirigidas:
  - `search_films_by_title`
  - `get_films_by_category`
  - `get_film_details`

- `sakila_rag_client.py`  
  Cliente RAG / agente SQL con LangChain:
  - Construye un `SQLDatabase` sobre sakila (MySQL).
  - Usa `SQLDatabaseToolkit` + `create_sql_agent` (patrón SQL agent de LangChain/LangGraph).
  - El modelo genera y ejecuta las consultas SQL que considere necesarias.

- `mcp_langchain_client.py`  
  Cliente LangChain + MCP:
  - Lanza el servidor `sakila-simple` por STDIO.
  - Usa `langchain-mcp` para exponer las tools como herramientas de LangChain.
  - El modelo decide qué tool usar y con qué argumentos.

- `benchmark_rag_vs_mcp.py`  
  Script que lanza varias preguntas y mide:
  - Tiempo de respuesta del RAG.
  - Tiempo de respuesta del agente MCP+LangChain.
  - Tamaño del contexto usado por RAG (nº de películas).

### 3. Cómo ejecutar el benchmark

Desde la raíz del repo `mcp/`:

```bash
uv run python ej11_rag_vs_mcp_sakila/benchmark_rag_vs_mcp.py
```

Verás, para cada pregunta:

- Tiempo en segundos de cada enfoque.
- Preview (primeros caracteres) de la respuesta RAG y MCP.
- Número de películas incluidas en el contexto RAG.

### 4. Interpretación

- **RAG (sakila_rag_client)**  
  - + Muy flexible: el modelo ve muchas películas a la vez.  
  - + Puede combinar información de varias categorías y campos.  
  - − Más tokens y latencia, respuestas más largas y a veces “verborrea”.

- **MCP + LangChain (mcp_langchain_client)**  
  - + Tools enfocadas: SQL directo y resultados acotados.  
  - + Menos contexto, menor latencia y respuesta más al grano.  
  - − Más dependiente de tener buenas tools; menos flexible para preguntas muy abiertas.

El objetivo pedagógico es ver cómo, sobre **la misma base de datos sakila**, cambia la experiencia según:

- Dejas al modelo “pensar con mucho contexto” (RAG).
- O le das herramientas muy específicas (MCP) y lo usas sobre todo como **orquestador**.
