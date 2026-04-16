"""Cliente HTTP al whatsapp-bridge (whatsmeow)."""

import asyncio
import logging

import httpx

from config import SEND_ENABLED, WA_BRIDGE_URL, MAX_MSG_PER_SEC

logger = logging.getLogger(__name__)

_rate_lock = asyncio.Lock()
_last_sent_at: float = 0.0


def _to_jid(phone: str) -> str:
    """El bridge espera un JID tipo '5491112345678@s.whatsapp.net'."""
    if "@" in phone:
        return phone
    digits = "".join(ch for ch in phone if ch.isdigit())
    return f"{digits}@s.whatsapp.net"


async def send_text(chat_or_phone: str, message: str) -> dict:
    """Envía un mensaje vía el bridge. Si SEND_ENABLED=false, hace dry-run."""
    global _last_sent_at

    jid = _to_jid(chat_or_phone)

    if not SEND_ENABLED:
        logger.info("[dry-run] to=%s msg=%s", jid, message.replace("\n", " | ")[:200])
        return {"status": "dry-run", "to": jid}

    # Rate limit simple (1 token bucket global)
    async with _rate_lock:
        loop = asyncio.get_event_loop()
        now = loop.time()
        min_gap = 1.0 / max(MAX_MSG_PER_SEC, 0.1)
        wait = max(0.0, (_last_sent_at + min_gap) - now)
        if wait > 0:
            await asyncio.sleep(wait)
        _last_sent_at = loop.time()

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{WA_BRIDGE_URL}/send",
                json={"chat": jid, "message": message},
            )
            resp.raise_for_status()
            data = resp.json()
            logger.info("Sent to %s", jid)
            return {"status": "sent", "to": jid, **data}
    except httpx.HTTPError as exc:
        logger.exception("Error enviando al bridge")
        return {"status": "error", "error": str(exc), "to": jid}
