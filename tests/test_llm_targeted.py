"""
Test unitari per Stage 2 (IA mirata) con mock OpenAI.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import json

from ingest.llm_targeted import disambiguate_headers, fix_ambiguous_rows, apply_targeted_ai


class TestLLMTargeted:
    """Test per Stage 2 (IA mirata)."""
    
    @pytest.mark.asyncio
    async def test_disambiguate_headers_success(self):
        """Test disambiguazione header con successo."""
        headers = ["prodotto", "produttore", "anno", "qty"]
        examples = {"prodotto": "Chianti", "produttore": "Barone", "anno": 2020, "qty": 12}
        
        # Mock risposta OpenAI
        mock_response = {
            "name": "prodotto",
            "winery": "produttore",
            "vintage": "anno",
            "qty": "qty"
        }
        
        with patch('ingest.llm_targeted.get_openai_client') as mock_client:
            mock_chat = AsyncMock()
            mock_chat.completions.create.return_value = MagicMock(
                choices=[MagicMock(message=MagicMock(content=json.dumps(mock_response)))]
            )
            mock_client.return_value = mock_chat
            
            mapping = await disambiguate_headers(headers, examples)
            
            assert isinstance(mapping, dict)
            assert "prodotto" in mapping
            assert mapping["prodotto"] == "name"
    
    @pytest.mark.asyncio
    async def test_disambiguate_headers_fallback(self):
        """Test fallback se OpenAI fallisce."""
        headers = ["prodotto", "produttore"]
        examples = {}
        
        with patch('ingest.llm_targeted.get_openai_client') as mock_client:
            mock_chat = AsyncMock()
            mock_chat.completions.create.side_effect = Exception("API Error")
            mock_client.return_value = mock_chat
            
            # Dovrebbe ritornare mapping vuoto o fallback
            mapping = await disambiguate_headers(headers, examples)
            
            assert isinstance(mapping, dict)
    
    @pytest.mark.asyncio
    async def test_fix_ambiguous_rows_success(self):
        """Test correzione righe ambigue con successo."""
        batch_rows = [
            {"name": "Chianti", "winery": "Barone", "vintage": "2020", "qty": "12 bottiglie"},
            {"name": "Barolo", "winery": "Vietti", "vintage": "2018", "qty": "6 pz"},
        ]
        
        # Mock risposta OpenAI
        mock_response = [
            {"name": "Chianti", "winery": "Barone", "vintage": 2020, "qty": 12},
            {"name": "Barolo", "winery": "Vietti", "vintage": 2018, "qty": 6},
        ]
        
        with patch('ingest.llm_targeted.get_openai_client') as mock_client:
            mock_chat = AsyncMock()
            mock_chat.completions.create.return_value = MagicMock(
                choices=[MagicMock(message=MagicMock(content=json.dumps(mock_response)))]
            )
            mock_client.return_value = mock_chat
            
            fixed_rows = await fix_ambiguous_rows(batch_rows)
            
            assert len(fixed_rows) == len(batch_rows)
            assert fixed_rows[0]["vintage"] == 2020  # Convertito a int
            assert fixed_rows[0]["qty"] == 12  # Estratto da "12 bottiglie"
    
    @pytest.mark.asyncio
    async def test_fix_ambiguous_rows_batch_size(self):
        """Test che rispetta batch_size."""
        # Crea batch grande (50 righe)
        batch_rows = [
            {"name": f"Wine {i}", "vintage": "2020", "qty": "12"}
            for i in range(50)
        ]
        
        with patch('ingest.llm_targeted.get_openai_client') as mock_client:
            mock_chat = AsyncMock()
            mock_chat.completions.create.return_value = MagicMock(
                choices=[MagicMock(message=MagicMock(content=json.dumps([])))]
            )
            mock_client.return_value = mock_chat
            
            # Dovrebbe processare in batch di max 20 (default)
            fixed_rows = await fix_ambiguous_rows(batch_rows)
            
            # Verifica che sia stato chiamato più volte (per batch)
            assert mock_chat.completions.create.call_count >= 2
    
    @pytest.mark.asyncio
    async def test_apply_targeted_ai_save(self):
        """Test apply_targeted_ai con decisione save."""
        wines_data = [
            {"name": "Chianti", "winery": "Barone", "vintage": 2020, "qty": 12, "price": 18.50}
        ]
        headers = ["name", "winery", "vintage", "qty", "price"]
        schema_score = 0.6  # Sotto soglia
        valid_rows = 0.5  # Sotto soglia
        
        with patch('ingest.llm_targeted.get_openai_client') as mock_client, \
             patch('ingest.llm_targeted.get_config') as mock_config:
            
            # Mock config
            mock_config.return_value.ia_targeted_enabled = True
            mock_config.return_value.schema_score_th = 0.7
            mock_config.return_value.min_valid_rows = 0.6
            
            # Mock OpenAI (simula correzione che migliora metriche)
            mock_chat = AsyncMock()
            mock_response = [
                {"name": "Chianti", "winery": "Barone", "vintage": 2020, "qty": 12, "price": 18.50, "type": "Rosso"}
            ]
            mock_chat.completions.create.return_value = MagicMock(
                choices=[MagicMock(message=MagicMock(content=json.dumps(mock_response)))]
            )
            mock_client.return_value = mock_chat
            
            result_wines, metrics, decision = await apply_targeted_ai(
                wines_data, headers, schema_score, valid_rows, "test.csv", "csv"
            )
            
            assert decision in ['save', 'escalate_to_stage3']
            assert len(result_wines) > 0
    
    @pytest.mark.asyncio
    async def test_apply_targeted_ai_feature_flag_disabled(self):
        """Test che rispetta feature flag disabilitato."""
        wines_data = [{"name": "Chianti", "vintage": 2020, "qty": 12}]
        headers = ["name", "vintage", "qty"]
        schema_score = 0.6
        valid_rows = 0.5
        
        with patch('ingest.llm_targeted.get_config') as mock_config:
            mock_config.return_value.ia_targeted_enabled = False
            
            result_wines, metrics, decision = await apply_targeted_ai(
                wines_data, headers, schema_score, valid_rows, "test.csv", "csv"
            )
            
            # Se feature flag disabilitato, dovrebbe escalare direttamente a Stage 3
            assert decision == 'escalate_to_stage3'





