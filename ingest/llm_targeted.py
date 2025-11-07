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

from __future__ import annotations

"""Stage 2: disambiguazione header con LLM leggero."""

import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import openai

from core.config import get_config
from core.diagnostics_state import increment
from core.logger import log_json

logger = logging.getLogger(__name__)

PROMPT_PATH = Path(__file__).resolve().parent / "prompts" / "llm_targeted_header.md"
_PROMPT_CACHE: Optional[str] = None
_openai_client = None


def get_openai_client():
    global _openai_client
    if _openai_client is None:
        config = get_config()
        api_key = config.openai_api_key
        if not api_key:
            raise ValueError("OPENAI_API_KEY non configurato")
        _openai_client = openai.OpenAI(api_key=api_key)
    return _openai_client


def _load_prompt_template() -> str:
    global _PROMPT_CACHE
    if _PROMPT_CACHE is None:
        if not PROMPT_PATH.exists():
            raise FileNotFoundError(f"Prompt Stage 2 non trovato: {PROMPT_PATH}")
        _PROMPT_CACHE = PROMPT_PATH.read_text(encoding="utf-8")
    return _PROMPT_CACHE


def _format_prompt(columns: List[str], samples: Dict[str, List[str]]) -> str:
    template = _load_prompt_template()
    payload_samples = {column: samples.get(column, [])[:5] for column in columns}
    return template.format(
        columns=json.dumps(columns, ensure_ascii=False),
        samples_by_column=json.dumps(payload_samples, ensure_ascii=False),
    )


async def llm_header_disambiguation(
    columns: List[str], samples: Dict[str, List[str]]
) -> List[Dict[str, Any]]:
    if not columns:
        return []

    config = get_config()
    client = get_openai_client()
    prompt = _format_prompt(columns, samples)

    response = client.chat.completions.create(
        model=config.llm_model_targeted,
        messages=[
            {
                "role": "system",
                "content": "Sei un assistente che abbina nomi di colonne a campi inventario. Rispondi solo con JSON.",
            },
            {"role": "user", "content": prompt},
        ],
        temperature=0.0,
        max_tokens=config.max_llm_tokens,
    )

    result_text = response.choices[0].message.content.strip()
    if result_text.startswith("```"):
        result_text = result_text.split("```")[1]
        if result_text.startswith("json"):
            result_text = result_text[4:]
        result_text = result_text.strip()

    data = json.loads(result_text)
    mappings = data.get("mappings", [])
    if not isinstance(mappings, list):
        return []

    return mappings


async def apply_targeted_ai(
    wines_data: List[Dict[str, Any]],
    original_columns: List[str],
    header_mapping: Dict[str, Dict[str, Any]],
    column_samples: Dict[str, List[str]],
    schema_score: float,
    valid_rows: float,
    file_name: str,
    ext: str,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any], str]:
    start_time = time.time()
    config = get_config()

    if not config.ia_targeted_enabled:
        logger.info("[LLM_TARGETED] Stage 2 disabilitato, passa a Stage 3")
        return wines_data, {}, "escalate_to_stage3"

    try:
        uncertain_columns: List[str] = []
        for column in original_columns:
            info = header_mapping.get(column, {})
            score = float(info.get("score", 0.0))
            if info.get("field") is None or score < config.header_confidence_th:
                uncertain_columns.append(column)

        increment("stage2.calls")

        if not uncertain_columns:
            metrics = {
                "elapsed_ms": (time.time() - start_time) * 1000,
                "checked_columns": [],
                "mappings": [],
                "schema_score": schema_score,
                "valid_rows": valid_rows,
            }
            return wines_data, metrics, "escalate_to_stage3"

        mappings = await llm_header_disambiguation(uncertain_columns, column_samples)
        increment("stage2.header_requests", len(uncertain_columns))
        increment("stage2.header_mappings", sum(1 for m in mappings if m.get("field")))

        elapsed_ms = (time.time() - start_time) * 1000
        metrics = {
            "elapsed_ms": elapsed_ms,
            "checked_columns": uncertain_columns,
            "mappings": mappings,
            "schema_score": schema_score,
            "valid_rows": valid_rows,
        }

        log_json(
            level="info",
            message="Stage 2 header disambiguation completed",
            file_name=file_name,
            ext=ext,
            stage="ia_targeted",
            checked_columns=uncertain_columns,
            mappings=mappings,
            schema_score=schema_score,
            valid_rows=valid_rows,
            elapsed_ms=elapsed_ms,
        )

        return wines_data, metrics, "escalate_to_stage3"

    except Exception as exc:
        elapsed_ms = (time.time() - start_time) * 1000
        logger.error("[LLM_TARGETED] Stage 2 failed: %s", exc, exc_info=True)
        log_json(
            level="error",
            message=f"Stage 2 failed: {exc}",
            file_name=file_name,
            ext=ext,
            stage="ia_targeted",
            elapsed_ms=elapsed_ms,
            decision="error",
        )
        return wines_data, {"error": str(exc)}, "escalate_to_stage3"


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

