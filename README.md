# 🍷 Gioia Processor - AI Microservice v2.0.0

## 📋 Panoramica

**Gioia Processor** è un microservizio FastAPI per elaborazione intelligente di file inventari vini con pipeline deterministica multi-stage.

**Versione**: 2.0.0 (Refactored)  
**Architettura**: Modulare (`api/`, `core/`, `ingest/`)  
**Pipeline**: 5 stage deterministica (Gate → Parse → IA Mirata → LLM Mode → OCR)

## 🚀 Funzionalità

### **Pipeline Processing**
- **Stage 0 (Gate)**: Routing automatico file per tipo
- **Stage 1 (Parse Classico)**: Parsing CSV/Excel con encoding detection, normalization, validation
- **Stage 2 (IA Mirata)**: Disambiguazione header e correzione righe ambigue con `gpt-4o-mini`
- **Stage 3 (LLM Mode)**: Estrazione da testo grezzo con `gpt-4o` (solo se necessario)
- **Stage 4 (OCR)**: Estrazione testo da immagini/PDF con Tesseract + Stage 3

### **API Endpoints**
- `POST /process-inventory` - Elabora file inventario (nuova pipeline)
- `POST /process-movement` - Processa movimento inventario (consumo/rifornimento)
- `GET /status/{job_id}` - Stato elaborazione job
- `GET /health` - Health check del servizio
- `GET /api/inventory/snapshot` - Snapshot inventario con facets
- `GET /api/viewer/{view_id}` - HTML viewer inventario

### **Database**
- PostgreSQL con SQLAlchemy async
- Tabelle dinamiche per utente (`inventario_{telegram_id}`, `consumi_{telegram_id}`)
- Batch insert ottimizzato
- Job management con idempotency

## 📁 Struttura Progetto

```
gioia-processor/
├── api/                      # FastAPI application
│   ├── main.py              # FastAPI app principale
│   └── routers/             # API routers
│       ├── ingest.py        # POST /process-inventory
│       ├── movements.py     # POST /process-movement
│       └── snapshot.py      # GET /api/inventory/snapshot, /api/viewer/*
│
├── core/                     # Moduli core
│   ├── config.py            # Configurazione (pydantic-settings)
│   ├── database.py          # Database interactions
│   ├── job_manager.py       # Job management
│   ├── logger.py            # Logging unificato (JSON)
│   └── alerting.py          # Sistema alerting
│
├── ingest/                   # Pipeline processing
│   ├── gate.py              # Stage 0: Routing
│   ├── parser.py            # Stage 1: Parse classico
│   ├── llm_targeted.py      # Stage 2: IA mirata
│   ├── llm_extract.py       # Stage 3: LLM mode
│   ├── ocr_extract.py       # Stage 4: OCR
│   ├── pipeline.py          # Orchestratore principale
│   ├── validation.py        # Pydantic validation
│   ├── normalization.py     # Normalization functions
│   ├── csv_parser.py        # CSV parsing
│   └── excel_parser.py     # Excel parsing
│
├── tests/                    # Test suite (~70+ test)
│   ├── test_*.py            # Test unitari e integration
│   └── data/                # Test fixtures
│
├── report/                   # Documentazione e verifiche
│   ├── VERIFICA_COMPLETA.md
│   ├── DOCUMENTAZIONE_COMPLETA.md
│   └── ...
│
├── admin_notifications.py    # Admin notifications
├── viewer_generator.py        # Viewer HTML generation
├── jwt_utils.py             # JWT validation
├── start_processor.py       # Entry point
└── README.md                # Questo file
```

## 🔧 Installazione e Setup

### **1. Setup Locale**
```bash
# Installa dipendenze
pip install -r requirements.txt

# Configura variabili ambiente
export DATABASE_URL="postgresql://user:pass@host:port/db"
export OPENAI_API_KEY="your_openai_key"
export PORT=8001

# Avvia server
python start_processor.py

# Oppure con uvicorn
uvicorn api.main:app --reload --port 8001
```

### **2. Test**
```bash
# Esegui tutti i test
pytest tests/

# Test con coverage
pytest tests/ --cov=ingest --cov=core --cov=api

# Test specifici
pytest tests/test_parsers.py
pytest tests/test_ingest_flow.py
```

## 🚀 Deploy Railway

### **1. Repository GitHub**
```bash
# Commit e push
git add .
git commit -m "Refactor processor v2.0.0"
git push origin main
```

### **2. Deploy su Railway**
1. Vai su Railway.app → New Project
2. Deploy from GitHub repo
3. Seleziona repository e cartella `gioia-processor`
4. Railway rileva automaticamente Python

### **3. Variabili Ambiente**
Configura in Railway dashboard:
```env
DATABASE_URL=postgresql://user:pass@host:port/db
OPENAI_API_KEY=your_openai_api_key
PORT=8001  # Railway auto-configura
```

### **4. Verifica Deploy**
```bash
# Health check
curl https://your-app.railway.app/health

# Test processamento
curl -X POST https://your-app.railway.app/process-inventory \
  -F "telegram_id=123456" \
  -F "business_name=Test" \
  -F "file_type=csv" \
  -F "file=@test.csv"
```

## ⚙️ Configurazione

### **Variabili Ambiente**

**Obbligatorie**:
- `DATABASE_URL`: URL connessione PostgreSQL

**Opzionali**:
- `PORT`: Porta server (default: 8001)
- `OPENAI_API_KEY`: API key OpenAI (se mancante, AI disabilitata)

**Feature Flags**:
- `IA_TARGETED_ENABLED`: Abilita Stage 2 (default: true)
- `LLM_FALLBACK_ENABLED`: Abilita Stage 3 (default: true)
- `OCR_ENABLED`: Abilita Stage 4 (default: true)

**Vedi**: `report/ENV_VARIABLES.md` per documentazione completa

### **Endpoint API**
- `POST /process-inventory` - Elabora file inventario
- `POST /process-movement` - Processa movimento inventario
- `GET /status/{job_id}` - Stato job elaborazione
- `GET /health` - Health check
- `GET /api/inventory/snapshot` - Snapshot inventario
- `GET /api/viewer/{view_id}` - HTML viewer inventario

## 📊 Database

### **Tabelle Principali**
- `users`: Utenti Telegram (telegram_id, business_name)
- `processing_jobs`: Job elaborazione (job_id, status, processing_method)

### **Tabelle Dinamiche per Utente**
- `inventario_{telegram_id}`: Inventario vini (name, winery, vintage, qty, price, type)
- `consumi_{telegram_id}`: Log movimenti (wine_id, movement_type, quantity)

## 📈 Monitoring

### **Logging JSON**
Tutti i log in formato JSON strutturato con:
- `correlation_id`: ID correlazione
- `stage`: Stage pipeline
- `decision`: Decisione finale
- `metrics`: Metriche specifiche stage
- `elapsed_sec`: Tempo elaborazione

**Log leggibili in Railway dashboard**

### **Alerting**
Sistema alerting configurato per:
- Stage 3 failure rate (>= 5 fallimenti/60min)
- LLM cost (>= €0.50/60min)
- Error rate (>= 10 errori/60min)

**Vedi**: `report/VERIFICA_ALERTING.md`

## 🔒 Sicurezza

- **CORS**: Configurato per comunicazione bot
- **Validazione**: Pydantic validation per tutti i dati
- **Error Handling**: Gestione errori robusta con fallback automatici
- **Idempotency**: Supporto `client_msg_id` per richieste duplicate

## 📚 Documentazione

- **README.md**: Questo file (panoramica generale)
- **report/DOCUMENTAZIONE_COMPLETA.md**: Documentazione tecnica completa
- **report/VERIFICA_COMPLETA.md**: Verifica completa refactoring
- **report/ENV_VARIABLES.md**: Documentazione variabili ambiente

## 🚀 Roadmap

- [ ] Cache Redis per performance
- [ ] Rate limiting API
- [ ] Monitoring avanzato (Datadog, Logtail)
- [ ] Supporto più formati file
- [ ] OCR migliorato con AI
- [ ] Batch processing per file grandi

## 🔧 Troubleshooting

### **Problemi Comuni**

#### **1. Database Connection Error**
```bash
# Verifica DATABASE_URL
echo $DATABASE_URL

# Test connessione
psql $DATABASE_URL -c "SELECT 1;"
```

#### **2. OpenAI API Error**
```bash
# Verifica OPENAI_API_KEY
echo $OPENAI_API_KEY

# Se mancante, AI features sono disabilitate (Stage 2 e 3)
```

#### **3. Port Binding Error**
Railway auto-configura `PORT`, ma per locale:
```bash
export PORT=8001
python start_processor.py
```

### **Monitoraggio**

**Logs**: Tutti i log in formato JSON su stdout (leggibili in Railway dashboard)

**Health Check**: `GET /health` endpoint per monitoraggio automatico

**Alerting**: Alert automatici per Stage 3 failure, costi LLM, errori

## 📞 Supporto

- **Documentazione**: `report/DOCUMENTAZIONE_COMPLETA.md`
- **Logs**: Railway dashboard → Logs
- **Verifiche**: `report/VERIFICA_COMPLETA.md`

---

**Versione**: 2.0.0  
**Data**: 2025-01-XX
