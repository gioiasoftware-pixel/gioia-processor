# 🔍 Analisi: Produttori Non Estratti per Vini con "Bolle" nell'Indice

## Problema Segnalato

L'utente ha caricato un inventario con 130 vini estratti, ma **i produttori delle prime etichette con "Bolle" nell'Indice non vengono estratti**.

## Analisi CSV

Guardando il file CSV fornito:

**Header**:
```
Indice,ID,Etichetta,Cantina,Uvaggio,Tipologia,Nazionalità,Regione,Comune,Fornitore,Q iniziale,Q cantina,prezzo fornitore,prezzo in carta,ANNATA
```

**Riga 2 (esempio)**:
```
Bolle,BOTCDPNCC2,Tradition,Cottet Debreuil,Pinot Nero Chardonnay,Champagne ,Francia,,,Ceretto,4,4,"30,90€",70€,
```

**Dati attesi**:
- **Nome vino**: "Tradition" (da colonna "Etichetta")
- **Produttore**: "Cottet Debreuil" (da colonna "Cantina")
- **Tipo vino**: "Spumante" (inferito da "Bolle" nella colonna "Indice")

## Possibili Cause

### 1. **Mapping Header Non Corretto**

**Verifica**:
- ✅ "Etichetta" è in `COLUMN_MAPPINGS_EXTENDED['name']` → Dovrebbe mappare a `name`
- ✅ "Cantina" è in `COLUMN_MAPPINGS_EXTENDED['winery']` → Dovrebbe mappare a `winery`
- ⚠️ "Indice" è ignorato dal mapping (corretto), ma i suoi valori sono ancora nel dataframe

**Problema Potenziale**: Se "Indice" viene mappato a "name" invece di "Etichetta", il sistema prenderà "Bolle" come nome invece di "Tradition".

### 2. **Normalizzazione Nome Vino**

Quando `normalize_values` viene chiamato:
1. Prende il valore dalla colonna mappata a `name` (dovrebbe essere "Tradition")
2. Se il valore è "Bolle" (sbagliato), chiama `extract_wine_name_from_category_pattern("Bolle", winery="Cottet Debreuil")`
3. Rileva che "Bolle" è solo una categoria
4. Usa `winery` come nome → "Cottet Debreuil" (sbagliato, dovrebbe essere "Tradition")

**Problema**: Il sistema sta usando "Bolle" come nome invece di "Tradition".

### 3. **Stage 0.5 vs Stage 1**

**Stage 0.5** (`header_identifier.py`):
- Identifica header riga per riga
- Estrae vini usando `header_mapping`
- Dovrebbe mappare correttamente "Etichetta" → `name` e "Cantina" → `winery`

**Stage 1** (`parser.py`):
- Usa pandas per leggere CSV
- Mappa header usando `map_headers`
- Dovrebbe mappare correttamente "Etichetta" → `name` e "Cantina" → `winery`

**Problema Potenziale**: Se Stage 0.5 fallisce o non estrae correttamente, Stage 1 potrebbe avere lo stesso problema.

## Soluzione Proposta

### 1. **Verificare Mapping Header**

Aggiungere logging dettagliato per vedere:
- Quali colonne vengono mappate
- Quali valori vengono estratti per `name` e `winery`
- Se "Indice" viene erroneamente mappato a `name`

### 2. **Correggere Estrazione Nome**

Se il nome estratto è "Bolle" (o altra categoria), ma c'è un valore valido nella colonna "Etichetta", usare quello invece di `winery`.

**Logica proposta**:
```python
# In normalize_values, dopo extract_wine_name_from_category_pattern
if extracted_name in problematic_terms and row.get('etichetta'):
    # Se il nome estratto è una categoria, ma c'è un valore in "Etichetta", usalo
    etichetta_value = normalize_string_field(row.get('etichetta'))
    if etichetta_value and etichetta_value not in problematic_terms:
        extracted_name = etichetta_value
        logger.debug(f"Usato valore da 'Etichetta' invece di categoria: '{etichetta_value}'")
```

### 3. **Verificare Stage 0.5**

Aggiungere logging per vedere:
- Se Stage 0.5 mappa correttamente "Etichetta" e "Cantina"
- Quali valori vengono estratti per le prime righe con "Bolle"

### 4. **Verificare Stage 1**

Aggiungere logging per vedere:
- Se Stage 1 mappa correttamente "Etichetta" e "Cantina"
- Quali valori vengono estratti per le prime righe con "Bolle"

## Test da Eseguire

1. **Test Mapping Header**:
   - Verificare che "Etichetta" mappa a `name`
   - Verificare che "Cantina" mappa a `winery`
   - Verificare che "Indice" NON mappa a `name`

2. **Test Estrazione Nome**:
   - Per riga con "Bolle" nell'Indice e "Tradition" nell'Etichetta:
     - Verificare che `name` = "Tradition" (non "Bolle" o "Cottet Debreuil")
     - Verificare che `winery` = "Cottet Debreuil"
     - Verificare che `type` = "Spumante" (inferito da "Bolle")

3. **Test Logging**:
   - Aggiungere log dettagliati per vedere esattamente cosa viene estratto

## Prossimi Passi

1. Aggiungere logging dettagliato in `normalize_values` per vedere cosa viene estratto
2. Verificare che "Etichetta" e "Cantina" vengano mappati correttamente
3. Correggere la logica di estrazione nome se necessario

