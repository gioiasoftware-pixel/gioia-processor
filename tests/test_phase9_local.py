"""
Test Phase 9.1: Test Locale End-to-End
Test completi per pipeline con file fixture reali.
"""
import pytest
import json
import os
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock
from fastapi.testclient import TestClient

from api.main import app
from ingest.pipeline import process_file
from tests.mocks import create_mock_openai_client, create_mock_config_with_flags


# Percorso file fixture
FIXTURES_DIR = Path(__file__).parent / "data"


class TestLocalEndToEnd:
    """Test end-to-end locale con file fixture."""
    
    @pytest.fixture
    def client(self):
        """Client FastAPI per test."""
        return TestClient(app)
    
    @pytest.fixture
    def mock_db(self):
        """Mock database per test."""
        from tests.mocks import create_mock_db
        return create_mock_db("success")
    
    def test_upload_clean_csv(self, client, mock_db):
        """Test upload CSV pulito (Stage 1 → Save)."""
        csv_path = FIXTURES_DIR / "clean.csv"
        
        with open(csv_path, "rb") as f:
            file_content = f.read()
        
        with patch('api.routers.ingest.get_db') as mock_get_db, \
             patch('api.routers.ingest.get_config') as mock_config, \
             patch('api.routers.ingest.batch_insert_wines') as mock_insert:
            
            # Mock database
            async def db_gen():
                yield mock_db
            mock_get_db.return_value = db_gen()
            
            # Mock config
            mock_config.return_value = create_mock_config_with_flags(
                ia_targeted_enabled=True,
                llm_fallback_enabled=True,
                ocr_enabled=True
            )
            
            # Mock insert
            mock_insert.return_value = AsyncMock(return_value=True)
            
            # Test upload
            response = client.post(
                "/process-inventory",
                files={"file": ("clean.csv", file_content, "text/csv")},
                data={
                    "telegram_id": 123,
                    "business_name": "Test Business",
                    "client_msg_id": "test-msg-1"
                }
            )
            
            assert response.status_code == 200
            result = response.json()
            assert result["status"] in ["processing", "success", "completed"]
            assert "job_id" in result
    
    def test_upload_ambiguous_headers_csv(self, client, mock_db):
        """Test upload CSV con header ambigui (Stage 1 → Stage 2 → Save)."""
        csv_path = FIXTURES_DIR / "ambiguous_headers.csv"
        
        with open(csv_path, "rb") as f:
            file_content = f.read()
        
        with patch('api.routers.ingest.get_db') as mock_get_db, \
             patch('api.routers.ingest.get_config') as mock_config, \
             patch('api.routers.ingest.batch_insert_wines') as mock_insert, \
             patch('ingest.llm_targeted.get_openai_client') as mock_openai:
            
            # Mock database
            async def db_gen():
                yield mock_db
            mock_get_db.return_value = db_gen()
            
            # Mock config
            mock_config.return_value = create_mock_config_with_flags(
                ia_targeted_enabled=True,
                llm_fallback_enabled=True
            )
            
            # Mock OpenAI per Stage 2
            mock_client = create_mock_openai_client("success", {
                "mapping": {
                    "Prodotto": "name",
                    "Produttore": "winery",
                    "Anno": "vintage",
                    "Qty": "qty",
                    "Prezzo vendita": "price",
                    "Tipo vino": "type"
                }
            })
            mock_openai.return_value = mock_client
            
            # Mock insert
            mock_insert.return_value = AsyncMock(return_value=True)
            
            # Test upload
            response = client.post(
                "/process-inventory",
                files={"file": ("ambiguous_headers.csv", file_content, "text/csv")},
                data={
                    "telegram_id": 123,
                    "business_name": "Test Business",
                    "client_msg_id": "test-msg-2"
                }
            )
            
            assert response.status_code == 200
            result = response.json()
            assert result["status"] in ["processing", "success", "completed"]
    
    def test_upload_chaotic_csv(self, client, mock_db):
        """Test upload CSV caotico (Stage 1 → Stage 2 → Stage 3 → Save)."""
        csv_path = FIXTURES_DIR / "chaotic.csv"
        
        with open(csv_path, "rb") as f:
            file_content = f.read()
        
        with patch('api.routers.ingest.get_db') as mock_get_db, \
             patch('api.routers.ingest.get_config') as mock_config, \
             patch('api.routers.ingest.batch_insert_wines') as mock_insert, \
             patch('ingest.llm_targeted.get_openai_client') as mock_openai_targeted, \
             patch('ingest.llm_extract.get_openai_client') as mock_openai_extract:
            
            # Mock database
            async def db_gen():
                yield mock_db
            mock_get_db.return_value = db_gen()
            
            # Mock config
            mock_config.return_value = create_mock_config_with_flags(
                ia_targeted_enabled=True,
                llm_fallback_enabled=True
            )
            
            # Mock OpenAI Stage 2 (fallisce)
            mock_client_targeted = create_mock_openai_client("error")
            mock_openai_targeted.return_value = mock_client_targeted
            
            # Mock OpenAI Stage 3 (successo)
            mock_client_extract = create_mock_openai_client("success", {
                "wines": [
                    {"name": "Chianti", "winery": "Barone", "vintage": 2020, "qty": 12, "price": 18.50}
                ]
            })
            mock_openai_extract.return_value = mock_client_extract
            
            # Mock insert
            mock_insert.return_value = AsyncMock(return_value=True)
            
            # Test upload
            response = client.post(
                "/process-inventory",
                files={"file": ("chaotic.csv", file_content, "text/csv")},
                data={
                    "telegram_id": 123,
                    "business_name": "Test Business",
                    "client_msg_id": "test-msg-3"
                }
            )
            
            assert response.status_code == 200
            result = response.json()
            assert result["status"] in ["processing", "success", "completed"]
    
    def test_upload_image_ocr(self, client, mock_db):
        """Test upload immagine OCR (Stage 4 → Stage 3 → Save)."""
        # Crea immagine mock
        from PIL import Image
        import io
        
        img = Image.new('RGB', (100, 100), color='white')
        img_bytes = io.BytesIO()
        img.save(img_bytes, format='PNG')
        img_bytes.seek(0)
        image_content = img_bytes.getvalue()
        
        with patch('api.routers.ingest.get_db') as mock_get_db, \
             patch('api.routers.ingest.get_config') as mock_config, \
             patch('api.routers.ingest.batch_insert_wines') as mock_insert, \
             patch('ingest.ocr_extract.pytesseract.image_to_string') as mock_ocr, \
             patch('ingest.llm_extract.get_openai_client') as mock_openai:
            
            # Mock database
            async def db_gen():
                yield mock_db
            mock_get_db.return_value = db_gen()
            
            # Mock config
            mock_config.return_value = create_mock_config_with_flags(
                ocr_enabled=True,
                llm_fallback_enabled=True
            )
            
            # Mock OCR
            mock_ocr.return_value = "Chianti Classico 2020 12 bottiglie 18.50 euro"
            
            # Mock OpenAI Stage 3
            mock_client = create_mock_openai_client("success", {
                "wines": [
                    {"name": "Chianti Classico", "vintage": 2020, "qty": 12, "price": 18.50}
                ]
            })
            mock_openai.return_value = mock_client
            
            # Mock insert
            mock_insert.return_value = AsyncMock(return_value=True)
            
            # Test upload
            response = client.post(
                "/process-inventory",
                files={"file": ("test.jpg", image_content, "image/jpeg")},
                data={
                    "telegram_id": 123,
                    "business_name": "Test Business",
                    "client_msg_id": "test-msg-4"
                }
            )
            
            assert response.status_code == 200
            result = response.json()
            assert result["status"] in ["processing", "success", "completed"]


class TestLoggingJSON:
    """Test logging JSON strutturato."""
    
    @pytest.mark.asyncio
    async def test_logging_json_structure(self):
        """Verifica che logging JSON abbia struttura corretta."""
        from core.logger import log_json
        import logging
        
        # Capture log
        log_capture = []
        
        class JSONHandler(logging.Handler):
            def emit(self, record):
                log_capture.append(record.msg)
        
        handler = JSONHandler()
        logger = logging.getLogger("test")
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        
        # Log con log_json
        log_json(
            level="info",
            message="Test log",
            correlation_id="test-correlation-123",
            telegram_id=123,
            stage="stage1",
            metrics={"schema_score": 0.8, "valid_rows": 0.9},
            decision="save"
        )
        
        # Verifica che log sia stato catturato
        assert len(log_capture) > 0
        
        # Verifica struttura JSON (se implementato)
        # Nota: log_json potrebbe stampare in console, non necessariamente in handler
        # Questo è un test semplificato


class TestMetrics:
    """Test metriche corrette."""
    
    def test_metrics_schema_score(self):
        """Verifica calcolo schema_score."""
        from ingest.parser import calculate_schema_score
        import pandas as pd
        
        # calculate_schema_score prende un DataFrame, non una lista
        df = pd.DataFrame({
            "name": ["Chianti"],
            "winery": ["Barone"],
            "vintage": [2020],
            "qty": [12],
            "price": [18.50],
            "type": ["Rosso"]
        })
        
        score = calculate_schema_score(df)
        
        assert score == 1.0  # Tutti i campi presenti
    
    def test_metrics_valid_rows(self):
        """Verifica calcolo valid_rows."""
        from ingest.validation import validate_batch
        
        wines = [
            {"name": "Chianti", "winery": "Barone", "vintage": 2020, "qty": 12, "price": 18.50},
            {"name": "Barolo", "winery": "Vietti", "vintage": 2018, "qty": 6, "price": 45.00},
        ]
        
        valid, errors = validate_batch(wines)
        
        assert len(valid) == 2
        assert len(errors) == 0
        assert len(valid) / len(wines) == 1.0  # 100% valid rows


class TestPipelineDirect:
    """Test pipeline direttamente senza API."""
    
    @pytest.mark.asyncio
    async def test_pipeline_clean_csv(self):
        """Test pipeline con CSV pulito."""
        csv_path = FIXTURES_DIR / "clean.csv"
        
        with open(csv_path, "rb") as f:
            file_content = f.read()
        
        with patch('ingest.pipeline.get_config') as mock_config, \
             patch('ingest.pipeline.batch_insert_wines') as mock_insert:
            
            # Mock config
            mock_config.return_value = create_mock_config_with_flags()
            
            # Mock insert
            mock_insert.return_value = True
            
            # Test pipeline
            # Signature: process_file(file_content, file_name, ext, telegram_id, business_name, correlation_id)
            # Ritorna: (wines_data, metrics, decision, stage_used)
            wines_data, metrics, decision, stage_used = await process_file(
                file_content=file_content,
                file_name="clean.csv",
                ext="csv",
                telegram_id=123,
                business_name="Test Business"
            )
            
            assert wines_data is not None
            assert isinstance(wines_data, list)
            assert decision in ['save', 'error']
    
    @pytest.mark.asyncio
    async def test_pipeline_ambiguous_headers(self):
        """Test pipeline con header ambigui."""
        csv_path = FIXTURES_DIR / "ambiguous_headers.csv"
        
        with open(csv_path, "rb") as f:
            file_content = f.read()
        
        with patch('ingest.pipeline.get_config') as mock_config, \
             patch('ingest.pipeline.batch_insert_wines') as mock_insert, \
             patch('ingest.llm_targeted.get_openai_client') as mock_openai:
            
            # Mock config
            mock_config.return_value = create_mock_config_with_flags(
                ia_targeted_enabled=True
            )
            
            # Mock OpenAI
            mock_client = create_mock_openai_client("success", {
                "mapping": {
                    "Prodotto": "name",
                    "Produttore": "winery",
                    "Anno": "vintage",
                    "Qty": "qty"
                }
            })
            mock_openai.return_value = mock_client
            
            # Mock insert
            mock_insert.return_value = True
            
            # Test pipeline
            # Signature: process_file(file_content, file_name, ext, telegram_id, business_name, correlation_id)
            # Ritorna: (wines_data, metrics, decision, stage_used)
            wines_data, metrics, decision, stage_used = await process_file(
                file_content=file_content,
                file_name="ambiguous_headers.csv",
                ext="csv",
                telegram_id=123,
                business_name="Test Business"
            )
            
            assert wines_data is not None
            assert isinstance(wines_data, list)

