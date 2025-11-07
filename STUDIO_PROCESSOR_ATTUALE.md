## Studio Processor Attuale

### Scopo del documento
- Fotografare lo stato reale del `gioia-processor` (novembre 2025) senza ipotizzare redesign.
- Evidenziare cosa fa ogni componente, quali input/risorse consuma, tempi/costi tipici e punti di attrito.
- Fornire base oggettiva a chi deve progettare miglioramenti incrementali.

---

### 1. Panoramica Rapida
- **Tipo**: pipeline asincrona FastAPI + orchestratore Python (pandas, rapidfuzz, OpenAI).
- **Entry point**: `POST /process-inventory` (`api/routers/ingest.py`).
- **Output**: salvataggio in tabella inventario dedicata a utente (`public."{telegram_id}_{business_name}_INVENTARIO"`).
- **Stages principali**: routing → Stage 0.5 (header identifier) → Stage 1 (parse classico) → Stage 2 (IA mirata) → Stage 3 (estrazione LLM) → Stage 4 (OCR, solo PDF/immagini) → post-processing + statistica.
- **Contesto multi-tenant**: create on-the-fly tabelle inventario/backup/log/consumi per ogni utente business.

---

### 2. Componenti e File Chiave
- `api/routers/ingest.py`: endpoint, job management, orchestrazione background, salvataggio DB, callback admin/bot.
- `ingest/pipeline.py`: orchestratore deterministico degli stage, logging strutturato, metriche aggregate.
- `ingest/header_identifier.py`: Stage 0.5 (identifica header multipli nei CSV, può estrarre già vini validi).
- `ingest/parser.py`: Stage 1 (parse classico, mapping header con rapidfuzz, normalizzazione valori, validation Pydantic).
- `ingest/llm_targeted.py`: Stage 2 (correzioni mirate con `gpt-4o-mini`).
- `ingest/llm_extract.py`: Stage 3 (estrazione completa con `gpt-4o`, chunking, deduplica).
- `ingest/ocr_extract.py`: Stage 4 (OCR via pytesseract → Stage 3 interno).
- `ingest/normalization.py`: libreria di normalizzazione header/valori (molto estesa, include inferenze da dizionari e fallback).
- `ingest/validation.py`: modelli Pydantic (`WineItemModel`) e batch validation.
- `core/config.py`: `ProcessorConfig` (env vars, feature flag: `IA_TARGETED_ENABLED`, `LLM_FALLBACK_ENABLED`, soglie mapping ecc.).
- `core/database.py`: connessioni async SQLAlchemy/asyncpg, creazione tabelle utente, `batch_insert_wines`.
- `post_processing.py`: normalizzazione finale + validazione LLM (gpt-4o-mini) su inventario salvato, retrial max 3.
- `core/logger.py`, `core/job_manager.py`, `admin_notifications.py`: logging JSON, job status, notifiche errori.

---

### 3. Flusso Dati (CSV/Excel)
1. **Stage 0 – Routing** (`ingest/gate.py`)
   - Identifica estensione, inoltra a percorso `csv_excel` o `ocr`.
   - Costo/tempo: trascurabile (<50 ms).

2. **Stage 0.5 – Header Identifier** (`ingest/header_identifier.py`)
   - Per CSV/TSV: scansiona più righe, cerca pattern header, crea mapping `DATABASE_FIELDS`.
   - Può produrre direttamente vini validi (se >=10 e valid_ratio ≥0.5 si ferma qui).
   - Tempo medio: 200‑500 ms su CSV 200 righe.

3. **Stage 1 – Parse classico** (`ingest/parser.py`)
   - Normalizza nomi colonne (`normalize_column_name`).
   - Mappa header via rapidfuzz (`map_headers`): threshold configurabile (`header_confidence_th` 0.55 default) e sinonimi estesi.
   - Converte ogni riga in dict includendo colonne non mappate (es. `Indice`).
   - `normalize_values` applica inferenze: estrazione nome/producer, lookup dizionari (`ingest/wine_terms_dict.py`), inferenza tipologia da “Indice”, conversione prezzi/quantità, blacklist righe rumorose.
   - Valida con `validate_batch` (Pydantic). Output `wines_data_valid`, metriche (`schema_score`, `valid_rows`, `rows_total`…).
   - Decisioni: `save` → fine; `escalate_to_stage2` → Stage 2; error → Stage 2.
   - Tempo medio: 0.5‑1.5 s per CSV 200 righe (dipende da pandas + normalizzazioni).

4. **Stage 2 – IA mirata** (`ingest/llm_targeted.py`, flag `IA_TARGETED_ENABLED`)
   - Prompt P1 (disambiguazione header) se mapping incerto.
   - Prompt P2 (fix righe) su batch da 20 righe (token limit 300).
   - Costo LLM: €0.00001‑€0.0002 per file, tempo 1‑3 s.
   - Decisioni: `save` o `escalate_to_stage3`.

5. **Stage 3 – LLM Extract** (`ingest/llm_extract.py`, flag `LLM_FALLBACK_ENABLED`)
   - Usa `gpt-4o`: chunking 80 KB, estrazione JSON secondo schema completo (include `min_quantity`).
   - Deduplica con `deduplicate_wines` (merge quantità).
   - Costo: ~€0.03‑€0.15 (2‑5 chunk), tempo 10‑30 s.

6. **Stage 4 – OCR** (`ingest/ocr_extract.py`)
   - Solo PDF/immagini: pytesseract → Stage 3.
   - Tempo 15‑30 s (OCR) + Stage 3, costo Stage 3.

7. **Unione Stage 0.5 + Stage 1/2/3**
   - Se Stage 0.5 ha estratto vini validi e Stage 1 li produce, vengono uniti e deduplicati.

8. **Salvataggio DB** (`core/database.batch_insert_wines`)
   - Batch size: default 500.
   - Inserisce 18 campi (name, producer, supplier, vintage, … notes) con timestamp.
   - Calcolo tabelle utente via `ensure_user_tables` (crea inventario/backup/log/consumi se non esistono).
   - Tempo: 100‑400 ms per 200 righe (dipende da rete/DB).

9. **Post-Processing** (`post_processing.py`)
   - Analizza inventario salvato: normalizza nuovamente, calcola statistiche, chiama LLM (gpt-4o-mini) per validazione.
   - Max 3 retry se trova anomalie (`invalid_wines_flagged`).
   - Costo: €0.0005‑€0.003, tempo 2‑5 s.

10. **Job Update & Notifiche**
    - `core/job_manager`: aggiorna stato (queued → processing → completed/error).
    - Notifiche admin tramite `admin_notifications.enqueue_admin_notification` su errori.

---

### 4. Dati Elaborati & Identità Vino
- Schema target (per riga): `name`, `winery`, `vintage`, `qty`, `price`, `type`, `min_quantity`, `supplier`, `grape_variety`, `region`, `country`, `classification`, `cost_price`, `alcohol_content`, `description`, `notes`.
- Normalizzazione attuale:
  - **Nome**: estrazione da pattern `Categoria (Nome)` + fallback da colonne `Etichetta/Label`; rimuove categorie pure.
  - **Produttore**: preferisce campo `winery`; se valore numerico → azzera (considerato ID).
  - **Fornitore**: popolato da colonne mappate `supplier`, blacklist per spostare nomi (es. `ceretto`, `winesider`).
  - **Tipologia**: inferenza da `type`, `name`, `Indice`, dizionari `wine_terms_dict`.
  - **Prezzi/Quantità**: regex per estrarre numeri, virgola europea.
- Deduplica: chiave = nome normalizzato + produttore + annata, merging quantità.
- Validazione Pydantic: obbliga `name` e `qty` ≥0.

---

### 5. Costi & Tempi Stimati (da `FLOW_PROCESSOR_E_COSTI_IA.md`)
| Scenario | Flow | Costo IA stimato | Tempo stimato |
|----------|------|------------------|---------------|
| CSV semplice | Stage 0 → 1 → save | €0.00 | 2‑5 s |
| CSV medio | Stage 0 → 1 → 2 → save | ~€0.00055 | 5‑10 s |
| CSV complesso | Stage 0 → 1 → 2 → 3 → save | ~€0.062 | 15‑30 s |
| CSV grande | Stage 0 → 1 → 2 → 3 (5 chunk) | ~€0.153 | 30‑60 s |
| PDF/immagine | Stage 0 → 4 → 3 → save | ~€0.062 | 20‑40 s |

---

### 6. Configurazione & Feature Flag
- `.env` caricato da `core/config.py` (`ProcessorConfig`).
- Variabili principali:
  - `DATABASE_URL`, `OPENAI_API_KEY`, `PORT`.
  - `IA_TARGETED_ENABLED`, `LLM_FALLBACK_ENABLED`, `OCR_ENABLED`.
  - Soglie Stage 1: `SCHEMA_SCORE_TH` (0.7), `MIN_VALID_ROWS` (0.6), `HEADER_CONFIDENCE_TH` (0.55).
  - Batch e modelli: `DB_INSERT_BATCH_SIZE`, `LLM_MODEL_TARGETED`, `LLM_MODEL_EXTRACT`, `LLM_MODEL_POST_PROCESSING`.
- Config validata a runtime (`validate_config`). Warning se OpenAI key assente (feature IA disabilitate automaticamente).

---

### 7. Dipendenze & Servizi Esterni
- **Database**: PostgreSQL (asyncpg via SQLAlchemy async). Tabelle per utente con indice su `name`, `producer`, `vintage`, `type`.
- **OpenAI**: modelli `gpt-4o`, `gpt-4o-mini`. Token monitorati via log (non c’è budget enforcement automatico).
- **OCR**: pytesseract locale; necessita dipendenze di sistema (Tesseract OCR) nel container.
- **Bot/Viewer**: callback HTTP verso `telegram-ai-bot` (link viewer) e `Vineinventory Viewer` (consuma DB direttamente).
- **Logging/Monitoring**: JSON logging (livello info-debug), `core.alerting.check_error_rate_alert` per threshold di errori.

---

### 8. Metriche & Osservabilità Attuale
- Ogni stage logga `elapsed_ms/sec`, `rows_total/valid`, decisioni, top motivi di scarto.
- `metrics` aggregati restituiti dalla pipeline: `schema_score`, `valid_rows`, `rows_filtered_blacklist`, `stage_used`, `stages_attempted`, `header_mapping`, `parse_info`.
- Post-processing produce stats: `total_rows`, `rows_flagged`, `invalid_wines_flagged`, `price_outliers`, ecc. (vedi `post_processing.normalize_saved_inventory`).
- Endpoint diagnostico appena aggiunto (`api/routers/diagnostics.py`) per interrogare stato pipeline.

---

### 9. Limitazioni Osservate (da diagnostica attuale)
- **Aggressività normalizzazione**: `normalize_values` può cambiare nomi/produttori validi (es. scarta valori numerici, sostituisce con categorie).
- **Confusione produttore/fornitore**: blacklist limitata, casi come "Wineinsider" finiscono in `producer`.
- **Mappature fuzzy**: soglia bassa → colonne sbagliate (es. `Etichetta` non mappata se noisy, `Indice` ignorato come header ma usato nei dati).
- **Stage 0.5**: produce vini ma li unisce con Stage 1 senza confronto qualità → possibile duplicazione/inconsistenza.
- **Costi LLM**: Stage 3 costoso su file grandi; mancano politiche di throttling/adaptive chunking.
- **Osservabilità**: log dettagliati ma dispersivi; non c’è dashboard sintetica.

---

### 10. Aree Miglioramento Incrementale (senza refactoring radicale)
- Introdurre modalità "safe" in Stage 1 (riutilizzando comportamento V1) quando mapping è affidabile.
- Rafforzare controllo identità vino (`nome`/`produttore`/`fornitore`) con liste di fornitori noti e log dedicati.
- Rendere opzionali le inferenze aggressive (`NormalizationPolicy` con flag) e tracciare ogni sovrascrittura.
- Consolidare metriche Stage 0.5/1/2/3 in diagnostica unica e inviare summary al bot.
- Ottimizzare Stage 3: ridurre chunk se Stage 1 ha già estratto dati sufficienti, introdurre early-exit.
- Migliorare `batch_insert_wines` per non perdere campi completi (oggi se `qty` mancante usa 0/1 di default).

---

### 11. Tempistiche Osservate (ultimi deploy)
- Deployment Railway con `nixpacks.toml` + `.dockerignore`: build ~2‑3 min.
- Pipeline Stage 1-only su inventario 130 vini: ~3‑4 s end-to-end (incluso salvataggio + post-processing).
- Pipeline Stage 3 (file complesso) su 300+ vini: 25‑35 s (dipende latenza OpenAI).
- Post-processing singolo inventario: 2‑4 s.

---

### 12. Risorse Documentali Collegate
- `FLOW_PROCESSOR_E_COSTI_IA.md`: diagrammi, costi IA, prompt dettagliati.
- `DIAGNOSTICA_POLISH.md`: elenco punti critici Stage 0‑4 + salvataggio.
- `PIANO_POLISH_PROCESSOR.md`: roadmap polish attuale (checklist in corso).
- `ANALISI_HEADER_MAPPING.md`, `ANALISI_45_VINI.md`, `ANALISI_PRODUTTORI_BOLLE.md`: analisi mirate su problemi reali.

---

### 13. Sintesi finale
Il processor attuale è completo e resiliente: accetta quasi ogni formato, automatizza estrazione e arricchimento, e mantiene logging dettagliato. I punti deboli sono concentrati nella normalizzazione Stage 1 (troppo invasiva), nell’identità produttore/fornitore e nell’elevato costo Stage 3. Le ottimizzazioni immediate possono inserirsi nell’architettura esistente mediante feature flag, safe mode e controlli mirati senza riscrivere l’orchestratore.


