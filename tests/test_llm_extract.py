"""
Test unitari per Stage 3 (LLM Mode) con mock OpenAI.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import json

from ingest.llm_extract import (
    prepare_text_input,
    chunk_text,
    extract_with_llm,
    deduplicate_wines,
    extract_llm_mode
)


class TestLLMExtract:
    """Test per Stage 3 (LLM Mode)."""
    
    def test_prepare_text_input_csv(self):
        """Test preparazione input testo da CSV."""
        content = b"Nome,Cantina,Annata\nChianti,Barone,2020"
        text = prepare_text_input(content, "csv")
        
        assert isinstance(text, str)
        assert "Chianti" in text
        assert "Barone" in text
    
    def test_prepare_text_input_txt(self):
        """Test preparazione input testo da TXT."""
        content = b"Chianti Classico della cantina Barone Ricasoli anno 2020"
        text = prepare_text_input(content, "txt")
        
        assert isinstance(text, str)
        assert "Chianti" in text
    
    def test_chunk_text_small(self):
        """Test chunking testo piccolo (non necessario)."""
        text = "Test content " * 100  # ~1.4 KB
        chunks = chunk_text(text, chunk_size=4000, overlap=1000)
        
        assert len(chunks) == 1
        assert chunks[0] == text
    
    def test_chunk_text_large(self):
        """Test chunking testo grande."""
        text = "Test content " * 10000  # ~140 KB
        chunks = chunk_text(text, chunk_size=4000, overlap=1000)
        
        assert len(chunks) > 1
        # Verifica overlap
        assert len(chunks[0]) <= 4000
    
    @pytest.mark.asyncio
    async def test_extract_with_llm_success(self):
        """Test estrazione vini da testo con LLM."""
        text_chunk = "Chianti Classico della cantina Barone Ricasoli anno 2020 abbiamo 12 bottiglie a 18.50 euro tipo rosso"
        
        # Mock risposta OpenAI
        mock_response = [
            {
                "name": "Chianti Classico",
                "winery": "Barone Ricasoli",
                "vintage": 2020,
                "qty": 12,
                "price": 18.50,
                "type": "Rosso"
            }
        ]
        
        with patch('ingest.llm_extract.get_openai_client') as mock_client:
            mock_chat = AsyncMock()
            mock_chat.completions.create.return_value = MagicMock(
                choices=[MagicMock(message=MagicMock(content=json.dumps(mock_response)))]
            )
            mock_client.return_value = mock_chat
            
            wines = await extract_with_llm(text_chunk)
            
            assert isinstance(wines, list)
            assert len(wines) == 1
            assert wines[0]["name"] == "Chianti Classico"
            assert wines[0]["vintage"] == 2020
    
    @pytest.mark.asyncio
    async def test_extract_with_llm_markdown_removal(self):
        """Test rimozione markdown code blocks."""
        text_chunk = "Test content"
        
        # Mock risposta con markdown
        mock_response_with_markdown = "```json\n" + json.dumps([{"name": "Test"}]) + "\n```"
        
        with patch('ingest.llm_extract.get_openai_client') as mock_client:
            mock_chat = AsyncMock()
            mock_chat.completions.create.return_value = MagicMock(
                choices=[MagicMock(message=MagicMock(content=mock_response_with_markdown))]
            )
            mock_client.return_value = mock_chat
            
            wines = await extract_with_llm(text_chunk)
            
            assert isinstance(wines, list)
    
    def test_deduplicate_wines_merge(self):
        """Test deduplicazione con merge quantità."""
        wines = [
            {"name": "Chianti", "winery": "Barone", "vintage": 2020, "qty": 12},
            {"name": "Chianti", "winery": "Barone", "vintage": 2020, "qty": 6},  # Duplicato
            {"name": "Barolo", "winery": "Vietti", "vintage": 2018, "qty": 6},
        ]
        
        deduplicated = deduplicate_wines(wines, merge_quantities=True)
        
        assert len(deduplicated) == 2
        # Chianti dovrebbe avere qty = 18 (12 + 6)
        chianti = next((w for w in deduplicated if w["name"] == "Chianti"), None)
        assert chianti is not None
        assert chianti["qty"] == 18
    
    def test_deduplicate_wines_no_merge(self):
        """Test deduplicazione senza merge."""
        wines = [
            {"name": "Chianti", "winery": "Barone", "vintage": 2020, "qty": 12},
            {"name": "Chianti", "winery": "Barone", "vintage": 2020, "qty": 6},  # Duplicato
        ]
        
        deduplicated = deduplicate_wines(wines, merge_quantities=False)
        
        assert len(deduplicated) == 1
        # Dovrebbe mantenere primo (qty = 12)
        assert deduplicated[0]["qty"] == 12
    
    @pytest.mark.asyncio
    async def test_extract_llm_mode_success(self):
        """Test extract_llm_mode completo."""
        content = b"Chianti Classico della cantina Barone Ricasoli anno 2020 abbiamo 12 bottiglie a 18.50 euro tipo rosso"
        
        # Mock risposta OpenAI
        mock_response = [
            {
                "name": "Chianti Classico",
                "winery": "Barone Ricasoli",
                "vintage": 2020,
                "qty": 12,
                "price": 18.50,
                "type": "Rosso"
            }
        ]
        
        with patch('ingest.llm_extract.get_openai_client') as mock_client, \
             patch('ingest.llm_extract.get_config') as mock_config:
            
            mock_config.return_value.llm_fallback_enabled = True
            
            mock_chat = AsyncMock()
            mock_chat.completions.create.return_value = MagicMock(
                choices=[MagicMock(message=MagicMock(content=json.dumps(mock_response)))]
            )
            mock_client.return_value = mock_chat
            
            wines_data, metrics, decision = await extract_llm_mode(
                content, "test.txt", "txt", telegram_id=123, business_name="Test", correlation_id="test-123"
            )
            
            assert decision == 'save'
            assert len(wines_data) > 0
            assert metrics["rows_valid"] > 0
    
    @pytest.mark.asyncio
    async def test_extract_llm_mode_feature_flag_disabled(self):
        """Test che rispetta feature flag disabilitato."""
        content = b"Test content"
        
        with patch('ingest.llm_extract.get_config') as mock_config:
            mock_config.return_value.llm_fallback_enabled = False
            
            wines_data, metrics, decision = await extract_llm_mode(
                content, "test.txt", "txt", telegram_id=123, business_name="Test"
            )
            
            # Se feature flag disabilitato, dovrebbe ritornare error
            assert decision == 'error'

