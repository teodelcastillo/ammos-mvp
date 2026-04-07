from db import get_conn, rows_to_list, row_to_dict

casos_tools = [
    {
        "name": "casos_crear",
        "description": "Crea un nuevo caso en el sistema del estudio.",
        "input_schema": {
            "type": "object",
            "properties": {
                "caratula":  {"type": "string", "description": "Carátula del caso (ej: 'García c/ López s/ Daños')"},
                "numero":    {"type": "string", "description": "Número de expediente (opcional)"},
                "cliente":   {"type": "string", "description": "Nombre del cliente"},
                "materia":   {"type": "string", "description": "Materia del caso (ej: Laboral, Civil, Penal)"},
                "fuero":     {"type": "string", "description": "Fuero (ej: Civil, Laboral, Federal)"},
                "juzgado":   {"type": "string", "description": "Juzgado o tribunal"},
                "abogado":   {"type": "string", "description": "Abogado responsable"},
                "notas":     {"type": "string", "description": "Notas adicionales (opcional)"},
            },
            "required": ["caratula"],
        },
    },
    {
        "name": "casos_buscar",
        "description": "Busca casos por carátula, cliente, número, materia o abogado.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query":   {"type": "string", "description": "Texto a buscar en carátula, cliente, número o materia"},
                "estado":  {"type": "string", "description": "Filtrar por estado: activo, archivado, cerrado"},
                "abogado": {"type": "string", "description": "Filtrar por abogado responsable"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "casos_ver",
        "description": "Ve los detalles completos de un caso por su ID.",
        "input_schema": {
            "type": "object",
            "properties": {
                "caso_id": {"type": "integer", "description": "ID del caso"},
            },
            "required": ["caso_id"],
        },
    },
    {
        "name": "casos_actualizar_estado",
        "description": "Actualiza el estado de un caso (activo, archivado, cerrado).",
        "input_schema": {
            "type": "object",
            "properties": {
                "caso_id": {"type": "integer", "description": "ID del caso"},
                "estado":  {"type": "string", "description": "Nuevo estado: activo, archivado, cerrado"},
                "notas":   {"type": "string", "description": "Nota sobre el cambio de estado (opcional)"},
            },
            "required": ["caso_id", "estado"],
        },
    },
    {
        "name": "casos_listar",
        "description": "Lista todos los casos activos, opcionalmente filtrados por abogado.",
        "input_schema": {
            "type": "object",
            "properties": {
                "abogado": {"type": "string", "description": "Filtrar por abogado (opcional)"},
                "estado":  {"type": "string", "description": "Estado a listar (default: activo)"},
            },
            "required": [],
        },
    },
]


async def handle_casos_tool(name: str, data: dict) -> dict:
    try:
        if name == "casos_crear":       return _crear(data)
        if name == "casos_buscar":      return _buscar(data)
        if name == "casos_ver":         return _ver(data)
        if name == "casos_actualizar_estado": return _actualizar_estado(data)
        if name == "casos_listar":      return _listar(data)
        return {"error": f"Tool desconocido: {name}"}
    except Exception as e:
        return {"error": str(e)}


def _crear(data: dict) -> dict:
    with get_conn() as conn:
        # Buscar o crear cliente si se proporcionó
        cliente_id = None
        if nombre_cliente := data.get("cliente"):
            row = conn.execute(
                "SELECT id FROM clientes WHERE nombre LIKE ?", (f"%{nombre_cliente}%",)
            ).fetchone()
            if row:
                cliente_id = row["id"]
            else:
                cur = conn.execute(
                    "INSERT INTO clientes (nombre) VALUES (?)", (nombre_cliente,)
                )
                cliente_id = cur.lastrowid

        cur = conn.execute(
            """INSERT INTO casos (caratula, numero, cliente_id, materia, fuero, juzgado, abogado, notas, fecha_inicio)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, DATE('now'))""",
            (
                data["caratula"],
                data.get("numero"),
                cliente_id,
                data.get("materia"),
                data.get("fuero"),
                data.get("juzgado"),
                data.get("abogado"),
                data.get("notas"),
            ),
        )
        return {"status": "creado", "caso_id": cur.lastrowid, "caratula": data["caratula"]}


def _buscar(data: dict) -> dict:
    q = f"%{data['query']}%"
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT c.id, c.caratula, c.numero, c.materia, c.fuero, c.estado, c.abogado,
                      cl.nombre as cliente
               FROM casos c LEFT JOIN clientes cl ON c.cliente_id = cl.id
               WHERE (c.caratula LIKE ? OR c.numero LIKE ? OR c.materia LIKE ?
                      OR cl.nombre LIKE ? OR c.abogado LIKE ?)
                 AND c.estado = ?
               ORDER BY c.creado_en DESC LIMIT 20""",
            (q, q, q, q, q, data.get("estado", "activo")),
        ).fetchall()
        return {"casos": rows_to_list(rows), "count": len(rows)}


def _ver(data: dict) -> dict:
    with get_conn() as conn:
        row = conn.execute(
            """SELECT c.*, cl.nombre as cliente, cl.telefono as cliente_tel, cl.email as cliente_email
               FROM casos c LEFT JOIN clientes cl ON c.cliente_id = cl.id
               WHERE c.id = ?""",
            (data["caso_id"],),
        ).fetchone()
        if not row:
            return {"error": f"Caso {data['caso_id']} no encontrado"}

        caso = row_to_dict(row)

        # Agregar horas totales
        horas = conn.execute(
            "SELECT COALESCE(SUM(horas), 0) as total FROM registros_tiempo WHERE caso_id = ?",
            (data["caso_id"],),
        ).fetchone()
        caso["horas_totales"] = horas["total"]

        return caso


def _actualizar_estado(data: dict) -> dict:
    with get_conn() as conn:
        notas_update = ""
        if nota := data.get("notas"):
            notas_update = f" | {nota}"

        conn.execute(
            "UPDATE casos SET estado = ?, notas = COALESCE(notas, '') || ? WHERE id = ?",
            (data["estado"], notas_update, data["caso_id"]),
        )
        return {"status": "actualizado", "caso_id": data["caso_id"], "estado": data["estado"]}


def _listar(data: dict) -> dict:
    estado = data.get("estado", "activo")
    with get_conn() as conn:
        query = """SELECT c.id, c.caratula, c.numero, c.materia, c.fuero, c.estado, c.abogado,
                          cl.nombre as cliente
                   FROM casos c LEFT JOIN clientes cl ON c.cliente_id = cl.id
                   WHERE c.estado = ?"""
        params = [estado]

        if abogado := data.get("abogado"):
            query += " AND c.abogado LIKE ?"
            params.append(f"%{abogado}%")

        query += " ORDER BY c.creado_en DESC"
        rows = conn.execute(query, params).fetchall()
        return {"casos": rows_to_list(rows), "count": len(rows)}
