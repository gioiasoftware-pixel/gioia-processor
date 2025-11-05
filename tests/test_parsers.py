"""
Test unitari per parser CSV e Excel.
"""
import pytest
import pandas as pd
from io import BytesIO

from ingest.csv_parser import detect_encoding, detect_delimiter, parse_csv
from ingest.excel_parser import parse_excel


class TestCSVParser:
    """Test per CSV parser."""
    
    def test_detect_encoding_utf8(self):
        """Test rilevamento encoding UTF-8."""
        content = "Nome,Cantina,Annata\nChianti,Barone,2020".encode('utf-8')
        encoding = detect_encoding(content)
        assert encoding == 'utf-8'
    
    def test_detect_encoding_utf8_sig(self):
        """Test rilevamento encoding UTF-8 BOM."""
        content = "\ufeffNome,Cantina,Annata\nChianti,Barone,2020".encode('utf-8-sig')
        encoding = detect_encoding(content)
        assert encoding in ['utf-8-sig', 'utf-8']
    
    def test_detect_delimiter_comma(self):
        """Test rilevamento delimitatore virgola."""
        content = "Nome,Cantina,Annata\nChianti,Barone,2020".encode('utf-8')
        delimiter = detect_delimiter(content, 'utf-8')
        assert delimiter == ','
    
    def test_detect_delimiter_semicolon(self):
        """Test rilevamento delimitatore punto e virgola."""
        content = "Nome;Cantina;Annata\nChianti;Barone;2020".encode('utf-8')
        delimiter = detect_delimiter(content, 'utf-8')
        assert delimiter == ';'
    
    def test_detect_delimiter_tab(self):
        """Test rilevamento delimitatore tab."""
        content = "Nome\tCantina\tAnnata\nChianti\tBarone\t2020".encode('utf-8')
        delimiter = detect_delimiter(content, 'utf-8')
        assert delimiter == '\t'
    
    def test_parse_csv_clean(self):
        """Test parsing CSV pulito."""
        content = "Nome,Cantina,Annata,Quantità\nChianti,Barone,2020,12".encode('utf-8')
        df, info = parse_csv(content, 'test.csv')
        
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 1
        assert 'Nome' in df.columns
        assert df.iloc[0]['Nome'] == 'Chianti'
        assert info['encoding'] in ['utf-8', 'utf-8-sig']
        assert info['separator'] == ','
    
    def test_parse_csv_with_bad_lines(self):
        """Test parsing CSV con righe malformate (skip)."""
        content = "Nome,Cantina,Annata\nChianti,Barone,2020\nBad,Line,With,Too,Many,Columns\nGood,Line,2021".encode('utf-8')
        df, info = parse_csv(content, 'test.csv')
        
        assert isinstance(df, pd.DataFrame)
        assert len(df) >= 2  # Almeno 2 righe valide


class TestExcelParser:
    """Test per Excel parser."""
    
    def test_parse_excel_simple(self):
        """Test parsing Excel semplice."""
        # Crea Excel in memoria
        df_test = pd.DataFrame({
            'Nome': ['Chianti', 'Barolo'],
            'Cantina': ['Barone', 'Vietti'],
            'Annata': [2020, 2018],
            'Quantità': [12, 6]
        })
        
        buffer = BytesIO()
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            df_test.to_excel(writer, sheet_name='Sheet1', index=False)
        buffer.seek(0)
        content = buffer.getvalue()
        
        df, info = parse_excel(content, 'test.xlsx')
        
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 2
        assert 'Nome' in df.columns
        assert info['sheet_name'] == 'Sheet1'
        assert info['rows'] == 2
    
    def test_parse_excel_multiple_sheets(self):
        """Test parsing Excel con più sheet (seleziona quello con più righe)."""
        buffer = BytesIO()
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            pd.DataFrame({'A': [1, 2]}).to_excel(writer, sheet_name='Sheet1', index=False)
            pd.DataFrame({'B': [1, 2, 3, 4]}).to_excel(writer, sheet_name='Sheet2', index=False)
        buffer.seek(0)
        content = buffer.getvalue()
        
        df, info = parse_excel(content, 'test.xlsx')
        
        assert isinstance(df, pd.DataFrame)
        assert info['sheet_name'] == 'Sheet2'  # Dovrebbe selezionare Sheet2 con più righe
        assert info['rows'] == 4

