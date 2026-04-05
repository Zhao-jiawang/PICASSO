#!/usr/bin/env python3

import argparse
from pathlib import Path

from aggregate_plot_ready import read_csv, write_weight_shift_summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Export bootstrap weight-shift summary table")
    parser.add_argument("--aggregated-run", required=True, help="Path to an aggregated run directory")
    parser.add_argument("--output-dir", required=True, help="Directory to store weight_shift_summary.csv")
    args = parser.parse_args()

    aggregated_run = Path(args.aggregated_run).resolve()
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    rows = read_csv(aggregated_run / "result.csv")
    write_weight_shift_summary(rows, output_dir)
    print(f"[PICASSO] Wrote weight-shift summary into {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
