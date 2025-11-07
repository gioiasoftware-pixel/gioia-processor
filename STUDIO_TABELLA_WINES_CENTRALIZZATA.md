# 📊 Studio: Tabella `wines` Centralizzata

## 🎯 Idea Proposta

Dopo il post-processing, salvare tutti i vini di tutti gli utenti nella tabella `wines` centralizzata (senza duplicati). Questo permetterebbe al processor di:
- **Arricchire dati mancanti**: Se un utente non ha certe informazioni su un vino (es. `alcohol_content`, `description`, `grape_variety`), ma altri utenti le hanno, il processor può completare automaticamente i dati.

## ✅ Vantaggi

### 1. **Arricchimento Automatico Dati**
- **Scenario**: Utente A ha "Chianti Classico" con solo `name` e `producer`
- **Utente B** ha lo stesso vino con `alcohol_content=14%`, `grape_variety=Sangiovese`, `description=...`
- **Risultato**: Il processor può automaticamente completare i dati mancanti di Utente A usando quelli di Utente B

### 2. **Database Conoscenza Condivisa**
- Creazione di un database centralizzato di vini con dati completi
- Migliora la qualità dei dati per tutti gli utenti
- Riduce la necessità di input manuale

### 3. **Miglioramento Qualità Dati**
- Se 10 utenti hanno lo stesso vino, i dati più completi vengono aggregati
- Validazione cross-utente: se 9 utenti hanno `alcohol_content=14%` e 1 ha `15%`, si può inferire che `14%` è più probabile

### 4. **Riduzione Costi LLM**
- Meno bisogno di chiamare LLM per inferire dati mancanti se già presenti nel database centralizzato
- Query dirette al database invece di chiamate AI

## ⚠️ Sfide e Considerazioni

### 1. **Identificazione Vino Unico (Deduplicazione)**

**Problema**: Come identificare che due vini di utenti diversi sono lo stesso vino?

**Chiave Attuale per Deduplicazione** (da `deduplicate_wines`):
```python
key = (name, winery, vintage)
```

**Problemi**:
- **Varianti nome**: "Chianti Classico" vs "Chianti Classico DOCG" vs "Chianti Classico Riserva"
- **Varianti producer**: "Antinori" vs "Marchesi Antinori" vs "Tenuta Antinori"
- **Vintage mancante**: Molti vini non hanno vintage, quindi `(name, winery, None)` potrebbe matchare vini diversi
- **Case sensitivity**: "Chianti" vs "chianti" (risolto con lowercase)
- **Accenti**: "Côte" vs "Cote" (da gestire)

**Soluzione Proposta**:
- Usare fuzzy matching per identificare vini simili
- Chiave più robusta: `(normalize_name(name), normalize_producer(producer), vintage, region, country)`
- Usare `rapidfuzz` per match fuzzy quando chiave esatta non matcha

### 2. **Schema Tabella `wines`**

**Schema Attuale** (da `database_async.py`):
```sql
CREATE TABLE wines (
    id SERIAL PRIMARY KEY,
    user_id INTEGER,  -- ⚠️ PROBLEMA: Non ha senso per tabella centralizzata
    name VARCHAR(200) NOT NULL,
    producer VARCHAR(200),
    vintage INTEGER,
    grape_variety VARCHAR(200),
    region VARCHAR(200),
    country VARCHAR(100),
    wine_type VARCHAR(50),
    classification VARCHAR(100),
    quantity INTEGER DEFAULT 0,  -- ⚠️ PROBLEMA: Quantità non ha senso centralizzata
    min_quantity INTEGER DEFAULT 0,  -- ⚠️ PROBLEMA: Min quantity non ha senso centralizzata
    cost_price FLOAT,  -- ⚠️ PROBLEMA: Prezzo varia per utente
    selling_price FLOAT,  -- ⚠️ PROBLEMA: Prezzo varia per utente
    alcohol_content FLOAT,
    description TEXT,
    notes TEXT,  -- ⚠️ PROBLEMA: Note sono specifiche per utente
    created_at TIMESTAMP,
    updated_at TIMESTAMP
)
```

**Schema Proposto** (senza campi user-specific):
```sql
CREATE TABLE wines (
    id SERIAL PRIMARY KEY,
    -- Identificazione vino
    name VARCHAR(200) NOT NULL,
    producer VARCHAR(200),
    vintage INTEGER,
    -- Dati tecnici (invarianti tra utenti)
    grape_variety VARCHAR(200),
    region VARCHAR(200),
    country VARCHAR(100),
    wine_type VARCHAR(50),
    classification VARCHAR(100),
    alcohol_content FLOAT,
    description TEXT,
    -- Metadati
    data_quality_score FLOAT,  -- Qualità dati (0-1): più utenti = più alta
    source_count INTEGER DEFAULT 1,  -- Quanti utenti hanno questo vino
    last_seen_at TIMESTAMP,
    created_at TIMESTAMP,
    updated_at TIMESTAMP,
    -- Indici per ricerca
    UNIQUE(name, producer, vintage)  -- Prevenire duplicati esatti
)
```

**Campi da ESCLUDERE** (user-specific):
- `user_id` - Non ha senso in tabella centralizzata
- `quantity` - Varia per utente
- `min_quantity` - Varia per utente
- `cost_price` - Varia per utente/fornitore
- `selling_price` - Varia per utente/prezzo
- `notes` - Note specifiche per utente

### 3. **Logica di Aggregazione Dati**

**Quando salvare in `wines`**:
- Dopo post-processing completato
- Solo vini con dati validi e normalizzati

**Come aggregare dati da più utenti**:
```python
# Pseudo-codice
def merge_wine_data(existing_wine, new_wine):
    """
    Merge dati vino: preferisci valori non-null, aggiorna se più completo
    """
    merged = existing_wine.copy()
    
    # Per ogni campo, preferisci valore non-null più completo
    for field in ['grape_variety', 'region', 'country', 'wine_type', 
                  'classification', 'alcohol_content', 'description']:
        existing_value = existing_wine.get(field)
        new_value = new_wine.get(field)
        
        # Preferisci valore più completo (più lungo o più specifico)
        if not existing_value and new_value:
            merged[field] = new_value
        elif existing_value and new_value:
            # Preferisci quello più lungo (più dettagliato)
            if len(str(new_value)) > len(str(existing_value)):
                merged[field] = new_value
            # Altrimenti mantieni esistente
    
    # Aggiorna metadati
    merged['source_count'] += 1
    merged['last_seen_at'] = datetime.utcnow()
    merged['data_quality_score'] = calculate_quality_score(merged)
    
    return merged
```

### 4. **Identificazione Vino (Fuzzy Matching)**

**Problema**: Come matchare "Chianti Classico" con "Chianti Classico DOCG"?

**Soluzione**:
```python
def find_matching_wine(name, producer, vintage, session):
    """
    Trova vino esistente in wines usando fuzzy matching
    """
    # 1. Prova match esatto (name, producer, vintage)
    exact_match = session.execute(
        select(Wine).where(
            func.lower(Wine.name) == name.lower(),
            func.lower(Wine.producer) == producer.lower(),
            Wine.vintage == vintage
        )
    ).scalar_one_or_none()
    
    if exact_match:
        return exact_match
    
    # 2. Prova match fuzzy (name + producer, vintage opzionale)
    all_wines = session.execute(select(Wine)).scalars().all()
    
    best_match = None
    best_score = 0
    threshold = 85  # 85% similarity
    
    for wine in all_wines:
        # Match name
        name_score = fuzz.WRatio(name.lower(), wine.name.lower())
        producer_score = fuzz.WRatio(producer.lower(), wine.producer.lower()) if producer and wine.producer else 0
        
        # Score combinato (name pesa di più)
        combined_score = (name_score * 0.7) + (producer_score * 0.3)
        
        # Bonus se vintage matcha
        if vintage and wine.vintage and vintage == wine.vintage:
            combined_score += 10
        
        if combined_score > best_score and combined_score >= threshold:
            best_score = combined_score
            best_match = wine
    
    return best_match
```

### 5. **Arricchimento Dati Utente**

**Quando arricchire**:
- Durante post-processing
- Quando si salva un nuovo inventario
- Quando un utente chiede informazioni su un vino

**Come arricchire**:
```python
def enrich_user_wine(user_wine, session):
    """
    Arricchisce vino utente con dati da wines centralizzata
    """
    # Trova match in wines
    central_wine = find_matching_wine(
        user_wine.name, 
        user_wine.producer, 
        user_wine.vintage,
        session
    )
    
    if not central_wine:
        return user_wine  # Nessun match, ritorna originale
    
    # Completa campi mancanti
    enriched = user_wine.copy()
    
    for field in ['grape_variety', 'region', 'country', 'wine_type',
                  'classification', 'alcohol_content', 'description']:
        if not enriched.get(field) and central_wine.get(field):
            enriched[field] = central_wine[field]
            logger.info(f"Arricchito campo {field} per vino {user_wine.name}")
    
    return enriched
```

### 6. **Privacy e Dati Sensibili**

**Considerazioni**:
- ✅ **Dati tecnici** (alcohol_content, grape_variety, region) sono pubblici → OK
- ✅ **Dati commerciali** (cost_price, selling_price, quantity) sono privati → NON salvati in `wines`
- ⚠️ **Producer/Name**: Potrebbero essere considerati dati commerciali? → Probabilmente OK (sono pubblici)
- ⚠️ **Description**: Potrebbe contenere note commerciali? → Da validare

**Soluzione**: 
- Salvare solo dati **non sensibili** e **invarianti** tra utenti
- Escludere: prezzi, quantità, note personali

### 7. **Performance**

**Considerazioni**:
- **Indici necessari**: `(name, producer, vintage)`, `(name)`, `(producer)`
- **Fuzzy matching**: Potrebbe essere lento con migliaia di vini → Usare cache o limitare ricerca
- **Batch insert**: Inserire/aggiornare in batch dopo post-processing

**Ottimizzazioni**:
- Cache in-memory per vini più comuni
- Indici compositi per ricerca veloce
- Fuzzy matching solo se match esatto fallisce

### 8. **Gestione Conflitti**

**Scenario**: 
- Utente A: `alcohol_content=14%`
- Utente B: `alcohol_content=15%`
- Utente C: `alcohol_content=14%`

**Strategia**:
1. **Voto a maggioranza**: Se 2+ utenti hanno stesso valore, usalo
2. **Data quality score**: Preferisci valore da utente con dati più completi
3. **Timestamp**: Preferisci valore più recente (se stesso quality score)
4. **Validazione range**: Se `alcohol_content` è fuori range (0-100), scarta

### 9. **Flusso Proposto**

```
1. Utente carica inventario
   ↓
2. Processor estrae e salva vini in tabella dinamica utente
   ↓
3. Post-processing normalizza e pulisce dati
   ↓
4. Per ogni vino normalizzato:
   a. Cerca match in wines (fuzzy matching)
   b. Se match trovato:
      - Merge dati (preferisci valori più completi)
      - Aggiorna source_count
      - Aggiorna data_quality_score
   c. Se no match:
      - Inserisci nuovo vino in wines
   ↓
5. Arricchimento dati utente:
   - Per ogni vino utente con dati mancanti:
     a. Cerca match in wines
     b. Completa campi mancanti
     c. Aggiorna tabella dinamica utente
```

## 📋 Checklist Implementazione

### Fase 1: Schema e Infrastruttura
- [ ] Creare/modificare schema tabella `wines` (senza campi user-specific)
- [ ] Creare indici per performance (`name`, `producer`, `vintage`, compositi)
- [ ] Implementare funzione `find_matching_wine()` con fuzzy matching
- [ ] Implementare funzione `merge_wine_data()` per aggregazione

### Fase 2: Salvataggio Post-Processing
- [ ] Modificare `post_processing.py` per salvare in `wines` dopo normalizzazione
- [ ] Implementare logica deduplicazione (fuzzy matching)
- [ ] Implementare logica merge dati (preferisci valori più completi)
- [ ] Aggiornare `data_quality_score` e `source_count`

### Fase 3: Arricchimento Dati
- [ ] Implementare funzione `enrich_user_wine()` 
- [ ] Integrare arricchimento in post-processing
- [ ] Aggiornare tabella dinamica utente con dati arricchiti

### Fase 4: Testing e Validazione
- [ ] Test con vini duplicati tra utenti diversi
- [ ] Test fuzzy matching con varianti nome/producer
- [ ] Test arricchimento dati mancanti
- [ ] Test performance con migliaia di vini

## 🎯 Vantaggi Finali

1. **Qualità Dati Migliorata**: Dati più completi per tutti gli utenti
2. **Riduzione Costi**: Meno chiamate LLM per inferire dati mancanti
3. **Esperienza Utente**: Inventari più completi automaticamente
4. **Scalabilità**: Database conoscenza condivisa cresce con il tempo

## ⚠️ Rischi e Mitigazioni

| Rischio | Mitigazione |
|---------|-------------|
| **Fuzzy matching errato** | Soglia alta (85%+), validazione manuale per match borderline |
| **Dati errati propagati** | Data quality score, validazione range, voto a maggioranza |
| **Performance lenta** | Indici, cache, batch processing |
| **Privacy concerns** | Solo dati non sensibili, escludere prezzi/quantità/note |

## 💡 Raccomandazioni

1. **Implementazione Graduale**:
   - Fase 1: Solo salvataggio (no arricchimento)
   - Fase 2: Arricchimento opzionale (flag configurabile)
   - Fase 3: Arricchimento automatico

2. **Monitoring**:
   - Tracciare quante volte viene fatto match
   - Tracciare quante volte dati vengono arricchiti
   - Tracciare data_quality_score medio

3. **Fallback**:
   - Se fuzzy matching fallisce o è incerto, non arricchire
   - Mantenere dati originali utente come fallback

4. **Configurazione**:
   - Flag per abilitare/disabilitare arricchimento
   - Soglia fuzzy matching configurabile
   - Minimo `source_count` per considerare dati affidabili

