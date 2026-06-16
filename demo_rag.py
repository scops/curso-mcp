# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "anthropic>=0.39.0",
#   "mysql-connector-python>=8.4.0",
#   "sentence-transformers>=2.7.0",
#   "numpy>=1.26.0",
#   "python-dotenv>=1.0.0",
# ]
# ///
"""
RAG mínimo sobre la base de datos Sakila (MySQL) usando Anthropic.
 
Pedagogía del flujo:
  1) INDEX:    Extraemos el DDL de cada tabla y lo embebemos como un
               chunk independiente.
  2) RETRIEVE: Para cada pregunta, embebemos la consulta y buscamos los
               TOP_K chunks más similares (cosine similarity).
  3) AUGMENT:  Inyectamos los DDL recuperados en el prompt.
  4) GENERATE: Claude traduce la pregunta a una query SQL válida.
  5) EXECUTE:  Ejecutamos la SQL contra MySQL (solo SELECT).
  6) ANSWER:   Devolvemos los resultados a Claude para que responda en
               lenguaje natural.
 
Limitaciones a discutir en clase (RAG vs MCP):
  - Recuperación one-shot: si las palabras de la pregunta no se
    parecen semánticamente al nombre/columnas de la tabla relevante,
    el retrieval falla y Claude no tiene cómo pedir más contexto.
  - Sin introspección: el modelo no descubre la BBDD, depende del
    pipeline. Con MCP podría llamar a list_tables → describe_table
    → execute_query iterativamente.
  - Sin acción: este script solo lee. Cualquier write requeriría
    rediseñar el pipeline. MCP modela acciones de forma natural.
  - Stale: si cambia el esquema, hay que re-indexar.
  - Sin composición: una pregunta que requiere dos pasos lógicos
    (subquery, agregación + filtro) puede caber en una SQL, pero si
    el resultado dependiera de una API externa, RAG no llega.
"""
 
import json
import os
import re
import sys
from textwrap import dedent
 
import mysql.connector
import numpy as np
from anthropic import Anthropic
from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer
 
# --------------------------------------------------------------------------- #
# Configuración (.env)                                                        #
# --------------------------------------------------------------------------- #
load_dotenv()
 
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
MYSQL_HOST        = os.getenv("SAKILA_HOST", "127.0.0.1")
MYSQL_PORT        = int(os.getenv("SAKILA_PORT", "3306"))
MYSQL_USER        = os.environ["SAKILA_USER"]
MYSQL_PASSWORD    = os.environ["SAKILA_PASSWORD"]
MYSQL_DB          = os.getenv("SAKILA_DB", "sakila")
 
EMBED_MODEL       = os.getenv("EMBED_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
TOP_K             = int(os.getenv("TOP_K", "5"))
CLAUDE_MODEL      = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6")
MAX_RESULT_ROWS   = int(os.getenv("MAX_RESULT_ROWS", "20"))
 
 
# --------------------------------------------------------------------------- #
# 1. INDEX — extraer y embeber el esquema                                     #
# --------------------------------------------------------------------------- #
def conectar_mysql():
    return mysql.connector.connect(
        host=MYSQL_HOST,
        port=MYSQL_PORT,
        user=MYSQL_USER,
        password=MYSQL_PASSWORD,
        database=MYSQL_DB,
    )
 
 
def extraer_chunks_esquema(conn) -> list[dict]:
    """Un chunk por tabla: {tabla, ddl, texto}.
 
    El campo `texto` es lo que se embebe; añadimos el nombre de la
    tabla y un encabezado en lenguaje natural para mejorar el match
    semántico (los nombres de columnas por sí solos no siempre lo dan).
    """
    cursor = conn.cursor()
    cursor.execute(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema = %s AND table_type = 'BASE TABLE' "
        "ORDER BY table_name",
        (MYSQL_DB,),
    )
    tablas = [fila[0] for fila in cursor.fetchall()]
 
    chunks: list[dict] = []
    for tabla in tablas:
        cursor.execute(f"SHOW CREATE TABLE `{tabla}`")
        ddl = cursor.fetchone()[1]
        texto_para_embedding = (
            f"Tabla `{tabla}` de la base de datos {MYSQL_DB}.\n\n"
            f"DDL:\n{ddl}"
        )
        chunks.append({"tabla": tabla, "ddl": ddl, "texto": texto_para_embedding})
    cursor.close()
    return chunks
 
 
# --------------------------------------------------------------------------- #
# 2. RETRIEVE — vector store mínimo en numpy                                  #
# --------------------------------------------------------------------------- #
class TiendaVectores:
    """Vector store en memoria (numpy + cosine similarity).
 
    Lo escribimos a mano a propósito: sin chromadb, sin faiss, sin
    qdrant. La clase entera son ~15 líneas y el alumno entiende
    exactamente qué pasa en cada paso del retrieval.
    """
 
    def __init__(self, modelo: SentenceTransformer):
        self.modelo = modelo
        self.docs: list[dict] = []
        self.matriz: np.ndarray | None = None
 
    def indexar(self, docs: list[dict]) -> None:
        textos = [doc["texto"] for doc in docs]
        # normalize_embeddings=True => norma 1 => cosine = producto escalar
        embeddings = self.modelo.encode(textos, normalize_embeddings=True)
        self.docs = docs
        self.matriz = np.asarray(embeddings)
 
    def buscar(self, consulta: str, k: int = TOP_K) -> list[tuple[dict, float]]:
        emb_consulta = self.modelo.encode([consulta], normalize_embeddings=True)[0]
        scores = self.matriz @ emb_consulta            # (N,) vector de similitudes
        indices = np.argsort(-scores)[:k]              # top-k descendente
        return [(self.docs[i], float(scores[i])) for i in indices]
 
 
# --------------------------------------------------------------------------- #
# 3+4. AUGMENT + GENERATE — Claude traduce a SQL                              #
# --------------------------------------------------------------------------- #
PROMPT_GENERACION_SQL = dedent("""
    Eres un asistente experto en MySQL 8. Traduce la pregunta del
    usuario a UNA query SQL válida.
 
    Reglas estrictas:
      - Solo SELECT. Nada de INSERT/UPDATE/DELETE/DDL.
      - Usa exclusivamente las tablas y columnas presentes en el
        contexto. Si el contexto es insuficiente para responder,
        contesta EXACTAMENTE: NO_SE_PUEDE
      - Devuelve SOLO la SQL. Sin explicación, sin markdown, sin
        punto y coma final.
 
    --- ESQUEMA RECUPERADO ---
    {contexto}
    --- FIN ESQUEMA ---
 
    Pregunta: {pregunta}
""").strip()
 
 
PROMPT_RESPUESTA_NL = dedent("""
    Explica al usuario el resultado de la consulta en español, de
    forma breve y clara. No repitas la SQL salvo que sea relevante.
 
    Pregunta original: {pregunta}
 
    SQL ejecutada:
    {sql}
 
    Filas devueltas (máximo {max_filas}):
    {filas}
""").strip()
 
 
def generar_sql(cliente: Anthropic, pregunta: str, contexto: str) -> str:
    mensaje = cliente.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=512,
        messages=[
            {
                "role": "user",
                "content": PROMPT_GENERACION_SQL.format(
                    contexto=contexto, pregunta=pregunta
                ),
            }
        ],
    )
    sql = mensaje.content[0].text.strip()
    # Limpieza defensiva: si Claude se nos despista y mete fences markdown
    sql = re.sub(r"^```(?:sql)?", "", sql, flags=re.MULTILINE)
    sql = re.sub(r"```$", "", sql, flags=re.MULTILINE)
    return sql.strip().rstrip(";")
 
 
def responder_lenguaje_natural(
    cliente: Anthropic, pregunta: str, sql: str, filas: list
) -> str:
    mensaje = cliente.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=512,
        messages=[
            {
                "role": "user",
                "content": PROMPT_RESPUESTA_NL.format(
                    pregunta=pregunta,
                    sql=sql,
                    max_filas=MAX_RESULT_ROWS,
                    filas=json.dumps(filas, default=str, ensure_ascii=False, indent=2),
                ),
            }
        ],
    )
    return mensaje.content[0].text.strip()
 
 
# --------------------------------------------------------------------------- #
# 5. EXECUTE — guardia de seguridad antes de tocar la BBDD                    #
# --------------------------------------------------------------------------- #
_PALABRAS_PROHIBIDAS = (
    "insert", "update", "delete", "drop", "alter", "create",
    "truncate", "grant", "revoke", "rename", "replace",
)
_REGEX_PROHIBIDAS = re.compile(
    r"\b(" + "|".join(_PALABRAS_PROHIBIDAS) + r")\b",
    re.IGNORECASE,
)
 
 
def es_select_seguro(sql: str) -> bool:
    """Defensa en profundidad: aunque el prompt diga 'solo SELECT',
    no confiamos en el LLM para autorizar nada destructivo.
 
    Usamos \\b (límites de palabra) y no substring matching: si no,
    columnas tan inocentes como `last_update` o `created_at` harían
    saltar la guardia porque contienen 'update' / 'create' como
    subcadena. Lección de clase: seguridad por substring = seguridad
    rota.
    """
    s = sql.strip().lower()
    if not s.startswith("select") and not s.startswith("with"):
        return False
    return _REGEX_PROHIBIDAS.search(s) is None
 
 
# --------------------------------------------------------------------------- #
# Bucle CLI                                                                   #
# --------------------------------------------------------------------------- #
def main() -> int:
    print("[+] Conectando a MySQL...")
    conn = conectar_mysql()
 
    print(f"[+] Cargando modelo de embeddings: {EMBED_MODEL}")
    modelo = SentenceTransformer(EMBED_MODEL)
 
    print("[+] Extrayendo esquema de Sakila...")
    chunks = extraer_chunks_esquema(conn)
    print(f"[+] {len(chunks)} tablas indexadas: "
          f"{', '.join(c['tabla'] for c in chunks)}")
 
    tienda = TiendaVectores(modelo)
    tienda.indexar(chunks)
 
    cliente = Anthropic(api_key=ANTHROPIC_API_KEY)
 
    print()
    print(f"RAG-Sakila listo (modelo Claude: {CLAUDE_MODEL}).")
    print("Escribe tu pregunta. Comandos: /quit, /retrieval (solo recupera, no genera).")
    print("-" * 70)
 
    while True:
        try:
            pregunta = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
 
        if not pregunta:
            continue
        if pregunta in ("/quit", "/exit", "salir"):
            break
 
        modo_solo_retrieval = pregunta.startswith("/retrieval ")
        if modo_solo_retrieval:
            pregunta = pregunta[len("/retrieval "):]
 
        # --- RETRIEVAL ---
        recuperados = tienda.buscar(pregunta, k=TOP_K)
        print(f"\n[retrieval] Top-{TOP_K} tablas:")
        for doc, score in recuperados:
            print(f"  {score:.3f}  {doc['tabla']}")
 
        if modo_solo_retrieval:
            continue
 
        contexto = "\n\n".join(doc["ddl"] for doc, _ in recuperados)
 
        # --- AUGMENT + GENERATE ---
        try:
            sql = generar_sql(cliente, pregunta, contexto)
        except Exception as exc:
            print(f"[!] Error llamando a Claude: {exc}")
            continue
 
        if sql.strip() == "NO_SE_PUEDE":
            print("\n[Claude] No tengo contexto suficiente con el retrieval actual.")
            print("         Prueba a reformular o subir TOP_K en .env.")
            continue
 
        if not es_select_seguro(sql):
            print(f"\n[!] SQL rechazado por la guardia (solo SELECT permitido):\n{sql}")
            continue
 
        print(f"\n[sql]\n{sql}")
 
        # --- EXECUTE ---
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute(sql)
            filas = cursor.fetchmany(MAX_RESULT_ROWS)
            cursor.close()
        except mysql.connector.Error as exc:
            print(f"[!] Error ejecutando SQL: {exc}")
            continue
 
        # --- ANSWER ---
        respuesta = responder_lenguaje_natural(cliente, pregunta, sql, filas)
        print(f"\n[Claude]\n{respuesta}")
 
    conn.close()
    print("Hasta luego.")
    return 0
 
 
if __name__ == "__main__":
    sys.exit(main())
 