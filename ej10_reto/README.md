# Ejercicio 10 – Reto libre MCP con API pública

Este ejercicio está pensado como **reto opcional** para quienes ya se sienten cómodos con Python y con los
ejercicios anteriores. La idea es que tú elijas el dominio y combines todas las piezas de MCP que hemos visto.

---

## 1. Elige una API que te motive

Usa el listado de APIs públicas de:

- https://github.com/public-apis/public-apis

Elige un tema que te apetezca de verdad:

- Música, películas, series.
- Deportes, juegos, ajedrez.
- Datos abiertos (transportes, clima, ciencia).
- Cualquier otra cosa que te interese.

Piensa en **qué tipo de preguntas** querrías poder hacer con MCP sobre esa API.

---

## 2. Objetivo del reto

Diseñar un **servidor MCP propio** para esa API, con la complejidad que tú quieras. La versión básica puede ser:

- Un servidor `FastMCP` con:
  - 1–2 tools de búsqueda/listado.
  - 1–2 tools de detalle (por id, por nombre, etc.).

A partir de ahí, puedes subir el nivel combinando ideas del curso:

- **Tools (c_tools)**  
  - Búsqueda (`search_*`, `list_*`) y detalle (`get_*_detail`).  
  - Algún tool más “semántico” que resuma o compare resultados.

- **Resources (c_know)**  
  - Resources de solo lectura (por ejemplo, `stats/latest`, `config`, `last_search`).

- **Prompts (c_instr)**  
  - Prompts MCP para roles específicos:
    - “Recomendador de X”.
    - “Analista técnico de Y”.

- **Elicitation**  
  - Tools que pidan datos al usuario vía `ctx.elicit(...)` antes de llamar a la API.

- **RAG (opcional)**  
  - Pequeño índice local (SQLite, JSON o memoria) con datos de tu dominio, expuesto como servidor MCP.

- **Memoria (c_mem)**  
  - Guardar feedback de recomendaciones o consultas y exponerlo como tool/resource.

No hace falta incluirlo TODO; la idea es que elijas qué piezas quieres practicar.

---

## 3. Requisitos mínimos sugeridos

Para que el reto sea “entregable” en el contexto del curso, te propongo estos mínimos:

1. Un servidor MCP con `FastMCP` (STDIO o HTTP).
2. Al menos **dos tools** bien documentadas:
   - Una de búsqueda o listado.
   - Una de detalle/acción.
3. Un README dentro de la carpeta de tu reto que explique:
   - API elegida y por qué.
   - Tools definidas y ejemplos de uso.
   - Cómo levantar el servidor y, si quieres, cómo probarlo con MCP Inspector.

Todo lo demás (resources, prompts, elicitation, RAG, memoria) es opcional, pero muy recomendable si te da tiempo.

---

## 4. Pista de estructura

Dentro de `ej10_reto/` puedes crear tu propia subcarpeta, por ejemplo:

- `ej10_reto/mcp_weather/`
- `ej10_reto/mcp_music/`
- `ej10_reto/mcp_chess/`

Y dentro:

- `server.py` (servidor MCP principal).
- `client_demo.py` (si quieres un pequeño cliente de ejemplo).
- `README.md` de tu reto.

Reutiliza patrones de los ejercicios:

- Ej5–6 para envolver APIs HTTP.
- Ej7 para ideas de RAG/resources/memoria.
- Ej2–4 para prompts y elicitation.

---

## 5. Cómo saber si vas por buen camino

Comprueba estos puntos:

- Tu servidor arranca sin errores (STDIO o HTTP).
- MCP Inspector o un host compatible puede:
  - Hacer `tools/list` y ver tus tools.
  - Hacer `tools/call` y obtener respuestas coherentes.
- Si implementas resources:
  - `resources/list` y `resources/read` funcionan.
- Si implementas elicitation:
  - Ves el formulario en el host y las distintas ramas (`ok`, `cancelled`, etc.) funcionan.

Con que llegues a una parte de esto ya habrás dado un salto importante; el objetivo del reto es que puedas
aplicar MCP a un dominio que te guste y solidificar lo aprendido en el curso.

