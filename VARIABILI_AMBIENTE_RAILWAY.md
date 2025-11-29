# 🔧 Variabili Ambiente - Configurazione Permissiva per Beta Tester

**Servizio**: `gioia-processor` (su Railway)  
**Scopo**: Configurare soglie permissive per accettare inventari già puliti senza AI

---

## 📍 Dove Configurare

### **Railway Dashboard**

1. Vai su **Railway.app** → Login
2. Seleziona progetto **gioia-processor**
3. Vai su **Settings** → **Variables**
4. Aggiungi/modifica le variabili elencate sotto
5. **Redeploy** il servizio (Railway rileva automaticamente le modifiche)

---

## ✅ Variabili da Configurare

### **1. Soglie Stage 1 - PERMISSIVE (Obbligatorie per Beta Tester)**

```env
SCHEMA_SCORE_TH=0.50
MIN_VALID_ROWS=0.50
HEADER_CONFIDENCE_TH=0.50
```

**Descrizione**:
- `SCHEMA_SCORE_TH`: Soglia schema_score per Stage 1 (default: 0.80 → **0.50 permissiva**)
- `MIN_VALID_ROWS`: Soglia righe valide per Stage 1 (default: 0.70 → **0.50 permissiva**)
- `HEADER_CONFIDENCE_TH`: Soglia confidenza mapping header (default: 0.72 → **0.50 permissiva**)

**Effetto**: File puliti con schema_score >= 0.50 e valid_rows >= 0.50 passeranno Stage 1 senza AI.

---

### **2. Normalizzazione - PERMISSIVA (Consigliata)**

```env
NORMALIZATION_POLICY=SAFE
```

**Descrizione**: Policy di normalizzazione valori
- `SAFE`: Più permissivo (default, già configurato)
- `AGGRESSIVE`: Più rigido

**Nota**: `SAFE` è già il default, ma è meglio esplicitarlo.

---

### **3. Delta Override - PERMISSIVA (Opzionale)**

```env
LLM_STRICT_OVERRIDE_DELTA=0.05
```

**Descrizione**: Delta minimo per consentire override in modalità SAFE (default: 0.10 → **0.05 permissiva**)

**Effetto**: Più permissivo per override di valori.

---

## 📋 Variabili Esistenti (Non Modificare)

Queste variabili dovrebbero già essere configurate. **Verifica** che esistano:

### **Database (OBBLIGATORIO)**
```env
DATABASE_URL=postgresql://user:password@host:port/database
```

### **OpenAI (Opzionale ma Consigliato)**
```env
OPENAI_API_KEY=sk-your-openai-api-key-here
```

### **Feature Flags (Opzionali)**
```env
IA_TARGETED_ENABLED=true
LLM_FALLBACK_ENABLED=true
OCR_ENABLED=true
```

**Nota**: Mantieni queste a `true` per avere AI disponibile per casi complessi.

---

## 📝 Configurazione Completa Railway

### **Copia e Incolla in Railway Variables**

```env
# ============================================
# CONFIGURAZIONE PERMISSIVA PER BETA TESTER
# ============================================

# Soglie Stage 1 - PERMISSIVE
SCHEMA_SCORE_TH=0.50
MIN_VALID_ROWS=0.50
HEADER_CONFIDENCE_TH=0.50

# Normalizzazione - PERMISSIVA
NORMALIZATION_POLICY=SAFE

# Delta Override - PERMISSIVA
LLM_STRICT_OVERRIDE_DELTA=0.05

# ============================================
# VARIABILI ESISTENTI (Verifica che ci siano)
# ============================================

# Database (OBBLIGATORIO)
DATABASE_URL=postgresql://user:password@host:port/database

# OpenAI (Opzionale ma Consigliato)
OPENAI_API_KEY=sk-your-openai-api-key-here

# Feature Flags (Mantieni true)
IA_TARGETED_ENABLED=true
LLM_FALLBACK_ENABLED=true
OCR_ENABLED=true
```

---

## 🔍 Verifica Configurazione

### **Dopo il Deploy**

1. **Health Check**:
   ```bash
   curl https://your-processor.railway.app/health
   ```

2. **Verifica Logs** su Railway Dashboard:
   - Cerca: `schema_score_th=0.5`, `min_valid_rows=0.5`
   - Dovresti vedere: `✅ Configurazione processor validata con successo`

3. **Test con File Pulito**:
   - Carica un file pulito
   - Verifica nei log che passi Stage 1:
     ```
     [PIPELINE] Stage 1 parse completed: decision=save
     schema_score=0.65 valid_rows=0.60
     ```
   - Verifica che **NON** vada a Stage 2:
     ```
     [PIPELINE] Stage 2 skipped (decision=save)
     ```

---

## 📊 Confronto Soglie

| Soglia | Default (Rigido) | Permissiva (Beta Tester) | Riduzione |
|--------|-------------------|--------------------------|-----------|
| `SCHEMA_SCORE_TH` | 0.80 | **0.50** | -37.5% |
| `MIN_VALID_ROWS` | 0.70 | **0.50** | -28.6% |
| `HEADER_CONFIDENCE_TH` | 0.72 | **0.50** | -30.6% |
| `LLM_STRICT_OVERRIDE_DELTA` | 0.10 | **0.05** | -50% |

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

## 📞 Supporto

- **Logs**: Railway Dashboard → Logs
- **Health Check**: `GET /health`
- **Documentazione**: `CONFIGURAZIONE_PERMISSIVA_BETA_TESTER.md`

---

**Versione Documento**: 1.0  
**Data**: 2025-01-XX  
**Servizio**: gioia-processor (Railway)

