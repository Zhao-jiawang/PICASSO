#!/usr/bin/env python3

import argparse
import json
from pathlib import Path
from typing import Any, Dict


def load_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def dump_json(path: Path, payload: Dict[str, Any]) -> None:
    with path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, sort_keys=True)
        fh.write("\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Export bootstrap PICASSO model parameterization")
    parser.add_argument("--repo-root", default=None, help="Repo root, defaults to script parent")
    parser.add_argument("--output", required=True, help="Output json path")
    args = parser.parse_args()

    script_path = Path(__file__).resolve()
    repo_root = Path(args.repo_root).resolve() if args.repo_root else script_path.parent.parent.parent
    output_path = Path(args.output).resolve()

    interfaces = load_json(repo_root / "configs" / "interfaces.json")
    baselines = load_json(repo_root / "configs" / "baselines.json")
    packages = load_json(repo_root / "configs" / "packages.json")
    memories = load_json(repo_root / "configs" / "memory.json")
    process_nodes = load_json(repo_root / "configs" / "process_nodes.json")
    legality_cfg = load_json(repo_root / "configs" / "bootstrap_legality.json")

    payload = {
        "schema_version": "bootstrap_v0",
        "status": "bootstrap",
        "notes": [
            "This file centralizes the bootstrap model parameterization used by the PICASSO runner scaffold.",
            "It is sourced from the current centralized PICASSO configuration constants and does not yet represent the final SC2026 calibrated model.",
            "Traffic matrices and closure-derived refinements are still bootstrap-level, but legality heuristics are centralized in configs/bootstrap_legality.json."
        ],
        "process_nodes": process_nodes,
        "interfaces": interfaces,
        "baselines": baselines,
        "packages": packages,
        "memories": memories,
        "bootstrap_legality": legality_cfg,
        "Be(i,p)": {
            "definition": "Interface-package bandwidth envelope for the bootstrap scaffold.",
            "package_topology_penalty": "captured through package-specific overrides for UCIe and reserved for fuller modeling later",
            "raw_interface_envelope": interfaces,
            "serialization_utilization_loss": "captured through bootstrap interface_efficiency factors",
            "usable_bandwidth_factor": legality_cfg["interface_efficiency"]
        },
        "Gedge(p,k)": {
            "definition": "Available exposed edge capacity for package p and chiplet organization k.",
            "keep_out_reservation": "not yet modeled explicitly",
            "memory_edge_reservation": "captured indirectly through io_competition_score in legality_details",
            "organization_dependent_edge_availability": "per_die_exposed_edges is exported in canonical design records",
            "package_specific_exposed_perimeter": "capacity scales with package_route_scale and total_exposed_edge_slots"
        },
        "I(d)": {
            "bootstrap_candidates": [
                "XSR",
                "USR",
                "UCIe"
            ],
            "definition": "Feasible interface upgrades at fixed remaining state.",
            "status": "reserved_for_future_legality_model"
        },
        "P(d)": {
            "bootstrap_candidates": [
                "OS",
                "FO",
                "SI"
            ],
            "definition": "Feasible package upgrades at fixed remaining state.",
            "status": "reserved_for_future_legality_model"
        },
        "Rbudget(p)": {
            "definition": "Package route budget for package p.",
            "package_class_richness_scaling": legality_cfg["package_route_scale"],
            "route_capacity_template": legality_cfg["package_route_scale"],
            "topology_penalty": "captured by multiplying edge_capacity with route_factor and chiplet geometry"
        }
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    dump_json(output_path, payload)
    print(f"[PICASSO] Exported model parameterization to {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
