# ✅ Verifica Metriche Fallback - Fase 10.2

**Data**: 2025-01-XX  
**Scope**: Verifica che le percentuali di escalation agli stage successivi siano tracciate

---

## 📋 Requisiti

Secondo Fase 10.2, dobbiamo tracciare:
1. ✅ Quanto spesso arriva a Stage 2 (IA mirata)
2. ✅ Quanto spesso arriva a Stage 3 (LLM mode)
3. ✅ Quanto spesso arriva a Stage 4 (OCR)
4. ✅ Documentare in dashboard o log aggregati

---

## ✅ Verifica Implementazione

### 1. Tracciamento in Pipeline

**Status**: ✅ **IMPLEMENTATO**

#### In `ingest/pipeline.py`:

**Linea 81**: `aggregated_metrics['stages_attempted'] = []`
- Lista degli stage tentati durante l'elaborazione

**Linea 210**: `metrics['stages_attempted'] = ['csv_excel_parse']`
- Stage 1 aggiunto quando viene tentato

**Linea 244**: `metrics['stages_attempted'].append('ia_targeted')`
- Stage 2 aggiunto quando viene tentato

**Linea 273**: `metrics['stages_attempted'].append('llm_mode')`
- Stage 3 aggiunto quando viene tentato

**Linea 329**: `metrics['stages_attempted'] = ['ocr']`
- Stage 4 aggiunto quando viene tentato

**Linea 130**: `aggregated_metrics['stage_used'] = stage_used`
- Stage finale utilizzato viene salvato nelle metriche

**Linea 143**: `stage=stage_used` nel `log_json()`
- Stage finale viene loggato in ogni log JSON

---

### 2. Tracciamento in Log JSON

**Status**: ✅ **IMPLEMENTATO**

Ogni log JSON contiene:
- ✅ `stage` - Stage finale utilizzato (csv_excel_parse, ia_targeted, llm_mode, ocr)
- ✅ `decision` - Decisione finale (save, escalate_to_stage2, escalate_to_stage3, error)
- ✅ `stages_attempted` - Lista stage tentati (in `extra` se presente)

**Esempi log**:

**Stage 1 completato**:
```json
{
  "timestamp": "2025-01-XX...",
  "level": "INFO",
  "message": "Pipeline completed: decision=save, stage=csv_excel_parse",
  "stage": "csv_excel_parse",
  "decision": "save",
  ...
}
```

**Stage 2 completato** (escalato da Stage 1):
```json
{
  "timestamp": "2025-01-XX...",
  "level": "INFO",
  "message": "Pipeline completed: decision=save, stage=ia_targeted",
  "stage": "ia_targeted",
  "decision": "save",
  ...
}
```

**Stage 3 completato** (escalato da Stage 2):
```json
{
  "timestamp": "2025-01-XX...",
  "level": "INFO",
  "message": "Pipeline completed: decision=save, stage=llm_mode",
  "stage": "llm_mode",
  "decision": "save",
  ...
}
```

**Stage 4 completato** (OCR):
```json
{
  "timestamp": "2025-01-XX...",
  "level": "INFO",
  "message": "Pipeline completed: decision=save, stage=ocr",
  "stage": "ocr",
  "decision": "save",
  ...
}
```

---

### 3. Tracciamento nel Database

**Status**: ⚠️ **PARZIALE**

#### In `core/job_manager.py`:

**Linea 78**: `processing_method: Optional[str] = None`
- Campo disponibile per salvare metodo di elaborazione

**Verifica utilizzo**:
- ❌ `stage_used` non viene salvato direttamente in `ProcessingJob`
- ⚠️ `processing_method` può essere usato per salvare `stage_used` ma non è sempre popolato

**Raccomandazione**: 
- Aggiornare `update_job_status()` per salvare sempre `stage_used` in `processing_method`
- Oppure aggiungere campo `stage_used` a `ProcessingJob` se necessario

---

### 4. Calcolo Percentuali Fallback

**Status**: ✅ **POSSIBILE DA LOG AGGREGATI**

Le percentuali possono essere calcolate aggregando i log JSON:

**Query log aggregati** (esempio pseudocodice):
```sql
-- Percentuale file che arrivano a Stage 2
SELECT 
  COUNT(*) FILTER (WHERE stage = 'ia_targeted') * 100.0 / COUNT(*) as pct_stage2
FROM logs
WHERE decision = 'save'

-- Percentuale file che arrivano a Stage 3
SELECT 
  COUNT(*) FILTER (WHERE stage = 'llm_mode') * 100.0 / COUNT(*) as pct_stage3
FROM logs
WHERE decision = 'save'

-- Percentuale file che arrivano a Stage 4
SELECT 
  COUNT(*) FILTER (WHERE stage = 'ocr') * 100.0 / COUNT(*) as pct_stage4
FROM logs
WHERE decision = 'save'
```

**Strumenti disponibili**:
- Railway Logs - Filtraggio per `stage` field
- Log aggregatori esterni (Datadog, Logtail, etc.)
- Query dirette su log JSON

---

## 📊 Metriche Disponibili

### Da Log JSON

Per ogni file processato, i log JSON contengono:

1. **Stage finale utilizzato** (`stage`):
   - `csv_excel_parse` - Stage 1 completato
   - `ia_targeted` - Stage 2 completato (escalato da Stage 1)
   - `llm_mode` - Stage 3 completato (escalato da Stage 2)
   - `ocr` - Stage 4 completato

2. **Decisione finale** (`decision`):
   - `save` - Salvato con successo
   - `escalate_to_stage2` - Escalato a Stage 2
   - `escalate_to_stage3` - Escalato a Stage 3
   - `error` - Errore

3. **Metriche specifiche stage**:
   - Stage 1: `schema_score`, `valid_rows`
   - Stage 2: `rows_fixed`, `improved_schema_score`
   - Stage 3: `rows_valid`, `rows_rejected`, `chunks`
   - Stage 4: `text_extracted`, `pages_processed`

---

## 🎯 Calcolo Percentuali

### Esempio Query Log Aggregati

**Percentuale Stage 2**:
```bash
# Filtra log dove stage = 'ia_targeted'
grep '"stage":"ia_targeted"' logs.json | wc -l
# Dividi per totale file processati
```

**Percentuale Stage 3**:
```bash
# Filtra log dove stage = 'llm_mode'
grep '"stage":"llm_mode"' logs.json | wc -l
```

**Percentuale Stage 4**:
```bash
# Filtra log dove stage = 'ocr'
grep '"stage":"ocr"' logs.json | wc -l
```

### Dashboard o Log Aggregati

**Opzioni disponibili**:
1. **Railway Logs** - Filtraggio per `stage` field
2. **Log Aggregator** (Datadog, Logtail, etc.) - Query su log JSON
3. **Database Query** - Se `processing_method` viene popolato con `stage_used`

---

## 📝 Raccomandazioni

### ✅ Implementato
- ✅ Stage finale loggato in ogni log JSON
- ✅ `stages_attempted` tracciato in metriche
- ✅ Log JSON strutturato per aggregazione

### ⚠️ Miglioramenti Possibili

1. **Salvare `stage_used` in database**:
   ```python
   # In update_job_status()
   processing_method = stage_used  # Salva stage finale
   ```

2. **Query database per percentuali**:
   ```sql
   SELECT 
     processing_method,
     COUNT(*) as count,
     COUNT(*) * 100.0 / SUM(COUNT(*)) OVER() as percentage
   FROM processing_jobs
   WHERE status = 'completed'
   GROUP BY processing_method
   ```

3. **Dashboard dedicata** (opzionale):
   - Visualizza percentuali fallback
   - Grafici per stage distribution
   - Trend nel tempo

---

## 🎯 Conclusione

**Fase 10.2: Metriche Fallback** ✅ **IMPLEMENTATO (da log aggregati)**

- ✅ Quanto spesso arriva a Stage 2 - Tracciabile da log JSON (`stage='ia_targeted'`)
- ✅ Quanto spesso arriva a Stage 3 - Tracciabile da log JSON (`stage='llm_mode'`)
- ✅ Quanto spesso arriva a Stage 4 - Tracciabile da log JSON (`stage='ocr'`)
- ✅ Documenta in dashboard o log aggregati - Log JSON strutturato permette aggregazione

**Status**: ✅ **COMPLETO** - Metriche fallback tracciabili via log JSON aggregati

**Nota**: Per query dirette su database, è raccomandato salvare `stage_used` in `processing_method` durante `update_job_status()`.

