# 📋 Audit Componenti - Gioia Processor

**Data**: 04/11/2025  
**Obiettivo**: Mappatura completa dei componenti esistenti prima del refactor

---

## 📁 Struttura Directory Attuale

```
gioia-processor/
├── main.py                    # FastAPI app principale (1689 righe)
├── database.py                # Modelli DB, gestione tabelle dinamiche (809 righe)
├── csv_processor.py           # Processamento CSV/Excel (685 righe)
├── ocr_processor.py           # Processamento OCR immagini (236 righe)
├── ai_processor.py            # Integrazione OpenAI GPT-4 (354 righe)
├── pdf_processor.py           # Placeholder PDF (33 righe)
├── viewer_generator.py        # Generazione HTML viewer (358 righe)
├── jwt_utils.py               # Validazione token JWT (32 righe)
├── config.py                  # Validazione configurazione (52 righe)
├── logging_config.py          # Setup logging colorato (57 righe)
├── structured_logging.py      # Logging con contesto (82 righe)
├── admin_notifications.py     # Notifiche admin bot (52 righe)
├── start_processor.py         # Entry point (47 righe)
├── requirements.txt           # Dipendenze
├── Procfile                   # Railway config
├── railway.json               # Railway config
├── README.md                  # Documentazione
├── migrations/                # SQL migrations
│   ├── 001_add_client_msg_id.sql
│   ├── 002_rate_limit.sql
│   └── 003_indices.sql
└── messaging/                 # (Directory - da verificare uso)
```

---

## 📄 Analisi File per File

### ✅ `main.py` - **ATTIVO** (Core)
**Responsabilità**: 
- FastAPI application setup
- Endpoint API principali
- Orchestrazione processamento inventario
- Gestione job asincroni
- Endpoint viewer/snapshot

**Funzioni principali**:
- `startup_event()` - Inizializzazione DB e AI
- `process_inventory()` - Endpoint POST `/process-inventory`
- `process_inventory_background()` - Elaborazione async
- `process_movement()` - Endpoint POST `/process-movement`
- `get_job_status()` - Endpoint GET `/status/{job_id}`
- `get_inventory_snapshot()` - Endpoint GET `/api/inventory/snapshot`
- `prepare_viewer_data_endpoint()` - Preparazione dati viewer
- Altri endpoint: health, debug, AI test

**Stato**: ✅ **ATTIVO** - Da mantenere ma refactorare internamente  
**Note**: File molto grande (1689 righe), contiene logica che dovrebbe essere in moduli separati

---

### ✅ `database.py` - **ATTIVO** (Core)
**Responsabilità**:
- Modelli SQLAlchemy (User, ProcessingJob)
- Gestione connessione DB asincrona
- Creazione tabelle dinamiche utente
- Funzioni CRUD inventario

**Funzioni principali**:
- `get_db()` - Dependency injection per sessioni DB
- `ensure_user_tables()` - Crea tabelle dinamiche per utente
- `get_user_table_name()` - Genera nomi tabelle dinamiche
- `save_inventory_to_db()` - Salvataggio batch vini
- `get_inventory_status()` - Status inventario utente
- `get_user_inventories()` - Recupera inventari utente

**Stato**: ✅ **ATTIVO** - Da mantenere, migrare a `core/database.py`  
**Note**: Logica ben strutturata, da mantenere

---

### ✅ `csv_processor.py` - **ATTIVO** (Ingest)
**Responsabilità**:
- Parsing CSV/Excel
- Auto-rilevamento encoding/separatore
- Mapping colonne intelligente
- Normalizzazione valori
- Deduplicazione vini
- Estrazione dati da righe

**Funzioni principali**:
- `detect_csv_separator()` - Auto-rilevamento separatore
- `normalize_column_name()` - Normalizzazione nomi colonne
- `find_column_mapping()` - Mapping colonne con sinonimi
- `create_smart_column_mapping()` - Mapping intelligente
- `process_csv_file()` - Processamento CSV completo
- `process_excel_file()` - Processamento Excel completo
- `deduplicate_wines()` - Deduplicazione
- `extract_wine_data_from_row()` - Estrazione dati da riga
- `classify_wine_type()` - Classificazione tipo vino ⚠️ **DUPLICATO**
- `clean_wine_name()` - Pulizia nome vino
- `filter_italian_wines()` - Filtro vini italiani

**Stato**: ✅ **ATTIVO** - Da refactorare in `ingest/csv_parser.py`, `ingest/excel_parser.py`, `ingest/normalization.py`  
**Note**: File grande (685 righe), contiene logica da separare

---

### ✅ `ocr_processor.py` - **ATTIVO** (Ingest)
**Responsabilità**:
- OCR immagini (pytesseract)
- Estrazione vini da testo OCR
- Pattern matching per vini
- Pulizia testo OCR

**Funzioni principali**:
- `process_image_ocr()` - Processamento immagine completo
- `extract_wines_from_ocr_text()` - Estrazione vini da testo
- `clean_ocr_text()` - Pulizia testo
- `extract_wine_from_match()` - Estrazione da pattern match
- `extract_wine_generic()` - Estrazione generica
- `extract_wines_by_blocks()` - Estrazione per blocchi
- `classify_wine_type()` - Classificazione tipo vino ⚠️ **DUPLICATO**

**Stato**: ✅ **ATTIVO** - Da refactorare in `ingest/ocr.py`  
**Note**: Versione `classify_wine_type` leggermente diversa da `csv_processor.py`

---

### ✅ `ai_processor.py` - **ATTIVO** (Ingest)
**Responsabilità**:
- Integrazione OpenAI GPT-4
- Analisi CSV con AI
- Estrazione vini da testo
- Classificazione tipo vino
- Miglioramento dati vini
- Validazione batch vini

**Funzioni principali**:
- `AIProcessor.__init__()` - Inizializzazione client OpenAI
- `count_tokens()` - Conta token per limiti
- `analyze_csv_structure()` - Analisi struttura CSV con AI
- `extract_wines_from_text()` - Estrazione vini da testo con AI
- `classify_wine_type()` - Classificazione con AI
- `improve_wine_data()` - Miglioramento dati singolo vino
- `validate_wine_data()` - Validazione batch vini

**Stato**: ✅ **ATTIVO** - Da refactorare in `ingest/llm_targeted.py` e `ingest/llm_extract.py`  
**Note**: Logica AI sparsa, da organizzare secondo pipeline target

---

### ⚙️ `pdf_processor.py` - **PARZIALE** (Placeholder)
**Responsabilità**:
- Placeholder per processamento PDF

**Funzioni principali**:
- `process_pdf_file()` - Solleva NotImplementedError

**Stato**: ⚙️ **PARZIALE** - Da implementare in `ingest/ocr.py` (PDF → OCR)  
**Note**: Attualmente non implementato, solo placeholder

---

### ✅ `viewer_generator.py` - **ATTIVO** (Viewer)
**Responsabilità**:
- Generazione HTML viewer
- Cache dati viewer
- Cache HTML viewer

**Funzioni principali**:
- `generate_viewer_html_from_db()` - Genera HTML da DB
- `generate_viewer_html()` - Genera HTML da dati
- `get_viewer_html_from_cache()` - Recupera HTML da cache
- `store_viewer_html()` - Salva HTML in cache
- `prepare_viewer_data()` - Prepara dati per viewer
- `get_viewer_data_from_cache()` - Recupera dati da cache
- `_get_html_template()` - Template HTML

**Stato**: ✅ **ATTIVO** - Da mantenere, non parte della pipeline ingest  
**Note**: Logica viewer separata, non toccare

---

### ✅ `jwt_utils.py` - **ATTIVO** (Core)
**Responsabilità**:
- Validazione token JWT per viewer

**Funzioni principali**:
- `validate_viewer_token()` - Valida token JWT

**Stato**: ✅ **ATTIVO** - Da mantenere  
**Note**: Funzionalità semplice, mantenere

---

### ✅ `config.py` - **ATTIVO** (Core)
**Responsabilità**:
- Validazione variabili ambiente

**Funzioni principali**:
- `validate_config()` - Valida configurazione

**Stato**: ✅ **ATTIVO** - Da refactorare in `core/config.py` con pydantic-settings  
**Note**: Attualmente semplice, da espandere con feature flags

---

### ✅ `logging_config.py` - **ATTIVO** (Core)
**Responsabilità**:
- Setup logging colorato

**Funzioni principali**:
- `setup_colored_logging()` - Configura logging

**Stato**: ✅ **ATTIVO** - Da refactorare in `core/logger.py` con structured logging  
**Note**: Attualmente usa colorlog, da migrare a structlog/loguru

---

### ✅ `structured_logging.py` - **ATTIVO** (Core)
**Responsabilità**:
- Logging con contesto (correlation_id, telegram_id)

**Funzioni principali**:
- `set_request_context()` - Imposta contesto
- `get_request_context()` - Recupera contesto
- `get_correlation_id()` - Recupera correlation_id
- `log_with_context()` - Log con contesto

**Stato**: ✅ **ATTIVO** - Da integrare in `core/logger.py`  
**Note**: Buona base, da integrare con structured logging JSON

---

### ✅ `admin_notifications.py` - **ATTIVO** (Core)
**Responsabilità**:
- Invio notifiche admin bot

**Funzioni principali**:
- `enqueue_admin_notification()` - Accoda notifica

**Stato**: ✅ **ATTIVO** - Da mantenere  
**Note**: Funzionalità semplice, mantenere

---

### ✅ `start_processor.py` - **ATTIVO** (Entry Point)
**Responsabilità**:
- Entry point per Railway

**Funzioni principali**:
- Main che avvia uvicorn

**Stato**: ✅ **ATTIVO** - Da mantenere  
**Note**: Entry point, mantenere

---

## 📊 Riepilogo Stati

| Stato | Conteggio | File |
|-------|----------|------|
| ✅ **ATTIVO** | 12 | main.py, database.py, csv_processor.py, ocr_processor.py, ai_processor.py, viewer_generator.py, jwt_utils.py, config.py, logging_config.py, structured_logging.py, admin_notifications.py, start_processor.py |
| ⚙️ **PARZIALE** | 1 | pdf_processor.py |
| 🗑️ **OBSOLETO** | 0 | (Nessuno identificato) |

---

## 🎯 Prossimi Passi

1. **Analisi duplicazioni** → `AUDIT_DUPLICAZIONI.md`
2. **Gap analysis** → `AUDIT_GAP_ANALYSIS.md`
3. **Piano refactor** → `AUDIT_REFACTOR_PLAN.md`

---

**Ultimo aggiornamento**: 04/11/2025

