"""
Generatore HTML per viewer con dati inventario embedded
"""
import json
import logging
from datetime import datetime
from typing import Dict, Any, List
from sqlalchemy import text as sql_text

logger = logging.getLogger(__name__)


async def generate_viewer_html_from_db(
    db,
    telegram_id: int,
    business_name: str,
    correlation_id: str = None
) -> str:
    """
    Estrae dati inventario dal DB e genera HTML completo.
    """
    from database import ensure_user_tables, User
    from sqlalchemy import select
    from datetime import datetime
    
    logger.info(
        f"[VIEWER_GENERATOR] Estrazione dati inventario per telegram_id={telegram_id}, "
        f"business_name={business_name}, correlation_id={correlation_id}"
    )
    
    # Verifica utente
    stmt = select(User).where(User.telegram_id == telegram_id)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()
    
    if not user:
        raise ValueError(f"Utente non trovato per telegram_id={telegram_id}")
    
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
    
    # Converte a dict per generate_viewer_html
    wines_data = []
    for wine in wines_rows:
        wines_data.append({
            "name": wine.name,
            "producer": wine.producer,
            "vintage": wine.vintage,
            "quantity": wine.quantity,
            "selling_price": wine.selling_price,
            "wine_type": wine.wine_type,
            "min_quantity": wine.min_quantity,
            "updated_at": wine.updated_at
        })
    
    logger.info(
        f"[VIEWER_GENERATOR] Recuperati {len(wines_data)} vini dal DB, "
        f"telegram_id={telegram_id}, correlation_id={correlation_id}"
    )
    
    # Genera HTML
    return await generate_viewer_html(wines_data, telegram_id, business_name, correlation_id)


async def generate_viewer_html(
    wines_data: List[Dict[str, Any]],
    telegram_id: int,
    business_name: str,
    correlation_id: str = None
) -> str:
    """
    Genera HTML completo del viewer con dati inventario embedded.
    
    Args:
        wines_data: Lista di vini dal database
        telegram_id: ID Telegram utente
        business_name: Nome locale
        correlation_id: ID correlazione per logging
        
    Returns:
        HTML completo come stringa
    """
    try:
        logger.info(
            f"[VIEWER_GENERATOR] Generazione HTML per telegram_id={telegram_id}, "
            f"business_name={business_name}, wines_count={len(wines_data)}, "
            f"correlation_id={correlation_id}"
        )
        
        # Formatta dati per viewer
        rows = []
        facets = {
            "type": {},
            "vintage": {},
            "winery": {}
        }
        
        for wine in wines_data:
            # Formatta riga
            row = {
                "name": wine.get("name") or "-",
                "winery": wine.get("producer") or "-",
                "vintage": wine.get("vintage"),
                "qty": wine.get("quantity") or 0,
                "price": float(wine.get("selling_price")) if wine.get("selling_price") else 0.0,
                "type": wine.get("wine_type") or "Altro",
                "critical": (
                    wine.get("quantity") is not None 
                    and wine.get("min_quantity") is not None 
                    and wine.get("quantity") <= wine.get("min_quantity")
                )
            }
            rows.append(row)
            
            # Calcola facets
            wine_type = wine.get("wine_type") or "Altro"
            facets["type"][wine_type] = facets["type"].get(wine_type, 0) + 1
            
            if wine.get("vintage"):
                vintage_str = str(wine.get("vintage"))
                facets["vintage"][vintage_str] = facets["vintage"].get(vintage_str, 0) + 1
            
            if wine.get("producer"):
                facets["winery"][wine.get("producer")] = facets["winery"].get(wine.get("producer"), 0) + 1
        
        # Meta info
        last_update = datetime.utcnow().isoformat()
        
        # Dati embedded in JSON
        embedded_data = {
            "rows": rows,
            "facets": facets,
            "meta": {
                "total_rows": len(rows),
                "last_update": last_update
            }
        }
        
        # Leggi template HTML base
        html_template = _get_html_template()
        
        # Inietta dati embedded nell'HTML
        html = html_template.replace(
            '// EMBEDDED_DATA_PLACEHOLDER',
            f'window.EMBEDDED_INVENTORY_DATA = {json.dumps(embedded_data, ensure_ascii=False)};'
        )
        
        logger.info(
            f"[VIEWER_GENERATOR] HTML generato con successo: rows={len(rows)}, "
            f"telegram_id={telegram_id}, correlation_id={correlation_id}"
        )
        
        return html
        
    except Exception as e:
        logger.error(
            f"[VIEWER_GENERATOR] Errore generazione HTML: {e}, "
            f"telegram_id={telegram_id}, correlation_id={correlation_id}",
            exc_info=True
        )
        raise


# Cache in-memory per HTML generati (view_id -> (html, timestamp))
_viewer_cache = {}
_cache_expiry_seconds = 3600  # 1 ora


def get_viewer_html_from_cache(view_id: str) -> tuple[str, bool]:
    """
    Recupera HTML dalla cache se disponibile e non scaduto.
    
    Returns:
        (html, found) - HTML e flag se trovato
    """
    import time
    
    if view_id not in _viewer_cache:
        return None, False
    
    html, timestamp = _viewer_cache[view_id]
    
    # Verifica scadenza
    if time.time() - timestamp > _cache_expiry_seconds:
        logger.info(f"[VIEWER_CACHE] View ID {view_id} scaduto, rimuovo dalla cache")
        del _viewer_cache[view_id]
        return None, False
    
    return html, True


def store_viewer_html(view_id: str, html: str):
    """
    Salva HTML nella cache.
    """
    import time
    _viewer_cache[view_id] = (html, time.time())
    logger.info(f"[VIEWER_CACHE] HTML salvato in cache per view_id={view_id}")


def _get_html_template() -> str:
    """
    Restituisce template HTML base del viewer.
    I placeholder verranno sostituiti:
    - // EMBEDDED_DATA_PLACEHOLDER → dati inventario JSON
    - // CSS_PLACEHOLDER → CSS inline
    - // JS_PLACEHOLDER → JS inline
    """
    return '''<!DOCTYPE html>
<html lang="it">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Vineventory - Inventario Vini</title>
    <link rel="stylesheet" href="https://vineinventory-viewer-production.up.railway.app/styles.css">
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
    <script>
        // EMBEDDED_DATA_PLACEHOLDER
        console.log("[VIEWER] Dati embedded caricati:", window.EMBEDDED_INVENTORY_DATA);
    </script>
</head>
<body>
    <!-- Banner Error (hidden by default) -->
    <div id="error-banner" class="error-banner hidden">
        <span>⚠️ Link scaduto o non valido</span>
    </div>

    <!-- Header -->
    <header class="header">
        <div class="header-left">
            <div class="logo-container">
                <img src="https://vineinventory-viewer-production.up.railway.app/assets/logo.png" alt="Gio.ia Logo" class="logo">
            </div>
            <div class="title-section">
                <h1 class="title">Vineventory</h1>
                <p class="meta" id="meta-info">Caricamento...</p>
            </div>
        </div>
        <div class="header-right">
            <div class="search-container">
                <svg class="search-icon" width="16" height="16" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg">
                    <path d="M7.33333 12.6667C10.2789 12.6667 12.6667 10.2789 12.6667 7.33333C12.6667 4.38781 10.2789 2 7.33333 2C4.38781 2 2 4.38781 2 7.33333C2 10.2789 4.38781 12.6667 7.33333 12.6667Z" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
                    <path d="M14 14L11.1 11.1" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
                </svg>
                <input type="text" id="search-input" class="search-input" placeholder="Search inventory...">
            </div>
            <a href="#" id="download-csv" class="download-btn">
                Download CSV
            </a>
        </div>
    </header>

    <!-- Main Content -->
    <div class="container">
        <!-- Sidebar Filters -->
        <aside class="sidebar">
            <h2 class="filters-title">FILTERS</h2>
            
            <!-- Tipologia Filter -->
            <div class="filter-section">
                <button class="filter-header" data-filter="type">
                    <span>TIPOLOGIA</span>
                    <svg class="filter-icon expanded" width="12" height="12" viewBox="0 0 12 12" fill="none" xmlns="http://www.w3.org/2000/svg">
                        <path d="M9 4.5L6 7.5L3 4.5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
                    </svg>
                </button>
                <div class="filter-content" id="filter-type">
                    <!-- Popolato dinamicamente -->
                </div>
            </div>

            <!-- Annata Filter -->
            <div class="filter-section">
                <button class="filter-header" data-filter="vintage">
                    <span>ANNATA</span>
                    <svg class="filter-icon" width="12" height="12" viewBox="0 0 12 12" fill="none" xmlns="http://www.w3.org/2000/svg">
                        <path d="M9 4.5L6 7.5L3 4.5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
                    </svg>
                </button>
                <div class="filter-content hidden" id="filter-vintage">
                    <!-- Popolato dinamicamente -->
                </div>
            </div>

            <!-- Cantina Filter -->
            <div class="filter-section">
                <button class="filter-header" data-filter="winery">
                    <span>CANTINA</span>
                    <svg class="filter-icon" width="12" height="12" viewBox="0 0 12 12" fill="none" xmlns="http://www.w3.org/2000/svg">
                        <path d="M9 4.5L6 7.5L3 4.5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
                    </svg>
                </button>
                <div class="filter-content hidden" id="filter-winery">
                    <!-- Popolato dinamicamente -->
                </div>
            </div>
        </aside>

        <!-- Main Table Area -->
        <main class="main-content">
            <div class="table-container">
                <table class="data-table" id="data-table">
                    <thead>
                        <tr>
                            <th>Nome</th>
                            <th>Annata</th>
                            <th>Quantità</th>
                            <th>Prezzo (€)</th>
                            <th>Scorta critica</th>
                        </tr>
                    </thead>
                    <tbody id="table-body">
                        <tr>
                            <td colspan="5" class="loading">Caricamento dati...</td>
                        </tr>
                    </tbody>
                </table>
            </div>

            <!-- Pagination -->
            <div class="pagination" id="pagination">
                <!-- Popolato dinamicamente -->
            </div>
        </main>
    </div>

    <script src="https://vineinventory-viewer-production.up.railway.app/app.js"></script>
    <style>
        /* CSS inline per garantire funzionamento standalone */
        /* CSS_PLACEHOLDER */
    </style>
</body>
</html>'''

