# 📊 ANALISI IMPLEMENTAZIONE: Sistema Storico Vino + Migrazione Telegram → User ID

## 🎯 Obiettivi

1. **Risolvere problema stock finale impreciso**: Creare una **fonte unica di verità** per lo storico di ogni vino
2. **Migrazione da Telegram a User ID**: Abbandonare `telegram_id` come identificatore tabelle, usare `user_id` + `business_name`

---

## 📋 Situazione Attuale

### Struttura Database Attuale

**Problema 1: Stock finale impreciso**
- Le tabelle dinamiche usano formato: `"{telegram_id}/{business_name} INVENTARIO"`
- Lo stock viene calcolato dinamicamente sommando i movimenti
- Se ci sono errori o movimenti mancanti, lo stock è sbagliato (es. 6 invece di 21)

**Problema 2: Dipendenza da Telegram**
- Tutte le tabelle dinamiche sono identificate da `telegram_id`
- Utenti web-only non hanno `telegram_id` (è nullable)
- Sistema sta abbandonando Telegram in favore di email/password

**Tabelle attuali (4 per utente):**

1. **`{telegram_id}/{business_name} INVENTARIO`**
   - Contiene i vini con `quantity` (stock attuale)
   - Campi: `id`, `user_id`, `name`, `producer`, `quantity`, `vintage`, ecc.

2. **`{telegram_id}/{business_name} INVENTARIO backup`**
   - Backup dell'inventario

3. **`{telegram_id}/{business_name} LOG interazione`**
   - Log delle interazioni con il bot

4. **`{telegram_id}/{business_name} Consumi e rifornimenti`**
   - Contiene solo i movimenti (consumi/rifornimenti)
   - Campi: `id`, `user_id`, `wine_name`, `wine_producer`, `movement_type`, `quantity_change`, `quantity_before`, `quantity_after`, `movement_date`
   - **Non c'è una fonte unica di verità per lo stock di un vino**

### Flusso Attuale Movimenti

1. **POST `/process-movement`** (movements.py)
   - Riceve: `telegram_id`, `business_name`, `wine_name`, `movement_type`, `quantity`
   - Cerca il vino in `INVENTARIO`
   - Calcola `quantity_after = quantity_before ± quantity`
   - **UPDATE** `INVENTARIO.quantity`
   - **INSERT** in `Consumi e rifornimenti`

2. **GET `/api/viewer/movements?wine_name=...`** (da implementare)
   - Dovrebbe leggere da `Consumi e rifornimenti`
   - Calcola lo stock finale sommando i movimenti
   - **Problema**: se ci sono errori o movimenti mancanti, lo stock è sbagliato

---

## 🚀 Soluzione Proposta

### Nuova Architettura

#### 1. Migrazione Identificatori: Telegram ID → User ID

**Nuovo formato tabelle:**
```
"{user_id}/{business_name} INVENTARIO"
"{user_id}/{business_name} Storico vino"
```

**Vantaggi:**
- ✅ **User ID è sempre presente**: tutti gli utenti hanno `user_id` (PK)
- ✅ **User ID non cambia mai**: a differenza di email o telegram_id
- ✅ **Compatibile con utenti web-only**: non richiede telegram_id
- ✅ **Più semplice da gestire**: user_id è già FK in tutte le tabelle

#### 2. Nuova Tabella: **Storico Vino**

Per ogni utente, creare una **5ª tabella**:

```
"{user_id}/{business_name} Storico vino"
```

**Schema proposto:**

```sql
CREATE TABLE "{user_id}/{business_name} Storico vino" (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    
    -- Identificazione vino (chiave unica per vino)
    wine_name VARCHAR(200) NOT NULL,
    wine_producer VARCHAR(200),
    wine_vintage INTEGER,
    
    -- Stock attuale (fonte unica di verità)
    current_stock INTEGER NOT NULL DEFAULT 0,
    
    -- Storico completo (JSON array)
    -- Ogni elemento: {type: 'consumo'|'rifornimento', quantity: int, date: timestamp, notes: str}
    history JSONB NOT NULL DEFAULT '[]'::jsonb,
    
    -- Metadati
    first_movement_date TIMESTAMP,
    last_movement_date TIMESTAMP,
    total_consumi INTEGER DEFAULT 0,  -- Somma totale consumi
    total_rifornimenti INTEGER DEFAULT 0,  -- Somma totale rifornimenti
    
    -- Timestamps
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE(user_id, wine_name, wine_producer, wine_vintage)
);

-- Indici per performance
CREATE INDEX idx_{user_id}_storico_wine_name ON "{user_id}/{business_name} Storico vino" (wine_name);
CREATE INDEX idx_{user_id}_storico_wine_producer ON "{user_id}/{business_name} Storico vino" (wine_producer);
CREATE INDEX idx_{user_id}_storico_last_movement ON "{user_id}/{business_name} Storico vino" (last_movement_date);
CREATE INDEX idx_{user_id}_storico_history_gin ON "{user_id}/{business_name} Storico vino" USING GIN (history);
```

**Vantaggi:**
- ✅ **Fonte unica di verità**: `current_stock` è sempre corretto
- ✅ **Storico completo**: tutti i movimenti in un unico campo JSONB
- ✅ **Performance**: query diretta senza JOIN o aggregazioni
- ✅ **Scalabilità**: JSONB è efficiente per array di movimenti

---

## 🔧 Modifiche Dettagliate

### PARTE A: Migrazione Telegram ID → User ID

#### A.1. Modifica `get_user_table_name()`

**File**: `gioia-processor/core/database.py`

**PRIMA:**
```python
def get_user_table_name(telegram_id: int, business_name: str, table_type: str) -> str:
    table_name = f'"{telegram_id}/{business_name} {table_type}"'
    return table_name
```

**DOPO:**
```python
def get_user_table_name(user_id: int, business_name: str, table_type: str) -> str:
    """
    Genera nome tabella nel formato: "{user_id}/{business_name} {table_type}"
    
    Args:
        user_id: ID utente (PK da users.id)
        business_name: Nome del locale
        table_type: Tipo tabella ("INVENTARIO", "INVENTARIO backup", "LOG interazione", "Consumi e rifornimenti", "Storico vino")
    
    Returns:
        Nome tabella quotato per PostgreSQL
    """
    if not business_name:
        business_name = "Upload Manuale"
    
    table_name = f'"{user_id}/{business_name} {table_type}"'
    return table_name
```

#### A.2. Modifica `ensure_user_tables()`

**File**: `gioia-processor/core/database.py`

**PRIMA:**
```python
async def ensure_user_tables(session, telegram_id: int, business_name: str) -> dict:
    # Cerca/crea utente per telegram_id
    upsert_user = sql_text("""
        INSERT INTO users (telegram_id, business_name, ...)
        VALUES (:telegram_id, :business_name, ...)
        ON CONFLICT (telegram_id) ...
    """)
    result_user = await session.execute(upsert_user, {"telegram_id": telegram_id, ...})
    user_id = result_user.scalar_one()
    
    table_inventario = get_user_table_name(telegram_id, business_name, "INVENTARIO")
    # ...
```

**DOPO:**
```python
async def ensure_user_tables(session, user_id: int, business_name: str) -> dict:
    """
    Crea le 5 tabelle utente nello schema public se non esistono.
    
    Tabelle create:
    1. "{user_id}/{business_name} INVENTARIO" - Inventario vini
    2. "{user_id}/{business_name} INVENTARIO backup" - Backup inventario
    3. "{user_id}/{business_name} LOG interazione" - Log interazioni bot
    4. "{user_id}/{business_name} Consumi e rifornimenti" - Consumi e rifornimenti
    5. "{user_id}/{business_name} Storico vino" - Storico vini (NUOVO)
    
    Args:
        session: Sessione database
        user_id: ID utente (PK da users.id)
        business_name: Nome business
    
    Returns:
        Dict con nomi tabelle create.
    """
    if not business_name:
        business_name = "Upload Manuale"
    
    try:
        # Verifica che utente esista
        check_user = sql_text("SELECT id FROM users WHERE id = :user_id")
        result = await session.execute(check_user, {"user_id": user_id})
        if not result.scalar_one_or_none():
            raise ValueError(f"User {user_id} non trovato")
        
        # Nomi tabelle (usando user_id invece di telegram_id)
        table_inventario = get_user_table_name(user_id, business_name, "INVENTARIO")
        table_backup = get_user_table_name(user_id, business_name, "INVENTARIO backup")
        table_log = get_user_table_name(user_id, business_name, "LOG interazione")
        table_consumi = get_user_table_name(user_id, business_name, "Consumi e rifornimenti")
        table_storico = get_user_table_name(user_id, business_name, "Storico vino")  # ← NUOVO
        
        # Verifica se almeno una tabella esiste
        table_name_check = f"{user_id}/{business_name} INVENTARIO"
        check_table = sql_text("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' AND table_name = :table_name
        """)
        result = await session.execute(check_table, {"table_name": table_name_check})
        table_exists = result.scalar_one_or_none()
        
        if not table_exists:
            # Crea tutte le tabelle (inclusa "Storico vino")
            # ... (vedi sezione B.1 per dettagli)
        
        return {
            "inventario": table_inventario,
            "backup": table_backup,
            "log": table_log,
            "consumi": table_consumi,
            "storico": table_storico  # ← NUOVO
        }
```

**⚠️ IMPORTANTE**: Tutti i chiamanti di `ensure_user_tables()` devono passare `user_id` invece di `telegram_id`!

#### A.3. Script Migrazione Tabelle Esistenti

**File**: `gioia-processor/migrations/005_migrate_telegram_to_user_id.py`

**Strategia:**
1. Trova tutte le tabelle con formato `"{telegram_id}/{business_name} ..."`
2. Per ogni tabella:
   - Estrai `telegram_id` e `business_name` dal nome
   - Trova `user_id` corrispondente da `users.telegram_id`
   - Rinomina tabella a `"{user_id}/{business_name} ..."`
3. Aggiorna tutti gli indici

**Codice:**

```python
"""
Migrazione: rinomina tabelle da formato telegram_id a user_id
"""
import asyncio
import re
import logging
from sqlalchemy import text as sql_text, select
from core.database import get_db, User

logger = logging.getLogger(__name__)

async def migrate_tables_telegram_to_user_id():
    """
    Rinomina tutte le tabelle da "{telegram_id}/{business_name} ..." a "{user_id}/{business_name} ..."
    """
    async for db in get_db():
        # Trova tutte le tabelle che iniziano con un numero (telegram_id)
        query_tables = sql_text("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
            AND table_name ~ '^"[0-9]+/'
            ORDER BY table_name
        """)
        
        result = await db.execute(query_tables)
        tables = result.fetchall()
        
        logger.info(f"[MIGRATION] Trovate {len(tables)} tabelle da migrare")
        
        # Pattern per estrarre telegram_id e business_name
        pattern = re.compile(r'^"(\d+)/([^"]+)\s+(.+)"$')
        
        migrated_count = 0
        error_count = 0
        
        for (table_name,) in tables:
            try:
                # Estrai telegram_id, business_name, table_type
                match = pattern.match(table_name)
                if not match:
                    logger.warning(f"[MIGRATION] Nome tabella non valido: {table_name}")
                    continue
                
                telegram_id_str, business_name, table_type = match.groups()
                telegram_id = int(telegram_id_str)
                
                # Trova user_id corrispondente
                stmt = select(User).where(User.telegram_id == telegram_id)
                result = await db.execute(stmt)
                user = result.scalar_one_or_none()
                
                if not user:
                    logger.warning(f"[MIGRATION] Utente telegram_id={telegram_id} non trovato per tabella {table_name}")
                    error_count += 1
                    continue
                
                user_id = user.id
                
                # Nuovo nome tabella
                new_table_name = f'"{user_id}/{business_name} {table_type}"'
                
                # Verifica se nuova tabella esiste già
                check_new = sql_text("""
                    SELECT table_name 
                    FROM information_schema.tables 
                    WHERE table_schema = 'public' AND table_name = :table_name
                """)
                result = await db.execute(check_new, {"table_name": new_table_name})
                if result.scalar_one_or_none():
                    logger.warning(f"[MIGRATION] Tabella {new_table_name} esiste già, skip {table_name}")
                    continue
                
                # Rinomina tabella
                rename_table = sql_text(f'ALTER TABLE {table_name} RENAME TO {new_table_name}')
                await db.execute(rename_table)
                
                # Rinomina indici (se esistono)
                query_indexes = sql_text("""
                    SELECT indexname
                    FROM pg_indexes
                    WHERE schemaname = 'public'
                    AND tablename = :old_table_name
                """)
                result = await db.execute(query_indexes, {"old_table_name": table_name.strip('"')})
                indexes = result.fetchall()
                
                for (index_name,) in indexes:
                    # Sostituisci telegram_id con user_id nel nome indice
                    new_index_name = index_name.replace(f"_{telegram_id}_", f"_{user_id}_")
                    rename_index = sql_text(f'ALTER INDEX "{index_name}" RENAME TO "{new_index_name}"')
                    await db.execute(rename_index)
                
                await db.commit()
                migrated_count += 1
                logger.info(f"[MIGRATION] Migrata: {table_name} → {new_table_name}")
                
            except Exception as e:
                await db.rollback()
                logger.error(f"[MIGRATION] Errore migrazione tabella {table_name}: {e}", exc_info=True)
                error_count += 1
                continue
        
        logger.info(
            f"[MIGRATION] Migrazione completata: {migrated_count} tabelle migrate, "
            f"{error_count} errori"
        )

if __name__ == "__main__":
    asyncio.run(migrate_tables_telegram_to_user_id())
```

---

### PARTE B: Sistema Storico Vino

#### B.1. Creazione Tabella Storico (ensure_user_tables)

**File**: `gioia-processor/core/database.py`

**Aggiungi dopo la creazione di "Consumi e rifornimenti":**

```python
# Crea tabella Storico vino
create_storico = sql_text(f"""
    CREATE TABLE IF NOT EXISTS {table_storico} (
        id SERIAL PRIMARY KEY,
        user_id INTEGER NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
        wine_name VARCHAR(200) NOT NULL,
        wine_producer VARCHAR(200),
        wine_vintage INTEGER,
        current_stock INTEGER NOT NULL DEFAULT 0,
        history JSONB NOT NULL DEFAULT '[]'::jsonb,
        first_movement_date TIMESTAMP,
        last_movement_date TIMESTAMP,
        total_consumi INTEGER DEFAULT 0,
        total_rifornimenti INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(user_id, wine_name, wine_producer, wine_vintage)
    )
""")
await session.execute(create_storico)

# Indici
indexes_storico = [
    f"CREATE INDEX IF NOT EXISTS idx_{user_id}_storico_wine_name ON {table_storico} (wine_name)",
    f"CREATE INDEX IF NOT EXISTS idx_{user_id}_storico_wine_producer ON {table_storico} (wine_producer)",
    f"CREATE INDEX IF NOT EXISTS idx_{user_id}_storico_last_movement ON {table_storico} (last_movement_date)",
    f"CREATE INDEX IF NOT EXISTS idx_{user_id}_storico_history_gin ON {table_storico} USING GIN (history)"
]
for index_sql in indexes_storico:
    await session.execute(sql_text(index_sql))
```

#### B.2. Processamento Movimento (process_movement_background)

**File**: `gioia-processor/api/routers/movements.py`

**Modifiche necessarie:**

1. **Cambiare signature** per accettare `user_id` invece di `telegram_id`:
```python
async def process_movement_background(
    job_id: str,
    user_id: int,  # ← CAMBIATO da telegram_id
    business_name: str,
    wine_name: str,
    movement_type: str,
    quantity: int
):
```

2. **Cercare utente per user_id**:
```python
stmt = select(User).where(User.id == user_id)
result = await db.execute(stmt)
user = result.scalar_one_or_none()
```

3. **Chiamare ensure_user_tables con user_id**:
```python
user_tables = await ensure_user_tables(db, user_id, business_name)  # ← user_id invece di telegram_id
```

4. **Aggiungere aggiornamento "Storico vino"** (dopo UPDATE INVENTARIO):
```python
# 1. Aggiorna/crea riga in "Storico vino"
table_storico = user_tables["storico"]

# Cerca se esiste già una riga per questo vino
search_storico = sql_text(f"""
    SELECT id, current_stock, history, total_consumi, total_rifornimenti
    FROM {table_storico}
    WHERE user_id = :user_id
    AND wine_name = :wine_name
    AND (wine_producer = :wine_producer OR (wine_producer IS NULL AND :wine_producer IS NULL))
    FOR UPDATE
    LIMIT 1
""")
result_storico = await db.execute(search_storico, {
    "user_id": user.id,
    "wine_name": wine_name_db,
    "wine_producer": wine_producer
})
storico_row = result_storico.fetchone()

movement_date = datetime.utcnow()
movement_entry = {
    "type": movement_type,
    "quantity": quantity,
    "date": movement_date.isoformat(),
    "quantity_before": quantity_before,
    "quantity_after": quantity_after
}

if storico_row:
    # Aggiorna riga esistente
    existing_history = storico_row[2] or []  # history
    existing_history.append(movement_entry)
    
    new_total_consumi = storico_row[3] or 0
    new_total_rifornimenti = storico_row[4] or 0
    
    if movement_type == 'consumo':
        new_total_consumi += quantity
    else:
        new_total_rifornimenti += quantity
    
    update_storico = sql_text(f"""
        UPDATE {table_storico}
        SET current_stock = :current_stock,
            history = :history::jsonb,
            total_consumi = :total_consumi,
            total_rifornimenti = :total_rifornimenti,
            last_movement_date = :movement_date,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = :storico_id
    """)
    await db.execute(update_storico, {
        "current_stock": quantity_after,
        "history": json.dumps(existing_history),
        "total_consumi": new_total_consumi,
        "total_rifornimenti": new_total_rifornimenti,
        "movement_date": movement_date,
        "storico_id": storico_row[0]
    })
else:
    # Crea nuova riga
    history = [movement_entry]
    
    insert_storico = sql_text(f"""
        INSERT INTO {table_storico}
            (user_id, wine_name, wine_producer, wine_vintage, current_stock, history,
             first_movement_date, last_movement_date, total_consumi, total_rifornimenti)
        VALUES (:user_id, :wine_name, :wine_producer, :wine_vintage, :current_stock, :history::jsonb,
                :movement_date, :movement_date, :total_consumi, :total_rifornimenti)
    """)
    await db.execute(insert_storico, {
        "user_id": user.id,
        "wine_name": wine_name_db,
        "wine_producer": wine_producer,
        "wine_vintage": None,  # TODO: estrai da INVENTARIO se disponibile
        "current_stock": quantity_after,
        "history": json.dumps(history),
        "movement_date": movement_date,
        "total_consumi": quantity if movement_type == 'consumo' else 0,
        "total_rifornimenti": quantity if movement_type == 'rifornimento' else 0
    })
```

#### B.3. Nuovo Endpoint: GET `/api/viewer/movements`

**File**: `gioia-processor/api/routers/snapshot.py`

**Aggiungi endpoint:**

```python
@router.get("/viewer/movements")
async def get_wine_movements_endpoint(
    wine_name: str = Query(...),
    user_id: int = Query(...)  # ← CAMBIATO da telegram_id
):
    """
    Restituisce movimenti e stock per un vino specifico.
    Legge da "Storico vino" (fonte unica di verità).
    """
    try:
        async for db in get_db():
            # Verifica utente
            stmt = select(User).where(User.id == user_id)  # ← user_id invece di telegram_id
            result = await db.execute(stmt)
            user = result.scalar_one_or_none()
            
            if not user:
                raise HTTPException(status_code=404, detail="Utente non trovato")
            
            if not user.business_name:
                raise HTTPException(status_code=400, detail="Utente senza business_name")
            
            # Assicura tabelle esistano
            user_tables = await ensure_user_tables(db, user_id, user.business_name)  # ← user_id
            table_storico = user_tables["storico"]
            
            # Cerca storico vino
            query_storico = sql_text(f"""
                SELECT 
                    current_stock,
                    history,
                    first_movement_date,
                    last_movement_date,
                    total_consumi,
                    total_rifornimenti
                FROM {table_storico}
                WHERE user_id = :user_id
                AND wine_name = :wine_name
                LIMIT 1
            """)
            
            result = await db.execute(query_storico, {
                "user_id": user_id,
                "wine_name": wine_name
            })
            storico_row = result.fetchone()
            
            if not storico_row:
                # Nessun movimento per questo vino
                return {
                    "wine_name": wine_name,
                    "current_stock": 0,
                    "opening_stock": 0,
                    "movements": []
                }
            
            # Estrai history (JSONB)
            history = storico_row[1] or []
            
            # Converti history in formato per frontend
            movements = []
            for entry in history:
                movements.append({
                    "at": entry["date"],
                    "type": entry["type"],
                    "quantity_change": entry["quantity"] if entry["type"] == "rifornimento" else -entry["quantity"],
                    "quantity_before": entry["quantity_before"],
                    "quantity_after": entry["quantity_after"]
                })
            
            # Ordina per data
            movements.sort(key=lambda x: x["at"])
            
            # Stock finale = current_stock dalla tabella (fonte unica di verità)
            current_stock = storico_row[0]
            
            # Opening stock = primo movimento quantity_before (o 0 se non c'è)
            opening_stock = movements[0]["quantity_before"] if movements else 0
            
            return {
                "wine_name": wine_name,
                "current_stock": current_stock,
                "opening_stock": opening_stock,
                "movements": movements,
                "total_consumi": storico_row[4] or 0,
                "total_rifornimenti": storico_row[5] or 0,
                "first_movement_date": storico_row[2].isoformat() if storico_row[2] else None,
                "last_movement_date": storico_row[3].isoformat() if storico_row[3] else None
            }
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[VIEWER_MOVEMENTS] Errore: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Errore interno: {str(e)}")
```

#### B.4. Migrazione Dati Storico Vino

**File**: `gioia-processor/migrations/004_migrate_wine_history.py`

**Strategia:**
1. Per ogni utente esistente
2. Leggi tutti i movimenti da `Consumi e rifornimenti` (già migrata a formato user_id)
3. Raggruppa per `wine_name` + `wine_producer`
4. Per ogni vino:
   - Calcola `current_stock` dall'ultimo movimento (`quantity_after`)
   - Costruisci `history` JSONB da tutti i movimenti
   - Calcola `total_consumi` e `total_rifornimenti`
   - INSERT/UPDATE in `Storico vino`

**Codice:** (vedi documento originale, sezione 3)

---

### PARTE C: Aggiornamento Web App

#### C.1. Modifiche Backend Web App

**File da modificare:**

1. **`gioia-web-app/backend/app/core/database.py`**
   - `get_user_wines()`: usa `user_id` invece di `telegram_id`
   - `get_wine_by_id()`: usa `user_id` invece di `telegram_id`
   - `search_wines()`: usa `user_id` invece di `telegram_id`
   - `check_user_has_dynamic_tables()`: cerca tabelle con formato `user_id` invece di `telegram_id`
   - `log_chat_message()`: usa `user_id` invece di `telegram_id`

2. **`gioia-web-app/backend/app/core/processor_client.py`**
   - `create_tables()`: passa `user_id` invece di `telegram_id`
   - `process_inventory()`: passa `user_id` invece di `telegram_id`
   - `process_movement()`: passa `user_id` invece di `telegram_id`
   - `update_wine_field()`: passa `user_id` invece di `telegram_id`
   - `add_wine()`: passa `user_id` invece di `telegram_id`

3. **`gioia-web-app/backend/app/api/wines.py`**
   - Tutti gli endpoint: usa `user.id` invece di `user.telegram_id`
   - Rimuovi controlli `if not telegram_id`

4. **`gioia-web-app/backend/app/api/viewer.py`**
   - `get_viewer_snapshot()`: usa `user.id` invece di `user.telegram_id`
   - `get_viewer_export_csv()`: usa `user.id` invece di `user.telegram_id`
   - `get_wine_movements()`: usa `user.id` invece di `user.telegram_id`
   - Chiama endpoint processor con `user_id` invece di `telegram_id`

5. **`gioia-web-app/backend/app/services/ai_service.py`**
   - Tutti i metodi: usa `user_id` invece di `telegram_id`
   - Costruisci nomi tabelle con `user_id` invece di `telegram_id`

6. **`gioia-web-app/backend/app/core/auth.py`**
   - `create_viewer_token()`: include `user_id` invece di `telegram_id`
   - `validate_viewer_token()`: valida `user_id` invece di `telegram_id`

#### C.2. Modifiche Frontend Web App

**File da modificare:**

1. **`gioia-web-app/frontend/app.js`**
   - `loadAndRenderMovementsChart()`: passa `user_id` invece di `telegram_id` alla chiamata API
   - Rimuovi tutti i riferimenti a `telegram_id` nelle chiamate API

2. **`gioia-web-app/frontend/features/chat/mobile/ChatMobile.js`**
   - Usa `user_id` invece di `telegram_id` nelle chiamate API

---

## 📝 Checklist Implementazione Completa

### Fase 1: Migrazione Telegram ID → User ID (PROCESSOR)

- [ ] Modificare `get_user_table_name()` per usare `user_id`
- [ ] Modificare `ensure_user_tables()` per accettare `user_id`
- [ ] Aggiornare tutti i chiamanti di `ensure_user_tables()` nel processor
- [ ] Creare script migrazione `005_migrate_telegram_to_user_id.py`
- [ ] Testare migrazione su database di sviluppo
- [ ] Eseguire migrazione su produzione

### Fase 2: Sistema Storico Vino (PROCESSOR)

- [ ] Aggiungere creazione tabella "Storico vino" in `ensure_user_tables()`
- [ ] Modificare `process_movement_background()` per aggiornare "Storico vino"
- [ ] Creare endpoint `GET /api/viewer/movements`
- [ ] Testare con movimenti reali

### Fase 3: Migrazione Dati Storico (PROCESSOR)

- [ ] Creare script `004_migrate_wine_history.py`
- [ ] Testare su database di sviluppo
- [ ] Eseguire su produzione

### Fase 4: Aggiornamento Web App Backend

- [ ] Modificare `database.py` per usare `user_id`
- [ ] Modificare `processor_client.py` per passare `user_id`
- [ ] Modificare `wines.py` per usare `user.id`
- [ ] Modificare `viewer.py` per usare `user.id`
- [ ] Modificare `ai_service.py` per usare `user_id`
- [ ] Modificare `auth.py` per includere `user_id` nel token
- [ ] Testare tutti gli endpoint

### Fase 5: Aggiornamento Web App Frontend

- [ ] Modificare `app.js` per passare `user_id` invece di `telegram_id`
- [ ] Modificare `ChatMobile.js` se necessario
- [ ] Testare grafico movimenti
- [ ] Testare tutte le funzionalità

### Fase 6: Testing Completo

- [ ] Testare nuovo movimento crea/aggiorna storico
- [ ] Testare endpoint restituisce stock corretto
- [ ] Verificare che frontend mostri stock corretto (21 invece di 6)
- [ ] Testare utenti web-only (senza telegram_id)
- [ ] Testare migrazione tabelle esistenti

---

## ⚠️ Considerazioni

### Compatibilità
- **Mantieni** tabella "Consumi e rifornimenti" per compatibilità
- **Non rimuovere** logica esistente finché non verificato che tutto funziona
- **Supporta entrambi i formati** durante periodo di transizione (se necessario)

### Rollback
- Se qualcosa va storto, le tabelle vecchie possono essere ripristinate
- Possibile ricostruire "Storico vino" ri-eseguendo la migrazione

### Performance
- **JSONB** è efficiente per array di movimenti (fino a migliaia)
- **Indice GIN** su `history` per query complesse (se necessario in futuro)
- **Indici** su `wine_name`, `wine_producer`, `last_movement_date`

### Scalabilità
- Se un vino ha **migliaia di movimenti**, considerare:
  - Archiviazione movimenti vecchi (> 1 anno) in tabella separata
  - Mantenere solo ultimi N movimenti in `history`

---

## 🎯 Risultato Atteso

Dopo l'implementazione:

1. ✅ **Stock finale sempre corretto**: `current_stock` in "Storico vino" è la fonte unica di verità
2. ✅ **Query veloci**: nessun calcolo dinamico, solo SELECT diretto
3. ✅ **Storico completo**: tutti i movimenti in un unico posto
4. ✅ **Frontend mostra stock corretto**: 21 invece di 6
5. ✅ **Sistema indipendente da Telegram**: usa `user_id` invece di `telegram_id`
6. ✅ **Supporto utenti web-only**: non richiede `telegram_id`

---

## 📅 Timeline Stimata

- **Fase 1**: 3-4 ore (migrazione telegram_id → user_id)
- **Fase 2**: 2-3 ore (sistema storico vino)
- **Fase 3**: 2-3 ore (migrazione dati storico)
- **Fase 4**: 4-5 ore (web app backend)
- **Fase 5**: 2-3 ore (web app frontend)
- **Fase 6**: 2-3 ore (testing completo)

**Totale**: ~15-21 ore

---

## 🔗 File da Modificare (RIEPILOGO)

### Processor (gioia-processor)

1. `core/database.py` - `get_user_table_name()`, `ensure_user_tables()`
2. `api/routers/movements.py` - `process_movement_background()`
3. `api/routers/snapshot.py` - nuovo endpoint `/api/viewer/movements`
4. `api/routers/ingest.py` - aggiornare chiamate a `ensure_user_tables()`
5. `api/routers/admin.py` - aggiornare chiamate a `ensure_user_tables()`
6. `api/routers/diagnostics.py` - aggiornare chiamate a `ensure_user_tables()`
7. `viewer_generator.py` - aggiornare chiamate a `ensure_user_tables()`
8. `core/scheduler.py` - aggiornare chiamate a `ensure_user_tables()`
9. `migrations/004_migrate_wine_history.py` - nuovo file
10. `migrations/005_migrate_telegram_to_user_id.py` - nuovo file

### Web App Backend (gioia-web-app/backend)

1. `app/core/database.py` - tutti i metodi che usano `telegram_id`
2. `app/core/processor_client.py` - tutti i metodi che passano `telegram_id`
3. `app/api/wines.py` - tutti gli endpoint
4. `app/api/viewer.py` - tutti gli endpoint
5. `app/services/ai_service.py` - tutti i metodi
6. `app/core/auth.py` - `create_viewer_token()`, `validate_viewer_token()`

### Web App Frontend (gioia-web-app/frontend)

1. `app.js` - `loadAndRenderMovementsChart()` e altre chiamate API
2. `features/chat/mobile/ChatMobile.js` - se usa `telegram_id`

---

**Fine Analisi** ✅
