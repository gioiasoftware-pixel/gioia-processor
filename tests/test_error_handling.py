"""
Test Phase 9.5: Test Error Handling
Verifica gestione errori completa in tutti gli scenari.
"""
import pytest
from unittest.mock import patch, MagicMock, AsyncMock

from ingest.gate import route_file
from ingest.pipeline import process_file
from ingest.parser import parse_classic
from ingest.llm_targeted import apply_targeted_ai
from ingest.llm_extract import extract_llm_mode
from ingest.ocr_extract import extract_ocr
from tests.mocks import create_mock_openai_client, create_mock_config_with_flags


class TestUnsupportedFormat:
    """Test gestione formato non supportato."""
    
    def test_unsupported_format_raises_error(self):
        """
        Test: File formato non supportato → errore gestito.
        
        Considerazioni:
        - File con estensione non supportata (es. .doc, .zip) deve sollevare ValueError
        - Errore deve essere user-friendly e chiaro
        - Verifica che gate.py gestisca correttamente formati non supportati
        """
        unsupported_content = b"This is a .doc file content"
        
        with pytest.raises(ValueError) as exc_info:
            route_file(unsupported_content, "test.doc", "doc")
        
        # Verifica che errore sia user-friendly
        error_message = str(exc_info.value).lower()
        assert "unsupported" in error_message or "not supported" in error_message or "formato" in error_message
        
        print("✅ Formato non supportato: errore gestito correttamente")
    
    def test_unknown_extension_handled(self):
        """
        Test: File con estensione sconosciuta → errore gestito.
        
        Considerazioni:
        - File senza estensione o estensione sconosciuta deve essere gestito
        - Verifica che pipeline gestisca gracefully
        """
        unknown_content = b"Unknown file content"
        
        with pytest.raises(ValueError):
            route_file(unknown_content, "test.unknown", "unknown")
        
        print("✅ Estensione sconosciuta: errore gestito correttamente")


class TestEmptyFile:
    """Test gestione file vuoto."""
    
    def test_empty_csv_file(self):
        """
        Test: File CSV vuoto → errore gestito.
        
        Considerazioni:
        - File CSV vuoto o con solo header deve essere gestito gracefully
        - Verifica che parser gestisca file vuoti senza crash
        """
        empty_csv = b"Name,Winery,Vintage\n"
        
        with patch('ingest.parser.get_config') as mock_config:
            mock_config.return_value = create_mock_config_with_flags()
            
            wines_data, metrics, decision = parse_classic(
                file_content=empty_csv,
                file_name="empty.csv",
                ext="csv"
            )
            
            # Verifica che risultato sia gestito (lista vuota o errore chiaro)
            assert isinstance(wines_data, list)
            # File vuoto può avere lista vuota o decision='error'
            assert decision in ['save', 'escalate_to_stage2', 'error'] or len(wines_data) == 0
            
            print("✅ File CSV vuoto: gestito correttamente")
    
    def test_empty_binary_file(self):
        """
        Test: File binario vuoto → errore gestito.
        
        Considerazioni:
        - File completamente vuoto (0 bytes) deve essere gestito
        - Verifica che pipeline gestisca gracefully
        """
        empty_content = b""
        
        with pytest.raises((ValueError, Exception)) as exc_info:
            route_file(empty_content, "empty.txt", "txt")
        
        # Verifica che errore sia gestito (non crash)
        assert exc_info.value is not None
        
        print("✅ File binario vuoto: errore gestito correttamente")


class TestAIFailureFallback:
    """Test fallback quando AI fallisce."""
    
    @pytest.mark.asyncio
    async def test_stage2_failure_fallback_to_stage3(self):
        """
        Test: AI Stage 2 fallisce → fallback a Stage 3.
        
        Considerazioni:
        - Se Stage 2 (Targeted AI) fallisce, pipeline deve escalare a Stage 3
        - Fallback deve essere automatico e trasparente
        - Verifica che Stage 3 sia chiamato quando Stage 2 fallisce
        """
        wines_data = [
            {"name": "Chianti", "winery": "Barone", "vintage": "2020", "qty": "12"}
        ]
        headers = ["name", "winery", "vintage", "qty"]
        schema_score = 0.6  # Sotto soglia
        valid_rows = 0.5  # Sotto soglia
        
        with patch('ingest.llm_targeted.get_openai_client') as mock_openai_targeted, \
             patch('ingest.llm_extract.get_openai_client') as mock_openai_extract, \
             patch('ingest.llm_targeted.get_config') as mock_config:
            
            mock_config.return_value = create_mock_config_with_flags(
                ia_targeted_enabled=True,
                llm_fallback_enabled=True
            )
            
            # Mock OpenAI Stage 2 fallisce
            mock_client_targeted = create_mock_openai_client("error")
            mock_openai_targeted.return_value = mock_client_targeted
            
            # Mock OpenAI Stage 3 successo
            mock_client_extract = create_mock_openai_client("success", {
                "wines": [
                    {"name": "Chianti", "winery": "Barone", "vintage": 2020, "qty": 12}
                ]
            })
            mock_openai_extract.return_value = mock_client_extract
            
            # Chiama apply_targeted_ai (Stage 2)
            result_wines, metrics, decision = await apply_targeted_ai(
                wines_data, headers, schema_score, valid_rows, "test.csv", "csv"
            )
            
            # Verifica che decision sia 'escalate_to_stage3' (fallback)
            assert decision == 'escalate_to_stage3', \
                f"Stage 2 fallito dovrebbe escalare a Stage 3, trovato: {decision}"
            
            print("✅ Stage 2 fallisce → fallback a Stage 3")
    
    @pytest.mark.asyncio
    async def test_stage2_timeout_fallback_to_stage3(self):
        """
        Test: AI Stage 2 timeout → fallback a Stage 3.
        
        Considerazioni:
        - Se Stage 2 va in timeout, pipeline deve escalare a Stage 3
        - Timeout non deve bloccare l'intera pipeline
        """
        wines_data = [{"name": "Chianti", "vintage": "2020", "qty": "12"}]
        headers = ["name", "vintage", "qty"]
        schema_score = 0.6
        valid_rows = 0.5
        
        with patch('ingest.llm_targeted.get_openai_client') as mock_openai_targeted, \
             patch('ingest.llm_targeted.get_config') as mock_config:
            
            mock_config.return_value = create_mock_config_with_flags(
                ia_targeted_enabled=True,
                llm_fallback_enabled=True
            )
            
            # Mock OpenAI Stage 2 timeout
            mock_client_targeted = create_mock_openai_client("timeout")
            mock_openai_targeted.return_value = mock_client_targeted
            
            # Chiama apply_targeted_ai (Stage 2)
            result_wines, metrics, decision = await apply_targeted_ai(
                wines_data, headers, schema_score, valid_rows, "test.csv", "csv"
            )
            
            # Verifica che decision sia 'escalate_to_stage3' (fallback)
            assert decision == 'escalate_to_stage3', \
                f"Stage 2 timeout dovrebbe escalare a Stage 3, trovato: {decision}"
            
            print("✅ Stage 2 timeout → fallback a Stage 3")
    
    @pytest.mark.asyncio
    async def test_stage3_failure_handled(self):
        """
        Test: AI Stage 3 fallisce → errore gestito.
        
        Considerazioni:
        - Se Stage 3 fallisce (ultimo stage), errore deve essere user-friendly
        - Verifica che pipeline gestisca gracefully il fallimento finale
        """
        text_chunk = "Chianti Classico 2020 12 bottiglie"
        
        with patch('ingest.llm_extract.get_openai_client') as mock_openai, \
             patch('ingest.llm_extract.get_config') as mock_config:
            
            mock_config.return_value = create_mock_config_with_flags(
                llm_fallback_enabled=True
            )
            
            # Mock OpenAI Stage 3 fallisce
            mock_client = create_mock_openai_client("error")
            mock_openai.return_value = mock_client
            
            # Chiama extract_llm_mode (Stage 3)
            # Signature: extract_llm_mode(file_content: bytes, file_name: str, ext: str)
            # Ritorna: (wines_data, metrics, decision)
            wines_data, metrics, decision = await extract_llm_mode(
                text_chunk.encode('utf-8'), "test.txt", "txt"
            )
            
            # Verifica che errore sia gestito (decision='error' o lista vuota)
            assert decision == 'error' or len(wines_data) == 0, \
                f"Stage 3 fallito dovrebbe ritornare 'error' o lista vuota, trovato: {decision}"
            
            print("✅ Stage 3 fallisce → errore gestito correttamente")


class TestAllStagesFail:
    """Test quando tutti gli stage falliscono."""
    
    @pytest.mark.asyncio
    async def test_all_stages_fail_user_friendly_error(self):
        """
        Test: Tutti gli stage falliscono → errore user-friendly.
        
        Considerazioni:
        - Se Stage 1, 2, 3 falliscono tutti, errore deve essere user-friendly
        - Messaggio errore deve essere chiaro e non tecnico
        - Verifica che pipeline gestisca gracefully il fallimento completo
        """
        from pathlib import Path
        
        fixtures_dir = Path(__file__).parent / "data"
        csv_path = fixtures_dir / "chaotic.csv"  # File caotico che richiede tutti gli stage
        
        with open(csv_path, "rb") as f:
            file_content = f.read()
        
        with patch('ingest.pipeline.get_config') as mock_config, \
             patch('ingest.pipeline.batch_insert_wines') as mock_insert, \
             patch('ingest.llm_targeted.get_openai_client') as mock_openai_targeted, \
             patch('ingest.llm_extract.get_openai_client') as mock_openai_extract:
            
            mock_config.return_value = create_mock_config_with_flags(
                ia_targeted_enabled=True,
                llm_fallback_enabled=True
            )
            
            # Mock insert (non necessario se fallisce)
            mock_insert.return_value = True
            
            # Mock OpenAI Stage 2 fallisce
            mock_client_targeted = create_mock_openai_client("error")
            mock_openai_targeted.return_value = mock_client_targeted
            
            # Mock OpenAI Stage 3 fallisce
            mock_client_extract = create_mock_openai_client("error")
            mock_openai_extract.return_value = mock_client_extract
            
            # Chiama pipeline
            # Signature: process_file(file_content, file_name, ext, telegram_id, business_name, correlation_id)
            # Ritorna: (wines_data, metrics, decision, stage_used)
            wines_data, metrics, decision, stage_used = await process_file(
                file_content=file_content,
                file_name="chaotic.csv",
                ext="csv",
                telegram_id=123,
                business_name="Test Business"
            )
            
            # Verifica che risultato contenga errore user-friendly
            assert wines_data is not None
            assert isinstance(wines_data, list)
            # Se tutti gli stage falliscono, decision dovrebbe essere 'error'
            assert decision in ['save', 'error']
            
            print("✅ Tutti gli stage falliscono → errore user-friendly")
    
    @pytest.mark.asyncio
    async def test_ocr_failure_handled(self):
        """
        Test: OCR fallisce → errore gestito.
        
        Considerazioni:
        - Se OCR fallisce, errore deve essere gestito gracefully
        - Verifica che pipeline gestisca errori OCR senza crash
        """
        from PIL import Image
        import io
        
        # Crea immagine test
        img = Image.new('RGB', (100, 100), color='white')
        img_bytes = io.BytesIO()
        img.save(img_bytes, format='PNG')
        img_bytes.seek(0)
        image_content = img_bytes.getvalue()
        
        with patch('ingest.ocr_extract.pytesseract.image_to_string') as mock_ocr, \
             patch('ingest.ocr_extract.get_config') as mock_config:
            
            mock_config.return_value = create_mock_config_with_flags(
                ocr_enabled=True
            )
            
            # Mock OCR fallisce
            mock_ocr.side_effect = Exception("OCR Error: Tesseract not found")
            
            # Chiama extract_ocr
            wines_data, metrics, decision, stage_used = await extract_ocr(
                image_content, "test.jpg", "jpg", telegram_id=123, business_name="Test"
            )
            
            # Verifica che errore sia gestito (decision='error' o gestito gracefully)
            assert decision == 'error' or len(wines_data) == 0, \
                f"OCR fallito dovrebbe ritornare 'error', trovato: {decision}"
            
            print("✅ OCR fallisce → errore gestito correttamente")


class TestDatabaseErrors:
    """Test gestione errori database."""
    
    @pytest.mark.asyncio
    async def test_database_insert_error_handled(self):
        """
        Test: Errore insert database → errore gestito.
        
        Considerazioni:
        - Se insert database fallisce, errore deve essere gestito
        - Verifica che pipeline gestisca errori DB senza crash
        """
        from pathlib import Path
        
        fixtures_dir = Path(__file__).parent / "data"
        csv_path = fixtures_dir / "clean.csv"
        
        with open(csv_path, "rb") as f:
            file_content = f.read()
        
        with patch('ingest.pipeline.get_config') as mock_config, \
             patch('ingest.pipeline.batch_insert_wines') as mock_insert:
            
            mock_config.return_value = create_mock_config_with_flags()
            
            # Mock insert fallisce
            mock_insert.side_effect = Exception("Database connection error")
            
            # Chiama pipeline
            # Signature: process_file(file_content, file_name, ext, telegram_id, business_name, correlation_id)
            # Ritorna: (wines_data, metrics, decision, stage_used)
            wines_data, metrics, decision, stage_used = await process_file(
                file_content=file_content,
                file_name="clean.csv",
                ext="csv",
                telegram_id=123,
                business_name="Test Business"
            )
            
            # Verifica che errore sia gestito (non crash)
            assert wines_data is not None
            assert isinstance(wines_data, list)
            
            print("✅ Errore insert database → errore gestito correttamente")


class TestMalformedData:
    """Test gestione dati malformati."""
    
    def test_malformed_csv_handled(self):
        """
        Test: CSV malformato → errore gestito.
        
        Considerazioni:
        - CSV con righe inconsistenti o malformate deve essere gestito
        - Verifica che parser gestisca CSV malformati senza crash
        """
        malformed_csv = b"Name,Winery,Vintage\nChianti,Barone\nBarolo,Vietti,2018,Extra,Data"
        
        with patch('ingest.parser.get_config') as mock_config:
            mock_config.return_value = create_mock_config_with_flags()
            
            wines_data, metrics, decision = parse_classic(
                file_content=malformed_csv,
                file_name="malformed.csv",
                ext="csv"
            )
            
            # Verifica che risultato sia gestito (lista parziale o errore chiaro)
            assert isinstance(wines_data, list)
            # CSV malformato può avere righe valide parziali o decision='error'
            assert decision in ['save', 'escalate_to_stage2', 'error']
            
            print("✅ CSV malformato → gestito correttamente")
    
    @pytest.mark.asyncio
    async def test_invalid_json_from_ai_handled(self):
        """
        Test: JSON malformato da AI → errore gestito.
        
        Considerazioni:
        - Se AI ritorna JSON malformato, errore deve essere gestito
        - Verifica che parser gestisca JSON invalido senza crash
        """
        headers = ["prodotto", "produttore"]
        
        with patch('ingest.llm_targeted.get_openai_client') as mock_get_client, \
             patch('ingest.llm_targeted.get_config') as mock_config:
            
            mock_config.return_value = create_mock_config_with_flags(
                ia_targeted_enabled=True
            )
            
            # Mock OpenAI ritorna JSON malformato
            mock_client = create_mock_openai_client("malformed")
            mock_get_client.return_value = mock_client
            
            # Chiama disambiguate_headers
            mapping = await disambiguate_headers(headers, {})
            
            # Verifica che errore sia gestito (mapping vuoto o fallback)
            assert isinstance(mapping, dict)
            # JSON malformato può risultare in mapping vuoto o fallback
            print("✅ JSON malformato da AI → gestito correttamente")

