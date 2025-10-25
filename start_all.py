#!/usr/bin/env python3
"""
Script per avviare sia il web server che il worker Redis Stream
"""
import subprocess
import sys
import os
import signal
import time
from threading import Thread

def start_web_server():
    """Avvia il web server FastAPI"""
    print("🚀 Avvio web server...")
    subprocess.run([sys.executable, "start_processor.py"])

def start_worker():
    """Avvia il worker Redis Stream"""
    print("🔄 Avvio worker Redis Stream...")
    subprocess.run([sys.executable, "consumer.py"])

def signal_handler(sig, frame):
    """Gestisce il segnale di terminazione"""
    print("\n🛑 Arresto servizi...")
    sys.exit(0)

def main():
    """Avvia entrambi i processi"""
    print("🎯 Avvio Gioia Processor (Web + Worker)")
    
    # Gestione segnali
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        # Avvia worker in background
        worker_thread = Thread(target=start_worker, daemon=True)
        worker_thread.start()
        
        # Aspetta un momento per il worker
        time.sleep(2)
        
        # Avvia web server (bloccante)
        start_web_server()
        
    except KeyboardInterrupt:
        print("\n🛑 Arresto servizi...")
        sys.exit(0)

if __name__ == "__main__":
    main()
