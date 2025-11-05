# 🚀 Guida Deploy Processor v2.0.0

**Data**: 2025-01-XX  
**Versione**: 2.0.0  
**Scope**: Guida completa per deploy su Railway

---

## 📋 Pre-Requisiti

### 1. Repository GitHub
- ✅ Repository creato e aggiornato
- ✅ Codice committato e pushato
- ✅ Branch principale (main/master) aggiornato

### 2. Account Railway
- ✅ Account Railway creato
- ✅ Progetto Railway esistente (se update) o nuovo progetto

### 3. Database PostgreSQL
- ✅ Database PostgreSQL creato su Railway
- ✅ `DATABASE_URL` disponibile

---

## 🔧 Configurazione Pre-Deploy

### 1. Verifica File Essenziali

#### ✅ Procfile
```
web: python start_processor.py
```

#### ✅ railway.json
```json
{
  "$schema": "https://railway.app/railway.schema.json",
  "build": {
    "builder": "NIXPACKS"
  },
  "deploy": {
    "startCommand": "python start_processor.py",
    "restartPolicyType": "ON_FAILURE",
    "restartPolicyMaxRetries": 10
  }
}
```

#### ✅ requirements.txt
Verificare che contenga tutte le dipendenze:
- fastapi, uvicorn
- sqlalchemy, asyncpg, psycopg2-binary
- openai, tiktoken
- pandas, openpyxl
- pytesseract, Pillow, pdf2image
- pydantic, pydantic-settings
- rapidfuzz, charset-normalizer
- colorlog, pyjwt
- python-dotenv
- pytest, pytest-asyncio, httpx (per test)

#### ✅ start_processor.py
Verificare che punti a `api.main:app`:
```python
uvicorn.run("api.main:app", ...)
```

---

## 📝 Variabili Ambiente Railway

### Variabili Obbligatorie

#### DATABASE_URL
```
DATABASE_URL=postgresql://user:password@host:port/database
```
**Fonte**: Railway PostgreSQL dashboard → Settings → Connect

#### PORT
```
PORT=8001
```
**Nota**: Railway auto-configura, ma specificare se necessario

### Variabili Opzionali (Consigliate)

#### OpenAI (per AI features)
```
OPENAI_API_KEY=sk-your-openai-api-key-here
```

#### Feature Flags (default: tutti true)
```
IA_TARGETED_ENABLED=true
LLM_FALLBACK_ENABLED=true
OCR_ENABLED=true
```

#### Soglie Configurabili (opzionali)
```
SCHEMA_SCORE_TH=0.7
MIN_VALID_ROWS=0.6
HEADER_CONFIDENCE_TH=0.75
BATCH_SIZE_AMBIGUOUS_ROWS=20
MAX_LLM_TOKENS=300
LLM_MODEL_TARGETED=gpt-4o-mini
LLM_MODEL_EXTRACT=gpt-4o
DB_INSERT_BATCH_SIZE=500
```

**Vedi**: `report/ENV_VARIABLES.md` per documentazione completa

---

## 🚀 Deploy Railway

### Step 1: Connessione Repository

1. Vai su **Railway.app** → Dashboard
2. Clicca **"New Project"** (o seleziona progetto esistente)
3. Seleziona **"Deploy from GitHub repo"**
4. Connetti repository GitHub (se non già connesso)
5. Seleziona repository `gioia-processor`
6. Railway rileva automaticamente Python

### Step 2: Configurazione Variabili Ambiente

1. Vai su **Settings** → **Variables**
2. Aggiungi tutte le variabili ambiente:
   - `DATABASE_URL` (obbligatorio)
   - `OPENAI_API_KEY` (opzionale, ma consigliato)
   - `PORT` (opzionale, Railway auto-configura)
   - Feature flags (opzionali, default: true)

### Step 3: Database PostgreSQL

1. Se non presente, crea **PostgreSQL** service:
   - Clicca **"+ New"** → **"Database"** → **"Add PostgreSQL"**
2. Copia `DATABASE_URL`:
   - Clicca sul database → **Settings** → **Connect**
   - Copia connection string completa
3. Aggiungi `DATABASE_URL` in variabili ambiente del processor

### Step 4: Deploy

1. Railway inizia automaticamente il deploy
2. Monitora **Deployments** tab:
   - Build logs
   - Runtime logs
3. Attendi completamento (2-5 minuti)

### Step 5: Verifica Deploy

1. **Health Check**:
   ```bash
   curl https://your-app.railway.app/health
   ```
   Risposta attesa:
   ```json
   {
     "status": "healthy",
     "service": "gioia-processor",
     "version": "2.0.0",
     ...
   }
   ```

2. **Test Endpoint**:
   ```bash
   curl -X POST https://your-app.railway.app/process-inventory \
     -F "telegram_id=123456" \
     -F "business_name=Test" \
     -F "file_type=csv" \
     -F "file=@test.csv"
   ```

---

## 🔍 Post-Deploy Verifica

### 1. Logs Railway

Monitora logs in Railway dashboard:
- **Build logs**: Verificare che build sia completato senza errori
- **Runtime logs**: Verificare che server sia avviato correttamente
- **Error logs**: Verificare che non ci siano errori critici

### 2. Test Endpoint

#### Health Check
```bash
curl https://your-app.railway.app/health
```

#### Status Job
```bash
curl https://your-app.railway.app/status/{job_id}
```

#### Process Inventory (test)
```bash
curl -X POST https://your-app.railway.app/process-inventory \
  -F "telegram_id=123456" \
  -F "business_name=Test Business" \
  -F "file_type=csv" \
  -F "file=@tests/data/clean.csv"
```

### 3. Verifica Database

1. Verifica connessione database:
   - Railway PostgreSQL dashboard → Query
   - Eseguire: `SELECT 1;`

2. Verifica tabelle:
   - Eseguire: `SELECT table_name FROM information_schema.tables WHERE table_schema = 'public';`
   - Dovrebbe mostrare: `users`, `processing_jobs`, etc.

### 4. Verifica Logging

1. Monitora logs Railway:
   - Verificare che log JSON siano formattati correttamente
   - Verificare presenza `correlation_id`, `stage`, `decision`, `metrics`

2. Esempio log atteso:
   ```json
   {
     "timestamp": "2025-01-XX...",
     "level": "info",
     "message": "Stage 1 completed",
     "correlation_id": "...",
     "telegram_id": 123456,
     "stage": "csv_parse",
     "decision": "save",
     "metrics": {...}
   }
   ```

### 5. Test Bot Integration

1. Aggiorna bot con nuovo `PROCESSOR_URL`:
   ```
   PROCESSOR_URL=https://your-app.railway.app
   ```

2. Test bot:
   - Invia file CSV/Excel al bot
   - Verifica elaborazione
   - Verifica notifica completamento

---

## ⚠️ Troubleshooting Deploy

### Problema 1: Build Fails

**Sintomi**: Build error in Railway logs

**Cause comuni**:
- `requirements.txt` mancante o incompleto
- Dipendenze incompatibili
- Python version incompatibile

**Soluzione**:
1. Verifica `requirements.txt` completo
2. Verifica Python version (Railway auto-rileva, ma specificare se necessario)
3. Controlla build logs per errori specifici

### Problema 2: Server Non Avvia

**Sintomi**: Deploy completa ma server non risponde

**Cause comuni**:
- `start_processor.py` non trovato
- `api.main:app` non trovato
- Port binding error

**Soluzione**:
1. Verifica `Procfile`: `web: python start_processor.py`
2. Verifica `start_processor.py` punta a `api.main:app`
3. Verifica `PORT` variabile ambiente (Railway auto-configura)

### Problema 3: Database Connection Error

**Sintomi**: Errori database connection in logs

**Cause comuni**:
- `DATABASE_URL` non configurato
- `DATABASE_URL` formato errato
- Database non accessibile

**Soluzione**:
1. Verifica `DATABASE_URL` in variabili ambiente
2. Verifica formato: `postgresql://user:password@host:port/database`
3. Testa connessione database da Railway dashboard

### Problema 4: OpenAI API Error

**Sintomi**: Errori OpenAI API in logs

**Cause comuni**:
- `OPENAI_API_KEY` non configurato
- `OPENAI_API_KEY` invalido
- Rate limit OpenAI

**Soluzione**:
1. Verifica `OPENAI_API_KEY` in variabili ambiente
2. Verifica API key valida su OpenAI dashboard
3. Verifica rate limits

### Problema 5: Endpoint Non Trovati

**Sintomi**: 404 Not Found su endpoint

**Cause comuni**:
- Router non registrati in `api/main.py`
- Path endpoint errato

**Soluzione**:
1. Verifica `api/main.py` include tutti i router:
   ```python
   from api.routers import ingest, movements, snapshot
   app.include_router(ingest.router)
   app.include_router(movements.router)
   app.include_router(snapshot.router)
   ```

---

## 📊 Monitoraggio Post-Deploy

### Metriche da Monitorare

1. **Health Check**:
   - Frequenza: Ogni 5 minuti
   - Endpoint: `/health`
   - Alert se status != "healthy"

2. **Error Rate**:
   - Monitora logs per errori
   - Alert se error rate > 10/60min (configurato in alerting)

3. **Stage 3 Failure Rate**:
   - Monitora escalation a Stage 3
   - Alert se fallimenti > 5/60min (configurato in alerting)

4. **LLM Costs**:
   - Monitora costi stimati via logs
   - Alert se costi > €0.50/60min (configurato in alerting)

5. **Response Time**:
   - Monitora tempi elaborazione
   - Verifica entro soglie (Stage 1 < 2s, Stage 2 < 5s, Stage 3 < 15s)

### Log Analysis

1. **Railway Dashboard** → Logs:
   - Filtra per livello: ERROR, WARN
   - Cerca pattern: `correlation_id`, `stage`, `decision`
   - Analizza metriche escalation

2. **JSON Logs**:
   - Log in formato JSON strutturato
   - Aggregabili per analisi (es. percentuali escalation)

---

## ✅ Checklist Deploy Completo

### Pre-Deploy
- [x] Codice committato e pushato su GitHub ✅
- [x] `Procfile` verificato ✅
- [x] `railway.json` verificato ✅
- [x] `requirements.txt` completo ✅
- [x] `start_processor.py` corretto ✅
- [x] Documentazione completa ✅

### Deploy Railway
- [ ] Repository GitHub connesso
- [ ] Database PostgreSQL creato
- [ ] Variabili ambiente configurate:
  - [ ] `DATABASE_URL` (obbligatorio)
  - [ ] `OPENAI_API_KEY` (opzionale)
  - [ ] `PORT` (opzionale, Railway auto-configura)
  - [ ] Feature flags (opzionali)
- [ ] Deploy completato con successo

### Post-Deploy
- [ ] Health check funzionante (`/health`)
- [ ] Database connesso
- [ ] Logs verificati (JSON strutturato)
- [ ] Test endpoint completati
- [ ] Bot integration testata
- [ ] Monitoraggio configurato

---

## 🔗 Link Utili

- **Railway Dashboard**: https://railway.app
- **Railway Docs**: https://docs.railway.app
- **OpenAI Dashboard**: https://platform.openai.com
- **Documentazione Processor**: `report/DOCUMENTAZIONE_COMPLETA.md`
- **Variabili Ambiente**: `report/ENV_VARIABLES.md`

---

**Versione**: 2.0.0  
**Data**: 2025-01-XX  
**Status**: ✅ **PRONTO PER DEPLOY**

