"""
Migrazione: rinomina tabelle da formato telegram_id a user_id
"""
import asyncio
import re
import logging
from sqlalchemy import text as sql_text, select
from core.database import get_db, User

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def migrate_tables_telegram_to_user_id():
    """
    Rinomina tutte le tabelle da "{telegram_id}/{business_name} ..." a "{user_id}/{business_name} ..."
    """
    async for db in get_db():
        # Trova tutte le tabelle che iniziano con un numero (telegram_id)
        # NOTA: in information_schema.tables i nomi sono SENZA virgolette
        query_tables = sql_text("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
            AND table_name ~ '^[0-9]+/'
            ORDER BY table_name
        """)
        
        result = await db.execute(query_tables)
        tables = result.fetchall()
        
        logger.info(f"[MIGRATION] Trovate {len(tables)} tabelle da migrare")
        
        # Pattern per estrarre telegram_id e business_name
        # NOTA: table_name da information_schema NON ha virgolette
        pattern = re.compile(r'^(\d+)/(.+?)\s+(.+)$')
        
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
        break

if __name__ == "__main__":
    asyncio.run(migrate_tables_telegram_to_user_id())
