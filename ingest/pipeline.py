"""
Pipeline Orchestratore - Orchestratore principale per tutti gli stage.

Gestisce il flusso completo: Stage 0 (routing) → Stage 1-4 → Salvataggio DB.
Conforme a "Update processor.md" - Pipeline deterministica.
"""
import logging
import time
from typing import List, Dict, Any, Optional, Tuple
from core.config import get_config
from core.logger import log_json, set_request_context, get_request_context
from ingest.gate import route_file
from ingest.parser import parse_classic
from ingest.llm_targeted import apply_targeted_ai
from ingest.llm_extract import extract_llm_mode, deduplicate_wines
from ingest.ocr_extract import extract_ocr

logger = logging.getLogger(__name__)


async def process_file(
    file_content: bytes,
    file_name: str,
    ext: Optional[str] = None,
    telegram_id: Optional[int] = None,
    business_name: Optional[str] = None,
    correlation_id: Optional[str] = None
) -> Tuple[List[Dict[str, Any]], Dict[str, Any], str, str]:
    """
    Orchestratore principale della pipeline di elaborazione.
    
    Flow deterministico:
    1. Stage 0: Routing (gate.py) → determina percorso iniziale
       - CSV/Excel → Stage 1
       - PDF/immagini → Stage 4
    2. Stage 1: Parse classico (se csv_excel)
       - Se OK → ✅ SALVA
       - Se escalate → Stage 2
    3. Stage 2: IA mirata (se abilitato e escalate da Stage 1)
       - Se OK → ✅ SALVA
       - Se escalate → Stage 3
    4. Stage 3: LLM mode (se abilitato e escalate da Stage 2 o Stage 4)
       - Se OK → ✅ SALVA
       - Se error → ERRORE gestito
    5. Stage 4: OCR (se PDF/immagini)
       - OCR → passa a Stage 3 internamente
       - Ritorna risultati Stage 3
    
    Conforme a "Update processor.md" - Pipeline orchestratore.
    
    Args:
        file_content: Contenuto file (bytes)
        file_name: Nome file
        ext: Estensione file (se None, estrae da file_name)
        telegram_id: ID Telegram per logging
        business_name: Nome business per logging
        correlation_id: ID correlazione per logging (genera se None)
    
    Returns:
        Tuple (wines_data, metrics, decision, stage_used):
        - wines_data: Lista dict con vini validi (pronta per salvataggio DB)
        - metrics: Dict con metriche aggregate di tutti gli stage
        - decision: 'save' se OK, 'error' se fallimento
        - stage_used: Stage finale utilizzato ('csv_excel_parse', 'ia_targeted', 'llm_mode', 'ocr')
    """
    start_time = time.time()
    config = get_config()
    
    # Imposta contesto per logging
    set_request_context(telegram_id=telegram_id, correlation_id=correlation_id)
    ctx = get_request_context()
    correlation_id = ctx.get("correlation_id")
    
    # Metriche aggregate
    aggregated_metrics: Dict[str, Any] = {
        'file_name': file_name,
        'ext': ext,
        'telegram_id': telegram_id,
        'business_name': business_name,
        'correlation_id': correlation_id,
        'stages_attempted': [],
        'total_elapsed_sec': 0.0
    }
    
    wines_data: List[Dict[str, Any]] = []
    decision = 'error'
    stage_used = 'unknown'
    
    try:
        # Stage 0: Routing
        logger.info(f"[PIPELINE] Starting processing: {file_name} (ext={ext})")
        log_json(
            level='info',
            message=f"Pipeline started for file: {file_name}",
            file_name=file_name,
            ext=ext,
            telegram_id=telegram_id,
            correlation_id=correlation_id
        )
        
        try:
            stage_route, ext_normalized = route_file(file_content, file_name, ext)
            ext = ext_normalized
            aggregated_metrics['ext'] = ext
            aggregated_metrics['stage_route'] = stage_route
            logger.info(f"[PIPELINE] Stage 0: Routed to {stage_route} (ext={ext})")
        except ValueError as e:
            logger.error(f"[PIPELINE] Stage 0 routing failed: {e}")
            aggregated_metrics['error'] = f"Routing failed: {str(e)}"
            return [], aggregated_metrics, 'error', 'gate_error'
        
        # Routing: CSV/Excel → Stage 1, PDF/immagini → Stage 4
        if stage_route == 'csv_excel':
            # Percorso: Stage 1 → Stage 2 → Stage 3
            wines_data, metrics, decision, stage_used = await _process_csv_excel_path(
                file_content, file_name, ext, telegram_id, correlation_id, config
            )
        elif stage_route == 'ocr':
            # Percorso: Stage 4 → Stage 3 (internamente)
            wines_data, metrics, decision, stage_used = await _process_ocr_path(
                file_content, file_name, ext, telegram_id, correlation_id, config
            )
        else:
            logger.error(f"[PIPELINE] Unknown routing: {stage_route}")
            aggregated_metrics['error'] = f"Unknown routing: {stage_route}"
            return [], aggregated_metrics, 'error', 'unknown_route'
        
        # Aggrega metriche
        aggregated_metrics.update(metrics)
        aggregated_metrics['stage_used'] = stage_used
        aggregated_metrics['decision'] = decision
        aggregated_metrics['total_elapsed_sec'] = time.time() - start_time
        aggregated_metrics['rows_valid'] = len(wines_data)
        
        # Log finale
        log_json(
            level='info' if decision == 'save' else 'error',
            message=f"Pipeline completed: decision={decision}, stage={stage_used}, rows={len(wines_data)}",
            file_name=file_name,
            ext=ext,
            telegram_id=telegram_id,
            correlation_id=correlation_id,
            stage=stage_used,
            decision=decision,
            rows_valid=len(wines_data),
            elapsed_sec=aggregated_metrics['total_elapsed_sec']
        )
        
        logger.info(
            f"[PIPELINE] Completed: {file_name} | "
            f"decision={decision}, stage={stage_used}, "
            f"rows={len(wines_data)}, elapsed={aggregated_metrics['total_elapsed_sec']:.2f}s"
        )
        
        return wines_data, aggregated_metrics, decision, stage_used
        
    except Exception as e:
        elapsed_sec = time.time() - start_time
        logger.error(f"[PIPELINE] Unexpected error: {e}", exc_info=True)
        
        aggregated_metrics['error'] = str(e)
        aggregated_metrics['total_elapsed_sec'] = elapsed_sec
        aggregated_metrics['stage_used'] = 'pipeline_error'
        
        log_json(
            level='error',
            message=f"Pipeline failed with unexpected error: {str(e)}",
            file_name=file_name,
            ext=ext,
            telegram_id=telegram_id,
            correlation_id=correlation_id,
            elapsed_sec=elapsed_sec,
            decision='error'
        )
        
        # Alert se errori aumentano
        try:
            from core.alerting import check_error_rate_alert
            check_error_rate_alert(
                telegram_id=telegram_id,
                correlation_id=correlation_id,
                threshold=10,  # Alert se 10+ errori in 60 min
                window_minutes=60
            )
        except Exception as alert_error:
            logger.warning(f"[ALERT] Error checking error rate alert: {alert_error}")
        
        return [], aggregated_metrics, 'error', 'pipeline_error'


async def _process_csv_excel_path(
    file_content: bytes,
    file_name: str,
    ext: str,
    telegram_id: Optional[int],
    correlation_id: Optional[str],
    config
) -> Tuple[List[Dict[str, Any]], Dict[str, Any], str, str]:
    """
    Processa percorso CSV/Excel: Stage 1 → Stage 2 → Stage 3.
    
    Returns:
        Tuple (wines_data, metrics, decision, stage_used)
    """
    wines_data: List[Dict[str, Any]] = []
    metrics: Dict[str, Any] = {}
    decision = 'error'
    stage_used = 'unknown'
    
    # Stage 1: Parse classico
    try:
        logger.info(f"[PIPELINE] Stage 1: Starting classic parse for {file_name}")
        # parse_classic è sincrono, non async
        wines_data, metrics, decision = parse_classic(
            file_content=file_content,
            file_name=file_name,
            ext=ext
        )
        stage_used = 'csv_excel_parse'
        # Inizializza stages_attempted se non presente
        if 'stages_attempted' not in metrics:
            metrics['stages_attempted'] = []
        metrics['stages_attempted'].append('csv_excel_parse')
        
        if decision == 'save':
            logger.info(f"[PIPELINE] Stage 1 SUCCESS: {len(wines_data)} wines extracted")
            return wines_data, metrics, decision, stage_used
        elif decision == 'escalate_to_stage2':
            logger.info(f"[PIPELINE] Stage 1: Escalating to Stage 2 (IA mirata)")
        else:
            logger.warning(f"[PIPELINE] Stage 1: Unexpected decision={decision}, escalating to Stage 2")
            decision = 'escalate_to_stage2'
    except Exception as e:
        logger.error(f"[PIPELINE] Stage 1 failed: {e}", exc_info=True)
        # Inizializza metrics se Stage 1 fallisce completamente
        if not metrics:
            metrics = {
                'schema_score': 0.0,
                'valid_rows': 0.0,
                'rows_total': 0,
                'rows_valid': 0,
                'rows_rejected': 0,
                'stages_attempted': []
            }
        metrics['stage1_error'] = str(e)
        metrics.setdefault('stages_attempted', []).append('csv_excel_parse')
        decision = 'escalate_to_stage2'  # Try Stage 2
    
    # Stage 2: IA mirata (se abilitato e escalate da Stage 1)
    if decision == 'escalate_to_stage2' and config.ia_targeted_enabled:
        try:
            logger.info(f"[PIPELINE] Stage 2: Starting targeted AI for {file_name}")
            # Passa dati Stage 1 a Stage 2
            stage1_wines = wines_data if wines_data else []
            stage1_schema_score = metrics.get('schema_score', 0.0)
            stage1_valid_rows = metrics.get('valid_rows', 0.0)
            original_columns = metrics.get('original_columns', [])
            
            wines_data, metrics_stage2, decision = await apply_targeted_ai(
                wines_data=stage1_wines,
                original_columns=original_columns,
                schema_score=stage1_schema_score,
                valid_rows=stage1_valid_rows,
                file_name=file_name,
                ext=ext
            )
            stage_used = 'ia_targeted'
            # Assicura che stages_attempted esista
            metrics.setdefault('stages_attempted', []).append('ia_targeted')
            metrics.update(metrics_stage2)
            
            if decision == 'save':
                logger.info(f"[PIPELINE] Stage 2 SUCCESS: {len(wines_data)} wines extracted")
                return wines_data, metrics, decision, stage_used
            elif decision == 'escalate_to_stage3':
                logger.info(f"[PIPELINE] Stage 2: Escalating to Stage 3 (LLM mode)")
            else:
                logger.warning(f"[PIPELINE] Stage 2: Unexpected decision={decision}, escalating to Stage 3")
                decision = 'escalate_to_stage3'
        except Exception as e:
            logger.error(f"[PIPELINE] Stage 2 failed: {e}", exc_info=True)
            metrics['stage2_error'] = str(e)
            decision = 'escalate_to_stage3'  # Try Stage 3
    elif decision == 'escalate_to_stage2' and not config.ia_targeted_enabled:
        logger.info(f"[PIPELINE] Stage 2 disabled (IA_TARGETED_ENABLED=false), skipping to Stage 3")
        decision = 'escalate_to_stage3'
    
    # Stage 3: LLM mode (se abilitato e escalate da Stage 2)
    # SOLUZIONE 1 (IBRIDO): Salva vini da stage precedenti (Stage 1 o Stage 2) per unirli con Stage 3
    # Usa i vini migliorati da Stage 2 se disponibili, altrimenti quelli di Stage 1
    previous_stage_wines = wines_data.copy() if wines_data else []  # Salva vini prima di Stage 3
    
    if decision == 'escalate_to_stage3' and config.llm_fallback_enabled:
        try:
            logger.info(f"[PIPELINE] Stage 3: Starting LLM mode for {file_name}")
            wines_data_stage3, metrics_stage3, decision = await extract_llm_mode(
                file_content=file_content,
                file_name=file_name,
                ext=ext,
                telegram_id=telegram_id,
                correlation_id=correlation_id
            )
            stage_used = 'llm_mode'
            # Assicura che stages_attempted esista
            metrics.setdefault('stages_attempted', []).append('llm_mode')
            metrics.update(metrics_stage3)
            
            if decision == 'save':
                # SOLUZIONE 1 (IBRIDO): Unisci stage precedenti (Stage 1/2) + Stage 3
                if previous_stage_wines:
                    logger.info(
                        f"[PIPELINE] Unendo stage precedenti ({len(previous_stage_wines)} vini) + "
                        f"Stage 3 ({len(wines_data_stage3)} vini)"
                    )
                    
                    # Unisci i due dataset
                    combined_wines = previous_stage_wines + wines_data_stage3
                    logger.info(f"[PIPELINE] Totale vini prima deduplicazione: {len(combined_wines)}")
                    
                    # Deduplica per (name, winery, vintage) e somma qty se duplicati
                    wines_data = deduplicate_wines(combined_wines, merge_quantities=True)
                    
                    logger.info(
                        f"[PIPELINE] Stage 1/2+3 (IBRIDO) SUCCESS: "
                        f"{len(previous_stage_wines)} (Stage 1/2) + {len(wines_data_stage3)} (Stage 3) = "
                        f"{len(combined_wines)} (totale) → {len(wines_data)} (dopo deduplicazione)"
                    )
                    
                    # Aggiorna metriche con info unione
                    metrics['previous_stage_wines_count'] = len(previous_stage_wines)
                    metrics['stage3_wines_count'] = len(wines_data_stage3)
                    metrics['combined_wines_count'] = len(combined_wines)
                    metrics['final_wines_count'] = len(wines_data)
                    metrics['deduplication_removed'] = len(combined_wines) - len(wines_data)
                else:
                    # Nessun vino da stage precedenti, usa solo Stage 3
                    wines_data = wines_data_stage3
                    logger.info(f"[PIPELINE] Stage 3 SUCCESS: {len(wines_data)} wines extracted (no previous stage data to merge)")
                
                return wines_data, metrics, decision, stage_used
            else:
                logger.error(f"[PIPELINE] Stage 3 FAILED: decision={decision}")
                # Se Stage 3 fallisce ma abbiamo vini da stage precedenti, usali comunque
                if previous_stage_wines:
                    logger.info(
                        f"[PIPELINE] Stage 3 fallito ma ho {len(previous_stage_wines)} vini da stage precedenti, "
                        f"usando quelli come fallback"
                    )
                    wines_data = previous_stage_wines
                    decision = 'save'  # Salva comunque i vini di stage precedenti
                    metrics['fallback_to_previous_stage'] = True
                    return wines_data, metrics, decision, 'llm_mode_fallback_previous'
                return wines_data_stage3, metrics, decision, stage_used
        except Exception as e:
            logger.error(f"[PIPELINE] Stage 3 failed: {e}", exc_info=True)
            metrics['stage3_error'] = str(e)
            decision = 'error'
            return [], metrics, decision, 'llm_mode_error'
    elif decision == 'escalate_to_stage3' and not config.llm_fallback_enabled:
        logger.warning(f"[PIPELINE] Stage 3 disabled (LLM_FALLBACK_ENABLED=false), cannot proceed")
        metrics['error'] = 'Stage 3 (LLM mode) disabled and Stage 1-2 failed'
        decision = 'error'
        return [], metrics, decision, 'llm_mode_disabled'
    
    # Nessuno stage ha avuto successo
    logger.error(f"[PIPELINE] All stages failed for {file_name}")
    metrics['error'] = 'All stages failed'
    return [], metrics, decision, stage_used


async def _process_ocr_path(
    file_content: bytes,
    file_name: str,
    ext: str,
    telegram_id: Optional[int],
    correlation_id: Optional[str],
    config
) -> Tuple[List[Dict[str, Any]], Dict[str, Any], str, str]:
    """
    Processa percorso OCR: Stage 4 → Stage 3 (internamente).
    
    Stage 4 chiama internamente Stage 3, quindi non serve chiamare Stage 3 dopo.
    
    Returns:
        Tuple (wines_data, metrics, decision, stage_used)
    """
    wines_data: List[Dict[str, Any]] = []
    metrics: Dict[str, Any] = {}
    decision = 'error'
    stage_used = 'ocr'
    
    # Stage 4: OCR (se abilitato)
    if config.ocr_enabled:
        try:
            logger.info(f"[PIPELINE] Stage 4: Starting OCR for {file_name}")
            wines_data, metrics, decision = await extract_ocr(
                file_content=file_content,
                file_name=file_name,
                ext=ext,
                telegram_id=telegram_id,
                correlation_id=correlation_id
            )
            # Assicura che stages_attempted esista
            if 'stages_attempted' not in metrics:
                metrics['stages_attempted'] = []
            metrics['stages_attempted'].append('ocr')
            
            if decision == 'save':
                logger.info(f"[PIPELINE] Stage 4 SUCCESS: {len(wines_data)} wines extracted via OCR+LLM")
                return wines_data, metrics, decision, stage_used
            else:
                logger.error(f"[PIPELINE] Stage 4 FAILED: decision={decision}")
                return wines_data, metrics, decision, stage_used
        except Exception as e:
            logger.error(f"[PIPELINE] Stage 4 failed: {e}", exc_info=True)
            metrics['stage4_error'] = str(e)
            metrics['error'] = f"OCR failed: {str(e)}"
            decision = 'error'
            return [], metrics, decision, 'ocr_error'
    else:
        logger.warning(f"[PIPELINE] Stage 4 disabled (OCR_ENABLED=false)")
        metrics['error'] = 'OCR disabled'
        decision = 'error'
        return [], metrics, decision, 'ocr_disabled'

