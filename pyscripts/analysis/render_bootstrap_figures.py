#!/usr/bin/env python3

import argparse
import csv
import shutil
from pathlib import Path
from typing import Dict, List

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


FIGURE_FILENAMES = {
    "fig4": "fig4_baselines",
    "fig5": "fig5_interface_memory",
    "fig6": "fig6_phase_map",
    "fig7": "fig7_pareto_energy",
    "fig8": "fig8_closure",
}

BASELINE_ABBREV = {
    "Joint": "J",
    "Stage-wise": "SW",
    "Package-oblivious": "PO",
    "Architecture-first": "AF",
    "Partition-first": "PF",
    "Cost-interface-first": "CIF",
    "Outer-loop repair": "GOR",
    "Memory-off": "MO",
}

PALETTE = {
    "primary": "#235789",
    "accent": "#c1292e",
    "support": "#f1d302",
    "neutral": "#4b5563",
    "mono": "#0f766e",
    "few": "#b45309",
    "many": "#7c3aed",
}


def read_csv(path: Path) -> List[Dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    if not rows:
        raise ValueError(f"{path} is empty")
    return rows


def maybe_float(value: str) -> float:
    if value in ("", None):
        return 0.0
    return float(value)


def maybe_int(value: str) -> int:
    if value in ("", None):
        return 0
    return int(float(value))


def save_outputs(fig: plt.Figure, repo_root: Path, figure_key: str) -> None:
    stem = FIGURE_FILENAMES[figure_key]
    results_dir = repo_root / "results" / "figures"
    paper_dir = repo_root / "paper" / "figures"
    results_dir.mkdir(parents=True, exist_ok=True)
    paper_dir.mkdir(parents=True, exist_ok=True)

    pdf_path = results_dir / f"{stem}.pdf"
    png_path = results_dir / f"{stem}.png"
    fig.savefig(pdf_path, bbox_inches="tight")
    fig.savefig(png_path, bbox_inches="tight", dpi=220)
    shutil.copy2(pdf_path, paper_dir / pdf_path.name)
    shutil.copy2(png_path, paper_dir / png_path.name)


def finalize(fig: plt.Figure, repo_root: Path, figure_key: str) -> None:
    fig.tight_layout()
    save_outputs(fig, repo_root, figure_key)
    plt.close(fig)


def render_fig4(plot_ready_dir: Path, repo_root: Path) -> None:
    winners = read_csv(plot_ready_dir / "winner_change_matrix.csv")
    losses = read_csv(plot_ready_dir / "reevaluated_loss.csv")

    ordered_modes = []
    for row in winners:
        mode = row["baseline_mode"]
        if mode not in ordered_modes:
            ordered_modes.append(mode)

    changed_by_mode = []
    loss_by_mode = []
    for mode in ordered_modes:
        mode_winners = [row for row in winners if row["baseline_mode"] == mode]
        mode_losses = [row for row in losses if row["baseline_mode"] == mode]
        changed_by_mode.append(
            sum(1.0 if row.get("winner_changed_vs_joint", row.get("winner_changed_vs_global")) == "true" else 0.0 for row in mode_winners)
            / max(len(mode_winners), 1)
        )
        loss_by_mode.append(
            sum(maybe_float(row["edp_loss_pct"]) for row in mode_losses) / max(len(mode_losses), 1)
        )
    labels = [BASELINE_ABBREV.get(mode, mode) for mode in ordered_modes]

    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5))
    axes[0].bar(labels, changed_by_mode, color=PALETTE["primary"])
    axes[0].set_ylim(0.0, 1.1)
    axes[0].set_ylabel("Winner-change rate vs Joint")
    axes[0].set_title("Fig. 4a Baseline Winner Shift")
    axes[0].grid(axis="y", alpha=0.25)
    for idx, value in enumerate(changed_by_mode):
        axes[0].text(idx, value + 0.03, f"{value:.2f}", ha="center", fontsize=9)

    axes[1].bar(labels, loss_by_mode, color=PALETTE["accent"])
    axes[1].set_ylabel("Mean EDP loss vs Joint (%)")
    axes[1].set_title("Fig. 4b Re-evaluated Loss")
    axes[1].grid(axis="y", alpha=0.25)

    fig.suptitle("PICASSO Bootstrap Fig. 4", fontsize=14, fontweight="bold")
    finalize(fig, repo_root, "fig4")


def render_fig5(plot_ready_dir: Path, repo_root: Path) -> None:
    interface_rows = read_csv(plot_ready_dir / "interface_vs_package.csv")
    memory_rows = read_csv(plot_ready_dir / "memory_off_ablation.csv")

    labels = [f"{row['workload_motif']}\n{row['interface_class']}/{row['package_class']}" for row in interface_rows]
    avg_cost = [maybe_float(row["avg_cost"]) / 1e15 for row in interface_rows]
    memory_labels = [row["workload_motif"] for row in memory_rows]
    memory_bw = [maybe_int(row["memory_bandwidth_gbps"]) for row in memory_rows]

    fig, axes = plt.subplots(1, 2, figsize=(13, 4.5))
    axes[0].bar(labels, avg_cost, color=PALETTE["primary"])
    axes[0].set_ylabel("Avg cost (1e15 units)")
    axes[0].set_title("Fig. 5a Interface vs Package")
    axes[0].tick_params(axis="x", rotation=22)
    axes[0].grid(axis="y", alpha=0.25)

    bars = axes[1].bar(memory_labels, memory_bw, color=PALETTE["support"])
    axes[1].set_ylabel("Observed memory BW (Gbps)")
    axes[1].set_title("Fig. 5b Memory-Off Ablation")
    axes[1].grid(axis="y", alpha=0.25)
    scale = max(memory_bw or [1]) * 0.02
    for bar, row in zip(bars, memory_rows):
        axes[1].text(
            bar.get_x() + bar.get_width() / 2.0,
            bar.get_height() + scale,
            row["winner_changed_vs_joint"] if row.get("memory_off_supported") == "true" else row["status"],
            ha="center",
            va="bottom",
            fontsize=8,
            rotation=15,
        )

    fig.suptitle("PICASSO Bootstrap Fig. 5", fontsize=14, fontweight="bold")
    finalize(fig, repo_root, "fig5")


def render_fig6(plot_ready_dir: Path, repo_root: Path) -> None:
    phase_rows = read_csv(plot_ready_dir / "phase_boundary.csv")
    split_rows = read_csv(plot_ready_dir / "split_margin.csv")

    regime_colors = {
        "mono": PALETTE["mono"],
        "few": PALETTE["few"],
        "many": PALETTE["many"],
    }

    fig, axes = plt.subplots(1, 2, figsize=(13, 4.5))
    for regime in ["mono", "few", "many"]:
        regime_rows = [row for row in phase_rows if row["regime"] == regime]
        if not regime_rows:
            continue
        axes[0].scatter(
            [maybe_int(row["chiplet_count"]) for row in regime_rows],
            [maybe_int(row["tops_target_tops"]) for row in regime_rows],
            s=80,
            color=regime_colors[regime],
            label=regime,
        )
    axes[0].set_xlabel("Chiplet count")
    axes[0].set_ylabel("Target TOPS")
    axes[0].set_title("Fig. 6a Phase Boundary Map")
    axes[0].grid(alpha=0.25)
    axes[0].legend(frameon=False)

    split_labels = [row["design_id"] for row in split_rows]
    split_values = [maybe_float(row["edp_margin_pct"]) for row in split_rows]
    axes[1].bar(split_labels, split_values, color=PALETTE["neutral"])
    axes[1].set_ylabel("EDP margin (%)")
    axes[1].set_title("Fig. 6b Split Margin")
    axes[1].tick_params(axis="x", rotation=35)
    axes[1].grid(axis="y", alpha=0.25)

    fig.suptitle("PICASSO Bootstrap Fig. 6", fontsize=14, fontweight="bold")
    finalize(fig, repo_root, "fig6")


def render_fig7(plot_ready_dir: Path, repo_root: Path) -> None:
    pareto_rows = read_csv(plot_ready_dir / "pareto_points.csv")
    energy_rows = read_csv(plot_ready_dir / "energy_breakdown.csv")

    fig, axes = plt.subplots(1, 2, figsize=(13, 4.8))
    for row in pareto_rows:
        is_pareto = row["is_pareto_front"] == "true"
        cost = maybe_float(row["cost"]) / 1e15
        energy = maybe_float(row["energy"]) / 1e9
        axes[0].scatter(
            cost,
            energy,
            s=110 if is_pareto else 80,
            color=PALETTE["accent"] if is_pareto else PALETTE["primary"],
            alpha=0.9 if is_pareto else 0.75,
        )
        axes[0].text(cost, energy, row["design_id"].split("_")[-1], fontsize=8)
    axes[0].set_xlabel("Cost (1e15 units)")
    axes[0].set_ylabel("Energy (1e9 units)")
    axes[0].set_title("Fig. 7a Pareto Points")
    axes[0].grid(alpha=0.25)

    design_ids = sorted({row["design_id"] for row in energy_rows})
    components = sorted({row["component"] for row in energy_rows})
    bottoms = [0.0] * len(design_ids)
    color_cycle = ["#235789", "#c1292e", "#f1d302", "#7c3aed", "#0f766e", "#6b7280", "#d97706"]
    for idx, component in enumerate(components):
        values = []
        for design_id in design_ids:
            match = next(row for row in energy_rows if row["design_id"] == design_id and row["component"] == component)
            values.append(maybe_float(match["energy"]) / 1e9)
        axes[1].bar(design_ids, values, bottom=bottoms, label=component, color=color_cycle[idx % len(color_cycle)])
        bottoms = [bottom + value for bottom, value in zip(bottoms, values)]
    axes[1].set_ylabel("Energy (1e9 units)")
    axes[1].set_title("Fig. 7b Energy Breakdown")
    axes[1].tick_params(axis="x", rotation=35)
    axes[1].legend(frameon=False, fontsize=8, ncol=2)

    fig.suptitle("PICASSO Bootstrap Fig. 7", fontsize=14, fontweight="bold")
    finalize(fig, repo_root, "fig7")


def render_fig8(plot_ready_dir: Path, repo_root: Path) -> None:
    sensitivity_rows = read_csv(plot_ready_dir / "sensitivity_tags.csv")
    drift_rows = read_csv(plot_ready_dir / "boundary_drift.csv")

    cases = [row["capacity_case"] for row in sensitivity_rows]
    agreements = [maybe_float(row["winner_agreement"]) for row in sensitivity_rows]
    drift_labels = [row["metric"] for row in drift_rows]
    drift_values = [maybe_float(row["value"]) for row in drift_rows]

    fig, axes = plt.subplots(1, 2, figsize=(12.5, 4.5))
    bars = axes[0].bar(cases, agreements, color=PALETTE["primary"])
    axes[0].set_ylim(0.0, max([1.0] + agreements) * 1.1)
    axes[0].set_ylabel("Winner agreement")
    axes[0].set_title("Fig. 8a Router Sensitivity")
    axes[0].grid(axis="y", alpha=0.25)
    for bar, row in zip(bars, sensitivity_rows):
        axes[0].text(
            bar.get_x() + bar.get_width() / 2.0,
            bar.get_height() + 0.03,
            row["status"],
            ha="center",
            va="bottom",
            fontsize=8,
            rotation=12,
        )

    axes[1].bar(drift_labels, drift_values, color=PALETTE["accent"])
    axes[1].set_ylabel("Boundary drift")
    axes[1].set_title("Fig. 8b Closure Drift")
    axes[1].tick_params(axis="x", rotation=18)
    axes[1].grid(axis="y", alpha=0.25)
    for idx, row in enumerate(drift_rows):
        axes[1].text(idx, drift_values[idx] + 0.03, row["status"], ha="center", fontsize=8, rotation=12)

    fig.suptitle("PICASSO Bootstrap Fig. 8", fontsize=14, fontweight="bold")
    finalize(fig, repo_root, "fig8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Render bootstrap PICASSO figures from plot-ready CSVs")
    parser.add_argument("--figure", required=True, choices=sorted(FIGURE_FILENAMES), help="Figure key to render")
    parser.add_argument("--plot-ready-dir", required=True, help="Plot-ready run directory")
    parser.add_argument("--repo-root", default=None, help="Repo root, defaults to script parent")
    args = parser.parse_args()

    script_path = Path(__file__).resolve()
    repo_root = Path(args.repo_root).resolve() if args.repo_root else script_path.parent.parent.parent
    plot_ready_dir = Path(args.plot_ready_dir).resolve()

    if args.figure == "fig4":
        render_fig4(plot_ready_dir, repo_root)
    elif args.figure == "fig5":
        render_fig5(plot_ready_dir, repo_root)
    elif args.figure == "fig6":
        render_fig6(plot_ready_dir, repo_root)
    elif args.figure == "fig7":
        render_fig7(plot_ready_dir, repo_root)
    elif args.figure == "fig8":
        render_fig8(plot_ready_dir, repo_root)

    print(f"[PICASSO] Rendered {args.figure} from {plot_ready_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
