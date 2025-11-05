# ✅ Verifica Sistema Alerting - Fase 10.3

**Data**: 2025-01-XX  
**Scope**: Verifica che gli alert siano configurati e funzionanti

---

## 📋 Requisiti

Secondo Fase 10.3, dobbiamo configurare:
1. ✅ Alert se Stage 3 fallisce spesso
2. ✅ Alert se costi LLM superano soglia
3. ✅ Alert se errori aumentano

---

## ✅ Verifica Implementazione

### 1. Modulo Alerting (`core/alerting.py`)

**Status**: ✅ **IMPLEMENTATO**

**Funzioni disponibili**:
- ✅ `check_stage3_failure_alert()` - Alert se Stage 3 fallisce spesso
- ✅ `check_llm_cost_alert()` - Alert se costi LLM superano soglia
- ✅ `check_error_rate_alert()` - Alert se errori aumentano
- ✅ `estimate_llm_cost()` - Stima costo LLM in base a modello e token

**Caratteristiche**:
- ✅ Contatori in-memory per finestre temporali (60 minuti default)
- ✅ Prevenzione spam (un alert per finestra)
- ✅ Cleanup automatico finestre vecchie
- ✅ Integrazione con `admin_notifications` per invio notifiche

---

### 2. Integrazione Alert Stage 3 Failure

**Status**: ✅ **IMPLEMENTATO**

**File**: `ingest/llm_extract.py`

**Linea 421-434**: Quando Stage 3 fallisce:
```python
# Alert se Stage 3 fallisce spesso
try:
    from core.alerting import check_stage3_failure_alert
    check_stage3_failure_alert(
        telegram_id=telegram_id,
        correlation_id=correlation_id,
        threshold=5,  # Alert se 5+ fallimenti in 60 min
        window_minutes=60
    )
except Exception as alert_error:
    logger.warning(f"[ALERT] Error checking Stage 3 failure alert: {alert_error}")
```

**Funzionamento**:
- ✅ Traccia ogni fallimento Stage 3 in finestra temporale
- ✅ Se fallimenti >= 5 in 60 minuti → invia alert
- ✅ Alert inviato via `admin_notifications` table
- ✅ Prevenzione spam (un alert per finestra)

---

### 3. Integrazione Alert Costi LLM

**Status**: ✅ **IMPLEMENTATO**

**File**: `ingest/llm_extract.py`

**Linea 198-235**: Quando viene fatta chiamata LLM:
```python
# Alert costi LLM se necessario
try:
    from core.alerting import check_llm_cost_alert, estimate_llm_cost
    import tiktoken
    
    # Stima token (approssimativo)
    encoding = tiktoken.encoding_for_model(config.llm_model_extract)
    input_tokens = len(encoding.encode(prompt))
    output_tokens = response.usage.completion_tokens if hasattr(response, 'usage') else 0
    
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
```

**Funzionamento**:
- ✅ Stima costo per ogni chiamata LLM (Stage 2 e Stage 3)
- ✅ Aggrega costi in finestra temporale (60 minuti)
- ✅ Se costi totali >= 0.50€ in 60 minuti → invia alert
- ✅ Prezzi aggiornati (gennaio 2025):
  - `gpt-4o-mini`: €0.15/1M input, €0.60/1M output
  - `gpt-4o`: €2.50/1M input, €10.00/1M output

---

### 4. Integrazione Alert Error Rate

**Status**: ✅ **IMPLEMENTATO**

**File**: `ingest/pipeline.py`

**Linea 157-178**: Quando pipeline fallisce:
```python
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
```

**Funzionamento**:
- ✅ Traccia ogni errore pipeline in finestra temporale
- ✅ Se errori >= 10 in 60 minuti → invia alert
- ✅ Alert inviato via `admin_notifications` table
- ✅ Prevenzione spam (un alert per finestra)

---

## 📊 Soglie Configurate

| Alert | Soglia | Finestra | Severità |
|-------|--------|----------|----------|
| Stage 3 Failure | 5 fallimenti | 60 minuti | Warning |
| LLM Cost | 0.50€ | 60 minuti | Warning |
| Error Rate | 10 errori | 60 minuti | Error |

---

## 🔧 Configurazione

### Soglie Modificabili

Le soglie sono hardcoded nei file, ma possono essere facilmente modificate:

**Stage 3 Failure** (`ingest/llm_extract.py`):
```python
threshold=5,  # Modificare qui
window_minutes=60
```

**LLM Cost** (`ingest/llm_extract.py`):
```python
threshold=0.50,  # Modificare qui
window_minutes=60
```

**Error Rate** (`ingest/pipeline.py`):
```python
threshold=10,  # Modificare qui
window_minutes=60
```

### Variabili Ambiente (Futuro)

Per rendere configurabili, si può aggiungere in `core/config.py`:
```python
alert_stage3_threshold: int = Field(default=5, description="Soglia fallimenti Stage 3 per alert")
alert_llm_cost_threshold: float = Field(default=0.50, description="Soglia costo LLM per alert (€)")
alert_error_rate_threshold: int = Field(default=10, description="Soglia errori per alert")
alert_window_minutes: int = Field(default=60, description="Finestra temporale alert (minuti)")
```

---

## 📝 Notifiche Admin

**Status**: ✅ **INTEGRATO**

Gli alert vengono inviati via `admin_notifications` table:

**Payload Alert**:
```json
{
  "alert_type": "stage3_failure_high" | "llm_cost_high" | "error_rate_high",
  "message": "Messaggio descrittivo",
  "threshold": 5 | 0.50 | 10,
  "failures_count" | "estimated_cost" | "error_count": valore,
  "window_minutes": 60,
  "component": "gioia-processor",
  "severity": "warning" | "error"
}
```

**Processamento**:
- ✅ Alert accodati in `admin_notifications` table
- ✅ Bot admin processa notifiche e invia alert Telegram
- ✅ Correlation ID tracciato per debugging

---

## 🎯 Conclusione

**Fase 10.3: Alerting** ✅ **IMPLEMENTATO**

- ✅ Alert se Stage 3 fallisce spesso — implementato in `llm_extract.py`
- ✅ Alert se costi LLM superano soglia — implementato in `llm_extract.py`
- ✅ Alert se errori aumentano — implementato in `pipeline.py`

**Status**: ✅ **COMPLETO** - Sistema alerting configurato e funzionante

**Nota**: 
- Le soglie sono configurabili modificando i valori nei file
- Per multi-istanza, considerare Redis per contatori condivisi
- Gli alert vengono inviati via `admin_notifications` table per processamento dal bot admin

