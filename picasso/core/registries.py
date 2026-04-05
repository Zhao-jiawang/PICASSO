from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict


@dataclass(frozen=True)
class RegistryBundle:
    interfaces: Dict[str, Any]
    packages: Dict[str, Any]
    memories: Dict[str, Any]
    process_nodes: Dict[str, Any]
    baselines: Dict[str, Any]
    legality: Dict[str, Any]


@lru_cache(maxsize=None)
def _load_json(path_str: str) -> Dict[str, Any]:
    path = Path(path_str)
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


@lru_cache(maxsize=None)
def load_registry_bundle(repo_root: str) -> RegistryBundle:
    root = Path(repo_root)
    return RegistryBundle(
        interfaces=_load_json(str(root / "configs" / "interfaces.json")),
        packages=_load_json(str(root / "configs" / "packages.json")),
        memories=_load_json(str(root / "configs" / "memory.json")),
        process_nodes=_load_json(str(root / "configs" / "process_nodes.json")),
        baselines=_load_json(str(root / "configs" / "baselines.json")),
        legality=_load_json(str(root / "configs" / "bootstrap_legality.json")),
    )


def motif_model(bundle: RegistryBundle, motif_name: str | None) -> Dict[str, float]:
    motif_key = motif_name or "dense_decoder_block"
    return bundle.legality["motif_models"].get(motif_key, bundle.legality["motif_models"]["dense_decoder_block"])


def interface_metrics(bundle: RegistryBundle, interface_class: str, package_class: str, tech: str) -> Dict[str, float]:
    interface_cfg = bundle.interfaces[interface_class]
    if "package_overrides" in interface_cfg and package_class in interface_cfg["package_overrides"]:
        override = interface_cfg["package_overrides"][package_class]
        return {
            "density_area_per_gbps": float(override.get("nop_density_area_per_gbps", 1200.0)),
            "hop_cost": float(override.get("nop_hop_cost", 6.0)),
        }
    if "tech_overrides" in interface_cfg and tech in interface_cfg["tech_overrides"]:
        override = interface_cfg["tech_overrides"][tech]
        return {
            "density_area_per_gbps": float(override.get("nop_density_area_per_gbps", 1200.0)),
            "hop_cost": float(override.get("nop_hop_cost", override.get("serdes_power_mw_per_lane", 70.0) / 10.0)),
        }
    return {
        "density_area_per_gbps": 1200.0,
        "hop_cost": 6.0,
    }
