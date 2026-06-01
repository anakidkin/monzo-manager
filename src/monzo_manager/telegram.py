import httpx

from monzo_manager.config import settings
from monzo_manager.log import setup_rotating_logger

logger = setup_rotating_logger()


async def send_telegram_notification(message: str):
    """Sends a formatted HTML message to the configured Telegram chat."""
    url = f"https://api.telegram.org/bot{settings.tg_token}/sendMessage"
    payload = {
        "chat_id": settings.tg_chat_id,
        "text": message,
        "parse_mode": "HTML"
    }

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, json=payload)
            if response.status_code != 200:
                logger.error(f"❌ Failed to send Telegram notification: {response.text}")
        except Exception:
            logger.exception("❌ Telegram API is unavailable")
