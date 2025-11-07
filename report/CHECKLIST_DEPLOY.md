# ✅ Checklist Deploy Processor v2.0.0

**Data**: 2025-01-XX  
**Versione**: 2.0.0  
**Status**: ✅ **PRONTO PER DEPLOY**

---

## 📋 Pre-Deploy Checklist

### ✅ File Essenziali Verificati
- [x] `Procfile` — `web: python start_processor.py` ✅
- [x] `railway.json` — Configurazione Railway corretta ✅
- [x] `start_processor.py` — Punta a `api.main:app` ✅
- [x] `requirements.txt` — Tutte le dipendenze presenti ✅
- [x] `api/main.py` — Tutti i router inclusi ✅
- [x] `core/config.py` — Configurazione pydantic-settings ✅
- [x] `core/database.py` — Database interactions ✅
- [x] `core/logger.py` — Logging unificato ✅
- [x] `ingest/pipeline.py` — Pipeline orchestrator ✅

### ✅ Architettura Verificata
- [x] Struttura modulare (`api/`, `core/`, `ingest/`) ✅
- [x] Pipeline deterministica a 5 stage ✅
- [x] Tutti i router registrati in `api/main.py` ✅
- [x] Endpoint compatibili (signature invariata) ✅

### ✅ Testing Verificato
- [x] Test suite completa (~70+ test) ✅
- [x] Mock utilities implementati ✅
- [x] Test coverage stimato > 80% ✅

### ✅ Documentazione Completa
- [x] `README.md` aggiornato ✅
- [x] `report/DOCUMENTAZIONE_COMPLETA.md` ✅
- [x] `report/DEPLOY_GUIDE.md` ✅
- [x] `report/ENV_VARIABLES.md` ✅
- [x] `report/COMPARATIVA_PRIMA_DOPO.md` ✅

---

## 🚀 Deploy Checklist

### Step 1: Git Commit & Push
- [ ] Commit con messaggio: `"refactor: processor v2.0.0 - modular architecture, deterministic pipeline"`
- [ ] Push su branch principale (main/master)
- [ ] Verifica repository GitHub aggiornato

### Step 2: Railway - Connessione Repository
- [ ] Vai su Railway.app → Dashboard
- [ ] Clicca "New Project" (o seleziona progetto esistente)
- [ ] Seleziona "Deploy from GitHub repo"
- [ ] Connetti repository GitHub (se non già connesso)
- [ ] Seleziona repository `gioia-processor`
- [ ] Verifica Railway rileva Python automaticamente

### Step 3: Railway - Database PostgreSQL
- [ ] Crea PostgreSQL service (se non presente):
  - Clicca "+ New" → "Database" → "Add PostgreSQL"
- [ ] Copia `DATABASE_URL`:
  - Clicca database → Settings → Connect
  - Copia connection string completa

### Step 4: Railway - Variabili Ambiente
- [ ] Vai su Settings → Variables
- [ ] Aggiungi variabili obbligatorie:
  - [ ] `DATABASE_URL` = (da PostgreSQL service)
- [ ] Aggiungi variabili opzionali (consigliate):
  - [ ] `OPENAI_API_KEY` = (per AI features)
  - [ ] `PORT` = `8001` (opzionale, Railway auto-configura)
- [ ] Aggiungi feature flags (opzionali, default: true):
  - [ ] `IA_TARGETED_ENABLED=true`
  - [ ] `LLM_FALLBACK_ENABLED=true`
  - [ ] `OCR_ENABLED=true`

### Step 5: Railway - Deploy
- [ ] Railway inizia automaticamente deploy
- [ ] Monitora Deployments tab:
  - [ ] Build logs (verifica build completato)
  - [ ] Runtime logs (verifica server avviato)
- [ ] Attendi completamento (2-5 minuti)

### Step 6: Verifica Deploy
- [ ] Health check:
  ```bash
  curl https://your-app.railway.app/health
  ```
  - [ ] Risposta: `{"status": "healthy", "service": "gioia-processor", "version": "2.0.0", ...}`
- [ ] Test endpoint:
  ```bash
  curl -X POST https://your-app.railway.app/process-inventory \
    -F "telegram_id=123456" \
    -F "business_name=Test" \
    -F "file_type=csv" \
    -F "file=@tests/data/clean.csv"
  ```
  - [ ] Risposta: `{"status": "processing", "job_id": "...", ...}`

---

## 🔍 Post-Deploy Checklist

### Verifica Funzionamento
- [ ] Health check OK (`GET /health`)
- [ ] Database connesso (verifica in health check response)
- [ ] OpenAI configurato (verifica in health check response)
- [ ] Endpoint `/process-inventory` funziona
- [ ] Endpoint `/process-movement` funziona
- [ ] Endpoint `/status/{job_id}` funziona
- [ ] Endpoint `/api/inventory/snapshot` funziona

### Verifica Logging
- [ ] Logs JSON strutturati visibili in Railway dashboard
- [ ] Logs includono `correlation_id`, `stage`, `decision`, `metrics`
- [ ] Logs formattati correttamente (JSON)

### Bot Integration
- [ ] Aggiorna bot con nuovo `PROCESSOR_URL`:
  ```
  PROCESSOR_URL=https://your-app.railway.app
  ```
- [ ] Test bot: invia file CSV/Excel al bot
- [ ] Verifica elaborazione completata
- [ ] Verifica notifica bot funziona

### Monitoraggio Iniziale (24h)
- [ ] Monitora error rate (alert se > 10/60min)
- [ ] Monitora Stage 3 failure rate (alert se > 5/60min)
- [ ] Monitora costi LLM (alert se > €0.50/60min)
- [ ] Verifica percentuali escalation:
  - [ ] Percentuale file che vanno a Stage 2
  - [ ] Percentuale file che vanno a Stage 3
  - [ ] Percentuale file che vanno a Stage 4
- [ ] Verifica tempi elaborazione:
  - [ ] Stage 1 < 2s
  - [ ] Stage 2 < 5s
  - [ ] Stage 3 < 15s
  - [ ] End-to-end < 30s

---

## ⚠️ Troubleshooting

### Se Build Fails
1. Verifica `requirements.txt` completo
2. Verifica Python version (Railway auto-rileva)
3. Controlla build logs per errori specifici

### Se Server Non Avvia
1. Verifica `Procfile`: `web: python start_processor.py`
2. Verifica `start_processor.py` punta a `api.main:app`
3. Verifica `PORT` variabile ambiente

### Se Database Connection Error
1. Verifica `DATABASE_URL` in variabili ambiente
2. Verifica formato: `postgresql://user:password@host:port/database`
3. Testa connessione database da Railway dashboard

### Se OpenAI API Error
1. Verifica `OPENAI_API_KEY` in variabili ambiente
2. Verifica API key valida su OpenAI dashboard
3. Verifica rate limits

### Se Endpoint Non Trovati
1. Verifica `api/main.py` include tutti i router
2. Verifica path endpoint corretti

---

## 📚 Documentazione Riferimento

- **Guida Deploy**: `report/DEPLOY_GUIDE.md`
- **Variabili Ambiente**: `report/ENV_VARIABLES.md`
- **Documentazione Completa**: `report/DOCUMENTAZIONE_COMPLETA.md`
- **Comparativa Prima/Dopo**: `report/COMPARATIVA_PRIMA_DOPO.md`
- **Verifica Completa**: `report/VERIFICA_COMPLETA.md`

---

## 🎯 Status Finale

**Pre-Deploy**: ✅ **COMPLETATO**  
**Deploy Railway**: ⚠️ **AZIONE MANUALE RICHIESTA**  
**Post-Deploy**: ⚠️ **DA FARE**

---

**Versione**: 2.0.0  
**Data**: 2025-01-XX  
**Status**: ✅ **PRONTO PER DEPLOY** (dopo commit/push)





