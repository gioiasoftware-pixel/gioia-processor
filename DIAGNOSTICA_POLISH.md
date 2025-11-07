# 🛠️ Diagnostica Processor – “Polish & Hardening”

Obiettivo: individuare i punti in cui l’attuale pipeline tende a cancellare, trasformare o introdurre rumore nell’inventario e definire un piano di pulizia/stabilizzazione.

## 1. Panoramica pipeline attuale

| Stage | File chiave | Note diagnostiche |
|-------|-------------|-------------------|
| Stage 0 – Routing | `ingest/gate.py`, `ingest/pipeline.py` | Seleziona “csv_excel” o “ocr” e avvia Stage 0.5. |
| Stage 0.5 – Header Identifier | `ingest/header_identifier.py` | Identifica header via fuzzy matching, crea backup dei vini estratti. |
| Stage 1 – Parser classico | `ingest/parser.py` + `ingest/normalization.py` | Applica mapping sinonimi, normalizza e valida. |
| Stage 2 – IA mirata | `ingest/llm_targeted.py` | Raramente attivato (config); aggiunge logiche custom. |
| Stage 3 – LLM mode | `ingest/llm_extract.py` | Re-estrazione completa via LLM, merge con stage precedenti, dedup. |
| Stage 4 – OCR | `ingest/ocr_extract.py` | Per PDF/img, poi Stage 3. |
| Salvataggio | `core/database.batch_insert_wines` | Inserisce solo subset campi (`name`, `producer`, `quantity`, ecc.). |
| Post-processing | `post_processing.py` | Pulizia, dedup, LLM validation loop, learned terms. |

## 2. Criticità osservate

### 2.1 Stage 0.5 / Stage 1
- **Mapping aggressivo**: se `Etichetta` vuota, usa `Cantina` come `name` anche quando il campo contiene valori generici ("producer", "Winesider"). Risultato: molte righe “producer” / “–” nel DB.
- **Colonne ignorate**: Stage 1 scarta “Indice” dal mapping, ma il tipo non sempre viene salvato come `wine_type` → molti vini restano `Altro`.
- **Normalizzazione prezzi/quantità**: `normalize_price` gestisce virgole e simboli, ma non logga conversioni fallite. Quantità 0 se `Q cantina` non compatibile. Nessun campo `min_quantity` fino all’ultimo fix.
- **Righe di servizio**: CSV con header ripetuti produce righe rumorose (nome="Indice", "Bolle", ecc.) perché Stage 1 le tratta come record validi prima della filtrazione.

### 2.2 Stage 3 – LLM
- **Duplice estrazione**: Stage 3 reinterpreta l’intero testo e poi `deduplicate_wines` unisce con Stage 0.5/1. Se LLM altera nomi (es. tronca, normalizza) può creare nuove righe invece di aggiornare quelle esistenti.
- **Categorie → nomi**: prompt forza a usare il `winery` come nome se “Bolle” ecc., ma se `winery` è generico la riga rimane invalida. Serve scoring per scartare casi generici.
- **LLM fallback**: se Stage 3 fallisce, Stage 1 ritorna i risultati originali (meno campi) ma senza segnalarlo → l’utente non sa che l’estrazione è parziale.

### 2.3 Post-processing
- **LLM correction loop**: `post_processing.normalize_saved_inventory` invia batch all’LLM fino a 3 volte; se l’LLM suggerisce correzioni sbagliate, possono sovrascrivere valori buoni senza traccia.
- **Cancellazioni**: funzione `is_invalid_wine_name()` elimina vini con `name` corto/numero. Buono per “0” ma rischioso se la pipeline ha sbagliato preprocess (es. `Il Bruciato` → salvato come `0`, viene cancellato).
- **Batch corrections**: applicate dinamicamente con SQL generato dall’LLM (es. `extract_from_parentheses`). Se lo schema cambia o il pattern è troppo generico rischiamo update massivi errati.

### 2.4 Database/Salvataggio
- **Campi non mappati**: `batch_insert_wines` salva `region`, `country`, `supplier`, `classification`, ma molte pipeline non valorizzano questi campi → viewer mostra `-`. Serve chain completa dall’input.
- **Dedup**: Post-processing deduplica su `name`, `producer`, `vintage`, `quantity`, `price`, … se Stage 1 crea righe rumorose, possiamo perdere dati validi.

## 3. Aree da “polishare”

1. **Mapping deterministico header → schema DB**
   - Centralizzare la matrice mapping (già estesa) e applicarla all’inizio della pipeline in modo coerente.
   - In caso di ambiguità (es. `Index`, `ID`), preservare i dati in campi di supporto (`meta_index`) invece di trattarli come nomi.

2. **Filtri anti-rumore**
   - Prima del salvataggio scartare righe dove `name` ∈ {`producer`, `fornitore`, valori placeholder}. 
   - Applicare heuristics: se `name` = `winery` e `winery` ∈ lista fornitori → riga sospetta (flag/log, non cancellare silenziosamente).

3. **Gestione tipologie (“Indice”)**
   - Stage 0.5/1: se colonna “Indice” o “Tipologia” valorizzata, normalizzare in `wine_type` (`Bolle` → `Spumante`).
   - Stage 3: passare la stessa informazione nel prompt e nella normalizzazione.

4. **Prezzi e quantità**
   - Logging quando `normalize_price` o `normalize_qty` falliscono. 
   - Salvare anche `cost_price` (prezzo fornitore) e `selling_price` separati; se mancano, mantenere `None` invece di `0`.

5. **LLM Stage 3**
   - Limitare merge/dedup: usare ID temporanei per distinguere vini Stage1 vs LLM; se `name` cambia troppo, loggare anziché unire.
   - Introdurre “confidence score” sul risultato LLM; se troppo basso, preferire Stage1.

6. **Post-processing**
   - Modalità “audit”: loggare tutte le modifiche applicate dall’LLM (prima/dopo) e consentire rollback.
   - Limitare cancellazioni automatiche (es. `is_invalid_wine_name`) a casi certi.
   - Persistenza learned terms: oggi ogni correzione genera update dinamico; meglio usare mapping strutturato (term→correzione) e applicarlo in Stage 1.

7. **Osservabilità**
   - Aggiungere report post-job che mostra: numero righe Stage 0.5, Stage1, Stage3, scarti, correzioni LLM, cancellazioni post-processing.
   - Endpoint diagnostico per confrontare inventario DB vs CSV originale (come fatto manualmente ora).

## 4. Piano di lavoro suggerito

| Step | Azione | Priorità |
|------|--------|----------|
| 1 | Consolidare mapping header → campi DB e filtrare righe rumorose prima dell’inserimento | Alta |
| 2 | Aggiornare Stage 1/Stage 3 per valorizzare `wine_type`, `cost_price`, `supplier`, `region`, `country` coerentemente | Alta |
| 3 | Ridurre trasformazioni invasive in post-processing (audit/log, niente delete automatiche senza conferma) | Media |
| 4 | Migliorare logging & metriche (conteggi scarti, dedup, modifiche LLM) | Media |
| 5 | Versionare i dataset (originale vs salvato) per confronto futuro e QA | Media |
| 6 | Documentare pipeline “polishata” e predisporre test regressione con CSV reali (come l’inventario HEY) | Media |

---

Con questo studio possiamo procedere a semplificare e “irrobustire” il processor evitando che le varie fasi annullino o distorcano i dati originali. Fammi sapere da quale step vuoi partire e implemento. 


