#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
exec "$repo_root/scripts/run_points_parallel.sh" --config "$repo_root/configs/paper_full.json" "$@"
