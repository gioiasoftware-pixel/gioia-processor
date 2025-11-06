# 📚 Documentazione Completa Processor - Fase 7

**Data**: 2025-01-XX  
**Versione**: 2.0.0  
**Scope**: Documentazione completa del refactored processor

---

## 📋 Indice

1. [Architettura](#architettura)
2. [Pipeline Processing](#pipeline-processing)
3. [API Endpoints](#api-endpoints)
4. [Configurazione](#configurazione)
5. [Database](#database)
6. [Logging e Monitoring](#logging-e-monitoring)
7. [Deployment](#deployment)

---

## Architettura

### Struttura Moduli

```
gioia-processor/
├── api/                    # FastAPI application
│   ├── main.py            # FastAPI app principale
│   └── routers/           # API routers
│       ├── ingest.py      # POST /process-inventory
│       ├── movements.py   # POST /process-movement
│       └── snapshot.py    # GET /api/inventory/snapshot, /api/viewer/*
│
├── core/                   # Moduli core
│   ├── config.py          # Configurazione (pydantic-settings)
│   ├── database.py        # Database interactions
│   ├── job_manager.py     # Job management
│   ├── logger.py          # Logging unificato
│   └── alerting.py        # Sistema alerting
│
├── ingest/                 # Pipeline processing
│   ├── gate.py            # Stage 0: Routing
│   ├── parser.py          # Stage 1: Parse classico
│   ├── llm_targeted.py    # Stage 2: IA mirata
│   ├── llm_extract.py     # Stage 3: LLM mode
│   ├── ocr_extract.py     # Stage 4: OCR
│   ├── pipeline.py        # Orchestratore principale
│   ├── validation.py      # Pydantic validation
│   ├── normalization.py   # Normalization functions
│   ├── csv_parser.py      # CSV parsing
│   └── excel_parser.py    # Excel parsing
│
├── tests/                  # Test suite
│   ├── test_*.py          # Test unitari e integration
│   └── data/              # Test fixtures
│
├── admin_notifications.py  # Admin notifications
├── viewer_generator.py     # Viewer HTML generation
├── jwt_utils.py           # JWT validation
└── start_processor.py     # Entry point
```

---

## Pipeline Processing

### Stage 0: Gate (Routing)

**File**: `ingest/gate.py`

**Funzione**: `route_file(file_content, file_name, ext) -> (stage, ext)`

**Logica**:
- CSV/Excel → `stage='csv_excel'` → Stage 1
- PDF/immagini → `stage='ocr'` → Stage 4
- Formato non supportato → `ValueError`

---

### Stage 1: Parse Classico

**File**: `ingest/parser.py`

**Funzione**: `parse_classic(file_content, file_name, ext) -> (wines_data, metrics, decision)`

**Flow**:
1. Parsing CSV/Excel (encoding detection, delimiter sniffing)
2. Header normalization e mapping
3. Value normalization (vintage, qty, price, type)
4. Pydantic validation
5. Calcolo metriche (`schema_score`, `valid_rows`)
6. Decision logic:
   - Se `schema_score >= 0.7` e `valid_rows >= 0.6` → `decision='save'`
   - Altrimenti → `decision='escalate_to_stage2'`

**Metriche**:
- `schema_score`: Colonne target coperte / 6
- `valid_rows`: Righe valide / totale

---

### Stage 2: IA Mirata

**File**: `ingest/llm_targeted.py`

**Funzione**: `apply_targeted_ai(wines_data, headers, file_name, ext) -> (wines_data, headers, schema_score, valid_rows, decision)`

**Flow**:
1. Disambiguazione header (Prompt P1) se necessario
2. Fix righe ambigue (Prompt P2) in batch da 20
3. Recalcolo metriche
4. Decision logic:
   - Se metriche migliorate → `decision='save'`
   - Altrimenti → `decision='escalate_to_stage3'`

**Modello LLM**: `gpt-4o-mini` (economico)

---

### Stage 3: LLM Mode

**File**: `ingest/llm_extract.py`

**Funzione**: `extract_llm_mode(file_content, file_name, ext) -> (wines_data, metrics, decision)`

**Flow**:
1. Preparazione input testo (CSV/Excel/TXT → testo grezzo)
2. Chunking se > 80KB (chunk 40KB con overlap 1KB)
3. Estrazione LLM per chunk (Prompt P3)
4. Deduplicazione vini
5. Normalizzazione e validazione
6. Decision: `decision='save'` se vini estratti, altrimenti `decision='error'`

**Modello LLM**: `gpt-4o` (robusto)

---

### Stage 4: OCR

**File**: `ingest/ocr_extract.py`

**Funzione**: `extract_ocr(file_content, file_name, ext) -> (wines_data, metrics, decision)`

**Flow**:
1. Estrazione testo da immagini (pytesseract) o PDF (pdf2image + pytesseract)
2. Passa testo a Stage 3 (LLM mode)
3. Ritorna risultati Stage 3

---

### Pipeline Orchestrator

**File**: `ingest/pipeline.py`

**Funzione**: `process_file(file_content, file_name, ext, telegram_id, business_name, correlation_id) -> (wines_data, metrics, decision, stage_used)`

**Flow Deterministico**:
```
Stage 0 (Gate) → Routing
  ├─ CSV/Excel → Stage 1
  │   ├─ OK → ✅ SALVA
  │   └─ Escalate → Stage 2
  │       ├─ OK → ✅ SALVA
  │       └─ Escalate → Stage 3
  │           ├─ OK → ✅ SALVA
  │           └─ Error → ❌ ERRORE
  └─ PDF/immagini → Stage 4
      └─ OCR → Stage 3
          ├─ OK → ✅ SALVA
          └─ Error → ❌ ERRORE
```

---

## API Endpoints

### POST /process-inventory

**Router**: `api/routers/ingest.py`

**Descrizione**: Elabora file inventario usando la nuova pipeline

**Request**:
- `telegram_id` (int)
- `business_name` (str)
- `file_type` (str): csv, excel, xlsx, xls, image, jpg, jpeg, png, pdf
- `file` (UploadFile)
- `mode` (str, optional): "add" o "replace" (default: "add")
- `dry_run` (bool, optional): Se True, solo anteprima (default: False)
- `client_msg_id` (str, optional): Per idempotency
- `correlation_id` (str, optional): Per logging

**Response**:
```json
{
  "status": "processing" | "success" | "error",
  "job_id": "uuid",
  "message": "...",
  "wines_count": 0,
  "preview": {...}
}
```

---

### POST /process-movement

**Router**: `api/routers/movements.py`

**Descrizione**: Processa movimento inventario (consumo/rifornimento)

**Request**:
- `telegram_id` (int)
- `business_name` (str)
- `wine_name` (str)
- `movement_type` (str): "consumo" o "rifornimento"
- `quantity` (int)

**Response**:
```json
{
  "status": "success" | "error",
  "message": "...",
  "wines_updated": [...]
}
```

---

### GET /status/{job_id}

**Router**: `api/main.py`

**Descrizione**: Ottieni stato job elaborazione

**Response**:
```json
{
  "job_id": "...",
  "status": "pending" | "processing" | "completed" | "error",
  "wines_count": 0,
  ...
}
```

---

### GET /health

**Router**: `api/main.py`

**Descrizione**: Health check del servizio

**Response**:
```json
{
  "status": "healthy",
  "service": "gioia-processor",
  "version": "2.0.0",
  ...
}
```

---

## Configurazione

### Variabili Ambiente

**File**: `core/config.py` (pydantic-settings)

#### Obbligatorie
- `DATABASE_URL`: URL connessione PostgreSQL

#### Opzionali
- `PORT`: Porta server (default: 8001)
- `OPENAI_API_KEY`: API key OpenAI (se mancante, AI disabilitata)

#### Feature Flags
- `IA_TARGETED_ENABLED`: Abilita Stage 2 (default: true)
- `LLM_FALLBACK_ENABLED`: Abilita Stage 3 (default: true)
- `OCR_ENABLED`: Abilita Stage 4 (default: true)

#### Soglie
- `CSV_MAX_ATTEMPTS`: Tentativi parsing CSV (default: 3)
- `SCHEMA_SCORE_TH`: Soglia schema score per escalation (default: 0.7)
- `MIN_VALID_ROWS`: Soglia righe valide per escalation (default: 0.6)
- `HEADER_CONFIDENCE_TH`: Soglia confidenza header mapping (default: 0.6)

#### LLM Configuration
- `BATCH_SIZE_AMBIGUOUS_ROWS`: Batch size Stage 2 (default: 20)
- `MAX_LLM_TOKENS`: Max token per chiamata LLM (default: 300)
- `LLM_MODEL_TARGETED`: Modello Stage 2 (default: "gpt-4o-mini")
- `LLM_MODEL_EXTRACT`: Modello Stage 3 (default: "gpt-4o")

---

## Database

### Tabelle

#### `users`
- `id`: Primary key
- `telegram_id`: ID Telegram (unique)
- `business_name`: Nome business
- `onboarding_completed`: Boolean

#### `processing_jobs`
- `job_id`: Primary key (UUID)
- `telegram_id`: FK verso users
- `status`: pending, processing, completed, error
- `client_msg_id`: Per idempotency
- `file_type`, `file_name`, `file_size_bytes`
- `total_wines`, `processed_wines`, `saved_wines`
- `processing_method`: Stage utilizzato
- `created_at`, `started_at`, `completed_at`

#### Tabelle dinamiche per utente
- `inventario_{telegram_id}`: Inventario vini
- `consumi_{telegram_id}`: Log movimenti

---

## Logging e Monitoring

### Logging JSON

**File**: `core/logger.py`

**Funzione**: `log_json(level, message, **kwargs)`

**Campi obbligatori**:
- `correlation_id`: ID correlazione
- `telegram_id`: ID Telegram utente
- `stage`: Stage pipeline (csv_parse, ia_targeted, llm_mode, ocr)
- `decision`: Decisione finale (save, escalate_to_stage2, escalate_to_stage3, error)
- `elapsed_sec`: Tempo elaborazione

**Formato**:
```json
{
  "timestamp": "2025-01-XX...",
  "level": "info",
  "message": "...",
  "correlation_id": "...",
  "telegram_id": 123,
  "stage": "csv_parse",
  "decision": "save",
  "elapsed_sec": 1.5,
  "metrics": {...}
}
```

### Alerting

**File**: `core/alerting.py`

**Alert configurati**:
1. **Stage 3 Failure**: Alert se >= 5 fallimenti in 60 minuti
2. **LLM Cost**: Alert se >= €0.50 in 60 minuti
3. **Error Rate**: Alert se >= 10 errori in 60 minuti

**Notifiche**: Inviate via `admin_notifications` table

---

## Deployment

### Railway

**File**: `Procfile`, `railway.json`

**Command**: `python start_processor.py`

**Variabili ambiente**:
- `DATABASE_URL`: PostgreSQL connection string
- `OPENAI_API_KEY`: OpenAI API key
- `PORT`: Porta server (Railway auto-configura)

### Entry Point

**File**: `start_processor.py`

**Uso**: `uvicorn api.main:app --host 0.0.0.0 --port 8001`

---

## Testing

### Test Suite

**Directory**: `tests/`

**Test disponibili**:
- `test_parsers.py`: Test parsing CSV/Excel
- `test_normalization.py`: Test normalization
- `test_validation.py`: Test Pydantic validation
- `test_gate.py`: Test routing
- `test_llm_targeted.py`: Test Stage 2 (con mock)
- `test_llm_extract.py`: Test Stage 3 (con mock)
- `test_ocr.py`: Test Stage 4 (con mock)
- `test_ingest_flow.py`: Test pipeline completa
- `test_endpoints.py`: Test endpoint API
- `test_performance.py`: Test performance
- `test_llm_costs.py`: Test costi LLM
- `test_error_handling.py`: Test error handling
- `test_real_data_assets.py`: Test con file reali

**Eseguire test**:
```bash
pytest tests/
pytest tests/ --cov=ingest --cov=core --cov=api
```

---

## Compatibilità

### Backward Compatibility

✅ **Endpoint invariati**: Tutti gli endpoint mantengono signature originale
✅ **Response format invariato**: Formato JSON compatibile con bot
✅ **Bot compatibility**: Bot funziona senza modifiche

---

## Performance

### Tempi Target

- **Stage 1**: < 2s per file normale
- **Stage 2**: < 5s per batch
- **Stage 3**: < 15s per chunk
- **End-to-end**: < 30s per file normale

### Costi LLM

- **Stage 2**: `gpt-4o-mini` (~€0.15/1M input)
- **Stage 3**: `gpt-4o` (~€2.50/1M input) solo se necessario
- **Totale**: < €0.10 per file medio

---

## Roadmap

### Miglioramenti Futuri

- [ ] Cache Redis per performance
- [ ] Rate limiting API
- [ ] Monitoring avanzato (Datadog, Logtail)
- [ ] Supporto più formati file
- [ ] OCR migliorato con AI
- [ ] Batch processing per file grandi

---

## Supporto

### Documentazione Aggiuntiva

- `report/VERIFICA_COMPLETA.md`: Verifica completa refactoring
- `report/ENV_VARIABLES.md`: Documentazione variabili ambiente
- `README.md`: Documentazione principale progetto

### Troubleshooting

**Problemi comuni**:
1. **Database connection error**: Verifica `DATABASE_URL`
2. **OpenAI API error**: Verifica `OPENAI_API_KEY`
3. **Port binding error**: Verifica `PORT` (Railway auto-configura)

**Logs**: Tutti i log in formato JSON su stdout (leggibili in Railway dashboard)

---

**Versione**: 2.0.0  
**Data**: 2025-01-XX




