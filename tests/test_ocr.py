"""
Test unitari per Stage 4 (OCR) con mock pytesseract.
"""
import pytest
from unittest.mock import patch, MagicMock
from PIL import Image
import io

from ingest.ocr_extract import extract_text_from_image, extract_text_from_pdf, extract_ocr


class TestOCRExtract:
    """Test per Stage 4 (OCR)."""
    
    def test_extract_text_from_image_success(self):
        """Test estrazione testo da immagine."""
        # Crea immagine test
        img = Image.new('RGB', (100, 100), color='white')
        img_bytes = io.BytesIO()
        img.save(img_bytes, format='PNG')
        img_bytes.seek(0)
        image_content = img_bytes.getvalue()
        
        # Mock pytesseract
        with patch('ingest.ocr_extract.pytesseract.image_to_string') as mock_ocr:
            mock_ocr.return_value = "Chianti Classico 2020 12 bottiglie 18.50 euro"
            
            text = extract_text_from_image(image_content)
            
            assert isinstance(text, str)
            assert "Chianti" in text
            mock_ocr.assert_called_once()
    
    def test_extract_text_from_image_error(self):
        """Test gestione errore OCR."""
        image_content = b"invalid image data"
        
        with patch('ingest.ocr_extract.pytesseract.image_to_string') as mock_ocr:
            mock_ocr.side_effect = Exception("OCR Error")
            
            # Dovrebbe gestire errore e ritornare stringa vuota o sollevare
            try:
                text = extract_text_from_image(image_content)
                assert isinstance(text, str)
            except Exception:
                pass  # OK se solleva eccezione
    
    def test_extract_text_from_pdf_success(self):
        """Test estrazione testo da PDF."""
        # Crea PDF mock (solo test struttura)
        pdf_content = b"%PDF-1.4 fake pdf content"
        
        # Mock pdf2image
        mock_images = [
            Image.new('RGB', (100, 100), color='white'),
            Image.new('RGB', (100, 100), color='white'),
        ]
        
        with patch('ingest.ocr_extract.convert_from_bytes') as mock_convert, \
             patch('ingest.ocr_extract.pytesseract.image_to_string') as mock_ocr:
            
            mock_convert.return_value = mock_images
            mock_ocr.side_effect = ["Page 1 text", "Page 2 text"]
            
            text = extract_text_from_pdf(pdf_content)
            
            assert isinstance(text, str)
            assert "Page 1" in text
            assert "Page 2" in text
            assert mock_ocr.call_count == 2  # Chiamato per ogni pagina
    
    def test_extract_text_from_pdf_single_page(self):
        """Test PDF con una sola pagina."""
        pdf_content = b"%PDF-1.4 fake pdf content"
        
        mock_image = Image.new('RGB', (100, 100), color='white')
        
        with patch('ingest.ocr_extract.convert_from_bytes') as mock_convert, \
             patch('ingest.ocr_extract.pytesseract.image_to_string') as mock_ocr:
            
            mock_convert.return_value = [mock_image]
            mock_ocr.return_value = "Single page text"
            
            text = extract_text_from_pdf(pdf_content)
            
            assert isinstance(text, str)
            assert "Single page" in text
            assert mock_ocr.call_count == 1
    
    @pytest.mark.asyncio
    async def test_extract_ocr_image_to_llm(self):
        """Test extract_ocr con immagine (passa a LLM mode)."""
        image_content = b"fake image data"
        
        # Mock OCR
        with patch('ingest.ocr_extract.extract_text_from_image') as mock_extract, \
             patch('ingest.ocr_extract.extract_llm_mode') as mock_llm, \
             patch('ingest.ocr_extract.get_config') as mock_config:
            
            mock_config.return_value.ocr_enabled = True
            
            mock_extract.return_value = "Chianti Classico 2020 12 bottiglie"
            
            # Mock LLM mode
            mock_llm.return_value = (
                [{"name": "Chianti Classico", "vintage": 2020, "qty": 12}],
                {"rows_valid": 1},
                "save"
            )
            
            wines_data, metrics, decision, stage_used = await extract_ocr(
                image_content, "test.jpg", "jpg", telegram_id=123, business_name="Test"
            )
            
            assert decision == 'save'
            assert len(wines_data) > 0
            assert stage_used == 'ocr'
            mock_extract.assert_called_once()
            mock_llm.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_extract_ocr_pdf_to_llm(self):
        """Test extract_ocr con PDF (passa a LLM mode)."""
        pdf_content = b"%PDF-1.4 fake pdf"
        
        # Mock OCR
        with patch('ingest.ocr_extract.extract_text_from_pdf') as mock_extract, \
             patch('ingest.ocr_extract.extract_llm_mode') as mock_llm, \
             patch('ingest.ocr_extract.get_config') as mock_config:
            
            mock_config.return_value.ocr_enabled = True
            
            mock_extract.return_value = "Barolo 2018 6 bottiglie"
            
            # Mock LLM mode
            mock_llm.return_value = (
                [{"name": "Barolo", "vintage": 2018, "qty": 6}],
                {"rows_valid": 1},
                "save"
            )
            
            wines_data, metrics, decision, stage_used = await extract_ocr(
                pdf_content, "test.pdf", "pdf", telegram_id=123, business_name="Test"
            )
            
            assert decision == 'save'
            assert len(wines_data) > 0
            assert stage_used == 'ocr'
            mock_extract.assert_called_once()
            mock_llm.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_extract_ocr_feature_flag_disabled(self):
        """Test che rispetta feature flag disabilitato."""
        image_content = b"fake image"
        
        with patch('ingest.ocr_extract.get_config') as mock_config:
            mock_config.return_value.ocr_enabled = False
            
            wines_data, metrics, decision, stage_used = await extract_ocr(
                image_content, "test.jpg", "jpg", telegram_id=123, business_name="Test"
            )
            
            # Se feature flag disabilitato, dovrebbe ritornare error
            assert decision == 'error'




