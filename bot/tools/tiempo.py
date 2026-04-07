from db import get_conn, rows_to_list

tiempo_tools = [
    {
        "name": "tiempo_registrar",
        "description": "Registra horas trabajadas en un caso. Útil para llevar el control de tiempo por abogado.",
        "input_schema": {
            "type": "object",
            "properties": {
                "caso_id":     {"type": "integer", "description": "ID del caso"},
                "abogado":     {"type": "string",  "description": "Nombre del abogado"},
                "horas":       {"type": "number",  "description": "Cantidad de horas (ej: 1.5 para 1h30m)"},
                "descripcion": {"type": "string",  "description": "Descripción de la tarea realizada"},
                "fecha":       {"type": "string",  "description": "Fecha en formato YYYY-MM-DD (default: hoy)"},
            },
            "required": ["caso_id", "abogado", "horas"],
        },
    },
    {
        "name": "tiempo_resumen",
        "description": "Muestra el resumen de horas trabajadas por caso o por abogado en un período.",
        "input_schema": {
            "type": "object",
            "properties": {
                "caso_id":    {"type": "integer", "description": "Filtrar por caso específico (opcional)"},
                "abogado":    {"type": "string",  "description": "Filtrar por abogado (opcional)"},
                "desde":      {"type": "string",  "description": "Desde fecha YYYY-MM-DD (default: inicio del mes)"},
                "hasta":      {"type": "string",  "description": "Hasta fecha YYYY-MM-DD (default: hoy)"},
            },
            "required": [],
        },
    },
]


async def handle_tiempo_tool(name: str, data: dict) -> dict:
    try:
        if name == "tiempo_registrar": return _registrar(data)
        if name == "tiempo_resumen":   return _resumen(data)
        return {"error": f"Tool desconocido: {name}"}
    except Exception as e:
        return {"error": str(e)}


def _registrar(data: dict) -> dict:
    with get_conn() as conn:
        # Verificar que el caso existe
        caso = conn.execute(
            "SELECT caratula FROM casos WHERE id = ?", (data["caso_id"],)
        ).fetchone()
        if not caso:
            return {"error": f"Caso {data['caso_id']} no encontrado"}

        cur = conn.execute(
            """INSERT INTO registros_tiempo (caso_id, abogado, horas, descripcion, fecha)
               VALUES (?, ?, ?, ?, COALESCE(?, DATE('now')))""",
            (
                data["caso_id"],
                data["abogado"],
                data["horas"],
                data.get("descripcion"),
                data.get("fecha"),
            ),
        )
        return {
            "status": "registrado",
            "id": cur.lastrowid,
            "caso": caso["caratula"],
            "horas": data["horas"],
            "abogado": data["abogado"],
        }


def _resumen(data: dict) -> dict:
    with get_conn() as conn:
        # Resumen por caso en el período
        query = """
            SELECT c.caratula, rt.abogado, SUM(rt.horas) as total_horas,
                   COUNT(*) as registros
            FROM registros_tiempo rt
            JOIN casos c ON rt.caso_id = c.id
            WHERE rt.fecha BETWEEN COALESCE(?, DATE('now','start of month')) AND COALESCE(?, DATE('now'))
        """
        params = [data.get("desde"), data.get("hasta")]

        if caso_id := data.get("caso_id"):
            query += " AND rt.caso_id = ?"
            params.append(caso_id)
        if abogado := data.get("abogado"):
            query += " AND rt.abogado LIKE ?"
            params.append(f"%{abogado}%")

        query += " GROUP BY c.id, rt.abogado ORDER BY total_horas DESC"
        rows = conn.execute(query, params).fetchall()

        total = sum(r["total_horas"] for r in rows)
        return {
            "registros": rows_to_list(rows),
            "total_horas": total,
            "desde": data.get("desde", "inicio del mes"),
            "hasta": data.get("hasta", "hoy"),
        }
