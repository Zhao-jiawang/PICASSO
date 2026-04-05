#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

config=""
run_name=""
jobs="${PICASSO_JOBS:-}"

usage() {
  cat <<'EOF'
Usage: run_points_parallel.sh --config <config.json> [--run-name <name>] [--jobs <count>]

Runs a PICASSO point experiment in parallel shards by invoking picasso_runner.py
with disjoint point ranges and --skip-postprocess, then performs one final reuse
pass to aggregate the completed raw points into a single run bundle.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --config)
      config="$2"
      shift 2
      ;;
    --run-name)
      run_name="$2"
      shift 2
      ;;
    --jobs)
      jobs="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "[PICASSO] ERROR: unknown argument '$1'" >&2
      usage >&2
      exit 1
      ;;
  esac
done

if [[ -z "$config" ]]; then
  echo "[PICASSO] ERROR: --config is required" >&2
  usage >&2
  exit 1
fi

config_path="$(python3 - "$repo_root" "$config" <<'PY'
from pathlib import Path
import sys
repo_root = Path(sys.argv[1]).resolve()
config = Path(sys.argv[2])
print((config if config.is_absolute() else (repo_root / config)).resolve())
PY
)"

if [[ ! -f "$config_path" ]]; then
  echo "[PICASSO] ERROR: config not found: $config_path" >&2
  exit 1
fi

if [[ -z "$jobs" ]]; then
  jobs="$(nproc 2>/dev/null || getconf _NPROCESSORS_ONLN || echo 1)"
fi

readarray -t config_meta < <(python3 - "$repo_root" "$config_path" <<'PY'
from pathlib import Path
import sys

repo_root = Path(sys.argv[1]).resolve()
config_path = Path(sys.argv[2]).resolve()

if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from picasso.pipeline import expand_points, load_json, validate_config_shape

config = load_json(config_path)
validate_config_shape(config)
expanded = expand_points(config, repo_root)
print(config["experiment_name"])
print(len(expanded))
PY
)

experiment_name="${config_meta[0]}"
total_points="${config_meta[1]}"

if [[ -z "$run_name" ]]; then
  timestamp="$(date +%Y%m%d_%H%M%S)"
  run_name="${timestamp}_${experiment_name}"
fi

if ! [[ "$jobs" =~ ^[0-9]+$ ]] || (( jobs < 1 )); then
  echo "[PICASSO] ERROR: invalid --jobs value '$jobs'" >&2
  exit 1
fi

if ! [[ "$total_points" =~ ^[0-9]+$ ]] || (( total_points < 1 )); then
  echo "[PICASSO] ERROR: no points expanded from $config_path" >&2
  exit 1
fi

if (( jobs > total_points )); then
  jobs="$total_points"
fi

log_dir="$repo_root/results/logs/$run_name"
mkdir -p "$log_dir"

shard_size=$(( (total_points + jobs - 1) / jobs ))
pids=()
ranges=()
logs=()

echo "[PICASSO] Parallel point run"
echo "[PICASSO] config=$config_path"
echo "[PICASSO] run_name=$run_name"
echo "[PICASSO] jobs=$jobs total_points=$total_points shard_size=$shard_size"

for (( shard_index=0; shard_index<jobs; shard_index++ )); do
  start=$(( shard_index * shard_size + 1 ))
  end=$(( start + shard_size - 1 ))
  if (( start > total_points )); then
    break
  fi
  if (( end > total_points )); then
    end="$total_points"
  fi
  shard_log="$log_dir/shard_${start}_${end}.log"
  echo "[PICASSO] Launch shard ${start}-${end} -> $shard_log"
  python3 "$repo_root/pyscripts/pipeline/picasso_runner.py" \
    --config "$config_path" \
    --run-name "$run_name" \
    --point-start "$start" \
    --point-end "$end" \
    --skip-postprocess \
    >"$shard_log" 2>&1 &
  pids+=("$!")
  ranges+=("${start}-${end}")
  logs+=("$shard_log")
done

failures=0
for i in "${!pids[@]}"; do
  pid="${pids[$i]}"
  range="${ranges[$i]}"
  shard_log="${logs[$i]}"
  if wait "$pid"; then
    echo "[PICASSO] Shard ${range} completed"
  else
    echo "[PICASSO] ERROR: shard ${range} failed; see $shard_log" >&2
    failures=1
  fi
done

if (( failures != 0 )); then
  exit 1
fi

echo "[PICASSO] Final reuse/postprocess pass for $run_name"
python3 "$repo_root/pyscripts/pipeline/picasso_runner.py" \
  --config "$config_path" \
  --run-name "$run_name"
