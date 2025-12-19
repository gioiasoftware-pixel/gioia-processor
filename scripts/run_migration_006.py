#!/usr/bin/env python3
"""
Script per eseguire la migrazione SQL 006_make_telegram_id_nullable.sql

Uso:
    python scripts/run_migration_006.py

Oppure con DATABASE_URL esplicito:
    DATABASE_URL=postgresql://user:pass@host:5432/dbname python scripts/run_migration_006.py
"""
import os
import sys
import asyncio
import logging
from pathlib import Path

# Aggiungi la root del progetto al path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import text as sql_text
from core.database import AsyncSessionLocal, get_database_url

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def run_migration_006():
    """Esegue la migrazione 006: rende telegram_id nullable"""
    
    migration_file = project_root / "migrations" / "006_make_telegram_id_nullable.sql"
    
    if not migration_file.exists():
        logger.error(f"File migrazione non trovato: {migration_file}")
        sys.exit(1)
    
    # Leggi il contenuto del file SQL
    with open(migration_file, 'r', encoding='utf-8') as f:
        sql_content = f.read()
    
    logger.info(f"Eseguendo migrazione 006: {migration_file.name}")
    logger.info(f"Database URL: {get_database_url()}")
    
    try:
        async with AsyncSessionLocal() as session:
            # Esegui il file SQL completo (meglio per blocchi DO $$)
            # Rimuovi solo i commenti iniziali
            lines = sql_content.split('\n')
            sql_clean = '\n'.join([line for line in lines if not line.strip().startswith('--') or 'Esegui con:' in line])
            
            logger.info("Eseguendo migrazione SQL completa...")
            await session.execute(sql_text(sql_clean))
            await session.commit()
            
            logger.info("✅ Migrazione 006 completata con successo!")
            
    except Exception as e:
        logger.error(f"❌ Errore durante migrazione 006: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(run_migration_006())
