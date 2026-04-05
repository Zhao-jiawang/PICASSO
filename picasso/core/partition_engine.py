from __future__ import annotations

import math
from dataclasses import dataclass
from functools import lru_cache
from typing import Dict, List, Tuple

from .common_math import clamp
from .models import NormalizedPoint, SearchState
from .workload_graph import LayerNode, WorkloadGraph


@dataclass(frozen=True)
class PartitionFactors:
    b: int
    k: int
    h: int
    w: int

    @property
    def size(self) -> int:
        return self.b * self.k * self.h * self.w


@dataclass(frozen=True)
class FetchPlan:
    b: int
    k: int
    h: int
    w: int
    ifm_fetch: int
    wgt_fetch: int


@dataclass(frozen=True)
class PartitionCandidate:
    factors: PartitionFactors
    partition_order: Tuple[str, str, str, str]
    utilization: float
    score: float


@dataclass(frozen=True)
class PartitionSearchSpace:
    layer_index: int
    candidates: Tuple[PartitionCandidate, ...]


@dataclass(frozen=True)
class LayerPartitionPlan:
    layer_index: int
    factors: PartitionFactors
    fetch_plan: FetchPlan
    utilization: float
    partition_order: Tuple[str, str, str, str]
    candidate_rank: int
    search_space_size: int


@dataclass(frozen=True)
class PartitionPlan:
    total_cores: int
    layer_plans: List[LayerPartitionPlan]
    search_spaces: Dict[int, PartitionSearchSpace]


@lru_cache(maxsize=None)
def _factorizations(total: int) -> Tuple[PartitionFactors, ...]:
    factors: List[PartitionFactors] = []
    for b in range(1, total + 1):
        if total % b != 0:
            continue
        rest_b = total // b
        for k in range(1, rest_b + 1):
            if rest_b % k != 0:
                continue
            rest_k = rest_b // k
            for h in range(1, rest_k + 1):
                if rest_k % h != 0:
                    continue
                w = rest_k // h
                factors.append(PartitionFactors(b=b, k=k, h=h, w=w))
    return tuple(factors)


def _ceil_util(real: int, part: int) -> float:
    return real / (math.ceil(real / max(part, 1)) * max(part, 1))


def _axis_preference(layer: LayerNode, state: SearchState) -> Tuple[str, str, str, str]:
    if layer.kind == "conv":
        return ("k", "h", "w", "b") if state.mapping_tiling >= 2 else ("h", "w", "k", "b")
    if layer.kind in {"linear", "attention", "cache"} and layer.ofmap_shape.h >= 1024:
        return ("h", "k", "b", "w")
    if layer.kind in {"attention", "collective", "dispatch", "combine"}:
        return ("h", "k", "b", "w")
    if layer.kind in {"router", "expert_ffn", "linear"}:
        return ("k", "b", "h", "w")
    return ("k", "h", "b", "w")


def _score_partition(layer: LayerNode, factors: PartitionFactors, state: SearchState, total_cores: int) -> float:
    util = (
        _ceil_util(layer.ofmap_shape.b, factors.b)
        * _ceil_util(max(layer.ofmap_shape.c, 1), factors.k)
        * _ceil_util(max(layer.ofmap_shape.h, 1), factors.h)
        * _ceil_util(max(layer.ofmap_shape.w, 1), factors.w)
    )
    preference = _axis_preference(layer, state)
    axis_map = {"b": factors.b, "k": factors.k, "h": factors.h, "w": factors.w}
    priority_score = 0.0
    for rank, axis in enumerate(preference):
        priority_score += axis_map[axis] * (4 - rank)
    fetch_bias = 1.0 + 0.05 * max(state.mapping_tiling - 1, 0) + 0.04 * max(state.segment_span - 1, 0)
    if layer.collective_kind:
        fetch_bias += 0.18
    if layer.kind == "conv":
        fetch_bias += 0.10 if state.batch_cluster else 0.0
    balance_penalty = abs(math.log2(max(factors.k, 1))) * 0.03 + abs(math.log2(max(factors.h * factors.w, 1))) * 0.02
    return util * fetch_bias + priority_score / max(total_cores * 10.0, 1.0) - balance_penalty


def _fetch_plan(layer: LayerNode, factors: PartitionFactors, point: NormalizedPoint) -> FetchPlan:
    buffer_bytes = point.ul3_bytes_per_core
    batch = max(math.ceil(layer.ifmap_shape.b / max(factors.b, 1)), 1)
    height = max(math.ceil(layer.ofmap_shape.h / max(factors.h, 1)), 1)
    width = max(math.ceil(layer.ofmap_shape.w / max(factors.w, 1)), 1)
    ifm_per_partition = max(math.ceil(layer.activation_bytes / max(factors.size, 1)), 1)
    if layer.kind == "conv":
        conv_h = min((height - 1) * layer.stride_h + layer.kernel_h, layer.ifmap_shape.h)
        conv_w = min((width - 1) * layer.stride_w + layer.kernel_w, layer.ifmap_shape.w)
        ifm_per_partition = max(math.ceil(layer.ifmap_shape.c / max(factors.k, 1)), 1) * batch * conv_h * conv_w
    ofm_per_partition = max(math.ceil(layer.output_bytes / max(factors.size, 1)), 1)
    weight_per_partition = 0 if not layer.has_weights else max(1, math.ceil(layer.weight_bytes / max(factors.k, 1)))
    total = ifm_per_partition + ofm_per_partition + weight_per_partition
    if total <= buffer_bytes:
        return FetchPlan(1, 1, 1, 1, 1, 1)

    fetch_b = 1
    fetch_k = 1
    fetch_h = 1
    fetch_w = 1
    if layer.has_weights and weight_per_partition > buffer_bytes * 0.35:
        fetch_k = max(1, math.ceil(weight_per_partition / max(buffer_bytes * 0.35, 1)))
    resident_weight = max(math.ceil(weight_per_partition / max(fetch_k, 1)), 0)

    def activation_resident(fetch_product: int) -> int:
        return (
            max(math.ceil(ifm_per_partition / max(fetch_product, 1)), 1)
            + max(math.ceil(ofm_per_partition / max(fetch_product, 1)), 1)
        )

    target_activation_budget = max(buffer_bytes - resident_weight, int(buffer_bytes * 0.40), 1)
    residual = activation_resident(1) + resident_weight
    if residual > buffer_bytes and layer.ofmap_shape.h > 1:
        fetch_h = max(1, math.ceil(activation_resident(1) / target_activation_budget))
    residual = activation_resident(fetch_h) + resident_weight
    if residual > buffer_bytes and layer.ofmap_shape.b > 1:
        fetch_b = max(1, math.ceil(activation_resident(fetch_h) / target_activation_budget))
    residual = activation_resident(fetch_h * fetch_b) + resident_weight
    if residual > buffer_bytes and layer.ofmap_shape.w > 1:
        fetch_w = max(1, math.ceil(activation_resident(fetch_h * fetch_b) / target_activation_budget))
    return FetchPlan(fetch_b, fetch_k, fetch_h, fetch_w, ifm_fetch=max(fetch_b * fetch_h * fetch_w, 1), wgt_fetch=max(fetch_k, 1))


def enumerate_partition_candidates(
    layer: LayerNode,
    point: NormalizedPoint,
    state: SearchState,
    partition_budget: int | None = None,
) -> PartitionSearchSpace:
    total_cores = max(partition_budget or (point.xx * point.yy), 1)
    candidates = []
    for factors in _factorizations(total_cores):
        util = (
            _ceil_util(layer.ofmap_shape.b, factors.b)
            * _ceil_util(max(layer.ofmap_shape.c, 1), factors.k)
            * _ceil_util(max(layer.ofmap_shape.h, 1), factors.h)
            * _ceil_util(max(layer.ofmap_shape.w, 1), factors.w)
        )
        if util < 0.45:
            continue
        candidates.append(
            PartitionCandidate(
                factors=factors,
                partition_order=_axis_preference(layer, state),
                utilization=clamp(util, 0.0, 1.0),
                score=_score_partition(layer, factors, state, total_cores),
            )
        )
    ordered = tuple(sorted(candidates, key=lambda candidate: candidate.score, reverse=True))
    return PartitionSearchSpace(layer_index=layer.index, candidates=ordered)


def choose_partition_plan(point: NormalizedPoint, state: SearchState, graph: WorkloadGraph) -> PartitionPlan:
    total_cores = max(point.xx * point.yy, 1)
    trace_summary = point.workload_trace_summary or {}
    expert_count = max(int(trace_summary.get("expert_count", 1)), 1)
    layer_plans: List[LayerPartitionPlan] = []
    search_spaces: Dict[int, PartitionSearchSpace] = {}
    for layer in graph.layers:
        partition_budget = total_cores
        if layer.kind == "expert_ffn" and expert_count > 1:
            partition_budget = max(total_cores // expert_count, 1)
        space = enumerate_partition_candidates(layer, point, state, partition_budget=partition_budget)
        if not space.candidates:
            raise ValueError(f"no partition candidates available for layer {layer.name}")
        best = space.candidates[0]
        search_spaces[layer.index] = space
        layer_plans.append(
            LayerPartitionPlan(
                layer_index=layer.index,
                factors=best.factors,
                fetch_plan=_fetch_plan(layer, best.factors, point),
                utilization=best.utilization,
                partition_order=best.partition_order,
                candidate_rank=0,
                search_space_size=len(space.candidates),
            )
        )
    return PartitionPlan(total_cores=total_cores, layer_plans=layer_plans, search_spaces=search_spaces)
