#!/usr/bin/env python3

from __future__ import annotations

import argparse
import datetime as dt
from pathlib import Path
import subprocess
import sys

# Make top-level package import robust even when this script is invoked via absolute path.
SCRIPT_PATH = Path(__file__).resolve()
REPO_ROOT = SCRIPT_PATH.parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from picasso.pipeline import (
    build_config_snapshot,
    build_run_manifest,
    dump_json,
    expand_points,
    load_json,
    maybe_float,
    maybe_int,
    normalize_point,
    run_point,
    summarize_best_by_baseline,
    validate_config_shape,
    write_best_arch,
    write_csv,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Unified PICASSO Python-native runner")
    parser.add_argument("--config", required=True, help="Path to a JSON config file")
    parser.add_argument("--repo-root", default=None, help="Repo root, defaults to script parent")
    parser.add_argument("--run-name", default=None, help="Reuse or force a specific run bundle name")
    parser.add_argument("--point-start", type=int, default=None, help="1-based inclusive start index for a point shard")
    parser.add_argument("--point-end", type=int, default=None, help="1-based inclusive end index for a point shard")
    parser.add_argument("--skip-postprocess", action="store_true", help="Run assigned points only and skip aggregation/export steps")
    args = parser.parse_args()

    script_path = SCRIPT_PATH
    repo_root = Path(args.repo_root).resolve() if args.repo_root else REPO_ROOT
    config_path = Path(args.config).resolve()
    config = load_json(config_path)

    validate_config_shape(config)

    config_name = str(config["experiment_name"])
    tier = str(config["tier"])
    if args.run_name:
        run_name = str(args.run_name)
        timestamp = run_name[:15] if len(run_name) >= 15 else dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    else:
        timestamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        run_name = f"{timestamp}_{config_name}"

    results_root = repo_root / "results"
    raw_dir = results_root / "raw" / run_name
    aggregated_dir = results_root / "aggregated" / run_name
    plot_ready_dir = results_root / "plot_ready" / run_name
    figures_dir = results_root / "figures"
    for directory in [raw_dir, aggregated_dir, plot_ready_dir, figures_dir]:
        directory.mkdir(parents=True, exist_ok=True)

    expanded_points = expand_points(config, repo_root)
    normalized_points = [normalize_point(repo_root, point, point_index) for point_index, point in enumerate(expanded_points, start=1)]
    point_start = args.point_start or 1
    point_end = args.point_end or len(normalized_points)
    if point_start < 1 or point_end < point_start or point_end > len(normalized_points):
        raise ValueError(f"Invalid point shard range: start={point_start}, end={point_end}, total={len(normalized_points)}")
    selected_points = normalized_points[point_start - 1 : point_end]

    config_snapshot = build_config_snapshot(
        run_name=run_name,
        config_path=config_path,
        repo_root=repo_root,
        config=config,
        timestamp=timestamp,
        normalized_points=selected_points,
        command=[
            sys.executable,
            str(script_path),
            "--config",
            str(config_path),
            *([] if args.repo_root is None else ["--repo-root", str(repo_root)]),
            *([] if args.run_name is None else ["--run-name", str(run_name)]),
            *([] if args.point_start is None else ["--point-start", str(point_start)]),
            *([] if args.point_end is None else ["--point-end", str(point_end)]),
            *(["--skip-postprocess"] if args.skip_postprocess else []),
        ],
    )
    dump_json(raw_dir / "config_snapshot.json", config_snapshot)

    rows = []
    for point_index, point in enumerate(selected_points, start=point_start):
        rows.append(run_point(repo_root=repo_root, config_name=config_name, tier=tier, raw_dir=raw_dir, point=point, point_index=point_index))

    if args.skip_postprocess:
        print(f"[PICASSO] Completed shard run: {run_name} points {point_start}-{point_end}")
        return 0

    aggregated_csv = aggregated_dir / "result.csv"
    write_csv(aggregated_csv, rows)
    best_summary = write_best_arch(aggregated_dir / "best_arch.txt", rows)
    best_by_baseline = summarize_best_by_baseline(rows, maybe_int=maybe_int, maybe_float=maybe_float)

    manifest = build_run_manifest(
        run_name=run_name,
        tier=tier,
        config_path=config_path,
        repo_root=repo_root,
        raw_dir=raw_dir,
        aggregated_csv=aggregated_csv,
        rows=rows,
        best_summary=best_summary,
        best_by_baseline=best_by_baseline,
        maybe_int=maybe_int,
        maybe_float=maybe_float,
    )
    dump_json(aggregated_dir / "manifest.json", manifest)
    dump_json(plot_ready_dir / "manifest.json", manifest)

    subprocess.run(
        [
            sys.executable,
            str(repo_root / "pyscripts" / "analysis" / "export_design_records.py"),
            "--aggregated-csv",
            str(aggregated_csv),
            "--output-dir",
            str(aggregated_dir / "design_records"),
        ],
        cwd=repo_root,
        check=True,
    )
    subprocess.run(
        [
            sys.executable,
            str(repo_root / "pyscripts" / "analysis" / "export_model_parameterization.py"),
            "--output",
            str(results_root / "aggregated" / "model_parameterization.json"),
        ],
        cwd=repo_root,
        check=True,
    )
    subprocess.run(
        [
            sys.executable,
            str(repo_root / "pyscripts" / "pipeline" / "aggregate_plot_ready.py"),
            "--aggregated-run",
            str(aggregated_dir),
            "--output-dir",
            str(plot_ready_dir),
            "--manifest-output",
            str(figures_dir / "paper_figure_manifest.json"),
        ],
        cwd=repo_root,
        check=True,
    )
    subprocess.run(
        [
            sys.executable,
            str(repo_root / "pyscripts" / "pipeline" / "refresh_paper_manifest.py"),
            "--repo-root",
            str(repo_root),
            "--output",
            str(figures_dir / "paper_figure_manifest.json"),
        ],
        cwd=repo_root,
        check=True,
    )

    print(f"[PICASSO] Completed run: {run_name}")
    print(f"[PICASSO] Raw logs: {raw_dir.relative_to(repo_root)}")
    print(f"[PICASSO] Aggregated CSV: {aggregated_csv.relative_to(repo_root)}")
    print(f"[PICASSO] Best design: {best_summary['design_id']} ({best_summary['cost']:.5f})")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"[PICASSO] ERROR: {exc}", file=sys.stderr)
        raise
