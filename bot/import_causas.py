"""
Importación del sheet "GENERAL DE CAUSAS" a la base de datos.
Columnas del sheet: caratula | expte | cliente | nro | juzgado | mediacion | observaciones
"""

import json
import logging
import os
import unicodedata
from difflib import SequenceMatcher

from googleapiclient.discovery import build

from db import get_conn
from google_auth import get_credentials

logger = logging.getLogger("import_causas")

SHEET_ID    = os.getenv("CAUSAS_SHEET_ID",    "1LmF0vYJXPmUJ3mpIk4AUQGgc3bBWI8meAa-4e_e5uSA")
SHEET_RANGE = os.getenv("CAUSAS_SHEET_RANGE", "A:G")
# Similitud mínima para considerar dos nombres como el mismo cliente (0-1)
FUZZY_THRESHOLD = float(os.getenv("CLIENT_FUZZY_THRESHOLD", "0.82"))

_ALIASES_PATH = os.path.join(os.path.dirname(__file__), "client_aliases.json")

HEADER_MAP = {
    "caratula": "caratula", "carátula": "caratula",
    "expte": "numero",      "expediente": "numero",
    "cliente": "cliente",
    "nro": "nro_interno",
    "juzgado": "juzgado",
    "mediacion": "mediacion", "mediación": "mediacion",
    "observaciones": "observaciones",
}

# Sufijos legales a ignorar al comparar nombres
_LEGAL_SUFFIXES = [
    " sa", " srl", " sac", " saci", " sacif", " s a", " s r l",
    " s a c i f", " s a c", " sa de cv", " ag", " inc", " ltd",
]


# ──────────────────────────────────────────────
# Normalización
# ──────────────────────────────────────────────

def _normalize(s: str) -> str:
    """Minúsculas, sin tildes, sin espacios extra."""
    s = s.strip().lower()
    return "".join(
        c for c in unicodedata.normalize("NFD", s)
        if unicodedata.category(c) != "Mn"
    )


def _normalize_for_dedup(s: str) -> str:
    """Normalización agresiva para comparar nombres de clientes.
    Elimina puntos, comas, sufijos legales y colapsa espacios."""
    s = _normalize(s)
    # Eliminar puntos y comas (SA / S.A. / S.A)
    s = s.replace(".", "").replace(",", "")
    # Colapsar espacios
    s = " ".join(s.split())
    # Quitar sufijos legales al final
    for suf in sorted(_LEGAL_SUFFIXES, key=len, reverse=True):
        if s.endswith(suf):
            s = s[: -len(suf)].strip()
            break
    return s


def _similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


# ──────────────────────────────────────────────
# Aliases explícitos (client_aliases.json)
# ──────────────────────────────────────────────

def _load_aliases() -> dict[str, list[str]]:
    try:
        with open(_ALIASES_PATH) as f:
            return json.load(f)
    except Exception:
        return {}


def _resolve_alias(name: str, aliases: dict[str, list[str]]) -> str | None:
    """Devuelve el nombre canónico si el nombre matchea algún alias explícito."""
    name_norm = _normalize(name)
    for canonical, patterns in aliases.items():
        for pattern in patterns:
            if _normalize(pattern) in name_norm or name_norm in _normalize(pattern):
                return canonical
    return None


# ──────────────────────────────────────────────
# Deduplicación automática por fuzzy matching
# ──────────────────────────────────────────────

def _cluster_clients(names: list[str]) -> list[list[str]]:
    """Agrupa nombres similares. Retorna lista de grupos; el primer elemento es el canónico."""
    dedup_keys = [(n, _normalize_for_dedup(n)) for n in names]
    # Ordenar: más largo primero (el nombre más completo suele ser el canónico)
    dedup_keys.sort(key=lambda x: -len(x[1]))

    groups: list[list[str]] = []
    assigned: set[int] = set()

    for i, (name_i, key_i) in enumerate(dedup_keys):
        if i in assigned:
            continue
        group = [name_i]
        assigned.add(i)
        for j, (name_j, key_j) in enumerate(dedup_keys):
            if j in assigned:
                continue
            if _similarity(key_i, key_j) >= FUZZY_THRESHOLD:
                group.append(name_j)
                assigned.add(j)
        groups.append(group)

    return groups


def build_client_map(raw_names: list[str], aliases: dict) -> dict[str, str]:
    """
    Construye un mapa {nombre_original → nombre_canónico} aplicando:
    1. Aliases explícitos (mayor prioridad)
    2. Fuzzy clustering automático
    """
    # Primero resolver aliases explícitos
    alias_resolved: dict[str, str] = {}
    remaining: list[str] = []
    for name in raw_names:
        canonical = _resolve_alias(name, aliases)
        if canonical:
            alias_resolved[name] = canonical
        else:
            remaining.append(name)

    # Deduplicar los restantes por fuzzy
    unique_remaining = list(dict.fromkeys(remaining))  # preservar orden, sin duplicados
    clusters = _cluster_clients(unique_remaining)

    fuzzy_map: dict[str, str] = {}
    for group in clusters:
        canonical = group[0]  # el más largo / primero del grupo
        for name in group:
            fuzzy_map[name] = canonical

    return {**fuzzy_map, **alias_resolved}


# ──────────────────────────────────────────────
# Lectura del sheet
# ──────────────────────────────────────────────

def _parse_bool(val: str) -> bool:
    return _normalize(val) in ("true", "si", "sí", "1", "x", "yes")


def _read_sheet() -> list[dict]:
    creds = get_credentials()
    service = build("sheets", "v4", credentials=creds)
    result = service.spreadsheets().values().get(
        spreadsheetId=SHEET_ID, range=SHEET_RANGE
    ).execute()

    rows = result.get("values", [])
    logger.info("Sheet devolvió %d filas totales", len(rows))
    if not rows:
        return []

    # Primera fila no vacía = headers
    header_idx = next(
        (i for i, r in enumerate(rows) if any(c.strip() for c in r)), 0
    )
    raw_headers = [h.strip() for h in rows[header_idx]]
    headers = [HEADER_MAP.get(_normalize(h), _normalize(h)) for h in raw_headers]
    logger.info("Headers en fila %d: %s", header_idx + 1, headers)

    records = []
    for row in rows[header_idx + 1:]:
        padded = row + [""] * (len(headers) - len(row))
        rec = dict(zip(headers, padded))
        if any(v.strip() for v in rec.values()):
            records.append(rec)

    return records


# ──────────────────────────────────────────────
# Importación
# ──────────────────────────────────────────────

def run_import(dry_run: bool = False) -> dict:
    """
    Importa el sheet a la DB.
    dry_run=True: solo reporta qué haría, sin escribir.
    """
    logger.info("Leyendo sheet GENERAL DE CAUSAS (dry_run=%s)...", dry_run)
    try:
        records = _read_sheet()
    except Exception as e:
        import traceback
        return {"error": f"{type(e).__name__}: {e}\n{traceback.format_exc()}"}

    aliases = _load_aliases()

    # Construir mapa de deduplicación sobre todos los nombres únicos del sheet
    all_raw_names = list(dict.fromkeys(
        r.get("cliente", "").strip() for r in records if r.get("cliente", "").strip()
    ))
    client_map = build_client_map(all_raw_names, aliases)

    # Grupos con más de 1 variante (para mostrar en preview)
    from collections import defaultdict
    canonical_to_variants: dict[str, list[str]] = defaultdict(list)
    for original, canonical in client_map.items():
        if original != canonical:
            canonical_to_variants[canonical].append(original)

    merged_groups = [
        {"canonical": k, "variants": v}
        for k, v in canonical_to_variants.items()
        if v
    ]
    logger.info("Grupos de clientes unificados: %d", len(merged_groups))

    stats = {
        "total_filas": len(records),
        "clientes_nuevos": 0,
        "clientes_existentes": 0,
        "casos_nuevos": 0,
        "casos_existentes": 0,
        "omitidos": 0,
        "merged_groups": merged_groups,
        "detalles": [],
    }

    with get_conn() as conn:
        for rec in records:
            caratula = rec.get("caratula", "").strip()
            if not caratula:
                stats["omitidos"] += 1
                continue

            numero    = rec.get("numero", "").strip() or None
            raw_cl    = rec.get("cliente", "").strip()
            cliente_n = client_map.get(raw_cl, raw_cl)
            juzgado   = rec.get("juzgado", "").strip() or None
            mediacion = _parse_bool(rec.get("mediacion", ""))
            notas_parts = []
            if nro := rec.get("nro_interno", "").strip():
                notas_parts.append(f"Nro interno: {nro}")
            if obs := rec.get("observaciones", "").strip():
                notas_parts.append(obs)
            notas = " | ".join(notas_parts) or None

            # ¿Ya existe el caso?
            query = "SELECT id FROM casos WHERE LOWER(TRIM(caratula)) = LOWER(TRIM(?))"
            params: tuple = (caratula,)
            if numero:
                query += " OR (numero IS NOT NULL AND numero = ?)"
                params = (caratula, numero)
            if conn.execute(query, params).fetchone():
                stats["casos_existentes"] += 1
                stats["detalles"].append({"accion": "omitido", "caratula": caratula, "razon": "ya existe"})
                continue

            # Cliente
            cliente_id = None
            if cliente_n:
                row = conn.execute(
                    "SELECT id FROM clientes WHERE LOWER(TRIM(nombre)) = LOWER(TRIM(?))",
                    (cliente_n,)
                ).fetchone()
                if row:
                    cliente_id = row[0]
                    stats["clientes_existentes"] += 1
                else:
                    if not dry_run:
                        cur = conn.execute("INSERT INTO clientes (nombre) VALUES (?)", (cliente_n,))
                        cliente_id = cur.lastrowid
                    stats["clientes_nuevos"] += 1

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
                "cliente_original": raw_cl if raw_cl != cliente_n else "",
                "juzgado": juzgado or "—",
            })

    logger.info(
        "Importación %s: %d casos, %d clientes nuevos, %d grupos unificados",
        "simulada" if dry_run else "completada",
        stats["casos_nuevos"], stats["clientes_nuevos"], len(merged_groups),
    )
    return stats
