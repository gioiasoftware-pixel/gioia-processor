import os
import logging
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# Carica variabili ambiente
DATABASE_URL = os.getenv("DATABASE_URL")
PORT = int(os.getenv("PORT", 8001))
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

# Configurazione processor
PROCESSOR_NAME = "Gioia Processor"
PROCESSOR_VERSION = "1.0.0"

def validate_config():
    """Valida le configurazioni critiche all'avvio."""
    errors = []
    
    if not DATABASE_URL:
        errors.append("DATABASE_URL non configurato")
    
    if not OPENAI_API_KEY:
        logger.warning("OPENAI_API_KEY non configurato - AI features disabilitate")
    
    if errors:
        error_msg = "❌ Configurazione processor mancante:\n" + "\n".join(f"  - {error}" for error in errors)
        logger.error(error_msg)
        raise ValueError(error_msg)
    
    logger.info("✅ Configurazione processor validata con successo")
    return True


