from __future__ import annotations

import sqlite3
from pathlib import Path


BASE_DIR = Path(__file__).parent
DB_PATH = BASE_DIR / "incidents.db"
SCHEMA_PATH = BASE_DIR / "schema.sql"


def _load_schema() -> str:
    with SCHEMA_PATH.open("r", encoding="utf-8") as f:
        return f.read()


def _seed_tickets(conn: sqlite3.Connection) -> None:
    tickets = [
        (
            "Error 500 en la API de usuarios",
            (
                "Los usuarios reportan que al intentar iniciar sesión reciben un "
                "error 500 desde hace unos minutos. En los logs de la API aparece "
                "un traceback de Python indicando `database is locked` al acceder "
                "a la tabla `sessions`."
            ),
            "api,login,error-500,sqlite,lock",
            "2025-01-10T09:15:00Z",
        ),
        (
            "Timeout al acceder al panel de administración",
            (
                "El panel de administración tarda más de 60 segundos en cargar "
                "y en muchos casos el frontend muestra un timeout. En los logs "
                "de nginx se observan múltiples respuestas 504 hacia /admin/. "
                "El problema empezó después de desplegar la versión 2.3.0."
            ),
            "admin,timeout,nginx,504,deploy",
            "2025-01-09T16:30:00Z",
        ),
        (
            "Usuarios no pueden restablecer la contraseña",
            (
                "Al solicitar el restablecimiento de contraseña, el usuario ve "
                "un mensaje de éxito pero nunca recibe el correo. En los logs "
                "del servicio de correo aparecen errores de autenticación SMTP "
                "por credenciales expiradas."
            ),
            "password-reset,email,smtp,auth",
            "2025-01-08T11:05:00Z",
        ),
        (
            "Errores de conexión intermitentes a la base de datos",
            (
                "Varias aplicaciones reportan errores `could not connect to server: "
                "Connection refused` al acceder a la base de datos principal. "
                "El problema aparece en picos de tráfico altos y se resuelve "
                "reiniciando el pod de base de datos."
            ),
            "database,connection,timeout,high-traffic",
            "2025-01-07T13:20:00Z",
        ),
        (
            "Problemas de login con autenticación de dos factores",
            (
                "Algunos usuarios con 2FA activado indican que el código TOTP "
                "es rechazado incluso cuando lo introducen dentro de los 30 segundos. "
                "La hora del servidor de autenticación está desfasada ~90 segundos "
                "respecto a NTP."
            ),
            "login,2fa,totp,ntp,time-sync",
            "2025-01-06T08:45:00Z",
        ),
        (
            "Subidas de ficheros fallan con error 413",
            (
                "Los usuarios no pueden subir adjuntos de más de 5MB. El navegador "
                "muestra un error y en nginx se registran respuestas 413 Request "
                "Entity Too Large para /upload/. La configuración actual de nginx "
                "limita el tamaño máximo a 5M."
            ),
            "uploads,nginx,413,file-size",
            "2025-01-05T17:10:00Z",
        ),
        (
            "CPU al 100% en el servidor de colas",
            (
                "El servicio de colas RabbitMQ muestra la CPU al 100% y la latencia "
                "de procesamiento de mensajes supera los 30 segundos. Se observa "
                "una sola cola con millones de mensajes pendientes generados por "
                "un job mal configurado."
            ),
            "rabbitmq,queues,cpu,latency,background-jobs",
            "2025-01-04T12:00:00Z",
        ),
    ]

    conn.executemany(
        "INSERT INTO tickets (title, body, tags, created_at) VALUES (?, ?, ?, ?)",
        tickets,
    )
    conn.commit()


def main() -> None:
    if DB_PATH.exists():
        DB_PATH.unlink()

    conn = sqlite3.connect(DB_PATH)
    try:
        schema_sql = _load_schema()
        conn.executescript(schema_sql)
        _seed_tickets(conn)
        print(f"Base de datos creada en {DB_PATH} con tickets de ejemplo.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()

