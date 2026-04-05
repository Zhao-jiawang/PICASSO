#!/usr/bin/env python3

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List


def dump_json(path: Path, payload: Dict[str, Any]) -> None:
    with path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, sort_keys=True)
        fh.write("\n")


def build_moe_trace() -> Dict[str, Any]:
    experts = [f"expert_{idx}" for idx in range(8)]
    tokens = []
    dispatch_pattern = [
        [0, 1],
        [0, 2],
        [1, 2],
        [0, 3],
        [3, 4],
        [0, 4],
        [5, 6],
        [0, 7],
    ]
    for token_id in range(64):
        pair = dispatch_pattern[token_id % len(dispatch_pattern)]
        tokens.append(
            {
                "token_id": token_id,
                "top2_experts": [experts[pair[0]], experts[pair[1]]],
                "locality_hit": token_id % 3 == 0,
            }
        )

    return {
        "trace_id": "mixtral_moe_trace",
        "trace_type": "mixtral_moe_trace",
        "status": "generated_trace",
        "required_properties": {
            "expert_count": 8,
            "top_k": 2,
            "load_imbalance_factor": 1.35,
            "locality_probability": 0.34
        },
        "experts": experts,
        "tokens": tokens,
        "notes": [
            "This is the deterministic Mixtral-style MoE trace artifact used by the PICASSO workload layer.",
            "Its metadata is consumed by the Python-native workload resolver and evaluator."
        ]
    }


def build_collective_trace() -> Dict[str, Any]:
    phases: List[Dict[str, Any]] = []
    for step in range(6):
        phases.append(
            {
                "phase_id": step,
                "collective": "all_reduce" if step % 2 == 0 else "all_gather",
                "bucket_size_mb": 128,
                "participant_group": "training_collective_heavy_pod",
                "route_pressure_tag": "high" if step in (1, 2, 4) else "medium",
                "memory_attachment_pressure": "high" if step in (2, 5) else "medium"
            }
        )

    return {
        "trace_id": "megatron_collective_trace",
        "trace_type": "megatron_collective_trace",
        "status": "generated_trace",
        "required_properties": {
            "bucket_size_mb": 128,
            "phases": ["all_reduce", "all_gather"]
        },
        "phases": phases,
        "notes": [
            "This is the deterministic Megatron-style collective trace artifact used by the PICASSO workload layer.",
            "Its metadata is consumed by the Python-native workload resolver and evaluator."
        ]
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate PICASSO workload traces")
    parser.add_argument("--repo-root", default=None, help="Repo root, defaults to script parent")
    args = parser.parse_args()

    script_path = Path(__file__).resolve()
    repo_root = Path(args.repo_root).resolve() if args.repo_root else script_path.parent.parent.parent
    output_dir = repo_root / "workloads" / "generated"
    output_dir.mkdir(parents=True, exist_ok=True)

    moe_trace = build_moe_trace()
    collective_trace = build_collective_trace()

    moe_path = output_dir / "mixtral_moe_trace.json"
    collective_path = output_dir / "megatron_collective_trace.json"
    dump_json(moe_path, moe_trace)
    dump_json(collective_path, collective_trace)

    manifest = {
        "generated_files": [
            str(moe_path.relative_to(repo_root)),
            str(collective_path.relative_to(repo_root))
        ],
        "status": "generated_trace_manifest"
    }
    dump_json(output_dir / "manifest.json", manifest)
    print(f"[PICASSO] Generated workload traces in {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
