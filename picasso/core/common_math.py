from __future__ import annotations

import hashlib


def stable_int(value: str) -> int:
    return int(hashlib.sha1(value.encode("utf-8")).hexdigest()[:8], 16)


def clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def clamp_int(value: int, lower: int, upper: int) -> int:
    return max(lower, min(upper, value))

