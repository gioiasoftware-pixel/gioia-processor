# 📥 Inserimento Manuale Inventari Beta Tester

**Scopo**: Inserire manualmente inventari puliti nel database senza che i beta tester debbano scrivere al bot.

---

## 🎯 Quando Usare

- ✅ Hai pulito manualmente l'inventario di un beta tester
- ✅ Vuoi inserire dati direttamente nel database
- ✅ Il beta tester non ha ancora fatto onboarding o non può usare il bot
- ✅ Vuoi sostituire completamente un inventario esistente

---

## 📋 Prerequisiti

1. **File CSV pulito** con formato template:
   - Header: `Nome,Produttore,Fornitore,Annata,Quantità,Prezzo,Costo,Tipologia,Uvaggio,Regione,Paese,Classificazione`
   - Usa `TEMPLATE_INVENTARIO_PULITO.csv` come riferimento

2. **Telegram ID** del beta tester
   - Puoi ottenerlo dal database o chiedendolo al beta tester

3. **Business Name** del beta tester
   - Nome del ristorante/enoteca (es: "Ristorante XYZ")

4. **Variabili ambiente** configurate:
   - `DATABASE_URL` deve essere configurata nel `.env` o come variabile ambiente

---

## 🚀 Come Usare

### **1. Prepara il CSV**

Assicurati che il CSV abbia questo formato:

```csv
Nome,Produttore,Fornitore,Annata,Quantità,Prezzo,Costo,Tipologia,Uvaggio,Regione,Paese,Classificazione
Barolo DOCG,Giacomo Conterno,Importatore XYZ,2018,12,45.50,32.00,Rosso,Nebbiolo,Piemonte,Italia,DOCG
Chianti Classico,Fontodi,Distributore ABC,2019,24,28.00,18.50,Rosso,Sangiovese,Toscana,Italia,DOCG
```

**Campi obbligatori**:
- `Nome` - Nome del vino (obbligatorio)
- `Quantità` - Quantità bottiglie (obbligatorio, default 0 se vuoto)

**Campi opzionali**:
- Tutti gli altri campi possono essere vuoti

---

### **2. Ottieni Telegram ID**

#### **Opzione A: Dal Database**

```sql
SELECT telegram_id, business_name, username, first_name 
FROM users 
WHERE business_name = 'Nome Ristorante';
```

#### **Opzione B: Chiedi al Beta Tester**

Il beta tester può ottenere il suo Telegram ID usando un bot come `@userinfobot` su Telegram.

#### **Opzione C: Se Non Esiste**

Se l'utente non esiste ancora, lo script lo creerà automaticamente. Basta fornire:
- Un `telegram_id` valido (numero intero)
- Il `business_name`

---

### **3. Esegui lo Script**

#### **Modalità ADD (aggiunge all'inventario esistente)**

```bash
cd gioia-processor
python admin_insert_inventory.py <telegram_id> "<business_name>" <file_csv>
```

**Esempio**:
```bash
python admin_insert_inventory.py 123456789 "Ristorante XYZ" inventario_pulito.csv
```

#### **Modalità REPLACE (sostituisce inventario esistente)**

```bash
python admin_insert_inventory.py <telegram_id> "<business_name>" <file_csv> --replace
```

**Esempio**:
```bash
python admin_insert_inventory.py 123456789 "Ristorante XYZ" inventario_pulito.csv --replace
```

---

## 📊 Output

Lo script mostra:

```
============================================================
ADMIN INSERT INVENTORY
============================================================
Telegram ID: 123456789
Business Name: Ristorante XYZ
CSV File: inventario_pulito.csv
Mode: ADD
============================================================
Lettura CSV: inventario_pulito.csv
Trovati 25 vini nel CSV
Utente 123456789 trovato: Ristorante XYZ
Inserimento 25 vini nel database...
✅ Inserimento completato: 25 salvati, 0 errori su 25 totali

============================================================
✅ INSERIMENTO COMPLETATO
============================================================
Vini salvati: 25
Errori: 0
============================================================
```

---

## 🔍 Verifica Inserimento

### **1. Verifica nel Database**

```sql
-- Conta vini inseriti
SELECT COUNT(*) 
FROM "{telegram_id}/{business_name} INVENTARIO"
WHERE user_id = (SELECT id FROM users WHERE telegram_id = {telegram_id});

-- Vedi alcuni vini
SELECT name, producer, quantity, selling_price 
FROM "{telegram_id}/{business_name} INVENTARIO"
WHERE user_id = (SELECT id FROM users WHERE telegram_id = {telegram_id})
LIMIT 10;
```

### **2. Verifica tramite Bot**

Il beta tester può usare `/inventario` nel bot per vedere i vini inseriti.

### **3. Verifica tramite Viewer**

Se il viewer è configurato, puoi vedere l'inventario su:
```
https://your-viewer.railway.app/view/{telegram_id}/{business_name}
```

---

## ⚠️ Note Importanti

### **Utente Non Esistente**

Se l'utente non esiste nel database:
- ✅ Lo script lo crea automaticamente
- ✅ Imposta `onboarding_completed = True`
- ✅ Crea le tabelle necessarie (`INVENTARIO`, `BACKUP`, `LOG`, `CONSUMI`)

### **Business Name Diverso**

Se l'utente esiste ma con `business_name` diverso:
- ✅ Lo script aggiorna il `business_name` automaticamente
- ⚠️ Le tabelle esistenti mantengono il vecchio nome
- ⚠️ Potrebbero esserci problemi se le tabelle hanno nomi diversi

**Soluzione**: Usa sempre lo stesso `business_name` per lo stesso utente.

### **Modalità REPLACE**

Quando usi `--replace`:
- ⚠️ **TUTTI** i vini esistenti vengono eliminati
- ⚠️ Non c'è backup automatico
- ✅ Poi vengono inseriti i nuovi vini dal CSV

**Raccomandazione**: Fai un backup prima di usare `--replace`.

---

## 🛠️ Troubleshooting

### **Errore: File non trovato**

```
❌ Errore: File non trovato: inventario.csv
```

**Soluzione**: Verifica il path del file. Usa path assoluto se necessario:
```bash
python admin_insert_inventory.py 123456789 "Ristorante XYZ" "C:/path/to/inventario.csv"
```

---

### **Errore: DATABASE_URL non configurata**

```
❌ Errore: database_url field required
```

**Soluzione**: Configura `DATABASE_URL` nel `.env` o come variabile ambiente:
```bash
export DATABASE_URL="postgresql://user:pass@host:port/db"
```

---

### **Errore: Riga saltata (Nome vuoto)**

```
Riga 5: Nome vuoto, saltata
```

**Soluzione**: Verifica che tutte le righe abbiano almeno il campo `Nome` compilato.

---

### **Errore: Quantità invalida**

```
Riga 3: Quantità invalida (abc), impostata a 0
```

**Soluzione**: Verifica che `Quantità` contenga solo numeri (può essere decimale con punto o virgola).

---

## 📝 Esempio Completo

### **Scenario**: Inserire inventario per "Ristorante La Pergola"

1. **Prepara CSV** (`inventario_la_pergola.csv`):
```csv
Nome,Produttore,Fornitore,Annata,Quantità,Prezzo,Costo,Tipologia,Uvaggio,Regione,Paese,Classificazione
Barolo DOCG,Giacomo Conterno,Importatore XYZ,2018,12,45.50,32.00,Rosso,Nebbiolo,Piemonte,Italia,DOCG
Chianti Classico,Fontodi,Distributore ABC,2019,24,28.00,18.50,Rosso,Sangiovese,Toscana,Italia,DOCG
```

2. **Ottieni Telegram ID** (es: `987654321`)

3. **Esegui script**:
```bash
cd gioia-processor
python admin_insert_inventory.py 987654321 "Ristorante La Pergola" inventario_la_pergola.csv
```

4. **Verifica**:
```bash
# Il beta tester può ora vedere l'inventario con /inventario nel bot
```

---

## 🔐 Sicurezza

- ⚠️ Questo script ha accesso diretto al database
- ⚠️ Usa solo per inserimenti manuali autorizzati
- ✅ Non esporre questo script pubblicamente
- ✅ Mantieni le credenziali database sicure

---

## 📞 Supporto

Se hai problemi:
1. Controlla i log dello script
2. Verifica che il CSV sia nel formato corretto
3. Verifica che `DATABASE_URL` sia configurata
4. Controlla che l'utente esista o possa essere creato

---

**Versione**: 1.0  
**Data**: 2025-01-XX  
**Script**: `admin_insert_inventory.py`

