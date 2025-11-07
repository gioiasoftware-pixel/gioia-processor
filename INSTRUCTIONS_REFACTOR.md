## Roadmap ristrutturazione Processor

> Documento importato da istruzioni utente del 7 novembre 2025. Usare come riferimento ufficiale durante la ristrutturazione.

### 0) Ordine roadmap integrazione
1. Config & tipi → aggiungi provenance/confidence.
2. Header mapping v2 (Hungarian 1-a-1) + SAFE mode in normalization.
3. Resolver supplier/producer + nuovi campi `raw_*` e lineage.
4. Reconciler per stage (campo-per-campo, conf-based).
5. Dedup morbida.
6. LLM targeted solo per disambiguazione header.
7. Early-exit / guardrail Stage 3.
8. Logging diff-aware + diagnostica.
9. Test + fixture.

### 1) Config – nuovi flag/policy
- `core/config.py`
  ```python
  from typing import Literal

  class ProcessorConfig(BaseModel):
      # ... esistenti ...
      NORMALIZATION_POLICY: Literal["SAFE", "AGGRESSIVE"] = os.getenv("NORMALIZATION_POLICY", "SAFE")
      HEADER_CONFIDENCE_TH: float = float(os.getenv("HEADER_CONFIDENCE_TH", "0.72"))
      SCHEMA_SCORE_TH: float = float(os.getenv("SCHEMA_SCORE_TH", "0.80"))
      MIN_VALID_ROWS: float = float(os.getenv("MIN_VALID_ROWS", "0.70"))
      LLM_STRICT_OVERRIDE_DELTA: float = float(os.getenv("LLM_STRICT_OVERRIDE_DELTA", "0.10"))
  ```
- `.env.example`
  ```text
  NORMALIZATION_POLICY=SAFE
  HEADER_CONFIDENCE_TH=0.72
  SCHEMA_SCORE_TH=0.80
  MIN_VALID_ROWS=0.70
  LLM_STRICT_OVERRIDE_DELTA=0.10
  ```

### 2) Tipi con provenance/confidence (nuovi file)
- `ingest/types.py`
  - Definisci `Source`, `FieldVal`, helper `fv`, `WineRow` con campi strutturati + `raw_*`, `source_*`.
- `ingest/utils_confidence.py`
  - `can_override(old, new_conf, policy, delta)`
  - `pick_better(a, b)` con tie-break preferendo stage non LLM.

### 3) Header Mapping v2 (Hungarian 1-a-1)
- In `ingest/parser.py`:
  - Usa `numpy` + `scipy.optimize.linear_sum_assignment`.
  - Dizionario `SYNONYMS`.
  - Funzioni `col_score`, `map_headers_v2`.
  - `parse_dataframe` produce lista `WineRow` + mapping.

### 4) Normalization SAFE (non distruttiva)
- `ingest/normalization.py` aggiornata per usare `WineRow`, `FieldVal`, policy SAFE.
- Non modificare name/winery se conf alta; pulizia minima; numeri estratti con regex; inferenza tipologia leggera.

### 5) Resolver Supplier vs Producer
- Dataset seed `data/suppliers.yml`, `data/wineries.yml`, `data/dnt_labels.txt`, `data/dnt_wineries.txt`.
- Nuovo modulo `ingest/supplier_resolver.py` con `classify_party` + regole.
- Applicare dopo normalizzazione (`resolve_supplier_producer`).

### 6) Reconciliation stage-to-stage
- `ingest/reconcile.py` con `reconcile_rows` (usa `pick_better`).
- Utilizzare quando fondiamo Stage 0.5/1/2/3.

### 7) Dedup morbida
- Nuovo `ingest/dedup.py` con `_norm`, `same_wine`, `deduplicate` (usa fuzzy + reconcile).

### 8) LLM targeted solo header
- Prompt file `ingest/prompts/llm_targeted_header.md`.
- Stage 2 limita funzioni a disambiguazione header (no correzione celle).

### 9) Guardrail Stage 3
- In `ingest/pipeline.py`: salta Stage 3 se metriche Stage 1 soddisfano soglie config e nessun campo critico mancante.

### 10) DB & insert
- Migrazione: aggiungi `raw_name`, `raw_winery`, `raw_supplier`, `lineage` (jsonb), `source_file`, `source_row`.
- `core/database.batch_insert_wines` aggiorna payload per nuovi campi, evita forzare qty=0.

### 11) Logging diff-aware + diagnostica
- Nuovo `core/logger_diff.py` con `log_field_override`.
- Endpoint diagnostico `/diagnostics/summary` con aggregazione ultimi job.

### 12) Test & fixtures
- `tests/fixtures/{1_pulito.csv, 2_sinonimi.csv, 3_caotico.csv, 4_supplier_buggato.csv}`.
- `tests/test_processor_safe_mode.py`, `tests/test_dedup.py` come da specifica.

### 13) Bot summary (facoltativo)
- Messaggio riassuntivo al termine job con override percentuali, supplier fix, early-exit, costi stimati.

### 14) Integrazione orchestratore (pseudocodice)
- `rows_stage05` optional → `parse_dataframe` Stage 1 → `reconcile_lists` → `normalize_values` → `resolve_supplier_producer` → metriche → Stage 2 header LLM (se serve) → Stage 3 guardato → `deduplicate` → `batch_insert_wines` → `post_processing`.

### Nota costi/benefici attesa
- SAFE mode + Hungarian riducono sovrascritture.
- Resolver supplier/producer ripulisce dataset.
- Early-exit Stage 3 abbatte tempi e costi per file già buoni.


