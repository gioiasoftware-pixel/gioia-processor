"""
Test unitari per normalizzazione header e valori.
"""
import pytest

from ingest.normalization import (
    normalize_column_name,
    map_headers,
    normalize_vintage,
    normalize_qty,
    normalize_price,
    normalize_wine_type,
    normalize_values,
    classify_wine_type
)


class TestHeaderNormalization:
    """Test per normalizzazione header."""
    
    def test_normalize_column_name_lowercase(self):
        """Test lowercase."""
        assert normalize_column_name("Nome") == "nome"
    
    def test_normalize_column_name_trim(self):
        """Test trim spazi."""
        assert normalize_column_name("  Nome  ") == "nome"
    
    def test_normalize_column_name_remove_symbols(self):
        """Test rimozione simboli."""
        assert normalize_column_name("Nome Prodotto!") == "nome prodotto"
        assert normalize_column_name("Prezzo (€)") == "prezzo "
    
    def test_normalize_column_name_multiple_spaces(self):
        """Test rimozione spazi multipli."""
        assert normalize_column_name("Nome  Prodotto") == "nome prodotto"
    
    def test_map_headers_exact_match(self):
        """Test mapping header con match esatto."""
        headers = ["nome", "cantina", "annata"]
        standard_headers = ["name", "winery", "vintage"]
        mapping = map_headers(headers, standard_headers)
        
        assert mapping["nome"] == "name"
        assert mapping["cantina"] == "winery"
        assert mapping["annata"] == "vintage"
    
    def test_map_headers_fuzzy_match(self):
        """Test mapping header con fuzzy matching."""
        headers = ["prodotto", "produttore", "anno"]
        standard_headers = ["name", "winery", "vintage"]
        mapping = map_headers(headers, standard_headers, confidence_threshold=0.7)
        
        # Dovrebbe mappare "prodotto" -> "name", "produttore" -> "winery", "anno" -> "vintage"
        assert len(mapping) > 0


class TestValueNormalization:
    """Test per normalizzazione valori."""
    
    def test_normalize_vintage_valid(self):
        """Test normalizzazione annata valida."""
        assert normalize_vintage("2020") == 2020
        assert normalize_vintage("2018") == 2018
        assert normalize_vintage("2020") == 2020
    
    def test_normalize_vintage_out_of_range(self):
        """Test annata fuori range."""
        assert normalize_vintage("1899") is None  # Troppo vecchia
        assert normalize_vintage("2100") is None  # Troppo futura
    
    def test_normalize_vintage_invalid(self):
        """Test annata non valida."""
        assert normalize_vintage("invalid") is None
        assert normalize_vintage("") is None
    
    def test_normalize_qty_integer(self):
        """Test normalizzazione quantità intera."""
        assert normalize_qty("12") == 12
        assert normalize_qty("0") == 0
        assert normalize_qty("100") == 100
    
    def test_normalize_qty_with_text(self):
        """Test quantità con testo."""
        assert normalize_qty("12 bottiglie") == 12
        assert normalize_qty("6 pz") == 6
        assert normalize_qty("quantità: 24") == 24
    
    def test_normalize_qty_default(self):
        """Test quantità default."""
        assert normalize_qty("") == 0
        assert normalize_qty(None) == 0
        assert normalize_qty("invalid") == 0
    
    def test_normalize_price_float(self):
        """Test normalizzazione prezzo float."""
        assert normalize_price("18.50") == 18.50
        assert normalize_price("45.00") == 45.00
    
    def test_normalize_price_european_comma(self):
        """Test prezzo con virgola europea."""
        assert normalize_price("18,50") == 18.50
        assert normalize_price("45,00") == 45.00
    
    def test_normalize_price_with_symbols(self):
        """Test prezzo con simboli."""
        assert normalize_price("€18.50") == 18.50
        assert normalize_price("18.50€") == 18.50
    
    def test_normalize_wine_type_rosso(self):
        """Test normalizzazione tipo rosso."""
        assert normalize_wine_type("Rosso") == "Rosso"
        assert normalize_wine_type("rosso") == "Rosso"
        assert normalize_wine_type("RED") == "Rosso"
        assert normalize_wine_type("Red Wine") == "Rosso"
    
    def test_normalize_wine_type_bianco(self):
        """Test normalizzazione tipo bianco."""
        assert normalize_wine_type("Bianco") == "Bianco"
        assert normalize_wine_type("bianco") == "Bianco"
        assert normalize_wine_type("WHITE") == "Bianco"
        assert normalize_wine_type("White Wine") == "Bianco"
    
    def test_normalize_wine_type_spumante(self):
        """Test normalizzazione tipo spumante."""
        assert normalize_wine_type("Spumante") == "Spumante"
        assert normalize_wine_type("Champagne") == "Spumante"
        assert normalize_wine_type("Sparkling") == "Spumante"
    
    def test_classify_wine_type_from_name(self):
        """Test classificazione tipo da nome."""
        assert classify_wine_type("Chianti") == "Rosso"
        assert classify_wine_type("Barolo") == "Rosso"
        assert classify_wine_type("Pinot Grigio") == "Bianco"
        assert classify_wine_type("Prosecco") == "Spumante"
        assert classify_wine_type("Champagne") == "Spumante"
    
    def test_normalize_values_complete_row(self):
        """Test normalizzazione completa riga."""
        row = {
            "name": "Chianti Classico",
            "winery": "Barone Ricasoli",
            "vintage": "2020",
            "qty": "12 bottiglie",
            "price": "18,50",
            "type": "rosso"
        }
        
        normalized = normalize_values(row)
        
        assert normalized["name"] == "Chianti Classico"
        assert normalized["winery"] == "Barone Ricasoli"
        assert normalized["vintage"] == 2020
        assert normalized["qty"] == 12
        assert normalized["price"] == 18.50
        assert normalized["type"] == "Rosso"

