# 🔍 Diagnostica Pulizia Processor

**Data**: 2025-01-XX  
**Scope**: Identificare file/codice non utilizzato, duplicati, o orfani

---

## 📋 File da Analizzare

### File Python Principali
- ✅ `api/main.py` - FastAPI app principale
- ✅ `api/routers/ingest.py` - Router inventory processing
- ✅ `api/routers/movements.py` - Router movements
- ✅ `api/routers/snapshot.py` - Router viewer/snapshot
- ✅ `core/config.py` - Configurazione
- ✅ `core/database.py` - Database
- ✅ `core/job_manager.py` - Job management
- ✅ `core/logger.py` - Logging
- ✅ `core/alerting.py` - Alerting
- ✅ `ingest/gate.py` - Stage 0
- ✅ `ingest/parser.py` - Stage 1
- ✅ `ingest/llm_targeted.py` - Stage 2
- ✅ `ingest/llm_extract.py` - Stage 3
- ✅ `ingest/ocr_extract.py` - Stage 4
- ✅ `ingest/pipeline.py` - Orchestrator
- ✅ `ingest/validation.py` - Pydantic validation
- ✅ `ingest/normalization.py` - Normalization
- ✅ `ingest/csv_parser.py` - CSV parsing
- ✅ `ingest/excel_parser.py` - Excel parsing
- ✅ `admin_notifications.py` - Admin notifications
- ✅ `viewer_generator.py` - Viewer HTML generation
- ✅ `jwt_utils.py` - JWT validation

### File Script/Entry Point
- ✅ `start_processor.py` - Entry point principale
- ❓ `test_processor.py` - Test vecchio (da verificare)
- ❓ `test_local_processor.py` - Test locale (da verificare)

---

## 🔍 Analisi File

### File Potenzialmente Non Utilizzati

#### `test_processor.py`
**Status**: ❌ **DA ELIMINARE**
- File test vecchio, sostituito da `tests/` directory
- Non più utilizzato

#### `test_local_processor.py`
**Status**: ❌ **DA ELIMINARE**
- Script test locale temporaneo
- Non più necessario (test in `tests/`)

---

## 📄 File MD da Consolidare/Eliminare

### File MD da Consolidare in `report/`
- ✅ `VERIFICA_CRITERI_ACCETTAZIONE.md` → `report/VERIFICA_CRITERI_ACCETTAZIONE.md`
- ✅ `VERIFICA_ALERTING.md` → `report/VERIFICA_ALERTING.md`
- ✅ `VERIFICA_LOGGING_JSON.md` → `report/VERIFICA_LOGGING_JSON.md`
- ✅ `VERIFICA_METRICHE_FALLBACK.md` → `report/VERIFICA_METRICHE_FALLBACK.md`
- ✅ `VERIFICA_FASE_8_CLEANUP.md` → `report/VERIFICA_FASE_8_CLEANUP.md`
- ✅ `VERIFICA_COMPLETA_FASE_1-4.md` → `report/VERIFICA_COMPLETA_FASE_1-4.md`
- ✅ `VERIFICA_COMPLETA_FASE_1-5.md` → `report/VERIFICA_COMPLETA_FASE_1-5.md`
- ✅ `DIAGNOSTICA_BUG_TEST_FASE9.md` → `report/DIAGNOSTICA_BUG_TEST_FASE9.md`
- ✅ `RIEPILOGO_FASE_6.md` → `report/RIEPILOGO_FASE_6.md`
- ✅ `ENV_VARIABLES.md` → `report/ENV_VARIABLES.md`

### File MD da Mantenere (fuori da report)
- ✅ `README.md` - Documentazione principale progetto

### File MD da Eliminare
- ❌ Nessun file MD da eliminare (tutti utili per report)

---

## 🔧 Codice da Verificare

### Import Non Utilizzati
Da verificare manualmente import in ogni file.

### Funzioni Non Utilizzate
Da verificare manualmente funzioni non chiamate.

---

## 📊 Riepilogo Azioni

1. ✅ Eliminare `test_processor.py`
2. ✅ Eliminare `test_local_processor.py`
3. ✅ Creare cartella `report/`
4. ✅ Spostare tutti i file MD di verifica in `report/`
5. ✅ Consolidare verifiche in un unico file `report/VERIFICA_COMPLETA.md`
6. ✅ Completare Fase 7 (documentazione)
7. ✅ Spostare documentazione Fase 7 in `report/`

