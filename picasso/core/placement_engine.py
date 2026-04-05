from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple

from .cluster_model import ClusterCoord, CoreCluster, build_core_cluster
from .models import NormalizedPoint, SearchState
from .partition_engine import PartitionPlan
from .workload_graph import WorkloadGraph


CoreCoord = ClusterCoord


@dataclass(frozen=True)
class PlacementSchedule:
    layer_index: int
    segment_id: int
    partition_order: Tuple[str, str, str, str]
    permute_order: Tuple[int, ...]
    ordered_core_ids: Tuple[int, ...]


@dataclass(frozen=True)
class LayerPlacement:
    layer_index: int
    segment_id: int
    partition_order: Tuple[str, str, str, str]
    partition_to_core: List[int]
    schedule: PlacementSchedule


@dataclass(frozen=True)
class PlacementPlan:
    cluster: CoreCluster
    core_coords: List[CoreCoord]
    layer_placements: List[LayerPlacement]


def _chiplet_priority(point: NormalizedPoint, state: SearchState, layer_index: int) -> List[int]:
    chiplet_ids = list(range(max(point.xcut * point.ycut, 1)))
    if len(chiplet_ids) <= 1:
        return chiplet_ids
    offset = int(round(state.placement_skew * (len(chiplet_ids) - 1)))
    offset += layer_index % len(chiplet_ids)
    offset %= len(chiplet_ids)
    return chiplet_ids[offset:] + chiplet_ids[:offset]


def _order_cores_within_chiplet(coords: List[CoreCoord], reverse: bool) -> List[CoreCoord]:
    rows: Dict[int, List[CoreCoord]] = {}
    for coord in coords:
        rows.setdefault(coord.y, []).append(coord)
    ordered: List[CoreCoord] = []
    for row_idx, y in enumerate(sorted(rows)):
        row = sorted(rows[y], key=lambda item: item.x, reverse=reverse if row_idx % 2 == 0 else not reverse)
        ordered.extend(row)
    return ordered


def _permute_order(order: Tuple[str, str, str, str]) -> Tuple[int, ...]:
    axis_id = {"k": 0, "b": 1, "h": 2, "w": 3}
    return tuple(axis_id[axis] for axis in order)


def build_placement_plan(point: NormalizedPoint, state: SearchState, graph: WorkloadGraph, partition_plan: PartitionPlan) -> PlacementPlan:
    del graph
    cluster = build_core_cluster(point)
    core_coords = list(cluster.coords)
    chiplet_map: Dict[int, List[CoreCoord]] = {}
    for coord in core_coords:
        chiplet_map.setdefault(coord.chiplet_id, []).append(coord)

    layer_placements: List[LayerPlacement] = []
    for layer_plan in partition_plan.layer_plans:
        segment_id = layer_plan.layer_index // max(state.segment_span, 1)
        chiplet_priority = _chiplet_priority(point, state, layer_plan.layer_index if not state.batch_cluster else segment_id)
        ordered_coords: List[CoreCoord] = []
        reverse = state.placement_skew < 0
        for chiplet_id in chiplet_priority:
            ordered_coords.extend(_order_cores_within_chiplet(chiplet_map[chiplet_id], reverse=reverse))
        if len(ordered_coords) != partition_plan.total_cores:
            raise ValueError("placement plan core count mismatch")
        partition_core_count = max(layer_plan.factors.size, 1)
        if partition_core_count > len(ordered_coords):
            raise ValueError("placement plan does not have enough cores for requested partition size")
        ordered_core_ids = tuple(coord.core_id for coord in ordered_coords[:partition_core_count])
        schedule = PlacementSchedule(
            layer_index=layer_plan.layer_index,
            segment_id=segment_id,
            partition_order=layer_plan.partition_order,
            permute_order=_permute_order(layer_plan.partition_order),
            ordered_core_ids=ordered_core_ids,
        )
        layer_placements.append(
            LayerPlacement(
                layer_index=layer_plan.layer_index,
                segment_id=segment_id,
                partition_order=layer_plan.partition_order,
                partition_to_core=list(ordered_core_ids),
                schedule=schedule,
            )
        )
    return PlacementPlan(cluster=cluster, core_coords=core_coords, layer_placements=layer_placements)
