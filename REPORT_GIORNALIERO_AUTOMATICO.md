# 📊 Report Giornaliero Automatico - Movimenti

**Versione**: 1.0  
**Data**: 2025-01-XX  
**Scopo**: Sistema automatico per inviare report giornalieri dei movimenti (consumi e rifornimenti) a tutti gli utenti

---

## 🎯 Funzionalità

Il sistema genera e invia automaticamente ogni giorno alle **10:00 ora italiana** un report dei movimenti del giorno precedente a tutti gli utenti attivi.

**Report include**:
- 📈 Statistiche generali (consumi, rifornimenti, variazione netta)
- 🍷 Dettaglio per vino (top 10 vini più attivi)
- 📅 Data del report (giorno precedente)

---

## ⚙️ Come Funziona

### **Architettura**

```
Processor Startup
    ↓
Scheduler APScheduler (AsyncIOScheduler)
    ↓
Ogni giorno alle 10:00 (ora italiana)
    ↓
Per ogni utente attivo:
    1. Query movimenti giorno precedente
    2. Calcola statistiche
    3. Genera report formattato
    4. Invia via Telegram
```

### **Componenti**

1. **`core/scheduler.py`**: 
   - Scheduler APScheduler con AsyncIOScheduler
   - Job schedulato con CronTrigger (10:00 ogni giorno)
   - Funzioni per generare e inviare report

2. **Integrazione in `api/main.py`**:
   - Scheduler avviato al startup
   - Scheduler fermato allo shutdown

3. **Dipendenza**: `apscheduler>=3.10.0`, `pytz>=2023.3`

---

## 🔧 Configurazione

### **Variabili Ambiente**

#### **Obbligatorie**

```env
# Token bot Telegram per inviare messaggi
TELEGRAM_BOT_TOKEN=your_bot_token_here
```

#### **Opzionali**

```env
# Abilita/disabilita report giornalieri (default: true)
DAILY_REPORTS_ENABLED=true
```

**Nota**: Se `TELEGRAM_BOT_TOKEN` non è configurato, i report giornalieri vengono disabilitati automaticamente.

---

## 📋 Dettagli Implementazione

### **1. Scheduler**

**File**: `core/scheduler.py`

**Funzioni principali**:
- `get_scheduler()`: Ottiene scheduler globale
- `setup_daily_reports_scheduler()`: Configura job giornaliero
- `start_scheduler()`: Avvia scheduler
- `shutdown_scheduler()`: Ferma scheduler
- `send_daily_reports_to_all_users()`: Funzione eseguita ogni giorno
- `generate_daily_movements_report()`: Genera report per un utente

### **2. Query Database**

**Tabella utilizzata**: `"{telegram_id}/{business_name} Consumi e rifornimenti"`

**Query movimenti**:
```sql
SELECT 
    wine_name,
    wine_producer,
    movement_type,
    quantity_change,
    quantity_before,
    quantity_after,
    movement_date
FROM "{telegram_id}/{business_name} Consumi e rifornimenti"
WHERE user_id = :user_id
AND movement_date >= :start_date  -- 00:00 del giorno precedente
AND movement_date <= :end_date    -- 23:59 del giorno precedente
ORDER BY movement_date ASC
```

### **3. Calcolo Statistiche**

Per ogni utente:
- **Totale consumi**: Somma di `abs(quantity_change)` per `movement_type='consumo'`
- **Totale rifornimenti**: Somma di `quantity_change` per `movement_type='rifornimento'`
- **Variazione netta**: `rifornimenti - consumi`
- **Raggruppamento per vino**: Top 10 vini più attivi

### **4. Formattazione Report**

**Formato**: Markdown Telegram

**Esempio report**:
```
📊 **Report Movimenti - 15/01/2025**

🏢 **Ristorante La Pergola**

📈 **Statistiche Generali**
• Consumi: 45 bottiglie
• Rifornimenti: 120 bottiglie
• Variazione netta: +75 bottiglie
• Movimenti totali: 12

🍷 **Dettaglio per Vino**

**Barolo DOCG**
  📉 Consumate: 12 bottiglie
  📈 Rifornite: 24 bottiglie

**Chianti Classico**
  📉 Consumate: 8 bottiglie
  📈 Rifornite: 15 bottiglie

...

💡 Usa `/inventario` per vedere il tuo inventario completo
```

---

## 🚀 Avvio Automatico

Il scheduler si avvia automaticamente quando il processor parte:

1. **Al startup** (`api/main.py`):
   ```python
   @app.on_event("startup")
   async def startup_event():
       # ... altre inizializzazioni ...
       start_scheduler()  # Avvia scheduler
   ```

2. **Al shutdown**:
   ```python
   @app.on_event("shutdown")
   async def shutdown_event():
       shutdown_scheduler()  # Ferma scheduler
   ```

---

## ⏰ Orario Esecuzione

**Orario**: Ogni giorno alle **10:00 ora italiana** (Europe/Rome)

**Timezone**: `pytz.timezone('Europe/Rome')`

**Nota**: Il report riguarda sempre il **giorno precedente** (00:00 - 23:59).

**Esempio**:
- Se oggi è **16 gennaio 2025 alle 10:00**
- Il report riguarda **15 gennaio 2025** (00:00 - 23:59)

---

## 🔍 Logging

Tutti gli eventi sono loggati con prefisso `[DAILY_REPORT]` o `[SCHEDULER]`:

```
[SCHEDULER] Scheduler avviato
[SCHEDULER] Report giornaliero configurato: ogni giorno alle 10:00 (ora italiana)
[DAILY_REPORT] Inizio generazione report giornalieri
[DAILY_REPORT] Generazione report per data: 2025-01-15
[DAILY_REPORT] Trovati 25 utenti attivi
[DAILY_REPORT] Report inviato a 123456789/Ristorante La Pergola
[DAILY_REPORT] Completato: 20 inviati, 3 saltati, 2 errori
```

---

## 🛠️ Troubleshooting

### **Problema: Report non vengono inviati**

**Verifica**:
1. `TELEGRAM_BOT_TOKEN` configurato?
2. `DAILY_REPORTS_ENABLED=true`?
3. Scheduler avviato? (controlla log startup)
4. Utenti hanno movimenti nel giorno precedente?

**Log da controllare**:
```
[SCHEDULER] Scheduler avviato
[SCHEDULER] Report giornaliero configurato: ogni giorno alle 10:00 (ora italiana)
```

---

### **Problema: Scheduler non parte**

**Possibili cause**:
- Errore durante startup
- Dipendenze mancanti (`apscheduler`, `pytz`)

**Soluzione**:
```bash
pip install apscheduler>=3.10.0 pytz>=2023.3
```

---

### **Problema: Report inviati a orario sbagliato**

**Verifica timezone**:
- Scheduler usa `Europe/Rome` (ora italiana)
- Verifica che il server sia configurato correttamente

**Test manuale**:
```python
from datetime import datetime
import pytz

italy_tz = pytz.timezone('Europe/Rome')
now = datetime.now(italy_tz)
print(f"Ora attuale Italia: {now}")
```

---

### **Problema: Utenti non ricevono report**

**Possibili cause**:
1. Utente non ha `onboarding_completed=True`
2. Utente non ha `business_name`
3. Nessun movimento nel giorno precedente (report saltato)
4. Errore invio Telegram (rate limiting, token invalido)

**Log da controllare**:
```
[DAILY_REPORT] Report inviato a {telegram_id}/{business_name}
[DAILY_REPORT] Errore invio report a {telegram_id}
[TELEGRAM_NOTIFIER] Errore invio messaggio Telegram
```

---

## 🧪 Test Manuale

### **Test Generazione Report**

Puoi testare manualmente la generazione report:

```python
from core.scheduler import generate_daily_movements_report
from datetime import datetime
import pytz

italy_tz = pytz.timezone('Europe/Rome')
yesterday = datetime.now(italy_tz) - timedelta(days=1)

report = await generate_daily_movements_report(
    telegram_id=123456789,
    business_name="Ristorante La Pergola",
    report_date=yesterday.replace(hour=0, minute=0, second=0, microsecond=0)
)

print(report)
```

### **Test Invio Report**

Puoi testare l'invio a tutti gli utenti:

```python
from core.scheduler import send_daily_reports_to_all_users

await send_daily_reports_to_all_users()
```

**⚠️ ATTENZIONE**: Questo invierà report a TUTTI gli utenti attivi!

---

## 📊 Statistiche Report

Il report include:

### **Statistiche Generali**
- Totale consumi (bottiglie)
- Totale rifornimenti (bottiglie)
- Variazione netta (bottiglie)
- Numero movimenti totali

### **Dettaglio per Vino**
- Top 10 vini più attivi
- Consumi per vino
- Rifornimenti per vino

---

## 🔄 Estensioni Future

Possibili miglioramenti:

1. **Report personalizzabili**:
   - Utente può scegliere orario invio
   - Utente può disabilitare report

2. **Report multipli**:
   - Report settimanale
   - Report mensile
   - Report annuale

3. **Formati multipli**:
   - Report HTML
   - Report PDF
   - Report Excel

4. **Filtri**:
   - Solo consumi
   - Solo rifornimenti
   - Per categoria vino

---

## 📝 Note Tecniche

### **APScheduler**

- **AsyncIOScheduler**: Compatibile con asyncio
- **CronTrigger**: Trigger cron per scheduling
- **Timezone**: Europe/Rome (ora italiana)
- **Misfire Grace Time**: 3600 secondi (1 ora)

### **Performance**

- Query ottimizzate con indici esistenti
- Rate limiting Telegram: pausa 0.5s tra invii
- Max instances: 1 (solo una esecuzione alla volta)

### **Affidabilità**

- Se il job viene perso, viene eseguito entro 1 ora (misfire_grace_time)
- Errori per singolo utente non bloccano altri utenti
- Logging completo per debugging

---

## ✅ Checklist Configurazione

- [ ] `TELEGRAM_BOT_TOKEN` configurato in Railway
- [ ] `DAILY_REPORTS_ENABLED=true` (opzionale, default true)
- [ ] Dipendenze installate (`apscheduler`, `pytz`)
- [ ] Scheduler avviato al startup (verifica log)
- [ ] Test manuale generazione report
- [ ] Verifica invio report (controlla log)

---

**Versione**: 1.0  
**Autore**: Sistema Report Giornaliero Automatico  
**Data**: 2025-01-XX

