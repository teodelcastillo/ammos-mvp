"""Configuración centralizada desde variables de entorno."""

import os

DB_PATH = os.getenv("DB_PATH", "/app/data/ammos.db")

WA_BRIDGE_URL = os.getenv("WA_BRIDGE_URL", "http://whatsapp-bridge:8080")

TIMEZONE = os.getenv("TIMEZONE", "America/Argentina/Cordoba")

# Clave para endpoints administrativos (X-Admin-Token)
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "dev-token-change-me")

# Solo mandar WhatsApp si esto está en "true". Por defecto modo dry-run
# para que el equipo pueda probar sin spamear durante la prueba interna.
SEND_ENABLED = os.getenv("SEND_ENABLED", "false").lower() == "true"

# Cada cuántos segundos el worker revisa la cola de mensajes programados
SCHEDULER_INTERVAL_SEC = int(os.getenv("SCHEDULER_INTERVAL_SEC", "30"))

# Rate limit básico para no saturar el bridge
MAX_MSG_PER_SEC = float(os.getenv("MAX_MSG_PER_SEC", "1"))

ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-5")
ANTHROPIC_MODEL_FAST = os.getenv("ANTHROPIC_MODEL_FAST", "claude-haiku-4-5")
