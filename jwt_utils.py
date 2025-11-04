"""
Utility per validazione token JWT per viewer
"""
import jwt
import os
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

# Secret key condivisa con bot (da variabile ambiente)
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "change-me-in-production-secret-key-2025")
JWT_ALGORITHM = "HS256"


def validate_viewer_token(token: str) -> Optional[Dict[str, Any]]:
    """
    Valida token JWT per viewer.
    
    Args:
        token: Token JWT da validare
        
    Returns:
        Dict con telegram_id e business_name se valido, None se non valido o scaduto
    """
    try:
        if not token:
            logger.warning("[JWT_VALIDATE] Token vuoto")
            return None
        
        # Verifica configurazione
        if not JWT_SECRET_KEY or JWT_SECRET_KEY == "change-me-in-production-secret-key-2025":
            logger.warning("[JWT_VALIDATE] JWT_SECRET_KEY non configurata o default!")
        
        # Decodifica e valida token
        payload = jwt.decode(
            token,
            JWT_SECRET_KEY,
            algorithms=[JWT_ALGORITHM]
        )
        
        # Estrai dati necessari
        telegram_id = payload.get("telegram_id")
        business_name = payload.get("business_name")
        
        if not telegram_id or not business_name:
            logger.warning(
                f"[JWT_VALIDATE] Token valido ma payload incompleto: "
                f"telegram_id={telegram_id}, business_name={business_name}"
            )
            return None
        
        logger.info(
            f"[JWT_VALIDATE] Token JWT validato con successo: "
            f"telegram_id={telegram_id}, business_name={business_name}"
        )
        
        return {
            "telegram_id": telegram_id,
            "business_name": business_name
        }
        
    except jwt.ExpiredSignatureError:
        logger.warning("[JWT_VALIDATE] Token JWT scaduto")
        return None
    except jwt.InvalidTokenError as e:
        logger.warning(f"[JWT_VALIDATE] Token JWT non valido: {e}")
        return None
    except Exception as e:
        logger.error(
            f"[JWT_VALIDATE] Errore durante validazione token JWT: {e}",
            exc_info=True
        )
        return None

