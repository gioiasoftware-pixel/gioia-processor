# 🔎 Gap Analysis - Gioia Processor

**Data**: 04/11/2025  
**Obiettivo**: Confronto tra pipeline attuale e pipeline target

---

## 📊 Pipeline Attuale vs Target

### Pipeline Attuale (Come Funziona Oggi)

```
File Input
    ↓
main.py::process_inventory_background()
    ↓
├─ CSV → csv_processor.py::process_csv_file()
│   ├─ Auto-rilevamento encoding/separatore
│   ├─ Mapping colonne (statico + AI se necessario)
│   ├─ Estrazione dati righe
│   ├─ Deduplicazione
│   └─ Validazione AI (opzionale)
│
├─ Excel → csv_processor.py::process_excel_file()
│   ├─ Parsing Excel
│   ├─ Mapping colonne (statico + AI se necessario)
│   ├─ Estrazione dati righe
│   ├─ Deduplicazione
│   └─ Validazione AI (opzionale)
│
├─ Image → ocr_processor.py::process_image_ocr()
│   ├─ OCR (pytesseract)
│   ├─ Estrazione vini da testo (AI o pattern)
│   ├─ Miglioramento AI
│   └─ Validazione AI
│
└─ PDF → pdf_processor.py::process_pdf_file()
    └─ ⚠️ NotImplementedError
    
    ↓
save_inventory_to_db()
```

**Problemi Attuali**:
- ❌ Non c'è pipeline deterministica (non ci sono metriche per decidere quando passare a stage successivo)
- ❌ AI viene usata sempre, anche quando non necessario (costi alti)
- ❌ Non c'è validazione Pydantic strutturata
- ❌ Non c'è logging JSON strutturato con metriche
- ❌ Non c'è Stage 0 (Gate) esplicito
- ❌ Non c'è Stage 2 (IA mirata) - AI viene chiamata sempre, non solo per ambiguità
- ❌ Non c'è Stage 3 (LLM mode) - Non c'è estrazione da testo grezzo per CSV rotti
- ⚠️ OCR va direttamente ad AI, non passa per LLM mode se necessario

---

## 🎯 Pipeline Target (Come Dovrebbe Funzionare)

```
Stage 0 — Gate iniziale
    ↓
├─ ext ∈ {csv,tsv,xlsx,xls} → Stage 1
├─ ext ∈ {pdf,jpg,jpeg,png} → Stage 4 (OCR)
└─ altro → errore formato non supportato

Stage 1 — Parse classico (NO IA)
    ├─ Encoding detection (utf-8-sig → utf-8 → latin-1)
    ├─ Delimiter sniff (CSV)
    ├─ Parsing (pandas)
    ├─ Header cleaning (normalization)
    ├─ Header mapping (sinonimi + rapidfuzz)
    ├─ Value normalization
    ├─ Validazione Pydantic
    ├─ Calcolo metriche (schema_score, valid_rows)
    └─ Decisione:
        ├─ Se schema_score ≥ 0.7 e valid_rows ≥ 0.6 → ✅ SALVA
        └─ Altrimenti → Stage 2

Stage 2 — IA mirata (micro-aggiustamenti)
    ├─ Se colonne ambigue → Prompt 1 (disambiguazione)
    ├─ Se valori problematici → Prompt 2 (correzione batch)
    ├─ Ricalcola metriche
    └─ Decisione:
        ├─ Se supera soglie → ✅ SALVA
        └─ Altrimenti → Stage 3

Stage 3 — LLM mode (estrazione tabellare)
    ├─ Preparazione input testo
    ├─ Chunking se >80 KB
    ├─ Estrazione con LLM (Prompt 3)
    ├─ Unione blocchi
    ├─ Deduplicazione
    ├─ Validazione Pydantic
    └─ Decisione:
        ├─ Se rows_valid > 0 → ✅ SALVA
        └─ Altrimenti → ❌ ERRORE

Stage 4 — OCR (solo PDF/immagine)
    ├─ OCR (pytesseract)
    ├─ Estrazione testo
    └─ → Stage 3 (LLM mode)
```

---

## 🔍 Gap Analysis per Stage

### Stage 0 — Gate iniziale

| Componente | Stato Attuale | Stato Target | Gap |
|-----------|---------------|--------------|-----|
| Routing per tipo file | ⚙️ **PARZIALE** | ✅ Richiesto | ⚠️ Routing esiste in `main.py` ma non è modulare |
| Gestione errori formato | ✅ **PRESENTE** | ✅ Richiesto | ✅ OK |
| Logging routing | ❌ **ASSENTE** | ✅ Richiesto | ⚠️ Manca logging strutturato |

**Gap**:
- ⚠️ Routing esiste ma non è modulare (non c'è `ingest/gate.py`)
- ⚠️ Non c'è logging strutturato per routing decision

**Azione**: Creare `ingest/gate.py` con funzione `route_file()`

---

### Stage 1 — Parse classico (NO IA)

| Componente | Stato Attuale | Stato Target | Gap |
|-----------|---------------|--------------|-----|
| Encoding detection | ✅ **PRESENTE** | ✅ Richiesto | ✅ OK (chardet in `csv_processor.py`) |
| Delimiter sniff | ✅ **PRESENTE** | ✅ Richiesto | ✅ OK (`detect_csv_separator`) |
| Parsing CSV | ✅ **PRESENTE** | ✅ Richiesto | ✅ OK (pandas) |
| Parsing Excel | ✅ **PRESENTE** | ✅ Richiesto | ✅ OK (pandas) |
| Header cleaning | ⚙️ **PARZIALE** | ✅ Richiesto | ⚠️ Esiste `normalize_column_name()` ma non completo |
| Header mapping | ✅ **PRESENTE** | ✅ Richiesto | ⚠️ Usa dizionario statico, manca rapidfuzz |
| Value normalization | ⚙️ **PARZIALE** | ✅ Richiesto | ⚠️ Esiste ma non strutturato, manca regex vintage/qty |
| Validazione Pydantic | ❌ **ASSENTE** | ✅ Richiesto | 🔴 **CRITICO** - Manca completamente |
| Calcolo metriche | ❌ **ASSENTE** | ✅ Richiesto | 🔴 **CRITICO** - Manca schema_score e valid_rows |
| Decisione pipeline | ❌ **ASSENTE** | ✅ Richiesto | 🔴 **CRITICO** - Non c'è logica decisionale |

**Gap Critici**:
- 🔴 **Manca validazione Pydantic** - Non c'è `WineItemModel`
- 🔴 **Manca calcolo metriche** - Non c'è `schema_score` e `valid_rows`
- 🔴 **Manca decisione pipeline** - Non c'è logica per decidere quando passare a Stage 2
- ⚠️ Header mapping usa dizionario statico, manca rapidfuzz per fuzzy matching
- ⚠️ Value normalization non strutturato (manca regex vintage, estrazione qty da "12 bottiglie")

**Azione**:
1. Creare `ingest/validation.py` con `WineItemModel` (Pydantic)
2. Creare `ingest/normalization.py` con:
   - `normalize_column_name()` (migliorato)
   - `map_headers()` (con rapidfuzz)
   - `normalize_values()` (vintage regex, qty extraction, price parsing)
3. Creare `ingest/parser.py` (orchestratore Stage 1) con:
   - Calcolo metriche
   - Logica decisionale

---

### Stage 2 — IA mirata

| Componente | Stato Attuale | Stato Target | Gap |
|-----------|---------------|--------------|-----|
| Disambiguazione colonne | ⚙️ **PARZIALE** | ✅ Richiesto | ⚠️ Esiste `ai_processor.analyze_csv_structure()` ma non è mirato |
| Correzione valori batch | ❌ **ASSENTE** | ✅ Richiesto | 🔴 **CRITICO** - Non esiste |
| Prompt 1 (disambiguazione) | ⚙️ **PARZIALE** | ✅ Richiesto | ⚠️ Prompt esiste ma non è ottimizzato (troppo lungo) |
| Prompt 2 (correzione valori) | ❌ **ASSENTE** | ✅ Richiesto | 🔴 **CRITICO** - Non esiste |
| Ricalcolo metriche | ❌ **ASSENTE** | ✅ Richiesto | 🔴 **CRITICO** - Manca |
| Decisione pipeline | ❌ **ASSENTE** | ✅ Richiesto | 🔴 **CRITICO** - Manca |

**Gap Critici**:
- 🔴 **Manca Stage 2 completamente** - AI viene chiamata sempre, non solo per ambiguità
- 🔴 **Manca prompt 2** - Non c'è correzione valori batch
- 🔴 **Manca logica decisionale** - Non c'è ricalcolo metriche e decisione

**Azione**:
1. Creare `ingest/llm_targeted.py` con:
   - `disambiguate_headers()` - Prompt 1 ottimizzato
   - `fix_ambiguous_rows()` - Prompt 2 nuovo
   - `apply_targeted_ai()` - Orchestratore Stage 2

---

### Stage 3 — LLM mode

| Componente | Stato Attuale | Stato Target | Gap |
|-----------|---------------|--------------|-----|
| Preparazione input testo | ❌ **ASSENTE** | ✅ Richiesto | 🔴 **CRITICO** - Non esiste |
| Chunking | ❌ **ASSENTE** | ✅ Richiesto | 🔴 **CRITICO** - Non esiste |
| Estrazione LLM | ⚙️ **PARZIALE** | ✅ Richiesto | ⚠️ Esiste `ai_processor.extract_wines_from_text()` ma non è ottimizzato |
| Prompt 3 (estrazione tabellare) | ⚙️ **PARZIALE** | ✅ Richiesto | ⚠️ Prompt esiste ma non è ottimizzato per CSV rotti |
| Unione blocchi | ❌ **ASSENTE** | ✅ Richiesto | 🔴 **CRITICO** - Non esiste |
| Deduplicazione | ✅ **PRESENTE** | ✅ Richiesto | ✅ OK (`deduplicate_wines`) |
| Validazione Pydantic | ❌ **ASSENTE** | ✅ Richiesto | 🔴 **CRITICO** - Manca |

**Gap Critici**:
- 🔴 **Manca Stage 3 completamente** - Non c'è estrazione da testo grezzo per CSV rotti
- 🔴 **Manca chunking** - Non c'è gestione file grandi
- 🔴 **Manca preparazione input** - Non c'è conversione CSV/Excel → testo grezzo

**Azione**:
1. Creare `ingest/llm_extract.py` con:
   - `prepare_text_input()` - Conversione CSV/Excel → testo
   - `extract_with_llm()` - Estrazione con Prompt 3 ottimizzato
   - `extract_llm_mode()` - Orchestratore Stage 3 con chunking

---

### Stage 4 — OCR

| Componente | Stato Attuale | Stato Target | Gap |
|-----------|---------------|--------------|-----|
| OCR immagini | ✅ **PRESENTE** | ✅ Richiesto | ✅ OK (pytesseract) |
| OCR PDF | ❌ **ASSENTE** | ✅ Richiesto | 🔴 **CRITICO** - Manca (pdf2image) |
| Passaggio a Stage 3 | ⚠️ **PARZIALE** | ✅ Richiesto | ⚠️ OCR va direttamente ad AI, non passa per Stage 3 |

**Gap**:
- 🔴 **Manca OCR PDF** - `pdf_processor.py` solleva NotImplementedError
- ⚠️ **Flusso non corretto** - OCR va direttamente ad AI, dovrebbe passare per Stage 3 (LLM mode)

**Azione**:
1. Implementare OCR PDF in `ingest/ocr.py` con `pdf2image`
2. Modificare flusso OCR: OCR → testo → Stage 3 (non direttamente AI)

---

## 📊 Riepilogo Gap

| Stage | Componenti OK | Componenti Parziali | Componenti Mancanti | Criticità |
|-------|---------------|---------------------|---------------------|-----------|
| Stage 0 | 1 | 1 | 0 | ⚠️ Media |
| Stage 1 | 4 | 3 | 3 | 🔴 **ALTA** |
| Stage 2 | 0 | 1 | 5 | 🔴 **ALTA** |
| Stage 3 | 1 | 1 | 5 | 🔴 **ALTA** |
| Stage 4 | 1 | 1 | 1 | 🔴 **ALTA** |

---

## 🎯 Priorità Interventi

### Priority 1 (Critico)
1. ✅ **Validazione Pydantic** - Creare `WineItemModel`
2. ✅ **Calcolo metriche** - Implementare `schema_score` e `valid_rows`
3. ✅ **Logica decisionale Stage 1** - Decidere quando passare a Stage 2
4. ✅ **Stage 2 completo** - Implementare IA mirata
5. ✅ **Stage 3 completo** - Implementare LLM mode

### Priority 2 (Importante)
1. ⚠️ **Normalizzazione valori** - Migliorare regex vintage, estrazione qty
2. ⚠️ **Header mapping rapidfuzz** - Fuzzy matching colonne
3. ⚠️ **OCR PDF** - Implementare supporto PDF
4. ⚠️ **Logging strutturato** - JSON con metriche

### Priority 3 (Nice to Have)
1. ⚠️ **Gate modulare** - Creare `ingest/gate.py`
2. ⚠️ **Chunking ottimizzato** - Gestione file molto grandi

---

**Ultimo aggiornamento**: 04/11/2025

