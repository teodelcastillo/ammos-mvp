from googleapiclient.discovery import build

from google_auth import get_credentials

drive_tools = [
    {
        "name": "drive_search_files",
        "description": "Busca archivos en Google Drive por nombre o contenido. Útil para encontrar escritos, contratos, expedientes, etc.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Texto a buscar en nombres y contenido de archivos",
                },
                "mime_type": {
                    "type": "string",
                    "description": "Filtrar por tipo MIME (ej: application/pdf, application/vnd.google-apps.document)",
                },
                "max_results": {
                    "type": "integer",
                    "description": "Máximo de resultados (default 10)",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "drive_get_file_content",
        "description": "Lee el contenido de texto de un archivo de Google Drive (solo Google Docs y Sheets).",
        "input_schema": {
            "type": "object",
            "properties": {
                "file_id": {
                    "type": "string",
                    "description": "ID del archivo en Google Drive",
                },
            },
            "required": ["file_id"],
        },
    },
    {
        "name": "drive_list_folder",
        "description": "Lista archivos en una carpeta de Google Drive.",
        "input_schema": {
            "type": "object",
            "properties": {
                "folder_id": {
                    "type": "string",
                    "description": "ID de la carpeta. Usar 'root' para la raíz.",
                },
                "max_results": {
                    "type": "integer",
                    "description": "Máximo de resultados (default 20)",
                },
            },
            "required": [],
        },
    },
]


def _get_service():
    return build("drive", "v3", credentials=get_credentials())


async def handle_drive_tool(name: str, input_data: dict) -> dict:
    try:
        service = _get_service()

        if name == "drive_search_files":
            return _search_files(service, input_data)
        elif name == "drive_get_file_content":
            return _get_file_content(service, input_data)
        elif name == "drive_list_folder":
            return _list_folder(service, input_data)
        return {"error": f"Tool desconocido: {name}"}
    except Exception as e:
        return {"error": str(e)}


def _search_files(service, data: dict) -> dict:
    query = data["query"]
    max_results = data.get("max_results", 10)

    q = f"fullText contains '{query}' and trashed = false"
    if mime := data.get("mime_type"):
        q += f" and mimeType = '{mime}'"

    results = (
        service.files()
        .list(
            q=q,
            pageSize=max_results,
            fields="files(id, name, mimeType, modifiedTime, webViewLink, size)",
            orderBy="modifiedTime desc",
        )
        .execute()
    )

    files = results.get("files", [])
    return {
        "files": [
            {
                "id": f["id"],
                "name": f["name"],
                "type": f["mimeType"],
                "modified": f.get("modifiedTime", ""),
                "link": f.get("webViewLink", ""),
            }
            for f in files
        ],
        "count": len(files),
    }


def _get_file_content(service, data: dict) -> dict:
    file_id = data["file_id"]
    meta = service.files().get(fileId=file_id, fields="mimeType,name").execute()
    mime = meta["mimeType"]

    if mime == "application/vnd.google-apps.document":
        content = service.files().export(fileId=file_id, mimeType="text/plain").execute()
        text = content.decode("utf-8") if isinstance(content, bytes) else content
        return {"name": meta["name"], "content": text}

    if mime == "application/vnd.google-apps.spreadsheet":
        content = service.files().export(fileId=file_id, mimeType="text/csv").execute()
        text = content.decode("utf-8") if isinstance(content, bytes) else content
        return {"name": meta["name"], "content": text}

    return {"name": meta["name"], "error": "Solo se puede leer el contenido de Google Docs y Sheets."}


def _list_folder(service, data: dict) -> dict:
    folder_id = data.get("folder_id", "root")
    max_results = data.get("max_results", 20)

    results = (
        service.files()
        .list(
            q=f"'{folder_id}' in parents and trashed = false",
            pageSize=max_results,
            fields="files(id, name, mimeType, modifiedTime)",
            orderBy="name",
        )
        .execute()
    )

    files = results.get("files", [])
    return {
        "files": [
            {
                "id": f["id"],
                "name": f["name"],
                "type": f["mimeType"],
                "modified": f.get("modifiedTime", ""),
            }
            for f in files
        ],
        "count": len(files),
    }
