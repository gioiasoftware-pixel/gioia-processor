# 🍷 Gioia System - Bot Telegram + Processor AI

## 📋 Panoramica

**Gioia System** è un sistema completo composto da:
- **Telegram Bot** - Interfaccia utente per gestione inventari vini
- **AI Processor** - Microservizio FastAPI per elaborazione intelligente file inventari

Il sistema gestisce parsing di file CSV/Excel e riconoscimento OCR da immagini per estrarre dati sui vini con AI GPT-4.

## 🚀 Funzionalità

### **File Processing**
- **CSV**: Parsing file CSV con AI GPT-4 per riconoscimento intelligente colonne
- **Excel**: Supporto file Excel (.xlsx, .xls) con AI enhancement
- **OCR**: Riconoscimento testo da immagini con Tesseract + AI GPT-4
- **AI Enhancement**: Miglioramento automatico dati vini con OpenAI GPT-4

### **API Endpoints**
- `GET /health` - Health check del servizio
- `POST /process-inventory` - Elabora file inventario
- `GET /status/{telegram_id}` - Stato elaborazione utente
- `GET /ai/status` - Stato AI processor
- `POST /ai/test` - Test elaborazione AI

### **Database Integration**
- Connessione PostgreSQL con SQLAlchemy
- Modelli per inventari e vini
- Gestione transazioni e backup

## 📁 Struttura Sistema Completo

```
gioia-system/
├── telegram-bot/              # Bot Telegram
│   ├── main.py               # Bot principale
│   ├── handlers/             # Gestori comandi
│   ├── utils/                # Utility bot
│   └── requirements.txt       # Dipendenze bot
│
├── gioia-processor/          # AI Processor
│   ├── main.py               # FastAPI application
│   ├── ai_processor.py       # AI GPT-4 integration
│   ├── csv_processor.py      # Logica parsing CSV/Excel
│   ├── ocr_processor.py      # Logica OCR immagini
│   ├── database.py           # Connessione e modelli DB
│   ├── requirements.txt      # Dipendenze processor
│   ├── start_processor.py    # Script avvio servizio
│   ├── test_processor.py     # Test automatici
│   ├── Procfile              # Configurazione deploy Railway
│   ├── railway.json          # Config Railway
│   └── README.md             # Documentazione processor
│
└── README.md                 # Documentazione sistema completo
```

## 🔧 Installazione e Deploy Sistema Completo

### **1. Setup Locale - Sistema Completo**
```bash
# Clona o organizza la struttura
mkdir gioia-system
cd gioia-system

# Setup Bot Telegram
cd telegram-bot
pip install -r requirements.txt
export TELEGRAM_BOT_TOKEN="your_bot_token"
export PROCESSOR_URL="http://localhost:8001"
python main.py

# Setup AI Processor (in un altro terminale)
cd ../gioia-processor
pip install -r requirements.txt
export DATABASE_URL="postgresql://user:pass@host:port/db"
export OPENAI_API_KEY="your_openai_key"
export PORT=8001

# Test sistema completo
python test_processor.py

# Avvia processor
python start_processor.py
```

### **2. Deploy Sistema Completo**

#### **STEP 1: Repository GitHub**
```bash
# 1. Crea repository GitHub per il sistema completo
# Vai su GitHub.com → New Repository
# Nome: gioia-system
# Descrizione: Sistema completo Gioia - Bot Telegram + AI Processor
# Pubblica come pubblico

# 2. Organizza struttura locale
mkdir gioia-system
cd gioia-system

# 3. Copia bot Telegram nella cartella
cp -r /path/to/telegram-bot ./telegram-bot

# 4. Copia processor nella cartella
cp -r /path/to/gioia-processor ./gioia-processor

# 5. Commit e push sistema completo
git init
git add .
git commit -m "Initial commit: Gioia System - Bot + AI Processor"
git remote add origin https://github.com/tuo-username/gioia-system.git
git push -u origin main
```

#### **STEP 2: Deploy Processor su Railway**
1. **Vai su Railway.app** e fai login
2. **Clicca "New Project"**
3. **Seleziona "Deploy from GitHub repo"**
4. **Connetti il repository `gioia-system`**
5. **Seleziona cartella `gioia-processor`** per il deploy
6. **Railway rileva automaticamente** il progetto Python

#### **STEP 3: Configurazione Variabili Ambiente**
Nel dashboard Railway del progetto processor:

```env
# Variabili obbligatorie
DATABASE_URL=postgresql://user:pass@host:port/db
PORT=8001

# Variabili AI (opzionali ma consigliate)
OPENAI_API_KEY=your_openai_api_key

# Variabili opzionali
PYTHON_VERSION=3.11
ENVIRONMENT=production
```

#### **STEP 4: Deploy Bot Telegram**
Per il bot Telegram, puoi usare:
- **Railway** (come il processor)
- **Heroku** 
- **Render**
- **VPS** dedicato
- **Locale** con ngrok per testing

**Come ottenere DATABASE_URL:**
1. **Crea database PostgreSQL** su Railway
2. **Clicca sul database** → Settings → Connect
3. **Copia la stringa di connessione** completa
4. **Incolla in DATABASE_URL**

#### **STEP 4: Configurazione Deploy**
Railway dovrebbe rilevare automaticamente:
- **Build Command**: `pip install -r requirements.txt`
- **Start Command**: `python start_processor.py`
- **Port**: 8001

#### **STEP 5: Verifica Deploy**
1. **Attendi deploy completato** (2-3 minuti)
2. **Clicca sul dominio** generato da Railway
3. **Testa endpoint**: `https://your-app.railway.app/health`
4. **Dovrebbe restituire**: `{"status": "healthy", "service": "gioia-processor"}`

#### **STEP 6: Test Completo**
```bash
# Test con script automatico
python test_processor.py

# Test manuale
curl https://your-app.railway.app/health
```

### **3. Test Deploy**
```bash
# Health check
curl https://your-app.railway.app/health

# Test processamento (esempio)
curl -X POST https://your-app.railway.app/process-inventory \
  -F "telegram_id=123456" \
  -F "business_name=Test Restaurant" \
  -F "file_type=csv" \
  -F "file=@test.csv"
```

## 🔗 Configurazione Sistema Completo

### **Variabili Ambiente Bot**
Nel bot principale (`telegram-bot/main.py`), configura:
```env
# Bot Telegram
TELEGRAM_BOT_TOKEN=your_bot_token
PROCESSOR_URL=https://your-processor.railway.app

# Opzionali
LOG_LEVEL=INFO
DEBUG_MODE=false
```

### **Variabili Ambiente Processor**
Nel processor (`gioia-processor/`), configura:
```env
# Database
DATABASE_URL=postgresql://user:pass@host:port/db
PORT=8001

# AI
OPENAI_API_KEY=your_openai_api_key

# Opzionali
PYTHON_VERSION=3.11
ENVIRONMENT=production
```

### **URL Endpoints Processor**
- **Health**: `GET /health`
- **Process**: `POST /process-inventory`
- **Status**: `GET /status/{telegram_id}`
- **AI Status**: `GET /ai/status`
- **Debug Info**: `GET /debug/info`

## 📊 Modelli Database

### **Inventario**
- `id`: Primary key
- `telegram_id`: ID utente Telegram
- `business_name`: Nome locale/azienda
- `created_at`: Timestamp creazione
- `status`: Stato elaborazione

### **Vino**
- `id`: Primary key
- `inventory_id`: FK verso inventario
- `name`: Nome vino
- `vintage`: Annata
- `producer`: Produttore
- `region`: Regione
- `price`: Prezzo
- `quantity`: Quantità
- `wine_type`: Tipo vino (rosso/bianco/rosato/spumante)

## 🛠️ Sviluppo

### **Test Locale**
```bash
# Avvia server sviluppo
uvicorn main:app --reload --port 8001

# Test health check
curl http://localhost:8001/health
```

## 📈 Monitoraggio

### **Logs**
- Elaborazione file
- Errori parsing
- Performance OCR
- Connessioni database

### **Metriche**
- File processati
- Tempo elaborazione
- Success rate
- Errori per tipo

## 🔒 Sicurezza

- **CORS**: Configurato per comunicazione bot
- **Validazione**: Controllo input file
- **Error Handling**: Gestione errori robusta
- **Rate Limiting**: (da implementare)

## 🚀 Roadmap

- [ ] Cache Redis per performance
- [ ] Rate limiting API
- [ ] Monitoring avanzato
- [ ] Supporto più formati file
- [ ] OCR migliorato con AI
- [ ] Batch processing

## 🔧 Troubleshooting Railway

### **Problemi Comuni**

#### **1. Deploy Fallisce**
```bash
# Controlla logs su Railway dashboard
# Errori comuni:
- requirements.txt mancante
- start_processor.py non trovato
- DATABASE_URL non configurato
```

#### **2. Database Connection Error**
```bash
# Verifica DATABASE_URL
echo $DATABASE_URL

# Test connessione locale
psql $DATABASE_URL -c "SELECT 1;"
```

#### **3. Port Binding Error**
```bash
# Verifica che PORT sia configurato
# Railway dovrebbe impostarlo automaticamente
# Se manuale: export PORT=8001
```

#### **4. Dependencies Error**
```bash
# Aggiorna requirements.txt
pip freeze > requirements.txt

# Verifica versioni compatibili
pip install --upgrade -r requirements.txt
```

### **Monitoraggio Railway**

#### **Logs in Tempo Reale**
1. **Railway Dashboard** → Progetto → Logs
2. **Filtra per livello**: ERROR, WARN, INFO
3. **Monitora**: Connessioni DB, API calls, Errori

#### **Metriche Performance**
- **CPU Usage**: Monitora utilizzo risorse
- **Memory**: Controlla consumo RAM
- **Response Time**: Tempo risposta API
- **Error Rate**: Percentuale errori

#### **Health Check Automatico**
Railway monitora automaticamente:
- **Endpoint**: `/health`
- **Timeout**: 30 secondi
- **Retry**: 3 tentativi
- **Restart**: Automatico su failure

## ✅ CHECKLIST DEPLOY COMPLETO

### **Pre-Deploy**
- [ ] Repository GitHub creato (`gioia-processor`)
- [ ] Tutti i file creati (main.py, requirements.txt, etc.)
- [ ] Codice committato e pushato su GitHub
- [ ] Test locale funzionante

### **Deploy Railway**
- [ ] Progetto Railway creato
- [ ] Repository GitHub connesso
- [ ] Database PostgreSQL creato
- [ ] Variabili ambiente configurate
- [ ] Deploy completato con successo

### **Post-Deploy**
- [ ] Health check funzionante (`/health`)
- [ ] Database connesso
- [ ] URL processor ottenuto
- [ ] Bot principale aggiornato con PROCESSOR_URL
- [ ] Test integrazione bot-processor

### **Verifica Finale Sistema Completo**
- [ ] **Processor deployato** su Railway ✅
- [ ] **Bot deployato** e funzionante ✅
- [ ] **Connessione bot-processor** funzionante ✅
- [ ] **Database** connesso e operativo ✅
- [ ] **AI features** abilitate ✅
- [ ] **Test end-to-end** completato ✅

### **Test Sistema Completo**
```bash
# 1. Test processor
curl https://your-processor.railway.app/health

# 2. Test debug info
curl https://your-processor.railway.app/debug/info

# 3. Test AI
curl https://your-processor.railway.app/ai/status

# 4. Test bot (nel bot Telegram)
/testprocessor

# 5. Test completo inventario
# Invia file CSV/Excel/immagine al bot
# Verifica elaborazione e notifica
```

## 📞 Supporto

Per problemi o domande:
- **Repository**: `gioia-processor`
- **Logs**: Railway dashboard → Logs
- **Database**: Railway PostgreSQL dashboard
- **Bot Integration**: Usa `/testprocessor` nel bot

### **Comandi Debug**
```bash
# Test locale
python start_processor.py

# Test endpoint
curl http://localhost:8001/health

# Test database
python -c "from database import engine; print('DB OK')"

# Test completo
python test_processor.py
```

## 🎯 Gestione Workspace Cursor

### **Struttura Workspace Unificato**
```
gioia-system/                    # Workspace principale
├── telegram-bot/               # Bot Telegram
│   ├── main.py                # ← Apri in Cursor
│   ├── handlers/
│   └── requirements.txt
│
├── gioia-processor/           # AI Processor  
│   ├── main.py                # ← Apri in Cursor
│   ├── ai_processor.py        # ← Apri in Cursor
│   ├── database.py           # ← Apri in Cursor
│   └── requirements.txt
│
└── README.md                  # ← Questo file
```

### **Comandi Cursor Workspace**
```bash
# Apri tutto il sistema in Cursor
cursor gioia-system/

# Apri solo il processor
cursor gioia-system/gioia-processor/

# Apri solo il bot
cursor gioia-system/telegram-bot/

# Test completo sistema
cd gioia-system/gioia-processor
python test_processor.py
```

### **Sviluppo Simultaneo**
- ✅ **Bot e Processor** nello stesso workspace
- ✅ **Debugging** integrato
- ✅ **Git** unificato per tutto il sistema
- ✅ **Deploy** separati ma coordinati

---

**Nota**: Il sistema è ora completamente integrato con bot Telegram e AI processor in un unico workspace per sviluppo e gestione semplificati.
