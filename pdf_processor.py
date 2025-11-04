"""
Processore PDF per estrazione dati inventario vini
NOTA: Funzionalità PDF non ancora implementata
"""
import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)


async def process_pdf_file(file_content: bytes, file_name: str = "") -> List[Dict[str, Any]]:
    """
    Processa file PDF e estrae dati sui vini.
    
    NOTA: Funzionalità PDF non ancora implementata.
    Questa funzione solleva NotImplementedError.
    
    Args:
        file_content: Contenuto del file PDF come bytes
        file_name: Nome del file (opzionale)
        
    Returns:
        Lista di dizionari con dati vini
        
    Raises:
        NotImplementedError: Funzionalità PDF non ancora implementata
    """
    logger.warning(
        f"[PDF_PROCESSOR] Tentativo di processare file PDF: {file_name} "
        f"(size={len(file_content)} bytes) - Funzionalità non implementata"
    )
    raise NotImplementedError(
        "Processamento PDF non ancora implementato. "
        "Usa file CSV, Excel o immagini per il momento."
    )

