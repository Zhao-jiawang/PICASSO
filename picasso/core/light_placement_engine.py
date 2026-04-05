from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List, Tuple

from .data_layout import LayoutModel
from .models import NormalizedPoint, SearchState
from .partition_engine import PartitionPlan
from .placement_engine import CoreCoord, PlacementPlan
from .segmentation_engine import SegmentDescriptor, SegmentScheme
from .workload_graph import WorkloadGraph


@dataclass(frozen=True)
class DRAttachment:
    ifmap_sources: Tuple[int, ...]
    weight_sources: Tuple[int, ...]
    ofmap_targets: Tuple[int, ...]
    source_mode: str


@dataclass(frozen=True)
class LightPartitionSpec:
    layer_index: int
    b: int
    k: int
    h: int
    w: int
    fetch_ifmap: int
    fetch_weight: int


@dataclass(frozen=True)
class LightLayerPlacement:
    layer_index: int
    segment_id: int
    stage_id: int
    active_core_ids: Tuple[int, ...]
    active_chiplets: Tuple[int, ...]
    partition_to_core: Tuple[int, ...]
    partition: LightPartitionSpec
    dram_attachment: DRAttachment
    multicast_root_core: int
    path_policy: str


@dataclass(frozen=True)
class LightSegmentPlacement:
    segment_id: int
    layer_indices: Tuple[int, ...]
    active_core_ids: Tuple[int, ...]
    active_chiplets: Tuple[int, ...]
    stage_count: int
    path_policy: str


@dataclass(frozen=True)
class LightPlacementPlan:
    segments: Tuple[LightSegmentPlacement, ...]
    layer_placements: Tuple[LightLayerPlacement, ...]
    layer_by_index: Dict[int, LightLayerPlacement]


def _chiplet_id_to_coord(chiplet_id: int, point: NormalizedPoint) -> Tuple[int, int]:
    return chiplet_id % max(point.xcut, 1), chiplet_id // max(point.xcut, 1)


def _boundary_chiplets(point: NormalizedPoint) -> Tuple[int, ...]:
    boundary = []
    for chiplet_id in range(max(point.xcut * point.ycut, 1)):
        chiplet_x, chiplet_y = _chiplet_id_to_coord(chiplet_id, point)
        if chiplet_x in {0, point.xcut - 1} or chiplet_y in {0, point.ycut - 1}:
            boundary.append(chiplet_id)
    return tuple(boundary)


def _nearest_boundary_chiplets(active_chiplets: Tuple[int, ...], point: NormalizedPoint, max_count: int, rotate: int = 0) -> Tuple[int, ...]:
    if not active_chiplets:
        return (0,)
    boundary = _boundary_chiplets(point)
    active_coords = [_chiplet_id_to_coord(chiplet_id, point) for chiplet_id in active_chiplets]
    cx = sum(coord[0] for coord in active_coords) / len(active_coords)
    cy = sum(coord[1] for coord in active_coords) / len(active_coords)
    ranked = sorted(
        boundary,
        key=lambda chiplet_id: (
            abs(_chiplet_id_to_coord(chiplet_id, point)[0] - cx)
            + abs(_chiplet_id_to_coord(chiplet_id, point)[1] - cy),
            chiplet_id,
        ),
    )
    if ranked and rotate:
        shift = rotate % len(ranked)
        ranked = ranked[shift:] + ranked[:shift]
    return tuple(ranked[: max(max_count, 1)])


def _path_policy(active_chiplets: Tuple[int, ...], stage_count: int, state: SearchState, point: NormalizedPoint) -> str:
    if len(active_chiplets) <= 1:
        return "xy"
    x_coords = [_chiplet_id_to_coord(chiplet_id, point)[0] for chiplet_id in active_chiplets]
    y_coords = [_chiplet_id_to_coord(chiplet_id, point)[1] for chiplet_id in active_chiplets]
    x_span = max(x_coords) - min(x_coords)
    y_span = max(y_coords) - min(y_coords)
    if state.interleave and stage_count > 1:
        return "adaptive"
    if y_span > x_span:
        return "yx"
    if x_span > y_span:
        return "xy"
    return "adaptive" if state.interleave else "xy"


def _multicast_root_core(active_core_ids: Tuple[int, ...], core_lookup: Dict[int, CoreCoord]) -> int:
    if not active_core_ids:
        return -1
    if len(active_core_ids) == 1:
        return active_core_ids[0]
    return min(
        active_core_ids,
        key=lambda core_id: sum(
            abs(core_lookup[core_id].x - core_lookup[other].x) + abs(core_lookup[core_id].y - core_lookup[other].y)
            for other in active_core_ids
        ),
    )


def build_light_placement_plan(
    point: NormalizedPoint,
    state: SearchState,
    graph: WorkloadGraph,
    segment_scheme: SegmentScheme,
    partition_plan: PartitionPlan,
    placement_plan: PlacementPlan,
    layout_model: LayoutModel,
) -> LightPlacementPlan:
    del layout_model
    core_lookup = {coord.core_id: coord for coord in placement_plan.core_coords}
    partition_by_layer = {plan.layer_index: plan for plan in partition_plan.layer_plans}
    placement_by_layer = {placement.layer_index: placement for placement in placement_plan.layer_placements}

    layer_assignments: List[LightLayerPlacement] = []
    layer_by_index: Dict[int, LightLayerPlacement] = {}
    segments: List[LightSegmentPlacement] = []

    for segment in segment_scheme.segments:
        active_core_ids: List[int] = []
        active_core_set = set()
        active_chiplet_ids: List[int] = []
        active_chiplet_set = set()
        for layer_index in segment.layer_indices:
            placement = placement_by_layer[layer_index]
            for core_id in placement.partition_to_core:
                if core_id not in active_core_set:
                    active_core_set.add(core_id)
                    active_core_ids.append(core_id)
                chiplet_id = core_lookup[core_id].chiplet_id
                if chiplet_id not in active_chiplet_set:
                    active_chiplet_set.add(chiplet_id)
                    active_chiplet_ids.append(chiplet_id)

        active_core_tuple = tuple(active_core_ids)
        active_chiplet_tuple = tuple(active_chiplet_ids)
        segment_path_policy = _path_policy(active_chiplet_tuple, segment.stage_count, state, point)
        segments.append(
            LightSegmentPlacement(
                segment_id=segment.segment_id,
                layer_indices=segment.layer_indices,
                active_core_ids=active_core_tuple,
                active_chiplets=active_chiplet_tuple,
                stage_count=segment.stage_count,
                path_policy=segment_path_policy,
            )
        )

        for offset, layer_index in enumerate(segment.layer_indices):
            layer = graph.layers[layer_index]
            placement = placement_by_layer[layer_index]
            partition = partition_by_layer[layer_index]
            stage_id = segment.stage_ids[offset]
            if layer.collective_kind in {"all_reduce", "all_gather", "dispatch", "combine", "attention"}:
                source_mode = "striped"
                ifmap_sources = _nearest_boundary_chiplets(active_chiplet_tuple, point, max_count=min(len(active_chiplet_tuple), 2), rotate=segment.segment_id)
                weight_sources = ifmap_sources if layer.has_weights else active_chiplet_tuple
            elif state.interleave and len(active_chiplet_tuple) > 1:
                source_mode = "interleave"
                ifmap_sources = _nearest_boundary_chiplets(active_chiplet_tuple, point, max_count=2, rotate=segment.segment_id)
                weight_sources = _nearest_boundary_chiplets(active_chiplet_tuple, point, max_count=2, rotate=segment.segment_id + 1)
            else:
                source_mode = "nearest"
                ifmap_sources = _nearest_boundary_chiplets(active_chiplet_tuple, point, max_count=1, rotate=segment.segment_id)
                weight_sources = _nearest_boundary_chiplets(active_chiplet_tuple, point, max_count=1, rotate=segment.segment_id + offset)

            if not layer.prevs:
                ifmap_sources = _nearest_boundary_chiplets(active_chiplet_tuple, point, max_count=max(len(ifmap_sources), 1), rotate=segment.segment_id)
            if not layer.has_weights or not layer.weight_from_memory:
                weight_sources = active_chiplet_tuple if active_chiplet_tuple else (0,)

            ofmap_targets = active_chiplet_tuple
            if layer.writes_to_memory or segment.to_memory or offset == len(segment.layer_indices) - 1:
                ofmap_targets = _nearest_boundary_chiplets(active_chiplet_tuple, point, max_count=max(1, min(len(active_chiplet_tuple), 2)), rotate=segment.segment_id + 1)

            assignment = LightLayerPlacement(
                layer_index=layer_index,
                segment_id=segment.segment_id,
                stage_id=stage_id,
                active_core_ids=active_core_tuple,
                active_chiplets=active_chiplet_tuple,
                partition_to_core=tuple(placement.partition_to_core),
                partition=LightPartitionSpec(
                    layer_index=layer_index,
                    b=partition.factors.b,
                    k=partition.factors.k,
                    h=partition.factors.h,
                    w=partition.factors.w,
                    fetch_ifmap=partition.fetch_plan.ifm_fetch,
                    fetch_weight=partition.fetch_plan.wgt_fetch,
                ),
                dram_attachment=DRAttachment(
                    ifmap_sources=ifmap_sources,
                    weight_sources=weight_sources,
                    ofmap_targets=ofmap_targets,
                    source_mode=source_mode,
                ),
                multicast_root_core=_multicast_root_core(active_core_tuple, core_lookup),
                path_policy=segment_path_policy,
            )
            layer_assignments.append(assignment)
            layer_by_index[layer_index] = assignment

    return LightPlacementPlan(
        segments=tuple(segments),
        layer_placements=tuple(layer_assignments),
        layer_by_index=layer_by_index,
    )
