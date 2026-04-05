#!/usr/bin/env python3

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Set


def load_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def dump_json(path: Path, payload: Dict[str, Any]) -> None:
    with path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, sort_keys=True)
        fh.write("\n")


def edp(record: Dict[str, Any]) -> float:
    return float(record["surrogate_metrics"]["edp"])


def chiplet_count(record: Dict[str, Any]) -> int:
    return int(record["state_tuple"]["k"]["chiplet_count"])


def boundary_score(record: Dict[str, Any]) -> float:
    terms = record.get("closure_terms", {})
    return min(abs(float(terms.get("M1", 0.0))), abs(float(terms.get("M2", 0.0))))


def legality_pressure(record: Dict[str, Any]) -> float:
    details = record.get("legality_details", {})
    margins = [
        abs(float(record.get("closure_terms", {}).get("M1", 0.0))),
        abs(float(record.get("closure_terms", {}).get("M2", 0.0))),
        abs(float(details.get("io_competition_score", 0.0) - 1.0)),
        abs(float(details.get("channel_count_available", 0.0) - details.get("channel_count_required", 0.0))),
    ]
    return min(margins)


def ordered_records(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return sorted(records, key=lambda record: (edp(record), record["design_id"]))


def add_unique(target: List[str], candidates: List[str], seen: Set[str], limit: int) -> None:
    for design_id in candidates:
        if design_id in seen:
            continue
        target.append(design_id)
        seen.add(design_id)
        if len(target) >= limit:
            return


def main() -> int:
    parser = argparse.ArgumentParser(description="Sample bootstrap backend points from canonical design records")
    parser.add_argument("--aggregated-run", required=True, help="Path to an aggregated run directory")
    parser.add_argument("--output-dir", required=True, help="Directory to store sampled backend cohorts")
    args = parser.parse_args()

    aggregated_run = Path(args.aggregated_run).resolve()
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    design_records = load_json(aggregated_run / "design_records.json")["records"]
    if not design_records:
        raise ValueError("No design records found for backend sampling")

    cohorts: Dict[str, List[str]] = {
        "winner": [],
        "boundary": [],
        "near_legality": [],
        "disagreement": [],
        "control": [],
    }
    selected: Set[str] = set()

    baseline_groups: Dict[str, List[Dict[str, Any]]] = {}
    for record in design_records:
        baseline_groups.setdefault(record["baseline_mode"], []).append(record)

    winner_summary: Dict[str, Dict[str, Any]] = {}
    winner_candidates: List[str] = []
    disagreement_candidates: List[str] = []
    for baseline_mode in sorted(baseline_groups):
        ranked = ordered_records(baseline_groups[baseline_mode])
        winner_summary[baseline_mode] = {
            "count": len(ranked),
            "top1": ranked[0]["design_id"],
            "top3": [record["design_id"] for record in ranked[:3]],
        }
        winner_candidates.append(ranked[0]["design_id"])
        if baseline_mode != "Joint":
            disagreement_candidates.append(ranked[0]["design_id"])

    boundary_candidates = [
        record["design_id"]
        for record in sorted(
            design_records,
            key=lambda record: (boundary_score(record), edp(record), record["design_id"]),
        )
    ]
    near_legality_candidates = [
        record["design_id"]
        for record in sorted(
            design_records,
            key=lambda record: (
                0 if record.get("legality_flags", {}).get("overall") != "legal" else 1,
                legality_pressure(record),
                edp(record),
                record["design_id"],
            ),
        )
    ]

    for record in ordered_records(design_records):
        if record["baseline_mode"] == "Memory-off":
            disagreement_candidates.append(record["design_id"])
        if 6 <= chiplet_count(record) <= 8:
            disagreement_candidates.append(record["design_id"])
        if record.get("workload_motif") in {"mixtral_moe_trace", "megatron_collective_trace"}:
            disagreement_candidates.append(record["design_id"])

    total_records = len(design_records)
    target_boundary = max(1, min(6, total_records // 6))
    target_near_legality = max(1, min(6, total_records // 6))
    target_disagreement = max(1, min(6, total_records // 6))

    add_unique(cohorts["winner"], winner_candidates, selected, len(winner_candidates))
    add_unique(cohorts["boundary"], boundary_candidates, selected, target_boundary)
    add_unique(cohorts["near_legality"], near_legality_candidates, selected, target_near_legality)
    add_unique(cohorts["disagreement"], disagreement_candidates, selected, target_disagreement)

    legal_remaining = [
        record["design_id"]
        for record in ordered_records(design_records)
        if record["design_id"] not in selected and record.get("legality_flags", {}).get("overall") == "legal"
    ]
    add_unique(cohorts["control"], legal_remaining, selected, min(20, len(legal_remaining)))

    payload = {
        "status": "bootstrap_observed_sampler",
        "source_run": str(aggregated_run),
        "record_count": len(design_records),
        "cohorts": cohorts,
        "winner_summary_by_baseline": winner_summary,
        "notes": [
            "This sampler is deterministic but metric-driven over canonical design records.",
            "Winner uses top-1 per baseline, boundary uses smallest |M1|/|M2|, near_legality uses legality-pressure ordering, and control draws from remaining legal points."
        ],
    }
    dump_json(output_dir / "sampled_backend_points.json", payload)
    print(f"[PICASSO] Sampled backend points into {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
