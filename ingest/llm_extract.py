"""
LLM Extract (Stage 3) - Estrazione tabellare da testo grezzo.

Usare solo quando Stage 1+2 falliscono.
Conforme a "Update processor.md" - Stage 3: LLM mode.
"""
import json
import logging
import time
import pandas as pd
import io
from typing import List, Dict, Any, Optional, Tuple
import openai
from core.config import get_config
from core.logger import log_json
from ingest.validation import validate_batch, wine_model_to_dict
from ingest.normalization import normalize_values

logger = logging.getLogger(__name__)

# Inizializza client OpenAI
_openai_client = None


def get_openai_client():
    """Ottiene client OpenAI (singleton)."""
    global _openai_client
    if _openai_client is None:
        config = get_config()
        api_key = config.openai_api_key
        if not api_key:
            raise ValueError("OPENAI_API_KEY non configurato")
        _openai_client = openai.OpenAI(api_key=api_key)
    return _openai_client


def prepare_text_input(
    file_content: bytes,
    ext: str
) -> str:
    """
    Prepara input testo per LLM mode.
    
    Conforme a "Update processor.md" - Stage 3: Preparazione input.
    
    Per CSV rotti: prendi intero file come testo grezzo (max 40-80 KB) o sampling.
    Per Excel rovinati: leggi celle raw e serializza in testo "riga per riga".
    
    Args:
        file_content: Contenuto file (bytes)
        ext: Estensione file
    
    Returns:
        Testo significativo pronto per LLM
    """
    max_bytes = 80 * 1024  # 80 KB max
    
    try:
        if ext in ['csv', 'tsv', 'txt']:
            # CSV/TSV/TXT: decodifica e prendi tutto (o primi 80 KB)
            # 'txt' è usato per testo OCR puro
            try:
                # Prova encoding comuni
                for encoding in ['utf-8-sig', 'utf-8', 'latin-1', 'cp1252']:
                    try:
                        text = file_content[:max_bytes].decode(encoding)
                        logger.debug(f"[LLM_EXTRACT] Text decoded with {encoding}")
                        return text
                    except (UnicodeDecodeError, LookupError):
                        continue
                
                # Fallback: utf-8 con errors='ignore'
                text = file_content[:max_bytes].decode('utf-8', errors='ignore')
                return text
            except Exception as e:
                logger.warning(f"[LLM_EXTRACT] Error decoding text: {e}")
                return str(file_content[:max_bytes])
        
        elif ext in ['xlsx', 'xls']:
            # Excel: leggi celle raw e serializza in testo "riga per riga"
            try:
                df = pd.read_excel(io.BytesIO(file_content), dtype=str)
                # Serializza in testo riga per riga
                lines = []
                for index, row in df.iterrows():
                    row_text = ' | '.join([str(val) if pd.notna(val) else '' for val in row.values])
                    lines.append(row_text)
                text = '\n'.join(lines)
                
                # Limita a 80 KB
                if len(text.encode('utf-8')) > max_bytes:
                    text = text[:max_bytes]
                
                logger.debug(f"[LLM_EXTRACT] Excel serialized to text: {len(lines)} lines")
                return text
            except Exception as e:
                logger.warning(f"[LLM_EXTRACT] Error reading Excel: {e}")
                return str(file_content[:max_bytes])
        
        else:
            # Altri formati: prova come testo
            try:
                text = file_content[:max_bytes].decode('utf-8', errors='ignore')
                return text
            except Exception:
                return str(file_content[:max_bytes])
    
    except Exception as e:
        logger.error(f"[LLM_EXTRACT] Error preparing text input: {e}", exc_info=True)
        return str(file_content[:max_bytes])


def chunk_text(text: str, chunk_size: int = 40 * 1024, overlap: int = 1000) -> List[str]:
    """
    Spezza testo in blocchi con sovrapposizione minima.
    
    Conforme a "Update processor.md" - Stage 3: Chunking.
    
    Args:
        text: Testo da spezzare
        chunk_size: Dimensione chunk in bytes (default 40 KB)
        overlap: Overlap tra chunk in bytes (default 1000)
    
    Returns:
        Lista di chunk di testo
    """
    text_bytes = text.encode('utf-8')
    chunks = []
    
    if len(text_bytes) <= chunk_size:
        return [text]
    
    start = 0
    while start < len(text_bytes):
        end = start + chunk_size
        
        # Tenta di tagliare a fine riga
        if end < len(text_bytes):
            # Cerca ultimo '\n' prima di end
            last_newline = text_bytes.rfind(b'\n', start, end)
            if last_newline > start:
                end = last_newline + 1
        
        chunk = text_bytes[start:end].decode('utf-8', errors='ignore')
        chunks.append(chunk)
        
        # Prossimo chunk con overlap
        start = end - overlap
        if start >= len(text_bytes):
            break
    
    logger.info(f"[LLM_EXTRACT] Text chunked: {len(chunks)} chunks from {len(text_bytes)} bytes")
    return chunks


async def extract_with_llm(text_chunk: str, telegram_id: Optional[int] = None, correlation_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Estrae vini da chunk testo usando Prompt P3 (estrazione tabellare).
    
    Prompt P3 conforme a "Update processor.md" - Sezione "Prompt pronti".
    
    Args:
        text_chunk: Chunk di testo (20-40 KB)
    
    Returns:
        Lista dict con vini estratti
    """
    config = get_config()
    
    if not config.llm_fallback_enabled:
        logger.warning("[LLM_EXTRACT] Stage 3 disabilitato (LLM_FALLBACK_ENABLED=false)")
        return []
    
    try:
        client = get_openai_client()
        
        # Prompt P3
        prompt = f"""Sei un estrattore di tabelle inventario vini.

Obiettivo:
- Dal testo fornito, estrai una lista di voci vino nel seguente schema JSON:
  {{ "name": string, "winery": string|null, "vintage": int|null, "qty": int>=0, "price": float|null, "type": string|null }}

Regole:
- "vintage" deve essere 1900–2099 oppure null.
- "qty" deve essere un intero (es. "12 bottiglie" → 12).
- "price" in EUR: accetta virgola (es. 8,50 → 8.5). Se assente → null.
- "type": una di [Rosso, Bianco, Rosato, Spumante, Altro]; se incerto → null.
- Ignora righe che non siano vini (totali, note, sconti).
- Output SOLO JSON (array di oggetti), nessun testo extra.

Testo:
<<<
{text_chunk}
>>>
"""
        
        response = client.chat.completions.create(
            model=config.llm_model_extract,
            messages=[
                {
                    "role": "system",
                    "content": "Sei un estrattore di tabelle inventario vini. Estrai dati vini da testo. Rispondi SOLO con JSON array."
                },
                {"role": "user", "content": prompt}
            ],
            temperature=0.1,
            max_tokens=4000
        )
        
        # Alert costi LLM se necessario
        try:
            from core.alerting import check_llm_cost_alert, estimate_llm_cost
            import tiktoken
            
            # Stima token (approssimativo)
            encoding = tiktoken.encoding_for_model(config.llm_model_extract)
            input_tokens = len(encoding.encode(prompt))
            output_tokens = response.usage.completion_tokens if hasattr(response, 'usage') and response.usage else 0
            
            # Stima costo
            estimated_cost = estimate_llm_cost(
                model=config.llm_model_extract,
                input_tokens=input_tokens,
                output_tokens=output_tokens
            )
            
            # Verifica alert
            check_llm_cost_alert(
                estimated_cost=estimated_cost,
                telegram_id=telegram_id,
                correlation_id=correlation_id,
                threshold=0.50,  # Alert se > 0.50€ in 60 min
                window_minutes=60
            )
        except Exception as alert_error:
            logger.debug(f"[ALERT] Error checking LLM cost alert: {alert_error}")
        
        result_text = response.choices[0].message.content.strip()
        
        # Estrai JSON (rimuovi markdown code blocks se presenti)
        if result_text.startswith("```"):
            result_text = result_text.split("```")[1]
            if result_text.startswith("json"):
                result_text = result_text[4:]
            result_text = result_text.strip()
        
        wines = json.loads(result_text)
        
        # Verifica che sia un array
        if not isinstance(wines, list):
            logger.warning("[LLM_EXTRACT] Risposta AI non è un array, ritorno vuoto")
            return []
        
        logger.info(f"[LLM_EXTRACT] Estratti {len(wines)} vini da chunk")
        return wines
        
    except json.JSONDecodeError as e:
        logger.error(f"[LLM_EXTRACT] Errore parsing JSON da AI: {e}")
        logger.debug(f"[LLM_EXTRACT] Risposta AI: {result_text[:500]}")
        return []
    except Exception as e:
        logger.error(f"[LLM_EXTRACT] Errore estrazione LLM: {e}", exc_info=True)
        return []


def deduplicate_wines(wines: List[Dict[str, Any]], merge_quantities: bool = True) -> List[Dict[str, Any]]:
    """
    Deduplica righe simili (name+winery+vintage), somma qty se necessario.
    
    Conforme a "Update processor.md" - Stage 3: Unione blocchi.
    
    Args:
        wines: Lista vini
        merge_quantities: Se True, somma quantità di duplicati
    
    Returns:
        Lista vini deduplicati
    """
    seen = {}
    deduplicated = []
    
    for wine in wines:
        # Crea chiave univoca: name+winery+vintage
        name = str(wine.get('name', '')).lower().strip()
        winery = str(wine.get('winery', '')).lower().strip() if wine.get('winery') else ''
        vintage = wine.get('vintage')
        
        key = (name, winery, vintage)
        
        if key in seen:
            # Duplicato trovato
            existing_wine = seen[key]
            if merge_quantities:
                # Somma quantità
                existing_qty = existing_wine.get('qty', 0) or 0
                new_qty = wine.get('qty', 0) or 0
                existing_wine['qty'] = existing_qty + new_qty
                
                # Mantieni dati più completi (preferisci valori non null)
                for field in ['winery', 'vintage', 'price', 'type']:
                    if not existing_wine.get(field) and wine.get(field):
                        existing_wine[field] = wine[field]
        else:
            seen[key] = wine.copy()
            deduplicated.append(seen[key])
    
    logger.info(
        f"[LLM_EXTRACT] Deduplicazione: {len(wines)} -> {len(deduplicated)} vini "
        f"({len(wines) - len(deduplicated)} duplicati rimossi)"
    )
    
    return deduplicated


async def extract_llm_mode(
    file_content: bytes,
    file_name: str,
    ext: str,
    telegram_id: Optional[int] = None,
    correlation_id: Optional[str] = None
) -> Tuple[List[Dict[str, Any]], Dict[str, Any], str]:
    """
    Orchestratore Stage 3: Estrazione LLM mode da testo grezzo.
    
    Flow:
    1. Prepara input testo (CSV/Excel → testo grezzo)
    2. Chunking se >80 KB (blocchi 20-40 KB con sovrapposizione)
    3. Estrae da ogni chunk con LLM (Prompt P3)
    4. Unisce risultati
    5. Deduplica (name+winery+vintage), somma qty se necessario
    6. Validazione finale con Pydantic
    7. Se 0 valide → fallimento, altrimenti → SALVA
    
    Conforme a "Update processor.md" - Stage 3: LLM mode.
    
    Args:
        file_content: Contenuto file (bytes)
        file_name: Nome file
        ext: Estensione file
    
    Returns:
        Tuple (wines_data, metrics, decision):
        - wines_data: Lista dict con vini validi
        - metrics: Dict con metriche (rows_valid, rows_rejected, chunks, etc.)
        - decision: 'save' se OK, 'error' se fallimento
    """
    start_time = time.time()
    config = get_config()
    
    if not config.llm_fallback_enabled:
        logger.warning("[LLM_EXTRACT] Stage 3 disabilitato (LLM_FALLBACK_ENABLED=false)")
        return [], {'error': 'Stage 3 disabilitato'}, 'error'
    
    try:
        # 1. Prepara input testo
        text = prepare_text_input(file_content, ext)
        
        if not text or len(text.strip()) == 0:
            logger.error("[LLM_EXTRACT] Testo vuoto dopo preparazione")
            return [], {'error': 'Testo vuoto'}, 'error'
        
        # 2. Chunking se >80 KB
        chunks = chunk_text(text, chunk_size=40 * 1024, overlap=1000)
        
        # 3. Estrae da ogni chunk
        all_wines = []
        for chunk_idx, chunk in enumerate(chunks):
            try:
                wines_chunk = await extract_with_llm(chunk, telegram_id=telegram_id, correlation_id=correlation_id)
                all_wines.extend(wines_chunk)
                logger.debug(f"[LLM_EXTRACT] Chunk {chunk_idx + 1}/{len(chunks)}: {len(wines_chunk)} vini")
            except Exception as e:
                logger.warning(f"[LLM_EXTRACT] Errore chunk {chunk_idx + 1}: {e}")
                # Alert costi LLM per ogni chunk (gestito in extract_with_llm)
                continue
        
        if not all_wines:
            logger.warning("[LLM_EXTRACT] Nessun vino estratto da LLM")
            return [], {'error': 'Nessun vino estratto'}, 'error'
        
        # 4. Deduplica righe simili
        deduplicated_wines = deduplicate_wines(all_wines, merge_quantities=True)
        
        # 5. Normalizza valori
        normalized_wines = []
        for wine in deduplicated_wines:
            try:
                normalized = normalize_values(wine)
                if normalized.get('name'):  # Solo se ha name
                    normalized_wines.append(normalized)
            except Exception as e:
                logger.debug(f"[LLM_EXTRACT] Errore normalizzazione vino: {e}")
                continue
        
        # 6. Validazione finale con Pydantic
        valid_wines, rejected_wines, validation_stats = validate_batch(normalized_wines)
        
        # Converti WineItemModel in dict
        wines_data_valid = [wine_model_to_dict(wine) for wine in valid_wines]
        
        rows_valid = validation_stats['rows_valid']
        rows_rejected = validation_stats['rows_rejected']
        
        elapsed_sec = time.time() - start_time
        
        metrics = {
            'rows_total': len(normalized_wines),
            'rows_valid': rows_valid,
            'rows_rejected': rows_rejected,
            'rejection_reasons': validation_stats['rejection_reasons'],
            'chunks': len(chunks),
            'wines_extracted': len(all_wines),
            'wines_deduplicated': len(deduplicated_wines),
            'elapsed_sec': elapsed_sec
        }
        
        # 7. Decisione: se 0 valide → fallimento, altrimenti → SALVA
        if rows_valid == 0:
            decision = 'error'
            logger.error(
                f"[LLM_EXTRACT] Stage 3 FAILED: 0 righe valide su {len(normalized_wines)} estratte"
            )
        else:
            decision = 'save'
            logger.info(
                f"[LLM_EXTRACT] Stage 3 SUCCESS: {rows_valid} righe valide su {len(normalized_wines)} estratte"
            )
        
        # Logging JSON strutturato
        log_json(
            level='info' if decision == 'save' else 'error',
            message=f"Stage 3 completed: decision={decision}",
            file_name=file_name,
            ext=ext,
            stage='llm_mode',
            rows_total=len(normalized_wines),
            rows_valid=rows_valid,
            rows_rejected=rows_rejected,
            elapsed_sec=elapsed_sec,
            decision=decision,
            chunks=len(chunks)
        )
        
        return wines_data_valid, metrics, decision
        
    except Exception as e:
        elapsed_sec = time.time() - start_time
        logger.error(f"[LLM_EXTRACT] Errore in Stage 3: {e}", exc_info=True)
        
        # Log errore
        log_json(
            level='error',
            message=f"Stage 3 failed: {str(e)}",
            file_name=file_name,
            ext=ext,
            stage='llm_mode',
            elapsed_sec=elapsed_sec,
            decision='error'
        )
        
        # Alert se Stage 3 fallisce spesso
        try:
            from core.alerting import check_stage3_failure_alert
            # Nota: check_stage3_failure_alert è sincrona, può essere chiamata da async
            check_stage3_failure_alert(
                telegram_id=telegram_id,
                correlation_id=correlation_id,
                threshold=5,  # Alert se 5+ fallimenti in 60 min
                window_minutes=60
            )
        except Exception as alert_error:
            logger.warning(f"[ALERT] Error checking Stage 3 failure alert: {alert_error}")
        
        return [], {'error': str(e)}, 'error'

