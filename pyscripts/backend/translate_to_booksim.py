#!/usr/bin/env python3

import argparse
from pathlib import Path
from typing import Any, Dict, List

from translate_backend_common import dump_json, dump_text, write_backend_bundle


def build_payload(record: Dict[str, Any], cohort: str, aggregated_run: Path) -> Dict[str, Any]:
    memory = record["memory_attachment"]
    interface = record["state_tuple"]["i"]
    return {
        "design_id": record["design_id"],
        "cohort": cohort,
        "network_mode": "nop",
        "package_class": record["package_class"],
        "interface_class": interface["interface_class"],
        "chiplet_count": record["state_tuple"]["k"]["chiplet_count"],
        "nop_bandwidth": interface["nop_bandwidth"],
        "noc_bandwidth": memory["noc_bandwidth"],
        "latency_cycles": record["surrogate_metrics"]["latency_cycles"],
        "traffic_matrix": record["traffic_matrix"],
        "routing_policy": "bootstrap_placeholder",
        "topology": "bootstrap_placeholder",
        "canonical_record_path": str(aggregated_run / "design_records" / f"{record['design_id']}.json"),
    }


def build_artifacts(
    structured_dir: Path,
    payload: Dict[str, Any],
    record: Dict[str, Any],
    cohort: str,
    aggregated_run: Path,
) -> List[str]:
    files: List[str] = []
    dump_json(structured_dir / "booksim_config.json", payload)
    files.append("booksim_config.json")

    run_script = """#!/usr/bin/env bash
set -euo pipefail
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
tool_bin="${BOOKSIM_BIN:-booksim}"
if ! command -v "$tool_bin" >/dev/null 2>&1; then
  echo "[PICASSO] ERROR: BOOKSIM_BIN/booksim not found" >&2
  exit 2
fi
"$tool_bin" "$script_dir/booksim_config.json" | tee "$script_dir/booksim.log"
"""
    dump_text(structured_dir / "run_booksim.sh", run_script, executable=True)
    files.append("run_booksim.sh")
    return files


def main() -> int:
    parser = argparse.ArgumentParser(description="Translate canonical design records into bootstrap BookSim inputs")
    parser.add_argument("--aggregated-run", required=True, help="Path to aggregated run directory")
    parser.add_argument("--sampled-points", required=True, help="Path to sampled_backend_points.json")
    parser.add_argument("--output-dir", required=True, help="Output directory for translated inputs")
    args = parser.parse_args()

    write_backend_bundle(
        aggregated_run=Path(args.aggregated_run).resolve(),
        sampled_points_path=Path(args.sampled_points).resolve(),
        output_dir=Path(args.output_dir).resolve(),
        backend_name="booksim",
        payload_builder=build_payload,
        artifact_builder=build_artifacts,
    )
    print(f"[PICASSO] Wrote bootstrap BookSim inputs into {Path(args.output_dir).resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
