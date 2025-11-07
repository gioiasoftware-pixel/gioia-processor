"""
Configurazione pytest e fixture comuni.
"""
import pytest
import os
from unittest.mock import MagicMock, patch


@pytest.fixture
def mock_config():
    """Fixture per mock configurazione."""
    with patch('core.config.get_config') as mock:
        config = MagicMock()
        config.ia_targeted_enabled = True
        config.llm_fallback_enabled = True
        config.ocr_enabled = True
        config.schema_score_th = 0.7
        config.min_valid_rows = 0.6
        config.header_confidence_th = 0.75
        config.batch_size_ambiguous_rows = 20
        config.max_llm_tokens = 300
        config.llm_model_targeted = "gpt-4o-mini"
        config.llm_model_extract = "gpt-4o"
        config.ocr_extensions = "pdf,jpg,jpeg,png"
        config.db_insert_batch_size = 500
        mock.return_value = config
        yield config


@pytest.fixture
def sample_csv_content():
    """Fixture per contenuto CSV di esempio."""
    return b"Nome,Cantina,Annata,Quantità\nChianti,Barone,2020,12"


@pytest.fixture
def sample_wine_data():
    """Fixture per dati vino di esempio."""
    return {
        "name": "Chianti Classico",
        "winery": "Barone Ricasoli",
        "vintage": 2020,
        "qty": 12,
        "price": 18.50,
        "type": "Rosso"
    }





