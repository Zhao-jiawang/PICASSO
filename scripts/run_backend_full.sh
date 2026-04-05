#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
latest_run="$(find "$repo_root/results/aggregated" -maxdepth 1 -mindepth 1 -type d -name '*paper_full_bootstrap*' | sort | tail -n 1)"

if [[ -z "${latest_run:-}" ]]; then
  echo "[PICASSO] ERROR: no aggregated paper-full run found" >&2
  exit 1
fi

run_name="$(basename "$latest_run")"
output_dir="$repo_root/results/backend_aggregated/$run_name"
floorplan_dir="$repo_root/results/backend/floorplan/$run_name"
package_dir="$repo_root/results/backend/package/$run_name"
nop_dir="$repo_root/results/backend/nop/$run_name"
memory_dir="$repo_root/results/backend/memory/$run_name"
mkdir -p "$output_dir"

python3 "$repo_root/pyscripts/backend/sample_backend_points.py" \
  --aggregated-run "$latest_run" \
  --output-dir "$output_dir"

python3 "$repo_root/pyscripts/backend/translate_to_openroad.py" \
  --aggregated-run "$latest_run" \
  --sampled-points "$output_dir/sampled_backend_points.json" \
  --output-dir "$floorplan_dir"

python3 "$repo_root/pyscripts/backend/translate_to_package_router.py" \
  --aggregated-run "$latest_run" \
  --sampled-points "$output_dir/sampled_backend_points.json" \
  --output-dir "$package_dir"

python3 "$repo_root/pyscripts/backend/translate_to_booksim.py" \
  --aggregated-run "$latest_run" \
  --sampled-points "$output_dir/sampled_backend_points.json" \
  --output-dir "$nop_dir"

python3 "$repo_root/pyscripts/backend/translate_to_ramulator.py" \
  --aggregated-run "$latest_run" \
  --sampled-points "$output_dir/sampled_backend_points.json" \
  --output-dir "$memory_dir"

python3 "$repo_root/pyscripts/backend/aggregate_backend_closure.py" \
  --aggregated-run "$latest_run" \
  --sampled-points "$output_dir/sampled_backend_points.json" \
  --output-dir "$output_dir"
