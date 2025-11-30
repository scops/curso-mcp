# Ejercicios 5 y 6 – Chatbot OMDb con MCP (HTTP)

Esta carpeta contiene el código de los **ejercicios 5 y 6** del curso:

- **Ejercicio 5**: servidor MCP para OMDb usando transporte HTTP (`streamable-http`).
- **Ejercicio 6**: inspeccionar el servidor con MCP Inspector y consumirlo desde un cliente LLM con Streamlit.

La idea es que veas un ejemplo completo de:

- Cómo envolver una API HTTP real (OMDb) dentro de un servidor MCP.
- Cómo inspeccionar ese servidor con herramientas genéricas.
- Cómo construir un cliente LLM que usa MCP sin hablar directamente con OMDb.

---

## 1. Requisitos comunes

Como en el resto del curso:

- Estar en la raíz `mcp/`.
- Haber ejecutado al menos una vez:

  ```bash
  uv sync
  ```

- Tener configurado en `mcp/.env`:

  ```env
  ANTHROPIC_API_KEY=tu_api_key_de_anthropic
  OMDB_API_KEY=tu_api_key_de_omdb
  ANTHROPIC_MODEL=claude-3-5-sonnet-latest
  OMDB_MCP_URL=http://127.0.0.1:8000/mcp
  ```

  (Puedes ajustar el modelo si lo deseas.)

---

## 2. Ejercicio 5 – Servidor MCP OMDb (HTTP streamable)

Archivo principal: `ej5_6_chatbot_omdb/omdb_mcp_server.py`

Qué hace:

- Usa `FastMCP` para crear un servidor MCP llamado `"omdb-tools"`:

  ```python
  mcp = FastMCP(
      name="omdb-tools",
      host="127.0.0.1",
      port=8000,
  )
  ```

- Usa el transporte `streamable-http`:

  ```python
  def main() -> None:
      mcp.run(transport="streamable-http")
  ```

- Expone dos tools principales:
  - `search_movies(query, media_type, year, max_results)`  
    Busca en OMDb y devuelve una lista de resultados básicos (título, año, id de IMDB, etc.).
  - `get_movie_detail(imdb_id, plot)`  
    Devuelve detalles completos de una película/serie concreta.

Cómo levantar el servidor (desde `mcp/`):

```bash
uv run python ej5_6_chatbot_omdb/omdb_mcp_server.py
```

Si todo va bien, tendrás un servidor MCP escuchando en:

- `http://127.0.0.1:8000/mcp`

Notas didácticas:

- A diferencia de los ejemplos anteriores (STDIO), aquí el servidor:
  - Escucha en un puerto HTTP.
  - Se puede inspeccionar fácilmente con herramientas externas (siguiente ejercicio).

---

## 3. Ejercicio 6 – Inspector MCP + Cliente LLM

En este ejercicio vas a usar dos piezas:

1. **MCP Inspector** para “ver” el servidor.
2. Un **cliente LLM** en Streamlit que habla con el servidor MCP, no con OMDb directamente.

### 3.1. Probar el servidor con MCP Inspector

Con el servidor OMDb ya arrancado (ejercicio 5), en otra terminal:

```bash
npx @modelcontextprotocol/inspector
```

En la UI del inspector:

- Conéctate a:

  - `http://127.0.0.1:8000/mcp`

- Explora:
  - `list_tools()` → verás `search_movies` y `get_movie_detail`.
  - Prueba a llamar a `search_movies` con un título simple.
  - Mira cómo responde el servidor (estructura de JSON, campos devueltos, mensajes de error, etc.).

### 3.2. Cliente LLM: `omdb_llm_client.py`

Archivo principal: `ej5_6_chatbot_omdb/omdb_llm_client.py`

Qué hace:

- Es una app de **Streamlit** que:
  - Se conecta al servidor MCP vía HTTP con `streamablehttp_client(MCP_URL)`.
  - Crea una `ClientSession` MCP.
  - Descubre las tools disponibles (`search_movies`, `get_movie_details`, etc.) con `list_tools()`.
  - Pasa esa lista de tools a Claude (`Anthropic`) como parte de la petición.
  - Implementa el patrón:

    1. Claude responde con texto o con `tool_use`.
    2. Si hay `tool_use`, el cliente llama al servidor MCP (`session.call_tool(...)`).
    3. Convierte el resultado en `tool_result` y se lo devuelve al modelo.
    4. El modelo responde al usuario usando esos datos.

Cómo lanzarlo (con el servidor ya arrancado):

```bash
uv run streamlit run ej5_6_chatbot_omdb/omdb_llm_client.py
```

Se abrirá una página tipo chat donde puedes preguntar cosas como:

- “Recomiéndame 3 películas de ciencia ficción recientes y dime sus años.”
- “Dame más detalles sobre la película con id tt0133093.”

### 3.3. Qué remarcar en clase

- El cliente **no sabe nada** de cómo se llama a OMDb:
  - Solo sabe que hay tools con cierto nombre y esquema de entrada.
  - “Delegamos” toda la lógica OMDb en el servidor MCP.
- Cambiar el LLM (modelo, proveedor) no obliga a tocar el servidor OMDb.

---

## 4. Mini‑ejercicio sugerido

Algunas ideas que puedes probar como modificaciones en `omdb_llm_client.py`:

- Cambiar el prompt de sistema:
  - Hacer que el asistente responda con una recomendación personal (por qué ver esta peli).
  - O que priorice cierto tipo de información (por ejemplo, premios y críticas).
- Añadir un selector en la barra lateral para:
  - Elegir el tipo de contenido preferido (`movie`, `series`, `episode`).
  - Ajustar algún parámetro que luego el LLM tenga en cuenta a la hora de construir la pregunta a las tools.

De esta forma, practicas:

- Leer y entender un cliente MCP ya hecho.
- Hacer pequeños cambios controlados en la lógica de prompt/UX sin tocar el servidor.

---

## Encaje en el esquema del curso (MCP)

En los ejercicios 5 y 6 trabajas principalmente:

- **c_tools**: tools MCP reales sobre una API HTTP externa (`search_movies`, `get_movie_detail`).
- **c_query**: transporte `streamable-http`, donde la query del usuario viaja como JSON-RPC a un servidor MCP HTTP.

Primitivos MCP/FastMCP que aparecen:

- Servidor MCP HTTP con `FastMCP(...).run(transport="streamable-http")`.
- Tools MCP (`@mcp.tool()`) que envuelven llamadas a OMDb con `httpx`.
- Integración con MCP Inspector (`tools/list`, `tools/call`) y con un cliente LLM en Streamlit que usa `ClientSession` sobre HTTP.
