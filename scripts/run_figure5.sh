#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
latest_run="$(find "$repo_root/results/aggregated" -maxdepth 1 -mindepth 1 -type d -name '*paper_core_bootstrap*' | sort | tail -n 1)"

if [[ -z "${latest_run:-}" ]]; then
  echo "[PICASSO] ERROR: no aggregated paper-core run found" >&2
  exit 1
fi

run_name="$(basename "$latest_run")"

python3 "$repo_root/pyscripts/pipeline/aggregate_plot_ready.py" \
  --aggregated-run "$latest_run" \
  --output-dir "$repo_root/results/plot_ready/$run_name" \
  --manifest-output "$repo_root/results/figures/paper_figure_manifest.json"

python3 "$repo_root/pyscripts/analysis/render_bootstrap_figures.py" \
  --figure fig5 \
  --plot-ready-dir "$repo_root/results/plot_ready/$run_name" \
  --repo-root "$repo_root"

python3 "$repo_root/pyscripts/pipeline/refresh_paper_manifest.py" \
  --repo-root "$repo_root" \
  --output "$repo_root/results/figures/paper_figure_manifest.json"
