from db import get_conn, rows_to_list, row_to_dict

notas_tools = [
    {
        "name": "notas_crear",
        "description": "Guarda una nota de reunión o de caso. Puede estar asociada a un caso y/o cliente.",
        "input_schema": {
            "type": "object",
            "properties": {
                "contenido":      {"type": "string",  "description": "Contenido de la nota o minuta"},
                "caso_id":        {"type": "integer", "description": "ID del caso asociado (opcional)"},
                "cliente":        {"type": "string",  "description": "Nombre del cliente (opcional)"},
                "participantes":  {"type": "string",  "description": "Personas presentes en la reunión (opcional)"},
                "creado_por":     {"type": "string",  "description": "Quien crea la nota"},
                "fecha":          {"type": "string",  "description": "Fecha/hora de la reunión (default: ahora)"},
            },
            "required": ["contenido"],
        },
    },
    {
        "name": "notas_buscar",
        "description": "Busca notas por texto, caso o cliente.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query":    {"type": "string",  "description": "Texto a buscar en el contenido"},
                "caso_id":  {"type": "integer", "description": "Filtrar por caso (opcional)"},
                "cliente":  {"type": "string",  "description": "Filtrar por nombre de cliente (opcional)"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "notas_listar_caso",
        "description": "Lista todas las notas de un caso específico.",
        "input_schema": {
            "type": "object",
            "properties": {
                "caso_id": {"type": "integer", "description": "ID del caso"},
            },
            "required": ["caso_id"],
        },
    },
]


async def handle_notas_tool(name: str, data: dict) -> dict:
    try:
        if name == "notas_crear":       return _crear(data)
        if name == "notas_buscar":      return _buscar(data)
        if name == "notas_listar_caso": return _listar_caso(data)
        return {"error": f"Tool desconocido: {name}"}
    except Exception as e:
        return {"error": str(e)}


def _crear(data: dict) -> dict:
    with get_conn() as conn:
        # Buscar cliente si se proporcionó nombre
        cliente_id = None
        if nombre_cliente := data.get("cliente"):
            row = conn.execute(
                "SELECT id FROM clientes WHERE nombre LIKE ?", (f"%{nombre_cliente}%",)
            ).fetchone()
            if row:
                cliente_id = row["id"]

        cur = conn.execute(
            """INSERT INTO notas_reunion
               (contenido, caso_id, cliente_id, participantes, creado_por, fecha)
               VALUES (?, ?, ?, ?, ?, COALESCE(?, DATETIME('now')))""",
            (
                data["contenido"],
                data.get("caso_id"),
                cliente_id,
                data.get("participantes"),
                data.get("creado_por"),
                data.get("fecha"),
            ),
        )
        return {"status": "guardada", "nota_id": cur.lastrowid}


def _buscar(data: dict) -> dict:
    q = f"%{data['query']}%"
    with get_conn() as conn:
        query = """
            SELECT n.id, n.fecha, n.contenido, n.participantes, n.creado_por,
                   c.caratula as caso, cl.nombre as cliente
            FROM notas_reunion n
            LEFT JOIN casos c    ON n.caso_id = c.id
            LEFT JOIN clientes cl ON n.cliente_id = cl.id
            WHERE n.contenido LIKE ?
        """
        params = [q]

        if caso_id := data.get("caso_id"):
            query += " AND n.caso_id = ?"
            params.append(caso_id)
        if cliente := data.get("cliente"):
            query += " AND cl.nombre LIKE ?"
            params.append(f"%{cliente}%")

        query += " ORDER BY n.fecha DESC LIMIT 20"
        rows = conn.execute(query, params).fetchall()
        return {"notas": rows_to_list(rows), "count": len(rows)}


def _listar_caso(data: dict) -> dict:
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT n.id, n.fecha, n.contenido, n.participantes, n.creado_por
               FROM notas_reunion n WHERE n.caso_id = ?
               ORDER BY n.fecha DESC""",
            (data["caso_id"],),
        ).fetchall()
        return {"notas": rows_to_list(rows), "count": len(rows)}
