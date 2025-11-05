"""
Test unitari per gate (routing).
"""
import pytest

from ingest.gate import route_file


class TestGateRouting:
    """Test per routing file."""
    
    def test_route_csv(self):
        """Test routing CSV → Stage 1."""
        content = b"test content"
        stage, ext = route_file(content, "test.csv")
        
        assert stage == "csv_excel"
        assert ext == "csv"
    
    def test_route_excel(self):
        """Test routing Excel → Stage 1."""
        content = b"test content"
        stage, ext = route_file(content, "test.xlsx")
        
        assert stage == "csv_excel"
        assert ext == "xlsx"
    
    def test_route_pdf(self):
        """Test routing PDF → Stage 4."""
        content = b"test content"
        stage, ext = route_file(content, "test.pdf")
        
        assert stage == "ocr"
        assert ext == "pdf"
    
    def test_route_image(self):
        """Test routing immagine → Stage 4."""
        content = b"test content"
        stage, ext = route_file(content, "test.jpg")
        
        assert stage == "ocr"
        assert ext == "jpg"
    
    def test_route_unsupported(self):
        """Test formato non supportato."""
        content = b"test content"
        
        with pytest.raises(ValueError, match="Formato file non supportato"):
            route_file(content, "test.docx")
    
    def test_route_extract_from_filename(self):
        """Test estrazione estensione da nome file."""
        content = b"test content"
        stage, ext = route_file(content, "test.csv", ext=None)
        
        assert stage == "csv_excel"
        assert ext == "csv"
    
    def test_route_no_extension(self):
        """Test file senza estensione."""
        content = b"test content"
        
        with pytest.raises(ValueError, match="Impossibile determinare estensione"):
            route_file(content, "test", ext=None)

