from __future__ import annotations

from collections import Counter
from threading import Lock
from typing import Dict

_COUNTER = Counter()
_LOCK = Lock()


def increment(key: str, amount: int = 1) -> None:
    with _LOCK:
        _COUNTER[key] += amount


def get_snapshot() -> Dict[str, int]:
    with _LOCK:
        return dict(_COUNTER)


def reset() -> None:  # pragma: no cover - usato in test manuali
    with _LOCK:
        _COUNTER.clear()










