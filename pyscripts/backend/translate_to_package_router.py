#!/usr/bin/env python3

import argparse
from pathlib import Path
from typing import Any, Dict, List

from translate_backend_common import dump_json, dump_text, write_backend_bundle


def build_payload(record: Dict[str, Any], cohort: str, aggregated_run: Path) -> Dict[str, Any]:
    interface = record["state_tuple"]["i"]
    return {
        "design_id": record["design_id"],
        "cohort": cohort,
        "package_class": record["package_class"],
        "interface_class": interface["interface_class"],
        "chiplet_count": record["state_tuple"]["k"]["chiplet_count"],
        "nop_bandwidth": interface["nop_bandwidth"],
        "route_budget_hint": "bootstrap_placeholder",
        "edge_capacity_hint": "bootstrap_placeholder",
        "traffic_matrix": record["traffic_matrix"],
        "per_edge_bandwidth": record["per_edge_bandwidth"],
        "closure_terms": record["closure_terms"],
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
    dump_json(structured_dir / "package_input.json", payload)
    files.append("package_input.json")

    run_script = """#!/usr/bin/env bash
set -euo pipefail
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
tool_bin="${PICASSO_PACKAGE_ROUTER_BIN:-semi_physical_package_router}"
if ! command -v "$tool_bin" >/dev/null 2>&1; then
  echo "[PICASSO] ERROR: PICASSO_PACKAGE_ROUTER_BIN/semi_physical_package_router not found" >&2
  exit 2
fi
"$tool_bin" --input "$script_dir/package_input.json" --output "$script_dir/package_report.json" | tee "$script_dir/package_router.log"
"""
    dump_text(structured_dir / "run_package_router.sh", run_script, executable=True)
    files.append("run_package_router.sh")
    return files


def main() -> int:
    parser = argparse.ArgumentParser(description="Translate canonical design records into bootstrap package-router inputs")
    parser.add_argument("--aggregated-run", required=True, help="Path to aggregated run directory")
    parser.add_argument("--sampled-points", required=True, help="Path to sampled_backend_points.json")
    parser.add_argument("--output-dir", required=True, help="Output directory for translated inputs")
    args = parser.parse_args()

    write_backend_bundle(
        aggregated_run=Path(args.aggregated_run).resolve(),
        sampled_points_path=Path(args.sampled_points).resolve(),
        output_dir=Path(args.output_dir).resolve(),
        backend_name="package_router",
        payload_builder=build_payload,
        artifact_builder=build_artifacts,
    )
    print(f"[PICASSO] Wrote bootstrap package-router inputs into {Path(args.output_dir).resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
