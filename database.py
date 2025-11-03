from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, ForeignKey, Text, Boolean, event
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy import text as sql_text
from datetime import datetime
import os
import logging
import re

logger = logging.getLogger(__name__)

# Base per i modelli
Base = declarative_base()

class User(Base):
    """Modello per gli utenti del bot"""
    __tablename__ = 'users'
    
    id = Column(Integer, primary_key=True)
    telegram_id = Column(Integer, unique=True, nullable=False, index=True)
    username = Column(String(100))
    first_name = Column(String(100))
    last_name = Column(String(100))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Dati onboarding
    business_name = Column(String(200))
    business_type = Column(String(100))  # enoteca, ristorante, bar, etc.
    location = Column(String(200))
    phone = Column(String(50))
    email = Column(String(200))
    onboarding_completed = Column(Boolean, default=False)
    
    # Relazioni rimosse - i vini sono ora in tabelle dinamiche nello schema public

# NOTA: I modelli Wine, InventoryBackup, InventoryLog NON sono più modelli Base
# Vengono create dinamicamente nello schema public usando SQL diretto in ensure_user_tables()
# 
# Le tabelle vengono create con nomi dinamici:
# "{telegram_id}/{business_name} INVENTARIO"
# "{telegram_id}/{business_name} INVENTARIO backup"
# "{telegram_id}/{business_name} LOG interazione"
# "{telegram_id}/{business_name} Consumi e rifornimenti"
# con foreign key verso public.users(id)

class ProcessingJob(Base):
    """Job di elaborazione inventario asincrono"""
    __tablename__ = 'processing_jobs'
    
    id = Column(Integer, primary_key=True)
    job_id = Column(String(50), unique=True, nullable=False, index=True)  # UUID o ID univoco
    
    # Dati utente
    telegram_id = Column(Integer, nullable=False, index=True)
    business_name = Column(String(200))
    
    # Stato elaborazione
    status = Column(String(20), nullable=False, default='pending')  # pending, processing, completed, error
    file_type = Column(String(20))  # csv, excel, image
    file_name = Column(String(200))
    file_size_bytes = Column(Integer)
    
    # Progress
    total_wines = Column(Integer, default=0)
    processed_wines = Column(Integer, default=0)
    saved_wines = Column(Integer, default=0)
    error_count = Column(Integer, default=0)
    
    # Risultati (JSON)
    result_data = Column(Text)  # JSON con risultato completo
    error_message = Column(Text)
    
    # Idempotenza
    client_msg_id = Column(String(100), nullable=True, index=True)  # ID messaggio client per idempotenza
    update_id = Column(Integer, nullable=True)  # Telegram update.id
    
    # Metadati
    created_at = Column(DateTime, default=datetime.utcnow)
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    processing_method = Column(String(50))  # csv_ai_enhanced, excel_ai_enhanced, ocr_ai_enhanced

# Configurazione database
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/gioia_processor")

# Engine asincrono per PostgreSQL con pool prudente
engine = create_async_engine(
    DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://"),
    pool_size=int(os.getenv("DB_POOL_SIZE", "10")),  # Pool size configurabile
    max_overflow=0,  # IMPORTANTE: evita superare max_connections
    pool_pre_ping=True,  # Auto-reconnect
    echo=False
)

# Session factory asincrona
AsyncSessionLocal = sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False
)

async def get_db():
    """Dependency per ottenere sessione database"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()

async def migrate_consumi_table_if_needed(session, table_name: str):
    """
    Migra tabella 'Consumi e rifornimenti' dalla vecchia alla nuova struttura se necessario.
    
    Vecchia struttura: wine_name, wine_producer, movement_type, quantity_change, 
                       quantity_before, quantity_after, notes, movement_date
    Nuova struttura: data, Prodotto, prodotto_rifornito, prodotto_consumato
    """
    try:
        from sqlalchemy import text as sql_text
        
        # Verifica se ha colonna vecchia (movement_type) o nuova (prodotto_rifornito)
        check_columns = sql_text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_schema = 'public' 
            AND table_name = :table_name
            AND column_name IN ('movement_type', 'prodotto_rifornito')
        """)
        result = await session.execute(check_columns, {"table_name": table_name.replace('"', '')})
        columns_found = [row[0] for row in result.fetchall()]
        
        # Se ha movement_type ma non prodotto_rifornito, è vecchia struttura - migra
        if 'movement_type' in columns_found and 'prodotto_rifornito' not in columns_found:
            logger.info(f"Migrating table {table_name} from old to new structure")
            
            # Backup dati vecchi se esistono (opzionale - solo per sicurezza)
            # Qui possiamo decidere se perdere i dati vecchi o convertirli
            # Per ora: cancella e ricrea (i dati vecchi non sono compatibili con nuova struttura)
            
            # Cancella tabella vecchia e ricrea con nuova struttura
            drop_table = sql_text(f'DROP TABLE IF EXISTS {table_name} CASCADE')
            await session.execute(drop_table)
            
            # Ricrea con nuova struttura
            create_consumi = sql_text(f"""
                CREATE TABLE {table_name} (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
                    data TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
                    Prodotto VARCHAR(200) NOT NULL,
                    prodotto_rifornito INTEGER DEFAULT NULL,
                    prodotto_consumato INTEGER DEFAULT NULL
                )
            """)
            await session.execute(create_consumi)
            await session.commit()
            
            logger.info(f"Table {table_name} migrated successfully")
        
    except Exception as e:
        logger.error(f"Error migrating table {table_name}: {e}")
        # Non bloccare l'esecuzione se la migrazione fallisce

def get_user_table_name(telegram_id: int, business_name: str, table_type: str) -> str:
    """
    Genera nome tabella nel formato: "{telegram_id}/{business_name} {table_type}"
    
    Args:
        telegram_id: ID Telegram dell'utente
        business_name: Nome del locale
        table_type: Tipo tabella ("INVENTARIO", "INVENTARIO backup", "LOG interazione", "Consumi e rifornimenti")
    
    Returns:
        Nome tabella quotato per PostgreSQL (es. "927230913/Upload Manuale INVENTARIO")
    """
    if not business_name:
        business_name = "Upload Manuale"
    
    table_name = f'"{telegram_id}/{business_name} {table_type}"'
    return table_name

async def ensure_user_tables(session, telegram_id: int, business_name: str) -> dict:
    """
    Crea le 4 tabelle utente nello schema public se non esistono.
    
    Tabelle create:
    1. "{telegram_id}/{business_name} INVENTARIO" - Inventario vini
    2. "{telegram_id}/{business_name} INVENTARIO backup" - Backup inventario
    3. "{telegram_id}/{business_name} LOG interazione" - Log interazioni bot
    4. "{telegram_id}/{business_name} Consumi e rifornimenti" - Consumi e rifornimenti
    
    Ritorna dict con nomi tabelle create.
    """
    if not business_name:
        business_name = "Upload Manuale"
    
    try:
        # Nomi tabelle
        table_inventario = get_user_table_name(telegram_id, business_name, "INVENTARIO")
        table_backup = get_user_table_name(telegram_id, business_name, "INVENTARIO backup")
        table_log = get_user_table_name(telegram_id, business_name, "LOG interazione")
        table_consumi = get_user_table_name(telegram_id, business_name, "Consumi e rifornimenti")
        
        # Verifica se almeno una tabella esiste (controlla INVENTARIO come riferimento)
        # PostgreSQL usa il nome tabella senza virgolette per il check in information_schema
        table_name_check = f"{telegram_id}/{business_name} INVENTARIO"
        check_table = sql_text("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' AND table_name = :table_name
        """)
        result = await session.execute(check_table, {"table_name": table_name_check})
        table_exists = result.scalar_one_or_none()
        
        if not table_exists:
            # Crea tabella INVENTARIO
            create_inventario = sql_text(f"""
                CREATE TABLE IF NOT EXISTS {table_inventario} (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
                    name VARCHAR(200) NOT NULL,
                    producer VARCHAR(200),
                    vintage INTEGER,
                    grape_variety VARCHAR(200),
                    region VARCHAR(200),
                    country VARCHAR(100),
                    wine_type VARCHAR(50),
                    classification VARCHAR(100),
                    quantity INTEGER DEFAULT 0,
                    min_quantity INTEGER DEFAULT 0,
                    cost_price FLOAT,
                    selling_price FLOAT,
                    alcohol_content FLOAT,
                    description TEXT,
                    notes TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            await session.execute(create_inventario)
            
            # Crea tabella INVENTARIO backup
            create_backup = sql_text(f"""
                CREATE TABLE IF NOT EXISTS {table_backup} (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
                    backup_name VARCHAR(200) NOT NULL,
                    backup_data TEXT NOT NULL,
                    backup_type VARCHAR(20) DEFAULT 'initial',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            await session.execute(create_backup)
            
            # Crea tabella LOG interazione
            create_log = sql_text(f"""
                CREATE TABLE IF NOT EXISTS {table_log} (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
                    interaction_type VARCHAR(50) NOT NULL,
                    interaction_data TEXT,
                    notes TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            await session.execute(create_log)
            
            # Crea tabella Consumi e rifornimenti
            # Struttura nuova: data, Prodotto, prodotto_rifornito, prodotto_consumato
            create_consumi = sql_text(f"""
                CREATE TABLE IF NOT EXISTS {table_consumi} (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
                    data TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
                    Prodotto VARCHAR(200) NOT NULL,
                    prodotto_rifornito INTEGER DEFAULT NULL,
                    prodotto_consumato INTEGER DEFAULT NULL
                )
            """)
            await session.execute(create_consumi)
            
            await session.commit()
            logger.info(f"Created tables for {telegram_id}/{business_name}: INVENTARIO, INVENTARIO backup, LOG interazione, Consumi e rifornimenti")
        else:
            # Tabella esiste già - verifica se ha struttura vecchia e migra
            await migrate_consumi_table_if_needed(session, table_consumi)
            logger.info(f"Tables already exist for {telegram_id}/{business_name}, migration checked if needed")
        
        return {
            "inventario": table_inventario,
            "backup": table_backup,
            "log": table_log,
            "consumi": table_consumi
        }
        
    except Exception as e:
        logger.error(f"Error ensuring user tables for {telegram_id}/{business_name}: {e}")
        raise

async def create_tables():
    """
    Crea solo tabelle condivise nello schema public: User e ProcessingJob.
    Wine, InventoryBackup, InventoryLog vengono creati dinamicamente negli schemi utente.
    """
    try:
        # Crea solo User e ProcessingJob nello schema public
        # I modelli Wine, InventoryBackup, InventoryLog sono stati rimossi dalla Base
        # quindi non verranno creati qui
        async with engine.begin() as conn:
            # Crea solo le tabelle dei modelli Base esistenti (User e ProcessingJob)
            await conn.run_sync(Base.metadata.create_all)

        # Allinea schema di sistema (idempotente): colonne e indici mancanti, tabelle service
        async with AsyncSessionLocal() as session:
            try:
                # Idempotenza su processing_jobs
                await session.execute(sql_text("""
                    ALTER TABLE processing_jobs
                      ADD COLUMN IF NOT EXISTS client_msg_id VARCHAR(100),
                      ADD COLUMN IF NOT EXISTS update_id INTEGER;
                """))

                # Indice unico parziale per idempotenza
                await session.execute(sql_text("""
                    CREATE UNIQUE INDEX IF NOT EXISTS uq_processing_jobs_telegram_client_msg
                      ON processing_jobs (telegram_id, client_msg_id)
                      WHERE client_msg_id IS NOT NULL;
                """))

                # Tabella rate limiting coerente col codice attuale
                await session.execute(sql_text("""
                    CREATE TABLE IF NOT EXISTS rate_limits (
                        id SERIAL PRIMARY KEY,
                        telegram_id INTEGER NOT NULL,
                        action VARCHAR(50) NOT NULL,
                        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );
                """))

                await session.execute(sql_text("""
                    CREATE INDEX IF NOT EXISTS idx_rate_limits_telegram_action_timestamp
                        ON rate_limits (telegram_id, action, timestamp DESC);
                """))

                # Compatibilità temporanea: alcune versioni potrebbero interrogare rate_limit_logs
                await session.execute(sql_text("""
                    DO $$
                    BEGIN
                      IF NOT EXISTS (
                        SELECT 1 FROM information_schema.views
                        WHERE table_schema = 'public' AND table_name = 'rate_limit_logs'
                      ) THEN
                        CREATE VIEW rate_limit_logs AS
                          SELECT id, telegram_id, action, timestamp AS created_at
                          FROM rate_limits;
                      END IF;
                    END$$;
                """))

                await session.commit()
                logger.info("Database tables created successfully (public schema): users, processing_jobs")
                logger.info("System schema aligned: processing_jobs idempotency columns, rate_limits table, compatibility view")
                logger.info("Note: Tabelle inventario vengono create per-utente nello schema public via ensure_user_tables()")
            except Exception as align_error:
                await session.rollback()
                logger.error(f"Error aligning system schema: {align_error}")
                # Non bloccare startup: al limite fallirà l'endpoint con errore chiaro
    except Exception as e:
        logger.error(f"Error creating database tables: {e}")
        raise

async def save_inventory_to_db(session, telegram_id: int, business_name: str, wines_data: list, mode: str = "add", batch_size: int = 100):
    """
    Salva inventario e vini nel database nello schema utente specifico.
    
    Args:
        mode: "add" (aggiunge vini esistenti) o "replace" (sostituisce tutto l'inventario)
        batch_size: Numero di vini da inserire in batch per performance (default 100)
    """
    try:
        from sqlalchemy import select, Table, MetaData, insert
        from sqlalchemy import text as sql_text
        
        # Trova o crea utente (in schema public)
        stmt = select(User).where(User.telegram_id == telegram_id)
        result = await session.execute(stmt)
        user = result.scalar_one_or_none()
        
        if not user:
            # Crea nuovo utente
            user = User(
            telegram_id=telegram_id,
            business_name=business_name,
                onboarding_completed=True
            )
            session.add(user)
            await session.flush()
        
        # Aggiorna business_name se necessario
        if not user.business_name:
            user.business_name = business_name
            user.onboarding_completed = True
        
        # Assicura che tabelle utente esistano
        user_tables = await ensure_user_tables(session, telegram_id, business_name)
        table_inventario = user_tables["inventario"]
        table_backup = user_tables["backup"]
        
        # Se mode="replace", cancella inventario esistente
        if mode == "replace":
            logger.info(f"Mode 'replace': deleting existing inventory for user {telegram_id}")
            delete_existing = sql_text(f"DELETE FROM {table_inventario} WHERE user_id = :user_id")
            await session.execute(delete_existing, {"user_id": user.id})
            await session.commit()
            logger.info(f"Existing inventory deleted for user {telegram_id}")
        
        # Normalizza e prepara vini per batch insert
        normalized_wines = []  # Lista vini normalizzati pronti per inserimento
        saved_count = 0
        warning_count = 0  # Separato da error_count: solo warnings (annate mancanti, dati opzionali)
        error_count = 0    # Solo errori critici (vino non salvato)
        warnings_log = []   # Lista warnings separata
        errors_log = []     # Lista errori critici
        
        for wine_data in wines_data:
            errors = []
            warnings = []
            
            try:
                # Normalizza vintage: converti stringa a int
                vintage = wine_data.get("vintage")
                vintage_original = vintage
                if vintage:
                    if isinstance(vintage, str):
                        # Estrai solo numeri (anni 1900-2099)
                        import re
                        vintage_match = re.search(r'\b(19|20)\d{2}\b', str(vintage))
                        if vintage_match:
                            vintage = int(vintage_match.group())
                        else:
                            vintage = None
                            warnings.append(f"Annata '{vintage_original}' non valida - salvato senza annata")
                    elif isinstance(vintage, (int, float)):
                        vintage = int(vintage)
                        # Verifica range valido
                        if vintage < 1900 or vintage > 2099:
                            warnings.append(f"Annata {vintage} fuori range - salvato comunque")
                    else:
                        vintage = None
                        warnings.append(f"Tipo annata non riconosciuto: {type(vintage_original).__name__}")
                else:
                    warnings.append("Annata mancante")
                
                # Normalizza quantity: converti a int
                quantity = wine_data.get("quantity", 1)
                quantity_original = quantity
                try:
                    if isinstance(quantity, str):
                        import re
                        qty_match = re.search(r'\d+', str(quantity))
                        quantity = int(qty_match.group()) if qty_match else 1
                        if qty_match is None:
                            warnings.append(f"Quantità '{quantity_original}' non valida - impostata a 1")
                    else:
                        quantity = int(quantity) if quantity else 1
                        if quantity <= 0:
                            warnings.append(f"Quantità {quantity} non valida - impostata a 1")
                            quantity = 1
                except (ValueError, TypeError) as e:
                    warnings.append(f"Errore conversione quantità '{quantity_original}': {e} - impostata a 1")
                    quantity = 1
                
                # Normalizza cost_price: converti a float
                cost_price = wine_data.get("cost_price")
                cost_price_original = cost_price
                if cost_price:
                    try:
                        if isinstance(cost_price, str):
                            import re
                            cost_clean = re.sub(r'[^\d.,]', '', str(cost_price).replace(',', '.'))
                            cost_price = float(cost_clean) if cost_clean else None
                            if cost_price is None:
                                warnings.append(f"Costo acquisto '{cost_price_original}' non valido - salvato senza costo")
                        else:
                            cost_price = float(cost_price) if cost_price else None
                            if cost_price and cost_price < 0:
                                warnings.append(f"Costo negativo {cost_price} - salvato comunque")
                    except (ValueError, TypeError) as e:
                        warnings.append(f"Errore conversione costo '{cost_price_original}': {e} - salvato senza costo")
                        cost_price = None
                else:
                    cost_price = None
                
                # Normalizza selling_price: converti a float
                selling_price = wine_data.get("selling_price")
                selling_price_original = selling_price
                # Fallback: se non c'è selling_price ma c'è 'price', usa quello (compatibilità)
                if not selling_price and wine_data.get("price"):
                    selling_price = wine_data.get("price")
                    selling_price_original = selling_price
                
                if selling_price:
                    try:
                        if isinstance(selling_price, str):
                            import re
                            price_clean = re.sub(r'[^\d.,]', '', str(selling_price).replace(',', '.'))
                            selling_price = float(price_clean) if price_clean else None
                            if selling_price is None:
                                warnings.append(f"Prezzo vendita '{selling_price_original}' non valido - salvato senza prezzo")
                        else:
                            selling_price = float(selling_price) if selling_price else None
                            if selling_price and selling_price < 0:
                                warnings.append(f"Prezzo negativo {selling_price} - salvato comunque")
                    except (ValueError, TypeError) as e:
                        warnings.append(f"Errore conversione prezzo '{selling_price_original}': {e} - salvato senza prezzo")
                        selling_price = None
                else:
                    selling_price = None
                
                # Normalizza alcohol_content: converti stringa con % a float
                alcohol_content = wine_data.get("alcohol_content")
                alcohol_original = alcohol_content
                if alcohol_content:
                    try:
                        if isinstance(alcohol_content, str):
                            # Rimuovi % e altri caratteri, mantieni solo numeri e punto/virgola
                            import re
                            alcohol_clean = re.sub(r'[^\d.,]', '', str(alcohol_content).replace(',', '.'))
                            alcohol_content = float(alcohol_clean) if alcohol_clean else None
                            if alcohol_content is None:
                                warnings.append(f"Gradazione alcolica '{alcohol_original}' non valida - salvato senza gradazione")
                            elif alcohol_content < 0 or alcohol_content > 100:
                                warnings.append(f"Gradazione alcolica {alcohol_content}% fuori range - salvato comunque")
                        else:
                            alcohol_content = float(alcohol_content) if alcohol_content else None
                            if alcohol_content and (alcohol_content < 0 or alcohol_content > 100):
                                warnings.append(f"Gradazione alcolica {alcohol_content}% fuori range - salvato comunque")
                    except (ValueError, TypeError) as e:
                        warnings.append(f"Errore conversione gradazione alcolica '{alcohol_original}': {e} - salvato senza gradazione")
                        alcohol_content = None
                
                # Prepara note con errori/warning
                notes_parts = []
                if wine_data.get("notes"):
                    notes_parts.append(str(wine_data.get("notes")))
                
                if warnings:
                    notes_parts.append("\n⚠️ AVVISI ELABORAZIONE:")
                    notes_parts.extend([f"  • {w}" for w in warnings])
                
                if errors:
                    notes_parts.append("\n❌ ERRORI:")
                    notes_parts.extend([f"  • {e}" for e in errors])
                
                combined_notes = "\n".join(notes_parts) if notes_parts else None
                
                # Accumula vino normalizzato per batch insert
                normalized_wine = {
                    "user_id": user.id,
                    "name": wine_data.get("name", "Vino senza nome"),
                    "producer": wine_data.get("producer"),
                    "vintage": vintage,
                    "grape_variety": wine_data.get("grape_variety"),
                    "region": wine_data.get("region"),
                    "country": wine_data.get("country"),
                    "wine_type": wine_data.get("wine_type"),
                    "classification": wine_data.get("classification"),
                    "quantity": quantity,
                    "min_quantity": wine_data.get("min_quantity", 0),
                    "cost_price": cost_price,
                    "selling_price": selling_price,
                    "alcohol_content": alcohol_content,
                    "description": wine_data.get("description"),
                    "notes": combined_notes,
                    "created_at": datetime.utcnow(),
                    "updated_at": datetime.utcnow()
                }
                normalized_wines.append(normalized_wine)
                
                # Conta warnings e errori (per report)
                if warnings:
                    warning_count += 1
                    warnings_log.append({
                        "wine": wine_data.get("name", "Sconosciuto"),
                        "warnings": warnings
                    })
                
                if errors:
                    error_count += 1
                    errors_log.append({
                        "wine": wine_data.get("name", "Sconosciuto"),
                        "errors": errors
                    })
                
            except Exception as e:
                # Errore critico - salva comunque il vino con note di errore
                logger.error(f"Errore critico normalizzando vino {wine_data.get('name', 'Unknown')}: {e}")
                error_count += 1
                errors_log.append({
                    "wine": wine_data.get("name", "Sconosciuto"),
                    "errors": [f"Errore critico: {str(e)}"]
                })
                
                # Prova a salvare comunque con dati disponibili nello schema utente
                try:
                    error_note = f"❌ ERRORE ELABORAZIONE: {str(e)}\n⚠️ Vino salvato con dati parziali. Verificare manualmente."
                    if wine_data.get("notes"):
                        error_note = f"{wine_data.get('notes')}\n\n{error_note}"
                    
                    insert_wine_error = sql_text(f"""
                        INSERT INTO {table_inventario} 
                        (user_id, name, producer, vintage, region, wine_type, quantity, notes, description, created_at, updated_at)
                        VALUES 
                        (:user_id, :name, :producer, :vintage, :region, :wine_type, :quantity, :notes, :description, :created_at, :updated_at)
                        RETURNING id
                    """)
                    
                    result = await session.execute(insert_wine_error, {
                        "user_id": user.id,
                        "name": wine_data.get("name", "Vino senza nome - ERRORE"),
                        "producer": wine_data.get("producer"),
                        "vintage": None,
                        "region": wine_data.get("region"),
                        "wine_type": wine_data.get("wine_type"),
                        "quantity": 1,
                        "notes": error_note,
                        "description": wine_data.get("description"),
                        "created_at": datetime.utcnow(),
                        "updated_at": datetime.utcnow()
                    })
                    wine_id = result.scalar_one()
                    saved_count += 1
                except Exception as save_error:
                    logger.error(f"Impossibile salvare vino {wine_data.get('name', 'Unknown')} anche con dati parziali: {save_error}")
                    continue
        
        # BATCH INSERT per performance (inserisce vini in batch)
        if normalized_wines:
            logger.info(f"Inserting {len(normalized_wines)} wines in batches of {batch_size}")
            
            # Inserisci in batch usando executemany (loop efficiente)
            insert_wine_stmt = sql_text(f"""
                INSERT INTO {table_inventario} 
                (user_id, name, producer, vintage, grape_variety, region, country, 
                 wine_type, classification, quantity, min_quantity, cost_price, selling_price, 
                 alcohol_content, description, notes, created_at, updated_at)
                VALUES 
                (:user_id, :name, :producer, :vintage, :grape_variety, :region, :country, 
                 :wine_type, :classification, :quantity, :min_quantity, :cost_price, :selling_price, 
                 :alcohol_content, :description, :notes, :created_at, :updated_at)
            """)
            
            # Inserisci in batch (SQLAlchemy async esegue executemany implicitamente)
            for i in range(0, len(normalized_wines), batch_size):
                batch = normalized_wines[i:i + batch_size]
                # Esegui ogni elemento del batch (SQLAlchemy ottimizza internamente)
                for wine_params in batch:
                    await session.execute(insert_wine_stmt, wine_params)
                saved_count += len(batch)
                logger.debug(f"Inserted batch {i//batch_size + 1}: {len(batch)} wines")
                # Commit ogni batch per evitare transazioni troppo lunghe
                await session.commit()
            
            logger.info(f"Batch insert completed: {saved_count} wines saved")
        
        # Crea backup automatico dopo il salvataggio
        import json
        backup_data = json.dumps([{
            "name": w.get("name"),
            "producer": w.get("producer"),
            "vintage": w.get("vintage"),
            "quantity": w.get("quantity", 0),
            "price": w.get("price")
        } for w in wines_data], ensure_ascii=False, indent=2)
        
        insert_backup = sql_text(f"""
            INSERT INTO {table_backup}
            (user_id, backup_name, backup_data, backup_type, created_at)
            VALUES
            (:user_id, :backup_name, :backup_data, :backup_type, :created_at)
        """)
        await session.execute(insert_backup, {
            "user_id": user.id,
            "backup_name": f"Inventario giorno 0 - {business_name}",
            "backup_data": backup_data,
            "backup_type": "initial",
            "created_at": datetime.utcnow()
        })
        
        await session.commit()
        
        # Log appropriato in base a warnings/errori
        if error_count > 0:
            logger.error(f"Saved {saved_count} wines for user {telegram_id}/{business_name}, {error_count} errori critici, {warning_count} warnings")
            logger.error(f"Errors summary: {errors_log}")
        elif warning_count > 0:
            logger.warning(f"Saved {saved_count} wines for user {telegram_id}/{business_name}, {warning_count} warnings (annate mancanti, dati opzionali)")
        else:
            logger.info(f"Saved {saved_count} wines for user {telegram_id}/{business_name} without errors or warnings")
        
        return {
            "user_id": user.id,
            "saved_count": saved_count,
            "total_count": len(wines_data),
            "warning_count": warning_count,  # Separato: solo warnings
            "error_count": error_count,      # Solo errori critici
            "warnings": warnings_log,       # Lista warnings
            "errors": errors_log,            # Lista errori critici
            "table_name": table_inventario
        }
        
    except Exception as e:
        await session.rollback()
        logger.error(f"Error saving inventory to database: {e}")
        raise

async def get_user_inventories(session, telegram_id: int):
    """Ottieni inventari di un utente dalla tabella INVENTARIO"""
    try:
        from sqlalchemy import select
        
        # Trova utente
        stmt = select(User).where(User.telegram_id == telegram_id)
        result = await session.execute(stmt)
        user = result.scalar_one_or_none()
        
        if not user or not user.business_name:
            return []
        
        # Ottieni nome tabella INVENTARIO
        table_inventario = get_user_table_name(telegram_id, user.business_name, "INVENTARIO")
        
        # Query vini dalla tabella INVENTARIO
        select_wines = sql_text(f'SELECT * FROM {table_inventario} WHERE user_id = :user_id ORDER BY created_at DESC')
        result = await session.execute(select_wines, {"user_id": user.id})
        
        # Converti risultati in dizionari
        wines = []
        for row in result:
            wines.append({
                "id": row.id,
                "user_id": row.user_id,
                "name": row.name,
                "producer": row.producer,
                "vintage": row.vintage,
                "grape_variety": row.grape_variety,
                "region": row.region,
                "country": row.country,
                "wine_type": row.wine_type,
                "classification": row.classification,
                "quantity": row.quantity,
                "min_quantity": row.min_quantity,
                "cost_price": row.cost_price,
                "selling_price": row.selling_price,
                "alcohol_content": row.alcohol_content,
                "description": row.description,
                "notes": row.notes,
                "created_at": row.created_at,
                "updated_at": row.updated_at
            })
        
        return wines
    except Exception as e:
        logger.error(f"Error getting user inventories: {e}")
        # Se tabella non esiste, ritorna lista vuota
        return []

async def get_inventory_status(session, telegram_id: int):
    """Ottieni stato elaborazione per utente dalla tabella INVENTARIO"""
    try:
        from sqlalchemy import select
        
        stmt = select(User).where(User.telegram_id == telegram_id)
        result = await session.execute(stmt)
        user = result.scalar_one_or_none()
        
        if not user:
            return {
                "telegram_id": telegram_id,
                "total_wines": 0,
                "onboarding_completed": False,
                "status": "not_found",
                "table_name": None
            }
        
        wines_count = 0
        table_name = None
        
        if user.business_name:
            # Conta vini nella tabella INVENTARIO
            try:
                table_inventario = get_user_table_name(telegram_id, user.business_name, "INVENTARIO")
                table_name = table_inventario
                count_query = sql_text(f'SELECT COUNT(*) FROM {table_inventario} WHERE user_id = :user_id')
                result = await session.execute(count_query, {"user_id": user.id})
                wines_count = result.scalar_one() or 0
            except Exception as table_error:
                logger.warning(f"Table {table_name} not found or error counting wines: {table_error}")
                wines_count = 0
        
        return {
            "telegram_id": telegram_id,
            "total_wines": wines_count,
            "onboarding_completed": user.onboarding_completed,
            "business_name": user.business_name,
            "status": "completed" if user.onboarding_completed else "processing",
            "table_name": table_name
        }
    except Exception as e:
        logger.error(f"Error getting inventory status: {e}")
        raise

