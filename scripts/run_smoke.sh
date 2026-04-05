#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
runner_args=(
  --config "$repo_root/configs/paper_smoke.json"
)
if [[ -n "${PICASSO_RUN_NAME:-}" ]]; then
  runner_args+=(--run-name "$PICASSO_RUN_NAME")
fi
python3 "$repo_root/pyscripts/pipeline/picasso_runner.py" "${runner_args[@]}"
