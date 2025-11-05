"""
Test endpoint API.
"""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, AsyncMock, MagicMock
import json
import os

from api.main import app


@pytest.fixture
def client():
    """Fixture per TestClient."""
    return TestClient(app)


@pytest.fixture
def sample_csv_file():
    """Fixture per file CSV di test."""
    fixture_path = os.path.join(os.path.dirname(__file__), "data", "clean.csv")
    with open(fixture_path, "rb") as f:
        return f.read()


class TestHealthEndpoint:
    """Test endpoint /health."""
    
    def test_health_check(self, client):
        """Test health check."""
        response = client.get("/health")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy" or data["status"] == "unhealthy"
        assert "service" in data
        assert data["service"] == "gioia-processor"


class TestProcessInventoryEndpoint:
    """Test endpoint POST /process-inventory."""
    
    @pytest.mark.asyncio
    async def test_process_inventory_csv(self, client, sample_csv_file):
        """Test process-inventory con CSV."""
        with patch('api.routers.ingest.get_db') as mock_db, \
             patch('api.routers.ingest.create_job') as mock_create, \
             patch('api.routers.ingest.process_inventory_background') as mock_background:
            
            # Mock database
            mock_session = AsyncMock()
            mock_db.return_value.__aiter__.return_value = [mock_session]
            
            # Mock job creation
            mock_create.return_value = "test-job-id-123"
            
            # Mock background task
            mock_background.return_value = None
            
            response = client.post(
                "/process-inventory",
                data={
                    "telegram_id": 123,
                    "business_name": "Test Business",
                    "file_type": "csv",
                    "client_msg_id": "test-123",
                    "correlation_id": "corr-123",
                    "mode": "add",
                    "dry_run": False
                },
                files={"file": ("test.csv", sample_csv_file, "text/csv")}
            )
            
            assert response.status_code in [200, 201]
            data = response.json()
            assert "status" in data
            assert "job_id" in data
    
    def test_process_inventory_invalid_telegram_id(self, client, sample_csv_file):
        """Test con telegram_id invalido."""
        response = client.post(
            "/process-inventory",
            data={
                "telegram_id": -1,
                "business_name": "Test",
                "file_type": "csv"
            },
            files={"file": ("test.csv", sample_csv_file, "text/csv")}
        )
        
        assert response.status_code == 400
    
    def test_process_inventory_empty_file(self, client):
        """Test con file vuoto."""
        response = client.post(
            "/process-inventory",
            data={
                "telegram_id": 123,
                "business_name": "Test",
                "file_type": "csv"
            },
            files={"file": ("empty.csv", b"", "text/csv")}
        )
        
        assert response.status_code == 400
    
    def test_process_inventory_unsupported_type(self, client, sample_csv_file):
        """Test con tipo file non supportato."""
        response = client.post(
            "/process-inventory",
            data={
                "telegram_id": 123,
                "business_name": "Test",
                "file_type": "docx"
            },
            files={"file": ("test.docx", sample_csv_file, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")}
        )
        
        assert response.status_code == 400


class TestStatusEndpoint:
    """Test endpoint GET /status/{job_id}."""
    
    @pytest.mark.asyncio
    async def test_get_job_status_not_found(self, client):
        """Test status job non trovato."""
        with patch('api.main.get_db') as mock_db:
            mock_session = AsyncMock()
            mock_session.execute.return_value.scalar_one_or_none.return_value = None
            mock_db.return_value.__aiter__.return_value = [mock_session]
            
            response = client.get("/status/non-existent-job-id")
            
            assert response.status_code == 404
    
    @pytest.mark.asyncio
    async def test_get_job_status_completed(self, client):
        """Test status job completato."""
        from datetime import datetime
        from core.database import ProcessingJob
        
        with patch('api.main.get_db') as mock_db:
            mock_session = AsyncMock()
            mock_job = MagicMock(spec=ProcessingJob)
            mock_job.job_id = "test-job-123"
            mock_job.status = "completed"
            mock_job.telegram_id = 123
            mock_job.business_name = "Test"
            mock_job.file_type = "csv"
            mock_job.file_name = "test.csv"
            mock_job.total_wines = 10
            mock_job.processed_wines = 10
            mock_job.saved_wines = 10
            mock_job.error_count = 0
            mock_job.created_at = datetime.utcnow()
            mock_job.started_at = datetime.utcnow()
            mock_job.completed_at = datetime.utcnow()
            mock_job.result_data = json.dumps({"status": "success", "wines_saved": 10})
            
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = mock_job
            mock_session.execute.return_value = mock_result
            mock_db.return_value.__aiter__.return_value = [mock_session]
            
            response = client.get("/status/test-job-123")
            
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "completed"
            assert data["job_id"] == "test-job-123"
            assert "result" in data


class TestProcessMovementEndpoint:
    """Test endpoint POST /process-movement."""
    
    def test_process_movement_invalid_type(self, client):
        """Test con movement_type invalido."""
        response = client.post(
            "/process-movement",
            data={
                "telegram_id": 123,
                "business_name": "Test",
                "wine_name": "Chianti",
                "movement_type": "invalid",
                "quantity": 5
            }
        )
        
        assert response.status_code == 400
    
    def test_process_movement_negative_quantity(self, client):
        """Test con quantità negativa."""
        response = client.post(
            "/process-movement",
            data={
                "telegram_id": 123,
                "business_name": "Test",
                "wine_name": "Chianti",
                "movement_type": "consumo",
                "quantity": -5
            }
        )
        
        assert response.status_code == 400


class TestSnapshotEndpoint:
    """Test endpoint GET /api/inventory/snapshot."""
    
    def test_snapshot_invalid_token(self, client):
        """Test con token JWT invalido."""
        with patch('api.routers.snapshot.validate_viewer_token') as mock_validate:
            mock_validate.return_value = None
            
            response = client.get("/api/inventory/snapshot?token=invalid-token")
            
            assert response.status_code == 401
    
    @pytest.mark.asyncio
    async def test_snapshot_valid_token(self, client):
        """Test con token JWT valido."""
        with patch('api.routers.snapshot.validate_viewer_token') as mock_validate, \
             patch('api.routers.snapshot.get_db') as mock_db:
            
            mock_validate.return_value = {"telegram_id": 123, "business_name": "Test"}
            
            mock_session = AsyncMock()
            mock_user = MagicMock()
            mock_user.id = 1
            mock_session.execute.return_value.scalar_one_or_none.return_value = mock_user
            mock_session.execute.return_value.fetchall.return_value = []
            mock_db.return_value.__aiter__.return_value = [mock_session]
            
            response = client.get("/api/inventory/snapshot?token=valid-token")
            
            assert response.status_code == 200
            data = response.json()
            assert "rows" in data
            assert "facets" in data
            assert "meta" in data

