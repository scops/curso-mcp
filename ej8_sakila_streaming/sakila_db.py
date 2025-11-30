from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Any, Dict, Iterable, List, Tuple

import mysql.connector
from dotenv import load_dotenv


load_dotenv()


def _get_mysql_config() -> Dict[str, Any]:
    """
    Lee configuración de conexión a la base de datos sakila
    desde variables de entorno.
    """
    host = os.getenv("SAKILA_HOST", "127.0.0.1")
    port = int(os.getenv("SAKILA_PORT", "3306"))
    user = os.getenv("SAKILA_USER")
    password = os.getenv("SAKILA_PASSWORD")
    database = os.getenv("SAKILA_DB", "sakila")

    if not user or not password:
        raise RuntimeError(
            "Faltan credenciales para la base de datos sakila. "
            "Define SAKILA_USER y SAKILA_PASSWORD en tu .env."
        )

    return {
        "host": host,
        "port": port,
        "user": user,
        "password": password,
        "database": database,
    }


@contextmanager
def get_connection():
    """
    Context manager sencillo para obtener una conexión a MySQL.
    """
    cfg = _get_mysql_config()
    conn = mysql.connector.connect(**cfg)
    try:
        yield conn
    finally:
        conn.close()


def fetch_all(query: str, params: Iterable[Any] | None = None) -> List[Tuple[Any, ...]]:
    """
    Ejecuta un SELECT y devuelve todas las filas.
    """
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(query, tuple(params or []))
        rows = list(cur.fetchall())
        cur.close()
    return rows


def execute_and_return_id(query: str, params: Iterable[Any]) -> int:
    """
    Ejecuta un INSERT y devuelve el último id generado.
    """
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(query, tuple(params))
        conn.commit()
        last_id = cur.lastrowid
        cur.close()
    return int(last_id)


