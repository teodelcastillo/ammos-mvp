import json
import logging
import os
from collections import defaultdict
from datetime import datetime
from zoneinfo import ZoneInfo

from anthropic import AsyncAnthropic

from tools.calendar import calendar_tools, handle_calendar_tool
from tools.drive import drive_tools, handle_drive_tool
from tools.weather import weather_tools, handle_weather_tool
from tools.casos import casos_tools, handle_casos_tool
from tools.tiempo import tiempo_tools, handle_tiempo_tool
from tools.notas import notas_tools, handle_notas_tool

logger = logging.getLogger(__name__)

TIMEZONE = os.getenv("TIMEZONE", "America/Argentina/Cordoba")
BOT_NAME = os.getenv("BOT_NAME", "Bot")
CALENDAR_ID = os.getenv("CALENDAR_ID", "primary")  # ID del calendario a usar

client = AsyncAnthropic()

SYSTEM_PROMPT = """Sos un asistente virtual para el estudio jurídico Del Castillo, ubicado en Córdoba, Argentina.

Tu rol es ayudar al equipo del estudio con:
- *Calendario*: vencimientos, reuniones, audiencias, plazos del calendario "Estudio del Castillo abogados"
- *Casos*: crear, buscar y actualizar el estado de expedientes
- *Tiempo*: registrar horas trabajadas por caso y abogado
- *Notas*: guardar y buscar minutas de reuniones
- *Drive*: buscar documentos en Google Drive
- *Consultas generales*: clima, información útil, etc.

Contexto:
- Fecha y hora actual: {current_time}
- Zona horaria: America/Argentina/Cordoba (UTC-3)
- Ubicación por defecto: Córdoba, Argentina

Reglas:
- Respondé siempre en español
- Sé conciso y profesional
- Para fechas, usá formato argentino (DD/MM/YYYY)
- Cuando te pidan "esta semana", considerá de lunes a viernes de la semana actual
- Cuando te pidan "vencimientos", buscá eventos del calendario
- Para el clima, usá Córdoba, Argentina por defecto
- Las respuestas van por WhatsApp: usá texto plano, *negrita* con asteriscos, guiones para listas. Sin markdown complejo
- Si te piden agendar algo y falta información (hora, duración), preguntá antes de crear el evento
- La duración por defecto de una reunión es 1 hora
- Para casos, siempre confirmá antes de cambiar el estado a cerrado o archivado
- Cuando registres tiempo, confirmá el registro con un resumen claro

Cuando alguien te pregunte qué podés hacer, ayuda, comandos, o similares, respondé EXACTAMENTE esto (sin agregar ni quitar nada):

*Soy el asistente del Estudio Del Castillo* 👋

*📅 Calendario*
- Vencimientos de esta semana / mes
- Eventos de hoy / próximos días
- Agendar reunión con [persona] el [día] a las [hora]
- Buscar evento [texto]

*⚖️ Casos*
- Crear caso: [carátula], cliente [nombre], materia [materia]
- Buscar caso [texto]
- Ver caso [número]
- Listar casos activos
- Actualizar estado del caso [id] a cerrado/archivado

*⏱️ Tiempo*
- Registrar [N] horas de [abogado] en caso [id]: [descripción]
- Resumen de horas de [abogado] este mes
- Horas del caso [id]

*📝 Notas*
- Guardar nota: [texto] (puede vincularse a un caso)
- Buscar nota [texto]
- Notas del caso [id]

*📁 Drive*
- Buscar documento [texto]
- Listar carpeta [nombre]

*🌤️ General*
- Clima de hoy / mañana
- Cualquier consulta general"""

ALL_TOOLS = calendar_tools + drive_tools + weather_tools + casos_tools + tiempo_tools + notas_tools

# Simple conversation memory: last exchanges per chat
_history: dict[str, list[dict]] = defaultdict(list)
_MAX_HISTORY = 6  # max message pairs to keep


def _get_history(chat_id: str) -> list[dict]:
    """Return conversation history in Claude API message format."""
    messages = []
    for pair in _history[chat_id][-_MAX_HISTORY:]:
        messages.append({"role": "user", "content": pair["user"]})
        messages.append({"role": "assistant", "content": pair["assistant"]})
    return messages


def _save_history(chat_id: str, user_msg: str, assistant_msg: str):
    _history[chat_id].append({"user": user_msg, "assistant": assistant_msg})
    if len(_history[chat_id]) > _MAX_HISTORY * 2:
        _history[chat_id] = _history[chat_id][-_MAX_HISTORY:]


async def process_message(message: str, sender_name: str, chat_id: str) -> str:
    now = datetime.now(ZoneInfo(TIMEZONE))
    current_time = now.strftime("%A %d/%m/%Y %H:%M")
    system = SYSTEM_PROMPT.replace("{current_time}", current_time)

    user_content = f"[{sender_name}]: {message}"

    # Build messages with history
    messages = _get_history(chat_id) + [{"role": "user", "content": user_content}]

    # Tool-use loop (max 8 iterations to prevent runaway)
    for _ in range(8):
        response = await client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            system=system,
            tools=ALL_TOOLS,
            messages=messages,
        )

        if response.stop_reason == "tool_use":
            # Serialize assistant content for message history
            assistant_blocks = []
            tool_results = []

            for block in response.content:
                if block.type == "text":
                    assistant_blocks.append({"type": "text", "text": block.text})
                elif block.type == "tool_use":
                    assistant_blocks.append(
                        {
                            "type": "tool_use",
                            "id": block.id,
                            "name": block.name,
                            "input": block.input,
                        }
                    )
                    result = await _handle_tool(block.name, block.input)
                    logger.info("Tool %s -> %s", block.name, json.dumps(result, ensure_ascii=False, default=str)[:200])
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": json.dumps(result, ensure_ascii=False, default=str),
                        }
                    )

            messages.append({"role": "assistant", "content": assistant_blocks})
            messages.append({"role": "user", "content": tool_results})
        else:
            # Final text response
            text_parts = [b.text for b in response.content if hasattr(b, "text")]
            answer = "\n".join(text_parts) if text_parts else "No pude procesar tu consulta."

            _save_history(chat_id, user_content, answer)
            return answer

    return "Se excedió el límite de procesamiento. Intentá reformular tu consulta."


async def _handle_tool(name: str, input_data: dict) -> dict:
    # Pasar CALENDAR_ID si no está especificado
    if name.startswith("calendar_") and "calendar_id" not in input_data:
        input_data["calendar_id"] = CALENDAR_ID

    if name.startswith("calendar_"):
        return await handle_calendar_tool(name, input_data)
    elif name.startswith("drive_"):
        return await handle_drive_tool(name, input_data)
    elif name.startswith("weather_"):
        return await handle_weather_tool(name, input_data)
    elif name.startswith("casos_"):
        return await handle_casos_tool(name, input_data)
    elif name.startswith("tiempo_"):
        return await handle_tiempo_tool(name, input_data)
    elif name.startswith("notas_"):
        return await handle_notas_tool(name, input_data)
    return {"error": f"Tool desconocido: {name}"}
