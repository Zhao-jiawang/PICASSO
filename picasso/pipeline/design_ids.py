from __future__ import annotations


def design_id_for(config_name: str, point_index: int) -> str:
    return f"{config_name}_{point_index:03d}"
