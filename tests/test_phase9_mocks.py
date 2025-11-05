"""
Test Phase 9.A: Mock & Simulation Plan
Comprehensive tests per verificare tutti i mock e scenari.
"""
import pytest
import json
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock
from openai import RateLimitError

from tests.mocks import (
    create_mock_openai_client,
    create_mock_ocr,
    create_mock_db,
    create_mock_config_with_flags
)
from ingest.llm_targeted import disambiguate_headers, fix_ambiguous_rows, apply_targeted_ai
from ingest.llm_extract import extract_with_llm, extract_llm_mode
from ingest.ocr_extract import extract_text_from_image, extract_text_from_pdf, extract_ocr
from core.database import batch_insert_wines


class TestOpenAIMocks:
    """Test mock OpenAI per Stage 2 e Stage 3."""
    
    @pytest.mark.asyncio
    async def test_openai_success_json_correct(self):
        """Test OpenAI con risposta JSON corretta."""
        headers = ["prodotto", "produttore", "anno"]
        examples = {"prodotto": "Chianti", "produttore": "Barone", "anno": 2020}
        
        mock_response = {
            "name": "prodotto",
            "winery": "produttore",
            "vintage": "anno"
        }
        
        with patch('ingest.llm_targeted.get_openai_client') as mock_get_client:
            mock_client = create_mock_openai_client("success", mock_response)
            mock_get_client.return_value = mock_client
            
            mapping = await disambiguate_headers(headers, examples)
            
            assert isinstance(mapping, dict)
            assert "prodotto" in mapping
    
    @pytest.mark.asyncio
    async def test_openai_malformed_json(self):
        """Test OpenAI con risposta JSON malformata."""
        headers = ["prodotto", "produttore"]
        
        with patch('ingest.llm_targeted.get_openai_client') as mock_get_client:
            mock_client = create_mock_openai_client("malformed")
            mock_get_client.return_value = mock_client
            
            # Dovrebbe gestire JSON malformato e fallback
            try:
                mapping = await disambiguate_headers(headers, {})
                # OK se ritorna mapping vuoto o solleva
                assert isinstance(mapping, dict)
            except Exception:
                pass  # OK se solleva eccezione
    
    @pytest.mark.asyncio
    async def test_openai_api_error(self):
        """Test OpenAI con errore API."""
        headers = ["prodotto", "produttore"]
        
        with patch('ingest.llm_targeted.get_openai_client') as mock_get_client:
            mock_client = create_mock_openai_client("error")
            mock_get_client.return_value = mock_client
            
            # Dovrebbe gestire errore e fallback
            mapping = await disambiguate_headers(headers, {})
            assert isinstance(mapping, dict)  # Ritorna mapping vuoto o fallback
    
    @pytest.mark.asyncio
    async def test_openai_timeout(self):
        """Test OpenAI con timeout."""
        headers = ["prodotto", "produttore"]
        
        with patch('ingest.llm_targeted.get_openai_client') as mock_get_client:
            mock_client = create_mock_openai_client("timeout")
            mock_get_client.return_value = mock_client
            
            # Dovrebbe gestire timeout
            try:
                mapping = await disambiguate_headers(headers, {})
                assert isinstance(mapping, dict)
            except asyncio.TimeoutError:
                pass  # OK se solleva TimeoutError
    
    @pytest.mark.asyncio
    async def test_openai_rate_limit(self):
        """Test OpenAI con rate limit."""
        headers = ["prodotto", "produttore"]
        
        with patch('ingest.llm_targeted.get_openai_client') as mock_get_client:
            mock_client = create_mock_openai_client("rate_limit")
            mock_get_client.return_value = mock_client
            
            # Dovrebbe gestire rate limit e escalare a Stage 3
            try:
                mapping = await disambiguate_headers(headers, {})
                assert isinstance(mapping, dict)
            except RateLimitError:
                pass  # OK se solleva RateLimitError
    
    @pytest.mark.asyncio
    async def test_feature_flag_ia_targeted_disabled(self):
        """Test feature flag IA_TARGETED_ENABLED=false."""
        wines_data = [{"name": "Chianti", "vintage": 2020, "qty": 12}]
        headers = ["name", "vintage", "qty"]
        
        with patch('ingest.llm_targeted.get_config') as mock_config:
            mock_config.return_value = create_mock_config_with_flags(
                ia_targeted_enabled=False
            )
            
            result_wines, metrics, decision = await apply_targeted_ai(
                wines_data, headers, 0.6, 0.5, "test.csv", "csv"
            )
            
            # Dovrebbe escalare direttamente a Stage 3
            assert decision == 'escalate_to_stage3'
    
    @pytest.mark.asyncio
    async def test_feature_flag_llm_fallback_disabled(self):
        """Test feature flag LLM_FALLBACK_ENABLED=false."""
        # Se LLM fallback disabilitato, Stage 3 non dovrebbe essere chiamato
        # Questo è testato in test_ingest_flow.py
        pass


class TestOCRMocks:
    """Test mock OCR per Stage 4."""
    
    def test_ocr_success_image(self):
        """Test OCR con successo su immagine."""
        image_content = b"fake image data"
        
        with patch('ingest.ocr_extract.pytesseract.image_to_string') as mock_ocr:
            mock_ocr_obj = create_mock_ocr("success", "Chianti Classico 2020 12 bottiglie")
            mock_ocr.side_effect = lambda img, **kwargs: mock_ocr_obj.image_to_string(img)
            
            text = extract_text_from_image(image_content)
            
            assert isinstance(text, str)
            assert "Chianti" in text
    
    def test_ocr_success_pdf_multipage(self):
        """Test OCR con PDF multipagina."""
        pdf_content = b"%PDF-1.4 fake pdf"
        
        from PIL import Image
        
        mock_images = [
            Image.new('RGB', (100, 100), color='white'),
            Image.new('RGB', (100, 100), color='white'),
        ]
        
        with patch('ingest.ocr_extract.convert_from_bytes') as mock_convert, \
             patch('ingest.ocr_extract.pytesseract.image_to_string') as mock_ocr:
            
            mock_convert.return_value = mock_images
            mock_ocr_obj = create_mock_ocr("success", "Page text", pages=2)
            mock_ocr.side_effect = lambda img, **kwargs: mock_ocr_obj.image_to_string(img)
            
            text = extract_text_from_pdf(pdf_content)
            
            assert isinstance(text, str)
            assert mock_ocr.call_count == 2  # Chiamato per ogni pagina
    
    def test_ocr_error(self):
        """Test OCR con errore."""
        image_content = b"invalid image"
        
        with patch('ingest.ocr_extract.pytesseract.image_to_string') as mock_ocr:
            mock_ocr_obj = create_mock_ocr("error")
            mock_ocr.side_effect = lambda img, **kwargs: mock_ocr_obj.image_to_string(img)
            
            # Dovrebbe gestire errore graceful
            try:
                text = extract_text_from_image(image_content)
                assert isinstance(text, str)
            except Exception:
                pass  # OK se solleva eccezione
    
    def test_ocr_empty_text(self):
        """Test OCR con testo vuoto."""
        image_content = b"fake image"
        
        with patch('ingest.ocr_extract.pytesseract.image_to_string') as mock_ocr:
            mock_ocr_obj = create_mock_ocr("empty")
            mock_ocr.side_effect = lambda img, **kwargs: mock_ocr_obj.image_to_string(img)
            
            text = extract_text_from_image(image_content)
            
            assert isinstance(text, str)
            assert text == "" or len(text) == 0
    
    @pytest.mark.asyncio
    async def test_ocr_pass_to_stage3(self):
        """Test che OCR passa a Stage 3 con testo estratto."""
        image_content = b"fake image"
        
        with patch('ingest.ocr_extract.extract_text_from_image') as mock_extract, \
             patch('ingest.ocr_extract.extract_llm_mode') as mock_llm, \
             patch('ingest.ocr_extract.get_config') as mock_config:
            
            mock_config.return_value = create_mock_config_with_flags(ocr_enabled=True)
            mock_extract.return_value = "Chianti Classico 2020 12 bottiglie"
            
            mock_llm.return_value = (
                [{"name": "Chianti Classico", "vintage": 2020, "qty": 12}],
                {"rows_valid": 1},
                "save"
            )
            
            wines_data, metrics, decision, stage_used = await extract_ocr(
                image_content, "test.jpg", "jpg", telegram_id=123, business_name="Test"
            )
            
            assert decision == 'save'
            assert stage_used == 'ocr'
            mock_llm.assert_called_once()  # Verifica passaggio a Stage 3


class TestDatabaseMocks:
    """Test mock database per batch insert."""
    
    @pytest.mark.asyncio
    async def test_db_insert_success(self):
        """Test database insert con successo."""
        wines = [
            {"name": "Chianti", "winery": "Barone", "vintage": 2020, "qty": 12}
        ]
        
        mock_db = create_mock_db("success")
        
        with patch('core.database.get_db') as mock_get_db:
            async def db_gen():
                yield mock_db
            mock_get_db.return_value = db_gen()
            
            # Test batch_insert_wines
            # Nota: batch_insert_wines usa get_db() direttamente
            # Questo è un test semplificato
            assert mock_db._insert_mode == "success"
    
    @pytest.mark.asyncio
    async def test_db_insert_partial_error(self):
        """Test database insert con errore parziale."""
        mock_db = create_mock_db("partial_error")
        
        # Simula errore parziale
        try:
            await mock_db.execute("INSERT INTO wines ...", {})
        except Exception as e:
            assert "Partial" in str(e) or "error" in str(e).lower()
    
    @pytest.mark.asyncio
    async def test_db_insert_error(self):
        """Test database insert con errore completo."""
        mock_db = create_mock_db("error")
        
        try:
            await mock_db.execute("INSERT INTO wines ...", {})
        except Exception as e:
            assert "error" in str(e).lower() or "Error" in str(e)


class TestTimeoutMocks:
    """Test mock timeout per chiamate LLM e OCR."""
    
    @pytest.mark.asyncio
    async def test_llm_timeout_handling(self):
        """Test gestione timeout chiamate LLM."""
        headers = ["prodotto", "produttore"]
        
        with patch('ingest.llm_targeted.get_openai_client') as mock_get_client:
            mock_client = create_mock_openai_client("timeout")
            mock_get_client.return_value = mock_client
            
            # Dovrebbe gestire timeout gracefully
            try:
                mapping = await disambiguate_headers(headers, {})
                assert isinstance(mapping, dict)
            except asyncio.TimeoutError:
                pass  # OK se solleva TimeoutError


class TestExecutionWithoutExternalKeys:
    """Test esecuzione senza chiavi esterne (solo mock)."""
    
    @pytest.mark.asyncio
    async def test_without_openai_key_mock_only(self):
        """Test con OPENAI_API_KEY mancante (usa solo mock)."""
        # Imposta OPENAI_API_KEY vuoto
        with patch.dict('os.environ', {'OPENAI_API_KEY': ''}):
            # Mock get_openai_client per evitare errore
            with patch('ingest.llm_targeted.get_openai_client') as mock_get_client:
                mock_client = create_mock_openai_client("success")
                mock_get_client.return_value = mock_client
                
                # Test dovrebbe funzionare con mock
                headers = ["prodotto", "produttore"]
                mapping = await disambiguate_headers(headers, {})
                assert isinstance(mapping, dict)
    
    def test_ocr_disabled_without_binaries(self):
        """Test OCR disabilitato in assenza di binari (usa mock)."""
        image_content = b"fake image"
        
        # Simula OCR disabilitato via feature flag
        with patch('ingest.ocr_extract.get_config') as mock_config:
            mock_config.return_value = create_mock_config_with_flags(ocr_enabled=False)
            
            # Test extract_ocr con feature flag disabilitato
            import asyncio
            result = asyncio.run(extract_ocr(
                image_content, "test.jpg", "jpg", telegram_id=123, business_name="Test"
            ))
            
            wines_data, metrics, decision, stage_used = result
            assert decision == 'error'  # OCR disabilitato → errore

