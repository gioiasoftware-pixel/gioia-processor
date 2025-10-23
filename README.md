# 🍷 Gioia Processor - Microservizio Elaborazione Inventari

## 📋 Panoramica

**Gioia Processor** è un microservizio FastAPI dedicato all'elaborazione di file inventari per il sistema Gioia. Gestisce parsing di file CSV/Excel e riconoscimento OCR da immagini per estrarre dati sui vini.

## 🚀 Funzionalità

### **File Processing**
- **CSV**: Parsing file CSV con pattern matching intelligente
- **Excel**: Supporto file Excel (.xlsx, .xls) con openpyxl
- **OCR**: Riconoscimento testo da immagini inventari con Tesseract

### **API Endpoints**
- `GET /health` - Health check del servizio
- `POST /process-inventory` - Elabora file inventario
- `GET /status/{telegram_id}` - Stato elaborazione utente

### **Database Integration**
- Connessione PostgreSQL con SQLAlchemy
- Modelli per inventari e vini
- Gestione transazioni e backup

## 📁 Struttura Progetto

```
gioia-processor/
├── main.py                 # FastAPI application
├── csv_processor.py        # Logica parsing CSV/Excel
├── ocr_processor.py       # Logica OCR immagini
├── database.py            # Connessione e modelli DB
├── requirements.txt       # Dipendenze Python
├── start_processor.py     # Script avvio servizio
├── Procfile              # Configurazione deploy Railway
├── railway.json          # Config Railway
└── README.md             # Documentazione
```

## 🔧 Installazione e Deploy

### **1. Setup Locale**
```bash
# Installa dipendenze
pip install -r requirements.txt

# Configura variabili ambiente
export DATABASE_URL="postgresql://user:pass@host:port/db"
export PORT=8001

# Test locale
python test_processor.py

# Avvia servizio
python start_processor.py
```

### **2. Deploy Railway - GUIDA COMPLETA**

#### **STEP 1: Preparazione Repository**
```bash
# 1. Crea repository GitHub
# Vai su GitHub.com → New Repository
# Nome: gioia-processor
# Descrizione: Microservizio elaborazione inventari Gioia
# Pubblica come pubblico

# 2. Clona e configura
git clone https://github.com/tuo-username/gioia-processor.git
cd gioia-processor

# 3. Crea tutti i file (già creati)
# 4. Commit e push
git add .
git commit -m "Initial commit: Gioia Processor microservice"
git push origin main
```

#### **STEP 2: Deploy su Railway**
1. **Vai su Railway.app** e fai login
2. **Clicca "New Project"**
3. **Seleziona "Deploy from GitHub repo"**
4. **Connetti il repository `gioia-processor`**
5. **Railway rileva automaticamente** il progetto Python

#### **STEP 3: Configurazione Variabili Ambiente**
Nel dashboard Railway del progetto:

```env
# Variabili obbligatorie
DATABASE_URL=postgresql://user:pass@host:port/db
PORT=8001

# Variabili opzionali
PYTHON_VERSION=3.11
ENVIRONMENT=production
```

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

## 🔗 Configurazione Bot

### **Variabile Ambiente Bot**
Nel bot principale, configura:
```env
PROCESSOR_URL=https://your-processor.railway.app
```

### **URL Endpoints**
- **Health**: `GET /health`
- **Process**: `POST /process-inventory`
- **Status**: `GET /status/{telegram_id}`

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

### **Verifica Finale**
- [ ] `/testprocessor` nel bot restituisce successo
- [ ] Upload file inventario funziona
- [ ] Elaborazione file completata
- [ ] Dati salvati nel database
- [ ] Notifica utente ricevuta

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

---

**Nota**: Questo microservizio è completamente separato dal bot Telegram e gestisce solo l'elaborazione dei file inventari.
