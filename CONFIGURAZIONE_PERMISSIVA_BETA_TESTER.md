# 🔧 Configurazione Permissiva per Beta Tester - Processor 2.0.0

**Scopo**: Configurare il processor 2.0.0 per accettare inventari già puliti senza validazioni troppo rigide.

---

## 🎯 Problema

La versione 2.0.0 ha **"maglie strette"** che potrebbero rifiutare anche inventari puliti:
- ❌ `SCHEMA_SCORE_TH=0.80` - Soglia troppo alta per schema_score
- ❌ `MIN_VALID_ROWS=0.70` - Soglia troppo alta per righe valide
- ❌ Validazione Pydantic rigida (name obbligatorio, vintage 1900-2099, etc.)
- ❌ Header confidence threshold = 0.72

**Risultato**: Inventari puliti potrebbero essere inviati a Stage 2/3 (AI) anche quando non necessario.

---

## ✅ Soluzione: Configurazione Permissiva

Mantieni la **versione 2.0.0** ma configura soglie più basse per inventari già puliti.

### **Variabili Ambiente da Configurare**

Aggiungi queste variabili ambiente in Railway (o `.env` locale):

```env
# ============================================
# CONFIGURAZIONE PERMISSIVA PER BETA TESTER
# ============================================

# Soglie Stage 1 - PERMISSIVE (per inventari già puliti)
SCHEMA_SCORE_TH=0.50          # Default: 0.80 - Abbassato per accettare più file
MIN_VALID_ROWS=0.50           # Default: 0.70 - Abbassato per accettare più file
HEADER_CONFIDENCE_TH=0.50     # Default: 0.72 - Abbassato per header matching

# Normalizzazione - PERMISSIVA
NORMALIZATION_POLICY=SAFE     # SAFE = più permissivo, AGGRESSIVE = più rigido

# Feature Flags - Disabilita AI se non necessario
IA_TARGETED_ENABLED=true      # Mantieni abilitato per casi complessi
LLM_FALLBACK_ENABLED=true     # Mantieni abilitato per casi complessi
OCR_ENABLED=true              # Mantieni abilitato per foto/PDF

# Delta per override in modalità SAFE
LLM_STRICT_OVERRIDE_DELTA=0.05  # Default: 0.10 - Più permissivo
```

---

## 📊 Confronto Soglie

| Soglia | Default (Rigido) | Permissiva (Beta Tester) | Differenza |
|--------|------------------|--------------------------|------------|
| `SCHEMA_SCORE_TH` | 0.80 | 0.50 | -37.5% |
| `MIN_VALID_ROWS` | 0.70 | 0.50 | -28.6% |
| `HEADER_CONFIDENCE_TH` | 0.72 | 0.50 | -30.6% |

**Effetto**: Con soglie più basse, più file puliti passeranno Stage 1 senza AI.

---

## 🔄 Comportamento con Configurazione Permissiva

### **Prima (Default Rigido)** ❌

```
File pulito con schema_score=0.65, valid_rows=0.60
  ↓
Stage 1: schema_score=0.65 < 0.80 → ESCALATE
  ↓
Stage 2: AI chiamata (gpt-4o-mini) - COSTO €0.01-0.02
  ↓
Salva
```

**Problema**: AI chiamata anche per file puliti.

---

### **Dopo (Permissiva)** ✅

```
File pulito con schema_score=0.65, valid_rows=0.60
  ↓
Stage 1: schema_score=0.65 >= 0.50 ✅ AND valid_rows=0.60 >= 0.50 ✅
  ↓
SALVA DIRETTAMENTE - NO AI
```

**Vantaggio**: File puliti salvati senza AI, zero costi.

---

## 🛠️ Implementazione

### **Opzione 1: Variabili Ambiente (Consigliata)**

Aggiungi le variabili in Railway Dashboard:

1. Vai su **Railway Dashboard** → Progetto Processor
2. **Settings** → **Variables**
3. Aggiungi:
   ```
   SCHEMA_SCORE_TH=0.50
   MIN_VALID_ROWS=0.50
   HEADER_CONFIDENCE_TH=0.50
   NORMALIZATION_POLICY=SAFE
   ```
4. **Redeploy** il servizio

---

### **Opzione 2: File .env Locale**

Per test locale, crea/modifica `.env`:

```env
# Database
DATABASE_URL=postgresql://user:pass@host:port/db

# OpenAI (opzionale, ma consigliato)
OPENAI_API_KEY=your_key

# Configurazione Permissiva
SCHEMA_SCORE_TH=0.50
MIN_VALID_ROWS=0.50
HEADER_CONFIDENCE_TH=0.50
NORMALIZATION_POLICY=SAFE
```

---

## 📈 Risultati Attesi

### **File Puliti (Beta Tester)**

**Prima** (soglie rigide):
- 30-40% vanno a Stage 2 (AI)
- Costo: €0.01-0.02 per file
- Tempo: 20-40 secondi

**Dopo** (soglie permissive):
- 5-10% vanno a Stage 2 (solo file veramente problematici)
- Costo: €0 per file puliti
- Tempo: 8-15 secondi

**Risparmio**: ~90% costi AI per file puliti

---

## ⚠️ Attenzione

### **Quando NON usare soglie permissive**

- ❌ Se ricevi inventari non puliti
- ❌ Se vuoi massima qualità dati
- ❌ Se vuoi che AI corregga errori automaticamente

### **Quando usare soglie permissive**

- ✅ Inventari già puliti/pre-processati
- ✅ Beta tester con file controllati
- ✅ Vuoi minimizzare costi AI
- ✅ Vuoi massima velocità

---

## 🔍 Verifica Configurazione

### **Test Locale**

```bash
# Verifica che le variabili siano caricate
python -c "
from gioia-processor.core.config import get_config
config = get_config()
print(f'SCHEMA_SCORE_TH: {config.schema_score_th}')
print(f'MIN_VALID_ROWS: {config.min_valid_rows}')
print(f'HEADER_CONFIDENCE_TH: {config.header_confidence_th}')
"
```

**Output atteso**:
```
SCHEMA_SCORE_TH: 0.5
MIN_VALID_ROWS: 0.5
HEADER_CONFIDENCE_TH: 0.5
```

---

### **Test con File Pulito**

1. Carica un file pulito
2. Verifica nei log che passi Stage 1 senza escalation:
   ```
   [PIPELINE] Stage 1 parse completed: decision=save
   schema_score=0.65 valid_rows=0.60
   ```
3. Verifica che **NON** vada a Stage 2:
   ```
   [PIPELINE] Stage 2 skipped (decision=save)
   ```

---

## 📝 Configurazione Graduale

Se vuoi essere più conservativo, puoi abbassare gradualmente:

### **Livello 1: Moderatamente Permissivo**
```env
SCHEMA_SCORE_TH=0.65
MIN_VALID_ROWS=0.60
HEADER_CONFIDENCE_TH=0.60
```

### **Livello 2: Permissivo (Consigliato per Beta Tester)**
```env
SCHEMA_SCORE_TH=0.50
MIN_VALID_ROWS=0.50
HEADER_CONFIDENCE_TH=0.50
```

### **Livello 3: Molto Permissivo (Solo se necessario)**
```env
SCHEMA_SCORE_TH=0.40
MIN_VALID_ROWS=0.40
HEADER_CONFIDENCE_TH=0.40
```

**⚠️ Attenzione**: Livello 3 potrebbe accettare file con problemi.

---

## 🎯 Raccomandazione Finale

**Per Beta Tester con inventari puliti**:

1. ✅ **Mantieni versione 2.0.0** (non tornare alla 1.0)
2. ✅ **Configura soglie permissive** (SCHEMA_SCORE_TH=0.50, MIN_VALID_ROWS=0.50)
3. ✅ **Mantieni AI abilitata** (per casi complessi)
4. ✅ **Monitora log** per verificare che file puliti passino Stage 1

**Vantaggi**:
- ✅ Mantieni architettura modulare e manutenibile
- ✅ Mantieni sistema di alerting e monitoring
- ✅ Mantieni test coverage completo
- ✅ Zero costi AI per file puliti
- ✅ Massima velocità per file puliti
- ✅ AI disponibile per casi complessi

---

## 📊 Esempio Pratico

### **File Pulito: 100 vini, schema_score=0.65, valid_rows=0.60**

**Con Default (Rigido)**:
```
Stage 1: schema_score=0.65 < 0.80 → ESCALATE
Stage 2: AI chiamata (gpt-4o-mini)
  → Costo: €0.01-0.02
  → Tempo: 25-35 secondi
  → Risultato: ✅ Salvato
```

**Con Permissiva**:
```
Stage 1: schema_score=0.65 >= 0.50 ✅ AND valid_rows=0.60 >= 0.50 ✅
  → Decision: SAVE
  → Costo: €0
  → Tempo: 10-15 secondi
  → Risultato: ✅ Salvato
```

**Risparmio**: €0.01-0.02 per file, 15-20 secondi per file

---

## 🔄 Rollback

Se le soglie permissive causano problemi:

1. **Aumenta gradualmente** le soglie:
   ```env
   SCHEMA_SCORE_TH=0.60  # Da 0.50 a 0.60
   MIN_VALID_ROWS=0.55   # Da 0.50 a 0.55
   ```

2. **Monitora log** per vedere quanti file vanno a Stage 2

3. **Trova equilibrio** tra permissività e qualità

---

**Versione Documento**: 1.0  
**Data**: 2025-01-XX  
**Autore**: AI Assistant

