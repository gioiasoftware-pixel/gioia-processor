import uvicorn
import os
import logging
from dotenv import load_dotenv

# Carica variabili ambiente
load_dotenv()

# Configurazione logging colorato PRIMA di qualsiasi altro import che usa logging
from core.logger import setup_colored_logging
setup_colored_logging("processor")

logger = logging.getLogger(__name__)

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8001))
    host = os.getenv("HOST", "0.0.0.0")
    
    # Verifica variabili ambiente critiche
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        logger.warning("DATABASE_URL not set - database operations may fail")
    else:
        logger.info("Database URL configured")
    
    workers = int(os.getenv("UVICORN_WORKERS", "4"))  # Default 4 workers
    
    logger.info(f"Starting Gioia Processor on {host}:{port} with {workers} workers")
    logger.info(f"Environment: {os.getenv('ENVIRONMENT', 'production')}")
    
    try:
        # Usa nuovo api.main invece di main vecchio
        # Il logging è già configurato da setup_colored_logging sopra
        # uvicorn userà il root logger configurato
        uvicorn.run(
            "api.main:app",
            host=host,
            port=port,
            workers=workers,  # Multi-worker per concorrenza
            reload=False,
            log_level="info",
            access_log=True,
            use_colors=False  # Disabilita colori di uvicorn, usiamo colorlog
        )
    except Exception as e:
        logger.error(f"Failed to start server: {e}")
        raise
