# 🔍 Audit Duplicazioni - Gioia Processor

**Data**: 04/11/2025  
**Obiettivo**: Identificare codice duplicato e proporre quale mantenere

---

## 🔴 Duplicazioni Identificate

### 1. `classify_wine_type()` - **DUPLICATO**

**Ubicazioni**:
- `csv_processor.py:649-664`
- `ocr_processor.py:220-235`

**Confronto**:

#### Versione `csv_processor.py`:
```python
def classify_wine_type(text: str) -> str:
    text_lower = text.lower()
    
    if any(word in text_lower for word in ['rosso', 'red', 'nero', 'black', 'sangiovese', 'barbera', 'nebbiolo', 'cabernet', 'merlot', 'pinot noir', 'syrah', 'shiraz']):
        return 'rosso'
    elif any(word in text_lower for word in ['bianco', 'white', 'chardonnay', 'pinot grigio', 'sauvignon', 'riesling', 'gewürztraminer', 'moscato']):
        return 'bianco'
    elif any(word in text_lower for word in ['rosato', 'rosé', 'rose', 'pink']):
        return 'rosato'
    elif any(word in text_lower for word in ['spumante', 'champagne', 'prosecco', 'moscato', 'frizzante', 'sparkling', 'cava', 'crémant']):
        return 'spumante'
    else:
        return 'sconosciuto'
```

#### Versione `ocr_processor.py`:
```python
def classify_wine_type(text: str) -> str:
    text_lower = text.lower()
    
    if any(word in text_lower for word in ['rosso', 'red', 'nero', 'black', 'sangiovese', 'barbera', 'nebbiolo']):
        return 'rosso'
    elif any(word in text_lower for word in ['bianco', 'white', 'chardonnay', 'pinot grigio', 'sauvignon']):
        return 'bianco'
    elif any(word in text_lower for word in ['rosato', 'rosé', 'rose']):
        return 'rosato'
    elif any(word in text_lower for word in ['spumante', 'champagne', 'prosecco', 'moscato', 'frizzante']):
        return 'spumante'
    else:
        return 'sconosciuto'
```

**Differenze**:
- Versione `csv_processor.py` ha più parole chiave (più completa)
- Versione `csv_processor.py` include: `cabernet`, `merlot`, `pinot noir`, `syrah`, `shiraz` per rosso
- Versione `csv_processor.py` include: `riesling`, `gewürztraminer` per bianco
- Versione `csv_processor.py` include: `pink`, `sparkling`, `cava`, `crémant` per spumante

**Proposta**: ✅ **Mantenere versione `csv_processor.py`** (più completa)  
**Azione**: Spostare in `ingest/normalization.py` come funzione condivisa

---

### 2. Logica Estrazione Vini - **SIMILARE** (Non duplicato esatto)

**Ubicazioni**:
- `csv_processor.py:518-648` - `extract_wine_data_from_row()`
- `ocr_processor.py:54-235` - `extract_wines_from_ocr_text()`, `extract_wine_generic()`, `extract_wine_from_match()`

**Confronto**:
- Entrambe estraggono dati vini ma da sorgenti diverse:
  - CSV: da righe DataFrame pandas
  - OCR: da testo grezzo
- Logica simile ma non identica (necessaria per contesti diversi)

**Proposta**: ⚠️ **NON è duplicazione** - Sono logiche diverse per contesti diversi  
**Azione**: Nessuna, mantenere separate ma riorganizzare in moduli

---

### 3. Normalizzazione/Cleaning - **SIMILARE** (Non duplicato esatto)

**Ubicazioni**:
- `csv_processor.py:176-185` - `normalize_column_name()`
- `csv_processor.py:666-677` - `clean_wine_name()`
- `ocr_processor.py:99-113` - `clean_ocr_text()`

**Confronto**:
- `normalize_column_name()`: normalizza nomi colonne (lowercase, trim, rimuove spazi)
- `clean_wine_name()`: pulisce nomi vini (rimuove caratteri speciali, spazi multipli)
- `clean_ocr_text()`: pulisce testo OCR (rimuove caratteri strani, normalizza spazi)

**Proposta**: ⚠️ **NON è duplicazione** - Sono funzioni diverse per scopi diversi  
**Azione**: Unificare in `ingest/normalization.py` come funzioni separate ma coese

---

### 4. Mapping Colonne - **POTENZIALMENTE DUPLICATO** (Da verificare)

**Ubicazioni**:
- `csv_processor.py:12-30` - `COLUMN_MAPPINGS` (dizionario sinonimi)
- `csv_processor.py:246-268` - `create_smart_column_mapping()` (mapping intelligente)
- `ai_processor.py:21-87` - `analyze_csv_structure()` (mapping con AI)

**Confronto**:
- `COLUMN_MAPPINGS`: dizionario statico di sinonimi
- `create_smart_column_mapping()`: usa `COLUMN_MAPPINGS` per mapping automatico
- `analyze_csv_structure()`: usa AI per mapping quando automatico fallisce

**Proposta**: ✅ **NON è duplicazione** - Sono livelli diversi di mapping (statico → AI)  
**Azione**: Mantenere tutti e 3, ma riorganizzare secondo pipeline target:
- Mapping statico → `ingest/normalization.py`
- Mapping AI → `ingest/llm_targeted.py`

---

## 📊 Riepilogo Duplicazioni

| # | Funzione | File 1 | File 2 | Tipo | Azione |
|---|----------|--------|--------|------|--------|
| 1 | `classify_wine_type()` | `csv_processor.py` | `ocr_processor.py` | 🔴 **DUPLICATO** | ✅ Mantenere versione `csv_processor.py`, spostare in `ingest/normalization.py` |
| 2 | Estrazione vini | `csv_processor.py` | `ocr_processor.py` | ⚠️ **SIMILARE** | ✅ Mantenere separate (contesti diversi) |
| 3 | Normalizzazione | `csv_processor.py` | `ocr_processor.py` | ⚠️ **SIMILARE** | ✅ Unificare in `ingest/normalization.py` |
| 4 | Mapping colonne | `csv_processor.py` | `ai_processor.py` | ✅ **NON DUPLICATO** | ✅ Mantenere (livelli diversi) |

---

## 🎯 Azioni Proposte

### Azione 1: Unificare `classify_wine_type()`
- **File**: Creare `ingest/normalization.py`
- **Funzione**: `classify_wine_type(text: str) -> str`
- **Versione**: Usare versione più completa da `csv_processor.py`
- **Import**: Sostituire import in `csv_processor.py` e `ocr_processor.py`

### Azione 2: Riorganizzare Normalizzazione
- **File**: `ingest/normalization.py`
- **Funzioni da spostare**:
  - `normalize_column_name()` da `csv_processor.py`
  - `clean_wine_name()` da `csv_processor.py`
  - `clean_ocr_text()` da `ocr_processor.py` → `clean_text()`
  - `classify_wine_type()` da `csv_processor.py`

### Azione 3: Mantenere Separazione Logica
- **Estrazione CSV**: `ingest/csv_parser.py`, `ingest/excel_parser.py`
- **Estrazione OCR**: `ingest/ocr.py`
- **Mapping AI**: `ingest/llm_targeted.py`

---

**Ultimo aggiornamento**: 04/11/2025

