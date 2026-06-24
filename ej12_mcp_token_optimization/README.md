# ej12 · Optimización de tokens en MCP (vanilla vs naive vs optimizado)

Ejercicio **extra**. Responde a una pregunta incómoda que conviene hacerse en
clase: **¿MCP ahorra tokens?**

La respuesta honesta es: **MCP por sí solo NO ahorra tokens; el patrón ingenuo
de MCP gasta MÁS.** El ahorro aparece cuando aplicas técnicas concretas, y se
nota sobre todo **a escala** (muchas tools / varios servidores). Este ejercicio
lo mide en vivo con Langfuse en lugar de afirmarlo de memoria.

> Si vienes de `ej2_4_chatbot_arxiv`: allí comparabas "tools locales" vs "MCP"
> con 2 herramientas y la diferencia de tokens era ruido. Aquí montamos un
> servidor con **14 tools** (como un servidor MCP real) para que el coste de las
> definiciones de tools sea visible y medible.

---

## 1. El modelo mental: las definiciones de tools SON tokens

Cuando pasas `tools=[...]` al modelo, el nombre + la descripción + el JSON
Schema de **cada** tool viajan en el prompt. Y se reenvían **en cada turno** de
la conversación (cada `tool_use` → `tool_result` es un turno nuevo con todo el
contexto). De forma aproximada:

```
coste_input  ≈  (nº de tools cargadas) × (tamaño medio del schema) × (nº de turnos)
```

- En **vanilla** defines a mano solo las 2 tools que necesitas → coste mínimo.
- En **MCP naive** haces `list_tools()` y vuelcas las **14** → pagas 12 schemas
  que el modelo no va a usar, en todos los turnos.
- La **optimización** consiste en no cargar lo que no hace falta.

---

## 2. Las tres estrategias que mide el benchmark

| Estrategia | Tools enviadas al modelo | Ejecución |
| --- | --- | --- |
| `vanilla` | 2, escritas a mano | funciones Python locales |
| `mcp_naive` | **14** (catálogo completo vía `list_tools()`) | servidor MCP |
| `mcp_optimized` | **3**, filtradas por relevancia a la consulta | servidor MCP |

La única variable que cambia entre `mcp_naive` y `mcp_optimized` es **cuántas
definiciones de tools se envían**. Eso aísla la lección.

`mcp_optimized` usa *tool retrieval*: el cliente puntúa cada tool del catálogo
por solapamiento con la consulta y envía solo las `k=3` mejores
(`select_relevant_tools` en `benchmark_token_optimization.py`). En producción
ese filtro sería recuperación semántica con embeddings, pero el efecto sobre los
tokens es el mismo.

> Datos sintéticos a propósito: las tools devuelven resultados fijos, sin red.
> Así la medición de tokens es reproducible y no depende de arXiv.

---

## 3. Cómo ejecutarlo

### 3.1. (Opcional) Levantar Langfuse para verlo en la UI

Langfuse v3 necesita varios servicios (Postgres, ClickHouse, Redis, MinIO) — por
eso es un `docker-compose`, no un `Dockerfile`. Desde esta carpeta:

```bash
docker compose -f docker-compose.langfuse.yml --env-file ../.env up -d
```

- UI: http://localhost:3001 · login `admin@curso.local` / `changeme123`
  (puerto 3001 porque tienes otro servicio en el 3000; debe coincidir con
  `LANGFUSE_HOST` en `mcp/.env`)
- Las claves de proyecto se toman de `mcp/.env` (`LANGFUSE_PUBLIC_KEY` /
  `LANGFUSE_SECRET_KEY`). **Arranca siempre con `--env-file ../.env`**: los
  valores por defecto del compose son placeholders.
- Espera 2-3 min al primer arranque (migraciones de ClickHouse). Parar:
  `docker compose -f docker-compose.langfuse.yml down` (añade `-v` para borrar datos).

> A diferencia del compose oficial, los servicios de datos no publican puertos
> en el host, para no chocar con un Postgres/Redis que ya tengas corriendo.

### 3.2. Correr el benchmark

Desde la raíz del curso `mcp/`:

```bash
uv run python ej12_mcp_token_optimization/benchmark_token_optimization.py
```

Imprime una tabla con los tokens reales (campo `usage` de la API). **No necesita
Langfuse**: si no hay claves o el stack está caído, el benchmark funciona igual y
solo se salta el envío de trazas. Si Langfuse está activo, además verás cada
ejecución en **Tracing → Traces**, filtrable por el tag de estrategia
(`vanilla`, `mcp_naive`, `mcp_optimized`) o por `metadata.tool_mode`.

---

## 4. Resultados medidos

<!-- RESULTS:START -->
Ejecución de ejemplo con `claude-haiku-4-5`, 2 consultas, suma de tokens:

| estrategia | tools enviadas | input | output | total | vs vanilla |
| --- | ---: | ---: | ---: | ---: | ---: |
| `vanilla` | 2 | 3.193 | 303 | 3.496 | — |
| `mcp_naive` | 14 | 10.481 | 364 | 10.845 | **+228% input** |
| `mcp_optimized` | 3 | 4.875 | 387 | 5.262 | +53% input |

- **MCP naive cuesta 3,3× los input tokens de vanilla** para hacer exactamente
  lo mismo: el modelo recibe 14 definiciones de tools cuando solo usa 1.
- **El filtrado por relevancia recorta el 53,5% del sobrecoste** de naive
  (de 10.481 → 4.875 input tokens) enviando solo 3 tools en vez de 14.
- El output apenas varía: el coste está en el **input**, porque las
  definiciones de tools se reenvían en cada turno.
- En la 1ª llamada de cada consulta se ve aún más claro: ~715 (vanilla) vs
  ~2.460 (naive) vs ~1.060 (optimizado) input tokens — esa diferencia es,
  casi toda, schemas de tools.

> Números orientativos (un modelo y dos consultas). Lo relevante es el **patrón**,
> no las cifras exactas. Reprodúcelo tú: los verás en Langfuse filtrando por el
> tag de cada estrategia.
<!-- RESULTS:END -->

La forma esperada del resultado: `mcp_naive` muy por encima en input tokens;
`mcp_optimized` cae a un nivel parecido a `vanilla`. El delta naive→optimizado es
exactamente el coste de los ~11 schemas de tools irrelevantes, multiplicado por
los turnos.

---

## 5. Dónde se gana de verdad (las optimizaciones, en orden)

1. **No cargar tools irrelevantes (tool retrieval / progressive disclosure).**
   Es lo que hace `mcp_optimized`. En lugar de volcar todo el catálogo, el host
   selecciona (por relevancia, por embeddings, o cargando schemas "bajo demanda")
   solo lo que la tarea necesita. **Cuantas más tools tengas, más ahorras** — con
   2 tools no compensa; con 100 tools de 5 servidores, es la diferencia entre un
   prompt usable y uno saturado.

2. **Descripciones y schemas concisos.** Cada palabra de la descripción y cada
   propiedad del schema es input que se reenvía en cada turno. Descripciones
   cortas y schemas mínimos recortan el coste base de todas las estrategias.

3. **Code execution con MCP (el nivel avanzado).** En lugar de exponer cada tool
   al modelo y pasar cada resultado intermedio por el contexto, el modelo escribe
   código que llama a las tools MCP mediante una API; los resultados grandes se
   procesan en el entorno de ejecución y **solo lo relevante vuelve al contexto**.
   Ahí es donde los ahorros pasan de ~decenas de % a ~90%+ en flujos con muchos
   pasos y resultados voluminosos. Es un patrón, no algo que MCP haga solo.

### La conclusión para clase

MCP no es una técnica de ahorro de tokens; es un **protocolo de
interoperabilidad** (descubrimiento dinámico, desacoplar cliente/servidor,
reutilizar tools entre hosts). El coste en tokens depende de **cómo** el host
carga las tools:

- Hazlo ingenuamente (volcar todo) y MCP cuesta **más** que tools a mano.
- Hazlo bien (cargar lo justo / code execution) y MCP escala a decenas de
  servidores sin reventar el contexto, algo que con tools cableadas a mano no
  es mantenible.

---

## 6. Referencias

- Anthropic — *Code execution with MCP: building more efficient agents*
  (nov-2025): el caso de los tokens y el patrón de ejecución por código.
- `arxiv_mcp_server.py` de `ej2_4_chatbot_arxiv`: el servidor MCP "pequeño" del
  que parte este ejercicio.
