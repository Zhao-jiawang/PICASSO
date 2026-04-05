#!/usr/bin/env python3

import argparse
from pathlib import Path

from aggregate_plot_ready import load_json, write_illegal_breakdown


def main() -> int:
    parser = argparse.ArgumentParser(description="Export bootstrap illegal breakdown table")
    parser.add_argument("--aggregated-run", required=True, help="Path to an aggregated run directory")
    parser.add_argument("--output-dir", required=True, help="Directory to store illegal_breakdown.csv")
    args = parser.parse_args()

    aggregated_run = Path(args.aggregated_run).resolve()
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    records = load_json(aggregated_run / "design_records.json")["records"]
    write_illegal_breakdown(records, output_dir)
    print(f"[PICASSO] Wrote illegal breakdown into {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
