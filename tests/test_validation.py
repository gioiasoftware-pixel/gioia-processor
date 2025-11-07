"""
Test unitari per validazione Pydantic.
"""
import pytest
from pydantic import ValidationError

from ingest.validation import WineItemModel, validate_batch, wine_model_to_dict


class TestWineItemModel:
    """Test per WineItemModel (Pydantic)."""
    
    def test_valid_wine(self):
        """Test vino valido."""
        wine = WineItemModel(
            name="Chianti Classico",
            winery="Barone Ricasoli",
            vintage=2020,
            qty=12,
            price=18.50,
            type="Rosso"
        )
        
        assert wine.name == "Chianti Classico"
        assert wine.winery == "Barone Ricasoli"
        assert wine.vintage == 2020
        assert wine.qty == 12
        assert wine.price == 18.50
        assert wine.type == "Rosso"
    
    def test_wine_with_optional_fields(self):
        """Test vino con campi opzionali."""
        wine = WineItemModel(
            name="Barolo",
            qty=6
        )
        
        assert wine.name == "Barolo"
        assert wine.winery is None
        assert wine.vintage is None
        assert wine.qty == 6
        assert wine.price is None
        assert wine.type is None
    
    def test_wine_name_trim(self):
        """Test trim del nome."""
        wine = WineItemModel(
            name="  Chianti  ",
            qty=12
        )
        assert wine.name == "Chianti"
    
    def test_wine_name_min_length(self):
        """Test nome minimo 1 carattere."""
        with pytest.raises(ValidationError):
            WineItemModel(name="", qty=12)
    
    def test_wine_vintage_valid_range(self):
        """Test annata range valido."""
        wine = WineItemModel(name="Test", vintage=2020, qty=12)
        assert wine.vintage == 2020
        
        wine = WineItemModel(name="Test", vintage=1900, qty=12)
        assert wine.vintage == 1900
        
        wine = WineItemModel(name="Test", vintage=2099, qty=12)
        assert wine.vintage == 2099
    
    def test_wine_vintage_out_of_range(self):
        """Test annata fuori range diventa None."""
        wine = WineItemModel(name="Test", vintage=1899, qty=12)
        assert wine.vintage is None
        
        wine = WineItemModel(name="Test", vintage=2100, qty=12)
        assert wine.vintage is None
    
    def test_wine_qty_default(self):
        """Test quantità default 0."""
        wine = WineItemModel(name="Test")
        assert wine.qty == 0
    
    def test_wine_qty_negative(self):
        """Test quantità negativa diventa 0."""
        wine = WineItemModel(name="Test", qty=-5)
        assert wine.qty == 0
    
    def test_wine_price_negative(self):
        """Test prezzo negativo non valido."""
        with pytest.raises(ValidationError):
            WineItemModel(name="Test", qty=12, price=-10.0)
    
    def test_wine_type_literal(self):
        """Test tipo vino enum."""
        wine = WineItemModel(name="Test", qty=12, type="Rosso")
        assert wine.type == "Rosso"
        
        wine = WineItemModel(name="Test", qty=12, type="Bianco")
        assert wine.type == "Bianco"
        
        wine = WineItemModel(name="Test", qty=12, type="Spumante")
        assert wine.type == "Spumante"
    
    def test_wine_model_to_dict(self):
        """Test conversione modello a dict."""
        wine = WineItemModel(
            name="Chianti",
            winery="Barone",
            vintage=2020,
            qty=12,
            price=18.50,
            type="Rosso"
        )
        
        wine_dict = wine_model_to_dict(wine)
        
        assert isinstance(wine_dict, dict)
        assert wine_dict["name"] == "Chianti"
        assert wine_dict["winery"] == "Barone"
        assert wine_dict["vintage"] == 2020
        assert wine_dict["qty"] == 12
        assert wine_dict["price"] == 18.50
        assert wine_dict["type"] == "Rosso"


class TestBatchValidation:
    """Test per validazione batch."""
    
    def test_validate_batch_all_valid(self):
        """Test batch con tutti vini validi."""
        wines_data = [
            {"name": "Chianti", "winery": "Barone", "vintage": 2020, "qty": 12},
            {"name": "Barolo", "winery": "Vietti", "vintage": 2018, "qty": 6},
        ]
        
        valid_wines, rejected_wines, stats = validate_batch(wines_data)
        
        assert len(valid_wines) == 2
        assert len(rejected_wines) == 0
        assert stats["rows_total"] == 2
        assert stats["rows_valid"] == 2
        assert stats["rows_rejected"] == 0
    
    def test_validate_batch_some_rejected(self):
        """Test batch con alcuni vini rifiutati."""
        wines_data = [
            {"name": "Chianti", "winery": "Barone", "vintage": 2020, "qty": 12},  # Valido
            {"name": "", "winery": "Barone", "vintage": 2020, "qty": 12},  # Nome vuoto
            {"name": "Barolo", "winery": "Vietti", "vintage": 1899, "qty": 6},  # Annata fuori range
        ]
        
        valid_wines, rejected_wines, stats = validate_batch(wines_data)
        
        assert len(valid_wines) == 1
        assert len(rejected_wines) == 2
        assert stats["rows_total"] == 3
        assert stats["rows_valid"] == 1
        assert stats["rows_rejected"] == 2
        assert len(stats["rejection_reasons"]) == 2
    
    def test_validate_batch_empty(self):
        """Test batch vuoto."""
        wines_data = []
        
        valid_wines, rejected_wines, stats = validate_batch(wines_data)
        
        assert len(valid_wines) == 0
        assert len(rejected_wines) == 0
        assert stats["rows_total"] == 0
        assert stats["rows_valid"] == 0
        assert stats["rows_rejected"] == 0





