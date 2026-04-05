#!/usr/bin/env python3

import argparse
from pathlib import Path
from typing import Any, Dict, List

from translate_backend_common import dump_text, write_backend_bundle


def derive_channels(memory_bw_gbps: int) -> int:
    if memory_bw_gbps >= 512:
        return 16
    if memory_bw_gbps >= 256:
        return 8
    if memory_bw_gbps >= 128:
        return 4
    return 2


def build_payload(record: Dict[str, Any], cohort: str, aggregated_run: Path) -> Dict[str, Any]:
    memory = record["memory_attachment"]
    memory_bw_gbps = int(memory["memory_bandwidth_gbps"])
    return {
        "design_id": record["design_id"],
        "cohort": cohort,
        "memory_class": memory["memory_class"],
        "memory_bandwidth_gbps": memory_bw_gbps,
        "channel_count_hint": derive_channels(memory_bw_gbps),
        "workload": record["workload"],
        "workload_motif": record.get("workload_motif"),
        "trace_id": record["trace_id"],
        "attachment_style": "bootstrap_placeholder",
        "dram_trace_source": "bootstrap_placeholder",
        "canonical_record_path": str(aggregated_run / "design_records" / f"{record['design_id']}.json"),
    }


def yaml_scalar(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "null"
    if isinstance(value, (int, float)):
        return str(value)
    escaped = str(value).replace("\"", "\\\"")
    return f"\"{escaped}\""


def render_yaml_block(value: Any, indent: int = 0) -> List[str]:
    prefix = " " * indent
    if isinstance(value, dict):
        lines: List[str] = []
        for key, nested in value.items():
            if isinstance(nested, (dict, list)):
                lines.append(f"{prefix}{key}:")
                lines.extend(render_yaml_block(nested, indent + 2))
            else:
                lines.append(f"{prefix}{key}: {yaml_scalar(nested)}")
        return lines
    if isinstance(value, list):
        lines = []
        for item in value:
            if isinstance(item, (dict, list)):
                lines.append(f"{prefix}-")
                lines.extend(render_yaml_block(item, indent + 2))
            else:
                lines.append(f"{prefix}- {yaml_scalar(item)}")
        return lines
    return [f"{prefix}{yaml_scalar(value)}"]


def render_yaml(payload: Dict[str, Any]) -> str:
    return "\n".join(render_yaml_block(payload)) + "\n"


def build_artifacts(
    structured_dir: Path,
    payload: Dict[str, Any],
    record: Dict[str, Any],
    cohort: str,
    aggregated_run: Path,
) -> List[str]:
    files: List[str] = []
    dump_text(structured_dir / "ramulator_config.yaml", render_yaml(payload))
    files.append("ramulator_config.yaml")

    run_script = """#!/usr/bin/env bash
set -euo pipefail
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
tool_bin="${RAMULATOR_BIN:-ramulator2}"
if ! command -v "$tool_bin" >/dev/null 2>&1; then
  echo "[PICASSO] ERROR: RAMULATOR_BIN/ramulator2 not found" >&2
  exit 2
fi
"$tool_bin" -f "$script_dir/ramulator_config.yaml" | tee "$script_dir/ramulator.log"
"""
    dump_text(structured_dir / "run_ramulator.sh", run_script, executable=True)
    files.append("run_ramulator.sh")
    return files


def main() -> int:
    parser = argparse.ArgumentParser(description="Translate canonical design records into bootstrap Ramulator inputs")
    parser.add_argument("--aggregated-run", required=True, help="Path to aggregated run directory")
    parser.add_argument("--sampled-points", required=True, help="Path to sampled_backend_points.json")
    parser.add_argument("--output-dir", required=True, help="Output directory for translated inputs")
    args = parser.parse_args()

    write_backend_bundle(
        aggregated_run=Path(args.aggregated_run).resolve(),
        sampled_points_path=Path(args.sampled_points).resolve(),
        output_dir=Path(args.output_dir).resolve(),
        backend_name="ramulator",
        payload_builder=build_payload,
        artifact_builder=build_artifacts,
    )
    print(f"[PICASSO] Wrote bootstrap Ramulator inputs into {Path(args.output_dir).resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
