"""
Logging strutturato con telegram_id e correlation_id per processor.
"""
import json
import logging
import uuid
from typing import Optional

logger = logging.getLogger("processor")


def log_with_context(
    level: str,
    message: str,
    telegram_id: Optional[int] = None,
    correlation_id: Optional[str] = None,
    **extra
):
    """
    Log strutturato JSON con contesto utente.
    """
    payload = {
        "level": level.upper(),
        "message": message,
        "telegram_id": telegram_id,
        "correlation_id": correlation_id or str(uuid.uuid4()),
        **extra
    }
    
    logger.log(
        getattr(logging, level.upper(), logging.INFO),
        json.dumps(payload)
    )





