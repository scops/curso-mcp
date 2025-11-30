# Chatbot arXiv (Streamlit + Anthropic)

Este ejercicio construye un **chatbot que consulta arXiv** usando:

- Una interfaz web sencilla con **Streamlit**.
- El SDK de **Anthropic**.
- Unas cuantas **tools locales en Python** (por ejemplo, búsqueda de artículos, extracción de info).

Todavía **no hay MCP**: es el puente natural entre “LLM + tools locales” y “LLM + MCP”.

---

## 1. Requisitos previos

Todo el curso comparte:

- Un solo entorno gestionado con **uv** en la carpeta raíz `mcp/`.
- Un archivo de configuración común `mcp/.env` con tu API key de Anthropic y el modelo.

Si aún no lo has hecho, revisa `mcp/README.md` y sigue:

1. Instalar `uv` (vía Astral).
2. Desde `mcp/`, ejecutar `uv sync`.
3. Crear y rellenar `mcp/.env` con:

   ```env
   ANTHROPIC_API_KEY=tu_api_key_de_anthropic
   MODEL=claude-haiku-4-5-20251001
   ```

---

## 2. Instalar dependencias (una sola vez)

Desde la carpeta raíz del curso `mcp/`:

```bash
uv sync
```

Esto creará el entorno `.venv` común e instalará las dependencias declaradas en `mcp/pyproject.toml` (incluyendo `streamlit`, `arxiv`, `anthropic`, `python-dotenv`).

---

## 3. Ejecutar la app de Streamlit (sin MCP)

Lo más sencillo es ejecutar siempre desde `mcp/` usando uv.

### Opción A – uv run (recomendada)

Desde `mcp/`:

```bash
uv run streamlit run ej2_4_chatbot_arxiv/app.py
```

### Opción B – uvx (avanzada)

Solo recomiendo esta opción si ya te manejas bien con entornos.  
Aquí `uvx` instala las dependencias necesarias explícitamente:

```bash
uvx --with anthropic --with python-dotenv --with arxiv streamlit run ej2_4_chatbot_arxiv/app.py
```

En ambos casos, se abrirá la aplicación en:

- `http://localhost:8501`

---

## 4. Versión con MCP: `claude_mcp_client.py`

Una vez que entiendas `app.py`, puedes abrir la versión con MCP:

```bash
uv run streamlit run ej2_4_chatbot_arxiv/claude_mcp_client.py
```

No necesitas lanzar el servidor aparte: `app_con_mcp.py` arranca internamente
`arxiv_mcp_server.py` como proceso MCP y habla con él por STDIO.

### ¿Qué cambia respecto a `app.py`?

- **Antes (app.py, sin MCP):**
  - `app.py` importa directamente `search_papers` y `extract_info` de `tools_arxiv.py`.
  - Define a mano la lista `TOOLS` con el JSON Schema de cada herramienta.
  - Cuando Claude manda un `tool_use`, el código llama directamente a las funciones Python locales.

- **Ahora (`claude_mcp_client.py`, con MCP):**
  - Las funciones de herramientas se exponen en `arxiv_mcp_server.py` como tools MCP usando `FastMCP`.
  - `claude_mcp_client.py` se comporta como **cliente MCP**:
    - Lanza `arxiv_mcp_server.py` como servidor MCP.
    - Llama a `list_tools()` para descubrir qué tools hay y qué esquemas de entrada tienen.
    - Cuando Claude manda un `tool_use`, le pide al servidor MCP que ejecute el tool (no llama a funciones locales).

### ¿Qué gano con FastMCP si ya funcionaba la versión sin MCP?

Este es justo el objetivo didáctico del ejercicio:

- **Separación clara de responsabilidades**  
  - El servidor MCP (`arxiv_mcp_server.py`) se encarga de la **lógica de negocio** (cómo se busca en arXiv, cómo se lee el índice, etc.).
  - El cliente (esta app, un editor de código compatible con MCP, otra herramienta) solo sabe:
    - Qué tools hay.
    - Qué parámetros aceptan.
    - Cómo pedir que se ejecuten.

- **Reutilización de tools**  
  - Las mismas tools (search/extract) pueden ser usadas:
    - Desde esta app de Streamlit.
    - Desde un editor que hable MCP.
    - Desde otros scripts/servicios que actúen como clientes MCP.
  - No duplicas la lógica ni el JSON Schema de las herramientas en cada cliente.

- **Descubrimiento dinámico**  
  - En `app.py`, si cambias la signatura de una función tienes que acordarte de actualizar a mano la lista `TOOLS`.
  - Con MCP, el cliente llama a `list_tools()` y descubre:
    - Nombre.
    - Descripción.
    - Esquema de entrada (JSON Schema).
  - Esto hace que la integración sea mucho más robusta a cambios.

En resumen: la versión sin MCP te enseña el patrón básico “LLM + tools locales”, y la versión con MCP te muestra cómo **convertir esas mismas tools en un servicio estándar** al que se pueden conectar muchas aplicaciones distintas.

### 4.1. Prompts MCP e instrucciones de sistema

Además de las tools, en `arxiv_mcp_server.py` usamos los **prompts** de FastMCP para exponer
plantillas reutilizables que representan “modos de uso” del servidor:

- El servidor tiene unas **instrucciones generales** (`mcp.instructions`) que describen su rol:
  - "Eres un asistente experto en buscar y leer artículos científicos en arxiv.org…".
- También define prompts nombrados con `@mcp.prompt(...)`, por ejemplo:
  - `Búsqueda general en arXiv` → plantilla para buscar papers sobre un tema y devolver una lista breve en español.
  - `Análisis detallado de un paper` → plantilla para analizar a fondo un único paper a partir de su `arxiv_id`.

> Fíjate que aquí MCP no solo estandariza **c_tools** (tools ejecutables), sino también **c_instr**:
> instrucciones y plantillas de sistema que pueden ser compartidas por distintos clientes sin
> duplicar prompts en cada app.

Más adelante puedes jugar a modificar estas plantillas para cambiar el estilo de las respuestas
(más técnico, más divulgativo, solo bullets, etc.) sin tocar el cliente.

### 4.2. Elicitations: el servidor pide datos al usuario

En la versión con MCP también se introduce un ejemplo de **elicitation** en `arxiv_mcp_server.py`:

- Tool `analyze_paper_with_confirmation(ctx: Context)`:
  - No recibe argumentos normales; en su lugar, usa `ctx.elicit(...)` para pedir al usuario:
    - qué `paper_id` (arxiv_id) quiere analizar,
    - y si confirma que quiere lanzar el análisis detallado.
  - Según lo que el usuario haga en el host (rellenar/aceptar, declinar o cancelar), la tool devuelve:
    - `status="ok"` con el análisis (`extract_info`) del paper elegido, o
    - `status="cancelled"` con una razón (`user_did_not_confirm`, `user_declined_elicitation`, `user_cancelled_operation`).

¿Para qué sirve didácticamente?

- Ves el patrón **“el servidor MCP también puede iniciar la interacción”**:
  - tools normales → el LLM decide cómo llamar al servidor,
  - elicitation → es el servidor el que pide información al usuario a través del host.
- En tools como Inspector o Claude Desktop verás aparecer un pequeño formulario cuando se llama a esta tool, lo que ayuda a entender mejor la parte de `elicitation` de la spec MCP.

---

## 5. ¿Qué hace este ejercicio? (visión general)

A nivel conceptual:

- Muestra una interfaz web donde puedes:
  - Escribir una consulta (por ejemplo: “artículos recientes sobre transformers para visión”).
  - Ver cómo el sistema llama a tools que interactúan con **arXiv**.
- Usa **Anthropic Messages** con tools:
  - Le pasas a Claude una lista de tools disponibles (definidas en `tools_arxiv.py` o expuestas por MCP).
  - El modelo decide cuándo usarlas para buscar o procesar artículos.
- Incluye un pequeño ejemplo de **introspección del servidor MCP**:
  - Tools como `server_info` o `who_am_i` muestran nombre del servidor, nivel de log, transporte, etc.
  - Esto refuerza la idea de c_state: el servidor tiene identidad y configuración propias.

---

## 6. Patrón “LLM + tools locales”


Este ejercicio (en sus dos variantes) es ideal para remarcar:

- Aquí **todavía no usamos MCP**.
- Las herramientas son **funciones Python normales**, por ejemplo:
  - `search_papers(...)` – busca artículos en arXiv.
  - `extract_info(...)` – extrae datos relevantes del resultado.
- Al modelo se le pasa algo como:

  - `tools = [...]` con sus **JSON Schemas** (nombres, parámetros, tipos).

El flujo típico es:

1. El modelo responde con un `tool_use` (quiere llamar a un tool).
2. El código de la app:
   - Lee ese `tool_use`.
   - Llama a la función Python correspondiente (local).
   - Obtiene un resultado.
3. Luego el código devuelve un `tool_result` al modelo.
4. El modelo genera una respuesta final al usuario usando ese resultado.

Este patrón deja muy claro que:

- El LLM **no sabe programar** directamente contra arXiv.
- Lo que hace es **pedir** usar ciertas tools.
- Nuestro código orquesta todo: decide cómo implementar esas tools y cómo devolver los resultados al modelo.

---

## 7. Relación con MCP (siguiente paso del curso)

Este ejercicio es el puente perfecto para introducir MCP en la siguiente lección:

- Ahora:
  - El modelo llama a **funciones Python locales** dentro de este mismo proceso (`tools_arxiv.py`).
- Con MCP:
  - En lugar de hablar con funciones directas, el modelo hablará con un **servidor MCP** que exporta las mismas tools.
  - El cliente (por ejemplo, un editor o una app) se conectará al servidor MCP por STDIO o red.

Idea de ejercicio para la siguiente clase:

- Tomar este código de `tools_arxiv.py`.
- Convertir esas funciones en **tools expuestos por un servidor MCP**.
- Hacer que un cliente MCP (similar al de `ej1_first_chatbot`) pueda:
  - Descubrir esos tools.
  - Recibir peticiones del modelo para usarlos.

De esta forma, vas viendo paso a paso:

1. LLM + tools locales (este ejercicio).
2. LLM + tools remotos vía MCP (siguiente ejercicio).

---

## 8. Tests para comprobar que el ejercicio es entregable

Opción global (recomendada): desde la raíz `mcp/`:

```bash
uv run python -m unittest
```

Esto ejecutará los tests de **todos** los ejercicios (por ahora: `ej1_first_chatbot` y `ej2_4_chatbot_arxiv`).

Si solo quieres los tests de este ejercicio:

```bash
uv run python -m unittest ej2_4_chatbot_arxiv.tests.test_tools_arxiv ej2_4_chatbot_arxiv.tests.test_arxiv_mcp_server
```

Los tests de este ejercicio comprueban que:

- Las funciones base de `tools_arxiv.py` se comportan de forma estable en los casos básicos (por ejemplo, error amigable cuando no hay índice local).
- El servidor MCP `arxiv_mcp_server.py` llama correctamente a las funciones subyacentes y devuelve estructuras de datos coherentes, sin depender de llamadas reales a la API de arXiv.

---

## Encaje en el esquema del curso (MCP)

En estos ejercicios de arXiv trabajas principalmente:

- **c_tools**: tools para búsqueda y extracción de información en arXiv (`search_papers`, `extract_info`, y sus variantes MCP).
- **c_instr**: instrucciones de sistema y prompts MCP (`mcp.instructions`, `Búsqueda general en arXiv`, `Análisis detallado de un paper`).
- **c_state**: introspección básica del servidor (`server_info`, `who_am_i`) para ver su configuración.

Primitivos MCP/FastMCP que aparecen:

- Servidor MCP por STDIO (`FastMCP("arxiv-tools", ...)`).
- Tools MCP (`@mcp.tool()`).
- Prompts MCP (`@mcp.prompt(...)`) y uso de `session.get_prompt(...)` desde el cliente.
- Cliente MCP (`ClientSession`) que usa `list_tools()` y `call_tool()` para orquestar las llamadas desde Streamlit.
