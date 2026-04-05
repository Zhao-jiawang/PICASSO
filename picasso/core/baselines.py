from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List

from .registries import load_registry_bundle


BASELINE_ORDER = [
    "Joint",
    "Stage-wise",
    "Package-oblivious",
    "Architecture-first",
    "Partition-first",
    "Cost-interface-first",
    "Outer-loop repair",
    "Memory-off",
]

DIM_TO_MOVE = {
    "m": "map",
    "a": "arch",
    "k": "split",
    "i": "interface-package",
    "p": "interface-package",
    "b": "memory",
}


@dataclass(frozen=True)
class BaselineProfile:
    name: str
    family: str
    ordering: List[str]
    rank: int
    initial_temperature: float
    cooling: float
    score_bias: float
    package_blindness: float
    memory_blindness: float
    move_weights: Dict[str, float]


PROFILE_OVERRIDES = {
    "Joint": {"initial_temperature": 1.00, "cooling": 0.992, "score_bias": 1.000, "package_blindness": 0.00, "memory_blindness": 0.00},
    "Stage-wise": {"initial_temperature": 0.90, "cooling": 0.993, "score_bias": 1.035, "package_blindness": 0.04, "memory_blindness": 0.03},
    "Package-oblivious": {"initial_temperature": 0.86, "cooling": 0.994, "score_bias": 1.105, "package_blindness": 0.28, "memory_blindness": 0.05},
    "Architecture-first": {"initial_temperature": 0.88, "cooling": 0.994, "score_bias": 1.055, "package_blindness": 0.08, "memory_blindness": 0.06},
    "Partition-first": {"initial_temperature": 0.84, "cooling": 0.995, "score_bias": 1.075, "package_blindness": 0.10, "memory_blindness": 0.07},
    "Cost-interface-first": {"initial_temperature": 0.82, "cooling": 0.995, "score_bias": 1.090, "package_blindness": 0.12, "memory_blindness": 0.08},
    "Outer-loop repair": {"initial_temperature": 0.92, "cooling": 0.993, "score_bias": 1.045, "package_blindness": 0.06, "memory_blindness": 0.06},
    "Memory-off": {"initial_temperature": 0.80, "cooling": 0.996, "score_bias": 1.135, "package_blindness": 0.08, "memory_blindness": 0.34},
}


def build_move_weights(ordering: List[str]) -> Dict[str, float]:
    weights = {"map": 0.8, "arch": 0.8, "split": 0.8, "interface-package": 0.8, "memory": 0.8, "coupled": 0.7}
    total_dims = max(len(ordering), 1)
    for index, dim in enumerate(ordering):
        family = DIM_TO_MOVE[dim]
        weights[family] += float(total_dims - index)
    if weights["interface-package"] < 1.0:
        weights["interface-package"] = 1.0
    return weights


def load_baseline_profile(repo_root: Path, baseline_mode: str) -> BaselineProfile:
    bundle = load_registry_bundle(str(repo_root))
    registry = bundle.baselines
    if baseline_mode not in registry:
        raise ValueError(f"Unsupported baseline_mode: {baseline_mode}")

    entry = registry[baseline_mode]
    ordering = list(entry.get("ordering", []))
    rank = BASELINE_ORDER.index(baseline_mode) if baseline_mode in BASELINE_ORDER else len(BASELINE_ORDER)
    overrides = PROFILE_OVERRIDES.get(baseline_mode, PROFILE_OVERRIDES["Joint"])
    return BaselineProfile(
        name=baseline_mode,
        family=str(entry.get("family", "joint")),
        ordering=ordering,
        rank=rank,
        initial_temperature=float(overrides["initial_temperature"]),
        cooling=float(overrides["cooling"]),
        score_bias=float(overrides["score_bias"]),
        package_blindness=float(overrides["package_blindness"]),
        memory_blindness=float(overrides["memory_blindness"]),
        move_weights=build_move_weights(ordering),
    )
