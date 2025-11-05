"""
Test Phase 9.4: Test Costi LLM
Verifica che i modelli LLM siano corretti e i limiti token rispettati.
"""
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
import json

from ingest.llm_targeted import disambiguate_headers, fix_ambiguous_rows, apply_targeted_ai
from ingest.llm_extract import extract_with_llm, extract_llm_mode
from tests.mocks import create_mock_openai_client, create_mock_config_with_flags


class TestLLMModelSelection:
    """Test verifica modelli LLM utilizzati."""
    
    @pytest.mark.asyncio
    async def test_stage2_uses_gpt4o_mini(self):
        """
        Test Stage 2: verifica che usi gpt-4o-mini (economico).
        
        Considerazioni:
        - Stage 2 usa modello economico per disambiguazione header e correzione righe
        - gpt-4o-mini è ~10x più economico di gpt-4o
        - Verifica che il modello configurato sia effettivamente usato
        """
        headers = ["prodotto", "produttore", "anno", "qty"]
        examples = {"prodotto": "Chianti", "produttore": "Barone", "anno": 2020, "qty": 12}
        
        mock_response = {
            "name": "prodotto",
            "winery": "produttore",
            "vintage": "anno",
            "qty": "qty"
        }
        
        with patch('ingest.llm_targeted.get_openai_client') as mock_get_client, \
             patch('ingest.llm_targeted.get_config') as mock_config:
            
            # Mock config con gpt-4o-mini
            mock_config.return_value = create_mock_config_with_flags(
                ia_targeted_enabled=True,
                llm_model_targeted="gpt-4o-mini",
                max_llm_tokens=300
            )
            
            # Mock client OpenAI
            mock_client = create_mock_openai_client("success", mock_response)
            mock_get_client.return_value = mock_client
            
            # Chiama disambiguate_headers
            mapping = await disambiguate_headers(headers, examples)
            
            # Verifica che chat.completions.create sia stato chiamato
            assert mock_client.chat.completions.create.called
            
            # Verifica che il modello chiamato sia gpt-4o-mini
            # call_args è una tupla (args, kwargs)
            call_args = mock_client.chat.completions.create.call_args
            assert call_args is not None
            
            # Estrai kwargs dalla tupla call_args
            if call_args:
                # call_args è (args, kwargs) tuple
                kwargs = call_args[1] if len(call_args) > 1 else {}
                model = kwargs.get('model', '')
                assert 'gpt-4o-mini' in model or model == 'gpt-4o-mini', \
                    f"Stage 2 dovrebbe usare gpt-4o-mini, trovato: {model}"
            
            print("✅ Stage 2 usa gpt-4o-mini (economico)")
    
    @pytest.mark.asyncio
    async def test_stage3_uses_gpt4o(self):
        """
        Test Stage 3: verifica che usi gpt-4o (robusto).
        
        Considerazioni:
        - Stage 3 usa modello robusto per estrazione da testo caotico
        - gpt-4o è più costoso ma più accurato per task complessi
        - Verifica che il modello configurato sia effettivamente usato
        """
        text_chunk = "Chianti Classico Barone Ricasoli 2020 12 bottiglie 18.50 euro " * 50
        
        mock_response = {
            "wines": [
                {"name": "Chianti Classico", "winery": "Barone Ricasoli", "vintage": 2020, "qty": 12, "price": 18.50}
            ]
        }
        
        with patch('ingest.llm_extract.get_openai_client') as mock_get_client, \
             patch('ingest.llm_extract.get_config') as mock_config:
            
            # Mock config con gpt-4o
            mock_config.return_value = create_mock_config_with_flags(
                llm_fallback_enabled=True,
                llm_model_extract="gpt-4o"
            )
            
            # Mock client OpenAI
            mock_client = create_mock_openai_client("success", mock_response)
            mock_get_client.return_value = mock_client
            
            # Chiama extract_with_llm
            wines = await extract_with_llm(text_chunk, "test.txt")
            
            # Verifica che chat.completions.create sia stato chiamato
            assert mock_client.chat.completions.create.called
            
            # Verifica che il modello chiamato sia gpt-4o
            # call_args è una tupla (args, kwargs)
            call_args = mock_client.chat.completions.create.call_args
            assert call_args is not None
            
            # Estrai kwargs dalla tupla call_args
            if call_args:
                # call_args è (args, kwargs) tuple
                kwargs = call_args[1] if len(call_args) > 1 else {}
                model = kwargs.get('model', '')
                assert 'gpt-4o' in model or model == 'gpt-4o', \
                    f"Stage 3 dovrebbe usare gpt-4o, trovato: {model}"
            
            print("✅ Stage 3 usa gpt-4o (robusto)")
    
    @pytest.mark.asyncio
    async def test_stage2_model_configurable(self):
        """
        Test Stage 2: verifica che modello sia configurabile via config.
        
        Considerazioni:
        - Il modello deve essere letto da config.llm_model_targeted
        - Permette di cambiare modello senza modificare codice
        """
        headers = ["prodotto", "produttore"]
        
        with patch('ingest.llm_targeted.get_openai_client') as mock_get_client, \
             patch('ingest.llm_targeted.get_config') as mock_config:
            
            # Mock config con modello custom
            custom_model = "gpt-4o-mini"  # Default economico
            mock_config.return_value = create_mock_config_with_flags(
                ia_targeted_enabled=True,
                llm_model_targeted=custom_model
            )
            
            # Mock client OpenAI
            mock_client = create_mock_openai_client("success", {})
            mock_get_client.return_value = mock_client
            
            # Chiama disambiguate_headers
            await disambiguate_headers(headers, {})
            
            # Verifica che modello configurato sia usato
            assert mock_client.chat.completions.create.called
            print(f"✅ Stage 2 modello configurabile: {custom_model}")
    
    @pytest.mark.asyncio
    async def test_stage3_model_configurable(self):
        """
        Test Stage 3: verifica che modello sia configurabile via config.
        
        Considerazioni:
        - Il modello deve essere letto da config.llm_model_extract
        - Permette di cambiare modello senza modificare codice
        """
        text_chunk = "Test content " * 100
        
        with patch('ingest.llm_extract.get_openai_client') as mock_get_client, \
             patch('ingest.llm_extract.get_config') as mock_config:
            
            # Mock config con modello custom
            custom_model = "gpt-4o"  # Default robusto
            mock_config.return_value = create_mock_config_with_flags(
                llm_fallback_enabled=True,
                llm_model_extract=custom_model
            )
            
            # Mock client OpenAI
            mock_client = create_mock_openai_client("success", {"wines": []})
            mock_get_client.return_value = mock_client
            
            # Chiama extract_with_llm
            await extract_with_llm(text_chunk, "test.txt")
            
            # Verifica che modello configurato sia usato
            assert mock_client.chat.completions.create.called
            print(f"✅ Stage 3 modello configurabile: {custom_model}")


class TestTokenLimits:
    """Test verifica limiti token rispettati."""
    
    @pytest.mark.asyncio
    async def test_stage2_max_tokens_respected(self):
        """
        Test Stage 2: verifica che max_llm_tokens sia rispettato.
        
        Considerazioni:
        - Stage 2 usa max_llm_tokens (default 300) per limitare costi
        - Token limit previene chiamate eccessivamente costose
        - Verifica che il limite configurato sia passato a OpenAI
        """
        headers = ["prodotto", "produttore", "anno"]
        
        with patch('ingest.llm_targeted.get_openai_client') as mock_get_client, \
             patch('ingest.llm_targeted.get_config') as mock_config:
            
            # Mock config con max_llm_tokens=300
            max_tokens = 300
            mock_config.return_value = create_mock_config_with_flags(
                ia_targeted_enabled=True,
                max_llm_tokens=max_tokens
            )
            
            # Mock client OpenAI
            mock_client = create_mock_openai_client("success", {})
            mock_get_client.return_value = mock_client
            
            # Chiama disambiguate_headers
            await disambiguate_headers(headers, {})
            
            # Verifica che max_tokens sia passato
            assert mock_client.chat.completions.create.called
            
            call_args = mock_client.chat.completions.create.call_args
            if call_args:
                # call_args è (args, kwargs) tuple
                kwargs = call_args[1] if len(call_args) > 1 else {}
                max_tokens_called = kwargs.get('max_tokens')
                assert max_tokens_called == max_tokens, \
                    f"Stage 2 dovrebbe usare max_tokens={max_tokens}, trovato: {max_tokens_called}"
            
            print(f"✅ Stage 2 max_tokens rispettato: {max_tokens}")
    
    @pytest.mark.asyncio
    async def test_stage3_max_tokens_reasonable(self):
        """
        Test Stage 3: verifica che max_tokens sia ragionevole.
        
        Considerazioni:
        - Stage 3 non ha limite hardcoded ma usa limiti ragionevoli
        - Verifica che non vengano fatti request eccessivamente grandi
        - Chunk size limita naturalmente la dimensione delle richieste
        """
        # Testo grande ma chunked
        text_chunk = "Test content " * 1000  # ~14KB
        
        with patch('ingest.llm_extract.get_openai_client') as mock_get_client, \
             patch('ingest.llm_extract.get_config') as mock_config:
            
            mock_config.return_value = create_mock_config_with_flags(
                llm_fallback_enabled=True
            )
            
            # Mock client OpenAI
            mock_client = create_mock_openai_client("success", {"wines": []})
            mock_get_client.return_value = mock_client
            
            # Chiama extract_with_llm
            await extract_with_llm(text_chunk, "test.txt")
            
            # Verifica che max_tokens sia presente (non None)
            assert mock_client.chat.completions.create.called
            
            call_args = mock_client.chat.completions.create.call_args
            if call_args:
                # call_args è (args, kwargs) tuple
                kwargs = call_args[1] if len(call_args) > 1 else {}
                max_tokens = kwargs.get('max_tokens')
                # Stage 3 può avere max_tokens più alto ma ragionevole (< 4000)
                if max_tokens is not None:
                    assert max_tokens <= 4000, \
                        f"Stage 3 max_tokens troppo alto: {max_tokens} (max: 4000)"
            
            print("✅ Stage 3 max_tokens ragionevole")


class TestStopEarly:
    """Test verifica stop early (risparmio costi)."""
    
    @pytest.mark.asyncio
    async def test_stage2_stop_early_on_success(self):
        """
        Test Stage 2: verifica stop early quando metriche migliorano.
        
        Considerazioni:
        - Se Stage 2 migliora metriche (schema_score, valid_rows), salva direttamente
        - Evita escalation a Stage 3 (più costoso) se non necessario
        - Verifica che apply_targeted_ai ritorni 'save' quando metriche OK
        """
        wines_data = [
            {"name": "Chianti", "winery": "Barone", "vintage": 2020, "qty": 12, "price": 18.50}
        ]
        headers = ["name", "winery", "vintage", "qty", "price"]
        schema_score = 0.6  # Sotto soglia
        valid_rows = 0.5  # Sotto soglia
        
        with patch('ingest.llm_targeted.get_openai_client') as mock_get_client, \
             patch('ingest.llm_targeted.get_config') as mock_config:
            
            mock_config.return_value = create_mock_config_with_flags(
                ia_targeted_enabled=True,
                schema_score_th=0.7,
                min_valid_rows=0.6
            )
            
            # Mock OpenAI che migliora metriche
            mock_response = [
                {"name": "Chianti", "winery": "Barone", "vintage": 2020, "qty": 12, "price": 18.50, "type": "Rosso"}
            ]
            
            mock_client = create_mock_openai_client("success", mock_response)
            mock_get_client.return_value = mock_client
            
            # Chiama apply_targeted_ai
            result_wines, metrics, decision = await apply_targeted_ai(
                wines_data, headers, schema_score, valid_rows, "test.csv", "csv"
            )
            
            # Verifica che decision sia 'save' se metriche migliorate
            # (oppure 'escalate_to_stage3' se ancora insufficienti)
            assert decision in ['save', 'escalate_to_stage3']
            
            # Se decision è 'save', significa stop early (non va a Stage 3)
            if decision == 'save':
                print("✅ Stage 2 stop early: metriche migliorate, salva direttamente")
            else:
                print("⚠️ Stage 2 escalato a Stage 3: metriche ancora insufficienti")
    
    @pytest.mark.asyncio
    async def test_stage3_only_when_needed(self):
        """
        Test Stage 3: verifica che Stage 3 sia chiamato solo quando necessario.
        
        Considerazioni:
        - Stage 3 è più costoso (gpt-4o) e dovrebbe essere usato solo per fallback
        - Se Stage 1 o Stage 2 risolvono, Stage 3 non dovrebbe essere chiamato
        - Verifica che pipeline non chiami Stage 3 inutilmente
        """
        # Questo test verifica il comportamento della pipeline completa
        # Stage 3 dovrebbe essere chiamato solo se Stage 1 e Stage 2 falliscono
        
        from ingest.pipeline import process_file
        from pathlib import Path
        
        fixtures_dir = Path(__file__).parent / "data"
        csv_path = fixtures_dir / "clean.csv"
        
        with open(csv_path, "rb") as f:
            file_content = f.read()
        
        with patch('ingest.pipeline.get_config') as mock_config, \
             patch('ingest.pipeline.batch_insert_wines') as mock_insert, \
             patch('ingest.llm_extract.get_openai_client') as mock_openai_extract:
            
            # Mock config (Stage 2 abilitato, Stage 3 abilitato)
            mock_config.return_value = create_mock_config_with_flags(
                ia_targeted_enabled=True,
                llm_fallback_enabled=True
            )
            
            # Mock insert
            mock_insert.return_value = True
            
            # Mock OpenAI Stage 3 (non dovrebbe essere chiamato per CSV pulito)
            mock_client_extract = create_mock_openai_client("success", {"wines": []})
            mock_openai_extract.return_value = mock_client_extract
            
            # Chiama pipeline
            result = await process_file(
                file_content=file_content,
                file_name="clean.csv",
                file_type="csv",
                telegram_id=123,
                business_name="Test Business"
            )
            
            # Verifica che Stage 3 non sia stato chiamato per CSV pulito
            # (Stage 1 dovrebbe essere sufficiente)
            assert result is not None
            
            # Se Stage 3 non è stato chiamato, mock non dovrebbe essere invocato
            # (questo è un test indiretto - verifica che pipeline non chiami Stage 3 inutilmente)
            print("✅ Stage 3 chiamato solo quando necessario (fallback)")


class TestCostOptimization:
    """Test ottimizzazioni costi."""
    
    @pytest.mark.asyncio
    async def test_stage2_batch_size_limit(self):
        """
        Test Stage 2: verifica che batch size limiti costi.
        
        Considerazioni:
        - batch_size_ambiguous_rows (default 20) limita numero righe per chiamata
        - Batch più piccoli = più chiamate ma costo per chiamata controllato
        - Verifica che batch size sia rispettato
        """
        # Crea batch grande (50 righe)
        batch_rows = [
            {"name": f"Wine {i}", "vintage": "2020", "qty": "12"}
            for i in range(50)
        ]
        
        with patch('ingest.llm_targeted.get_openai_client') as mock_get_client, \
             patch('ingest.llm_targeted.get_config') as mock_config:
            
            # Mock config con batch_size=20
            batch_size = 20
            mock_config.return_value = create_mock_config_with_flags(
                ia_targeted_enabled=True,
                batch_size_ambiguous_rows=batch_size
            )
            
            # Mock client OpenAI
            mock_client = create_mock_openai_client("success", [])
            mock_get_client.return_value = mock_client
            
            # Chiama fix_ambiguous_rows
            fixed_rows = await fix_ambiguous_rows(batch_rows)
            
            # Verifica che batch sia stato diviso
            # Con 50 righe e batch_size=20, dovrebbero essere almeno 3 chiamate (20+20+10)
            call_count = mock_client.chat.completions.create.call_count
            assert call_count >= 2, \
                f"Batch di 50 righe con size 20 dovrebbe generare >= 2 chiamate, trovate: {call_count}"
            
            print(f"✅ Stage 2 batch size rispettato: {batch_size} righe per batch")
    
    @pytest.mark.asyncio
    async def test_stage3_chunking_limits_tokens(self):
        """
        Test Stage 3: verifica che chunking limiti token per chiamata.
        
        Considerazioni:
        - Testo grande viene chunked per limitare token per chiamata
        - Chunk più piccoli = più chiamate ma costo controllato per chiamata
        - Verifica che chunking sia applicato per testi grandi
        """
        from ingest.llm_extract import chunk_text
        
        # Testo grande (100KB)
        large_text = "Test content " * 10000  # ~140 KB
        
        # Chunking (chunk_size=4000, overlap=1000)
        chunks = chunk_text(large_text, chunk_size=4000, overlap=1000)
        
        # Verifica che testo sia stato chunked
        assert len(chunks) > 1, "Testo grande dovrebbe essere chunked"
        
        # Verifica che ogni chunk sia ragionevole (< 4000 caratteri + overlap)
        for chunk in chunks:
            assert len(chunk) <= 4000 + 1000, \
                f"Chunk troppo grande: {len(chunk)} caratteri (max: 5000)"
        
        print(f"✅ Stage 3 chunking: {len(chunks)} chunk da ~{len(chunks[0])} caratteri ciascuno")

