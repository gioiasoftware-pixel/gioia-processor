"""
Ingest pipeline per processamento file inventario vini.

Questo modulo contiene la pipeline deterministica per l'elaborazione di file:
- Stage 0: Gate (routing per tipo file)
- Stage 1: Parse classico (CSV/Excel senza IA)
- Stage 2: IA mirata (micro-aggiustamenti economici)
- Stage 3: LLM mode (estrazione tabellare da testo)
- Stage 4: OCR (PDF/immagini)
"""

