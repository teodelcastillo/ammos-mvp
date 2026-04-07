"""
Base de datos SQLite para el estudio jurídico.
Almacena casos, clientes, registros de tiempo y notas de reuniones.
"""

import sqlite3
import os
from contextlib import contextmanager

DB_PATH = os.getenv("DB_PATH", "/app/data/estudio.db")


def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    with get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS clientes (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre      TEXT NOT NULL,
                cuit        TEXT,
                email       TEXT,
                telefono    TEXT,
                domicilio   TEXT,
                notas       TEXT,
                creado_en   DATETIME DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS casos (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                numero              TEXT,
                caratula            TEXT NOT NULL,
                cliente_id          INTEGER REFERENCES clientes(id),
                materia             TEXT,
                fuero               TEXT,
                juzgado             TEXT,
                estado              TEXT DEFAULT 'activo',
                fecha_inicio        DATE,
                abogado             TEXT,
                notas               TEXT,
                creado_en           DATETIME DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS registros_tiempo (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                caso_id     INTEGER REFERENCES casos(id),
                abogado     TEXT NOT NULL,
                fecha       DATE NOT NULL,
                horas       REAL NOT NULL,
                descripcion TEXT,
                creado_en   DATETIME DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS notas_reunion (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                caso_id       INTEGER REFERENCES casos(id),
                cliente_id    INTEGER REFERENCES clientes(id),
                fecha         DATETIME NOT NULL,
                participantes TEXT,
                contenido     TEXT NOT NULL,
                creado_por    TEXT,
                creado_en     DATETIME DEFAULT CURRENT_TIMESTAMP
            );
        """)


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def row_to_dict(row) -> dict:
    return dict(row) if row else None


def rows_to_list(rows) -> list:
    return [dict(r) for r in rows]
