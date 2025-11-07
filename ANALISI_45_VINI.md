# Analisi: Perché vengono salvati solo 45 vini su 200+

## Dati del problema

### File CSV analizzato
- **File**: `inventario vini HEY (splendide) - Inventario.csv`
- **Righe totali**: 262 righe
- **Vini estratti**: 45 vini
- **Vini attesi**: ~200+ vini validi

### Struttura del file
1. **Riga 1**: Header principale `Indice,ID,Etichetta,Cantina,Uvaggio,Tipologia,Nazionalità,Regione,Comune,Fornitore,Q iniziale,Q cantina,prezzo fornitore,prezzo in carta,ANNATA`
2. **Righe 2-60**: Vini "Bolle" (spumanti) - ~59 vini
3. **Riga 60**: Header ripetuto
4. **Righe 61-133**: Vini "Bianchi" - ~73 vini
5. **Riga 133**: Header ripetuto
6. **Righe 135-217**: Vini "Rossi" - ~83 vini
7. **Riga 218**: Header ripetuto
8. **Righe 219-241**: Vini "Rosè" - ~23 vini
9. **Riga 241**: Header ripetuto
10. **Righe 242-262**: Vini "Passiti" - ~21 vini

**Totale stimato vini validi**: ~259 vini (escludendo righe vuote e header)

## Analisi dei log

### Stage 0.5: NON ESECUTA
**Problema critico**: Non vedo log di `[PIPELINE] Stage 0.5: Starting header identification` nei log forniti.

**Possibili cause**:
1. Stage 0.5 fallisce silenziosamente (eccezione catturata ma non loggata)
2. Stage 0.5 non trova header (ma dovrebbe loggare)
3. Stage 0.5 viene saltato per qualche motivo

**Impatto**: Senza Stage 0.5, il sistema non identifica correttamente gli header multipli e non estrae vini da tutte le sezioni.

### Stage 1: FALLISCE COMPLETAMENTE
```
[VALIDATION] Batch validation: 0/41 validi, 41 rifiutati
[VALIDATION] Motivi rifiuto: {'ValidationError': 41}
```

**Problema**: Tutti i 41 vini estratti hanno `name` vuoto → vengono rifiutati.

**Causa**: La colonna "Etichetta" non viene mappata correttamente a "name". Guardando il CSV:
- Colonna 3: "Etichetta" (nome vino)
- Colonna 4: "Cantina" (produttore)

**Perché fallisce**:
- `map_headers` probabilmente non matcha "Etichetta" con "name" (confidence troppo bassa?)
- O "Etichetta" viene mappata a un altro campo

### Stage 2: NON ESTRAGGE VINI
```
[LLM_TARGETED] Stage 2 INSUFFICIENT: schema_score=1.00 < 0.7 or valid_rows=0.00 < 0.6 → Stage 3
```

**Problema**: Stage 2 riceve 0 vini da Stage 1, quindi non può fare nulla.

### Stage 3 (LLM): ESTRAGGE SOLO 45 VINI
```
[LLM_EXTRACT] CSV preparato: 262 righe originali → 210 righe (header rimossi: 49)
[LLM_EXTRACT] Chunk 1/1: 45 vini estratti
[LLM_EXTRACT] Totale vini estratti da tutti i chunk: 45
```

**Problemi identificati**:

1. **File viene troncato a 80 KB**:
   - `prepare_text_input` limita a `max_bytes = 80 * 1024` (80 KB)
   - Il file potrebbe essere più grande e viene troncato
   - Solo le prime righe vengono processate

2. **Solo 1 chunk**:
   - `chunk_text` crea 1 chunk (file < 40 KB dopo pulizia?)
   - Ma il file originale ha 262 righe, quindi dovrebbe essere più grande
   - Probabilmente il file viene troncato PRIMA del chunking

3. **LLM estrae solo 45 vini**:
   - L'LLM processa solo una parte del file (prime righe)
   - Non processa le sezioni "Bianchi", "Rossi", "Rosè", "Passiti"

## Problemi identificati

### 1. Stage 0.5 non viene eseguito
**Causa**: Probabilmente fallisce silenziosamente o non trova header.

**Verifica necessaria**:
- Controllare se Stage 0.5 viene chiamato
- Verificare se trova gli header (dovrebbe trovare almeno 4 header: righe 1, 60, 133, 218, 241)
- Verificare se estrae vini da tutte le sezioni

### 2. Stage 1 non mappa "Etichetta" → "name"
**Causa**: `map_headers` non matcha "Etichetta" con "name" (confidence threshold troppo alto?).

**Verifica necessaria**:
- Controllare se "Etichetta" è in `COLUMN_MAPPINGS_EXTENDED['name']`
- Verificare confidence threshold (default 0.75, potrebbe essere troppo alto)
- Verificare se "Etichetta" viene mappata a un altro campo

### 3. Stage 3 tronca il file a 80 KB
**Causa**: `prepare_text_input` limita a 80 KB, troncando il file.

**Impatto**: Solo le prime righe vengono processate, perdendo tutte le sezioni successive.

**Soluzione necessaria**:
- Aumentare `max_bytes` o rimuovere il limite
- Oppure processare il file in chunk PRIMA della preparazione testo

### 4. LLM estrae solo vini dalla prima sezione
**Causa**: Il file viene troncato, quindi l'LLM vede solo le prime righe (vini "Bolle").

**Impatto**: Perde tutte le altre sezioni (Bianchi, Rossi, Rosè, Passiti).

## Raccomandazioni

### Priorità 1: Fix Stage 0.5
1. Aggiungere logging dettagliato in Stage 0.5 per capire perché non viene eseguito
2. Verificare che identifichi tutti gli header multipli
3. Verificare che estragga vini da tutte le sezioni

### Priorità 2: Fix mapping "Etichetta"
1. Verificare che "Etichetta" sia in `COLUMN_MAPPINGS_EXTENDED['name']`
2. Se non c'è, aggiungerla
3. Ridurre confidence threshold se necessario

### Priorità 3: Fix limite 80 KB in Stage 3
1. Aumentare `max_bytes` in `prepare_text_input` (es. 200 KB o 500 KB)
2. Oppure rimuovere il limite e processare tutto il file
3. Verificare che il chunking funzioni correttamente per file grandi

### Priorità 4: Migliorare logging
1. Aggiungere log dettagliati per ogni stage
2. Loggare quante righe vengono processate in ogni stage
3. Loggare perché vini vengono scartati

## Conclusione

Il problema principale è che:
1. **Stage 0.5 non viene eseguito** → non identifica header multipli
2. **Stage 1 fallisce** → non mappa "Etichetta" correttamente
3. **Stage 3 tronca il file** → processa solo prime righe (45 vini)

**Soluzione**: Fixare Stage 0.5 per identificare tutti gli header e estrarre vini da tutte le sezioni, oppure fixare Stage 3 per processare tutto il file senza troncarlo.

