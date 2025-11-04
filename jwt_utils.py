"""
Utility per validazione JWT token per viewer
"""
import jwt
import os
import logging
from typing import Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

# Secret key condivisa con bot (da variabile ambiente)
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "change-me-in-production-secret-key-2025")
JWT_ALGORITHM = "HS256"


def validate_viewer_token(token: str) -> Optional[Dict[str, Any]]:
    """
    Valida token JWT per viewer e ritorna payload se valido.
    
    Args:
        token: Token JWT string
        
    Returns:
        Dict con telegram_id e business_name se valido, None altrimenti
    """
    try:
        payload = jwt.decode(
            token,
            JWT_SECRET_KEY,
            algorithms=[JWT_ALGORITHM]
        )
        
        # Verifica campi obbligatori
        telegram_id = payload.get("telegram_id")
        business_name = payload.get("business_name")
        
        if not telegram_id or not business_name:
            logger.warning("Token JWT mancante telegram_id o business_name")
            return None
        
        return {
            "telegram_id": telegram_id,
            "business_name": business_name
        }
        
    except jwt.ExpiredSignatureError:
        logger.warning("Token JWT scaduto")
        return None
    except jwt.InvalidTokenError as e:
        logger.warning(f"Token JWT non valido: {e}")
        return None
    except Exception as e:
        logger.error(f"Errore validazione token JWT: {e}")
        return None

Utility per validazione JWT token per viewer
"""
import jwt
import os
import logging
from typing import Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

# Secret key condivisa con bot (da variabile ambiente)
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "change-me-in-production-secret-key-2025")
JWT_ALGORITHM = "HS256"


def validate_viewer_token(token: str) -> Optional[Dict[str, Any]]:
    """
    Valida token JWT per viewer e ritorna payload se valido.
    
    Args:
        token: Token JWT string
        
    Returns:
        Dict con telegram_id e business_name se valido, None altrimenti
    """
    try:
        payload = jwt.decode(
            token,
            JWT_SECRET_KEY,
            algorithms=[JWT_ALGORITHM]
        )
        
        # Verifica campi obbligatori
        telegram_id = payload.get("telegram_id")
        business_name = payload.get("business_name")
        
        if not telegram_id or not business_name:
            logger.warning("Token JWT mancante telegram_id o business_name")
            return None
        
        return {
            "telegram_id": telegram_id,
            "business_name": business_name
        }
        
    except jwt.ExpiredSignatureError:
        logger.warning("Token JWT scaduto")
        return None
    except jwt.InvalidTokenError as e:
        logger.warning(f"Token JWT non valido: {e}")
        return None
    except Exception as e:
        logger.error(f"Errore validazione token JWT: {e}")
        return None

