# 🏗️ Piano Refactor - Gioia Processor

**Data**: 04/11/2025  
**Obiettivo**: Piano dettagliato per refactor del processor secondo pipeline target

---

## 📁 Struttura Target

```
gioia-processor/
├── ingest/                    # 🆕 NUOVO - Pipeline ingest
│   ├── __init__.py
│   ├── gate.py               # 🆕 Stage 0 - Routing file
│   ├── csv_parser.py         # 🔄 Da csv_processor.py
│   ├── excel_parser.py       # 🔄 Da csv_processor.py
│   ├── normalization.py      # 🆕 Unificato da csv_processor.py + ocr_processor.py
│   ├── validation.py         # 🆕 NUOVO - Pydantic models
│   ├── llm_targeted.py       # 🔄 Da ai_processor.py (parte)
│   ├── llm_extract.py        # 🔄 Da ai_processor.py (parte)
│   ├── ocr.py                # 🔄 Da ocr_processor.py + pdf_processor.py
│   └── pipeline.py           # 🆕 NUOVO - Orchestratore pipeline
│
├── core/                      # 🆕 NUOVO - Core functionality
│   ├── __init__.py
│   ├── config.py             # 🔄 Da config.py (migliorato con pydantic-settings)
│   ├── database.py           # 🔄 Da database.py
│   ├── job_manager.py        # 🆕 Da main.py (logica job)
│   └── logger.py             # 🆕 Da logging_config.py + structured_logging.py
│
├── api/                       # 🆕 NUOVO - API layer
│   ├── __init__.py
│   ├── main.py               # 🔄 Da main.py (ridotto)
│   └── routers/
│       ├── __init__.py
│       ├── ingest.py         # 🆕 Endpoint ingest
│       ├── snapshot.py       # 🆕 Endpoint viewer/snapshot
│       └── export.py         # 🆕 Endpoint export
│
├── tests/                     # 🆕 NUOVO - Test suite
│   ├── data/                 # 🆕 Fixture test
│   ├── test_parsers.py
│   ├── test_normalization.py
│   ├── test_llm_targeted.py
│   ├── test_llm_extract.py
│   └── test_ingest_flow.py
│
├── main.py                    # ⚠️ DA RIMUOVERE - Sostituito da api/main.py
├── csv_processor.py           # ⚠️ DA RIMUOVERE - Sostituito da ingest/
├── ocr_processor.py           # ⚠️ DA RIMUOVERE - Sostituito da ingest/ocr.py
├── ai_processor.py           # ⚠️ DA RIMUOVERE - Sostituito da ingest/llm_*.py
├── pdf_processor.py           # ⚠️ DA RIMUOVERE - Sostituito da ingest/ocr.py
│
├── database.py                # ✅ DA MANTENERE - Migrare a core/database.py
├── viewer_generator.py        # ✅ DA MANTENERE - Non toccare
├── jwt_utils.py               # ✅ DA MANTENERE - Non toccare
├── admin_notifications.py     # ✅ DA MANTENERE - Non toccare
├── start_processor.py         # ✅ DA MANTENERE - Entry point
│
├── config.py                  # ⚠️ DA RIMUOVERE - Sostituito da core/config.py
├── logging_config.py          # ⚠️ DA RIMUOVERE - Sostituito da core/logger.py
├── structured_logging.py      # ⚠️ DA RIMUOVERE - Integrato in core/logger.py
│
└── migrations/                # ✅ DA MANTENERE
```

---

## 🔄 Mappatura File Esistenti → File Nuovi

### File da Creare (🆕 NUOVO)

| File Nuovo | Origine | Note |
|-----------|---------|------|
| `ingest/gate.py` | Nessuna | Routing file per tipo |
| `ingest/validation.py` | Nessuna | Pydantic models (completamente nuovo) |
| `ingest/pipeline.py` | Nessuna | Orchestratore pipeline (completamente nuovo) |
| `core/job_manager.py` | `main.py` | Estrarre logica job |
| `core/logger.py` | `logging_config.py` + `structured_logging.py` | Unificare logging |
| `api/routers/ingest.py` | `main.py` | Endpoint ingest |
| `api/routers/snapshot.py` | `main.py` | Endpoint viewer |
| `api/routers/export.py` | `main.py` | Endpoint export |

### File da Refactorare (🔄)

| File Esistente | File Nuovo | Azione |
|----------------|------------|--------|
| `csv_processor.py` | `ingest/csv_parser.py` | Estrai parsing CSV |
| `csv_processor.py` | `ingest/excel_parser.py` | Estrai parsing Excel |
| `csv_processor.py` | `ingest/normalization.py` | Estrai normalizzazione |
| `ocr_processor.py` | `ingest/ocr.py` | Refactor completo |
| `pdf_processor.py` | `ingest/ocr.py` | Integrare OCR PDF |
| `ai_processor.py` | `ingest/llm_targeted.py` | Estrai Stage 2 |
| `ai_processor.py` | `ingest/llm_extract.py` | Estrai Stage 3 |
| `config.py` | `core/config.py` | Migliorare con pydantic-settings |
| `database.py` | `core/database.py` | Spostare (mantenere logica) |
| `main.py` | `api/main.py` | Ridurre, spostare endpoint in routers |

### File da Rimuovere (⚠️ DA RIMUOVERE)

| File | Motivo | Quando |
|------|--------|-------|
| `main.py` | Sostituito da `api/main.py` | Dopo migrazione endpoint |
| `csv_processor.py` | Sostituito da `ingest/` | Dopo migrazione |
| `ocr_processor.py` | Sostituito da `ingest/ocr.py` | Dopo migrazione |
| `ai_processor.py` | Sostituito da `ingest/llm_*.py` | Dopo migrazione |
| `pdf_processor.py` | Sostituito da `ingest/ocr.py` | Dopo migrazione |
| `config.py` | Sostituito da `core/config.py` | Dopo migrazione |
| `logging_config.py` | Sostituito da `core/logger.py` | Dopo migrazione |
| `structured_logging.py` | Integrato in `core/logger.py` | Dopo migrazione |

### File da Mantenere (✅)

| File | Motivo |
|------|--------|
| `database.py` | Migrare a `core/database.py` ma mantenere logica |
| `viewer_generator.py` | Non parte della pipeline ingest |
| `jwt_utils.py` | Utilità semplice, mantenere |
| `admin_notifications.py` | Utilità semplice, mantenere |
| `start_processor.py` | Entry point, mantenere |
| `migrations/` | SQL migrations, mantenere |

---

## 📋 Lista Azioni Dettagliata

### Fase 1: Setup Architettura

1. **Creare struttura directory**
   ```bash
   mkdir -p gioia-processor/ingest
   mkdir -p gioia-processor/core
   mkdir -p gioia-processor/api/routers
   mkdir -p gioia-processor/tests/data
   ```

2. **Creare `__init__.py`**
   - `ingest/__init__.py`
   - `core/__init__.py`
   - `api/__init__.py`
   - `api/routers/__init__.py`

### Fase 2: Implementazione Moduli Ingest

1. **`ingest/validation.py`** (🆕 NUOVO)
   - Definire `WineItemModel` (Pydantic v2)
   - Funzione `validate_batch()`

2. **`ingest/normalization.py`** (🔄 Unificato)
   - `normalize_column_name()` da `csv_processor.py`
   - `clean_wine_name()` da `csv_processor.py`
   - `clean_ocr_text()` da `ocr_processor.py` → `clean_text()`
   - `classify_wine_type()` da `csv_processor.py` (versione più completa)
   - `map_headers()` con rapidfuzz (🆕 NUOVO)
   - `normalize_values()` con regex vintage, qty extraction (🆕 NUOVO)

3. **`ingest/csv_parser.py`** (🔄 Da `csv_processor.py`)
   - `detect_csv_separator()` (mantenere)
   - Parsing CSV con pandas (mantenere)
   - Integrare `ingest/normalization.py`

4. **`ingest/excel_parser.py`** (🔄 Da `csv_processor.py`)
   - Parsing Excel con pandas (mantenere)
   - Integrare `ingest/normalization.py`

5. **`ingest/gate.py`** (🆕 NUOVO)
   - `route_file()` - Routing per tipo file

6. **`ingest/parser.py`** (🆕 NUOVO - Orchestratore Stage 1)
   - `parse_classic()` - Orchestra Stage 1
   - Calcolo metriche (`schema_score`, `valid_rows`)
   - Logica decisionale (passare a Stage 2 o SALVA)

7. **`ingest/llm_targeted.py`** (🔄 Da `ai_processor.py`)
   - `disambiguate_headers()` - Prompt 1 ottimizzato
   - `fix_ambiguous_rows()` - Prompt 2 nuovo
   - `apply_targeted_ai()` - Orchestratore Stage 2

8. **`ingest/llm_extract.py`** (🔄 Da `ai_processor.py`)
   - `prepare_text_input()` - Conversione CSV/Excel → testo
   - `extract_with_llm()` - Estrazione con Prompt 3
   - `extract_llm_mode()` - Orchestratore Stage 3 con chunking

9. **`ingest/ocr.py`** (🔄 Da `ocr_processor.py` + `pdf_processor.py`)
   - `extract_text_from_image()` - OCR immagini
   - `extract_text_from_pdf()` - OCR PDF (🆕 NUOVO)
   - `process_ocr()` - Orchestratore OCR → Stage 3

10. **`ingest/pipeline.py`** (🆕 NUOVO)
    - `process_file()` - Orchestratore completo pipeline Stage 0-4

### Fase 3: Implementazione Core

1. **`core/config.py`** (🔄 Da `config.py`)
   - Migrare a `pydantic-settings`
   - Aggiungere feature flags
   - Aggiungere soglie e tentativi

2. **`core/database.py`** (🔄 Da `database.py`)
   - Spostare file (mantenere logica)
   - Aggiungere batch insert/upsert

3. **`core/job_manager.py`** (🆕 NUOVO)
   - Estrarre logica job da `main.py`
   - Funzioni: `create_job()`, `update_job_status()`, `get_job()`

4. **`core/logger.py`** (🆕 NUOVO)
   - Unificare `logging_config.py` + `structured_logging.py`
   - Structured logging JSON (structlog/loguru)

### Fase 4: Implementazione API

1. **`api/main.py`** (🔄 Da `main.py`)
   - Ridurre a setup FastAPI + import routers
   - Mantenere middleware CORS
   - Mantenere startup event

2. **`api/routers/ingest.py`** (🆕 NUOVO)
   - `POST /process-inventory` - Usa `ingest/pipeline.py`

3. **`api/routers/snapshot.py`** (🆕 NUOVO)
   - Migrare endpoint viewer da `main.py`

4. **`api/routers/export.py`** (🆕 NUOVO)
   - Migrare endpoint export da `main.py`

### Fase 5: Migrazione e Cleanup

1. **Aggiornare import**
   - Sostituire import `csv_processor`, `ocr_processor`, `ai_processor` in tutto il codice
   - Aggiornare import in `start_processor.py`

2. **Test compatibilità**
   - Verificare che endpoint funzionino
   - Verificare che bot funzioni senza modifiche

3. **Rimuovere file obsoleti**
   - Rimuovere `main.py` (vecchio)
   - Rimuovere `csv_processor.py`
   - Rimuovere `ocr_processor.py`
   - Rimuovere `ai_processor.py`
   - Rimuovere `pdf_processor.py`
   - Rimuovere `config.py` (vecchio)
   - Rimuovere `logging_config.py`
   - Rimuovere `structured_logging.py`

---

## 🔗 Compatibilità Endpoint

### Endpoint da Mantenere Invariati

| Endpoint | File Attuale | File Nuovo | Compatibilità |
|----------|--------------|------------|---------------|
| `POST /process-inventory` | `main.py` | `api/routers/ingest.py` | ✅ Invariato |
| `POST /process-movement` | `main.py` | `api/main.py` (mantenere) | ✅ Invariato |
| `GET /status/{job_id}` | `main.py` | `api/main.py` (mantenere) | ✅ Invariato |
| `GET /api/inventory/snapshot` | `main.py` | `api/routers/snapshot.py` | ✅ Invariato |
| `GET /api/inventory/export.csv` | `main.py` | `api/routers/export.py` | ✅ Invariato |

**Nota**: Tutti gli endpoint mantengono stessa signature e formato response. Solo implementazione interna cambia.

---

## 📊 Azioni Manuali Richieste

### 1. Variabili Ambiente

Aggiungere in `.env`:
```env
# Feature flags
IA_TARGETED_ENABLED=true
LLM_FALLBACK_ENABLED=true
OCR_ENABLED=true

# Tentativi / soglie
CSV_MAX_ATTEMPTS=3
SCHEMA_SCORE_TH=0.7
MIN_VALID_ROWS=0.6
HEADER_CONFIDENCE_TH=0.75

# IA mirata
BATCH_SIZE_AMBIGUOUS_ROWS=20
MAX_LLM_TOKENS=300
LLM_MODEL_TARGETED=gpt-4o-mini
LLM_MODEL_EXTRACT=gpt-4o

# OCR
OCR_EXTENSIONS=pdf,jpg,jpeg,png

# Batch DB
DB_INSERT_BATCH_SIZE=500
```

### 2. Dipendenze

Aggiungere in `requirements.txt`:
```txt
pydantic>=2.0
pydantic-settings>=2.0
rapidfuzz>=3.0
structlog>=23.0  # o loguru
charset-normalizer>=3.0
pdf2image>=1.16  # per OCR PDF
```

### 3. Test

Eseguire test dopo ogni fase:
```bash
# Test unitari
python -m pytest tests/

# Test endpoint
curl -X POST http://localhost:8001/process-inventory ...
```

---

## ✅ Checklist Migrazione

- [ ] Fase 1: Setup architettura
- [ ] Fase 2: Implementazione moduli ingest
- [ ] Fase 3: Implementazione core
- [ ] Fase 4: Implementazione API
- [ ] Fase 5: Migrazione e cleanup
- [ ] Test compatibilità bot
- [ ] Deploy staging
- [ ] Deploy produzione
- [ ] Rimozione file obsoleti

---

**Ultimo aggiornamento**: 04/11/2025

