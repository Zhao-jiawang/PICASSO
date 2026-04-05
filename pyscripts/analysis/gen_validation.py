#!/usr/bin/env python3

import argparse
import csv
import json
import shutil
import subprocess
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


PALETTE = {
    "primary": "#235789",
    "accent": "#c1292e",
    "support": "#f1d302",
    "neutral": "#4b5563",
    "mono": "#0f766e",
    "node7": "#0f766e",
    "node12": "#b45309",
}


def load_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def dump_json(path: Path, payload: Dict[str, Any]) -> None:
    with path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, sort_keys=True)
        fh.write("\n")


def read_csv(path: Path) -> List[Dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    if not rows:
        raise ValueError(f"{path} is empty")
    return rows


def write_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    if not rows:
        raise ValueError(f"No rows provided for {path}")
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def maybe_float(value: str) -> float:
    if value in ("", None):
        return 0.0
    return float(value)


def latest_dir(root: Path, suffix: str) -> Optional[Path]:
    candidates = sorted(path for path in root.glob(f"*{suffix}") if path.is_dir())
    return candidates[-1] if candidates else None


def load_latest_run_rows(repo_root: Path, suffix: str) -> List[Dict[str, str]]:
    aggregated_root = repo_root / "results" / "aggregated"
    run_dir = latest_dir(aggregated_root, suffix)
    if run_dir is None:
        raise FileNotFoundError(f"No aggregated run found for suffix '{suffix}'")
    return read_csv(run_dir / "result.csv")


def load_latest_run_snapshots(repo_root: Path, suffix: str) -> List[Dict[str, Any]]:
    raw_root = repo_root / "results" / "raw"
    run_dir = latest_dir(raw_root, suffix)
    if run_dir is None:
        raise FileNotFoundError(f"No raw run found for suffix '{suffix}'")
    return [load_json(snapshot_path) for snapshot_path in sorted(run_dir.glob("*/point_snapshot.json"))]


def compute_efficiency(params: Dict[str, Any]) -> float:
    return float(params["frequency_ghz"]) / float(params["scale_factor"]) / max(float(params["power_factor"]), 1e-9)


MIN_MATCHED_ANCHORS = 2


def _anchor_key(snapshot: Dict[str, Any]) -> tuple[str, str, str, int]:
    point = snapshot["normalized_point"]
    return (
        str(point.get("workload_motif") or point["workload_name"]),
        str(point.get("workload_exec_name") or point["workload_name"]),
        str(point["microarch_name"]),
        int(point.get("tops_target_tops") or point["tops"]),
    )


def build_compute_grounding(repo_root: Path) -> List[Dict[str, Any]]:
    process_nodes = load_json(repo_root / "configs" / "process_nodes.json")
    snapshots = (
        load_latest_run_snapshots(repo_root, "paper_smoke")
        + load_latest_run_snapshots(repo_root, "paper_core_bootstrap")
        + load_latest_run_snapshots(repo_root, "paper_full_bootstrap")
    )
    snapshots = [snapshot for snapshot in snapshots if snapshot["normalized_point"]["baseline_mode"] == "Joint"]
    grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    legal_anchor_by_tech: Dict[str, Dict[tuple[str, str], float]] = defaultdict(dict)
    for snapshot in snapshots:
        point = snapshot["normalized_point"]
        grouped[point["tech"]].append(snapshot)
        best_eval = snapshot["search_summary"]["best_eval"]
        if best_eval["legal"]:
            legal_anchor_by_tech[point["tech"]][_anchor_key(snapshot)] = float(best_eval["cycle"]) / max(point["tops"], 1)

    baseline_efficiency = compute_efficiency(process_nodes["12"]) if "12" in process_nodes else 1.0

    output_rows = []
    for node, params in sorted(process_nodes.items(), key=lambda item: int(item[0])):
        node_snapshots = grouped.get(node, [])
        avg_cycle = (
            sum(float(snapshot["search_summary"]["best_eval"]["cycle"]) for snapshot in node_snapshots) / len(node_snapshots)
            if node_snapshots
            else 0.0
        )
        avg_energy = (
            sum(float(snapshot["search_summary"]["best_eval"]["energy"]) for snapshot in node_snapshots) / len(node_snapshots)
            if node_snapshots
            else 0.0
        )
        avg_cycle_per_top = (
            sum(
                float(snapshot["search_summary"]["best_eval"]["cycle"]) / max(snapshot["normalized_point"]["tops"], 1)
                for snapshot in node_snapshots
            )
            / len(node_snapshots)
            if node_snapshots
            else 0.0
        )
        compute_efficiency_index = compute_efficiency(params)
        common_anchors = set(legal_anchor_by_tech.get("12", {})) & set(legal_anchor_by_tech.get(node, {}))
        if node == "12":
            latency_advantage = 1.0
            anchor_basis = "baseline"
        elif len(common_anchors) >= MIN_MATCHED_ANCHORS:
            baseline_anchor = sum(legal_anchor_by_tech["12"][anchor] for anchor in common_anchors) / len(common_anchors)
            node_anchor = sum(legal_anchor_by_tech[node][anchor] for anchor in common_anchors) / len(common_anchors)
            latency_advantage = baseline_anchor / max(node_anchor, 1e-9)
            anchor_basis = "matched_legal_anchor"
        else:
            latency_advantage = compute_efficiency_index / max(baseline_efficiency, 1e-9)
            anchor_basis = "process_registry_fallback"
        output_rows.append(
            {
                "process_node": node,
                "frequency_ghz": f"{params['frequency_ghz']:.6f}",
                "power_factor": f"{params['power_factor']:.6f}",
                "scale_factor": f"{params['scale_factor']:.6f}",
                "observed_design_count": len(node_snapshots),
                "legal_design_count": sum(1 for snapshot in node_snapshots if snapshot["search_summary"]["best_eval"]["legal"]),
                "matched_anchor_count": len(common_anchors) if node != "12" else 0,
                "observed_avg_cycle": f"{avg_cycle:.6f}",
                "observed_avg_energy": f"{avg_energy:.6f}",
                "observed_avg_cycle_per_top": f"{avg_cycle_per_top:.9f}",
                "compute_efficiency_index": f"{compute_efficiency_index:.6f}",
                "latency_advantage_vs_12nm": f"{latency_advantage:.6f}",
                "latency_advantage_basis": anchor_basis,
                "trend_tag": "better" if node == "7" else "baseline",
                "status": "bootstrap_grounded",
            }
        )
    return output_rows


def build_interface_envelope(repo_root: Path) -> List[Dict[str, Any]]:
    interfaces = load_json(repo_root / "configs" / "interfaces.json")
    output_rows: List[Dict[str, Any]] = []
    for interface_name, payload in sorted(interfaces.items()):
        if "tech_overrides" in payload:
            for tech, override in sorted(payload["tech_overrides"].items(), key=lambda item: int(item[0])):
                penalty_key = "serdes_power_mw_per_lane" if "serdes_power_mw_per_lane" in override else "nop_hop_cost"
                output_rows.append(
                    {
                        "interface_class": interface_name,
                        "context_type": "tech",
                        "context_value": tech,
                        "effective_density_area_per_gbps": f"{override['nop_density_area_per_gbps']:.6f}",
                        "penalty_metric_kind": penalty_key,
                        "penalty_metric_value": f"{override[penalty_key]:.6f}",
                        "trend_tag": "better" if tech == "7" else "baseline",
                        "status": "bootstrap_registry",
                    }
                )
        if "package_overrides" in payload:
            for package_class, override in sorted(payload["package_overrides"].items()):
                output_rows.append(
                    {
                        "interface_class": interface_name,
                        "context_type": "package",
                        "context_value": package_class,
                        "effective_density_area_per_gbps": f"{override['nop_density_area_per_gbps']:.6f}",
                        "penalty_metric_kind": "nop_hop_cost",
                        "penalty_metric_value": f"{override['nop_hop_cost']:.6f}",
                        "trend_tag": "better" if package_class in ("FO", "SI") else "baseline",
                        "status": "bootstrap_registry",
                    }
                )
    return output_rows


def build_package_yield_anchor(repo_root: Path) -> List[Dict[str, Any]]:
    full_rows = load_latest_run_rows(repo_root, "paper_full_bootstrap")
    grouped: Dict[str, List[Dict[str, str]]] = defaultdict(list)
    for row in full_rows:
        grouped[row["package_type"]].append(row)

    output_rows = []
    for package_class, rows in sorted(grouped.items()):
        avg_package_cost = sum(maybe_float(row["cost_package"]) for row in rows) / len(rows)
        avg_chip_cost = sum(maybe_float(row["cost_chip"]) for row in rows) / len(rows)
        avg_total_die_area = sum(maybe_float(row["total_die_area"]) for row in rows) / len(rows)
        yield_pressure_proxy = avg_total_die_area * avg_chip_cost
        output_rows.append(
            {
                "package_class": package_class,
                "observed_design_count": len(rows),
                "avg_package_cost": f"{avg_package_cost:.6f}",
                "avg_chip_cost": f"{avg_chip_cost:.6f}",
                "avg_total_die_area": f"{avg_total_die_area:.6f}",
                "yield_pressure_proxy": f"{yield_pressure_proxy:.6f}",
                "trend_tag": "better" if package_class == "OS" else "costlier",
                "status": "bootstrap_observed",
            }
        )
    return output_rows


def save_figure(fig: plt.Figure, repo_root: Path) -> None:
    results_dir = repo_root / "results" / "figures"
    paper_dir = repo_root / "paper" / "figures"
    results_dir.mkdir(parents=True, exist_ok=True)
    paper_dir.mkdir(parents=True, exist_ok=True)

    pdf_path = results_dir / "fig3_validation.pdf"
    png_path = results_dir / "fig3_validation.png"
    fig.tight_layout()
    fig.savefig(pdf_path, bbox_inches="tight")
    fig.savefig(png_path, bbox_inches="tight", dpi=220)
    shutil.copy2(pdf_path, paper_dir / pdf_path.name)
    shutil.copy2(png_path, paper_dir / png_path.name)
    plt.close(fig)


def render_validation_figure(
    compute_rows: List[Dict[str, Any]],
    interface_rows: List[Dict[str, Any]],
    package_rows: List[Dict[str, Any]],
    repo_root: Path,
) -> None:
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.8))

    compute_labels = [f"{row['process_node']}nm" for row in compute_rows]
    efficiency = [maybe_float(row["compute_efficiency_index"]) for row in compute_rows]
    latency = [maybe_float(row["latency_advantage_vs_12nm"]) for row in compute_rows]
    bars = axes[0].bar(
        compute_labels,
        efficiency,
        color=[PALETTE["node12"] if row["process_node"] == "12" else PALETTE["node7"] for row in compute_rows],
    )
    axes[0].plot(compute_labels, latency, color=PALETTE["accent"], marker="o", linewidth=2)
    axes[0].set_title("Fig. 3a Compute Grounding")
    axes[0].set_ylabel("Efficiency index / latency advantage")
    axes[0].grid(axis="y", alpha=0.25)
    for bar, row in zip(bars, compute_rows):
        axes[0].text(
            bar.get_x() + bar.get_width() / 2.0,
            bar.get_height() + 0.05,
            f"n={row['observed_design_count']} l={row['legal_design_count']}",
            ha="center",
            fontsize=8,
        )

    interface_labels = [f"{row['interface_class']}@{row['context_value']}" for row in interface_rows]
    interface_density = [maybe_float(row["effective_density_area_per_gbps"]) for row in interface_rows]
    colors = []
    for row in interface_rows:
        if row["interface_class"] == "XSR":
            colors.append(PALETTE["primary"])
        elif row["interface_class"] == "USR":
            colors.append(PALETTE["neutral"])
        else:
            colors.append(PALETTE["support"])
    axes[1].bar(interface_labels, interface_density, color=colors)
    axes[1].set_title("Fig. 3b Interface Envelope")
    axes[1].set_ylabel("Density area per Gbps")
    axes[1].tick_params(axis="x", rotation=28)
    axes[1].grid(axis="y", alpha=0.25)

    package_labels = [row["package_class"] for row in package_rows]
    package_cost = [maybe_float(row["avg_package_cost"]) for row in package_rows]
    yield_proxy = [maybe_float(row["yield_pressure_proxy"]) / 1e3 for row in package_rows]
    bars = axes[2].bar(package_labels, package_cost, color=[PALETTE["mono"], PALETTE["support"], PALETTE["accent"]][: len(package_rows)])
    axes[2].plot(package_labels, yield_proxy, color=PALETTE["primary"], marker="o", linewidth=2)
    axes[2].set_title("Fig. 3c Package and Yield Anchor")
    axes[2].set_ylabel("Package cost / yield proxy (1e3)")
    axes[2].grid(axis="y", alpha=0.25)
    for bar, row in zip(bars, package_rows):
        axes[2].text(
            bar.get_x() + bar.get_width() / 2.0,
            bar.get_height() + 0.5,
            row["trend_tag"],
            ha="center",
            fontsize=8,
        )

    fig.suptitle("PICASSO Bootstrap Fig. 3 Validation Chain", fontsize=14, fontweight="bold")
    save_figure(fig, repo_root)


def refresh_manifest(repo_root: Path) -> None:
    subprocess.run(
        [
            sys.executable,
            str(repo_root / "pyscripts" / "pipeline" / "refresh_paper_manifest.py"),
            "--repo-root",
            str(repo_root),
            "--output",
            str(repo_root / "results" / "figures" / "paper_figure_manifest.json"),
        ],
        cwd=repo_root,
        check=True,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate bootstrap Fig. 3 validation data and figure")
    parser.add_argument("--repo-root", default=None, help="Repo root, defaults to script parent")
    args = parser.parse_args()

    script_path = Path(__file__).resolve()
    repo_root = Path(args.repo_root).resolve() if args.repo_root else script_path.parent.parent.parent
    validation_dir = repo_root / "validation"
    validation_dir.mkdir(parents=True, exist_ok=True)

    compute_rows = build_compute_grounding(repo_root)
    interface_rows = build_interface_envelope(repo_root)
    package_rows = build_package_yield_anchor(repo_root)

    compute_path = validation_dir / "compute_grounding.csv"
    interface_path = validation_dir / "interface_envelope.csv"
    package_path = validation_dir / "package_yield_anchor.csv"
    write_csv(compute_path, compute_rows)
    write_csv(interface_path, interface_rows)
    write_csv(package_path, package_rows)

    manifest = {
        "schema_version": "bootstrap_v0",
        "generated_files": [
            str(compute_path.relative_to(repo_root)),
            str(interface_path.relative_to(repo_root)),
            str(package_path.relative_to(repo_root)),
            "results/figures/fig3_validation.pdf",
            "results/figures/fig3_validation.png",
        ],
        "notes": [
            "Bootstrap validation data combine config registries with the latest smoke, paper-core, and paper-full runs.",
            "Compute grounding uses Joint-baseline snapshots and requires at least two comparable matched legal anchors; otherwise it falls back to process-registry normalization.",
            "The trends are grounded in the current scaffold and remain placeholders for later calibration."
        ],
        "status": "bootstrap_validation",
    }
    dump_json(validation_dir / "manifest.json", manifest)

    render_validation_figure(compute_rows, interface_rows, package_rows, repo_root)
    refresh_manifest(repo_root)
    print(f"[PICASSO] Generated bootstrap validation data into {validation_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
