"""
OCR Extract (Stage 4) - Estrazione testo da PDF/immagini.

Usa pytesseract (+ pdf2image per PDF).
Output testo → passa a LLM mode (Stage 3).
Conforme a "Update processor.md" - Stage 4: OCR.
"""
import logging
import time
from typing import List, Dict, Any, Optional, Tuple
import pytesseract
from PIL import Image
import io
from pdf2image import convert_from_bytes
from core.config import get_config
from core.logger import log_json
from ingest.llm_extract import extract_llm_mode

logger = logging.getLogger(__name__)


def extract_text_from_image(image_content: bytes) -> str:
    """
    Estrae testo da immagine usando pytesseract.
    
    Conforme a "Update processor.md" - Stage 4: OCR.
    
    Args:
        image_content: Contenuto immagine (bytes)
    
    Returns:
        Testo estratto
    """
    try:
        # Apri immagine
        image = Image.open(io.BytesIO(image_content))
        logger.debug(f"[OCR] Image loaded: {image.size}, mode: {image.mode}")
        
        # Converti in RGB se necessario
        if image.mode != 'RGB':
            image = image.convert('RGB')
        
        # Esegui OCR (italiano + inglese)
        ocr_text = pytesseract.image_to_string(image, lang='ita+eng')
        
        logger.info(f"[OCR] OCR extracted {len(ocr_text)} characters from image")
        return ocr_text
        
    except Exception as e:
        logger.error(f"[OCR] Error extracting text from image: {e}", exc_info=True)
        raise


def extract_text_from_pdf(pdf_content: bytes) -> str:
    """
    Estrae testo da PDF usando pdf2image + pytesseract.
    
    Conforme a "Update processor.md" - Stage 4: OCR.
    Rasterizza PDF in immagini e applica OCR.
    
    Args:
        pdf_content: Contenuto PDF (bytes)
    
    Returns:
        Testo estratto (concatenato da tutte le pagine)
    """
    try:
        # Rasterizza PDF in immagini
        images = convert_from_bytes(pdf_content)
        logger.info(f"[OCR] PDF converted to {len(images)} images")
        
        # Estrai testo da ogni pagina
        all_text = []
        for page_idx, image in enumerate(images):
            try:
                # Converti in RGB se necessario
                if image.mode != 'RGB':
                    image = image.convert('RGB')
                
                # OCR
                page_text = pytesseract.image_to_string(image, lang='ita+eng')
                all_text.append(page_text)
                logger.debug(f"[OCR] Page {page_idx + 1}/{len(images)}: {len(page_text)} characters")
            except Exception as e:
                logger.warning(f"[OCR] Error processing page {page_idx + 1}: {e}")
                continue
        
        # Concatena testo di tutte le pagine
        full_text = '\n\n'.join(all_text)
        
        logger.info(f"[OCR] OCR extracted {len(full_text)} total characters from PDF ({len(images)} pages)")
        return full_text
        
    except Exception as e:
        logger.error(f"[OCR] Error extracting text from PDF: {e}", exc_info=True)
        raise


async def extract_ocr(
    file_content: bytes,
    file_name: str,
    ext: str,
    telegram_id: Optional[int] = None,
    correlation_id: Optional[str] = None
) -> Tuple[List[Dict[str, Any]], Dict[str, Any], str]:
    """
    Orchestratore Stage 4: Estrazione OCR da PDF/immagini.
    
    Flow:
    1. Rileva tipo file (PDF o immagine)
    2. Estrae testo con OCR (pytesseract + pdf2image per PDF)
    3. Passa testo a Stage 3 (LLM mode) per estrazione vini
    4. Ritorna risultati Stage 3
    
    Conforme a "Update processor.md" - Stage 4: OCR.
    
    NOTA: Non usare OCR su CSV/Excel (devono andare a Stage 1).
    
    Args:
        file_content: Contenuto file (bytes)
        file_name: Nome file
        ext: Estensione file
    
    Returns:
        Tuple (wines_data, metrics, decision):
        - wines_data: Lista dict con vini estratti (da Stage 3)
        - metrics: Dict con metriche (OCR + Stage 3)
        - decision: 'save' o 'error' (da Stage 3)
    """
    start_time = time.time()
    config = get_config()
    
    if not config.ocr_enabled:
        logger.warning("[OCR] Stage 4 disabilitato (OCR_ENABLED=false)")
        return [], {'error': 'OCR disabilitato'}, 'error'
    
    try:
        # Verifica che sia un formato supportato per OCR
        if ext not in ['pdf', 'jpg', 'jpeg', 'png']:
            logger.error(f"[OCR] Formato non supportato per OCR: {ext}")
            return [], {'error': f'Formato {ext} non supportato per OCR'}, 'error'
        
        # 1. Estrai testo con OCR
        ocr_text = ""
        ocr_info = {}
        
        if ext == 'pdf':
            try:
                ocr_text = extract_text_from_pdf(file_content)
                # Conta pagine (approximativo)
                try:
                    from pdf2image import convert_from_bytes
                    images = convert_from_bytes(file_content)
                    ocr_info['pages'] = len(images)
                except:
                    ocr_info['pages'] = 1
            except Exception as e:
                logger.error(f"[OCR] Error extracting text from PDF: {e}", exc_info=True)
                return [], {'error': f'Errore OCR PDF: {str(e)}'}, 'error'
        else:  # jpg, jpeg, png
            try:
                ocr_text = extract_text_from_image(file_content)
                ocr_info['pages'] = 1
            except Exception as e:
                logger.error(f"[OCR] Error extracting text from image: {e}", exc_info=True)
                return [], {'error': f'Errore OCR immagine: {str(e)}'}, 'error'
        
        if not ocr_text or len(ocr_text.strip()) == 0:
            logger.warning("[OCR] Nessun testo estratto da OCR")
            return [], {'error': 'Nessun testo estratto da OCR'}, 'error'
        
        ocr_info['text_length'] = len(ocr_text)
        ocr_info['engine'] = 'tesseract'
        ocr_elapsed_sec = time.time() - start_time
        ocr_info['elapsed_sec'] = ocr_elapsed_sec
        
        logger.info(f"[OCR] OCR completed: {len(ocr_text)} characters in {ocr_elapsed_sec:.2f}s")
        
        # 2. Passa testo a Stage 3 (LLM mode)
        # Stage 3 ha prepare_text_input che gestisce CSV/Excel, ma possiamo
        # passare il testo come file_content bytes e Stage 3 lo processerà
        # come testo grezzo nel suo prepare_text_input
        text_bytes = ocr_text.encode('utf-8')
        
        # Chiama Stage 3 (LLM mode) con testo estratto
        # Stage 3 gestirà il testo grezzo correttamente
        wines_data, llm_metrics, decision = await extract_llm_mode(
            file_content=text_bytes,
            file_name=file_name,
            ext='txt',  # Estensione fittizia per testo puro (Stage 3 lo gestirà come testo)
            telegram_id=telegram_id,
            correlation_id=correlation_id
        )
        
        # Combina metriche OCR + Stage 3
        combined_metrics = {
            **ocr_info,
            **llm_metrics,
            'stage': 'ocr',
            'ocr_elapsed_sec': ocr_elapsed_sec
        }
        
        total_elapsed_sec = time.time() - start_time
        combined_metrics['total_elapsed_sec'] = total_elapsed_sec
        
        # Logging JSON strutturato
        log_json(
            level='info' if decision == 'save' else 'error',
            message=f"Stage 4 completed: decision={decision}",
            file_name=file_name,
            ext=ext,
            stage='ocr',
            rows_valid=combined_metrics.get('rows_valid', 0),
            rows_rejected=combined_metrics.get('rows_rejected', 0),
            elapsed_sec=total_elapsed_sec,
            decision=decision,
            pages=ocr_info.get('pages', 1),
            text_length=ocr_info.get('text_length', 0)
        )
        
        logger.info(
            f"[OCR] Stage 4 SUCCESS: {combined_metrics.get('rows_valid', 0)} vini estratti "
            f"in {total_elapsed_sec:.2f}s (OCR: {ocr_elapsed_sec:.2f}s)"
        )
        
        return wines_data, combined_metrics, decision
        
    except Exception as e:
        elapsed_sec = time.time() - start_time
        logger.error(f"[OCR] Errore in Stage 4: {e}", exc_info=True)
        
        # Log errore
        log_json(
            level='error',
            message=f"Stage 4 failed: {str(e)}",
            file_name=file_name,
            ext=ext,
            stage='ocr',
            elapsed_sec=elapsed_sec,
            decision='error'
        )
        
        return [], {'error': str(e)}, 'error'

