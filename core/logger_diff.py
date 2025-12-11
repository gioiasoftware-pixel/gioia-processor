from __future__ import annotations

import logging
from copy import deepcopy
from typing import Dict

from ingest.types import FieldVal

from .diagnostics_state import increment

logger = logging.getLogger(__name__)


def _as_dict(field: FieldVal) -> Dict[str, object]:
    return {
        "value": field.value,
        "confidence": field.confidence,
        "source": field.source,
        "lineage": deepcopy(field.lineage),
    }


def log_field_override(field: str, old: FieldVal, new: FieldVal) -> None:
    if old.value == new.value and new.confidence == old.confidence:
        return

    increment(f"override.{field}")
    if old.value != new.value:
        increment(f"override.{field}.value_changed")
    if new.confidence > old.confidence:
        increment(f"override.{field}.confidence_increase")

    logger.info(
        "[DIFF] Field override",
        extra={
            "field": field,
            "old": _as_dict(old),
            "new": _as_dict(new),
        },
    )









