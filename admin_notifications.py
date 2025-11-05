"""
Gestione notifiche admin per gioia-processor.
Accoda notifiche nella tabella admin_notifications per essere processate dal bot admin.
"""
import json
import logging
from typing import Dict, Any, Optional

from core.database import get_db
from sqlalchemy import text as sql_text

logger = logging.getLogger(__name__)


async def enqueue_admin_notification(
    event_type: str,
    telegram_id: int,
    payload: Dict[str, Any],
    correlation_id: Optional[str] = None
) -> bool:
    """
    Accoda una notifica admin nella tabella admin_notifications.
    
    Args:
        event_type: Tipo evento ('onboarding_completed', 'inventory_uploaded', 'error', ecc.)
        telegram_id: ID Telegram dell'utente
        payload: Dizionario con dettagli evento (business_name, error_message, ecc.)
        correlation_id: ID correlazione per debugging (opzionale)
    
    Returns:
        True se inserita con successo, False altrimenti
    """
    try:
        # Serializza payload in JSON
        payload_json = json.dumps(payload)
        
        # Inserisci nella tabella admin_notifications usando get_db()
        async for db in get_db():
            query = sql_text("""
                INSERT INTO admin_notifications 
                (event_type, telegram_id, correlation_id, payload, status)
                VALUES (:event_type, :telegram_id, :correlation_id, :payload::jsonb, 'pending')
            """)
            
            await db.execute(
                query,
                {
                    "event_type": event_type,
                    "telegram_id": telegram_id,
                    "correlation_id": correlation_id,
                    "payload": payload_json
                }
            )
            await db.commit()
            break
        
        logger.info(
            f"[ADMIN_NOTIF] Notifica accodata: event_type={event_type}, "
            f"telegram_id={telegram_id}, correlation_id={correlation_id}"
        )
        return True
        
    except Exception as e:
        logger.error(
            f"[ADMIN_NOTIF] Errore durante accodamento notifica: {e}",
            exc_info=True
        )
        return False

