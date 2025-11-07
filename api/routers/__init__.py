"""
Routers per API gioia-processor.

Moduli:
- ingest: Router per elaborazione inventario (POST /process-inventory)
- snapshot: Router per snapshot inventario e viewer (GET /api/inventory/*, GET /api/viewer/*)
- movements: Router per movimenti (POST /process-movement)
"""
from . import ingest, snapshot, movements, diagnostics

__all__ = ["ingest", "snapshot", "movements", "diagnostics"]
