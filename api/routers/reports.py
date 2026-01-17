"""
Router per recupero report PDF giornalieri.
"""
import logging
from datetime import date, datetime
from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response
from core.daily_reports_db import get_daily_report_pdf
from core.database import AsyncSessionLocal, User, get_user_table_name
from sqlalchemy import select, text as sql_text
from core.pdf_report_generator import generate_inventory_stats_pdf

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/reports", tags=["reports"])


@router.get("/daily/{user_id}")
async def get_daily_report_pdf_endpoint(
    user_id: int,
    report_date: Optional[str] = Query(None, description="Data report in formato YYYY-MM-DD (default: ieri)")
):
    """
    Recupera PDF report giornaliero per un utente.
    
    Args:
        user_id: ID utente
        report_date: Data report (default: ieri)
    
    Returns:
        PDF file
    """
    try:
        # Parse data report
        if report_date:
            try:
                report_date_obj = datetime.strptime(report_date, "%Y-%m-%d").date()
            except ValueError:
                raise HTTPException(status_code=400, detail="Formato data non valido. Usa YYYY-MM-DD")
        else:
            # Default: ieri
            from datetime import timedelta
            report_date_obj = (datetime.now().date() - timedelta(days=1))
        
        # Verifica utente esista
        async with AsyncSessionLocal() as session:
            stmt = select(User).where(User.id == user_id)
            result = await session.execute(stmt)
            user = result.scalar_one_or_none()
            
            if not user:
                raise HTTPException(status_code=404, detail="Utente non trovato")
        
        # Recupera PDF
        report_data = await get_daily_report_pdf(user_id, report_date_obj)
        
        if not report_data:
            raise HTTPException(
                status_code=404, 
                detail=f"Report non trovato per la data {report_date_obj.strftime('%Y-%m-%d')}"
            )
        
        # Ritorna PDF
        return Response(
            content=report_data['pdf_data'],
            media_type="application/pdf",
            headers={
                "Content-Disposition": f"attachment; filename=report_{user_id}_{report_date_obj.strftime('%Y%m%d')}.pdf"
            }
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[REPORTS_API] Errore recupero PDF: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Errore interno del server")


@router.get("/inventory/{user_id}")
async def get_inventory_stats_pdf_endpoint(user_id: int):
    """
    Recupera PDF statistiche inventario per un utente.
    """
    try:
        async with AsyncSessionLocal() as session:
            stmt = select(User).where(User.id == user_id)
            result = await session.execute(stmt)
            user = result.scalar_one_or_none()

            if not user:
                raise HTTPException(status_code=404, detail="Utente non trovato")

            table_name = get_user_table_name(user.id, user.business_name, "INVENTARIO")

            table_name_check = table_name.strip('"')
            check_table_query = sql_text("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_schema = 'public'
                    AND table_name = :table_name
                )
            """)
            result = await session.execute(check_table_query, {"table_name": table_name_check})
            table_exists = result.scalar()

            if not table_exists:
                raise HTTPException(status_code=404, detail="Inventario non trovato")

            query = sql_text(f"""
                SELECT wine_type, quantity, selling_price
                FROM {table_name}
                WHERE user_id = :user_id
            """)
            result = await session.execute(query, {"user_id": user.id})
            rows = result.fetchall()

        if not rows:
            raise HTTPException(status_code=404, detail="Inventario vuoto")

        total_wines = len(rows)
        total_bottles = sum((r[1] or 0) for r in rows)
        total_value = sum(((r[2] or 0) * (r[1] or 0)) for r in rows)

        types_distribution = {}
        low_stock_count = 0
        out_of_stock_count = 0

        for wine_type, quantity, _selling_price in rows:
            wt = wine_type or "Altro"
            types_distribution[wt] = types_distribution.get(wt, 0) + 1
            qty = quantity or 0
            if qty == 0:
                out_of_stock_count += 1
            elif qty < 5:
                low_stock_count += 1

        stats = {
            "total_wines": total_wines,
            "total_bottles": total_bottles,
            "total_value": total_value,
            "types_distribution": types_distribution,
            "low_stock_count": low_stock_count,
            "out_of_stock_count": out_of_stock_count
        }

        pdf_bytes = generate_inventory_stats_pdf(user.business_name or "Gio.ia", stats)
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f"attachment; filename=inventory_stats_{user_id}.pdf"
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[REPORTS_API] Errore recupero PDF inventario: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Errore interno del server")

