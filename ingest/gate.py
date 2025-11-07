"""
Gate (Stage 0) - Routing file per tipo.

Determina il percorso della pipeline in base all'estensione del file.
"""
import logging
from typing import Tuple, Optional

logger = logging.getLogger(__name__)


def route_file(file_content: bytes, file_name: str, ext: Optional[str] = None) -> Tuple[str, str]:
    """
    Route file in base all'estensione per determinare stage iniziale.
    
    Args:
        file_content: Contenuto file (bytes)
        file_name: Nome file
        ext: Estensione file (se None, estrae da file_name)
    
    Returns:
        Tuple (stage, ext):
        - stage: 'csv_excel' per CSV/Excel → Stage 1, 'ocr' per PDF/immagini → Stage 4
        - ext: Estensione normalizzata (lowercase, senza punto)
    
    Raises:
        ValueError: Se formato file non supportato
    """
    # Estrai estensione se non fornita
    if ext is None:
        if '.' in file_name:
            ext = file_name.rsplit('.', 1)[-1].lower()
        else:
            raise ValueError(f"Impossibile determinare estensione file: {file_name}")
    
    # Normalizza estensione
    ext = ext.lower().strip().lstrip('.')
    
    # Stage 1: CSV/Excel (parser classico)
    if ext in ['csv', 'tsv', 'xlsx', 'xls']:
        logger.info(f"[GATE] File {file_name} routed to Stage 1 (CSV/Excel parser)")
        return 'csv_excel', ext
    
    # Stage 4: OCR (PDF/immagini)
    if ext in ['pdf', 'jpg', 'jpeg', 'png']:
        logger.info(f"[GATE] File {file_name} routed to Stage 4 (OCR)")
        return 'ocr', ext
    
    # Formato non supportato
    error_msg = f"Formato file non supportato: .{ext}. Supportati: CSV, TSV, XLSX, XLS, PDF, JPG, JPEG, PNG"
    logger.error(f"[GATE] {error_msg}")
    raise ValueError(error_msg)





