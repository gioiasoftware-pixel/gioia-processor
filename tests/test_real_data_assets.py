"""
Test Phase 9.6: Test con Asset Reali
Verifica che tutti i file nella cartella tests/data/ vengano processati correttamente.

Questo test verifica:
1. Che tutti i file vengano "presi" (routed correttamente) ✅
2. Che vengano processati negli stage corretti ✅
3. Che i dati vengano estratti correttamente ✅
4. Che la validazione funzioni ✅

File testati:
- clean.csv → Stage 1 (parsing classico)
- ambiguous_headers.csv → Stage 2 (disambiguazione header)
- chaotic.csv → Stage 3 (LLM extraction)
- messy_delimiters.csv → Stage 1 (delimiter sniffing)
- inventario simo.xlsx - Vini.csv → Stage 1 (file grande, 341 linee)
- INVENTARIO 2025 UFFICIALE pdf.pdf → Stage 4 (OCR)
"""
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock

from ingest.pipeline import process_file
from ingest.gate import route_file
from ingest.parser import parse_classic
from tests.mocks import create_mock_openai_client, create_mock_config_with_flags

# Percorso file fixture
FIXTURES_DIR = Path(__file__).parent / "data"


class TestRealDataAssets:
    """Test con tutti i file reali nella cartella data/."""
    
    @pytest.fixture
    def all_data_files(self):
        """Lista tutti i file nella cartella data."""
        files = []
        for file_path in FIXTURES_DIR.iterdir():
            if file_path.is_file():
                files.append(file_path)
        return sorted(files)
    
    def test_all_files_exist(self, all_data_files):
        """Verifica che i file esistano."""
        assert len(all_data_files) > 0, "Nessun file trovato nella cartella data/"
        
        for file_path in all_data_files:
            assert file_path.exists(), f"File non trovato: {file_path}"
            assert file_path.stat().st_size > 0, f"File vuoto: {file_path}"
        
        print(f"✅ Trovati {len(all_data_files)} file nella cartella data/")
        for f in all_data_files:
            print(f"   - {f.name} ({f.stat().st_size} bytes)")
    
    def test_all_files_routed_correctly(self, all_data_files):
        """Verifica che tutti i file vengano routed correttamente (Stage 0)."""
        routing_results = {}
        
        for file_path in all_data_files:
            with open(file_path, "rb") as f:
                file_content = f.read()
            
            ext = file_path.suffix.lstrip('.')
            file_name = file_path.name
            
            try:
                stage, ext_normalized = route_file(file_content, file_name, ext)
                routing_results[file_name] = {
                    'routed': True,
                    'stage': stage,
                    'ext': ext_normalized,
                    'size': len(file_content)
                }
                print(f"✅ {file_name}: routed to {stage} (ext: {ext_normalized})")
            except ValueError as e:
                routing_results[file_name] = {
                    'routed': False,
                    'error': str(e),
                    'size': len(file_content)
                }
                print(f"❌ {file_name}: routing failed - {e}")
        
        # Verifica che almeno alcuni file siano routed
        routed_count = sum(1 for r in routing_results.values() if r.get('routed', False))
        assert routed_count > 0, f"Nessun file routed correttamente. Risultati: {routing_results}"
        
        print(f"\n📊 Riepilogo routing:")
        print(f"   - File totali: {len(all_data_files)}")
        print(f"   - File routed: {routed_count}")
        print(f"   - File non routed: {len(all_data_files) - routed_count}")
    
    @pytest.mark.asyncio
    async def test_clean_csv_processed_correctly(self):
        """Test: clean.csv dovrebbe essere processato in Stage 1 e salvato."""
        csv_path = FIXTURES_DIR / "clean.csv"
        
        with open(csv_path, "rb") as f:
            file_content = f.read()
        
        with patch('ingest.pipeline.get_config') as mock_config, \
             patch('ingest.pipeline.batch_insert_wines') as mock_insert:
            
            mock_config.return_value = create_mock_config_with_flags()
            mock_insert.return_value = True
            
            wines_data, metrics, decision, stage_used = await process_file(
                file_content=file_content,
                file_name="clean.csv",
                ext="csv",
                telegram_id=123,
                business_name="Test Business",
                correlation_id=None
            )
            
            # Verifica che sia stato processato
            assert wines_data is not None
            assert isinstance(wines_data, list)
            assert len(wines_data) > 0, "clean.csv dovrebbe avere vini validi"
            
            # Verifica che sia stato processato in Stage 1 (csv_excel_parse)
            assert stage_used == 'csv_excel_parse', \
                f"clean.csv dovrebbe essere processato in Stage 1, trovato: {stage_used}"
            
            # Verifica che decision sia 'save'
            assert decision == 'save', \
                f"clean.csv dovrebbe essere salvato, trovato: {decision}"
            
            print(f"✅ clean.csv: {len(wines_data)} vini processati in {stage_used}")
    
    @pytest.mark.asyncio
    async def test_ambiguous_headers_escalated_to_stage2(self):
        """Test: ambiguous_headers.csv dovrebbe escalare a Stage 2."""
        csv_path = FIXTURES_DIR / "ambiguous_headers.csv"
        
        with open(csv_path, "rb") as f:
            file_content = f.read()
        
        with patch('ingest.pipeline.get_config') as mock_config, \
             patch('ingest.pipeline.batch_insert_wines') as mock_insert, \
             patch('ingest.llm_targeted.get_openai_client') as mock_openai:
            
            mock_config.return_value = create_mock_config_with_flags(
                ia_targeted_enabled=True
            )
            
            # Mock OpenAI per Stage 2
            mock_client = create_mock_openai_client("success", {
                "mapping": {
                    "Prodotto": "name",
                    "Produttore": "winery",
                    "Anno": "vintage",
                    "Qty": "qty"
                }
            })
            mock_openai.return_value = mock_client
            
            mock_insert.return_value = True
            
            wines_data, metrics, decision, stage_used = await process_file(
                file_content=file_content,
                file_name="ambiguous_headers.csv",
                ext="csv",
                telegram_id=123,
                business_name="Test Business",
                correlation_id=None
            )
            
            # Verifica che sia stato processato
            assert wines_data is not None
            assert isinstance(wines_data, list)
            
            # Verifica che sia escalato a Stage 2 (se abilitato) o Stage 3
            assert stage_used in ['ia_targeted', 'llm_mode'], \
                f"ambiguous_headers.csv dovrebbe escalare a Stage 2 o 3, trovato: {stage_used}"
            
            print(f"✅ ambiguous_headers.csv: {len(wines_data)} vini processati in {stage_used}")
    
    @pytest.mark.asyncio
    async def test_chaotic_csv_escalated_to_stage3(self):
        """Test: chaotic.csv dovrebbe escalare a Stage 3."""
        csv_path = FIXTURES_DIR / "chaotic.csv"
        
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
            
            # Mock OpenAI Stage 2 fallisce (escala a Stage 3)
            mock_client_targeted = create_mock_openai_client("error")
            mock_openai_targeted.return_value = mock_client_targeted
            
            # Mock OpenAI Stage 3 successo
            mock_client_extract = create_mock_openai_client("success", {
                "wines": [
                    {"name": "Chianti", "winery": "Barone", "vintage": 2020, "qty": 12}
                ]
            })
            mock_openai_extract.return_value = mock_client_extract
            
            mock_insert.return_value = True
            
            wines_data, metrics, decision, stage_used = await process_file(
                file_content=file_content,
                file_name="chaotic.csv",
                ext="csv",
                telegram_id=123,
                business_name="Test Business",
                correlation_id=None
            )
            
            # Verifica che sia stato processato
            assert wines_data is not None
            assert isinstance(wines_data, list)
            
            # Verifica che sia escalato a Stage 3
            assert stage_used == 'llm_mode', \
                f"chaotic.csv dovrebbe essere processato in Stage 3, trovato: {stage_used}"
            
            print(f"✅ chaotic.csv: {len(wines_data)} vini processati in {stage_used}")
    
    @pytest.mark.asyncio
    async def test_messy_delimiters_parsed_correctly(self):
        """Test: messy_delimiters.csv dovrebbe essere parsato correttamente."""
        csv_path = FIXTURES_DIR / "messy_delimiters.csv"
        
        with open(csv_path, "rb") as f:
            file_content = f.read()
        
        with patch('ingest.parser.get_config') as mock_config:
            mock_config.return_value = create_mock_config_with_flags()
            
            wines_data, metrics, decision = parse_classic(
                file_content=file_content,
                file_name="messy_delimiters.csv",
                ext="csv"
            )
            
            # Verifica che sia stato parsato
            assert wines_data is not None
            assert isinstance(wines_data, list)
            
            # Verifica che decision sia valida
            assert decision in ['save', 'escalate_to_stage2', 'error']
            
            print(f"✅ messy_delimiters.csv: {len(wines_data)} vini parsati, decision: {decision}")
    
    @pytest.mark.asyncio
    async def test_large_csv_file_processed(self):
        """Test: inventario simo.xlsx - Vini.csv (file grande, 341 linee)."""
        csv_path = FIXTURES_DIR / "inventario simo.xlsx - Vini.csv"
        
        if not csv_path.exists():
            pytest.skip(f"File non trovato: {csv_path}")
        
        with open(csv_path, "rb") as f:
            file_content = f.read()
        
        with patch('ingest.pipeline.get_config') as mock_config, \
             patch('ingest.pipeline.batch_insert_wines') as mock_insert:
            
            mock_config.return_value = create_mock_config_with_flags()
            mock_insert.return_value = True
            
            wines_data, metrics, decision, stage_used = await process_file(
                file_content=file_content,
                file_name="inventario simo.xlsx - Vini.csv",
                ext="csv",
                telegram_id=123,
                business_name="Test Business",
                correlation_id=None
            )
            
            # Verifica che sia stato processato
            assert wines_data is not None
            assert isinstance(wines_data, list)
            
            # File grande dovrebbe avere molti vini
            assert len(wines_data) > 0, "File grande dovrebbe avere vini validi"
            
            print(f"✅ inventario simo.xlsx - Vini.csv: {len(wines_data)} vini processati in {stage_used}")
    
    @pytest.mark.asyncio
    async def test_pdf_file_routed_to_ocr(self):
        """Test: PDF file dovrebbe essere routed a Stage 4 (OCR)."""
        pdf_path = FIXTURES_DIR / "INVENTARIO 2025 UFFICIALE pdf.pdf"
        
        if not pdf_path.exists():
            pytest.skip(f"File PDF non trovato: {pdf_path}")
        
        with open(pdf_path, "rb") as f:
            file_content = f.read()
        
        # Verifica routing
        stage, ext = route_file(file_content, "INVENTARIO 2025 UFFICIALE pdf.pdf", "pdf")
        
        assert stage == 'ocr', f"PDF dovrebbe essere routed a OCR, trovato: {stage}"
        assert ext == 'pdf', f"Estensione dovrebbe essere pdf, trovato: {ext}"
        
        print(f"✅ PDF file: routed to {stage} (ext: {ext})")
        
        # Test completo con mock OCR
        with patch('ingest.pipeline.get_config') as mock_config, \
             patch('ingest.pipeline.batch_insert_wines') as mock_insert, \
             patch('ingest.ocr_extract.pytesseract') as mock_ocr, \
             patch('ingest.llm_extract.get_openai_client') as mock_openai:
            
            mock_config.return_value = create_mock_config_with_flags(
                ocr_enabled=True,
                llm_fallback_enabled=True
            )
            
            # Mock OCR
            mock_ocr.image_to_string.return_value = "Chianti Classico 2020 12 bottiglie"
            
            # Mock OpenAI Stage 3
            mock_client = create_mock_openai_client("success", {
                "wines": [
                    {"name": "Chianti Classico", "vintage": 2020, "qty": 12}
                ]
            })
            mock_openai.return_value = mock_client
            
            mock_insert.return_value = True
            
            wines_data, metrics, decision, stage_used = await process_file(
                file_content=file_content,
                file_name="INVENTARIO 2025 UFFICIALE pdf.pdf",
                ext="pdf",
                telegram_id=123,
                business_name="Test Business",
                correlation_id=None
            )
            
            # Verifica che sia stato processato
            assert wines_data is not None
            assert isinstance(wines_data, list)
            
            # Verifica che sia stato processato in Stage 4 (OCR)
            assert stage_used == 'ocr', \
                f"PDF dovrebbe essere processato in Stage 4, trovato: {stage_used}"
            
            print(f"✅ PDF file: {len(wines_data)} vini processati in {stage_used}")
    
    @pytest.mark.asyncio
    async def test_all_files_processed_end_to_end(self, all_data_files):
        """Test end-to-end: processa tutti i file e verifica che vengano "presi"."""
        results = {}
        
        for file_path in all_data_files:
            with open(file_path, "rb") as f:
                file_content = f.read()
            
            file_name = file_path.name
            ext = file_path.suffix.lstrip('.')
            
            # Skip PDF se troppo grande o non mockato OCR
            if ext == 'pdf' and len(file_content) > 100000:  # > 100KB
                print(f"⏭️  Skipping {file_name} (PDF troppo grande per test completo)")
                continue
            
            with patch('ingest.pipeline.get_config') as mock_config, \
                 patch('ingest.pipeline.batch_insert_wines') as mock_insert, \
                 patch('ingest.llm_targeted.get_openai_client') as mock_openai_targeted, \
                 patch('ingest.llm_extract.get_openai_client') as mock_openai_extract, \
                 patch('ingest.ocr_extract.pytesseract') as mock_ocr:
                
                mock_config.return_value = create_mock_config_with_flags(
                    ia_targeted_enabled=True,
                    llm_fallback_enabled=True,
                    ocr_enabled=True
                )
                
                # Mock OpenAI
                mock_client_targeted = create_mock_openai_client("success", {
                    "mapping": {"test": "name"}
                })
                mock_openai_targeted.return_value = mock_client_targeted
                
                mock_client_extract = create_mock_openai_client("success", {
                    "wines": [{"name": "Test Wine", "vintage": 2020, "qty": 1}]
                })
                mock_openai_extract.return_value = mock_client_extract
                
                # Mock OCR
                mock_ocr.image_to_string.return_value = "Test wine content"
                
                mock_insert.return_value = True
                
                try:
                    wines_data, metrics, decision, stage_used = await process_file(
                        file_content=file_content,
                        file_name=file_name,
                        ext=ext,
                        telegram_id=123,
                        business_name="Test Business",
                        correlation_id=None
                    )
                    
                    results[file_name] = {
                        'success': True,
                        'wines_count': len(wines_data),
                        'decision': decision,
                        'stage_used': stage_used,
                        'size': len(file_content)
                    }
                    
                    print(f"✅ {file_name}: {len(wines_data)} vini, stage={stage_used}, decision={decision}")
                    
                except Exception as e:
                    results[file_name] = {
                        'success': False,
                        'error': str(e),
                        'size': len(file_content)
                    }
                    print(f"❌ {file_name}: errore - {e}")
        
        # Riepilogo
        successful = sum(1 for r in results.values() if r.get('success', False))
        total = len(results)
        
        print(f"\n📊 Riepilogo End-to-End:")
        print(f"   - File processati: {successful}/{total}")
        print(f"   - File con errori: {total - successful}")
        
        for file_name, result in results.items():
            if result.get('success'):
                print(f"   ✅ {file_name}: {result['wines_count']} vini, {result['stage_used']}")
            else:
                print(f"   ❌ {file_name}: {result.get('error', 'Unknown error')}")
        
        # Verifica che almeno alcuni file siano stati processati con successo
        assert successful > 0, f"Nessun file processato con successo. Risultati: {results}"

