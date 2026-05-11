"""Shared domain enums used across multiple service modules.

Extracted from llm_router.py (W4 DIP fix) so that lower-level modules
(sensitivity_scorer, pii_detector) can import SensitivityLevel without
creating an upward dependency on llm_router.
"""
from __future__ import annotations

from enum import Enum


class SensitivityLevel(str, Enum):
    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
