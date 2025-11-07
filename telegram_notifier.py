"""
Utility per inviare messaggi Telegram direttamente agli utenti dal processor.
"""
import logging
import httpx
from typing import Optional
from core.config import get_config

logger = logging.getLogger(__name__)


async def send_telegram_message(
    telegram_id: int,
    message: str,
    parse_mode: Optional[str] = "Markdown"
) -> bool:
    """
    Invia un messaggio Telegram direttamente all'utente.
    
    Args:
        telegram_id: ID Telegram dell'utente
        message: Testo del messaggio
        parse_mode: Modalità parsing (Markdown, HTML, None)
    
    Returns:
        True se inviato con successo, False altrimenti
    """
    try:
        config = get_config()
        bot_token = config.telegram_bot_token
        
        if not bot_token:
            logger.warning(
                f"[TELEGRAM_NOTIFIER] TELEGRAM_BOT_TOKEN non configurato - "
                f"impossibile inviare messaggio a {telegram_id}"
            )
            return False
        
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        
        payload = {
            "chat_id": telegram_id,
            "text": message
        }
        
        if parse_mode:
            payload["parse_mode"] = parse_mode
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(url, json=payload)
            
            if response.status_code == 200:
                result = response.json()
                if result.get("ok"):
                    logger.info(
                        f"[TELEGRAM_NOTIFIER] Messaggio inviato con successo a {telegram_id}"
                    )
                    return True
                else:
                    error_desc = result.get("description", "Unknown error")
                    logger.warning(
                        f"[TELEGRAM_NOTIFIER] Errore API Telegram: {error_desc}"
                    )
                    return False
            else:
                error_text = response.text
                logger.warning(
                    f"[TELEGRAM_NOTIFIER] Errore HTTP {response.status_code}: {error_text}"
                )
                return False
                    
    except Exception as e:
        logger.error(
            f"[TELEGRAM_NOTIFIER] Errore invio messaggio Telegram a {telegram_id}: {e}",
            exc_info=True
        )
        return False

