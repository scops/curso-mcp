# Ejercicio 8 – MCP + MySQL (sakila) + OMDb + visualizaciones

En este ejercicio vas a simular el backend de una **plataforma de streaming** combinando:

- Una base de datos **MySQL sakila** como catálogo principal.
- La API de **OMDb** para enriquecer el catálogo y crear nuevas películas.
- Un servidor **MCP** que expone tools de lectura y escritura sobre sakila.
- Un cliente **Streamlit** que permite al LLM usar esos tools y mostrar visualizaciones sencillas.

La idea es que veas cómo MCP te permite mezclar datos internos (BD) y externos (OMDb) y cómo un LLM puede usar esos tools para responder preguntas y actualizar el catálogo.

---

## 1. Requisitos previos

Antes de empezar con este ejercicio, asegúrate de:

1. Tener la base de datos **sakila** instalada en un MySQL local.
2. Haber ejecutado al menos una vez, desde la raíz `mcp/`:

   ```bash
   uv sync
   ```

3. Tener las variables necesarias en `mcp/.env`:

   ```env
   # Claves para el modelo
   ANTHROPIC_API_KEY=tu_api_key_de_anthropic
   MODEL=claude-haiku-4-5-20251001

   # Configuración de la base de datos sakila
   SAKILA_HOST=127.0.0.1
   SAKILA_PORT=3306
   SAKILA_USER=tu_usuario
   SAKILA_PASSWORD=tu_password
   SAKILA_DB=sakila

   # Clave para OMDb
   OMDB_API_KEY=tu_api_key_de_omdb
   ```

El módulo `sakila_db.py` se encarga de leer estas variables y abrir la conexión a MySQL.

---

## 2. Ficheros importantes del ejercicio

Dentro de `ej8_sakila_streaming/` encontrarás:

- `sakila_db.py`  
  Módulo de acceso a la base de datos:
  - Crea una conexión a MySQL sakila usando las variables de entorno.
  - Expone helpers como:
    - `fetch_all(query, params)` → para lanzar consultas `SELECT`.
    - `execute_and_return_id(query, params)` → para hacer `INSERT` y devolver el `id` generado.

- `sakila_mcp_server.py`  
  Servidor MCP (`FastMCP("sakila-streaming")`) que combina:
  - Lectura desde la base de datos `sakila`.
  - Llamadas a la API de OMDb usando `httpx` y `OMDB_API_KEY`.

  Tools principales:

  - `get_latest_films(limit: int = 10)`  
    Devuelve las últimas películas registradas en la tabla `film` (id, título, año, rating, duración).

  - `get_rating_distribution()`  
    Devuelve dos listas `ratings` y `counts` para construir un gráfico de barras con el número de películas por rating (G, PG, PG‑13, etc.).

  - `create_film_from_omdb(title: str, year: int | None = None)`  
    - Busca la película en OMDb por título/año.
    - Recupera sus detalles (`Title`, `Year`, `Plot`, `imdbID`, etc.).
    - Inserta un registro en la tabla `film` de sakila (con valores razonables por defecto).
    - Devuelve el `film_id` creado, el `imdb_id` y un resumen de la respuesta de OMDb.

  Mensaje didáctico clave: MCP aquí no solo sirve para **leer** datos, también expone tools que **escriben** en la base de datos.

- `streamlit_sakila_client.py`  
  Cliente Streamlit que se comporta como **host MCP**:
  - Lanza el servidor `sakila_mcp_server.py` por STDIO.
  - Llama a `list_tools()` y pasa esos tools a Claude.
  - Implementa el patrón `tool_use → session.call_tool(...) → tool_result`.
  - Construye la interfaz de chat y las visualizaciones.

---

## 3. Paso 1 – Probar el servidor MCP de sakila

Antes de abrir la interfaz web, conviene asegurarse de que el servidor MCP arranca sin problemas.

Desde la raíz `mcp/`:

```bash
uv run python ej8_sakila_streaming/sakila_mcp_server.py
```

Si todo va bien:

- El servidor se inicializará como `sakila-streaming` usando transporte `stdio`.
- Se conectará a la base de datos MySQL usando las variables de entorno.
- Validará que `OMDB_API_KEY` está disponible (lo necesita para `create_film_from_omdb`).

Puedes probar este servidor con una herramienta como **MCP Inspector** (vinculándolo como comando `python ej8_sakila_streaming/sakila_mcp_server.py`) para ver:

- El resultado de `list_tools()`.
- Llamadas manuales a `get_latest_films`, `get_rating_distribution` y `create_film_from_omdb`.

---

## 4. Paso 2 – Lanzar el cliente Streamlit (host MCP)

La forma recomendada es ejecutar siempre desde `mcp/` usando `uv`:

```bash
uv run streamlit run ej8_sakila_streaming/streamlit_sakila_client.py
```

Esto abrirá una aplicación en tu navegador (por defecto `http://localhost:8501`) con:

- Un área de chat donde puedes escribir tus consultas.
- Un panel lateral con controles y botones de ayuda.

Cada vez que haces una pregunta, el flujo es:

1. El cliente abre una sesión MCP (`ClientSession`) con el servidor `sakila_mcp_server.py`.
2. Llama a `list_tools()` para descubrir las tools disponibles.
3. Pasa esa lista de tools a Claude junto con tu mensaje.
4. El modelo puede:
   - Responder directamente con texto.
   - O bien pedir el uso de una o varias tools (mensajes `tool_use`).
5. Si hay `tool_use`, el cliente:
   - Llama a `session.call_tool(tool_name, tool_args)` en el servidor MCP.
   - Convierte la respuesta en `tool_result`.
   - Se la reenvía al modelo para que construya la respuesta final.

Tú solo ves el chat y, si miras los logs, puedes ver cómo el modelo decide qué tool usar.

---

## 5. Qué puedes preguntar al agente

Algunas ideas de prompts para que experimentes:

- Sobre el catálogo:
  - “Enséñame las últimas 5 películas que tenemos en el catálogo.”
  - “¿Qué películas recientes tenemos con rating PG-13?”

- Sobre OMDb + creación en sakila:
  - “Crea en la base de datos la película ‘Inception’ usando OMDb y dime qué `film_id` se ha creado.”
  - “Añade ‘The Matrix’ si no está en sakila y resúmeme de qué va.”

- Visualizaciones:
  - “Enséñame un gráfico con la distribución de ratings del catálogo.”

El cliente Streamlit incluye ejemplos en el panel lateral para llamar directamente a `get_rating_distribution` y dibujar el gráfico con `st.bar_chart`.

---

## 6. Mini‑ejercicios sugeridos

Te propongo varias ideas para que toques este ejercicio y lo adaptes:

- Cambiar el **prompt de sistema** en `streamlit_sakila_client.py` para que el asistente:
  - Hable con un tono más técnico o más informal.
  - Incluya siempre una pequeña recomendación personal (“si te gusta X, también te puede gustar Y…”).

- Añadir un selector en la barra lateral de Streamlit para:
  - Elegir el tipo de rating preferido (por ejemplo, mostrar primero películas `PG` y `PG-13`).
  - Limitar el número máximo de películas que se muestran en las respuestas.

- Crear nuevas tools en `sakila_mcp_server.py`, por ejemplo:
  - `get_films_by_category(category_name: str)` → devuelve todas las películas de una categoría concreta.
  - `get_top_customers(limit: int = 10)` → lista de clientes que más han alquilado (usando tablas `customer` y `rental`).

- Combinar este servidor con el servidor OMDb del ejercicio 5 en un host MCP que soporte varios servidores a la vez y preguntar cosas que mezclen ambos, por ejemplo:
  - “¿Tenéis disponible ‘ACADEMY DINOSAUR’? Si sí, dime en qué regiones y añade una sinopsis usando OMDb.”

Cada vez que añadas o cambies un tool, acostúmbrate a:

1. Probar primero el servidor solo (`uv run python ej8_sakila_streaming/sakila_mcp_server.py`).
2. Luego lanzar el cliente Streamlit y hacer algunas consultas de prueba.

Así podrás iterar con seguridad antes de subir tus cambios a Git.

---

## 7. Ejercicio final multi‑servidor (MAS)

Como colofón del curso, puedes configurar un host MCP (Claude Desktop, ChatGPT con MCP, Open WebUI, etc.) con **dos servidores a la vez**:

- Servidor OMDb del ejercicio 5 (HTTP, `streamable-http`).
- Servidor sakila/streaming de este ejercicio (STDIO).

Configuración típica:

- OMDb (HTTP):
  - Tipo: HTTP / `streamable-http`.
  - URL: `http://127.0.0.1:8000/mcp`.
  - Comando para levantarlo: `uv run python ej5_6_chatbot_omdb/omdb_mcp_server.py`.

- Sakila (STDIO):
  - Tipo: comando local.
  - Comando: `python`.
  - Args: `ej8_sakila_streaming/sakila_mcp_server.py`.
  - Directorio de trabajo: raíz `mcp/`.

En el host, crea un asistente con un prompt de sistema que explique claramente:

- Usa el servidor sakila para todo lo que tenga que ver con **catálogo interno** (qué películas tenemos, en qué regiones, etc.).
- Usa el servidor OMDb para **enriquecer** las películas con sinopsis, reparto, duración y ratings públicos.
- Cuando la consulta mezcle ambas cosas, combina:
  - Primero datos internos (disponibilidad en sakila).
  - Luego datos externos (detalles desde OMDb).

Prueba consultas tipo:

- “¿Tenéis disponible *ACADEMY DINOSAUR*? Si sí, dime dónde y añade una sinopsis usando OMDb.”
- “Recomiéndame 3 películas de ciencia ficción que tengamos en el catálogo y cuéntame de qué van.”

Este ejercicio final ilustra la parte de **sistemas multi‑agente (MAS)** de tu esquema: el modelo debe coordinarse con **dos servidores MCP distintos** para responder bien.

---

## Encaje en el esquema del curso (MCP)

En este ejercicio final trabajas sobre todo:

- **c_tools**: tools MCP de lectura y escritura sobre la BD sakila (`get_latest_films`, `get_rating_distribution`, `create_film_from_omdb`, etc.).
- **c_know**: uso de sakila como base de conocimiento estructurada (consultas de catálogo, agregados para visualizaciones).
- **c_query**: combinación de STDIO (sakila) y HTTP (OMDb) como canales MCP.
- **MAS / multi‑servidor**: coordinación entre varios servidores MCP (sakila + OMDb) desde un mismo host.

Primitivos MCP/FastMCP que aparecen:

- Servidor MCP por STDIO para sakila (`FastMCP("sakila-streaming")`).
- Tools MCP que mezclan datos internos (MySQL) y externos (OMDb vía HTTP).
- Cliente MCP en Streamlit que orquesta `list_tools()` y `call_tool()` para construir respuestas y visualizaciones.
