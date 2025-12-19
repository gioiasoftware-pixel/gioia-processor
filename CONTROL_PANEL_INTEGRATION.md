# 🔗 Integrazione Control Panel - Processor

## Panoramica

Il **Gioia Processor** è già completamente integrato e pronto per supportare il **Control Panel Admin**. Tutti gli endpoint necessari sono disponibili e funzionanti.

## Endpoint Disponibili per Control Panel

### 1. Creazione Tabelle Utente
**Endpoint**: `POST /create-tables`

Crea le 5 tabelle dinamiche per un utente:
- `{user_id}/{business_name} INVENTARIO`
- `{user_id}/{business_name} INVENTARIO backup`
- `{user_id}/{business_name} LOG interazione`
- `{user_id}/{business_name} Consumi e rifornimenti`
- `{user_id}/{business_name} Storico vino`

**Parametri**:
- `user_id` (int): ID utente
- `business_name` (string): Nome business

**Esempio**:
```bash
curl -X POST https://processor-url/create-tables \
  -F "user_id=123" \
  -F "business_name=My Restaurant"
```

### 2. Processamento Inventario
**Endpoint**: `POST /process-inventory`

Elabora file inventario (CSV, Excel, immagini, PDF) e popola le tabelle dinamiche.

**Parametri**:
- `user_id` (int): ID utente
- `business_name` (string): Nome business
- `file` (file): File inventario
- `file_type` (string): Tipo file (csv, excel, xlsx, image, pdf)
- `mode` (string): "add" o "replace"

### 3. Stato Job
**Endpoint**: `GET /status/{job_id}`

Ottiene lo stato di un job di elaborazione.

### 4. Admin Endpoints

#### Inserimento Inventario Pulito
**Endpoint**: `POST /admin/insert-inventory`

Inserisce inventario già pulito direttamente nel database (bypass pipeline).

#### Aggiornamento Campo Vino
**Endpoint**: `POST /admin/update-wine-field`

Aggiorna un singolo campo di un vino.

#### Aggiornamento Quantità con Movimento
**Endpoint**: `POST /admin/update-wine-field-with-movement`

Aggiorna quantità creando automaticamente un movimento nel log.

#### Aggiunta Vino
**Endpoint**: `POST /admin/add-wine`

Aggiunge un nuovo vino all'inventario.

## Integrazione con Web App Backend

Il Control Panel non chiama direttamente Processor, ma usa il backend Web App che agisce da proxy:

1. **Control Panel** → **Web App Backend** (`/api/admin/users`) → **Processor** (`/create-tables` o `/process-inventory`)
2. Il backend Web App gestisce autenticazione admin e chiama Processor con i parametri corretti
3. Processor crea le tabelle dinamiche nel database condiviso

## Database Condiviso

Tutte le tabelle dinamiche vengono create nello stesso database PostgreSQL condiviso tra:
- **Processor**: Crea e gestisce tabelle dinamiche
- **Web App**: Query e modifica dati utente
- **Control Panel**: Visualizza e gestisce dati tramite Web App backend

## Funzioni Core

### `ensure_user_tables(session, user_id, business_name)`

Funzione principale che crea le 5 tabelle dinamiche se non esistono già.

**Location**: `core/database.py`

**Uso**:
```python
from core.database import ensure_user_tables

async for db in get_db():
    user_tables = await ensure_user_tables(db, user_id, business_name)
    # Restituisce dict con nomi tabelle create
```

## Note Importanti

1. **User ID**: Processor usa `user_id` (non `telegram_id`) per creare tabelle dinamiche
2. **Business Name**: Obbligatorio per creare tabelle con nome corretto
3. **Tabelle Esistenti**: Se le tabelle esistono già, `ensure_user_tables()` non le ricrea
4. **Database Condiviso**: Tutti i servizi condividono lo stesso database PostgreSQL

## Verifica Integrazione

Per verificare che Processor sia pronto per il Control Panel:

```bash
# Health check
curl https://processor-url/health

# Verifica endpoint create-tables
curl -X POST https://processor-url/create-tables \
  -F "user_id=1" \
  -F "business_name=Test"
```

## Supporto Control Panel

✅ **Pronto**: Processor supporta completamente il Control Panel Admin
✅ **Endpoint Disponibili**: Tutti gli endpoint necessari sono implementati
✅ **Database**: Tabelle dinamiche create correttamente con formato `{user_id}/{business_name} {table_type}`
✅ **Integrazione**: Backend Web App già configurato per chiamare Processor

---

**Data**: 2025-01-XX  
**Versione Processor**: 2.0.0  
**Status**: ✅ Pronto per Control Panel
