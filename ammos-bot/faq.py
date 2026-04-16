"""FAQ matching simple por keywords (sin embeddings para el MVP)."""

from __future__ import annotations

import re
import unicodedata

from db import get_conn, row_to_dict


def _normalize(text: str) -> str:
    text = text.lower().strip()
    text = "".join(
        c for c in unicodedata.normalize("NFD", text)
        if unicodedata.category(c) != "Mn"
    )
    return re.sub(r"[^a-z0-9\s]", " ", text)


def _tokens(text: str) -> set[str]:
    return {t for t in _normalize(text).split() if len(t) > 2}


def match_faq(message: str, property_id: int | None) -> dict | None:
    """Busca una FAQ relevante.

    Score = cantidad de keywords matcheados + bonus si la propiedad coincide.
    Mínimo 2 keywords matcheadas para devolver respuesta (evita falsos positivos).
    """
    msg_tokens = _tokens(message)
    if not msg_tokens:
        return None

    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT * FROM faqs
            WHERE is_global = 1 OR property_id = ?
            """,
            (property_id,),
        ).fetchall()

    best = None
    best_score = 0

    for row in rows:
        row = dict(row)
        kws = _tokens((row.get("keywords") or "") + " " + row["question"])
        hits = len(msg_tokens & kws)
        if hits == 0:
            continue

        score = hits
        if property_id and row.get("property_id") == property_id:
            score += 1  # preferimos la FAQ específica de la propiedad

        if score > best_score:
            best_score = score
            best = row

    if best and best_score >= 2:
        return best
    return None
