"""
Test Phase 9.3: Test Performance
Verifica che i tempi di elaborazione rispettino le soglie definite.
"""
import pytest
import time
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock
import json

from ingest.parser import parse_classic
from ingest.llm_targeted import fix_ambiguous_rows, apply_targeted_ai
from ingest.llm_extract import extract_with_llm, chunk_text
from ingest.ocr_extract import extract_text_from_image, extract_text_from_pdf
from tests.mocks import create_mock_openai_client, create_mock_config_with_flags

# Percorso file fixture
FIXTURES_DIR = Path(__file__).parent / "data"


class TestPerformance:
    """Test performance per verificare tempi elaborazione."""
    
    def test_stage1_small_csv_under_2s(self):
        """
        Test Stage 1: verifica che parsing CSV piccolo (< 200 righe) sia < 2s.
        
        Considerazioni:
        - File piccolo: 50-200 righe
        - Include: encoding detection, delimiter sniffing, parsing, normalization, validation
        - Escludere: I/O rete, solo CPU/logic locale
        """
        csv_path = FIXTURES_DIR / "clean.csv"
        
        with open(csv_path, "rb") as f:
            file_content = f.read()
        
        with patch('ingest.parser.get_config') as mock_config:
            mock_config.return_value = create_mock_config_with_flags()
            
            start_time = time.time()
            
            wines_data, metrics, decision = parse_classic(
                file_content=file_content,
                file_name="clean.csv",
                ext="csv"
            )
            
            elapsed_time = time.time() - start_time
            
            # Verifica che risultato sia valido
            assert wines_data is not None
            assert isinstance(wines_data, list)
            assert decision in ['save', 'escalate_to_stage2']
            
            # Verifica tempo < 2s
            assert elapsed_time < 2.0, f"Stage 1 ha impiegato {elapsed_time:.2f}s, soglia: 2s"
            
            print(f"✅ Stage 1: {elapsed_time:.3f}s (soglia: 2s)")
    
    @pytest.mark.asyncio
    async def test_stage2_batch_20_under_5s(self):
        """
        Test Stage 2: verifica che correzione batch 20 righe ambigue sia < 5s.
        
        Considerazioni:
        - Batch size: 20 righe ambigue (default)
        - Include: chiamata OpenAI, parsing JSON, normalizzazione
        - Mock OpenAI per risultati deterministici (no rete)
        """
        # Crea batch di 20 righe ambigue
        batch_rows = [
            {
                "name": f"Wine {i}",
                "winery": f"Producer {i}",
                "vintage": "2020",  # String invece di int
                "qty": f"{i * 2} bottiglie",  # String con unità
                "price": f"{i * 10}.50 euro"  # String con unità
            }
            for i in range(20)
        ]
        
        with patch('ingest.llm_targeted.get_openai_client') as mock_get_client, \
             patch('ingest.llm_targeted.get_config') as mock_config:
            
            # Mock config
            mock_config.return_value = create_mock_config_with_flags(
                ia_targeted_enabled=True,
                batch_size_ambiguous_rows=20,
                max_llm_tokens=300
            )
            
            # Mock OpenAI (successo rapido)
            mock_response = [
                {
                    "name": f"Wine {i}",
                    "winery": f"Producer {i}",
                    "vintage": 2020,
                    "qty": i * 2,
                    "price": i * 10.50
                }
                for i in range(20)
            ]
            
            mock_client = create_mock_openai_client("success", mock_response)
            mock_get_client.return_value = mock_client
            
            start_time = time.time()
            
            fixed_rows = await fix_ambiguous_rows(batch_rows)
            
            elapsed_time = time.time() - start_time
            
            # Verifica risultato
            assert len(fixed_rows) == len(batch_rows)
            
            # Verifica tempo < 5s
            assert elapsed_time < 5.0, f"Stage 2 ha impiegato {elapsed_time:.2f}s, soglia: 5s"
            
            print(f"✅ Stage 2 (batch 20): {elapsed_time:.3f}s (soglia: 5s)")
    
    @pytest.mark.asyncio
    async def test_stage3_chunk_under_15s(self):
        """
        Test Stage 3: verifica che estrazione LLM per chunk 4k token sia < 15s.
        
        Considerazioni:
        - Chunk size: ~4000 token (circa 3000 caratteri)
        - Include: chiamata OpenAI, parsing JSON, deduplicazione
        - Mock OpenAI per risultati deterministici (no rete)
        """
        # Crea testo di ~3000 caratteri (circa 4000 token)
        text_chunk = "Chianti Classico Barone Ricasoli 2020 12 bottiglie 18.50 euro " * 50
        assert len(text_chunk) > 3000  # Verifica dimensione
        
        with patch('ingest.llm_extract.get_openai_client') as mock_get_client, \
             patch('ingest.llm_extract.get_config') as mock_config:
            
            # Mock config
            mock_config.return_value = create_mock_config_with_flags(
                llm_fallback_enabled=True,
                llm_model_extract="gpt-4o"
            )
            
            # Mock OpenAI (successo rapido)
            mock_response = {
                "wines": [
                    {"name": "Chianti Classico", "winery": "Barone Ricasoli", "vintage": 2020, "qty": 12, "price": 18.50}
                ]
            }
            
            mock_client = create_mock_openai_client("success", mock_response)
            mock_get_client.return_value = mock_client
            
            start_time = time.time()
            
            wines = await extract_with_llm(text_chunk, "test.txt")
            
            elapsed_time = time.time() - start_time
            
            # Verifica risultato
            assert wines is not None
            assert isinstance(wines, list)
            
            # Verifica tempo < 15s
            assert elapsed_time < 15.0, f"Stage 3 ha impiegato {elapsed_time:.2f}s, soglia: 15s"
            
            print(f"✅ Stage 3 (chunk 4k token): {elapsed_time:.3f}s (soglia: 15s)")
    
    def test_stage4_per_page_under_10s(self):
        """
        Test Stage 4: verifica che OCR per pagina immagine sia < 10s.
        
        Considerazioni:
        - Immagine: 1000x1000 pixel (simulato)
        - Include: conversione immagine, OCR, estrazione testo
        - Mock pytesseract per risultati deterministici (no binari OCR)
        """
        from PIL import Image
        import io
        
        # Crea immagine test (1000x1000)
        img = Image.new('RGB', (1000, 1000), color='white')
        img_bytes = io.BytesIO()
        img.save(img_bytes, format='PNG')
        img_bytes.seek(0)
        image_content = img_bytes.getvalue()
        
        with patch('ingest.ocr_extract.pytesseract.image_to_string') as mock_ocr:
            # Mock OCR (successo rapido)
            mock_ocr.return_value = "Chianti Classico 2020 12 bottiglie 18.50 euro"
            
            start_time = time.time()
            
            text = extract_text_from_image(image_content)
            
            elapsed_time = time.time() - start_time
            
            # Verifica risultato
            assert isinstance(text, str)
            assert len(text) > 0
            
            # Verifica tempo < 10s per pagina
            assert elapsed_time < 10.0, f"Stage 4 ha impiegato {elapsed_time:.2f}s, soglia: 10s"
            
            print(f"✅ Stage 4 (1 pagina OCR): {elapsed_time:.3f}s (soglia: 10s)")
    
    def test_stage4_pdf_multipage_performance(self):
        """
        Test Stage 4: verifica che OCR per PDF multipagina rispetti 10s per pagina.
        
        Considerazioni:
        - PDF: 3 pagine (simulate)
        - Include: conversione PDF→immagini, OCR per ogni pagina
        - Mock pdf2image e pytesseract per risultati deterministici
        """
        from PIL import Image
        
        pdf_content = b"%PDF-1.4 fake pdf content"
        num_pages = 3
        
        # Mock immagini (3 pagine)
        mock_images = [
            Image.new('RGB', (1000, 1000), color='white')
            for _ in range(num_pages)
        ]
        
        with patch('ingest.ocr_extract.convert_from_bytes') as mock_convert, \
             patch('ingest.ocr_extract.pytesseract.image_to_string') as mock_ocr:
            
            mock_convert.return_value = mock_images
            mock_ocr.side_effect = [f"Page {i+1} text" for i in range(num_pages)]
            
            start_time = time.time()
            
            text = extract_text_from_pdf(pdf_content)
            
            elapsed_time = time.time() - start_time
            
            # Verifica risultato
            assert isinstance(text, str)
            assert len(text) > 0
            
            # Verifica tempo < 10s per pagina
            time_per_page = elapsed_time / num_pages
            assert time_per_page < 10.0, f"Stage 4 PDF: {time_per_page:.2f}s per pagina, soglia: 10s"
            
            print(f"✅ Stage 4 (PDF {num_pages} pagine): {elapsed_time:.3f}s totale, {time_per_page:.3f}s per pagina (soglia: 10s)")
    
    def test_stage1_large_csv_performance(self):
        """
        Test Stage 1: verifica performance con CSV grande (1000+ righe).
        
        Considerazioni:
        - File grande: 1000+ righe
        - Verifica che non degradi troppo (non bloccante ma utile per benchmark)
        """
        # Genera CSV grande (1000 righe)
        csv_lines = ["Nome,Cantina,Annata,Quantità,Prezzo,Tipo"]
        for i in range(1000):
            csv_lines.append(f"Wine {i},Producer {i},2020,{i*2},{i*10}.50,Rosso")
        
        csv_content = "\n".join(csv_lines).encode('utf-8')
        
        with patch('ingest.parser.get_config') as mock_config:
            mock_config.return_value = create_mock_config_with_flags()
            
            start_time = time.time()
            
            wines_data, metrics, decision = parse_classic(
                file_content=csv_content,
                file_name="large.csv",
                ext="csv"
            )
            
            elapsed_time = time.time() - start_time
            
            # Verifica risultato
            assert wines_data is not None
            assert isinstance(wines_data, list)
            
            # Verifica che non sia eccessivamente lento (benchmark: < 10s per 1000 righe)
            assert elapsed_time < 10.0, f"Stage 1 CSV grande ha impiegato {elapsed_time:.2f}s, benchmark: 10s"
            
            print(f"✅ Stage 1 (CSV 1000 righe): {elapsed_time:.3f}s (benchmark: 10s)")


class TestPerformanceChunking:
    """Test performance per chunking testo."""
    
    def test_chunk_text_performance(self):
        """
        Test performance chunking testo grande.
        
        Considerazioni:
        - Testo grande: 100KB+ (circa 70k caratteri)
        - Verifica che chunking sia efficiente (O(n))
        """
        # Genera testo grande
        text = "Test content " * 10000  # ~140 KB
        
        start_time = time.time()
        
        chunks = chunk_text(text, chunk_size=4000, overlap=1000)
        
        elapsed_time = time.time() - start_time
        
        # Verifica risultato
        assert len(chunks) > 1
        
        # Verifica che chunking sia veloce (< 1s anche per file molto grandi)
        assert elapsed_time < 1.0, f"Chunking ha impiegato {elapsed_time:.2f}s, soglia: 1s"
        
        print(f"✅ Chunking (100KB): {elapsed_time:.3f}s (soglia: 1s)")

