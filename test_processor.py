#!/usr/bin/env python3
"""
Script di test per Gioia Processor
Testa tutti gli endpoint e funzionalità principali
"""

import requests
import json
import os
import sys
from pathlib import Path

# Configurazione
BASE_URL = os.getenv("PROCESSOR_URL", "http://localhost:8001")
TEST_TELEGRAM_ID = 123456
TEST_BUSINESS_NAME = "Test Restaurant"

def test_health_check():
    """Test health check endpoint"""
    print("🔍 Testing health check...")
    try:
        response = requests.get(f"{BASE_URL}/health", timeout=10)
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Health check OK: {data}")
            return True
        else:
            print(f"❌ Health check failed: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Health check error: {e}")
        return False

def test_status_endpoint():
    """Test status endpoint"""
    print("🔍 Testing status endpoint...")
    try:
        response = requests.get(f"{BASE_URL}/status/{TEST_TELEGRAM_ID}", timeout=10)
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Status endpoint OK: {data}")
            return True
        else:
            print(f"❌ Status endpoint failed: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Status endpoint error: {e}")
        return False

def create_test_csv():
    """Crea file CSV di test"""
    csv_content = """Nome,Annata,Produttore,Regione,Prezzo,Quantità,Tipo
Chianti Classico,2019,Antinori,Toscana,25.50,12,Rosso
Pinot Grigio,2020,Alois Lageder,Alto Adige,18.00,8,Bianco
Prosecco,2021,La Marca,Veneto,12.00,15,Spumante
Barolo,2018,Gaja,Piemonte,85.00,3,Rosso"""
    
    test_file = Path("test_inventory.csv")
    test_file.write_text(csv_content, encoding='utf-8')
    return test_file

def test_process_inventory():
    """Test process inventory endpoint"""
    print("🔍 Testing process inventory...")
    
    # Crea file CSV di test
    test_file = create_test_csv()
    
    try:
        with open(test_file, 'rb') as f:
            files = {'file': ('test_inventory.csv', f, 'text/csv')}
            data = {
                'telegram_id': TEST_TELEGRAM_ID,
                'business_name': TEST_BUSINESS_NAME,
                'file_type': 'csv'
            }
            
            response = requests.post(
                f"{BASE_URL}/process-inventory",
                files=files,
                data=data,
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                print(f"✅ Process inventory OK: {result}")
                return True
            else:
                print(f"❌ Process inventory failed: {response.status_code}")
                print(f"Response: {response.text}")
                return False
                
    except Exception as e:
        print(f"❌ Process inventory error: {e}")
        return False
    finally:
        # Pulisci file di test
        if test_file.exists():
            test_file.unlink()

def test_database_connection():
    """Test connessione database"""
    print("🔍 Testing database connection...")
    try:
        from database import engine
        import asyncio
        
        async def test_db():
            try:
                async with engine.begin() as conn:
                    await conn.execute("SELECT 1")
                return True
            except Exception as e:
                print(f"Database error: {e}")
                return False
        
        result = asyncio.run(test_db())
        if result:
            print("✅ Database connection OK")
        else:
            print("❌ Database connection failed")
        return result
        
    except Exception as e:
        print(f"❌ Database test error: {e}")
        return False

def main():
    """Esegue tutti i test"""
    print("🍷 Gioia Processor - Test Suite")
    print("=" * 50)
    
    tests = [
        ("Health Check", test_health_check),
        ("Status Endpoint", test_status_endpoint),
        ("Database Connection", test_database_connection),
        ("Process Inventory", test_process_inventory),
    ]
    
    results = []
    
    for test_name, test_func in tests:
        print(f"\n📋 {test_name}")
        print("-" * 30)
        result = test_func()
        results.append((test_name, result))
    
    # Riepilogo risultati
    print("\n" + "=" * 50)
    print("📊 TEST RESULTS SUMMARY")
    print("=" * 50)
    
    passed = 0
    total = len(results)
    
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} - {test_name}")
        if result:
            passed += 1
    
    print(f"\n🎯 Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests passed! Processor is ready.")
        return 0
    else:
        print("⚠️  Some tests failed. Check the logs above.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
