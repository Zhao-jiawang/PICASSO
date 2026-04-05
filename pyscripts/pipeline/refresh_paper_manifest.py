#!/usr/bin/env python3

import argparse
import csv
import json
from pathlib import Path
from typing import Any, Dict, List, Optional


def load_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def dump_json(path: Path, payload: Dict[str, Any]) -> None:
    with path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, sort_keys=True)
        fh.write("\n")


def read_csv(path: Path) -> List[Dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def latest_dir(root: Path, suffix: str) -> Optional[Path]:
    candidates = sorted(path for path in root.glob(f"*{suffix}") if path.is_dir())
    return candidates[-1] if candidates else None


def relative(repo_root: Path, path: Optional[Path]) -> Optional[str]:
    if path is None:
        return None
    return str(path.relative_to(repo_root))


def status_from_boundary_drift(path: Optional[Path]) -> str:
    if path is None or not path.exists():
        return "pending_backend"
    rows = read_csv(path)
    if not rows:
        return "pending_backend"
    if all(row.get("status") == "pending_backend" for row in rows):
        return "pending_backend"
    return "backend_plot_ready"


def source_list(repo_root: Path, base_dir: Optional[Path], names: List[str]) -> List[str]:
    if base_dir is None:
        return []
    return [str((base_dir / name).relative_to(repo_root)) for name in names]


def rendered_status(repo_root: Path, figure_stem: str, fallback_status: str) -> str:
    pdf_path = repo_root / "results" / "figures" / f"{figure_stem}.pdf"
    png_path = repo_root / "results" / "figures" / f"{figure_stem}.png"
    if pdf_path.exists() and png_path.exists():
        return "rendered_current"
    return fallback_status


def validation_sources(repo_root: Path) -> List[str]:
    validation_dir = repo_root / "validation"
    names = [
        "compute_grounding.csv",
        "interface_envelope.csv",
        "package_yield_anchor.csv",
    ]
    sources = []
    for name in names:
        path = validation_dir / name
        if path.exists():
            sources.append(str(path.relative_to(repo_root)))
    return sources


def build_manifest(repo_root: Path) -> Dict[str, Any]:
    plot_ready_root = repo_root / "results" / "plot_ready"
    figures_root = repo_root / "results" / "figures"

    smoke_plot_ready = latest_dir(plot_ready_root, "paper_smoke")
    core_plot_ready = latest_dir(plot_ready_root, "paper_core_bootstrap")
    full_plot_ready = latest_dir(plot_ready_root, "paper_full_bootstrap")
    fallback_plot_ready = full_plot_ready or core_plot_ready or smoke_plot_ready

    core_backend = None
    if core_plot_ready:
        candidate = repo_root / "results" / "backend_aggregated" / core_plot_ready.name
        if candidate.exists():
            core_backend = candidate

    fig8_status = status_from_boundary_drift(
        (core_plot_ready / "boundary_drift.csv") if core_plot_ready else None
    )

    manifest = {
        "schema_version": "artifact_v1",
        "contexts": {
            "smoke_plot_ready": relative(repo_root, smoke_plot_ready),
            "paper_core_plot_ready": relative(repo_root, core_plot_ready),
            "paper_full_plot_ready": relative(repo_root, full_plot_ready),
            "paper_core_backend": relative(repo_root, core_backend),
        },
        "figures": [
            {
                "figure": "Fig. 3",
                "caption": "Validation chain",
                "source_data": validation_sources(repo_root) or ["validation/*.csv"],
                "generated_paths": [
                    str((figures_root / "fig3_validation.pdf").relative_to(repo_root)),
                    str((figures_root / "fig3_validation.png").relative_to(repo_root)),
                ],
                "latex_include_path": "paper/figures/fig3_validation.pdf",
                "generation_command": "python3 pyscripts/analysis/gen_validation.py",
                "status": rendered_status(repo_root, "fig3_validation", "pending_validation_chain"),
            },
            {
                "figure": "Fig. 4",
                "caption": "Stronger baselines",
                "source_data": source_list(
                    repo_root,
                    core_plot_ready,
                    ["winner_change_matrix.csv", "reevaluated_loss.csv"],
                ),
                "generated_paths": [
                    str((figures_root / "fig4_baselines.pdf").relative_to(repo_root)),
                    str((figures_root / "fig4_baselines.png").relative_to(repo_root)),
                ],
                "latex_include_path": "paper/figures/fig4_baselines.pdf",
                "generation_command": "./scripts/run_figure4.sh",
                "status": rendered_status(
                    repo_root,
                    "fig4_baselines",
                    "plot_ready_only" if core_plot_ready else "pending_core_plot_ready",
                ),
            },
            {
                "figure": "Fig. 5",
                "caption": "Interface vs package and memory ablation",
                "source_data": source_list(
                    repo_root,
                    core_plot_ready,
                    ["interface_vs_package.csv", "memory_off_ablation.csv"],
                ),
                "generated_paths": [
                    str((figures_root / "fig5_interface_memory.pdf").relative_to(repo_root)),
                    str((figures_root / "fig5_interface_memory.png").relative_to(repo_root)),
                ],
                "latex_include_path": "paper/figures/fig5_interface_memory.pdf",
                "generation_command": "./scripts/run_figure5.sh",
                "status": rendered_status(
                    repo_root,
                    "fig5_interface_memory",
                    "plot_ready_only" if core_plot_ready else "pending_core_plot_ready",
                ),
            },
            {
                "figure": "Fig. 6",
                "caption": "Phase map",
                "source_data": source_list(
                    repo_root,
                    full_plot_ready,
                    ["phase_boundary.csv", "split_margin.csv"],
                ),
                "generated_paths": [
                    str((figures_root / "fig6_phase_map.pdf").relative_to(repo_root)),
                    str((figures_root / "fig6_phase_map.png").relative_to(repo_root)),
                ],
                "latex_include_path": "paper/figures/fig6_phase_map.pdf",
                "generation_command": "./scripts/run_figure6.sh",
                "status": rendered_status(
                    repo_root,
                    "fig6_phase_map",
                    "plot_ready_only" if full_plot_ready else "pending_full_plot_ready",
                ),
            },
            {
                "figure": "Fig. 7",
                "caption": "Pareto and energy breakdown",
                "source_data": source_list(
                    repo_root,
                    full_plot_ready,
                    ["pareto_points.csv", "energy_breakdown.csv"],
                ),
                "generated_paths": [
                    str((figures_root / "fig7_pareto_energy.pdf").relative_to(repo_root)),
                    str((figures_root / "fig7_pareto_energy.png").relative_to(repo_root)),
                ],
                "latex_include_path": "paper/figures/fig7_pareto_energy.pdf",
                "generation_command": "./scripts/run_figure7.sh",
                "status": rendered_status(
                    repo_root,
                    "fig7_pareto_energy",
                    "plot_ready_only" if full_plot_ready else "pending_full_plot_ready",
                ),
            },
            {
                "figure": "Fig. 8",
                "caption": "Sensitivity and closure",
                "source_data": source_list(
                    repo_root,
                    core_plot_ready,
                    ["boundary_drift.csv", "sensitivity_tags.csv"],
                ),
                "generated_paths": [
                    str((figures_root / "fig8_closure.pdf").relative_to(repo_root)),
                    str((figures_root / "fig8_closure.png").relative_to(repo_root)),
                ],
                "latex_include_path": "paper/figures/fig8_closure.pdf",
                "generation_command": "./scripts/run_figure8.sh",
                "status": rendered_status(
                    repo_root,
                    "fig8_closure",
                    fig8_status if core_plot_ready else "pending_core_plot_ready",
                ),
            },
        ],
        "tables": [
            {
                "table": "illegal_breakdown",
                "source_data": source_list(repo_root, fallback_plot_ready, ["illegal_breakdown.csv"]),
                "generation_command": "python3 pyscripts/analysis/aggregate_illegal_breakdown.py",
                "status": "plot_ready_only" if fallback_plot_ready else "pending_plot_ready",
            },
            {
                "table": "weight_shift_summary",
                "source_data": source_list(repo_root, fallback_plot_ready, ["weight_shift_summary.csv"]),
                "generation_command": "python3 pyscripts/analysis/aggregate_weight_sweep.py",
                "status": "plot_ready_only" if fallback_plot_ready else "pending_plot_ready",
            },
        ],
        "notes": [
            "This manifest is assembled from the latest accepted plot-ready bundles for each figure family.",
            "Paper-facing figure copies under paper/figures/ are refreshed from the same generated assets recorded here."
        ],
    }
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Refresh the global paper figure manifest")
    parser.add_argument("--repo-root", default=None, help="Repo root, defaults to script parent")
    parser.add_argument("--output", required=True, help="Output paper_figure_manifest.json path")
    args = parser.parse_args()

    script_path = Path(__file__).resolve()
    repo_root = Path(args.repo_root).resolve() if args.repo_root else script_path.parent.parent.parent
    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    dump_json(output, build_manifest(repo_root))
    print(f"[PICASSO] Refreshed global paper figure manifest at {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
