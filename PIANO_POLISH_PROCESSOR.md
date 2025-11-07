# 🧼 Piano di Polish Processor

Obiettivo: ridurre le distorsioni dell’inventario e rendere deterministico il processo di ingestione.

## 📋 Checklist Operativa

### 1. Mapping header deterministico
- [ ] Consolidare matrice header→campi DB (Etichetta→name, Cantina→winery, Uvaggio→grape_variety, Tipologia/Indice→wine_type, Nazionalità→country, Regione/Comune→region, Fornitore→supplier, Q iniziale/Q cantina→qty/min_quantity, Prezzo fornitore→cost_price, Prezzo in carta→selling_price, Annata→vintage, ecc.).
- [ ] Applicare mapping sia in Stage 0.5 (`header_identifier`) sia in Stage 1 (`normalize_values`) per evitare interpretazioni incoerenti.
- [ ] Conservare valori “Indice”/“ID” in campi ausiliari invece di usarli come nomi.

### 2. Filtri anti-rumore prima dell’inserimento
- [ ] Scartare righe con `name` in blacklist (`producer`, `fornitore`, `--`, valori vuoti) o `winery` generico.
- [ ] Se `name` = `winery` e `winery` appartiene alla lista fornitori, loggare e filtrare.
- [ ] Ignorare righe note come header ripetuti (`Indice`, `Tipologia`, `Nome`, ecc.).

### 3. Tipologie (Index/Tipologia) coerenti
- [ ] Stage 0.5/1: dedurre `wine_type` da valori “Indice”/“Tipologia” → mappe (Bolle→Spumante, Bianchi→Bianco, ecc.).
- [ ] Stage 3 (LLM): passare la tipologia dedotta nel prompt e nella normalizzazione per evitare `Altro`.

### 4. Prezzi, quantità, scorta minima
- [ ] Normalizzare `selling_price` e `cost_price` (convertire virgola in punto, rimuovere simboli). Loggare conversioni fallite.
- [ ] Usare `Q cantina` come quantità principale, ma se manca usare `Q iniziale`.
- [ ] Salvare `min_quantity` quando disponibile per uso nel viewer e alert scorte.

### 5. Stage 3 LLM controllato
- [ ] Limitare merge/dedup: tracciare la provenienza (Stage1 vs LLM) e, se i nomi cambiano troppo, mantenere entrambe le versioni in audit anziché sovrascrivere.
- [ ] Introdurre scoring/confidenza; se basso, preferire Stage 1 e segnalare l’inventario come parziale.
- [ ] Loggare quando Stage 3 produce risultati assenti (0 righe) per gestire fallback.

### 6. Post-processing “safe mode”
- [ ] Audit log per ogni correzione/cancellazione (prima/dopo) con possibilità di rollback.
- [ ] Limitare eliminazioni automatiche (`is_invalid_wine_name`) a casi sicuri.
- [ ] Applicare correzioni massive (learned terms) tramite mapping strutturato anziché SQL dinamico.

### 7. Osservabilità e QA
- [ ] Report post-job (Stage 0.5 estratti, Stage1 estratti, Stage3 estratti, righe scartate, correzioni LLM, cancellazioni post-processing).
- [ ] Endpoint diagnostico confronto inventario DB vs file originale.
- [ ] Suite test regressione con CSV reali (es. inventario HEY) per garantire che i dati coincidano dopo il polish.

---

## 🚀 Fase 1 – Implementazione immediata
1. **Mapping + filtri anti-rumore** (Stage 0.5 & Stage 1).
2. **Tipologia da “Indice”** (Stage 0.5/1 + Stage 3).
3. **Prezzi, quantità, min_quantity** (normalizzazione + salvataggio).

## 🔁 Fase 2 – Controllo LLM e post-processing
4. Hardening Stage 3 (scoring, merge safe).
5. Post-processing audit e riduzione cancellazioni.

## 📊 Fase 3 – QA e osservabilità
6. Report post-job, endpoint diagnostico, test regressione.

Con questo piano possiamo procedere a pulire l’inventario in modo sistematico, passo dopo passo. Fammi sapere da quale step partire (Fase 1 suggerita) e implemento. 

