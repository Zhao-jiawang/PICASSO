from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from picasso.workloads import resolve_workload

from .schema import require_keys


NETWORK_TO_ID = {
    "darknet19": 0,
    "vgg19": 1,
    "resnet50": 2,
    "googlenet": 3,
    "resnet101": 4,
    "densenet": 5,
    "ires": 6,
    "gnmt": 7,
    "lstm": 8,
    "zfnet": 9,
    "transformer": 10,
    "transformer_cell": 11,
    "pnasnet": 12,
    "resnext50": 13,
    "resnet152": 14,
    "bert_block": 15,
    "gpt2_prefill_block": 16,
    "gpt2_decode_block": 17,
}

MICROARCH_TO_ID = {
    "polar": 0,
    "eyeriss": 1,
}

OBJECTIVE_TO_ID = {
    "latency": 0,
    "edp": 1,
    "energy": -1,
}


def load_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def load_baseline_registry(repo_root: Path) -> Dict[str, Any]:
    return load_json(repo_root / "configs" / "baselines.json")


def maybe_int(value: Any) -> int | None:
    if value in ("", None):
        return None
    return int(value)


def maybe_float(value: Any) -> float | None:
    if value in ("", None):
        return None
    return float(value)

def normalize_modes(value: Any, context: str) -> List[str]:
    if value is None:
        return []
    if isinstance(value, list):
        modes = [str(item) for item in value]
    else:
        modes = [str(value)]
    if not modes:
        raise ValueError(f"{context} must not be empty")
    return modes


def expand_points(config: Dict[str, Any], repo_root: Path) -> List[Dict[str, Any]]:
    baseline_registry = load_baseline_registry(repo_root)
    valid_modes = set(baseline_registry)
    config_modes = normalize_modes(config.get("baseline_modes"), "config.baseline_modes")
    default_mode = str(config.get("baseline_mode", "Joint"))
    default_modes = config_modes or [default_mode]
    default_proposal_budget = maybe_int(config.get("proposal_budget"))
    default_time_cap_minutes = maybe_float(config.get("time_cap_minutes"))

    expanded: List[Dict[str, Any]] = []
    for point_index, point in enumerate(config["points"], start=1):
        point_modes = normalize_modes(
            point.get("baseline_modes", point.get("baseline_mode")),
            f"point[{point_index}].baseline_modes",
        )
        point_modes = point_modes or default_modes
        for baseline_mode in point_modes:
            if baseline_mode not in valid_modes:
                raise ValueError(
                    f"Unsupported baseline_mode '{baseline_mode}' in point[{point_index}]. "
                    f"Valid modes: {', '.join(sorted(valid_modes))}"
                )
            expanded_point = dict(point)
            expanded_point["baseline_mode"] = baseline_mode
            expanded_point["proposal_budget"] = maybe_int(point.get("proposal_budget", default_proposal_budget))
            expanded_point["time_cap_minutes"] = maybe_float(point.get("time_cap_minutes", default_time_cap_minutes))
            expanded.append(expanded_point)
    return expanded


def normalize_point(repo_root: Path, point: Dict[str, Any], point_index: int) -> Dict[str, Any]:
    point = resolve_workload(repo_root, point)
    require_keys(
        point,
        [
            "design_name",
            "process_node",
            "microarch",
            "workload",
            "core_array",
            "stride",
            "batch_size",
            "search_rounds",
            "objective",
            "chiplet_partition",
            "package_class",
            "interface_class",
            "memory_class",
            "memory_bandwidth_gbps",
            "noc_bandwidth",
            "nop_bandwidth",
            "macs_per_core",
            "ul3_kb",
            "tops_target_tops",
            "seed",
        ],
        f"point[{point_index}]",
    )

    core_array = point["core_array"]
    chiplet_partition = point["chiplet_partition"]
    require_keys(core_array, ["x", "y"], f"point[{point_index}].core_array")
    require_keys(chiplet_partition, ["x", "y"], f"point[{point_index}].chiplet_partition")

    workload = point["workload"]
    executable_workload = str(point.get("workload_exec_binding", workload))
    if executable_workload not in NETWORK_TO_ID:
        raise ValueError(f"Unsupported workload '{workload}' in point[{point_index}]")
    microarch = point["microarch"]
    if microarch not in MICROARCH_TO_ID:
        raise ValueError(f"Unsupported microarch '{microarch}' in point[{point_index}]")
    objective = point["objective"]
    if objective not in OBJECTIVE_TO_ID:
        raise ValueError(f"Unsupported objective '{objective}' in point[{point_index}]")

    tops_target_tops = int(point["tops_target_tops"])
    total_tops_scaled = tops_target_tops * 1024
    xx = int(core_array["x"])
    yy = int(core_array["y"])
    macs_per_core = int(point["macs_per_core"])
    if 2 * xx * yy * macs_per_core != total_tops_scaled:
        raise ValueError(f"Invalid point[{point_index}] topology: 2 * {xx} * {yy} * {macs_per_core} != {total_tops_scaled}")

    xcut = int(chiplet_partition["x"])
    ycut = int(chiplet_partition["y"])
    if xx % xcut != 0 or yy % ycut != 0:
        raise ValueError(f"Invalid point[{point_index}] chiplet partition: {xx}x{yy} not divisible by {xcut}x{ycut}")

    return {
        "baseline_mode": point["baseline_mode"],
        "design_name": point["design_name"],
        "tech": str(point["process_node"]),
        "mm": MICROARCH_TO_ID[microarch],
        "microarch_name": microarch,
        "nn": NETWORK_TO_ID[executable_workload],
        "workload_name": workload,
        "workload_exec_name": executable_workload,
        "xx": xx,
        "yy": yy,
        "ss": int(point["stride"]),
        "bb": int(point["batch_size"]),
        "rr": int(point["search_rounds"]),
        "ff": OBJECTIVE_TO_ID[objective],
        "objective_name": objective,
        "workload_motif": point.get("workload_motif"),
        "workload_ref": point.get("workload_ref"),
        "workload_status": point.get("workload_status"),
        "workload_trace_ref": point.get("workload_trace_ref"),
        "workload_trace_summary": point.get("workload_trace_summary"),
        "workload_trace_scalars": point.get("workload_trace_scalars"),
        "xcut": xcut,
        "ycut": ycut,
        "package_type": point["package_class"],
        "IO_type": point["interface_class"],
        "ddr_type": point["memory_class"],
        "ddr_bw": int(point["memory_bandwidth_gbps"]) * 1024,
        "noc": int(point["noc_bandwidth"]),
        "nop_bw": int(point["nop_bandwidth"]),
        "mac": macs_per_core,
        "ul3": int(point["ul3_kb"]),
        "tops_target_tops": tops_target_tops,
        "tops": total_tops_scaled,
        "proposal_budget": maybe_int(point.get("proposal_budget")),
        "seed": int(point["seed"]),
        "time_cap_minutes": maybe_float(point.get("time_cap_minutes")),
    }
