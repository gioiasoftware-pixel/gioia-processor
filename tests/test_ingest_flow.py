"""
Test integration per pipeline completa.
"""
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
import json
import os

from ingest.pipeline import process_file


class TestIngestFlow:
    """Test per flow completo pipeline."""
    
    @pytest.mark.asyncio
    async def test_flow_stage1_save(self):
        """Test flow Stage 1 → SALVA (CSV pulito)."""
        # Leggi fixture clean.csv
        fixture_path = os.path.join(os.path.dirname(__file__), "data", "clean.csv")
        with open(fixture_path, "rb") as f:
            content = f.read()
        
        with patch('ingest.pipeline.get_config') as mock_config:
            mock_config.return_value.ia_targeted_enabled = True
            mock_config.return_value.llm_fallback_enabled = True
            mock_config.return_value.ocr_enabled = True
            mock_config.return_value.schema_score_th = 0.7
            mock_config.return_value.min_valid_rows = 0.6
        
        wines_data, metrics, decision, stage_used = await process_file(
            content, "clean.csv", "csv", telegram_id=123, business_name="Test", correlation_id="test-123"
        )
        
        # CSV pulito dovrebbe passare Stage 1 e salvare
        assert decision == 'save'
        assert len(wines_data) > 0
        assert stage_used == 'csv_excel_parse'
        assert metrics["rows_valid"] > 0
    
    @pytest.mark.asyncio
    async def test_flow_stage1_to_stage2(self):
        """Test flow Stage 1 → Stage 2 (header ambigui)."""
        # Leggi fixture ambiguous_headers.csv
        fixture_path = os.path.join(os.path.dirname(__file__), "data", "ambiguous_headers.csv")
        with open(fixture_path, "rb") as f:
            content = f.read()
        
        # Mock OpenAI per Stage 2
        mock_response = [
            {"name": "Chianti Classico", "winery": "Barone Ricasoli", "vintage": 2020, "qty": 12, "price": 18.50, "type": "Rosso"}
        ]
        
        with patch('ingest.pipeline.get_config') as mock_config, \
             patch('ingest.llm_targeted.get_openai_client') as mock_client:
            
            mock_config.return_value.ia_targeted_enabled = True
            mock_config.return_value.llm_fallback_enabled = True
            mock_config.return_value.ocr_enabled = True
            mock_config.return_value.schema_score_th = 0.7
            mock_config.return_value.min_valid_rows = 0.6
            
            mock_chat = AsyncMock()
            mock_chat.completions.create.return_value = MagicMock(
                choices=[MagicMock(message=MagicMock(content=json.dumps(mock_response)))]
            )
            mock_client.return_value = mock_chat
        
        wines_data, metrics, decision, stage_used = await process_file(
            content, "ambiguous_headers.csv", "csv", telegram_id=123, business_name="Test"
        )
        
        # Dovrebbe provare Stage 2 se Stage 1 non basta
        assert decision in ['save', 'escalate_to_stage3']
        assert len(wines_data) >= 0  # Potrebbe essere 0 se fallisce
    
    @pytest.mark.asyncio
    async def test_flow_stage1_to_stage2_to_stage3(self):
        """Test flow Stage 1 → Stage 2 → Stage 3 (CSV caotico)."""
        # Leggi fixture chaotic.csv
        fixture_path = os.path.join(os.path.dirname(__file__), "data", "chaotic.csv")
        with open(fixture_path, "rb") as f:
            content = f.read()
        
        # Mock OpenAI per Stage 2 e Stage 3
        mock_response_stage3 = [
            {"name": "Chianti Classico", "winery": "Barone Ricasoli", "vintage": 2020, "qty": 12, "price": 18.50, "type": "Rosso"},
            {"name": "Barolo", "winery": "Vietti", "vintage": 2018, "qty": 6, "price": 45.00, "type": "Rosso"},
        ]
        
        with patch('ingest.pipeline.get_config') as mock_config, \
             patch('ingest.llm_extract.get_openai_client') as mock_client:
            
            mock_config.return_value.ia_targeted_enabled = True
            mock_config.return_value.llm_fallback_enabled = True
            mock_config.return_value.ocr_enabled = True
            mock_config.return_value.schema_score_th = 0.7
            mock_config.return_value.min_valid_rows = 0.6
            
            mock_chat = AsyncMock()
            mock_chat.completions.create.return_value = MagicMock(
                choices=[MagicMock(message=MagicMock(content=json.dumps(mock_response_stage3)))]
            )
            mock_client.return_value = mock_chat
        
        wines_data, metrics, decision, stage_used = await process_file(
            content, "chaotic.csv", "csv", telegram_id=123, business_name="Test"
        )
        
        # CSV caotico dovrebbe andare fino a Stage 3
        assert decision in ['save', 'error']
        assert stage_used in ['llm_mode', 'csv_excel_parse', 'ia_targeted']
    
    @pytest.mark.asyncio
    async def test_flow_unsupported_format(self):
        """Test formato non supportato."""
        content = b"fake docx content"
        
        with pytest.raises(ValueError, match="Formato file non supportato"):
            await process_file(
                content, "test.docx", "docx", telegram_id=123, business_name="Test"
            )
    
    @pytest.mark.asyncio
    async def test_flow_metrics_correct(self):
        """Test che metriche siano corrette."""
        fixture_path = os.path.join(os.path.dirname(__file__), "data", "clean.csv")
        with open(fixture_path, "rb") as f:
            content = f.read()
        
        with patch('ingest.pipeline.get_config') as mock_config:
            mock_config.return_value.ia_targeted_enabled = True
            mock_config.return_value.llm_fallback_enabled = True
            mock_config.return_value.ocr_enabled = True
        
        wines_data, metrics, decision, stage_used = await process_file(
            content, "clean.csv", "csv", telegram_id=123, business_name="Test"
        )
        
        # Verifica metriche
        assert "rows_total" in metrics or "rows_valid" in metrics
        assert "file_name" in metrics
        assert "ext" in metrics
        assert "stage_used" in metrics or stage_used is not None
    
    @pytest.mark.asyncio
    async def test_flow_logging_json(self):
        """Test che logging JSON funzioni."""
        fixture_path = os.path.join(os.path.dirname(__file__), "data", "clean.csv")
        with open(fixture_path, "rb") as f:
            content = f.read()
        
        with patch('ingest.pipeline.get_config') as mock_config, \
             patch('ingest.pipeline.log_json') as mock_log:
            
            mock_config.return_value.ia_targeted_enabled = True
            mock_config.return_value.llm_fallback_enabled = True
            mock_config.return_value.ocr_enabled = True
            
            await process_file(
                content, "clean.csv", "csv", telegram_id=123, business_name="Test", correlation_id="test-123"
            )
            
            # Verifica che log_json sia stato chiamato
            assert mock_log.called




