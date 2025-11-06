"""
Logging strutturato per gioia-processor.

Unifica logging colorato e structured logging con supporto JSON.
"""
import logging
import json
import uuid
import sys
import contextvars
from typing import Optional, Dict, Any
from datetime import datetime

try:
    import colorlog
    COLORLOG_AVAILABLE = True
except ImportError:
    COLORLOG_AVAILABLE = False

# Context variables per tracciare richieste
_request_context: contextvars.ContextVar[Dict[str, Any]] = contextvars.ContextVar('request_context', default={})


def setup_colored_logging(service_name: str = "processor"):
    """
    Configura logging colorato con colorlog.
    
    Args:
        service_name: Nome del servizio per identificare log
    """
    # Handler per stdout con colori
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logging.DEBUG)
    
    if COLORLOG_AVAILABLE:
        # Formatter colorato
        formatter = colorlog.ColoredFormatter(
            f'%(log_color)s[%(levelname)s]%(reset)s %(cyan)s{service_name}%(reset)s | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S',
            reset=True,
            log_colors={
                'DEBUG': 'white',
                'INFO': 'blue',
                'WARNING': 'yellow',
                'ERROR': 'red',
                'CRITICAL': 'red,bg_white',
            },
            secondary_log_colors={},
            style='%'
        )
    else:
        # Formatter semplice se colorlog non disponibile
        formatter = logging.Formatter(
            f'[%(levelname)s] {service_name} | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
    
    handler.setFormatter(formatter)
    
    # Configura root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    
    # Rimuovi handler esistenti
    root_logger.handlers = []
    
    # Aggiungi handler colorato
    root_logger.addHandler(handler)
    
    # Configura logger specifici per ridurre verbosità
    logging.getLogger('httpx').setLevel(logging.WARNING)
    logging.getLogger('httpcore').setLevel(logging.WARNING)
    logging.getLogger('aiohttp').setLevel(logging.WARNING)
    
    return root_logger


def set_request_context(telegram_id: Optional[int] = None, correlation_id: Optional[str] = None):
    """
    Imposta contesto richiesta per logging strutturato.
    
    Args:
        telegram_id: ID Telegram dell'utente
        correlation_id: ID correlazione (genera se None)
    """
    if correlation_id is None:
        correlation_id = str(uuid.uuid4())
    
    context = {}
    if telegram_id is not None:
        context["telegram_id"] = telegram_id
    context["correlation_id"] = correlation_id
    
    _request_context.set(context)


def get_request_context() -> Dict[str, Any]:
    """
    Recupera contesto richiesta corrente.
    
    Returns:
        Dict con telegram_id e correlation_id
    """
    return _request_context.get({})


def get_correlation_id(context=None) -> Optional[str]:
    """
    Recupera correlation ID dal contesto.
    
    Args:
        context: Context (opzionale, per compatibilità)
    
    Returns:
        Correlation ID se disponibile, None altrimenti
    """
    ctx = get_request_context()
    return ctx.get("correlation_id")


def log_with_context(
    level: str,
    message: str,
    telegram_id: Optional[int] = None,
    correlation_id: Optional[str] = None,
    **extra
):
    """
    Log con contesto strutturato (telegram_id, correlation_id).
    
    Args:
        level: 'info', 'warning', 'error', 'debug'
        message: Messaggio da loggare
        telegram_id: ID Telegram (usa contesto se None)
        correlation_id: ID correlazione (usa contesto se None)
        **extra: Campi aggiuntivi per log
    """
    # Recupera contesto se non fornito
    ctx = get_request_context()
    if telegram_id is None:
        telegram_id = ctx.get("telegram_id")
    if correlation_id is None:
        correlation_id = ctx.get("correlation_id")
    
    # Formatta messaggio con contesto
    log_message = message
    if telegram_id:
        log_message = f"[telegram_id={telegram_id}] {log_message}"
    if correlation_id:
        log_message = f"[correlation_id={correlation_id}] {log_message}"
    
    # Log con livello appropriato
    logger = logging.getLogger(__name__)
    log_func = getattr(logger, level.lower(), logger.info)
    log_func(log_message, **extra)


def log_json(
    level: str,
    message: str,
    telegram_id: Optional[int] = None,
    correlation_id: Optional[str] = None,
    stage: Optional[str] = None,
    file_name: Optional[str] = None,
    ext: Optional[str] = None,
    schema_score: Optional[float] = None,
    valid_rows: Optional[float] = None,
    rows_total: Optional[int] = None,
    rows_valid: Optional[int] = None,
    rows_rejected: Optional[int] = None,
    elapsed_ms: Optional[float] = None,
    elapsed_sec: Optional[float] = None,
    decision: Optional[str] = None,
    **extra
):
    """
    Log strutturato in formato JSON (per produzione).
    
    Formato conforme a "Update processor.md" - Sezione "Logging strutturato".
    
    Args:
        level: 'info', 'warning', 'error', 'debug'
        message: Messaggio da loggare
        telegram_id: ID Telegram
        correlation_id: ID correlazione
        stage: Stage pipeline (csv_parse, ia_targeted, llm_mode, ocr)
        file_name: Nome file processato
        ext: Estensione file
        schema_score: Score schema (0.0-1.0)
        valid_rows: Percentuale righe valide (0.0-1.0)
        rows_total: Numero totale righe
        rows_valid: Numero righe valide
        rows_rejected: Numero righe rifiutate
        elapsed_ms: Tempo elaborazione in millisecondi
        elapsed_sec: Tempo elaborazione in secondi
        decision: Decisione pipeline (continue/stop/escalate)
        **extra: Campi aggiuntivi
    """
    # Recupera contesto se non fornito
    ctx = get_request_context()
    if telegram_id is None:
        telegram_id = ctx.get("telegram_id")
    if correlation_id is None:
        correlation_id = ctx.get("correlation_id")
    
    # Costruisci log JSON
    log_data = {
        "timestamp": datetime.utcnow().isoformat(),
        "level": level.upper(),
        "message": message,
    }
    
    # Campi obbligatori se disponibili
    if correlation_id:
        log_data["correlation_id"] = correlation_id
    if telegram_id:
        log_data["telegram_id"] = telegram_id
    if file_name:
        log_data["file_name"] = file_name
    if ext:
        log_data["ext"] = ext
    if stage:
        log_data["stage"] = stage
    
    # Metriche
    if schema_score is not None:
        log_data["schema_score"] = schema_score
    if valid_rows is not None:
        log_data["valid_rows"] = valid_rows
    if rows_total is not None:
        log_data["rows_total"] = rows_total
    if rows_valid is not None:
        log_data["rows_valid"] = rows_valid
    if rows_rejected is not None:
        log_data["rows_rejected"] = rows_rejected
    
    # Timing
    if elapsed_ms is not None:
        log_data["elapsed_ms"] = elapsed_ms
    if elapsed_sec is not None:
        log_data["elapsed_sec"] = elapsed_sec
    
    # Decisione
    if decision:
        log_data["decision"] = decision
    
    # Campi extra
    log_data.update(extra)
    
    # Log come JSON line
    logger = logging.getLogger(__name__)
    log_func = getattr(logger, level.lower(), logger.info)
    
    # Formatta come JSON line (una riga)
    json_line = json.dumps(log_data, ensure_ascii=False)
    log_func(json_line)




