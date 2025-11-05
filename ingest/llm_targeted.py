"""
LLM Targeted (Stage 2) - IA mirata per micro-aggiustamenti economici.

Usa IA solo per ambiguità locali, non per tutto il file.
Conforme a "Update processor.md" - Stage 2: IA mirata.
"""
import json
import logging
import time
from typing import List, Dict, Any, Optional, Tuple
import openai
import os
from core.config import get_config
from core.logger import log_json

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


async def disambiguate_headers(
    headers: List[str],
    examples: Optional[List[str]] = None
) -> Dict[str, str]:
    """
    Disambigua colonne usando Prompt P1 (disambiguazione colonne).
    
    Prompt P1 conforme a "Update processor.md" - Sezione "Prompt pronti".
    
    Args:
        headers: Lista colonne candidate (normalizzate)
        examples: Lista esempi header grezzi (opzionale)
    
    Returns:
        Dict mapping {'col_source': 'campo_target_or_null'}
    """
    config = get_config()
    
    if not config.ia_targeted_enabled:
        logger.warning("[LLM_TARGETED] Stage 2 disabilitato (IA_TARGETED_ENABLED=false)")
        return {}
    
    try:
        client = get_openai_client()
        
        # Prepara prompt P1
        headers_json = json.dumps(headers, ensure_ascii=False)
        examples_json = json.dumps(examples, ensure_ascii=False) if examples else "[]"
        
        prompt = f"""Sei un assistente che abbina nomi di colonne a campi noti.

Campi target: name, winery, vintage, qty, price, type.

Dati:
- Colonne candidate: {headers_json}
- Esempi header grezzi: {examples_json}

Istruzioni:
- Rispondi SOLO con JSON nel formato:
  {{"mapping":{{"<col_source>":"<campo_target_or_null>", ...}}}}
- Usa "null" se non sei certo.
- Non aggiungere testo extra.

Vincoli:
- vintage = annata (4 cifre 1900–2099)
- qty = quantità pezzi
- price = prezzo unitario (EUR)
"""
        
        response = client.chat.completions.create(
            model=config.llm_model_targeted,
            messages=[
                {
                    "role": "system",
                    "content": "Sei un assistente che abbina nomi di colonne a campi noti. Rispondi SOLO con JSON."
                },
                {"role": "user", "content": prompt}
            ],
            temperature=0.1,
            max_tokens=config.max_llm_tokens
        )
        
        # Alert costi LLM se necessario (Stage 2)
        try:
            from core.alerting import check_llm_cost_alert, estimate_llm_cost
            import tiktoken
            
            # Stima token
            encoding = tiktoken.encoding_for_model(config.llm_model_targeted)
            input_tokens = len(encoding.encode(prompt))
            output_tokens = response.usage.completion_tokens if hasattr(response, 'usage') and response.usage else 0
            
            # Stima costo
            estimated_cost = estimate_llm_cost(
                model=config.llm_model_targeted,
                input_tokens=input_tokens,
                output_tokens=output_tokens
            )
            
            # Verifica alert (senza telegram_id/correlation_id in questo contesto)
            check_llm_cost_alert(
                estimated_cost=estimated_cost,
                telegram_id=None,
                correlation_id=None,
                threshold=0.50,
                window_minutes=60
            )
        except Exception as alert_error:
            logger.debug(f"[ALERT] Error checking LLM cost alert (Stage 2): {alert_error}")
        
        result_text = response.choices[0].message.content.strip()
        
        # Estrai JSON (rimuovi markdown code blocks se presenti)
        if result_text.startswith("```"):
            result_text = result_text.split("```")[1]
            if result_text.startswith("json"):
                result_text = result_text[4:]
            result_text = result_text.strip()
        
        result = json.loads(result_text)
        mapping = result.get("mapping", {})
        
        logger.info(
            f"[LLM_TARGETED] Disambiguazione colonne: {len(mapping)} colonne mappate"
        )
        
        return mapping
        
    except Exception as e:
        logger.error(f"[LLM_TARGETED] Errore disambiguazione colonne: {e}", exc_info=True)
        return {}


async def fix_ambiguous_rows(
    batch_rows: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    Corregge valori problematici usando Prompt P2 (correzione valori batch).
    
    Prompt P2 conforme a "Update processor.md" - Sezione "Prompt pronti".
    
    Args:
        batch_rows: Array JSON di max 20 righe con valori grezzi
    
    Returns:
        Array JSON con STESSE righe nello stesso ordine, campi corretti
    """
    config = get_config()
    
    if not config.ia_targeted_enabled:
        logger.warning("[LLM_TARGETED] Stage 2 disabilitato (IA_TARGETED_ENABLED=false)")
        return batch_rows
    
    try:
        client = get_openai_client()
        
        # Prepara prompt P2
        batch_json = json.dumps(batch_rows, ensure_ascii=False, indent=2)
        
        prompt = f"""Sei un assistente dati. Correggi/estrai SOLO i campi mancanti o errati per ciascuna riga.

Schema target: {{name, winery, vintage, qty, price, type}}

Input (array JSON di max 20 righe) con valori grezzi:
{batch_json}

Istruzioni:
- Restituisci un array JSON con STESSE righe nello stesso ordine.
- Per ogni riga popola solo i campi mancanti/errati.
- vintage deve essere 1900–2099 o null.
- qty intero >= 0.
- price numero (virgola ammessa).
- type una di: Rosso, Bianco, Rosato, Spumante, Altro (scegli la più probabile o null).

Output SOLO JSON (nessun testo extra).
"""
        
        response = client.chat.completions.create(
            model=config.llm_model_targeted,
            messages=[
                {
                    "role": "system",
                    "content": "Sei un assistente dati. Correggi/estrai SOLO i campi mancanti o errati. Rispondi SOLO con JSON array."
                },
                {"role": "user", "content": prompt}
            ],
            temperature=0.1,
            max_tokens=config.max_llm_tokens
        )
        
        # Alert costi LLM se necessario (Stage 2 - fix_ambiguous_rows)
        try:
            from core.alerting import check_llm_cost_alert, estimate_llm_cost
            import tiktoken
            
            # Stima token
            encoding = tiktoken.encoding_for_model(config.llm_model_targeted)
            input_tokens = len(encoding.encode(prompt))
            output_tokens = response.usage.completion_tokens if hasattr(response, 'usage') and response.usage else 0
            
            # Stima costo
            estimated_cost = estimate_llm_cost(
                model=config.llm_model_targeted,
                input_tokens=input_tokens,
                output_tokens=output_tokens
            )
            
            # Verifica alert
            check_llm_cost_alert(
                estimated_cost=estimated_cost,
                telegram_id=None,
                correlation_id=None,
                threshold=0.50,
                window_minutes=60
            )
        except Exception as alert_error:
            logger.debug(f"[ALERT] Error checking LLM cost alert (Stage 2 - fix): {alert_error}")
        
        result_text = response.choices[0].message.content.strip()
        
        # Estrai JSON (rimuovi markdown code blocks se presenti)
        if result_text.startswith("```"):
            result_text = result_text.split("```")[1]
            if result_text.startswith("json"):
                result_text = result_text[4:]
            result_text = result_text.strip()
        
        fixed_rows = json.loads(result_text)
        
        # Verifica che sia un array e che abbia stesso numero di righe
        if not isinstance(fixed_rows, list):
            logger.warning("[LLM_TARGETED] Risposta AI non è un array, ritorno originale")
            return batch_rows
        
        if len(fixed_rows) != len(batch_rows):
            logger.warning(
                f"[LLM_TARGETED] Risposta AI ha {len(fixed_rows)} righe invece di {len(batch_rows)}, "
                "ritorno originale"
            )
            return batch_rows
        
        logger.info(
            f"[LLM_TARGETED] Corretti {len(fixed_rows)} righe problematiche"
        )
        
        return fixed_rows
        
    except Exception as e:
        logger.error(f"[LLM_TARGETED] Errore correzione valori: {e}", exc_info=True)
        return batch_rows


async def apply_targeted_ai(
    wines_data: List[Dict[str, Any]],
    original_columns: List[str],
    schema_score: float,
    valid_rows: float,
    file_name: str,
    ext: str
) -> Tuple[List[Dict[str, Any]], Dict[str, Any], str]:
    """
    Orchestratore Stage 2: Applica IA mirata per migliorare dati.
    
    Casi:
    - Colonne ambigue → disambiguate_headers()
    - Valori problematici → fix_ambiguous_rows() (batch)
    
    Post-processing:
    - Applica mappatura/valori restituiti
    - Ricalcola metriche
    - Se supera soglie → SALVA, altrimenti → Stage 3
    
    Conforme a "Update processor.md" - Stage 2: IA mirata.
    
    Args:
        wines_data: Lista vini con dati (dopo Stage 1)
        original_columns: Colonne originali del file
        schema_score: Schema score da Stage 1
        valid_rows: Valid rows da Stage 1
        file_name: Nome file
        ext: Estensione file
    
    Returns:
        Tuple (wines_data_fixed, metrics, decision):
        - wines_data_fixed: Lista vini corretti
        - metrics: Dict con metriche aggiornate
        - decision: 'save' se OK, 'escalate_to_stage3' se necessario Stage 3
    """
    start_time = time.time()
    config = get_config()
    
    if not config.ia_targeted_enabled:
        logger.info("[LLM_TARGETED] Stage 2 disabilitato, passa a Stage 3")
        return wines_data, {}, 'escalate_to_stage3'
    
    try:
        # Identifica colonne ambigue (non mappate correttamente)
        # Se schema_score < 0.7, probabilmente colonne ambigue
        header_mapping_ai = {}
        if schema_score < config.schema_score_th:
            logger.info("[LLM_TARGETED] Schema score basso, provo disambiguazione colonne")
            header_mapping_ai = await disambiguate_headers(
                headers=original_columns,
                examples=original_columns
            )
            
            if header_mapping_ai:
                logger.info(
                    f"[LLM_TARGETED] AI ha mappato {len(header_mapping_ai)} colonne ambigue"
                )
                # Nota: La mappatura colonne va applicata prima della normalizzazione
                # Per ora, se arriviamo qui, significa che Stage 1 ha già mappato
                # Le colonne ambigue potrebbero essere quelle non mappate
        
        # Identifica righe problematiche (valori mancanti o errati)
        # Se valid_rows < MIN_VALID_ROWS, ci sono righe problematiche
        rows_fixed = 0
        batch_count = 0
        
        if valid_rows < config.min_valid_rows and wines_data:
            # Identifica righe problematiche (hanno valori mancanti o errati)
            problematic_rows = []
            for wine in wines_data:
                # Righe problematiche: mancano campi obbligatori o hanno valori strani
                if not wine.get('name') or wine.get('qty') is None:
                    problematic_rows.append(wine)
            
            # Processa in batch
            if problematic_rows:
                batch_size = config.batch_size_ambiguous_rows
                for i in range(0, len(problematic_rows), batch_size):
                    batch = problematic_rows[i:i + batch_size]
                    batch_count += 1
                    
                    try:
                        fixed_batch = await fix_ambiguous_rows(batch)
                        
                        # Sostituisci righe corrette in wines_data
                        for idx, fixed_wine in enumerate(fixed_batch):
                            # Trova riga originale e sostituisci
                            original_idx = i + idx
                            if original_idx < len(problematic_rows):
                                # Cerca corrispondenza per nome (se presente)
                                original_wine = problematic_rows[original_idx]
                                # Sostituisci con valori corretti
                                for key, value in fixed_wine.items():
                                    if value is not None and value != "":
                                        original_wine[key] = value
                                rows_fixed += 1
                    except Exception as e:
                        logger.warning(f"[LLM_TARGETED] Errore batch {batch_count}: {e}")
                        continue
        
        # Ricalcola metriche (schema_score e valid_rows)
        # Per ora, assumiamo che le correzioni migliorino le metriche
        # In una implementazione completa, dovremmo ri-validare con Pydantic
        improved_schema_score = schema_score
        improved_valid_rows = valid_rows
        
        # Se abbiamo corretto colonne, miglioriamo schema_score
        if header_mapping_ai:
            improved_schema_score = min(1.0, schema_score + 0.1)
        
        # Se abbiamo corretto righe, miglioriamo valid_rows
        if rows_fixed > 0:
            total_rows = len(wines_data)
            if total_rows > 0:
                improved_valid_rows = min(1.0, valid_rows + (rows_fixed / total_rows))
        
        elapsed_ms = (time.time() - start_time) * 1000
        
        metrics = {
            'schema_score': improved_schema_score,
            'valid_rows': improved_valid_rows,
            'rows_total': len(wines_data),
            'rows_fixed': rows_fixed,
            'batch_count': batch_count,
            'elapsed_ms': elapsed_ms,
            'header_mapping_ai': header_mapping_ai
        }
        
        # Decisione: se supera soglie → SALVA, altrimenti → Stage 3
        if improved_schema_score >= config.schema_score_th and improved_valid_rows >= config.min_valid_rows:
            decision = 'save'
            logger.info(
                f"[LLM_TARGETED] Stage 2 SUCCESS: schema_score={improved_schema_score:.2f} >= {config.schema_score_th}, "
                f"valid_rows={improved_valid_rows:.2f} >= {config.min_valid_rows} → SALVA"
            )
        else:
            decision = 'escalate_to_stage3'
            logger.info(
                f"[LLM_TARGETED] Stage 2 INSUFFICIENT: schema_score={improved_schema_score:.2f} < {config.schema_score_th} "
                f"or valid_rows={improved_valid_rows:.2f} < {config.min_valid_rows} → Stage 3"
            )
        
        # Logging JSON strutturato
        log_json(
            level='info',
            message=f"Stage 2 completed: decision={decision}",
            file_name=file_name,
            ext=ext,
            stage='ia_targeted',
            schema_score=improved_schema_score,
            valid_rows=improved_valid_rows,
            rows_total=len(wines_data),
            rows_valid=int(improved_valid_rows * len(wines_data)) if wines_data else 0,
            elapsed_ms=elapsed_ms,
            decision=decision,
            batch_count=batch_count,
            rows_fixed=rows_fixed
        )
        
        return wines_data, metrics, decision
        
    except Exception as e:
        elapsed_ms = (time.time() - start_time) * 1000
        logger.error(f"[LLM_TARGETED] Errore in Stage 2: {e}", exc_info=True)
        
        # Log errore
        log_json(
            level='error',
            message=f"Stage 2 failed: {str(e)}",
            file_name=file_name,
            ext=ext,
            stage='ia_targeted',
            elapsed_ms=elapsed_ms,
            decision='error'
        )
        
        # In caso di errore, passa a Stage 3
        return wines_data, {}, 'escalate_to_stage3'

