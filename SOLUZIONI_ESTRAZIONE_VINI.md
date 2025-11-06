# Soluzioni per estrarre tutti i vini

## Problema attuale
- **Stage 1**: Trova 140 righe valide
- **Stage 3**: Estrae solo 87 vini
- **Mancano**: 53 vini (140 - 87 = 53)

## Analisi
Stage 3 rielabora il file originale da zero, ignorando i dati già parsati da Stage 1. Questo causa perdita di vini validi.

---

## Soluzioni proposte

### 🎯 **Soluzione 1: Unire Stage 1 + Stage 3 (IBRIDO)** ⭐ CONSIGLIATA
**Cosa fa:**
- Dopo che Stage 3 completa, unisce i vini trovati da Stage 1 con quelli di Stage 3
- Deduplica per (name, winery, vintage)
- Somma qty se duplicati

**Vantaggi:**
- ✅ Recupera tutti i vini di Stage 1 (140)
- ✅ Aggiunge quelli trovati solo da Stage 3
- ✅ Nessun costo aggiuntivo LLM
- ✅ Implementazione relativamente semplice

**Svantaggi:**
- ⚠️ Richiede deduplicazione intelligente
- ⚠️ Potrebbe sommare qty duplicati (ma è feature, non bug)

**Implementazione:**
- Modificare `pipeline.py` per salvare `stage1_wines` anche quando si passa a Stage 3
- Dopo Stage 3, unire `stage1_wines + stage3_wines`
- Deduplicare usando `deduplicate_wines()` già esistente

---

### ⚡ **Soluzione 3: Aumentare overlap e max_tokens (QUICK FIX)**
**Cosa fa:**
- Overlap chunk: `1000 bytes → 5000 bytes` (5x)
- Max tokens LLM: `6000 → 10000` (per chunk)

**Vantaggi:**
- ✅ Implementazione immediata (5 minuti)
- ✅ Riduce perdite ai bordi dei chunk
- ✅ Più capacità di estrazione per chunk

**Svantaggi:**
- ⚠️ Costo leggermente più alto per chiamata
- ⚠️ Potrebbe non risolvere completamente se il problema è altrove

**Implementazione:**
- `llm_extract.py`: `chunk_text(..., overlap=5000)`
- `llm_extract.py`: `max_tokens=10000` in `extract_with_llm()`

---

### 🔄 **Soluzione 4: Due passaggi LLM (conteggio + estrazione)**
**Cosa fa:**
- Prima chiamata: "Quanti vini ci sono in questo testo? Conta tutte le righe con dati vino."
- Seconda chiamata: "Estrai tutti i vini che hai contato."

**Vantaggi:**
- ✅ Spinge l'LLM a essere più completo
- ✅ Controllo esplicito sul numero atteso

**Svantaggi:**
- ❌ Doppio costo LLM (2x chiamate per chunk)
- ❌ L'LLM potrebbe comunque sbagliare il conteggio
- ⚠️ Implementazione più complessa

**Implementazione:**
- Aggiungere `extract_with_llm_count()` prima di `extract_with_llm()`
- Modificare prompt per includere conteggio atteso

---

### 🏗️ **Soluzione 5: Stage 3 arricchisce Stage 1 (REFACTORING)**
**Cosa fa:**
- Stage 3 riceve i vini di Stage 1 come input
- Stage 3 arricchisce/corregge i vini esistenti, non riparte da zero
- Stage 3 cerca solo righe mancanti nel file originale

**Vantaggi:**
- ✅ Recupera tutti i vini di Stage 1
- ✅ Stage 3 integra solo le righe mancanti
- ✅ Più efficiente (non riprocessa tutto)

**Svantaggi:**
- ❌ Richiede refactoring significativo
- ❌ Cambia architettura pipeline
- ⚠️ Implementazione complessa (1-2 ore)

**Implementazione:**
- Modificare `extract_llm_mode()` per accettare `stage1_wines` come parametro
- Prompt modificato: "Estrai tutti i vini da questo testo. Hai già questi vini: [...]. Estrai anche quelli mancanti."

---

## 🎯 Raccomandazione

**Combinare Soluzione 1 + Soluzione 3** per un intervento rapido ed efficace:

1. **Soluzione 3** (quick fix): Aumentare overlap e max_tokens
2. **Soluzione 1** (ibrido): Unire Stage 1 + Stage 3 dopo estrazione

**Risultato atteso:**
- Recupera tutti i vini di Stage 1 (140)
- Aggiunge quelli trovati da Stage 3 (87+)
- Totale: ~140+ vini invece di 87

**Tempo implementazione:** ~30 minuti
**Costo aggiuntivo:** Minimo (solo più token per chunk)

---

## Altre soluzioni considerate

### Soluzione 2: Passare dati Stage 1 a Stage 3 come riferimento
- Stage 3 riceve vini di Stage 1 nel prompt come esempio
- **Problema**: Aumenta significativamente i token, potrebbe non essere efficace

### Soluzione 6: Logging dettagliato
- Log per ogni riga scartata con motivo
- **Utile per debugging**, ma non risolve il problema direttamente
- **Consigliato come complemento** alle altre soluzioni



