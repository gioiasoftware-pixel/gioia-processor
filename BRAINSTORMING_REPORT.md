# 🧠 Brainstorming: Sistema Report

**Data**: 2025-01-XX  
**Obiettivo**: Analizzare dove è già previsto il report e dove integrarlo al meglio

---

## 📊 Analisi Situazione Attuale

### ✅ **Cosa è GIÀ Presente**

#### **1. Snapshot Inventario** (`api/routers/snapshot.py`)
- **Endpoint**: `GET /api/inventory/snapshot`
- **Funzionalità**: 
  - Restituisce lista vini con facets (type, vintage, winery)
  - Dati formattati per viewer
  - Meta informazioni (total_rows, last_update)
- **Uso**: Viewer web, bot (indirettamente)
- **Limiti**: Solo snapshot, nessuna analisi statistica

#### **2. Export CSV** (`api/routers/snapshot.py`)
- **Endpoint**: `GET /api/inventory/export.csv`
- **Funzionalità**: 
  - Export completo inventario in CSV
  - Tutti i campi disponibili
- **Uso**: Download dati per analisi esterne
- **Limiti**: Solo export, nessuna elaborazione

#### **3. Viewer HTML** (`viewer_generator.py`)
- **Funzionalità**: 
  - Genera HTML viewer interattivo
  - Filtri per tipo, annata, cantina
  - Visualizzazione inventario
- **Uso**: Visualizzazione web inventario
- **Limiti**: Solo visualizzazione, nessun report analitico

#### **4. Tabella Movimenti** (`core/database.py`)
- **Tabella**: `"{telegram_id}/{business_name} Consumi e rifornimenti"`
- **Campi disponibili**:
  - `wine_name`, `wine_producer`
  - `movement_type` (consumo/rifornimento)
  - `quantity_change`, `quantity_before`, `quantity_after`
  - `movement_date`
- **Stato**: ✅ Dati già tracciati e salvati
- **Uso attuale**: Solo logging movimenti
- **Potenziale**: ⭐⭐⭐⭐⭐ Per report movimenti/consumi

#### **5. Bot - Callback "full_report"** (`telegram-ai-bot/src/inventory.py`)
- **Posizione**: Linea 78, callback button
- **Stato**: ⚠️ **NON IMPLEMENTATO** (solo placeholder)
- **Messaggio**: "📊 Report completo in arrivo..."
- **Potenziale**: ⭐⭐⭐⭐⭐ Entry point per report nel bot

#### **6. Bot - Menzioni Report** (`telegram-ai-bot/src/bot.py`)
- **Linea 64**: "• 📊 Report e statistiche" (help)
- **Linea 141**: Esempio comando "Fammi un report del mio inventario"
- **Linea 151**: "• 📈 Report e statistiche" (features)
- **Stato**: ⚠️ Solo menzionato, non implementato

---

## 🎯 Cosa MANCA (Gap Analysis)

### **1. Report Analitici/Statistici**
- ❌ Statistiche inventario (valore totale, media prezzi, distribuzione tipi)
- ❌ Trend temporali (crescita/decrescita inventario)
- ❌ Analisi per categoria (Rosso vs Bianco, per regione, per produttore)
- ❌ Top vini per valore/quantità

### **2. Report Movimenti/Consumi**
- ❌ Report movimenti giornaliero/settimanale/mensile
- ❌ Analisi consumi per vino/produttore
- ❌ Trend consumi nel tempo
- ❌ Vini più venduti/consumati
- ❌ Rotazione scorte (turnover)

### **3. Report Scorte**
- ❌ Report scorte basse (già calcolato ma non reportato)
- ❌ Previsioni esaurimento scorte
- ❌ Analisi stock-out risk
- ❌ Consigli rifornimenti

### **4. Report Valore**
- ❌ Valore totale inventario (quantità × prezzo)
- ❌ Valore per categoria/tipologia
- ❌ Margine potenziale (prezzo vendita - costo)
- ❌ ROI per vino/produttore

### **5. Report Formattati**
- ❌ Report PDF
- ❌ Report HTML formattato (oltre al viewer)
- ❌ Report inviabili via email/Telegram
- ❌ Report periodici automatici

---

## 🏗️ Architettura Proposta

### **Struttura Moduli**

```
gioia-processor/
├── api/
│   └── routers/
│       ├── snapshot.py      ✅ (esistente - snapshot/export)
│       └── reports.py       🆕 (nuovo - report analitici)
│
├── core/
│   └── reports/            🆕 (nuovo modulo)
│       ├── __init__.py
│       ├── inventory_stats.py    # Statistiche inventario
│       ├── movements_report.py   # Report movimenti
│       ├── stock_report.py        # Report scorte
│       ├── value_report.py        # Report valore
│       └── formatters.py         # Formattazione PDF/HTML
│
└── viewer_generator.py      ✅ (esistente - può essere esteso)
```

---

## 📍 Punti di Integrazione

### **1. Processor - Nuovo Router Reports**

**File**: `api/routers/reports.py` (NUOVO)

**Endpoint proposti**:

```python
# Report inventario base
GET /api/reports/inventory/summary
GET /api/reports/inventory/stats
GET /api/reports/inventory/value

# Report movimenti
GET /api/reports/movements/daily
GET /api/reports/movements/weekly
GET /api/reports/movements/monthly
GET /api/reports/movements/top-wines

# Report scorte
GET /api/reports/stock/low-stock
GET /api/reports/stock/forecast

# Export formattati
GET /api/reports/inventory/pdf
GET /api/reports/inventory/html
GET /api/reports/movements/pdf
```

**Autenticazione**: Token JWT (come snapshot)

**Dati disponibili**:
- ✅ Tabella INVENTARIO (tutti i campi)
- ✅ Tabella CONSUMI (movimenti storici)
- ✅ Tabella BACKUP (storico inventario)
- ✅ Tabella LOG (interazioni bot)

---

### **2. Bot - Integrazione Report**

**File**: `telegram-ai-bot/src/inventory.py`

**Callback da implementare**:
```python
# Linea 78 - callback "full_report"
async def handle_full_report(update, context):
    # Chiama endpoint processor /api/reports/inventory/summary
    # Formatta risposta per Telegram
    # Invia report formattato
```

**Comandi bot**:
- `/report` - Report completo inventario
- `/report_movimenti` - Report movimenti
- `/report_scorte` - Report scorte basse
- `/stats` - Statistiche rapide

**Integrazione AI** (`telegram-ai-bot/src/ai.py`):
- AI può generare report su richiesta
- "Fammi un report del mio inventario"
- "Mostrami le statistiche dei consumi"

---

### **3. Viewer - Estensione Report**

**File**: `Vineinventory Viewer/app.js`

**Nuove sezioni viewer**:
- Tab "Report" nel viewer
- Grafici statistiche (Chart.js o simile)
- Export report direttamente dal viewer

**Endpoint viewer**:
- Chiama `/api/reports/*` per dati
- Visualizza grafici/statistiche
- Download PDF/HTML

---

### **4. Admin - Report Utenti**

**File**: `gioia-processor/admin_insert_inventory.py` (estendere)

**Nuovi script admin**:
- `admin_generate_report.py` - Genera report per utente
- `admin_batch_reports.py` - Report batch per tutti utenti

---

## 🔗 Integrazione con Componenti Esistenti

### **1. Snapshot Router** (`api/routers/snapshot.py`)

**Relazione**: Reports può riutilizzare logica snapshot
- ✅ Query database simili
- ✅ Autenticazione JWT già implementata
- ✅ Formattazione dati già presente

**Estensione possibile**:
```python
# In snapshot.py aggiungere:
@router.get("/inventory/stats")  # Estende snapshot con stats
async def get_inventory_stats(token: str = Query(...)):
    # Usa stessa logica snapshot + calcoli statistici
```

---

### **2. Movements Router** (`api/routers/movements.py`)

**Relazione**: Reports può leggere dati movimenti
- ✅ Tabella CONSUMI già popolata
- ✅ Struttura dati già definita
- ✅ Query movimenti già implementate (in movements.py)

**Estensione possibile**:
```python
# In movements.py aggiungere:
@router.get("/movements/report")  # Report movimenti
async def get_movements_report(...):
    # Query tabella CONSUMI
    # Calcola statistiche
    # Formatta report
```

**Oppure**:
- Creare nuovo router `reports.py` che legge da CONSUMI
- Separazione responsabilità: movements = scrittura, reports = lettura/analisi

---

### **3. Database Module** (`core/database.py`)

**Funzioni esistenti riutilizzabili**:
- ✅ `ensure_user_tables()` - Per accedere alle tabelle
- ✅ `get_user_table_name()` - Per nomi tabelle dinamiche
- ✅ `get_db()` - Per connessioni database

**Nuove funzioni da aggiungere**:
```python
# In core/database.py o nuovo core/reports/
async def get_inventory_stats(session, telegram_id, business_name):
    """Calcola statistiche inventario"""
    
async def get_movements_stats(session, telegram_id, business_name, period):
    """Calcola statistiche movimenti per periodo"""
    
async def get_stock_alerts(session, telegram_id, business_name):
    """Trova scorte basse"""
```

---

### **4. Viewer Generator** (`viewer_generator.py`)

**Estensione possibile**:
- Aggiungere generazione HTML report
- Riutilizzare logica `prepare_viewer_data()`
- Aggiungere template report HTML

---

## 📊 Tipi di Report da Implementare

### **1. Report Inventario Base**

**Dati**:
- Totale vini
- Totale bottiglie
- Valore totale inventario
- Distribuzione per tipo (Rosso/Bianco/etc.)
- Distribuzione per regione
- Top 10 vini per valore
- Top 10 vini per quantità

**Endpoint**: `GET /api/reports/inventory/summary`

**Formato risposta**:
```json
{
  "summary": {
    "total_wines": 150,
    "total_bottles": 2340,
    "total_value": 125000.50,
    "avg_price": 53.42
  },
  "distribution": {
    "by_type": {"Rosso": 80, "Bianco": 50, "Spumante": 20},
    "by_region": {"Toscana": 45, "Piemonte": 30, ...}
  },
  "top_wines": {
    "by_value": [...],
    "by_quantity": [...]
  }
}
```

---

### **2. Report Movimenti**

**Dati**:
- Movimenti ultimo giorno/settimana/mese
- Totale consumi vs rifornimenti
- Vini più venduti/consumati
- Trend movimenti nel tempo
- Rotazione scorte

**Endpoint**: `GET /api/reports/movements/{period}`

**Periodi**: `daily`, `weekly`, `monthly`, `custom`

**Formato risposta**:
```json
{
  "period": "weekly",
  "summary": {
    "total_consumi": 45,
    "total_rifornimenti": 120,
    "net_change": +75
  },
  "top_movements": [
    {"wine_name": "Barolo", "consumi": 12, "rifornimenti": 24}
  ],
  "trend": [
    {"date": "2025-01-15", "consumi": 5, "rifornimenti": 15}
  ]
}
```

---

### **3. Report Scorte**

**Dati**:
- Vini sotto soglia minima
- Previsioni esaurimento (basate su trend consumi)
- Consigli rifornimenti
- Analisi stock-out risk

**Endpoint**: `GET /api/reports/stock/low-stock`

**Formato risposta**:
```json
{
  "low_stock_count": 12,
  "critical_stock": [
    {
      "wine_name": "Barolo",
      "current_quantity": 3,
      "min_quantity": 10,
      "days_until_out": 15,
      "recommended_reorder": 20
    }
  ]
}
```

---

### **4. Report Valore**

**Dati**:
- Valore totale inventario
- Valore per categoria
- Margine potenziale totale
- ROI per vino/produttore

**Endpoint**: `GET /api/reports/inventory/value`

**Formato risposta**:
```json
{
  "total_value": 125000.50,
  "total_cost": 85000.00,
  "potential_margin": 40000.50,
  "by_category": {
    "Rosso": {"value": 80000, "cost": 55000},
    "Bianco": {"value": 30000, "cost": 20000}
  }
}
```

---

## 🎨 Formattazione Report

### **1. JSON** (default)
- Per API/integrazione
- Strutturato, facile da processare

### **2. HTML**
- Per viewer web
- Formattato, leggibile
- Grafici/visualizzazioni

### **3. PDF**
- Per download/stampa
- Formattazione professionale
- Logo, intestazione, footer

### **4. Telegram Markdown**
- Per bot Telegram
- Formattato per messaggi Telegram
- Emoji, tabelle, sezioni

---

## 🔄 Flusso Integrazione

### **Scenario 1: Report da Bot**

```
Utente → Bot: "/report"
    ↓
Bot → Processor: GET /api/reports/inventory/summary?token=JWT
    ↓
Processor → Database: Query INVENTARIO + CONSUMI
    ↓
Processor → Calcoli: Statistiche, aggregazioni
    ↓
Processor → Bot: JSON report
    ↓
Bot → Formattazione: Markdown Telegram
    ↓
Bot → Utente: Report formattato
```

### **Scenario 2: Report da Viewer**

```
Utente → Viewer: Click "Report"
    ↓
Viewer → Processor: GET /api/reports/inventory/stats?token=JWT
    ↓
Processor → Database: Query + calcoli
    ↓
Processor → Viewer: JSON report
    ↓
Viewer → Visualizzazione: Grafici Chart.js
    ↓
Utente → Download: PDF/HTML
```

### **Scenario 3: Report Automatico**

```
Scheduler → Processor: GET /api/reports/inventory/summary
    ↓
Processor → Database: Query
    ↓
Processor → Email/Telegram: Invia report periodico
```

---

## 📝 Checklist Implementazione

### **Fase 1: Core Reports Module**
- [ ] Creare `core/reports/` directory
- [ ] Implementare `inventory_stats.py`
- [ ] Implementare `movements_report.py`
- [ ] Implementare `stock_report.py`
- [ ] Implementare `value_report.py`
- [ ] Test unitari per ogni modulo

### **Fase 2: API Reports Router**
- [ ] Creare `api/routers/reports.py`
- [ ] Implementare endpoint `/api/reports/inventory/*`
- [ ] Implementare endpoint `/api/reports/movements/*`
- [ ] Implementare endpoint `/api/reports/stock/*`
- [ ] Autenticazione JWT (riutilizzare da snapshot)
- [ ] Test endpoint

### **Fase 3: Bot Integration**
- [ ] Implementare callback `full_report` in `inventory.py`
- [ ] Aggiungere comando `/report` in `bot.py`
- [ ] Integrare AI per generare report su richiesta
- [ ] Formattazione Markdown per Telegram
- [ ] Test bot

### **Fase 4: Viewer Integration**
- [ ] Aggiungere tab "Report" nel viewer
- [ ] Integrare Chart.js per grafici
- [ ] Aggiungere download PDF/HTML
- [ ] Test viewer

### **Fase 5: Formatters**
- [ ] Implementare HTML formatter
- [ ] Implementare PDF formatter (reportlab/weasyprint)
- [ ] Implementare Telegram Markdown formatter
- [ ] Test formatters

---

## 🎯 Priorità Implementazione

### **Alta Priorità** ⭐⭐⭐
1. **Report Inventario Base** - Fondamentale, richiesto dal bot
2. **Report Movimenti** - Dati già disponibili, alto valore
3. **Integrazione Bot** - Callback già presente, solo da implementare

### **Media Priorità** ⭐⭐
4. **Report Scorte** - Utile per gestione inventario
5. **Formattazione HTML** - Per viewer
6. **Statistiche Avanzate** - Valore aggiunto

### **Bassa Priorità** ⭐
7. **Report PDF** - Nice to have
8. **Report Automatici** - Futuro
9. **Grafici Avanzati** - Enhancement

---

## 💡 Considerazioni Tecniche

### **Performance**
- Query database ottimizzate (indici esistenti)
- Caching risultati report (Redis opzionale)
- Paginazione per report grandi

### **Sicurezza**
- Autenticazione JWT (già implementata)
- Validazione input periodi
- Rate limiting per endpoint report

### **Scalabilità**
- Report possono essere pesanti (molti dati)
- Considerare background jobs per report complessi
- Caching intelligente

---

## 🔗 File da Modificare/Creare

### **Nuovi File**
1. `gioia-processor/api/routers/reports.py` ⭐⭐⭐
2. `gioia-processor/core/reports/__init__.py`
3. `gioia-processor/core/reports/inventory_stats.py`
4. `gioia-processor/core/reports/movements_report.py`
5. `gioia-processor/core/reports/stock_report.py`
6. `gioia-processor/core/reports/value_report.py`
7. `gioia-processor/core/reports/formatters.py`

### **File da Modificare**
1. `gioia-processor/api/main.py` - Aggiungere router reports
2. `gioia-processor/api/routers/__init__.py` - Import reports
3. `telegram-ai-bot/src/inventory.py` - Implementare callback full_report
4. `telegram-ai-bot/src/bot.py` - Aggiungere comando /report
5. `telegram-ai-bot/src/ai.py` - Integrare generazione report AI

---

## 📚 Riferimenti Esistenti

### **Query Database Esistenti**
- `api/routers/snapshot.py` - Query inventario (linee 76-92)
- `api/routers/movements.py` - Query movimenti (linee 166-179)
- `core/database.py` - Struttura tabelle (linee 198-275)

### **Autenticazione**
- `jwt_utils.py` - Validazione token JWT
- `api/routers/snapshot.py` - Esempio uso JWT (linee 38-52)

### **Formattazione**
- `viewer_generator.py` - Generazione HTML
- `telegram-ai-bot/src/inventory.py` - Formattazione Telegram (linee 48-83)

---

**Prossimi Passi**: 
1. ✅ Analisi completata
2. ⏳ Implementare core/reports modules
3. ⏳ Implementare api/routers/reports.py
4. ⏳ Integrare nel bot
5. ⏳ Test end-to-end

