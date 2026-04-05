#!/usr/bin/env python3

import argparse
import csv
import json
import math
from pathlib import Path
import sys
from typing import Any, Dict, List

SCRIPT_PATH = Path(__file__).resolve()
REPO_ROOT = SCRIPT_PATH.parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from picasso.core import build_traffic_matrix, geometry_from_partition


def read_csv(path: Path) -> List[Dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def load_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def dump_json(path: Path, payload: Dict[str, Any]) -> None:
    with path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, sort_keys=True)
        fh.write("\n")


def maybe_float(row: Dict[str, str], key: str) -> float:
    return float(row[key]) if row.get(key) not in (None, "") else 0.0


def maybe_int(row: Dict[str, str], key: str) -> int:
    return int(float(row[key])) if row.get(key) not in (None, "") else 0


def motif_name(row: Dict[str, str]) -> str:
    return row.get("workload_motif") or row["workload_name"]


def round_or_zero(value: Any) -> float:
    return round(float(value or 0.0), 6)


def derive_projection_metadata(
    row: Dict[str, str],
    point_snapshot: Dict[str, Any],
    legality_cfg: Dict[str, Any],
    best_eval: Dict[str, Any],
    best_state: Dict[str, Any],
) -> Dict[str, Any]:
    geom = geometry_from_partition(
        maybe_int(row, "xx"),
        maybe_int(row, "yy"),
        maybe_int(row, "xcut"),
        maybe_int(row, "ycut"),
    )
    derived_terms = best_eval["derived_terms"]
    normalized_point = point_snapshot["normalized_point"]
    package_class = row["package_type"]
    interface_class = row["IO_type"]
    memory_class = row["ddr_type"]
    chiplet_count = geom["chiplet_count"]
    channel_bw = float(legality_cfg["memory_channel_bandwidth_gbps"][memory_class])
    channel_count_available = int(round(float(derived_terms.get("channel_count_available", 0.0))))
    channel_count_required = int(round(float(derived_terms.get("channel_count_required", 0.0))))
    total_interchip_bw = float(derived_terms.get("total_interchip_bw", 0.0))
    locality_hint = float(derived_terms.get("locality_score", 0.5))
    traffic_matrix = build_traffic_matrix(
        chiplet_count,
        total_interchip_bw,
        locality_hint,
        maybe_int(row, "xcut"),
        maybe_int(row, "ycut"),
    )

    peak_route_link = float(derived_terms.get("peak_route_link_gbps", 0.0))
    edge_demand = max((sum(edge_row) for edge_row in traffic_matrix), default=0.0)
    edge_margin = float(derived_terms.get("edge_margin", 0.0))
    route_margin = float(derived_terms.get("route_margin", 0.0))
    edge_capacity = max(edge_demand + edge_margin, 0.0)
    route_demand = peak_route_link
    route_budget = max(route_demand + route_margin, 0.0)

    raw_memory_bw = normalized_point["ddr_bw"] / 1024.0
    memory_balance = float(best_state.get("memory_balance", 1.0))
    available_memory_bw = raw_memory_bw * memory_balance
    memory_margin = float(derived_terms.get("memory_margin", 0.0))
    memory_required_bw = max(available_memory_bw - memory_margin, 0.0)

    closure_terms = {
        "M1": round_or_zero(edge_margin),
        "M2": round_or_zero(memory_margin),
        "Si": round_or_zero(legality_cfg["interface_efficiency"][interface_class]),
        "Sp": round_or_zero(legality_cfg["package_route_scale"][package_class]),
    }

    return {
        "geom": geom,
        "phy_count": int(round(float(derived_terms.get("phy_count", 0.0)))) if chiplet_count > 1 else 0,
        "traffic_matrix": traffic_matrix,
        "per_edge_bandwidth": {
            "edge_capacity": round_or_zero(edge_capacity),
            "edge_demand": round_or_zero(edge_demand),
            "edge_margin": round_or_zero(edge_margin),
            "route_budget": round_or_zero(route_budget),
            "route_demand": round_or_zero(route_demand),
            "route_margin": round_or_zero(route_margin),
            "per_die_exposed_edges": geom["per_die_exposed_edges"],
            "total_exposed_edge_slots": geom["total_exposed_edge_slots"],
        },
        "legality_details": {
            "channel_count_available": channel_count_available,
            "channel_count_required": channel_count_required,
            "io_competition_score": round_or_zero(derived_terms.get("io_competition_score", 0.0)),
            "memory_required_bw_gbps": round_or_zero(memory_required_bw),
            "peak_noc_link_gbps": round_or_zero(derived_terms.get("peak_noc_link_gbps", 0.0)),
            "peak_nop_link_gbps": round_or_zero(derived_terms.get("peak_nop_link_gbps", 0.0)),
            "peak_route_link_gbps": round_or_zero(peak_route_link),
            "peak_dram_channel_gbps": round_or_zero(derived_terms.get("peak_dram_channel_gbps", 0.0)),
            "edge_margin": round_or_zero(edge_margin),
            "route_margin": round_or_zero(route_margin),
            "memory_margin": round_or_zero(memory_margin),
            "noc_margin": round_or_zero(derived_terms.get("noc_margin", 0.0)),
            "dram_channel_margin": round_or_zero(derived_terms.get("dram_channel_margin", 0.0)),
            "buffer_margin": round_or_zero(derived_terms.get("buffer_margin", 0.0)),
            "total_interchip_bw": round_or_zero(total_interchip_bw),
            "reasons": list(best_eval["illegal_reasons"]),
        },
        "closure_terms": closure_terms,
        "memory_attachment": {
            "channel_count_available": channel_count_available,
            "channel_count_required": channel_count_required,
            "memory_channel_bandwidth_gbps": channel_bw,
        },
    }


def build_record(repo_root: Path, row: Dict[str, str], legality_cfg: Dict[str, Any]) -> Dict[str, Any]:
    point_snapshot_path = repo_root / row["point_snapshot"]
    point_snapshot = load_json(point_snapshot_path)
    point = point_snapshot["normalized_point"]
    search_summary = point_snapshot["search_summary"]
    best_eval = search_summary["best_eval"]
    best_state = search_summary["best_state"]
    projection = derive_projection_metadata(row, point_snapshot, legality_cfg, best_eval, best_state)

    record = {
        "schema_version": "python_native_v1",
        "design_id": row["design_id"],
        "baseline_mode": row["baseline_mode"],
        "proposal_budget": maybe_int(row, "proposal_budget"),
        "time_cap_minutes": maybe_float(row, "time_cap_minutes"),
        "workload": row["workload_name"],
        "workload_motif": row.get("workload_motif") or None,
        "trace_id": row["workload_name"],
        "workload_trace": {
            "trace_ref": point.get("workload_trace_ref"),
            "summary": point.get("workload_trace_summary", {}),
        },
        "tops_target": maybe_int(row, "tops") // 1024,
        "process_node": row["tech"],
        "seed": maybe_int(row, "seed"),
        "state_tuple": point_snapshot["state_tuple"],
        "best_state": best_state,
        "package_class": row["package_type"],
        "memory_attachment": {
            "memory_class": row["ddr_type"],
            "memory_bandwidth_gbps": maybe_int(row, "ddr_bw") // 1024,
            "noc_bandwidth": maybe_int(row, "noc"),
            **projection["memory_attachment"],
        },
        "die_area_breakdown": {
            "compute_die_area": maybe_float(row, "compute_die_area"),
            "io_die_area": maybe_float(row, "IO_die_area"),
            "total_die_area": maybe_float(row, "total_die_area"),
        },
        "phy_count": projection["phy_count"],
        "traffic_matrix": projection["traffic_matrix"],
        "per_edge_bandwidth": projection["per_edge_bandwidth"],
        "surrogate_metrics": {
            "latency_cycles": int(best_eval["cycle"]),
            "energy": float(best_eval["energy"]),
            "cost": maybe_float(row, "cost"),
            "cost_overall": float(best_eval["cost_overall"]),
            "edp": float(best_eval["edp"]),
        },
        "energy_breakdown": {
            "ubuf": maybe_float(row, "ubuf_energy"),
            "buf": maybe_float(row, "buf_energy"),
            "bus": maybe_float(row, "bus_energy"),
            "mac": maybe_float(row, "mac_energy"),
            "noc": maybe_float(row, "NoC_energy"),
            "nop": maybe_float(row, "NoP_energy"),
            "dram": maybe_float(row, "DRAM_energy"),
        },
        "cost_breakdown": {
            "cost_chip": maybe_float(row, "cost_chip"),
            "cost_package": maybe_float(row, "cost_package"),
            "cost_system_package": maybe_float(row, "cost_system_package"),
            "cost_soc": maybe_float(row, "cost_soc"),
        },
        "legality_flags": dict(best_eval["legality_flags"]),
        "legality_details": projection["legality_details"],
        "closure_terms": projection["closure_terms"],
        "derived_terms": dict(best_eval["derived_terms"]),
        "paths": {
            "stdout_log": row["stdout_log"],
            "stderr_log": row["stderr_log"],
            "result_log": row["result_log"],
            "point_snapshot": row["point_snapshot"],
        },
        "execution_controls": point_snapshot.get("execution_controls", {}),
        "notes": {
            "status": "exported_from_search_summary",
            "message": "This canonical design record is exported directly from the Python-native search summary and its derived evaluation terms.",
            "workload_ref": point.get("workload_ref"),
            "workload_status": point.get("workload_status"),
            "chiplet_geometry": projection["geom"],
        },
    }
    return record


def main() -> int:
    parser = argparse.ArgumentParser(description="Export canonical design records from Python-native search summaries")
    parser.add_argument("--aggregated-csv", required=True, help="Path to an aggregated result.csv")
    parser.add_argument("--output-dir", required=True, help="Output directory for exported design records")
    args = parser.parse_args()

    aggregated_csv = Path(args.aggregated_csv).resolve()
    output_dir = Path(args.output_dir).resolve()
    repo_root = aggregated_csv.parents[3]
    rows = read_csv(aggregated_csv)
    output_dir.mkdir(parents=True, exist_ok=True)
    legality_cfg = load_json(repo_root / "configs" / "bootstrap_legality.json")

    records = []
    for row in rows:
        record = build_record(repo_root, row, legality_cfg)
        records.append(record)
        dump_json(output_dir / f"{row['design_id']}.json", record)

    manifest = {
        "schema_version": "python_native_v1",
        "source_csv": str(aggregated_csv.relative_to(repo_root)),
        "record_count": len(records),
        "design_ids": [record["design_id"] for record in records],
        "record_dir": str(output_dir.relative_to(repo_root)),
    }
    dump_json(output_dir / "manifest.json", manifest)
    dump_json(output_dir.parent / "design_records.json", {"records": records})
    print(f"[PICASSO] Exported {len(records)} design records to {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
