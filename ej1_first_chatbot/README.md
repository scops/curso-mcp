# First MCP Chatbot (Cliente + Servidor)

Este proyecto es un **ejemplo mínimo de MCP** (Model Context Protocol) pensado para un curso en español.  
La idea es que veas, de forma muy concreta, cómo se hablan:

- Un **cliente MCP** que usa Claude (Anthropic).
- Un **servidor MCP** que expone un par de tools muy sencillos.

Así puedes entender los fundamentos sin perderte en detalles avanzados.

---

## ¿Qué es MCP en este contexto?

MCP (Model Context Protocol) es un protocolo que permite que un **LLM** (como Claude) pueda:

- Descubrir qué herramientas (tools) tiene disponibles.
- Ver qué parámetros espera cada tool.
- Pedir al cliente que **llame** a esos tools cuando lo necesita.

En este ejemplo:

- El **servidor MCP** está en `first_mcp_server.py` y define los tools.
- El **cliente MCP** está en `first_mcp_client.py` y:
  - Se conecta al servidor por **STDIO**.
  - Pregunta qué tools hay.
  - Llama a Claude, pasándole esos tools.
  - Si Claude decide usar un tool, el cliente se encarga de ejecutarlo en el servidor y devolver el resultado al modelo.

---

## Arquitectura del ejemplo

### Servidor MCP: `first_mcp_server.py`

Usa `FastMCP` para levantar un servidor MCP muy pequeño:

- `echo(texto: str) -> str`  
  Devuelve exactamente el mismo texto.  
  Sirve para comprobar que el “cableado” MCP funciona.

- `sumar(a: float, b: float) -> float`  
  Suma dos números, **pero está mal a propósito**: hace `a + b * 0.5`.  
  Esto es muy útil en clase para demostrar que:
  - El que realmente hace el cálculo es el **servidor MCP** (tu código).
  - El modelo solo utiliza el resultado que le llega; si el servidor se equivoca, el modelo “hereda” el error.

- `chiste_de_padre() -> str`  
  Devuelve un chiste de padre aleatorio de una lista en Python.  
  Sirve para tener un ejemplo simpático de tool puramente “lógico” (no llama a APIs externas).

El servidor se ejecuta con transporte `stdio`, que es la forma estándar de integrarse con clientes MCP:

- El cliente lanza el script del servidor.
- Se comunican por la entrada/salida estándar (sin HTTP, sockets, etc.).

### Cliente MCP: `first_mcp_client.py`

Hace tres cosas principales:

1. **Conexión al servidor MCP**
   - Lanza el servidor (`first_mcp_server.py`) usando `StdioServerParameters`.
   - Crea una `ClientSession` MCP.
   - Llama a `list_tools()` para descubrir los tools disponibles y los muestra por pantalla.

2. **Uso de Claude con tools MCP**
   - Lee tu mensaje desde la terminal.
   - Construye un mensaje para Claude (`Anthropic`) incluyendo la lista de tools.
   - Claude puede:
     - Responder con texto normal.
     - Pedir que se ejecute un `tool_use`.
   - Si Claude pide un tool, el cliente:
     - Llama a `session.call_tool(...)` en el servidor.
     - Añade el resultado como `tool_result` al historial de mensajes.
     - Vuelve a llamar a Claude para que genere una respuesta final usando ese resultado.

3. **Bucle de chat**
   - Muestra un prompt tipo `Tú:`.
   - Envía la consulta a `process_query`.
   - Imprime la respuesta del bot.
   - Puedes salir escribiendo `salir`, `exit` o `quit`.

---

## Requisitos previos

- Python 3.10+ (recomendado).
- Una cuenta y API key de Anthropic.

Paquetes Python típicos que necesitarás (pueden cambiar según la versión del curso):

- `mcp` y/o `mcp[client]`, `mcp[server]` (o el paquete donde venga `FastMCP`).
- `anthropic`
- `python-dotenv`

Ejemplo de instalación (ajusta según tus necesidades):

```bash
pip install mcp anthropic python-dotenv
```

---

## Configuración de variables de entorno

Usamos un archivo `.env` compartido para no escribir la API key directamente en el código.

La idea del curso es tener **un único `.env` en el directorio `mcp`**, que comparten todos los ejercicios:

- Directorio raíz de ejercicios: `mcp/`
  - Archivo de configuración común: `mcp/.env`
  - Ejemplos/ejercicios: `mcp/ej1_first_chatbot`, `mcp/ej2_4_chatbot_arxiv`, etc.

En ese directorio `mcp` crea un fichero `.env` con al menos:

```env
ANTHROPIC_API_KEY=tu_api_key_de_anthropic
MODEL=claude-haiku-4-5-20251001
```

Notas:

- `ANTHROPIC_API_KEY` la lee internamente el SDK de `anthropic`.
- `MODEL` la usamos en `first_mcp_client.py`.  
  Si no está definida, el cliente lanza un error claro indicando cómo configurarla.

---

## Cómo ejecutar el ejemplo

Recomendación del curso: usar siempre uv desde la raíz `mcp/`, para aprovechar el entorno común `.venv`.

Estando en la carpeta `mcp/`:

```bash
uv run python ej1_first_chatbot/first_mcp_client.py ej1_first_chatbot/first_mcp_server.py
```

El flujo será:

1. El cliente lanza el servidor MCP (`first_mcp_server.py`) usando el mismo intérprete de Python.
2. Se establece una sesión MCP por STDIO.
3. El cliente lista los tools disponibles y los muestra:
   - `echo`
   - `sumar`
   - `chiste_de_padre`
4. Entra en el bucle de chat. Verás algo tipo:

```text
Cliente MCP iniciado.
Escribe tu consulta o 'salir' para terminar.

Tú:
```

Prueba cosas como:

- `Tú: Usa el tool sumar con 2 y 3`  
- `Tú: Repite este texto con el tool echo: Hola MCP`
 - `Tú: Cuéntame un chiste de padre usando un tool`

Claude decidirá si usar un tool o responder directamente.

---

## Cómo ejecutar los tests

Para comprobar rápidamente que el ejercicio es “entregable” y que el servidor MCP funciona como esperamos (incluida la suma rota a propósito), puedes ejecutar los tests desde la raíz `mcp/` usando uv:

```bash
uv run python -m unittest ej1_first_chatbot.tests.test_server_tools
```

Los tests verifican que:

- `echo` devuelve exactamente el texto de entrada.
- `sumar` aplica la lógica `a + b * 0.5` (error intencionado).
- `chiste_de_padre` siempre devuelve uno de los chistes definidos en la lista de Python.

---

## Buenas prácticas aplicadas en este ejemplo

Aunque el código es muy pequeño, ya se introducen algunas buenas prácticas:

- **Separar cliente y servidor MCP**  
  Dos scripts: uno para exponer tools, otro para consumirlos.

- **Uso de tipos y docstrings**  
  Las funciones de tools tienen anotaciones de tipos y pequeñas explicaciones en español.

- **Uso de `sys.executable` en el cliente**  
  En lugar de llamar a `"python"` a secas, usamos el mismo intérprete con el que se está ejecutando el cliente.  
  Esto evita problemas si tienes varias versiones de Python instaladas.

- **Validación de la configuración (`MODEL`) al inicio**  
  Si no has definido la variable de entorno `MODEL`, el programa te avisa con un mensaje claro en lugar de fallar de forma confusa en tiempo de ejecución.

- **Funciones sencillas y foco en el flujo**  
  No se añaden patrones avanzados ni abstracciones innecesarias: la idea es que entiendas el flujo MCP de principio a fin.

---

## ¿Cómo seguir aprendiendo a partir de aquí?

Ideas de ejercicios para que practiques:

- Añadir un nuevo tool al servidor:
  - Por ejemplo, `multiplicar(a: float, b: float)`.
  - Volver a ejecutar el cliente y comprobar que aparece en la lista de tools.
- Crear un tool que trabaje con texto:
  - Ej: que reciba un párrafo y devuelva el número de palabras.
- Pedir a Claude que combine varios tools:
  - Por ejemplo, que primero llame a `echo` y luego use ese resultado para otra operación.

Recuerda: lo importante en este ejemplo no es hacer algo “útil” para producción, sino **ver claramente cómo un LLM puede descubrir y usar tools reales a través de MCP**.

---

## Ejercicio guiado: crea tu propio tool

En este primer ejercicio queremos que tú también escribas **al menos un tool propio** para que practiques cómo se declara y cómo se integra en el flujo MCP.

La idea es que añadas un tool sencillo pero útil, por ejemplo:

- `contar_palabras(texto: str) -> int`  
  Devuelve cuántas palabras tiene el texto que le pases.

### 1. Localiza el punto del código donde van los tools

Abre `first_mcp_server.py` y fíjate en las funciones decoradas con `@mcp.tool()`:

- `echo(...)`
- `sumar(...)`
- `chiste_de_padre(...)`

Justo debajo de estos tools verás un **comentario en mayúsculas** que dice que ahí va tu ejercicio.  
Ese es el sitio donde debes escribir tu propio tool.

### 2. Declara tu nuevo tool

Siguiendo el mismo patrón, crea una nueva función async con anotaciones de tipo:

- Usa el decorador `@mcp.tool()` encima de la función.
- Ponle un nombre claro al tool, por ejemplo `contar_palabras`.
- Declara los parámetros y el tipo de retorno, por ejemplo:
  - `texto: str` como entrada.
  - `int` como salida (el número de palabras).
- Añade un docstring corto en español explicando qué hace y para qué sirve.

No copies/pegues sin más: intenta entender cómo están definidas `echo`, `sumar` y `chiste_de_padre` y replica la misma estructura.

### 3. Implementa la lógica

Dentro de tu función, implementa la lógica que quieras.  
Para `contar_palabras`, una versión muy sencilla podría ser:

- Limpiar espacios en blanco al principio y al final.
- Separar el texto por espacios usando `split()`.
- Devolver la longitud de la lista resultante.

No hace falta que sea perfecto; lo importante es que veas cómo el servidor MCP ejecuta **tu código** cuando Claude decide llamar a ese tool.

### 4. Prueba tu tool con el cliente MCP

Vuelve a lanzar el cliente desde la raíz `mcp/`:

```bash
uv run python ej1_first_chatbot/first_mcp_client.py ej1_first_chatbot/first_mcp_server.py
```

Comprueba que:

- En el listado inicial de tools aparece tu nuevo tool (por ejemplo, `contar_palabras`).
- Puedes pedirle a Claude que lo use, por ejemplo:

  ```text
  Tú: Usa el tool contar_palabras con este texto: "MCP me ayuda a conectar un LLM con tools"
  ```

Fíjate en cómo el cliente:

- Le pasa a Claude la lista de tools disponibles (incluyendo el tuyo).
- Recibe de vuelta un `tool_use` si Claude decide usarlo.
- Llama al servidor MCP, ejecuta **tu función** y devuelve el resultado al modelo.

Así verás de principio a fin cómo se conecta una idea tuya (tu tool) con el LLM a través de MCP.

---

## Encaje en el esquema del curso (MCP)

En este ejercicio trabajas sobre todo:

- **c_tools**: definición de tools MCP sencillos (`echo`, `sumar`, `chiste_de_padre`, tu propio tool).
- **c_state**: separación clara entre cliente y servidor MCP (cada uno con su propio proceso).

Primitivos MCP/FastMCP que aparecen:

- Servidor MCP por STDIO (`FastMCP(...).run(transport="stdio")`).
- Cliente MCP que lanza el servidor como subproceso y usa `list_tools()` y `call_tool()` para orquestar las llamadas.
