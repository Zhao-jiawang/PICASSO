#!/usr/bin/env python3

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple


def read_csv(path: Path) -> List[Dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def write_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    if not rows:
        raise ValueError(f"No rows provided for {path}")
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def load_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def dump_json(path: Path, payload: Dict[str, Any]) -> None:
    with path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, sort_keys=True)
        fh.write("\n")


def require_columns(rows: List[Dict[str, str]], columns: Iterable[str], path: Path) -> None:
    if not rows:
        raise ValueError(f"{path} is empty")
    missing = [column for column in columns if column not in rows[0]]
    if missing:
        raise ValueError(f"{path} is missing required columns: {', '.join(missing)}")


def maybe_float(value: str) -> float:
    if value in ("", None):
        return 0.0
    return float(value)


def maybe_int(value: str) -> int:
    if value in ("", None):
        return 0
    return int(float(value))


def motif_of(row: Dict[str, str]) -> str:
    return row.get("workload_motif") or row["workload_name"]


def regime_from_chiplet_count(chiplet_count: int) -> str:
    if chiplet_count <= 1:
        return "mono"
    if chiplet_count <= 4:
        return "few"
    return "many"


def is_pareto_point(candidate: Dict[str, str], rows: List[Dict[str, str]]) -> bool:
    cost = maybe_float(candidate["cost"])
    energy = maybe_float(candidate["energy"])
    for other in rows:
        if other["design_id"] == candidate["design_id"]:
            continue
        other_cost = maybe_float(other["cost"])
        other_energy = maybe_float(other["energy"])
        dominates = (
            other_cost <= cost
            and other_energy <= energy
            and (other_cost < cost or other_energy < energy)
        )
        if dominates:
            return False
    return True


def pick_min(rows: List[Dict[str, str]], field: str) -> Dict[str, str]:
    return min(rows, key=lambda row: maybe_float(row[field]))


def prefer_joint_rows(rows: List[Dict[str, str]]) -> List[Dict[str, str]]:
    joint_rows = [row for row in rows if row["baseline_mode"] == "Joint"]
    return joint_rows or rows


def architecture_signature(row: Dict[str, str]) -> Tuple[str, ...]:
    return (
        row.get("point_name", ""),
        row.get("tech", ""),
        row.get("mm", ""),
        row.get("xx", ""),
        row.get("yy", ""),
        row.get("xcut", ""),
        row.get("ycut", ""),
        row.get("package_type", ""),
        row.get("IO_type", ""),
        row.get("ddr_type", ""),
        row.get("noc", ""),
        row.get("nop_bw", ""),
        row.get("mac", ""),
        row.get("ul3", ""),
        row.get("tops", ""),
    )


def write_winner_change_matrix(rows: List[Dict[str, str]], output_dir: Path) -> str:
    grouped: Dict[Tuple[str, str], List[Dict[str, str]]] = defaultdict(list)
    for row in rows:
        grouped[(row["baseline_mode"], motif_of(row))].append(row)
    joint_winners = {
        motif: pick_min(motif_rows, "edp")
        for motif, motif_rows in (
            (
                motif,
                [row for row in rows if row["baseline_mode"] == "Joint" and motif_of(row) == motif],
            )
            for motif in sorted({motif_of(row) for row in rows})
        )
        if motif_rows
    }

    output_rows = []
    for (baseline_mode, motif), motif_rows in sorted(grouped.items()):
        motif_winner = pick_min(motif_rows, "edp")
        reference_winner = joint_winners.get(motif, motif_winner)
        winner_changed = architecture_signature(motif_winner) != architecture_signature(reference_winner)
        output_rows.append(
            {
                "baseline_mode": baseline_mode,
                "workload_motif": motif,
                "winner_design_id": motif_winner["design_id"],
                "joint_winner_design_id": reference_winner["design_id"],
                "global_winner_design_id": reference_winner["design_id"],
                "winner_changed_vs_joint": str(winner_changed).lower(),
                "winner_changed_vs_global": str(winner_changed).lower(),
                "winner_package_class": motif_winner["package_type"],
                "winner_interface_class": motif_winner["IO_type"],
                "winner_memory_class": motif_winner["ddr_type"],
                "winner_edp": f"{maybe_float(motif_winner['edp']):.6f}",
                "status": "bootstrap_observed",
            }
        )

    path = output_dir / "winner_change_matrix.csv"
    write_csv(path, output_rows)
    return path.name


def write_reevaluated_loss(rows: List[Dict[str, str]], output_dir: Path) -> str:
    joint_reference = {
        motif: pick_min(motif_rows, "edp")
        for motif, motif_rows in (
            (
                motif,
                [row for row in rows if row["baseline_mode"] == "Joint" and motif_of(row) == motif],
            )
            for motif in sorted({motif_of(row) for row in rows})
        )
        if motif_rows
    }
    output_rows = []
    for row in rows:
        motif = motif_of(row)
        reference = joint_reference.get(motif, pick_min(rows, "edp"))
        ref_cost = maybe_float(reference["cost"])
        ref_energy = maybe_float(reference["energy"])
        ref_cycle = maybe_float(reference["cycle"])
        ref_edp = maybe_float(reference["edp"])
        output_rows.append(
            {
                "design_id": row["design_id"],
                "reference_design_id": reference["design_id"],
                "reference_baseline_mode": reference["baseline_mode"],
                "baseline_mode": row["baseline_mode"],
                "workload_motif": motif,
                "cost_loss_pct": f"{((maybe_float(row['cost']) - ref_cost) / ref_cost * 100.0) if ref_cost else 0.0:.6f}",
                "energy_loss_pct": f"{((maybe_float(row['energy']) - ref_energy) / ref_energy * 100.0) if ref_energy else 0.0:.6f}",
                "latency_loss_pct": f"{((maybe_float(row['cycle']) - ref_cycle) / ref_cycle * 100.0) if ref_cycle else 0.0:.6f}",
                "edp_loss_pct": f"{((maybe_float(row['edp']) - ref_edp) / ref_edp * 100.0) if ref_edp else 0.0:.6f}",
                "status": "bootstrap_observed",
            }
        )

    path = output_dir / "reevaluated_loss.csv"
    write_csv(path, output_rows)
    return path.name


def write_interface_vs_package(rows: List[Dict[str, str]], output_dir: Path) -> str:
    grouped: Dict[Tuple[str, str, str], List[Dict[str, str]]] = defaultdict(list)
    for row in rows:
        grouped[(motif_of(row), row["IO_type"], row["package_type"])].append(row)

    output_rows = []
    for (motif, interface_class, package_class), group_rows in sorted(grouped.items()):
        output_rows.append(
            {
                "workload_motif": motif,
                "interface_class": interface_class,
                "package_class": package_class,
                "design_count": len(group_rows),
                "avg_cost": f"{sum(maybe_float(row['cost']) for row in group_rows) / len(group_rows):.6f}",
                "avg_energy": f"{sum(maybe_float(row['energy']) for row in group_rows) / len(group_rows):.6f}",
                "avg_cycle": f"{sum(maybe_float(row['cycle']) for row in group_rows) / len(group_rows):.6f}",
                "status": "bootstrap_observed",
            }
        )

    path = output_dir / "interface_vs_package.csv"
    write_csv(path, output_rows)
    return path.name


def write_memory_off_ablation(rows: List[Dict[str, str]], output_dir: Path) -> str:
    joint_rows = [row for row in rows if row["baseline_mode"] == "Joint"]
    memory_off_rows = [row for row in rows if row["baseline_mode"] == "Memory-off"]
    grouped_joint: Dict[str, List[Dict[str, str]]] = defaultdict(list)
    grouped_memory_off: Dict[str, List[Dict[str, str]]] = defaultdict(list)
    for row in joint_rows:
        grouped_joint[motif_of(row)].append(row)
    for row in memory_off_rows:
        grouped_memory_off[motif_of(row)].append(row)

    output_rows = []
    motifs = sorted(set(grouped_joint) | set(grouped_memory_off))
    for motif in motifs:
        joint_winner = pick_min(grouped_joint[motif], "edp") if grouped_joint.get(motif) else None
        memory_off_winner = pick_min(grouped_memory_off[motif], "edp") if grouped_memory_off.get(motif) else None
        winner = memory_off_winner or joint_winner
        if winner is None:
            continue
        if joint_winner and memory_off_winner:
            ref_edp = maybe_float(joint_winner["edp"])
            ref_cost = maybe_float(joint_winner["cost"])
            ref_energy = maybe_float(joint_winner["energy"])
            ref_cycle = maybe_float(joint_winner["cycle"])
            status = "bootstrap_observed"
        else:
            ref_edp = ref_cost = ref_energy = ref_cycle = 0.0
            status = "bootstrap_placeholder"
        output_rows.append(
            {
                "workload_motif": motif,
                "observed_design_id": winner["design_id"],
                "joint_design_id": joint_winner["design_id"] if joint_winner else "",
                "memory_class": winner["ddr_type"],
                "memory_bandwidth_gbps": maybe_int(winner["ddr_bw"]) // 1024,
                "memory_off_supported": str(memory_off_winner is not None).lower(),
                "winner_changed_vs_joint": str(
                    joint_winner is not None
                    and memory_off_winner is not None
                    and architecture_signature(memory_off_winner) != architecture_signature(joint_winner)
                ).lower(),
                "cost_delta_pct": f"{((maybe_float(winner['cost']) - ref_cost) / ref_cost * 100.0) if ref_cost else 0.0:.6f}",
                "energy_delta_pct": f"{((maybe_float(winner['energy']) - ref_energy) / ref_energy * 100.0) if ref_energy else 0.0:.6f}",
                "latency_delta_pct": f"{((maybe_float(winner['cycle']) - ref_cycle) / ref_cycle * 100.0) if ref_cycle else 0.0:.6f}",
                "edp_delta_pct": f"{((maybe_float(winner['edp']) - ref_edp) / ref_edp * 100.0) if ref_edp else 0.0:.6f}",
                "status": status,
                "notes": "Memory-off rows compare the Memory-off winner against the Joint winner when both baselines are present.",
            }
        )

    path = output_dir / "memory_off_ablation.csv"
    write_csv(path, output_rows)
    return path.name


def write_phase_boundary(rows: List[Dict[str, str]], output_dir: Path) -> str:
    output_rows = []
    for row in rows:
        chiplet_count = maybe_int(row["xcut"]) * maybe_int(row["ycut"])
        output_rows.append(
            {
                "design_id": row["design_id"],
                "baseline_mode": row["baseline_mode"],
                "workload_motif": motif_of(row),
                "chiplet_count": chiplet_count,
                "regime": regime_from_chiplet_count(chiplet_count),
                "package_class": row["package_type"],
                "interface_class": row["IO_type"],
                "process_node": row["tech"],
                "tops_target_tops": maybe_int(row["tops"]) // 1024,
                "edp": f"{maybe_float(row['edp']):.6f}",
                "cost": f"{maybe_float(row['cost']):.6f}",
                "energy": f"{maybe_float(row['energy']):.6f}",
                "cycle": maybe_int(row["cycle"]),
                "status": "bootstrap_observed",
            }
        )

    path = output_dir / "phase_boundary.csv"
    write_csv(path, output_rows)
    return path.name


def write_split_margin(rows: List[Dict[str, str]], output_dir: Path) -> str:
    grouped: Dict[Tuple[str, str], List[Dict[str, str]]] = defaultdict(list)
    for row in rows:
        grouped[(row["baseline_mode"], motif_of(row))].append(row)

    output_rows = []
    for (baseline_mode, motif), group_rows in sorted(grouped.items()):
        winner = pick_min(group_rows, "edp")
        winner_edp = maybe_float(winner["edp"])
        winner_cost = maybe_float(winner["cost"])
        for row in group_rows:
            output_rows.append(
                {
                    "baseline_mode": baseline_mode,
                    "workload_motif": motif,
                    "design_id": row["design_id"],
                    "winner_design_id": winner["design_id"],
                    "edp_margin_pct": f"{((maybe_float(row['edp']) - winner_edp) / winner_edp * 100.0) if winner_edp else 0.0:.6f}",
                    "cost_margin_pct": f"{((maybe_float(row['cost']) - winner_cost) / winner_cost * 100.0) if winner_cost else 0.0:.6f}",
                    "chiplet_count": maybe_int(row["xcut"]) * maybe_int(row["ycut"]),
                    "status": "bootstrap_observed",
                }
            )

    path = output_dir / "split_margin.csv"
    write_csv(path, output_rows)
    return path.name


def write_pareto_points(rows: List[Dict[str, str]], output_dir: Path) -> str:
    output_rows = []
    for row in rows:
        output_rows.append(
            {
                "design_id": row["design_id"],
                "baseline_mode": row["baseline_mode"],
                "workload_motif": motif_of(row),
                "package_class": row["package_type"],
                "interface_class": row["IO_type"],
                "cost": f"{maybe_float(row['cost']):.6f}",
                "energy": f"{maybe_float(row['energy']):.6f}",
                "cycle": maybe_int(row["cycle"]),
                "is_pareto_front": str(is_pareto_point(row, rows)).lower(),
                "status": "bootstrap_observed",
            }
        )

    path = output_dir / "pareto_points.csv"
    write_csv(path, output_rows)
    return path.name


def write_energy_breakdown(record_map: Dict[str, Dict[str, Any]], output_dir: Path) -> str:
    output_rows = []
    for design_id, record in sorted(record_map.items()):
        breakdown = record["energy_breakdown"]
        total = sum(float(value) for value in breakdown.values())
        for component, value in breakdown.items():
            numeric = float(value)
            output_rows.append(
                {
                    "design_id": design_id,
                    "workload_motif": record.get("workload_motif") or record["workload"],
                    "component": component,
                    "energy": f"{numeric:.6f}",
                    "fraction": f"{(numeric / total) if total else 0.0:.6f}",
                    "status": "bootstrap_observed",
                }
            )

    path = output_dir / "energy_breakdown.csv"
    write_csv(path, output_rows)
    return path.name


def write_illegal_breakdown(records: List[Dict[str, Any]], output_dir: Path) -> str:
    categories = ["overall", "edge", "route", "memory"]
    output_rows = []
    for category in categories:
        counts = {"legal": 0, "illegal": 0, "unknown": 0}
        for record in records:
            value = record.get("legality_flags", {}).get(category, "unknown")
            if value not in counts:
                value = "unknown"
            counts[value] += 1
        output_rows.append(
            {
                "category": category,
                "legal_count": counts["legal"],
                "illegal_count": counts["illegal"],
                "unknown_count": counts["unknown"],
                "status": "bootstrap_placeholder" if counts["unknown"] == len(records) else "bootstrap_observed",
            }
        )

    path = output_dir / "illegal_breakdown.csv"
    write_csv(path, output_rows)
    return path.name


def write_weight_shift_summary(rows: List[Dict[str, str]], output_dir: Path) -> str:
    profiles = {
        "default_edp": "edp",
        "cost_focus": "cost",
        "energy_focus": "energy",
        "latency_focus": "cycle",
    }
    default_winner = pick_min(rows, profiles["default_edp"])
    output_rows = []
    for profile_name, metric in profiles.items():
        winner = pick_min(rows, metric)
        output_rows.append(
            {
                "weight_profile": profile_name,
                "metric": metric,
                "winner_design_id": winner["design_id"],
                "winner_changed_vs_default": str(winner["design_id"] != default_winner["design_id"]).lower(),
                "winner_metric_value": f"{maybe_float(winner[metric]):.6f}",
                "status": "bootstrap_observed",
            }
        )

    path = output_dir / "weight_shift_summary.csv"
    write_csv(path, output_rows)
    return path.name


def write_boundary_drift(backend_dir: Path | None, output_dir: Path) -> str:
    output_rows: List[Dict[str, Any]] = []
    if backend_dir:
        backend_path = backend_dir / "boundary_drift_backend.csv"
        if backend_path.exists():
            backend_rows = read_csv(backend_path)
            require_columns(backend_rows, ["metric", "value", "status"], backend_path)
            for row in backend_rows:
                output_rows.append(
                    {
                        "metric": row["metric"],
                        "value": row["value"],
                        "source": str(backend_path),
                        "status": row["status"],
                    }
                )
    if not output_rows:
        output_rows = [
            {
                "metric": "backend_pending",
                "value": "",
                "source": str(backend_dir) if backend_dir else "",
                "status": "pending_backend",
            }
        ]

    path = output_dir / "boundary_drift.csv"
    write_csv(path, output_rows)
    return path.name


def write_sensitivity_tags(backend_dir: Path | None, output_dir: Path) -> str:
    output_rows: List[Dict[str, Any]] = []
    if backend_dir:
        router_path = backend_dir / "router_sensitivity.csv"
        if router_path.exists():
            router_rows = read_csv(router_path)
            require_columns(
                router_rows,
                ["capacity_case", "winner_agreement", "precision", "recall", "boundary_drift", "status"],
                router_path,
            )
            for row in router_rows:
                output_rows.append(
                    {
                        "capacity_case": row["capacity_case"],
                        "sensitivity_tag": "router_capacity",
                        "winner_agreement": row["winner_agreement"],
                        "precision": row["precision"],
                        "recall": row["recall"],
                        "boundary_drift": row["boundary_drift"],
                        "status": row["status"],
                    }
                )
    if not output_rows:
        output_rows = [
            {
                "capacity_case": "backend_pending",
                "sensitivity_tag": "router_capacity",
                "winner_agreement": "",
                "precision": "",
                "recall": "",
                "boundary_drift": "",
                "status": "pending_backend",
            }
        ]

    path = output_dir / "sensitivity_tags.csv"
    write_csv(path, output_rows)
    return path.name


def build_paper_manifest(
    repo_root: Path,
    aggregated_run: Path,
    output_dir: Path,
    backend_dir: Path | None,
) -> Dict[str, Any]:
    run_name = aggregated_run.name
    figures_dir = repo_root / "results" / "figures"
    relative = lambda path: str(path.relative_to(repo_root))
    entries = [
        {
            "figure": "Fig. 3",
            "caption": "Validation chain",
            "source_data": ["validation/*.csv"],
            "generated_paths": [
                relative(figures_dir / "fig3_validation.pdf"),
                relative(figures_dir / "fig3_validation.png"),
            ],
            "latex_include_path": "paper/figures/fig3_validation.pdf",
            "generation_command": "python3 pyscripts/analysis/gen_validation.py",
            "status": "pending_validation_chain",
        },
        {
            "figure": "Fig. 4",
            "caption": "Stronger baselines",
            "source_data": [
                relative(output_dir / "winner_change_matrix.csv"),
                relative(output_dir / "reevaluated_loss.csv"),
            ],
            "generated_paths": [
                relative(figures_dir / "fig4_baselines.pdf"),
                relative(figures_dir / "fig4_baselines.png"),
            ],
            "latex_include_path": "paper/figures/fig4_baselines.pdf",
            "generation_command": "./scripts/run_figure4.sh",
            "status": "plot_ready_only",
        },
        {
            "figure": "Fig. 5",
            "caption": "Interface vs package and memory ablation",
            "source_data": [
                relative(output_dir / "interface_vs_package.csv"),
                relative(output_dir / "memory_off_ablation.csv"),
            ],
            "generated_paths": [
                relative(figures_dir / "fig5_interface_memory.pdf"),
                relative(figures_dir / "fig5_interface_memory.png"),
            ],
            "latex_include_path": "paper/figures/fig5_interface_memory.pdf",
            "generation_command": "./scripts/run_figure5.sh",
            "status": "plot_ready_only",
        },
        {
            "figure": "Fig. 6",
            "caption": "Phase map",
            "source_data": [
                relative(output_dir / "phase_boundary.csv"),
                relative(output_dir / "split_margin.csv"),
            ],
            "generated_paths": [
                relative(figures_dir / "fig6_phase_map.pdf"),
                relative(figures_dir / "fig6_phase_map.png"),
            ],
            "latex_include_path": "paper/figures/fig6_phase_map.pdf",
            "generation_command": "./scripts/run_figure6.sh",
            "status": "plot_ready_only",
        },
        {
            "figure": "Fig. 7",
            "caption": "Pareto and energy breakdown",
            "source_data": [
                relative(output_dir / "pareto_points.csv"),
                relative(output_dir / "energy_breakdown.csv"),
            ],
            "generated_paths": [
                relative(figures_dir / "fig7_pareto_energy.pdf"),
                relative(figures_dir / "fig7_pareto_energy.png"),
            ],
            "latex_include_path": "paper/figures/fig7_pareto_energy.pdf",
            "generation_command": "./scripts/run_figure7.sh",
            "status": "plot_ready_only",
        },
        {
            "figure": "Fig. 8",
            "caption": "Sensitivity and closure",
            "source_data": [
                relative(output_dir / "boundary_drift.csv"),
                relative(output_dir / "sensitivity_tags.csv"),
            ],
            "generated_paths": [
                relative(figures_dir / "fig8_closure.pdf"),
                relative(figures_dir / "fig8_closure.png"),
            ],
            "latex_include_path": "paper/figures/fig8_closure.pdf",
            "generation_command": "./scripts/run_figure8.sh",
            "status": "backend_plot_ready" if backend_dir else "pending_backend",
        },
    ]

    tables = [
        {
            "table": "illegal_breakdown",
            "source_data": [relative(output_dir / "illegal_breakdown.csv")],
            "generation_command": "python3 pyscripts/analysis/aggregate_illegal_breakdown.py",
            "status": "plot_ready_only",
        },
        {
            "table": "weight_shift_summary",
            "source_data": [relative(output_dir / "weight_shift_summary.csv")],
            "generation_command": "python3 pyscripts/analysis/aggregate_weight_sweep.py",
            "status": "plot_ready_only",
        },
    ]

    return {
        "schema_version": "bootstrap_v0",
        "run_name": run_name,
        "aggregated_run": relative(aggregated_run),
        "plot_ready_dir": relative(output_dir),
        "backend_dir": relative(backend_dir) if backend_dir else None,
        "figures": entries,
        "tables": tables,
        "notes": [
            "This manifest tracks plot-ready data and intended figure asset destinations.",
            "Bootstrap PDF and PNG rendering is available through scripts/run_figure4.sh through scripts/run_figure8.sh and python3 pyscripts/analysis/gen_validation.py."
        ],
    }


def update_plot_ready_manifest(output_dir: Path, generated_files: List[str], backend_dir: Path | None) -> None:
    manifest_path = output_dir / "manifest.json"
    manifest = load_json(manifest_path) if manifest_path.exists() else {}
    manifest["plot_ready_status"] = "bootstrap"
    manifest["generated_files"] = generated_files
    manifest["backend_dir"] = str(backend_dir) if backend_dir else None
    dump_json(manifest_path, manifest)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate bootstrap PICASSO plot-ready outputs")
    parser.add_argument("--aggregated-run", required=True, help="Path to an aggregated run directory")
    parser.add_argument("--output-dir", required=True, help="Path to a plot-ready run directory")
    parser.add_argument("--backend-dir", default=None, help="Optional backend aggregate directory")
    parser.add_argument("--manifest-output", required=True, help="Global paper_figure_manifest.json output path")
    args = parser.parse_args()

    aggregated_run = Path(args.aggregated_run).resolve()
    output_dir = Path(args.output_dir).resolve()
    backend_dir = Path(args.backend_dir).resolve() if args.backend_dir else None
    manifest_output = Path(args.manifest_output).resolve()
    repo_root = aggregated_run.parents[2]

    result_csv = aggregated_run / "result.csv"
    design_records_json = aggregated_run / "design_records.json"
    rows = read_csv(result_csv)
    require_columns(
        rows,
        [
            "design_id",
            "baseline_mode",
            "workload_name",
            "workload_motif",
            "IO_type",
            "package_type",
            "ddr_type",
            "xcut",
            "ycut",
            "tops",
            "cycle",
            "energy",
            "edp",
            "cost",
        ],
        result_csv,
    )
    records = load_json(design_records_json)["records"]
    record_map = {record["design_id"]: record for record in records}
    figure_rows = prefer_joint_rows(rows)
    figure_design_ids = {row["design_id"] for row in figure_rows}
    figure_record_map = {
        design_id: record_map[design_id]
        for design_id in sorted(figure_design_ids)
        if design_id in record_map
    }
    figure_records = list(figure_record_map.values())

    output_dir.mkdir(parents=True, exist_ok=True)

    generated_files = [
        write_winner_change_matrix(rows, output_dir),
        write_reevaluated_loss(rows, output_dir),
        write_interface_vs_package(figure_rows, output_dir),
        write_memory_off_ablation(rows, output_dir),
        write_phase_boundary(figure_rows, output_dir),
        write_split_margin(figure_rows, output_dir),
        write_pareto_points(figure_rows, output_dir),
        write_energy_breakdown(figure_record_map, output_dir),
        write_boundary_drift(backend_dir, output_dir),
        write_sensitivity_tags(backend_dir, output_dir),
        write_illegal_breakdown(figure_records, output_dir),
        write_weight_shift_summary(figure_rows, output_dir),
    ]

    paper_manifest = build_paper_manifest(repo_root, aggregated_run, output_dir, backend_dir)
    dump_json(output_dir / "paper_figure_manifest.json", paper_manifest)
    manifest_output.parent.mkdir(parents=True, exist_ok=True)
    dump_json(manifest_output, paper_manifest)
    generated_files.append("paper_figure_manifest.json")
    update_plot_ready_manifest(output_dir, generated_files, backend_dir)

    print(f"[PICASSO] Generated plot-ready bootstrap outputs into {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
