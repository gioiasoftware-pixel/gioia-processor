# Flow Processor e Costi IA - Documentazione Completa

## 📋 Indice
1. [Flow Completo Processor](#flow-completo-processor)
2. [Chiamate IA e Costi](#chiamate-ia-e-costi)
3. [Dettaglio Stage per Stage](#dettaglio-stage-per-stage)
4. [Post-Processing](#post-processing)
5. [Stima Costi Totali](#stima-costi-totali)

---

## 🔄 Flow Completo Processor

### Entry Point
**File**: `api/routers/ingest.py`  
**Endpoint**: `POST /process-inventory`

### Flow Diagram
```
┌─────────────────────────────────────────────────────────────┐
│ 1. POST /process-inventory                                   │
│    - Riceve file (CSV/Excel/PDF/Immagine)                    │
│    - Crea job_id                                             │
│    - Avvia process_inventory_background (async)              │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ 2. process_inventory_background                              │
│    - Aggiorna job status = 'processing'                      │
│    - Chiama process_file() (pipeline orchestrator)           │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ 3. process_file() - Pipeline Orchestrator                   │
│    File: ingest/pipeline.py                                 │
│                                                              │
│    ┌──────────────────────────────────────────┐            │
│    │ Stage 0: Routing (gate.py)               │            │
│    │ - Determina tipo file                    │            │
│    │ - CSV/Excel → percorso csv_excel         │            │
│    │ - PDF/Immagine → percorso ocr           │            │
│    └──────────────────────────────────────────┘            │
│                      ↓                                       │
│    ┌──────────────────────────────────────────┐            │
│    │ PERCORSO CSV/EXCEL                       │            │
│    │                                          │            │
│    │ ┌────────────────────────────────────┐   │            │
│    │ │ Stage 1: Parse Classico           │   │            │
│    │ │ File: ingest/parser.py            │   │            │
│    │ │ - NO IA                            │   │            │
│    │ │ - Fuzzy matching header           │   │            │
│    │ │ - Normalizzazione valori          │   │            │
│    │ │ - Validazione Pydantic            │   │            │
│    │ │ Decision: 'save' o 'escalate'     │   │            │
│    │ └────────────────────────────────────┘   │            │
│    │              ↓                           │            │
│    │    ┌────────────────────────────────────┐│            │
│    │    │ Stage 2: IA Mirata (Targeted)     ││            │
│    │    │ File: ingest/llm_targeted.py     ││            │
│    │    │ - ✅ CHIAMATA IA (gpt-4o-mini)    ││            │
│    │    │ - Disambiguazione header (P1)    ││            │
│    │    │ - Fix righe ambigue (P2)         ││            │
│    │    │ Decision: 'save' o 'escalate'     ││            │
│    │    └────────────────────────────────────┘│            │
│    │              ↓                           │            │
│    │    ┌────────────────────────────────────┐│            │
│    │    │ Stage 3: LLM Mode (Extract)       ││            │
│    │    │ File: ingest/llm_extract.py       ││            │
│    │    │ - ✅ CHIAMATA IA (gpt-4o)         ││            │
│    │    │ - Estrazione da testo grezzo     ││            │
│    │    │ - Chunking se > 80KB             ││            │
│    │    │ - Deduplicazione                 ││            │
│    │    │ Decision: 'save' o 'error'        ││            │
│    │    └────────────────────────────────────┘│            │
│    └──────────────────────────────────────────┘            │
│                                                              │
│    ┌──────────────────────────────────────────┐            │
│    │ PERCORSO PDF/IMMAGINI                    │            │
│    │                                          │            │
│    │ ┌────────────────────────────────────┐   │            │
│    │ │ Stage 4: OCR                       │   │            │
│    │ │ File: ingest/ocr_extract.py       │   │            │
│    │ │ - OCR (pytesseract)                │   │            │
│    │ │ - Estrae testo                     │   │            │
│    │ │ - Passa a Stage 3 internamente     │   │            │
│    │ │   (quindi chiama gpt-4o)           │   │            │
│    │ └────────────────────────────────────┘   │            │
│    └──────────────────────────────────────────┘            │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ 4. Salvataggio Database                                     │
│    - batch_insert_wines()                                   │
│    - Aggiorna job status = 'completed'                       │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ 5. Post-Processing (Background)                             │
│    File: post_processing.py                                 │
│    - Normalizzazione inventario salvato                    │
│    - ✅ CHIAMATA IA (gpt-4o-mini) - Validazione            │
│    - Max 3 retry se trova errori                            │
└─────────────────────────────────────────────────────────────┘
```

---

## 🤖 Chiamate IA e Costi

### Modelli Utilizzati

| Modello | Uso | Costo Input | Costo Output | File |
|---------|-----|-------------|--------------|------|
| **gpt-4o-mini** | Stage 2 (IA Mirata) | €0.15/1M | €0.60/1M | `ingest/llm_targeted.py` |
| **gpt-4o-mini** | Post-Processing | €0.15/1M | €0.60/1M | `post_processing.py` |
| **gpt-4o** | Stage 3 (LLM Extract) | €2.50/1M | €10.00/1M | `ingest/llm_extract.py` |

### Configurazione Modelli
**File**: `core/config.py`

```python
llm_model_targeted: str = "gpt-4o-mini"  # Stage 2
llm_model_extract: str = "gpt-4o"        # Stage 3
llm_model_post_processing: str = "gpt-4o-mini"  # Post-processing
```

---

## 📊 Dettaglio Stage per Stage

### Stage 0: Routing (NO IA)
**File**: `ingest/gate.py`  
**Costo**: €0.00  
**Descrizione**: Determina il percorso di elaborazione in base al tipo file.

---

### Stage 1: Parse Classico (NO IA)
**File**: `ingest/parser.py`  
**Costo**: €0.00  
**Descrizione**: 
- Parsing CSV/Excel classico
- Fuzzy matching header (rapidfuzz)
- Normalizzazione valori
- Validazione Pydantic

**Quando viene chiamato**: Sempre per file CSV/Excel

**Decisioni possibili**:
- `'save'`: Se schema_score > threshold → Salva direttamente
- `'escalate_to_stage2'`: Se schema_score basso o righe ambigue

---

### Stage 2: IA Mirata (Targeted AI) ✅ CHIAMATA IA
**File**: `ingest/llm_targeted.py`  
**Modello**: `gpt-4o-mini`  
**Costo Input**: €0.15/1M token  
**Costo Output**: €0.60/1M token  
**Max Tokens**: 300 (configurabile, default)

**Quando viene chiamato**: 
- Solo se Stage 1 decide `'escalate_to_stage2'`
- Solo se `IA_TARGETED_ENABLED=true` (default: true)

**Chiamate IA**:

#### 2.1 Disambiguazione Header (Prompt P1)
**Funzione**: `disambiguate_headers()`  
**Quando**: Se header ambigui o non mappati correttamente  
**Input tipico**: ~50-200 token (lista header)  
**Output tipico**: ~20-50 token (JSON mapping)  
**Costo stimato**: €0.00001 - €0.00005 per chiamata

**Prompt**:
```
Sei un assistente che abbina nomi di colonne a campi noti.
Campi target: name, winery, vintage, qty, price, type.
```

#### 2.2 Fix Righe Ambigue (Prompt P2)
**Funzione**: `fix_ambiguous_rows()`  
**Quando**: Se ci sono righe con dati ambigui o malformati  
**Input tipico**: ~100-500 token per batch (20 righe)  
**Output tipico**: ~50-200 token (JSON correzioni)  
**Costo stimato**: €0.00002 - €0.0001 per batch

**Prompt**:
```
Correggi righe ambigue usando mapping colonne fornito.
```

**Stima Costo Stage 2**:
- **Caso ottimale** (1 chiamata P1): ~€0.00001
- **Caso medio** (1 P1 + 2 batch P2): ~€0.00005
- **Caso pessimo** (1 P1 + 10 batch P2): ~€0.0002

---

### Stage 3: LLM Mode (Extract) ✅ CHIAMATA IA
**File**: `ingest/llm_extract.py`  
**Modello**: `gpt-4o`  
**Costo Input**: €2.50/1M token  
**Costo Output**: €10.00/1M token  
**Max Tokens**: 6000 (default)

**Quando viene chiamato**: 
- Se Stage 2 decide `'escalate_to_stage3'`
- Se Stage 4 (OCR) estrae testo
- Solo se `LLM_FALLBACK_ENABLED=true` (default: true)

**Chiamate IA**:

#### 3.1 Estrazione da Testo (Prompt P3)
**Funzione**: `extract_with_llm()`  
**Quando**: Sempre in Stage 3  
**Input tipico**: 
- File piccolo (< 80KB): ~2000-5000 token
- File grande (> 80KB): Chunking in parti da ~40KB (overlap 1KB)
  - Chunk 1: ~5000-10000 token
  - Chunk 2: ~5000-10000 token
  - ... (fino a N chunk)

**Output tipico**: 
- File piccolo: ~1000-3000 token (JSON array vini)
- File grande: ~2000-5000 token per chunk

**Costo stimato**:
- **File piccolo** (1 chunk, ~3000 input, ~2000 output): 
  - Input: 3000 × €2.50/1M = €0.0075
  - Output: 2000 × €10.00/1M = €0.02
  - **Totale: ~€0.03**
  
- **File medio** (2 chunk, ~8000 input, ~4000 output):
  - Input: 8000 × €2.50/1M = €0.02
  - Output: 4000 × €10.00/1M = €0.04
  - **Totale: ~€0.06**
  
- **File grande** (5 chunk, ~20000 input, ~10000 output):
  - Input: 20000 × €2.50/1M = €0.05
  - Output: 10000 × €10.00/1M = €0.10
  - **Totale: ~€0.15**

**Prompt**:
```
Estrai tutti i vini da questo testo CSV/Excel.
Output SOLO JSON array valido con schema WineItemModel.
```

#### 3.2 Retry con Prompt Rafforzato
**Funzione**: `extract_with_llm()` (retry logic)  
**Quando**: Se parsing JSON fallisce dopo 3 tentativi automatici  
**Costo**: Stesso di 3.1 (chiamata aggiuntiva)

**Stima Costo Stage 3**:
- **Caso ottimale** (file piccolo, 1 chiamata): ~€0.03
- **Caso medio** (file medio, 2 chunk): ~€0.06
- **Caso pessimo** (file grande, 5 chunk + retry): ~€0.30

---

### Stage 4: OCR (NO IA diretta, ma chiama Stage 3)
**File**: `ingest/ocr_extract.py`  
**Costo OCR**: €0.00 (pytesseract locale)  
**Costo IA**: Vedi Stage 3 (chiamato internamente)

**Quando viene chiamato**: 
- File PDF o immagini (jpg, jpeg, png)
- Solo se `OCR_ENABLED=true` (default: true)

**Flow**:
1. OCR estrae testo da PDF/immagine
2. Testo passa a Stage 3 (LLM Extract)
3. Costo IA = Costo Stage 3

---

## 🔄 Post-Processing

**File**: `post_processing.py`  
**Modello**: `gpt-4o-mini`  
**Costo Input**: €0.15/1M token  
**Costo Output**: €0.60/1M token  
**Max Tokens**: 1500

**Quando viene chiamato**: 
- Dopo che l'inventario è stato salvato (job status = 'completed')
- In background, non blocca l'utente
- Max 3 retry se trova errori

**Chiamate IA**:

#### Post-Processing: Validazione LLM
**Funzione**: `validate_wines_with_llm()`  
**Quando**: Dopo normalizzazione base (estrazione regione, normalizzazione valori)  
**Input tipico**: 
- Campione di 20 vini: ~2000-4000 token (JSON)
- Prompt validazione: ~500 token
- **Totale input**: ~2500-4500 token

**Output tipico**: 
- Se nessun errore: ~50-100 token
- Se errori trovati: ~500-1000 token (correzioni + pattern comuni)

**Costo stimato**:
- **Nessun errore** (1 chiamata, ~3000 input, ~100 output):
  - Input: 3000 × €0.15/1M = €0.00045
  - Output: 100 × €0.60/1M = €0.00006
  - **Totale: ~€0.0005**
  
- **Errori trovati** (1 chiamata + retry, ~4000 input, ~800 output):
  - Input: 4000 × €0.15/1M = €0.0006
  - Output: 800 × €0.60/1M = €0.00048
  - **Totale: ~€0.001**

- **Max retry** (3 chiamate):
  - **Totale: ~€0.003**

**Prompt**:
```
Analizza questo campione di vini e identifica errori comuni e PATTERN RICORRENTI.
Cerca: nomi che sono categorie, pattern non estratti, tipi vino errati, dati incoerenti.
```

**Stima Costo Post-Processing**:
- **Caso ottimale** (nessun errore, 1 chiamata): ~€0.0005
- **Caso medio** (errori trovati, 2 chiamate): ~€0.002
- **Caso pessimo** (max retry, 3 chiamate): ~€0.003

---

## 💰 Stima Costi Totali

### Scenario 1: File CSV/Excel Semplice (Stage 1 OK)
**Flow**: Stage 0 → Stage 1 → Salva  
**Costo IA**: €0.00  
**Tempo**: ~2-5 secondi

---

### Scenario 2: File CSV/Excel Medio (Stage 1 → Stage 2)
**Flow**: Stage 0 → Stage 1 → Stage 2 → Salva  
**Costo IA**: 
- Stage 2: ~€0.00005 (1 P1 + 2 batch P2)
- Post-Processing: ~€0.0005
- **Totale: ~€0.00055**

**Tempo**: ~5-10 secondi

---

### Scenario 3: File CSV/Excel Complesso (Stage 1 → Stage 2 → Stage 3)
**Flow**: Stage 0 → Stage 1 → Stage 2 → Stage 3 → Salva  
**Costo IA**: 
- Stage 2: ~€0.00005
- Stage 3: ~€0.06 (file medio, 2 chunk)
- Post-Processing: ~€0.002
- **Totale: ~€0.062**

**Tempo**: ~15-30 secondi

---

### Scenario 4: File CSV/Excel Molto Grande (Stage 1 → Stage 2 → Stage 3)
**Flow**: Stage 0 → Stage 1 → Stage 2 → Stage 3 (5 chunk) → Salva  
**Costo IA**: 
- Stage 2: ~€0.0002
- Stage 3: ~€0.15 (5 chunk)
- Post-Processing: ~€0.003
- **Totale: ~€0.153**

**Tempo**: ~30-60 secondi

---

### Scenario 5: File PDF/Immagine (OCR → Stage 3)
**Flow**: Stage 0 → Stage 4 (OCR) → Stage 3 → Salva  
**Costo IA**: 
- Stage 3: ~€0.06 (file medio)
- Post-Processing: ~€0.002
- **Totale: ~€0.062**

**Tempo**: ~20-40 secondi

---

## 📈 Riepilogo Costi per Tipo File

| Tipo File | Stage Usati | Costo IA Min | Costo IA Max | Costo IA Medio |
|-----------|-------------|--------------|--------------|----------------|
| CSV/Excel Semplice | Stage 1 | €0.00 | €0.00 | €0.00 |
| CSV/Excel Medio | Stage 1-2 | €0.0005 | €0.001 | €0.00075 |
| CSV/Excel Complesso | Stage 1-3 | €0.03 | €0.15 | €0.06 |
| PDF/Immagine | Stage 4-3 | €0.03 | €0.15 | €0.06 |

**Nota**: I costi includono sempre il post-processing (~€0.0005-€0.003).

---

## ⚙️ Configurazione e Ottimizzazione

### Variabili Ambiente per Controllo Costi

```bash
# Abilita/Disabilita Stage
IA_TARGETED_ENABLED=true      # Stage 2 (default: true)
LLM_FALLBACK_ENABLED=true     # Stage 3 (default: true)
OCR_ENABLED=true              # Stage 4 (default: true)

# Modelli (per cambiare costi)
LLM_MODEL_TARGETED=gpt-4o-mini    # Stage 2 (default: gpt-4o-mini)
LLM_MODEL_EXTRACT=gpt-4o           # Stage 3 (default: gpt-4o)
LLM_MODEL_POST_PROCESSING=gpt-4o-mini  # Post-processing (default: gpt-4o-mini)

# Limiti Token
MAX_LLM_TOKENS=300            # Stage 2 (default: 300)
MAX_LLM_TOKENS_EXTRACT=6000   # Stage 3 (default: 6000)
```

### Ottimizzazioni Implementate

1. **Stop Early**: Se Stage 1 ha successo, non chiama Stage 2-3
2. **Modelli Economici**: Stage 2 e Post-Processing usano `gpt-4o-mini` (10x più economico)
3. **Chunking Intelligente**: Stage 3 divide file grandi per evitare token eccessivi
4. **Retry Limitato**: Post-Processing max 3 retry
5. **Campione Limitato**: Post-Processing valida solo 20 vini (non tutto l'inventario)

---

## 📝 Note Finali

- **Costi reali** possono variare in base a:
  - Dimensione file
  - Complessità dati
  - Numero chunk necessari
  - Errori trovati in post-processing

- **Monitoraggio costi**: 
  - Log dettagliati in `core/alerting.py`
  - Alert se costo supera soglia (configurabile)

- **Riduzione costi**:
  - Disabilita Stage 2 se non necessario (`IA_TARGETED_ENABLED=false`)
  - Usa modelli più economici (es. `gpt-4o-mini` per Stage 3 se accettabile)
  - Riduci `max_tokens` se possibile

---

**Ultimo aggiornamento**: Gennaio 2025  
**Versione Processor**: 2.0.0


