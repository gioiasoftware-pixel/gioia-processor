"""
Scheduler per task periodici nel processor.

Gestisce report giornalieri automatici e altre task schedulabili.
Usa APScheduler con AsyncIOScheduler per compatibilità asyncio.
"""
import logging
import os
from datetime import datetime, timedelta
from typing import List, Dict, Any
import pytz

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select, text as sql_text

from core.database import AsyncSessionLocal, User, ensure_user_tables
from core.config import get_config
from telegram_notifier import send_telegram_message

logger = logging.getLogger(__name__)

# Timezone Italia
ITALY_TZ = pytz.timezone('Europe/Rome')

# Scheduler globale
_scheduler: AsyncIOScheduler = None


def get_scheduler() -> AsyncIOScheduler:
    """Ottiene o crea il scheduler globale."""
    global _scheduler
    if _scheduler is None:
        _scheduler = AsyncIOScheduler(timezone=ITALY_TZ)
    return _scheduler


async def generate_daily_movements_report(
    telegram_id: int,
    business_name: str,
    report_date: datetime
) -> str:
    """
    Genera report movimenti giornaliero per un utente.
    
    Args:
        telegram_id: ID Telegram utente
        business_name: Nome business
        report_date: Data del report (giorno precedente)
    
    Returns:
        Testo del report formattato per Telegram
    """
    async with AsyncSessionLocal() as session:
        try:
            # Trova utente
            stmt = select(User).where(User.telegram_id == telegram_id)
            result = await session.execute(stmt)
            user = result.scalar_one_or_none()
            
            if not user:
                logger.warning(f"[DAILY_REPORT] Utente {telegram_id} non trovato")
                return None
            
            # Assicura tabelle esistano
            user_tables = await ensure_user_tables(session, telegram_id, business_name)
            table_consumi = user_tables["consumi"]
            
            # Calcola range giornata (00:00 - 23:59 ora italiana)
            # IMPORTANTE: Converti in UTC per confronto con CURRENT_TIMESTAMP del database
            start_of_day_italy = report_date.replace(hour=0, minute=0, second=0, microsecond=0)
            end_of_day_italy = report_date.replace(hour=23, minute=59, second=59, microsecond=999999)
            
            # Converti in UTC per confronto con timestamp del database
            start_of_day_utc = start_of_day_italy.astimezone(pytz.UTC).replace(tzinfo=None)
            end_of_day_utc = end_of_day_italy.astimezone(pytz.UTC).replace(tzinfo=None)
            
            logger.info(
                f"[DAILY_REPORT] Cercando movimenti per {telegram_id} tra "
                f"{start_of_day_italy.strftime('%Y-%m-%d %H:%M:%S %Z')} e "
                f"{end_of_day_italy.strftime('%Y-%m-%d %H:%M:%S %Z')} "
                f"(UTC: {start_of_day_utc} - {end_of_day_utc})"
            )
            
            # Query movimenti del giorno
            query_movements = sql_text(f"""
                SELECT 
                    wine_name,
                    wine_producer,
                    movement_type,
                    quantity_change,
                    quantity_before,
                    quantity_after,
                    movement_date
                FROM {table_consumi}
                WHERE user_id = :user_id
                AND movement_date >= :start_date
                AND movement_date <= :end_date
                ORDER BY movement_date ASC
            """)
            
            result = await session.execute(query_movements, {
                "user_id": user.id,
                "start_date": start_of_day_utc,
                "end_date": end_of_day_utc
            })
            movements = result.fetchall()
            
            logger.info(
                f"[DAILY_REPORT] Trovati {len(movements)} movimenti per {telegram_id} "
                f"per data {report_date.strftime('%Y-%m-%d')}"
            )
            
            if not movements:
                # Nessun movimento, genera messaggio informativo
                report_date_str = report_date.strftime("%d/%m/%Y")
                report = f"📊 **Report Movimenti - {report_date_str}**\n\n"
                report += f"🏢 **{business_name}**\n\n"
                report += "ℹ️ Non sono stati riscontrati movimenti (consumi o rifornimenti) per questa giornata.\n\n"
                report += "💡 Usa `/view` per vedere il tuo inventario completo"
                return report
            
            # Calcola statistiche
            total_consumi = sum(
                abs(m[3]) for m in movements if m[2] == 'consumo'
            )  # quantity_change negativo per consumi
            total_rifornimenti = sum(
                m[3] for m in movements if m[2] == 'rifornimento'
            )
            net_change = total_rifornimenti - total_consumi
            
            # Raggruppa per vino
            wines_summary = {}
            for mov in movements:
                wine_name = mov[0] or "Sconosciuto"
                movement_type = mov[2]
                quantity_change = mov[3]
                
                if wine_name not in wines_summary:
                    wines_summary[wine_name] = {
                        "consumi": 0,
                        "rifornimenti": 0
                    }
                
                if movement_type == 'consumo':
                    wines_summary[wine_name]["consumi"] += abs(quantity_change)
                else:
                    wines_summary[wine_name]["rifornimenti"] += quantity_change
            
            # Formatta report
            report_date_str = report_date.strftime("%d/%m/%Y")
            
            report = f"📊 **Report Movimenti - {report_date_str}**\n\n"
            report += f"🏢 **{business_name}**\n\n"
            
            # Statistiche generali
            report += "📈 **Statistiche Generali**\n"
            report += f"• Consumi: {total_consumi} bottiglie\n"
            report += f"• Rifornimenti: {total_rifornimenti} bottiglie\n"
            report += f"• Variazione netta: {net_change:+d} bottiglie\n"
            report += f"• Movimenti totali: {len(movements)}\n\n"
            
            # Dettaglio per vino (max 10 vini più attivi)
            if wines_summary:
                report += "🍷 **Dettaglio per Vino**\n"
                
                # Ordina per totale movimenti (consumi + rifornimenti)
                sorted_wines = sorted(
                    wines_summary.items(),
                    key=lambda x: x[1]["consumi"] + x[1]["rifornimenti"],
                    reverse=True
                )[:10]  # Top 10
                
                for wine_name, stats in sorted_wines:
                    total_movements = stats["consumi"] + stats["rifornimenti"]
                    report += f"\n**{wine_name}**\n"
                    if stats["consumi"] > 0:
                        report += f"  📉 Consumate: {stats['consumi']} bottiglie\n"
                    if stats["rifornimenti"] > 0:
                        report += f"  📈 Rifornite: {stats['rifornimenti']} bottiglie\n"
            
            # Footer
            report += "\n\n"
            report += "💡 Usa `/view` per vedere il tuo inventario completo"
            
            return report
            
        except Exception as e:
            logger.error(
                f"[DAILY_REPORT] Errore generazione report per {telegram_id}: {e}",
                exc_info=True
            )
            return None


async def send_daily_reports_to_all_users():
    """
    Genera e invia report giornaliero movimenti a tutti gli utenti.
    
    Eseguita ogni giorno alle 10:00 ora italiana.
    """
    logger.info("[DAILY_REPORT] Inizio generazione report giornalieri")
    
    try:
        # Data del giorno precedente (ora italiana)
        now_italy = datetime.now(ITALY_TZ)
        yesterday = now_italy - timedelta(days=1)
        yesterday_date = yesterday.date()
        
        logger.info(
            f"[DAILY_REPORT] Generazione report per data: {yesterday_date.strftime('%Y-%m-%d')}"
        )
        
        async with AsyncSessionLocal() as session:
            # Recupera tutti gli utenti attivi
            stmt = select(User).where(
                User.onboarding_completed == True
            )
            result = await session.execute(stmt)
            users = result.scalars().all()
            
            logger.info(f"[DAILY_REPORT] Trovati {len(users)} utenti attivi")
            
            sent_count = 0
            skipped_count = 0
            error_count = 0
            
            for user in users:
                try:
                    if not user.business_name:
                        logger.warning(
                            f"[DAILY_REPORT] Utente {user.telegram_id} senza business_name, skip"
                        )
                        skipped_count += 1
                        continue
                    
                    # Genera report
                    report = await generate_daily_movements_report(
                        telegram_id=user.telegram_id,
                        business_name=user.business_name,
                        report_date=yesterday.replace(hour=0, minute=0, second=0, microsecond=0)
                    )
                    
                    if not report:
                        # Errore generazione report, skip
                        logger.warning(
                            f"[DAILY_REPORT] Errore generazione report per {user.telegram_id}, skip"
                        )
                        skipped_count += 1
                        continue
                    
                    # Invia report via Telegram
                    success = await send_telegram_message(
                        telegram_id=user.telegram_id,
                        message=report,
                        parse_mode="Markdown"
                    )
                    
                    if success:
                        sent_count += 1
                        logger.info(
                            f"[DAILY_REPORT] Report inviato a {user.telegram_id}/{user.business_name}"
                        )
                    else:
                        error_count += 1
                        logger.warning(
                            f"[DAILY_REPORT] Errore invio report a {user.telegram_id}"
                        )
                    
                    # Piccola pausa tra invii per evitare rate limiting
                    import asyncio
                    await asyncio.sleep(0.5)
                    
                except Exception as e:
                    error_count += 1
                    logger.error(
                        f"[DAILY_REPORT] Errore processamento utente {user.telegram_id}: {e}",
                        exc_info=True
                    )
                    continue
            
            logger.info(
                f"[DAILY_REPORT] Completato: {sent_count} inviati, "
                f"{skipped_count} saltati, {error_count} errori"
            )
            
    except Exception as e:
        logger.error(
            f"[DAILY_REPORT] Errore critico generazione report giornalieri: {e}",
            exc_info=True
        )


def setup_daily_reports_scheduler():
    """
    Configura scheduler per report giornalieri.
    
    Esegue report ogni giorno alle 10:00 ora italiana.
    """
    config = get_config()
    
    # Verifica configurazione
    if not config.telegram_bot_token:
        logger.warning(
            "[SCHEDULER] TELEGRAM_BOT_TOKEN non configurato - "
            "report giornalieri disabilitati"
        )
        return False
    
    # Verifica feature flag (opzionale)
    daily_reports_enabled = os.getenv("DAILY_REPORTS_ENABLED", "true").lower() == "true"
    if not daily_reports_enabled:
        logger.info("[SCHEDULER] Report giornalieri disabilitati (DAILY_REPORTS_ENABLED=false)")
        return False
    
    scheduler = get_scheduler()
    
    # Aggiungi job per report giornaliero alle 10:00 ora italiana
    scheduler.add_job(
        send_daily_reports_to_all_users,
        trigger=CronTrigger(
            hour=10,
            minute=0,
            timezone=ITALY_TZ
        ),
        id="daily_movements_report",
        name="Report Movimenti Giornaliero",
        replace_existing=True,
        max_instances=1,  # Solo una istanza alla volta
        misfire_grace_time=3600  # Se manca, esegui entro 1 ora
    )
    
    logger.info(
        "[SCHEDULER] Report giornaliero configurato: ogni giorno alle 10:00 (ora italiana)"
    )
    
    return True


def start_scheduler():
    """Avvia il scheduler."""
    scheduler = get_scheduler()
    
    if not scheduler.running:
        scheduler.start()
        logger.info("[SCHEDULER] Scheduler avviato")
        
        # Configura report giornalieri
        setup_daily_reports_scheduler()
    else:
        logger.warning("[SCHEDULER] Scheduler già in esecuzione")


def shutdown_scheduler():
    """Ferma il scheduler."""
    scheduler = get_scheduler()
    
    if scheduler.running:
        scheduler.shutdown()
        logger.info("[SCHEDULER] Scheduler fermato")

