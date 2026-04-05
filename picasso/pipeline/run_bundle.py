from __future__ import annotations

import csv
import json
import subprocess
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List

from picasso.core import run_python_search

from .design_ids import design_id_for


RESULT_HEADERS = [
    "tech",
    "mm",
    "nn",
    "xx",
    "yy",
    "ss",
    "bb",
    "rr",
    "ff",
    "xcut",
    "ycut",
    "package_type",
    "IO_type",
    "nop_bw",
    "ddr_type",
    "ddr_bw",
    "noc",
    "mac",
    "ul3",
    "tops",
    "cost_overall",
    "energy",
    "cycle",
    "edp",
    "cost",
    "idx",
    "ubuf_energy",
    "buf_energy",
    "bus_energy",
    "mac_energy",
    "NoC_energy",
    "NoP_energy",
    "DRAM_energy",
    "compute_die_area",
    "IO_die_area",
    "total_die_area",
    "cost_chip",
    "cost_package",
    "cost_system_package",
    "cost_soc",
]


def load_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def dump_json(path: Path, payload: Dict[str, Any]) -> None:
    with path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, sort_keys=True)
        fh.write("\n")


def build_result_row(
    design_id: str,
    config_name: str,
    tier: str,
    point: Dict[str, Any],
    raw_tokens: List[str],
    paths: Dict[str, str],
) -> Dict[str, Any]:
    if len(raw_tokens) != len(RESULT_HEADERS):
        raise ValueError(f"Unexpected result token count for {design_id}: expected {len(RESULT_HEADERS)}, got {len(raw_tokens)}")
    row = {
        "design_id": design_id,
        "point_name": point["design_name"],
        "tier": tier,
        "config_name": config_name,
        "engine": "python_native",
        "baseline_mode": point["baseline_mode"],
        "proposal_budget": point["proposal_budget"] if point["proposal_budget"] is not None else "",
        "time_cap_minutes": point["time_cap_minutes"] if point["time_cap_minutes"] is not None else "",
        "workload_name": point["workload_name"],
        "workload_motif": point.get("workload_motif"),
        "microarch_name": point["microarch_name"],
        "objective_name": point["objective_name"],
        "seed": point["seed"],
        "stdout_log": paths["stdout_log"],
        "stderr_log": paths["stderr_log"],
        "result_log": paths["result_log"],
        "point_snapshot": paths["point_snapshot"],
        "search_trace": paths.get("search_trace", ""),
    }
    row.update(dict(zip(RESULT_HEADERS, raw_tokens)))
    return row


def write_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    if not rows:
        raise ValueError("No rows to write")
    headers = list(rows[0].keys())
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)


def write_best_arch(path: Path, rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    best_row = min(rows, key=lambda row: float(row["cost"]))
    ordered = [
        best_row["tech"],
        best_row["mm"],
        best_row["xx"],
        best_row["yy"],
        best_row["ss"],
        best_row["ff"],
        best_row["xcut"],
        best_row["ycut"],
        best_row["package_type"],
        best_row["IO_type"],
        best_row["nop_bw"],
        best_row["ddr_type"],
        best_row["ddr_bw"],
        best_row["noc"],
        best_row["mac"],
        best_row["ul3"],
        best_row["tops"],
    ]
    with path.open("w", encoding="utf-8") as fh:
        fh.write(" ".join(str(item) for item in ordered))
        fh.write("\n")
    return {
        "design_id": best_row["design_id"],
        "point_name": best_row["point_name"],
        "cost": float(best_row["cost"]),
        "cost_overall": float(best_row["cost_overall"]),
    }


def summarize_best_by_baseline(rows: List[Dict[str, Any]], maybe_int: Any, maybe_float: Any) -> Dict[str, Any]:
    summary: Dict[str, Any] = {}
    for baseline_mode in sorted({row["baseline_mode"] for row in rows}):
        baseline_rows = [row for row in rows if row["baseline_mode"] == baseline_mode]
        best_row = min(baseline_rows, key=lambda row: float(row["cost"]))
        summary[baseline_mode] = {
            "design_id": best_row["design_id"],
            "point_name": best_row["point_name"],
            "cost": float(best_row["cost"]),
            "cost_overall": float(best_row["cost_overall"]),
            "proposal_budget": maybe_int(best_row["proposal_budget"]),
            "time_cap_minutes": maybe_float(best_row["time_cap_minutes"]),
        }
    return summary


def write_trace_jsonl(path: Path, trace_entries: List[Any]) -> None:
    with path.open("w", encoding="utf-8") as fh:
        for entry in trace_entries:
            fh.write(json.dumps(asdict(entry), sort_keys=True))
            fh.write("\n")


def git_commit(repo_root: Path) -> str:
    return subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo_root, check=True, capture_output=True, text=True).stdout.strip()


def build_config_snapshot(
    run_name: str,
    config_path: Path,
    repo_root: Path,
    config: Dict[str, Any],
    timestamp: str,
    normalized_points: List[Dict[str, Any]],
    command: List[str],
) -> Dict[str, Any]:
    return {
        "run_name": run_name,
        "config_path": str(config_path),
        "repo_root": str(repo_root),
        "engine": str(config.get("engine", "python_native")),
        "timestamp": timestamp,
        "git_commit": git_commit(repo_root),
        "command": command,
        "baseline_modes": sorted({point["baseline_mode"] for point in normalized_points}),
        "config": config,
    }


def build_run_manifest(
    run_name: str,
    tier: str,
    config_path: Path,
    repo_root: Path,
    raw_dir: Path,
    aggregated_csv: Path,
    rows: List[Dict[str, Any]],
    best_summary: Dict[str, Any],
    best_by_baseline: Dict[str, Any],
    maybe_int: Any,
    maybe_float: Any,
) -> Dict[str, Any]:
    return {
        "run_name": run_name,
        "tier": tier,
        "config_path": str(config_path.relative_to(repo_root)),
        "engine": "python_native",
        "raw_dir": str(raw_dir.relative_to(repo_root)),
        "aggregated_csv": str(aggregated_csv.relative_to(repo_root)),
        "best_arch": best_summary,
        "best_arch_by_baseline": best_by_baseline,
        "baseline_modes": sorted({row["baseline_mode"] for row in rows}),
        "point_count": len(rows),
        "design_ids": [row["design_id"] for row in rows],
        "proposal_budgets": sorted({budget for budget in (maybe_int(row["proposal_budget"]) for row in rows) if budget is not None}),
        "time_cap_minutes": sorted({cap for cap in (maybe_float(row["time_cap_minutes"]) for row in rows) if cap is not None}),
    }


def run_point(
    repo_root: Path,
    config_name: str,
    tier: str,
    raw_dir: Path,
    point: Dict[str, Any],
    point_index: int,
) -> Dict[str, Any]:
    design_id = design_id_for(config_name, point_index)
    point_dir = raw_dir / design_id
    point_dir.mkdir(parents=True, exist_ok=True)

    result_log = point_dir / "result.log"
    stdout_log = point_dir / "stdout.log"
    stderr_log = point_dir / "stderr.log"
    point_snapshot = point_dir / "point_snapshot.json"
    search_trace = point_dir / "search_trace.jsonl"

    if point_snapshot.exists() and result_log.exists() and stdout_log.exists() and stderr_log.exists() and search_trace.exists():
        point_payload = load_json(point_snapshot)
        if int(point_payload.get("returncode", 1)) == 0:
            result_lines = [line.strip() for line in result_log.read_text(encoding="utf-8").splitlines() if line.strip()]
            if result_lines:
                raw_tokens = result_lines[-1].split()
                print(f"[PICASSO] Reusing completed point {design_id}")
                return build_result_row(
                    design_id=design_id,
                    config_name=config_name,
                    tier=tier,
                    point=point,
                    raw_tokens=raw_tokens,
                    paths={
                        "stdout_log": str(stdout_log.relative_to(repo_root)),
                        "stderr_log": str(stderr_log.relative_to(repo_root)),
                        "result_log": str(result_log.relative_to(repo_root)),
                        "point_snapshot": str(point_snapshot.relative_to(repo_root)),
                        "search_trace": str(search_trace.relative_to(repo_root)),
                    },
                )

    execution = run_python_search(repo_root=repo_root, point_payload=point, design_id=design_id)
    stdout_log.write_text(execution.stdout, encoding="utf-8")
    stderr_log.write_text(execution.stderr, encoding="utf-8")
    result_log.write_text(" ".join(execution.raw_tokens) + "\n", encoding="utf-8")
    write_trace_jsonl(search_trace, execution.trace_entries)

    point_payload = {
        "design_id": design_id,
        "tier": tier,
        "engine": "python_native",
        "command": ["python_native_engine"],
        "normalized_point": point,
        "execution_controls": {
            "proposal_budget": point["proposal_budget"],
            "time_cap_minutes": point["time_cap_minutes"],
        },
        "state_tuple": {
            "m": {
                "workload": point["workload_name"],
                "workload_motif": point.get("workload_motif"),
                "workload_ref": point.get("workload_ref"),
                "workload_trace_ref": point.get("workload_trace_ref"),
                "workload_trace_summary": point.get("workload_trace_summary"),
                "batch_size": point["bb"],
                "search_rounds": point["rr"],
            },
            "a": {
                "microarch": point["microarch_name"],
                "core_array": {"x": point["xx"], "y": point["yy"]},
                "macs_per_core": point["mac"],
                "ul3_kb": point["ul3"],
            },
            "k": {
                "chiplet_partition": {"x": point["xcut"], "y": point["ycut"]},
                "chiplet_count": point["xcut"] * point["ycut"],
            },
            "i": {
                "interface_class": point["IO_type"],
                "nop_bandwidth": point["nop_bw"],
            },
            "p": {
                "package_class": point["package_type"],
            },
            "b": {
                "memory_class": point["ddr_type"],
                "memory_bandwidth_gbps": point["ddr_bw"] // 1024,
                "noc_bandwidth": point["noc"],
            },
        },
        "search_summary": execution.summary,
        "paths": {
            "search_trace": str(search_trace.relative_to(repo_root)),
            "stdout_log": str(stdout_log.relative_to(repo_root)),
            "stderr_log": str(stderr_log.relative_to(repo_root)),
            "result_log": str(result_log.relative_to(repo_root)),
        },
        "returncode": 0,
    }
    dump_json(point_snapshot, point_payload)

    return build_result_row(
        design_id=design_id,
        config_name=config_name,
        tier=tier,
        point=point,
        raw_tokens=execution.raw_tokens,
        paths={
            "stdout_log": str(stdout_log.relative_to(repo_root)),
            "stderr_log": str(stderr_log.relative_to(repo_root)),
            "result_log": str(result_log.relative_to(repo_root)),
            "point_snapshot": str(point_snapshot.relative_to(repo_root)),
            "search_trace": str(search_trace.relative_to(repo_root)),
        },
    )
