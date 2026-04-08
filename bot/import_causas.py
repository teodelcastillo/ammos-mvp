"""
Importación del sheet "GENERAL DE CAUSAS" a la base de datos.
Columnas del sheet: caratula | expte | cliente | nro | juzgado | mediacion | observaciones
"""

import logging
import os
import unicodedata

from googleapiclient.discovery import build

from db import get_conn, rows_to_list
from google_auth import get_credentials

logger = logging.getLogger("import_causas")

SHEET_ID = os.getenv("CAUSAS_SHEET_ID", "1LmF0vYJXPmUJ3mpIk4AUQGgc3bBWI8meAa-4e_e5uSA")
SHEET_RANGE = os.getenv("CAUSAS_SHEET_RANGE", "A:G")

# Mapeo de encabezados del sheet a campos internos
HEADER_MAP = {
    "caratula": "caratula",
    "carátula": "caratula",
    "expte": "numero",
    "expediente": "numero",
    "cliente": "cliente",
    "nro": "nro_interno",
    "juzgado": "juzgado",
    "mediacion": "mediacion",
    "mediación": "mediacion",
    "observaciones": "observaciones",
}


def _normalize(s: str) -> str:
    """Minúsculas, sin tildes, sin espacios extra."""
    s = s.strip().lower()
    return "".join(
        c for c in unicodedata.normalize("NFD", s)
        if unicodedata.category(c) != "Mn"
    )


def _parse_bool(val: str) -> bool:
    return _normalize(val) in ("true", "si", "sí", "1", "x", "yes")


def _read_sheet() -> list[dict]:
    """Lee el sheet y devuelve lista de dicts con los campos mapeados."""
    creds = get_credentials()
    service = build("sheets", "v4", credentials=creds)
    result = service.spreadsheets().values().get(
        spreadsheetId=SHEET_ID,
        range=SHEET_RANGE,
    ).execute()

    rows = result.get("values", [])
    logger.info("Sheet devolvió %d filas. Primera fila: %s", len(rows), rows[0] if rows else "VACÍO")
    if not rows:
        return []

    # Primera fila = headers
    raw_headers = [h.strip() for h in rows[0]]
    headers = [HEADER_MAP.get(_normalize(h), _normalize(h)) for h in raw_headers]
    logger.info("Headers detectados: %s", headers)

    records = []
    for row in rows[1:]:
        # Pad row to header length
        padded = row + [""] * (len(headers) - len(row))
        record = dict(zip(headers, padded))
        # Saltar filas completamente vacías
        if not any(v.strip() for v in record.values()):
            continue
        records.append(record)

    return records


def _get_or_create_cliente(conn, nombre: str) -> int | None:
    """Retorna ID del cliente existente o crea uno nuevo."""
    nombre = nombre.strip()
    if not nombre:
        return None

    existing = conn.execute(
        "SELECT id FROM clientes WHERE LOWER(TRIM(nombre)) = LOWER(TRIM(?))", (nombre,)
    ).fetchone()
    if existing:
        return existing[0]

    cursor = conn.execute(
        "INSERT INTO clientes (nombre) VALUES (?)", (nombre,)
    )
    return cursor.lastrowid


def run_import(dry_run: bool = False) -> dict:
    """
    Importa el sheet a la DB.
    dry_run=True: solo reporta qué haría, sin escribir.
    Retorna estadísticas del proceso.
    """
    logger.info("Leyendo sheet GENERAL DE CAUSAS (dry_run=%s)...", dry_run)

    try:
        records = _read_sheet()
    except Exception as e:
        import traceback
        return {"error": f"{type(e).__name__}: {e}\n{traceback.format_exc()}", "clientes_nuevos": 0, "casos_nuevos": 0, "omitidos": 0}

    stats = {
        "total_filas": len(records),
        "clientes_nuevos": 0,
        "clientes_existentes": 0,
        "casos_nuevos": 0,
        "casos_existentes": 0,
        "omitidos": 0,
        "detalles": [],
    }

    with get_conn() as conn:
        for rec in records:
            caratula = rec.get("caratula", "").strip()
            if not caratula:
                stats["omitidos"] += 1
                continue

            numero    = rec.get("numero", "").strip() or None
            cliente_n = rec.get("cliente", "").strip()
            juzgado   = rec.get("juzgado", "").strip() or None
            mediacion = _parse_bool(rec.get("mediacion", ""))
            notas_parts = []
            if nro := rec.get("nro_interno", "").strip():
                notas_parts.append(f"Nro interno: {nro}")
            if obs := rec.get("observaciones", "").strip():
                notas_parts.append(obs)
            notas = " | ".join(notas_parts) or None

            # Verificar si el caso ya existe (por carátula o número)
            existing_caso = conn.execute(
                "SELECT id FROM casos WHERE LOWER(TRIM(caratula)) = LOWER(TRIM(?))"
                + (" OR (numero IS NOT NULL AND numero = ?)" if numero else ""),
                (caratula, numero) if numero else (caratula,)
            ).fetchone()

            if existing_caso:
                stats["casos_existentes"] += 1
                stats["detalles"].append({"accion": "omitido", "caratula": caratula, "razon": "ya existe"})
                continue

            # Cliente
            cliente_id = None
            if cliente_n:
                existing_cl = conn.execute(
                    "SELECT id FROM clientes WHERE LOWER(TRIM(nombre)) = LOWER(TRIM(?))",
                    (cliente_n,)
                ).fetchone()
                if existing_cl:
                    cliente_id = existing_cl[0]
                    stats["clientes_existentes"] += 1
                else:
                    if not dry_run:
                        cur = conn.execute("INSERT INTO clientes (nombre) VALUES (?)", (cliente_n,))
                        cliente_id = cur.lastrowid
                    stats["clientes_nuevos"] += 1

            # Insertar caso
            if not dry_run:
                conn.execute(
                    """INSERT INTO casos
                       (caratula, numero, cliente_id, juzgado, mediacion, notas, estado)
                       VALUES (?, ?, ?, ?, ?, ?, 'activo')""",
                    (caratula, numero, cliente_id, juzgado, mediacion, notas)
                )
            stats["casos_nuevos"] += 1
            stats["detalles"].append({
                "accion": "importar",
                "caratula": caratula,
                "cliente": cliente_n or "—",
                "juzgado": juzgado or "—",
            })

    logger.info(
        "Importación %s: %d casos nuevos, %d existentes, %d clientes nuevos, %d omitidos",
        "simulada" if dry_run else "completada",
        stats["casos_nuevos"], stats["casos_existentes"],
        stats["clientes_nuevos"], stats["omitidos"],
    )
    return stats
