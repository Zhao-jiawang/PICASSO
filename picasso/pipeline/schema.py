from __future__ import annotations

from typing import Any, Dict, List


def require_keys(obj: Dict[str, Any], keys: List[str], context: str) -> None:
    missing = [key for key in keys if key not in obj]
    if missing:
        raise ValueError(f"{context} is missing required keys: {', '.join(missing)}")


def validate_config_shape(config: Dict[str, Any]) -> None:
    require_keys(config, ["experiment_name", "tier", "points"], "config")
    if not isinstance(config["points"], list) or not config["points"]:
        raise ValueError("config.points must be a non-empty list")
