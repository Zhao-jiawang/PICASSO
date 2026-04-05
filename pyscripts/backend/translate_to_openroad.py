#!/usr/bin/env python3

import argparse
from pathlib import Path
from typing import Any, Dict, List

from translate_backend_common import dump_json, dump_text, write_backend_bundle


def build_payload(record: Dict[str, Any], cohort: str, aggregated_run: Path) -> Dict[str, Any]:
    die_area = record["die_area_breakdown"]
    chiplet_count = record["state_tuple"]["k"]["chiplet_count"]
    return {
        "design_id": record["design_id"],
        "cohort": cohort,
        "process_node": record["process_node"],
        "package_class": record["package_class"],
        "chiplet_count": chiplet_count,
        "chiplet_partition": record["state_tuple"]["k"]["chiplet_partition"],
        "compute_die_area_mm2": die_area["compute_die_area"],
        "io_die_area_mm2": die_area["io_die_area"],
        "total_die_area_mm2": die_area["total_die_area"],
        "floorplan_outline_hint_mm2": die_area["total_die_area"],
        "macro_policy": "bootstrap_placeholder",
        "clock_target": "bootstrap_placeholder",
        "pdn_template": "bootstrap_placeholder",
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
    dump_json(structured_dir / "floorplan_input.json", payload)
    files.append("floorplan_input.json")

    driver = """# PICASSO bootstrap OpenROAD driver
set input_json [file normalize "floorplan_input.json"]
set output_json [file normalize "openroad_report.json"]
puts "PICASSO bootstrap OpenROAD driver"
puts "Input bundle: $input_json"
puts "Expected next step: import floorplan_input.json, create die/core outlines, place macros, run global routing, and emit a structured report to $output_json."
exit
"""
    dump_text(structured_dir / "openroad_driver.tcl", driver)
    files.append("openroad_driver.tcl")

    run_script = """#!/usr/bin/env bash
set -euo pipefail
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
tool_bin="${OPENROAD_BIN:-openroad}"
if ! command -v "$tool_bin" >/dev/null 2>&1; then
  echo "[PICASSO] ERROR: OPENROAD_BIN/openroad not found" >&2
  exit 2
fi
"$tool_bin" -exit "$script_dir/openroad_driver.tcl" | tee "$script_dir/openroad.log"
"""
    dump_text(structured_dir / "run_openroad.sh", run_script, executable=True)
    files.append("run_openroad.sh")
    return files


def main() -> int:
    parser = argparse.ArgumentParser(description="Translate canonical design records into bootstrap OpenROAD inputs")
    parser.add_argument("--aggregated-run", required=True, help="Path to aggregated run directory")
    parser.add_argument("--sampled-points", required=True, help="Path to sampled_backend_points.json")
    parser.add_argument("--output-dir", required=True, help="Output directory for translated inputs")
    args = parser.parse_args()

    write_backend_bundle(
        aggregated_run=Path(args.aggregated_run).resolve(),
        sampled_points_path=Path(args.sampled_points).resolve(),
        output_dir=Path(args.output_dir).resolve(),
        backend_name="openroad",
        payload_builder=build_payload,
        artifact_builder=build_artifacts,
    )
    print(f"[PICASSO] Wrote bootstrap OpenROAD inputs into {Path(args.output_dir).resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
