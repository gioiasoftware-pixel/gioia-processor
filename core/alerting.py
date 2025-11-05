"""
Sistema di Alerting per gioia-processor.

Gestisce alert per:
- Stage 3 fallisce spesso
- Costi LLM superano soglia
- Errori aumentano
"""
import logging
import time
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
from collections import defaultdict
from core.logger import get_correlation_id

logger = logging.getLogger(__name__)

# Import admin_notifications con fallback
try:
    from admin_notifications import enqueue_admin_notification
except ImportError:
    # Fallback se admin_notifications non disponibile
    async def enqueue_admin_notification(*args, **kwargs):
        logger.warning("[ALERT] admin_notifications not available, alerts will be logged only")
        return False

# Contatori in-memory per alert (per singola istanza)
# In produzione, considerare Redis per multi-istanza
_stage3_failures: Dict[str, list] = defaultdict(list)  # {time_window: [timestamps]}
_error_count: Dict[str, int] = defaultdict(int)  # {time_window: count}
_llm_cost_estimate: Dict[str, float] = defaultdict(float)  # {time_window: total_cost_estimate}


def _get_time_window(minutes: int = 60) -> str:
    """
    Ottiene finestra temporale corrente (per aggregazione).
    
    Args:
        minutes: Minuti per finestra (default 60)
    
    Returns:
        Stringa identificativa finestra (es. "2025-01-XX-10")
    """
    now = datetime.utcnow()
    window_minutes = (now.minute // minutes) * minutes
    window = now.replace(minute=window_minutes, second=0, microsecond=0)
    return window.strftime("%Y-%m-%d-%H-%M")


def _cleanup_old_windows(max_age_minutes: int = 120):
    """
    Rimuove finestre temporali vecchie.
    
    Args:
        max_age_minutes: Età massima finestre da mantenere
    """
    cutoff = datetime.utcnow() - timedelta(minutes=max_age_minutes)
    cutoff_str = cutoff.strftime("%Y-%m-%d-%H-%M")
    
    # Rimuovi chiavi vecchie
    for key in list(_stage3_failures.keys()):
        if key < cutoff_str:
            del _stage3_failures[key]
    
    for key in list(_error_count.keys()):
        if key < cutoff_str:
            del _error_count[key]
    
    for key in list(_llm_cost_estimate.keys()):
        if key < cutoff_str:
            del _llm_cost_estimate[key]


def check_stage3_failure_alert(
    telegram_id: Optional[int] = None,
    correlation_id: Optional[str] = None,
    threshold: int = 5,
    window_minutes: int = 60
) -> bool:
    """
    Verifica se Stage 3 fallisce spesso e invia alert se necessario.
    
    Args:
        telegram_id: ID Telegram utente
        correlation_id: ID correlazione
        threshold: Soglia fallimenti per alert (default 5 in 60 min)
        window_minutes: Finestra temporale in minuti (default 60)
    
    Returns:
        True se alert inviato, False altrimenti
    """
    try:
        _cleanup_old_windows()
        
        window = _get_time_window(window_minutes)
        current_time = time.time()
        
        # Aggiungi fallimento corrente
        _stage3_failures[window].append(current_time)
        
        # Conta fallimenti in finestra corrente
        failures_in_window = len(_stage3_failures[window])
        
        # Se supera soglia, invia alert
        if failures_in_window >= threshold:
            # Previeni spam: invia solo una volta per finestra
            alert_key = f"stage3_alert_{window}"
            if not hasattr(check_stage3_failure_alert, '_sent_alerts'):
                check_stage3_failure_alert._sent_alerts = set()
            
            if alert_key not in check_stage3_failure_alert._sent_alerts:
                check_stage3_failure_alert._sent_alerts.add(alert_key)
                
                # Invia notifica admin (async, ma chiamata da contesto sync)
                import asyncio
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        # Se loop già in esecuzione, usa create_task
                        asyncio.create_task(enqueue_admin_notification(
                            event_type="alert",
                            telegram_id=telegram_id or 0,
                            payload={
                                "alert_type": "stage3_failure_high",
                                "message": f"Stage 3 fallito {failures_in_window} volte nelle ultime {window_minutes} minuti",
                                "threshold": threshold,
                                "failures_count": failures_in_window,
                                "window_minutes": window_minutes,
                                "component": "gioia-processor",
                                "severity": "warning"
                            },
                            correlation_id=correlation_id or get_correlation_id()
                        ))
                    else:
                        loop.run_until_complete(enqueue_admin_notification(
                            event_type="alert",
                            telegram_id=telegram_id or 0,
                            payload={
                                "alert_type": "stage3_failure_high",
                                "message": f"Stage 3 fallito {failures_in_window} volte nelle ultime {window_minutes} minuti",
                                "threshold": threshold,
                                "failures_count": failures_in_window,
                                "window_minutes": window_minutes,
                                "component": "gioia-processor",
                                "severity": "warning"
                            },
                            correlation_id=correlation_id or get_correlation_id()
                        ))
                except Exception as notif_error:
                    logger.warning(f"[ALERT] Error sending admin notification: {notif_error}")
                
                logger.warning(
                    f"[ALERT] Stage 3 failure alert: {failures_in_window} failures in {window_minutes} minutes"
                )
                return True
        
        return False
        
    except Exception as e:
        logger.error(f"[ALERT] Error checking Stage 3 failure alert: {e}", exc_info=True)
        return False


def check_llm_cost_alert(
    estimated_cost: float,
    telegram_id: Optional[int] = None,
    correlation_id: Optional[str] = None,
    threshold: float = 0.50,  # 0.50€ per finestra
    window_minutes: int = 60
) -> bool:
    """
    Verifica se costi LLM superano soglia e invia alert se necessario.
    
    Args:
        estimated_cost: Costo stimato LLM per questa chiamata (in €)
        telegram_id: ID Telegram utente
        correlation_id: ID correlazione
        threshold: Soglia costo per alert (default 0.50€ in 60 min)
        window_minutes: Finestra temporale in minuti (default 60)
    
    Returns:
        True se alert inviato, False altrimenti
    """
    try:
        _cleanup_old_windows()
        
        window = _get_time_window(window_minutes)
        
        # Aggiungi costo corrente
        _llm_cost_estimate[window] += estimated_cost
        
        # Verifica se supera soglia
        total_cost = _llm_cost_estimate[window]
        
        if total_cost >= threshold:
            # Previeni spam: invia solo una volta per finestra
            alert_key = f"llm_cost_alert_{window}"
            if not hasattr(check_llm_cost_alert, '_sent_alerts'):
                check_llm_cost_alert._sent_alerts = set()
            
            if alert_key not in check_llm_cost_alert._sent_alerts:
                check_llm_cost_alert._sent_alerts.add(alert_key)
                
                # Invia notifica admin (async, ma chiamata da contesto sync)
                import asyncio
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        asyncio.create_task(enqueue_admin_notification(
                            event_type="alert",
                            telegram_id=telegram_id or 0,
                            payload={
                                "alert_type": "llm_cost_high",
                                "message": f"Costi LLM stimati: {total_cost:.2f}€ nelle ultime {window_minutes} minuti (soglia: {threshold}€)",
                                "estimated_cost": round(total_cost, 2),
                                "threshold": threshold,
                                "window_minutes": window_minutes,
                                "component": "gioia-processor",
                                "severity": "warning"
                            },
                            correlation_id=correlation_id or get_correlation_id()
                        ))
                    else:
                        loop.run_until_complete(enqueue_admin_notification(
                            event_type="alert",
                            telegram_id=telegram_id or 0,
                            payload={
                                "alert_type": "llm_cost_high",
                                "message": f"Costi LLM stimati: {total_cost:.2f}€ nelle ultime {window_minutes} minuti (soglia: {threshold}€)",
                                "estimated_cost": round(total_cost, 2),
                                "threshold": threshold,
                                "window_minutes": window_minutes,
                                "component": "gioia-processor",
                                "severity": "warning"
                            },
                            correlation_id=correlation_id or get_correlation_id()
                        ))
                except Exception as notif_error:
                    logger.warning(f"[ALERT] Error sending admin notification: {notif_error}")
                
                logger.warning(
                    f"[ALERT] LLM cost alert: {total_cost:.2f}€ in {window_minutes} minutes (threshold: {threshold}€)"
                )
                return True
        
        return False
        
    except Exception as e:
        logger.error(f"[ALERT] Error checking LLM cost alert: {e}", exc_info=True)
        return False


def check_error_rate_alert(
    telegram_id: Optional[int] = None,
    correlation_id: Optional[str] = None,
    threshold: int = 10,
    window_minutes: int = 60
) -> bool:
    """
    Verifica se errori aumentano e invia alert se necessario.
    
    Args:
        telegram_id: ID Telegram utente
        correlation_id: ID correlazione
        threshold: Soglia errori per alert (default 10 in 60 min)
        window_minutes: Finestra temporale in minuti (default 60)
    
    Returns:
        True se alert inviato, False altrimenti
    """
    try:
        _cleanup_old_windows()
        
        window = _get_time_window(window_minutes)
        
        # Incrementa contatore errori
        _error_count[window] += 1
        
        # Verifica se supera soglia
        errors_in_window = _error_count[window]
        
        if errors_in_window >= threshold:
            # Previeni spam: invia solo una volta per finestra
            alert_key = f"error_rate_alert_{window}"
            if not hasattr(check_error_rate_alert, '_sent_alerts'):
                check_error_rate_alert._sent_alerts = set()
            
            if alert_key not in check_error_rate_alert._sent_alerts:
                check_error_rate_alert._sent_alerts.add(alert_key)
                
                # Invia notifica admin (async, ma chiamata da contesto sync)
                import asyncio
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        asyncio.create_task(enqueue_admin_notification(
                            event_type="alert",
                            telegram_id=telegram_id or 0,
                            payload={
                                "alert_type": "error_rate_high",
                                "message": f"{errors_in_window} errori rilevati nelle ultime {window_minutes} minuti (soglia: {threshold})",
                                "error_count": errors_in_window,
                                "threshold": threshold,
                                "window_minutes": window_minutes,
                                "component": "gioia-processor",
                                "severity": "error"
                            },
                            correlation_id=correlation_id or get_correlation_id()
                        ))
                    else:
                        loop.run_until_complete(enqueue_admin_notification(
                            event_type="alert",
                            telegram_id=telegram_id or 0,
                            payload={
                                "alert_type": "error_rate_high",
                                "message": f"{errors_in_window} errori rilevati nelle ultime {window_minutes} minuti (soglia: {threshold})",
                                "error_count": errors_in_window,
                                "threshold": threshold,
                                "window_minutes": window_minutes,
                                "component": "gioia-processor",
                                "severity": "error"
                            },
                            correlation_id=correlation_id or get_correlation_id()
                        ))
                except Exception as notif_error:
                    logger.warning(f"[ALERT] Error sending admin notification: {notif_error}")
                
                logger.warning(
                    f"[ALERT] Error rate alert: {errors_in_window} errors in {window_minutes} minutes (threshold: {threshold})"
                )
                return True
        
        return False
        
    except Exception as e:
        logger.error(f"[ALERT] Error checking error rate alert: {e}", exc_info=True)
        return False


def estimate_llm_cost(
    model: str,
    input_tokens: int,
    output_tokens: int = 0
) -> float:
    """
    Stima costo LLM in base a modello e token.
    
    Args:
        model: Modello LLM (gpt-4o-mini, gpt-4o, etc.)
        input_tokens: Token input
        output_tokens: Token output (default 0)
    
    Returns:
        Costo stimato in €
    """
    # Prezzi per 1M token (aggiornati a gennaio 2025)
    # Fonte: https://openai.com/pricing
    pricing = {
        "gpt-4o-mini": {
            "input": 0.15 / 1_000_000,  # €0.15 per 1M token input
            "output": 0.60 / 1_000_000   # €0.60 per 1M token output
        },
        "gpt-4o": {
            "input": 2.50 / 1_000_000,   # €2.50 per 1M token input
            "output": 10.00 / 1_000_000  # €10.00 per 1M token output
        }
    }
    
    model_pricing = pricing.get(model, pricing["gpt-4o-mini"])
    
    input_cost = input_tokens * model_pricing["input"]
    output_cost = output_tokens * model_pricing["output"]
    
    return input_cost + output_cost

