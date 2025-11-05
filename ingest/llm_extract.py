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
                text_raw = None
                encoding_used = None
                for encoding in ['utf-8-sig', 'utf-8', 'latin-1', 'cp1252']:
                    try:
                        text_raw = file_content[:max_bytes].decode(encoding)
                        encoding_used = encoding
                        logger.debug(f"[LLM_EXTRACT] Text decoded with {encoding}")
                        break
                    except (UnicodeDecodeError, LookupError):
                        continue
                
                if text_raw is None:
                    # Fallback: utf-8 con errors='ignore'
                    text_raw = file_content[:max_bytes].decode('utf-8', errors='ignore')
                    encoding_used = 'utf-8'
                
                # Per CSV: rimuovi header ripetuti e righe vuote eccessive per migliorare estrazione
                if ext in ['csv', 'tsv']:
                    lines = text_raw.split('\n')
                    # Identifica header (prima riga con colonne tipiche)
                    header_keywords = ['indice', 'id', 'etichetta', 'cantina', 'nome', 'name', 'winery', 'vintage', 'qty', 'quantità', 'prezzo', 'price']
                    
                    # Mantieni prima riga se è header, rimuovi duplicati
                    cleaned_lines = []
                    seen_headers = set()
                    for line in lines:
                        line_lower = line.lower()
                        # Se è un header (contiene keyword e poche virgole/separatori)
                        is_header = any(kw in line_lower for kw in header_keywords) and (',' in line or '|' in line or '\t' in line)
                        
                        if is_header:
                            # Normalizza header per confronto (rimuovi spazi, lowercase)
                            header_normalized = ' '.join(line_lower.split())
                            if header_normalized not in seen_headers:
                                seen_headers.add(header_normalized)
                                # Mantieni solo primo header, rimuovi duplicati
                                if len(seen_headers) == 1:
                                    # Non includere header nel testo per LLM (AI lo ignora comunque)
                                    continue
                                else:
                                    # Header duplicato, salta
                                    continue
                        else:
                            # Riga dati normale
                            cleaned_lines.append(line)
                    
                    text = '\n'.join(cleaned_lines)
                    logger.info(f"[LLM_EXTRACT] CSV preparato: {len(lines)} righe originali → {len(cleaned_lines)} righe (header rimossi: {len(seen_headers)-1})")
                else:
                    text = text_raw
                
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
        
        # Prompt P3 (migliorato per evitare JSON malformato e estrarre più vini)
        prompt = f"""Sei un estrattore di tabelle inventario vini.

Obiettivo:
- Dal testo fornito, estrai TUTTE le voci vino presenti nel seguente schema JSON:
  {{ "name": string, "winery": string|null, "vintage": int|null, "qty": int>=0, "price": float|null, "type": string|null }}

Cosa estrarre:
- Estrai TUTTE le righe che hanno almeno un nome vino (campo "Etichetta" o "name")
- Se una riga ha nome vino ma altri campi vuoti, estrai comunque (usa null per campi mancanti)
- Estrai anche righe con qty=0 (vini esauriti)
- Se vedi righe header (es. "Indice,ID,Etichetta,Cantina..."), ignorale
- Se vedi righe completamente vuote, ignorale
- NON ignorare righe con nome vino valido, anche se hanno dati incompleti

Regole CRITICHE per JSON valido:
- ESCAPA tutte le virgolette nei valori: se il nome contiene " usa \\" (es. "Chianti" → "Chianti")
- ESCAPA tutti gli apostrofi: L'Etna → L\\'Etna oppure usa virgolette esterne "L'Etna"
- ESCAPA backslash: usa \\\\ per rappresentare \\
- Chiudi SEMPRE tutte le stringhe con virgolette doppie
- "vintage" deve essere 1900–2099 oppure null (non stringa).
- "qty" deve essere un intero (es. "12 bottiglie" → 12, "0" → 0).
- "price" in EUR: accetta virgola (es. 8,50 → 8.5). Se assente → null.
- "type": una di [Rosso, Bianco, Rosato, Spumante, Altro]; se incerto → null.

IMPORTANTE: 
- Estrai TUTTE le righe con nome vino, non solo quelle "complete"
- Verifica che il JSON sia valido prima di inviarlo
- Output SOLO JSON array valido, nessun testo extra, nessun commento

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
        
        # Tentativo 1: Parsing diretto
        try:
            wines = json.loads(result_text)
        except json.JSONDecodeError as json_error:
            logger.warning(f"[LLM_EXTRACT] Errore parsing JSON (tentativo 1): {json_error}")
            
            # Tentativo 2: Cerca array JSON nel testo (potrebbe essere in mezzo a testo)
            import re
            json_match = re.search(r'\[.*\]', result_text, re.DOTALL)
            if json_match:
                try:
                    wines = json.loads(json_match.group(0))
                    logger.info("[LLM_EXTRACT] JSON estratto con regex")
                except json.JSONDecodeError:
                    wines = None
            else:
                wines = None
            
            # Tentativo 3: Fix automatico JSON malformato (più aggressivo)
            if wines is None:
                try:
                    fixed_text = result_text
                    
                    # Step 1: Rimuovi caratteri non-printable (eccetto \n, \r, \t)
                    fixed_text = ''.join(char for char in fixed_text if char.isprintable() or char in '\n\r\t')
                    
                    # Step 2: Normalizza virgolette
                    fixed_text = fixed_text.replace('"', '"').replace('"', '"')
                    
                    # Step 3: Tenta di fixare stringhe non terminate usando regex
                    # Cerca pattern: "text... senza virgolette di chiusura
                    import re
                    
                    # Pattern per trovare stringhe non terminate: "text... senza "
                    # Sostituisce con "text..." (aggiunge virgolette di chiusura prima della prossima virgola o })
                    def fix_unterminated_string(match):
                        content = match.group(1)
                        # Se la stringa contiene caratteri problematici, escapa
                        content = content.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n').replace('\r', '\\r')
                        return f'"{content}"'
                    
                    # Trova tutte le stringhe che iniziano con " ma non finiscono con " prima di , o }
                    # Pattern: "([^"]*?)(?=[,}\]\n]|$)
                    # Ma questo è troppo complesso, meglio un approccio diverso
                    
                    # Step 4: Tenta parsing incrementale - estrai solo oggetti JSON validi
                    # Usa un approccio stack-based per trovare oggetti JSON completi
                    def find_json_objects(text):
                        """Trova oggetti JSON completi usando stack-based matching."""
                        objects = []
                        stack = []
                        start = -1
                        in_string = False
                        escape_next = False
                        
                        for i, char in enumerate(text):
                            if escape_next:
                                escape_next = False
                                continue
                            
                            if char == '\\':
                                escape_next = True
                                continue
                            
                            if char == '"':
                                in_string = not in_string
                                continue
                            
                            if in_string:
                                continue
                            
                            if char == '{':
                                if not stack:
                                    start = i
                                stack.append(char)
                            elif char == '}':
                                if stack and stack[-1] == '{':
                                    stack.pop()
                                    if not stack:
                                        # Oggetto completo trovato
                                        obj_str = text[start:i+1]
                                        objects.append(obj_str)
                                        start = -1
                        
                        return objects
                    
                    matches = find_json_objects(fixed_text)
                    
                    if matches:
                        valid_objects = []
                        for obj_str in matches:
                            try:
                                # Aggiungi virgolette mancanti se necessario
                                if not obj_str.strip().startswith('{'):
                                    continue
                                # Tenta parsing
                                obj = json.loads(obj_str)
                                valid_objects.append(obj)
                            except json.JSONDecodeError:
                                # Prova a fixare questo oggetto specifico
                                try:
                                    # Aggiungi virgolette di chiusura se mancanti
                                    if obj_str.count('"') % 2 != 0:  # Numero dispari di virgolette
                                        # Trova ultima virgoletta e aggiungi chiusura
                                        last_quote = obj_str.rfind('"')
                                        if last_quote > 0:
                                            # Aggiungi " prima di }
                                            fixed_obj = obj_str[:last_quote+1] + '"' + obj_str[last_quote+1:]
                                            if fixed_obj.endswith('}'):
                                                fixed_obj = fixed_obj[:-1] + '"}'
                                            obj = json.loads(fixed_obj)
                                            valid_objects.append(obj)
                                except:
                                    continue
                        
                        if valid_objects:
                            wines = valid_objects
                            logger.info(f"[LLM_EXTRACT] JSON fixato: estratti {len(valid_objects)} oggetti validi da {len(matches)} trovati")
                        else:
                            raise json.JSONDecodeError("Nessun oggetto valido estratto", fixed_text, 0)
                    else:
                        # Fallback: prova parsing diretto
                        wines = json.loads(fixed_text)
                        logger.info("[LLM_EXTRACT] JSON fixato automaticamente (parsing diretto)")
                        
                except (json.JSONDecodeError, Exception) as fix_error:
                    logger.error(f"[LLM_EXTRACT] Errore fix JSON automatico: {fix_error}")
                    logger.debug(f"[LLM_EXTRACT] Risposta AI (primi 1000 char): {result_text[:1000]}")
                    
                    # Tentativo 4: Retry con prompt più forte
                    logger.info("[LLM_EXTRACT] Retry con prompt più forte per JSON valido")
                    try:
                        retry_prompt = f"""Il JSON precedente era malformato. Genera un JSON array valido estraendo i vini dal testo.

RICORDA:
- Escapa tutte le virgolette nei valori stringa: "name" → "name"
- Escapa tutti gli apostrofi: L'Etna → L\\'Etna oppure "L'Etna"
- Chiudi tutte le stringhe e parentesi
- Output SOLO JSON array valido, nessun testo extra

Testo originale:
<<<
{text_chunk[:20000]}  # Limita a 20KB per retry
>>>

Genera JSON valido:"""
                        
                        retry_response = client.chat.completions.create(
                            model=config.llm_model_extract,
                            messages=[
                                {
                                    "role": "system",
                                    "content": "Sei un estrattore JSON. Genera SEMPRE JSON valido e ben formattato. Escapa tutti i caratteri speciali."
                                },
                                {"role": "user", "content": retry_prompt}
                            ],
                            temperature=0.1,
                            max_tokens=4000
                        )
                        
                        retry_text = retry_response.choices[0].message.content.strip()
                        if retry_text.startswith("```"):
                            retry_text = retry_text.split("```")[1]
                            if retry_text.startswith("json"):
                                retry_text = retry_text[4:]
                            retry_text = retry_text.strip()
                        
                        wines = json.loads(retry_text)
                        logger.info("[LLM_EXTRACT] JSON parsato dopo retry")
                    except Exception as retry_error:
                        logger.error(f"[LLM_EXTRACT] Errore anche nel retry: {retry_error}")
                        logger.debug(f"[LLM_EXTRACT] Risposta retry (primi 500 char): {retry_text[:500] if 'retry_text' in locals() else 'N/A'}")
                        return []
        
        # Verifica che sia un array
        if not isinstance(wines, list):
            logger.warning("[LLM_EXTRACT] Risposta AI non è un array, ritorno vuoto")
            return []
        
        logger.info(f"[LLM_EXTRACT] Estratti {len(wines)} vini da chunk")
        return wines
        
    except json.JSONDecodeError as e:
        logger.error(f"[LLM_EXTRACT] Errore parsing JSON da AI: {e}")
        logger.debug(f"[LLM_EXTRACT] Risposta AI (primi 1000 char): {result_text[:1000] if 'result_text' in locals() else 'N/A'}")
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
                logger.info(f"[LLM_EXTRACT] Chunk {chunk_idx + 1}/{len(chunks)}: {len(wines_chunk)} vini estratti")
            except Exception as e:
                logger.warning(f"[LLM_EXTRACT] Errore chunk {chunk_idx + 1}: {e}")
                # Alert costi LLM per ogni chunk (gestito in extract_with_llm)
                continue
        
        logger.info(f"[LLM_EXTRACT] Totale vini estratti da tutti i chunk: {len(all_wines)}")
        
        if not all_wines:
            logger.warning("[LLM_EXTRACT] Nessun vino estratto da LLM")
            return [], {'error': 'Nessun vino estratto'}, 'error'
        
        # 4. Deduplica righe simili
        deduplicated_wines = deduplicate_wines(all_wines, merge_quantities=True)
        logger.info(
            f"[LLM_EXTRACT] Dopo deduplicazione: {len(deduplicated_wines)} vini "
            f"(da {len(all_wines)} estratti, {len(all_wines) - len(deduplicated_wines)} duplicati rimossi)"
        )
        
        # 5. Normalizza valori
        normalized_wines = []
        for idx, wine in enumerate(deduplicated_wines):
            try:
                logger.debug(f"[LLM_EXTRACT] Normalizzando vino {idx+1}/{len(deduplicated_wines)}: {wine.get('name', 'N/A')[:50]}")
                normalized = normalize_values(wine)
                logger.debug(f"[LLM_EXTRACT] Vino normalizzato: name={normalized.get('name')}, qty={normalized.get('qty')}, price={normalized.get('price')}")
                
                # Filtra righe vuote: name deve essere valido e non placeholder
                name = normalized.get('name', '').strip()
                is_valid_name = (
                    name and 
                    len(name) > 0 and 
                    name.lower() not in ['nan', 'none', 'null', 'n/a', 'na', 'undefined']
                )
                
                # Verifica anche che non sia una riga completamente vuota
                has_other_data = (
                    normalized.get('winery') or 
                    normalized.get('qty', 0) > 0 or 
                    normalized.get('price') is not None or
                    normalized.get('vintage') is not None
                )
                
                if is_valid_name and (has_other_data or len(name) > 2):  # Permetti name solo se ha altri dati o è abbastanza lungo
                    normalized_wines.append(normalized)
                    logger.debug(f"[LLM_EXTRACT] Vino aggiunto a normalized_wines (totale: {len(normalized_wines)})")
                else:
                    logger.warning(
                        f"[LLM_EXTRACT] Vino scartato: name invalido o riga vuota "
                        f"(name='{name[:30]}', has_other_data={has_other_data})"
                    )
            except Exception as e:
                logger.warning(f"[LLM_EXTRACT] Errore normalizzazione vino {idx+1}: {e}", exc_info=True)
                continue
        
        logger.info(f"[LLM_EXTRACT] Dopo normalizzazione: {len(normalized_wines)} vini validi")
        
        # 6. Validazione finale con Pydantic
        if not normalized_wines:
            logger.error("[LLM_EXTRACT] Nessun vino dopo normalizzazione, fallimento")
            return [], {'error': 'Nessun vino dopo normalizzazione', 'wines_extracted': len(all_wines), 'wines_deduplicated': len(deduplicated_wines)}, 'error'
        
        valid_wines, rejected_wines, validation_stats = validate_batch(normalized_wines)
        logger.info(f"[LLM_EXTRACT] Dopo validazione Pydantic: {len(valid_wines)} validi, {len(rejected_wines)} rifiutati")
        
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

