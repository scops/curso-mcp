# Ejercicio 7 – MCP + RAG sobre una base de datos

En este ejercicio vas a combinar dos ideas importantes:

- **RAG** (Retrieval-Augmented Generation): usar una base de conocimiento propia para ayudar al modelo a responder.
- **MCP** (Model Context Protocol): exponer ese RAG como un servidor de tools reutilizable.

El escenario es una pequeña base de datos de **incidencias IT** en SQLite (`incidents.db`).  
El asistente debe responder dudas de soporte (errores 500, problemas de login, timeouts…) usando solo la información de esos tickets.

La idea es que primero montes un **RAG local embebido en un script** y, después, envuelvas exactamente el mismo pipeline en un **servidor MCP**.

---

## 1. Requisitos previos

Todo el curso comparte:

- Un único entorno gestionado con **uv** en la carpeta raíz `mcp/`.
- Un archivo de configuración común `mcp/.env`.

Antes de tocar este ejercicio, asegúrate de haber hecho:

1. Desde la raíz del repo `mcp/`:

   ```bash
   uv sync
   ```

2. Tener en `mcp/.env` al menos:

   ```env
   ANTHROPIC_API_KEY=tu_api_key_de_anthropic
   MODEL=claude-haiku-4-5-20251001

   OPENAI_API_KEY=tu_api_key_de_openai
   # Opcional: puedes cambiar el modelo de embeddings si quieres
   OPENAI_EMBEDDING_MODEL=text-embedding-3-small
   ```

`rag_local.py` usa:

- `ANTHROPIC_API_KEY` y `MODEL` para hablar con Claude.
- `OPENAI_API_KEY` (y opcionalmente `OPENAI_EMBEDDING_MODEL`) para calcular embeddings con OpenAI.

---

## 2. Ficheros importantes del ejercicio

Dentro de `ej7_mcp_rag_db/` tienes:

- `schema.sql`  
  Define la tabla `tickets` y las columnas necesarias.

- `seed_db.py`  
  Crea el fichero `incidents.db`, aplica `schema.sql` y rellena la tabla con varios tickets de ejemplo.

- `rag_local.py`  
  Módulo principal de RAG:
  - Carga los tickets desde `incidents.db`.
  - Genera **embeddings** del texto de cada ticket (título + cuerpo + tags).
  - Construye un índice en memoria con esos embeddings.
  - Expone funciones para:
    - Construir el índice (`build_index`).
    - Responder preguntas usando RAG (`answer(question: str, k: int = 5)`).

- `rag_mcp_server.py`  
  Envuelve la lógica de `rag_local.py` en un **servidor MCP** usando `FastMCP`:
  - Tool `index_tickets()` → reconstruye el índice de embeddings.
  - Tool `rag_answer(question: str, k: int = 5)` → ejecuta el pipeline RAG y devuelve `answer + sources`.

- `pseudo_client.py` (opcional)  
  Cliente mínimo de ejemplo que actúa como host MCP:
  - Lanza el servidor MCP por STDIO.
  - Llama a `list_tools()` para descubrir `index_tickets` y `rag_answer`.
  - Ejecuta `rag_answer` con una pregunta y muestra la respuesta y las fuentes.

- `rag_minimal.py` (opcional)  
  Versión recortada sin base de datos ni dependencias extra:
  - Los tickets están en una lista en memoria.
  - El cálculo de similitud coseno es puramente en Python.
  - Útil para repasar el concepto de RAG sin entrar en detalles de SQLite ni OpenAI.

---

## 3. Paso 1 – Crear y poblar la base de datos

Lo primero es asegurarte de que existe `incidents.db` con algunos tickets de ejemplo.

Desde la raíz `mcp/`:

```bash
uv run python ej7_mcp_rag_db/seed_db.py
```

Este script:

- Crea el fichero `ej7_mcp_rag_db/incidents.db`.
- Ejecuta el esquema definido en `ej7_mcp_rag_db/schema.sql`.
- Inserta varios tickets de incidencias realistas (errores 500, timeouts, problemas de login, etc.).

Puedes ejecutar este comando tantas veces como quieras; si la base de datos ya existe, el script la recrea.

---

## 4. Paso 2 – Probar el RAG local (sin MCP)

Antes de añadir MCP, conviene que veas el pipeline RAG funcionando como un módulo “privado”.

Desde `mcp/`:

```bash
uv run python ej7_mcp_rag_db/rag_local.py
```

Esto ejecuta un pequeño flujo de ejemplo (según lo definido en el script), típicamente:

- Cargar los tickets desde `incidents.db`.
- Construir el índice de embeddings.
- Lanzar una o varias preguntas de prueba para ver cómo responde el sistema.

La idea es que entiendas bien este patrón:

1. Pregunta → embedding de la pregunta.
2. Búsqueda de los `k` tickets más similares.
3. Construcción del contexto (texto + metadatos).
4. Llamada al modelo (`MODEL`) con ese contexto.

Mensaje importante: el modelo **no ve toda la base de datos**, solo los tickets que selecciona el índice de embeddings.

---

## 5. Paso 3 – Exponer el RAG como servidor MCP

Una vez que has visto el RAG local, el siguiente paso es envolverlo en un servidor MCP.

Desde `mcp/`:

```bash
uv run python ej7_mcp_rag_db/rag_mcp_server.py
```

Este script:

- Crea un servidor MCP `incidents-rag` usando `FastMCP`.
- Usa transporte `stdio` (el servidor lee/escribe por la entrada/salida estándar).
- Registra dos tools:
  - `index_tickets()` → llama a `rag_local.build_index()` y devuelve cuántos tickets se indexan.
  - `rag_answer(question: str, k: int = 5)` → llama a `rag_local.answer()` y devuelve un dict con:
    - `answer`: respuesta en lenguaje natural.
    - `sources`: lista de tickets usados como contexto.

La lógica de RAG (embeddings + búsqueda + prompting) sigue viviendo en `rag_local.py`.  
`rag_mcp_server.py` solo añade la capa MCP para que cualquier host se pueda conectar.

---

## 6. Paso 4 – Consumir el servidor desde un host MCP

Tienes dos opciones para probar el servidor MCP:

### 6.1. Cliente de ejemplo incluido (`pseudo_client.py`)

Desde `mcp/`:

```bash
uv run python ej7_mcp_rag_db/pseudo_client.py
```

Este cliente:

- Lanza el servidor MCP `rag_mcp_server.py` por STDIO.
- Hace `list_tools()` para descubrir las tools disponibles.
- Llama a `index_tickets` y luego a `rag_answer` con una pregunta de prueba.
- Muestra por pantalla la respuesta y los tickets fuente.

Es útil para ver en “modo texto” qué está pasando sin depender aún de un editor o UI avanzada.

### 6.2. Usar un host MCP real (opcional)

Si trabajas con un host como Claude Desktop, ChatGPT con MCP, Open WebUI u otro:

1. Registra un servidor MCP local con el comando:

   - Comando: `python`
   - Args: `ej7_mcp_rag_db/rag_mcp_server.py`
   - Transporte: `stdio`

2. Abre un chat y escribe dudas de soporte tipo:

   - “He visto errores `database is locked` en la API de usuarios, ¿qué puedo revisar?”
   - “Tenemos timeouts en el panel de administración después de un despliegue, ¿alguna pista?”

El host verá las tools `index_tickets` y `rag_answer` y decidirá cuándo usarlas para mejorar la respuesta.
Además, gracias a FastMCP, también exponemos **resources** de solo lectura:

- `tickets/latest` → devuelve los últimos tickets insertados (sin pasar por el modelo).
- `tickets/{ticket_id}` → devuelve el detalle bruto de un ticket concreto.

Esto te permite ver la diferencia entre:

- **Tools (c_tools)** → ejecutan lógica activa (pipeline RAG, embeddings, llamada al modelo).
- **Resources (c_know)** → exponen la base de conocimiento tal cual, sin efectos secundarios, para que el host pueda inspeccionarla, cachearla o mostrarla directamente.

---

## 7. Memoria y feedback (c_mem)

Para conectar este ejercicio con la idea de **memoria persistente (c_mem)**, el servidor MCP expone
un pequeño almacén de feedback en `feedback.json` usando dos tools y un resource:

- Tool `save_feedback(question: str, answer: str, helpful: bool)`  
  Guarda una entrada de feedback con marca temporal, la pregunta original, la respuesta generada
  y si al usuario le ha resultado útil o no.

- Tool `list_feedback(limit: int = 10)`  
  Devuelve las últimas entradas de feedback guardadas (hasta `limit`).

- Resource `feedback/latest`  
  Recurso de solo lectura que expone las últimas entradas de feedback sin modificar el estado.

La idea didáctica es que veas cómo un servidor MCP puede actuar como **interfaz estándar hacia una memoria
externa** (en este caso un JSON muy simple, pero podría ser una base de datos real, un sistema de logs, etc.).

---

## 8. Ideas de mini‑ejercicio para practicar

Te propongo varias modificaciones para que toques código y veas el impacto:

- Añadir una columna `severity` a la tabla `tickets` (por ejemplo `low`, `medium`, `high`) en `schema.sql` y actualizar `seed_db.py` para rellenarla.  
  Después, modifica `rag_local.answer` para que los tickets con `severity=high` puntúen un poco más en el ranking.

- Cambiar el prompt de sistema dentro de `rag_local.py` para que el asistente:
  - Devuelva siempre al final un pequeño “runbook” con pasos numerados.
  - Marque explícitamente qué tickets ha usado como referencia.

- Crear una tool MCP adicional en `rag_mcp_server.py`, por ejemplo:
  - `get_ticket_by_id(id: int)` → devuelve el ticket crudo para debugging.

- Conectar este servidor RAG junto con el servidor OMDb del ejercicio 5 en el mismo host MCP y observar cómo el modelo decide a qué servidor hablar según la consulta.

Cada cambio que hagas, intenta probarlo siempre desde la raíz con `uv run …` y, si tienes tests para este ejercicio, ejecútalos antes de subir tu código a Git.

---

## Encaje en el esquema del curso (MCP)

En este ejercicio trabajas de forma bastante completa:

- **c_tools**: tools que implementan el pipeline RAG (`index_tickets`, `rag_answer`, tools de feedback).
- **c_know**: resources de solo lectura sobre la base de conocimiento (`tickets/latest`, `tickets/{ticket_id}`).
- **c_mem**: tools y resources para memoria persistente (`save_feedback`, `list_feedback`, `feedback/latest`).

Primitivos MCP/FastMCP que aparecen:

- Servidor MCP por STDIO (`FastMCP("incidents-rag")`).
- Tools MCP (`@mcp.tool()`) que encapsulan el pipeline RAG y la gestión de feedback.
- Resources MCP (`@mcp.resource(...)`) para exponer tickets y feedback como datos de solo lectura.
