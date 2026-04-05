#!/usr/bin/env python3

import json
from pathlib import Path
from typing import Any, Dict, List, Tuple


def load_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def dump_json(path: Path, payload: Dict[str, Any]) -> None:
    with path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, sort_keys=True)
        fh.write("\n")


def dump_text(path: Path, payload: str, executable: bool = False) -> None:
    with path.open("w", encoding="utf-8") as fh:
        fh.write(payload)
    if executable:
        path.chmod(path.stat().st_mode | 0o111)


def load_records_and_cohorts(aggregated_run: Path, sampled_points_path: Path) -> Tuple[List[Dict[str, Any]], Dict[str, str], Dict[str, List[str]]]:
    records = load_json(aggregated_run / "design_records.json")["records"]
    sampled_points = load_json(sampled_points_path)
    design_to_cohort: Dict[str, str] = {}
    for cohort, design_ids in sampled_points["cohorts"].items():
        for design_id in design_ids:
            design_to_cohort[design_id] = cohort
    return records, design_to_cohort, sampled_points["cohorts"]


def write_backend_bundle(
    aggregated_run: Path,
    sampled_points_path: Path,
    output_dir: Path,
    backend_name: str,
    payload_builder,
    artifact_builder=None,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    records, design_to_cohort, cohorts = load_records_and_cohorts(aggregated_run, sampled_points_path)
    repo_root = aggregated_run.parents[2]
    baselines = load_json(repo_root / "configs" / "baselines.json")
    generated_files: List[str] = []
    structured_design_dirs: List[str] = []

    for record in records:
        design_id = record["design_id"]
        cohort = design_to_cohort.get(design_id, "unsampled")
        baseline_mode = record["baseline_mode"]
        baseline_meta = baselines.get(baseline_mode, {})
        payload = payload_builder(record, cohort, aggregated_run)
        payload["backend_name"] = backend_name
        payload["baseline_family"] = baseline_meta.get("family")
        payload["baseline_mode"] = baseline_mode
        payload["baseline_ordering"] = baseline_meta.get("ordering")
        payload["execution_controls"] = record.get("execution_controls", {})
        payload["proposal_budget"] = record.get("proposal_budget")
        payload["source_run"] = str(aggregated_run)
        payload["status"] = "bootstrap_placeholder"
        payload["time_cap_minutes"] = record.get("time_cap_minutes")
        path = output_dir / f"{design_id}.json"
        dump_json(path, payload)
        generated_files.append(path.name)
        if artifact_builder is not None:
            structured_dir = output_dir / design_id
            structured_dir.mkdir(parents=True, exist_ok=True)
            artifact_files = artifact_builder(structured_dir, payload, record, cohort, aggregated_run)
            design_manifest = {
                "backend_name": backend_name,
                "design_id": design_id,
                "cohort": cohort,
                "baseline_mode": baseline_mode,
                "baseline_family": baseline_meta.get("family"),
                "baseline_ordering": baseline_meta.get("ordering"),
                "canonical_record_path": payload.get("canonical_record_path"),
                "files": sorted(artifact_files),
                "status": "bootstrap_command_skeleton",
            }
            dump_json(structured_dir / "manifest.json", design_manifest)
            structured_design_dirs.append(design_id)

    manifest = {
        "backend_name": backend_name,
        "source_run": str(aggregated_run),
        "sampled_points_file": str(sampled_points_path),
        "record_count": len(records),
        "cohorts": cohorts,
        "baseline_modes": sorted({record["baseline_mode"] for record in records}),
        "generated_files": generated_files,
        "structured_design_dirs": structured_design_dirs,
        "notes": [
            "These backend inputs are canonical-design-record projections.",
            "They are placeholder tool-facing bundles, not actual backend execution outputs.",
            "Each design directory contains normalized input files plus a runnable command skeleton for later backend integration."
        ],
        "status": "bootstrap_placeholder",
    }
    dump_json(output_dir / "manifest.json", manifest)
