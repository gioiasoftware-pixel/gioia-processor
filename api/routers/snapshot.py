"""
Router per snapshot inventario e viewer.

Endpoint:
- GET /api/inventory/snapshot: Snapshot inventario con facets per filtri
- GET /api/inventory/export.csv: Export CSV inventario
- GET /api/viewer/data: Dati inventario dalla cache
- GET /api/viewer/{view_id}: HTML viewer generato
- POST /api/viewer/prepare-data: Prepara dati per viewer
"""
import csv
import io
import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Form, HTTPException, Query
from fastapi.responses import HTMLResponse, Response
from sqlalchemy import select, text as sql_text
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db, ensure_user_tables, User
from jwt_utils import validate_viewer_token
from viewer_generator import (
    generate_viewer_html_from_db,
    store_viewer_html,
    get_viewer_html_from_cache,
    prepare_viewer_data,
    get_viewer_data_from_cache
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["snapshot"])


@router.get("/inventory/snapshot")
async def get_inventory_snapshot_endpoint(token: str = Query(...)):
    """
    Endpoint per viewer: restituisce snapshot inventario con facets per filtri.
    Richiede token JWT valido come query parameter.
    
    Conforme a endpoint esistente in main.py.
    """
    try:
        logger.info(f"[VIEWER_API] Richiesta snapshot ricevuta, token_length={len(token)}")
        
        # Valida token JWT
        token_data = validate_viewer_token(token)
        if not token_data:
            logger.warning(f"[VIEWER_API] Token JWT non valido o scaduto, token_length={len(token)}")
            raise HTTPException(status_code=401, detail="Token scaduto o non valido")
        
        telegram_id = token_data["telegram_id"]
        business_name = token_data["business_name"]
        
        logger.info(
            f"[VIEWER_API] Snapshot richiesto per telegram_id={telegram_id}, "
            f"business_name={business_name}, token_validated=True"
        )
        
        async for db in get_db():
            # Verifica che utente esista
            stmt = select(User).where(User.telegram_id == telegram_id)
            result = await db.execute(stmt)
            user = result.scalar_one_or_none()
            
            if not user:
                raise HTTPException(status_code=404, detail="Utente non trovato")
            
            # Assicura che tabelle esistano
            user_tables = await ensure_user_tables(db, telegram_id, business_name)
            table_inventario = user_tables["inventario"]
            
            # Recupera tutti i vini
            query_wines = sql_text(f"""
                SELECT 
                    name,
                    producer,
                    vintage,
                    quantity,
                    selling_price,
                    wine_type,
                    min_quantity,
                    updated_at
                FROM {table_inventario}
                WHERE user_id = :user_id
                ORDER BY name, vintage
            """)
            
            result = await db.execute(query_wines, {"user_id": user.id})
            wines_rows = result.fetchall()
            
            # Formatta vini per risposta
            rows = []
            for wine in wines_rows:
                rows.append({
                    "name": wine.name or "-",
                    "winery": wine.producer or "-",
                    "vintage": wine.vintage,
                    "qty": wine.quantity or 0,
                    "price": float(wine.selling_price) if wine.selling_price else 0.0,
                    "type": wine.wine_type or "Altro",
                    "critical": wine.quantity is not None and wine.min_quantity is not None and wine.quantity <= wine.min_quantity
                })
            
            # Calcola facets (aggregazioni per filtri)
            facets = {
                "type": {},
                "vintage": {},
                "winery": {}
            }
            
            for wine in wines_rows:
                # Tipo
                wine_type = wine.wine_type or "Altro"
                facets["type"][wine_type] = facets["type"].get(wine_type, 0) + 1
                
                # Annata
                if wine.vintage:
                    vintage_str = str(wine.vintage)
                    facets["vintage"][vintage_str] = facets["vintage"].get(vintage_str, 0) + 1
                
                # Cantina (producer)
                if wine.producer:
                    facets["winery"][wine.producer] = facets["winery"].get(wine.producer, 0) + 1
            
            # Meta info
            last_update = None
            if wines_rows:
                # Trova ultimo updated_at
                last_update_row = max(wines_rows, key=lambda w: w.updated_at if w.updated_at else datetime.min)
                last_update = last_update_row.updated_at.isoformat() if last_update_row.updated_at else datetime.utcnow().isoformat()
            else:
                last_update = datetime.utcnow().isoformat()
            
            response = {
                "rows": rows,
                "facets": facets,
                "meta": {
                    "total_rows": len(rows),
                    "last_update": last_update
                }
            }
            
            logger.info(
                f"[VIEWER_API] Snapshot restituito con successo: rows={len(rows)}, "
                f"telegram_id={telegram_id}, business_name={business_name}, "
                f"facets_type_count={len(facets.get('type', {}))}, "
                f"facets_vintage_count={len(facets.get('vintage', {}))}, "
                f"facets_winery_count={len(facets.get('winery', {}))}"
            )
            return response
            
    except HTTPException as he:
        logger.error(
            f"[VIEWER_API] HTTPException durante snapshot: status={he.status_code}, "
            f"detail={he.detail}, token_length={len(token) if 'token' in locals() else 0}"
        )
        raise
    except Exception as e:
        logger.error(
            f"[VIEWER_API] Errore snapshot inventario: {e}, token_length={len(token) if 'token' in locals() else 0}",
            exc_info=True
        )
        raise HTTPException(status_code=500, detail=f"Errore interno: {str(e)}")


@router.get("/inventory/export.csv")
async def export_inventory_csv_endpoint(token: str = Query(...)):
    """
    Endpoint per viewer: export CSV inventario.
    Richiede token JWT valido come query parameter.
    
    Conforme a endpoint esistente in main.py.
    """
    try:
        # Valida token JWT
        token_data = validate_viewer_token(token)
        if not token_data:
            logger.warning(f"[VIEWER_EXPORT] Token JWT non valido o scaduto")
            raise HTTPException(status_code=401, detail="Token scaduto o non valido")
        
        telegram_id = token_data["telegram_id"]
        business_name = token_data["business_name"]
        
        logger.info(f"[VIEWER_EXPORT] Export CSV richiesto per telegram_id={telegram_id}, business_name={business_name}")
        
        async for db in get_db():
            # Verifica che utente esista
            stmt = select(User).where(User.telegram_id == telegram_id)
            result = await db.execute(stmt)
            user = result.scalar_one_or_none()
            
            if not user:
                raise HTTPException(status_code=404, detail="Utente non trovato")
            
            # Assicura che tabelle esistano
            user_tables = await ensure_user_tables(db, telegram_id, business_name)
            table_inventario = user_tables["inventario"]
            
            # Recupera tutti i vini
            query_wines = sql_text(f"""
                SELECT 
                    name,
                    producer,
                    vintage,
                    quantity,
                    selling_price,
                    wine_type,
                    region,
                    country,
                    grape_variety,
                    alcohol_content,
                    cost_price,
                    description,
                    notes
                FROM {table_inventario}
                WHERE user_id = :user_id
                ORDER BY name, vintage
            """)
            
            result = await db.execute(query_wines, {"user_id": user.id})
            wines_rows = result.fetchall()
            
            # Genera CSV
            output = io.StringIO()
            writer = csv.writer(output)
            
            # Header
            writer.writerow([
                "Nome",
                "Cantina",
                "Annata",
                "Quantità",
                "Prezzo (€)",
                "Tipo",
                "Regione",
                "Paese",
                "Vitigno",
                "Gradazione (%vol)",
                "Costo acquisto (€)",
                "Descrizione",
                "Note"
            ])
            
            # Righe dati
            for wine in wines_rows:
                writer.writerow([
                    wine.name or "",
                    wine.producer or "",
                    wine.vintage or "",
                    wine.quantity or 0,
                    f"{wine.selling_price:.2f}" if wine.selling_price else "",
                    wine.wine_type or "",
                    wine.region or "",
                    wine.country or "",
                    wine.grape_variety or "",
                    f"{wine.alcohol_content:.1f}" if wine.alcohol_content else "",
                    f"{wine.cost_price:.2f}" if wine.cost_price else "",
                    wine.description or "",
                    wine.notes or ""
                ])
            
            csv_content = output.getvalue()
            
            logger.info(f"[VIEWER_EXPORT] CSV generato: {len(wines_rows)} vini per {telegram_id}/{business_name}")
            
            return Response(
                content=csv_content,
                media_type="text/csv;charset=utf-8",
                headers={
                    "Content-Disposition": f'attachment; filename="inventario_{telegram_id}_{business_name.replace(" ", "_")}.csv"'
                }
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[VIEWER_EXPORT] Errore export CSV: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Errore interno: {str(e)}")


@router.post("/viewer/prepare-data")
async def prepare_viewer_data_endpoint(
    telegram_id: int = Form(...),
    business_name: str = Form(...),
    correlation_id: Optional[str] = Form(None)
):
    """
    Job 1: Estrae dati inventario dal DB e li prepara per il viewer.
    Salva in cache per essere recuperati dal viewer.
    
    Conforme a endpoint esistente in main.py.
    """
    try:
        logger.info(
            f"[VIEWER_PREPARE] Preparazione dati per telegram_id={telegram_id}, "
            f"business_name={business_name}, correlation_id={correlation_id}"
        )
        
        async for db in get_db():
            data = await prepare_viewer_data(
                db, telegram_id, business_name, correlation_id
            )
            
            logger.info(
                f"[VIEWER_PREPARE] Dati preparati con successo: rows={len(data.get('rows', []))}, "
                f"telegram_id={telegram_id}, correlation_id={correlation_id}"
            )
            break
        
        return {
            "status": "completed",
            "telegram_id": telegram_id,
            "message": "Dati preparati e pronti"
        }
        
    except Exception as e:
        logger.error(
            f"[VIEWER_PREPARE] Errore preparazione dati: {e}, "
            f"telegram_id={telegram_id}, correlation_id={correlation_id}",
            exc_info=True
        )
        raise HTTPException(status_code=500, detail=f"Errore interno: {str(e)}")


@router.get("/viewer/data")
async def get_viewer_data_endpoint(telegram_id: int = Query(...)):
    """
    Restituisce dati inventario preparati dalla cache.
    Chiamato dal viewer per ottenere i dati.
    
    Conforme a endpoint esistente in main.py.
    """
    try:
        logger.info(f"[VIEWER_DATA] Richiesta dati per telegram_id={telegram_id}")
        
        data, found = get_viewer_data_from_cache(telegram_id)
        
        if not found:
            logger.warning(f"[VIEWER_DATA] Dati non trovati in cache per telegram_id={telegram_id}")
            raise HTTPException(status_code=404, detail="Dati non disponibili. Riprova più tardi.")
        
        logger.info(
            f"[VIEWER_DATA] Dati restituiti: rows={len(data.get('rows', []))}, "
            f"telegram_id={telegram_id}"
        )
        
        return data
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"[VIEWER_DATA] Errore recupero dati: {e}, telegram_id={telegram_id}",
            exc_info=True
        )
        raise HTTPException(status_code=500, detail=f"Errore interno: {str(e)}")


@router.get("/viewer/{view_id}")
async def get_viewer_html_endpoint(view_id: str):
    """
    Serve HTML viewer generato dalla cache.
    
    Conforme a endpoint esistente in main.py.
    """
    try:
        logger.info(f"[VIEWER_GET] Richiesta HTML per view_id={view_id}")
        
        html, found = get_viewer_html_from_cache(view_id)
        
        if not found:
            logger.warning(f"[VIEWER_GET] View ID {view_id} non trovato o scaduto")
            raise HTTPException(status_code=404, detail="View non trovata o scaduta")
        
        logger.info(f"[VIEWER_GET] HTML servito per view_id={view_id}, length={len(html)}")
        
        return HTMLResponse(content=html)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[VIEWER_GET] Errore servendo HTML: {e}, view_id={view_id}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Errore interno: {str(e)}")

