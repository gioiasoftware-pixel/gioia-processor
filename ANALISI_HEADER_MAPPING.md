# Analisi Mapping Header Inventario

## Header Forniti dall'Utente

```
Indice | ID | Etichetta | Cantina | Uvaggio | Tipologia | Nazionalità | Regione | Comune | Fornitore | Q iniziale | Q cantina | prezzo fornitore | prezzo in carta | ANNATA
```

## Mapping Attuale

### ✅ Header Mappati Correttamente

| Header Utente | Campo Standard | Sinonimi Presenti | Status |
|---------------|----------------|-------------------|--------|
| **Etichetta** | `name` | ✅ 'etichetta' presente | ✅ **MAPPATO** |
| **Cantina** | `winery` | ✅ 'cantina' presente | ✅ **MAPPATO** |
| **Uvaggio** | `grape_variety` | ✅ 'uvaggio' presente | ✅ **MAPPATO** |
| **Tipologia** | `type` | ✅ 'tipologia' presente | ✅ **MAPPATO** |
| **Regione** | `region` | ✅ 'regione' presente | ✅ **MAPPATO** |
| **Fornitore** | `supplier` | ✅ 'fornitore' presente | ✅ **MAPPATO** |
| **Q iniziale** | `qty` | ✅ 'q iniziale' presente | ✅ **MAPPATO** |
| **Q cantina** | `qty` | ✅ 'q cantina' presente | ⚠️ **CONFLITTO** (entrambi mappano a qty) |
| **prezzo fornitore** | `cost_price` | ✅ 'prezzo fornitore' presente | ✅ **MAPPATO** |
| **prezzo in carta** | `price` | ✅ 'prezzo in carta' presente | ✅ **MAPPATO** |
| **ANNATA** | `vintage` | ✅ 'annata' presente | ✅ **MAPPATO** |

### ⚠️ Header Non Mappati o Problematici

| Header Utente | Problema | Soluzione |
|---------------|----------|-----------|
| **Indice** | Non mappato (probabilmente ignorato) | ✅ OK - colonna di servizio |
| **ID** | Non mappato (probabilmente ignorato) | ✅ OK - colonna di servizio (ora filtrato se usato come producer) |
| **Nazionalità** | ✅ **AGGIUNTO** ai sinonimi di `country` | ✅ **RISOLTO** |
| **Comune** | ✅ **AGGIUNTO** ai sinonimi di `region` | ✅ **RISOLTO** |

### ✅ Conflitto "Q iniziale" vs "Q cantina" - RISOLTO

**Problema**: Entrambi gli header mappano a `qty`. Il sistema ora gestisce la priorità:
- ✅ **"Q cantina" ha priorità** su "Q iniziale" per quantità attuale
- ✅ Se entrambi sono presenti, viene usato "Q cantina"
- ✅ Log dettagliato quando viene sostituito il mapping

**Implementazione**: Aggiunta logica di priorità in `map_headers()` che preferisce colonne con:
- "q cantina"
- "q. cantina"
- "quantità cantina"
- "q disponibile"
- "q stock"

## Stato Finale

### ✅ Tutti gli Header Mappati Correttamente

| Header Utente | Campo Standard | Status |
|---------------|----------------|--------|
| **Etichetta** | `name` | ✅ MAPPATO |
| **Cantina** | `winery` | ✅ MAPPATO |
| **Uvaggio** | `grape_variety` | ✅ MAPPATO |
| **Tipologia** | `type` | ✅ MAPPATO |
| **Nazionalità** | `country` | ✅ MAPPATO (aggiunto) |
| **Regione** | `region` | ✅ MAPPATO |
| **Comune** | `region` | ✅ MAPPATO (aggiunto) |
| **Fornitore** | `supplier` | ✅ MAPPATO |
| **Q iniziale** | `qty` | ⚠️ Usato solo se "Q cantina" non presente |
| **Q cantina** | `qty` | ✅ MAPPATO (priorità) |
| **prezzo fornitore** | `cost_price` | ✅ MAPPATO |
| **prezzo in carta** | `price` | ✅ MAPPATO |
| **ANNATA** | `vintage` | ✅ MAPPATO |

## Modifiche Implementate

1. ✅ **Aggiunto "nazionalità" e "nazionalita" ai sinonimi di `country`**
2. ✅ **Aggiunto "comune", "municipio", "località" ai sinonimi di `region`**
3. ✅ **Implementata logica di priorità per "Q cantina" su "Q iniziale"**

