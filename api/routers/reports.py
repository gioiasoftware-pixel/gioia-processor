"""
Router per recupero report PDF giornalieri.
"""
import logging
from datetime import date, datetime
from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response
from core.daily_reports_db import get_daily_report_pdf
from core.database import AsyncSessionLocal, User
from sqlalchemy import select

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

