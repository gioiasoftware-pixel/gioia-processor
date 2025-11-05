"""
Validation (Pydantic models) per Stage 1.

Definisce WineItemModel e funzioni di validazione batch.
"""
import logging
from typing import List, Dict, Any, Optional, Literal, Tuple
from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger(__name__)


class WineItemModel(BaseModel):
    """
    Modello Pydantic v2 per riga inventario vino.
    
    Schema conforme a "Update processor.md" - Sezione "Schema dati target".
    """
    name: str = Field(..., min_length=1, description="Nome vino (obbligatorio, min 1 char)")
    winery: Optional[str] = Field(None, description="Produttore/cantina (opzionale)")
    vintage: Optional[int] = Field(None, ge=1900, le=2099, description="Annata (1900-2099 o null)")
    qty: int = Field(default=0, ge=0, description="Quantità bottiglie (>= 0, default 0)")
    price: Optional[float] = Field(None, ge=0.0, description="Prezzo unitario (>= 0 o null)")
    type: Optional[Literal["Rosso", "Bianco", "Rosato", "Spumante", "Altro"]] = Field(
        None, 
        description="Tipo vino (enum o null)"
    )
    
    @field_validator('name')
    @classmethod
    def validate_name(cls, v: str) -> str:
        """Valida e normalizza nome vino."""
        if not v:
            raise ValueError("name deve essere non vuoto")
        return v.strip()
    
    @field_validator('winery')
    @classmethod
    def validate_winery(cls, v: Optional[str]) -> Optional[str]:
        """Valida e normalizza winery."""
        if v is None:
            return None
        return v.strip() if v.strip() else None
    
    @field_validator('vintage')
    @classmethod
    def validate_vintage(cls, v: Optional[int]) -> Optional[int]:
        """Valida vintage (1900-2099)."""
        if v is None:
            return None
        if v < 1900 or v > 2099:
            return None  # Fuori range = null (non errore)
        return v
    
    @field_validator('qty')
    @classmethod
    def validate_qty(cls, v: int) -> int:
        """Valida quantità (>= 0)."""
        if v < 0:
            return 0  # Negativo = 0 (default)
        return v
    
    @field_validator('price')
    @classmethod
    def validate_price(cls, v: Optional[float]) -> Optional[float]:
        """Valida prezzo (>= 0)."""
        if v is None:
            return None
        if v < 0:
            return None  # Negativo = null
        return v
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "name": "Barolo",
                "winery": "Giacomo Conterno",
                "vintage": 2018,
                "qty": 6,
                "price": 42.5,
                "type": "Rosso"
            }
        }
    }


def validate_batch(wines_data: List[Dict[str, Any]]) -> Tuple[List[WineItemModel], List[Dict[str, Any]], Dict[str, Any]]:
    """
    Valida batch di vini con Pydantic.
    
    Args:
        wines_data: Lista dizionari con dati vini grezzi
    
    Returns:
        Tuple (valid_wines, rejected_wines, stats):
        - valid_wines: Lista WineItemModel validi
        - rejected_wines: Lista dizionari con errori (include 'error' e 'data')
        - stats: Dict con statistiche (rows_total, rows_valid, rows_rejected, rejection_reasons)
    """
    valid_wines = []
    rejected_wines = []
    rejection_reasons: Dict[str, int] = {}
    
    for idx, wine_data in enumerate(wines_data):
        try:
            # Valida con Pydantic
            wine = WineItemModel(**wine_data)
            valid_wines.append(wine)
            logger.debug(f"[VALIDATION] Vino {idx+1} valido: name={wine.name}, qty={wine.qty}")
        except Exception as e:
            # Cattura errore validazione
            error_msg = str(e)
            error_type = type(e).__name__
            
            # Log dettagliato per debug
            logger.warning(
                f"[VALIDATION] Vino {idx+1} rifiutato: {error_type} - {error_msg[:100]}"
            )
            logger.debug(f"[VALIDATION] Dati vino rifiutato: {wine_data}")
            
            # Conta motivo rifiuto
            if error_type not in rejection_reasons:
                rejection_reasons[error_type] = 0
            rejection_reasons[error_type] += 1
            
            rejected_wines.append({
                'index': idx,
                'data': wine_data,
                'error': error_msg,
                'error_type': error_type
            })
    
    stats = {
        'rows_total': len(wines_data),
        'rows_valid': len(valid_wines),
        'rows_rejected': len(rejected_wines),
        'rejection_reasons': rejection_reasons
    }
    
    logger.info(
        f"[VALIDATION] Batch validation: {stats['rows_valid']}/{stats['rows_total']} validi, "
        f"{stats['rows_rejected']} rifiutati"
    )
    
    if stats['rows_rejected'] > 0:
        # Log motivi rifiuto per debug
        logger.info(f"[VALIDATION] Motivi rifiuto: {rejection_reasons}")
        # Log primi 3 vini rifiutati per esempio
        for i, rejected in enumerate(rejected_wines[:3]):
            logger.debug(
                f"[VALIDATION] Vino rifiutato {i+1}: {rejected.get('error_type')} - "
                f"name={rejected['data'].get('name', 'N/A')[:30]}, "
                f"qty={rejected['data'].get('qty', 'N/A')}"
            )
    
    return valid_wines, rejected_wines, stats


def wine_model_to_dict(wine: WineItemModel) -> Dict[str, Any]:
    """
    Converte WineItemModel in dict per compatibilità con codice esistente.
    
    Args:
        wine: WineItemModel
    
    Returns:
        Dict con dati vino
    """
    return wine.model_dump(exclude_none=False)

