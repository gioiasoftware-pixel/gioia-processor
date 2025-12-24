"""
Gestione database per report PDF giornalieri.
Crea tabella daily_reports e funzioni per salvare/recuperare PDF.
"""
import logging
from datetime import datetime, date
from typing import Optional, Dict, Any
from sqlalchemy import text as sql_text
from sqlalchemy.ext.asyncio import AsyncSession
from core.database import AsyncSessionLocal

logger = logging.getLogger(__name__)


async def ensure_daily_reports_table(session: AsyncSession):
    """
    Crea la tabella daily_reports se non esiste.
    """
    try:
        check_table_query = sql_text("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name = 'daily_reports'
            );
        """)
        result = await session.execute(check_table_query)
        table_exists = result.scalar()
        
        if table_exists:
            logger.info("[DAILY_REPORTS_DB] Tabella 'daily_reports' già esistente")
            return
        
        logger.info("[DAILY_REPORTS_DB] Creazione tabella 'daily_reports'...")
        create_table_query = sql_text("""
            CREATE TABLE daily_reports (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                report_date DATE NOT NULL,
                pdf_data BYTEA NOT NULL,
                business_name VARCHAR(200) NOT NULL,
                total_consumi INTEGER DEFAULT 0,
                total_rifornimenti INTEGER DEFAULT 0,
                total_movements INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, report_date)
            );
        """)
        await session.execute(create_table_query)
        
        # Crea indici
        create_index_1 = sql_text("CREATE INDEX idx_daily_reports_user_id ON daily_reports(user_id);")
        await session.execute(create_index_1)
        
        create_index_2 = sql_text("CREATE INDEX idx_daily_reports_report_date ON daily_reports(report_date DESC);")
        await session.execute(create_index_2)
        
        create_index_3 = sql_text("CREATE INDEX idx_daily_reports_user_date ON daily_reports(user_id, report_date DESC);")
        await session.execute(create_index_3)
        
        logger.info("[DAILY_REPORTS_DB] ✅ Tabella 'daily_reports' creata con successo")
    except Exception as e:
        logger.error(f"[DAILY_REPORTS_DB] Errore creando tabella daily_reports: {e}", exc_info=True)
        raise


async def save_daily_report_pdf(
    user_id: int,
    report_date: date,
    pdf_data: bytes,
    business_name: str,
    total_consumi: int = 0,
    total_rifornimenti: int = 0,
    total_movements: int = 0
) -> Optional[int]:
    """
    Salva un PDF report nel database.
    
    Args:
        user_id: ID utente
        report_date: Data del report
        pdf_data: Bytes del PDF
        business_name: Nome business
        total_consumi: Totale consumi
        total_rifornimenti: Totale rifornimenti
        total_movements: Totale movimenti
    
    Returns:
        ID del report salvato o None se errore
    """
    try:
        async with AsyncSessionLocal() as session:
            # Assicura tabella esista
            await ensure_daily_reports_table(session)
            
            # Usa INSERT ... ON CONFLICT per upsert
            insert_query = sql_text("""
                INSERT INTO daily_reports 
                    (user_id, report_date, pdf_data, business_name, total_consumi, total_rifornimenti, total_movements)
                VALUES (:user_id, :report_date, :pdf_data, :business_name, :total_consumi, :total_rifornimenti, :total_movements)
                ON CONFLICT (user_id, report_date) 
                DO UPDATE SET 
                    pdf_data = EXCLUDED.pdf_data,
                    business_name = EXCLUDED.business_name,
                    total_consumi = EXCLUDED.total_consumi,
                    total_rifornimenti = EXCLUDED.total_rifornimenti,
                    total_movements = EXCLUDED.total_movements,
                    created_at = CURRENT_TIMESTAMP
                RETURNING id
            """)
            result = await session.execute(insert_query, {
                "user_id": user_id,
                "report_date": report_date,
                "pdf_data": pdf_data,
                "business_name": business_name,
                "total_consumi": total_consumi,
                "total_rifornimenti": total_rifornimenti,
                "total_movements": total_movements
            })
            report_id = result.scalar()
            await session.commit()
            
            logger.info(f"[DAILY_REPORTS_DB] Report PDF salvato: id={report_id}, user_id={user_id}, date={report_date}")
            return report_id
    except Exception as e:
        logger.error(f"[DAILY_REPORTS_DB] Errore salvataggio report PDF: {e}", exc_info=True)
        return None


async def get_daily_report_pdf(user_id: int, report_date: date) -> Optional[Dict[str, Any]]:
    """
    Recupera un PDF report dal database.
    
    Args:
        user_id: ID utente
        report_date: Data del report
    
    Returns:
        Dict con pdf_data (bytes) e metadata, o None se non trovato
    """
    try:
        async with AsyncSessionLocal() as session:
            query = sql_text("""
                SELECT id, pdf_data, business_name, total_consumi, total_rifornimenti, total_movements, created_at
                FROM daily_reports
                WHERE user_id = :user_id AND report_date = :report_date
            """)
            result = await session.execute(query, {
                "user_id": user_id,
                "report_date": report_date
            })
            row = result.fetchone()
            
            if not row:
                logger.debug(f"[DAILY_REPORTS_DB] Report non trovato: user_id={user_id}, date={report_date}")
                return None
            
            return {
                "id": row[0],
                "pdf_data": bytes(row[1]),  # BYTEA -> bytes
                "business_name": row[2],
                "total_consumi": row[3],
                "total_rifornimenti": row[4],
                "total_movements": row[5],
                "created_at": row[6]
            }
    except Exception as e:
        logger.error(f"[DAILY_REPORTS_DB] Errore recupero report PDF: {e}", exc_info=True)
        return None

