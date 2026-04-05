from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List, Tuple

from .partition_engine import LayerPartitionPlan, PartitionPlan
from .placement_engine import CoreCoord, LayerPlacement, PlacementPlan
from .workload_graph import LayerNode, WorkloadGraph


@dataclass(frozen=True)
class DimRange:
    start: int
    end: int

    @property
    def size(self) -> int:
        return max(self.end - self.start, 0)

    def intersect(self, other: "DimRange") -> "DimRange":
        return DimRange(max(self.start, other.start), min(self.end, other.end))


@dataclass(frozen=True)
class FeatureMapRange:
    c: DimRange
    b: DimRange
    h: DimRange
    w: DimRange

    @property
    def volume(self) -> int:
        return self.c.size * self.b.size * self.h.size * self.w.size

    def intersect(self, other: "FeatureMapRange") -> "FeatureMapRange":
        return FeatureMapRange(
            c=self.c.intersect(other.c),
            b=self.b.intersect(other.b),
            h=self.h.intersect(other.h),
            w=self.w.intersect(other.w),
        )


@dataclass(frozen=True)
class LayoutEntry:
    partition_id: int
    core_id: int
    chiplet_id: int
    core_x: int
    core_y: int
    tensor_range: FeatureMapRange
    tensor_kind: str
    source_layer: int | None = None
    broadcast_group: int | None = None


@dataclass(frozen=True)
class BroadcastGroup:
    group_id: int
    tensor_kind: str
    source_core_id: int
    target_core_ids: Tuple[int, ...]
    volume: int


@dataclass(frozen=True)
class TensorLayout:
    tensor_kind: str
    entries: Tuple[LayoutEntry, ...]
    broadcast_groups: Tuple[BroadcastGroup, ...]
    total_volume: int
    unique_volume: int


@dataclass(frozen=True)
class LayerLayout:
    layer_index: int
    ifm_layout: TensorLayout
    wgt_layout: TensorLayout
    ofm_layout: TensorLayout
    ofm_entries: List[LayoutEntry]
    ifm_entries: List[LayoutEntry]
    wgt_entries: List[LayoutEntry]


@dataclass(frozen=True)
class LayoutModel:
    layer_layouts: List[LayerLayout]
    locality_score: float
    remote_weight_share: float
    segment_crossing_count: int


def _intervals(total: int, parts: int) -> List[DimRange]:
    if parts <= 0:
        return [DimRange(0, total)]
    boundaries = [0]
    for idx in range(1, parts):
        boundaries.append(math.ceil(total * idx / parts))
    boundaries.append(total)
    return [DimRange(boundaries[idx], boundaries[idx + 1]) for idx in range(parts)]


def _partition_indices(partition_id: int, counts: Dict[str, int], order: Tuple[str, str, str, str]) -> Dict[str, int]:
    working = partition_id
    indices: Dict[str, int] = {}
    for axis in reversed(order):
        axis_count = max(counts[axis], 1)
        indices[axis] = working % axis_count
        working //= axis_count
    return indices


def _ofm_range(layer: LayerNode, plan: LayerPartitionPlan, partition_id: int) -> FeatureMapRange:
    counts = {"b": max(plan.factors.b, 1), "k": max(plan.factors.k, 1), "h": max(plan.factors.h, 1), "w": max(plan.factors.w, 1)}
    indices = _partition_indices(partition_id, counts, plan.partition_order)
    ranges = {
        "b": _intervals(layer.ofmap_shape.b, counts["b"]),
        "k": _intervals(layer.ofmap_shape.c, counts["k"]),
        "h": _intervals(layer.ofmap_shape.h, counts["h"]),
        "w": _intervals(layer.ofmap_shape.w, counts["w"]),
    }
    return FeatureMapRange(c=ranges["k"][indices["k"]], b=ranges["b"][indices["b"]], h=ranges["h"][indices["h"]], w=ranges["w"][indices["w"]])


def _convert_range(tensor_range: object) -> FeatureMapRange:
    return FeatureMapRange(
        c=DimRange(tensor_range.c.start, tensor_range.c.end),
        b=DimRange(tensor_range.b.start, tensor_range.b.end),
        h=DimRange(tensor_range.h.start, tensor_range.h.end),
        w=DimRange(tensor_range.w.start, tensor_range.w.end),
    )


def _core_lookup(core_coords: List[CoreCoord]) -> Dict[int, CoreCoord]:
    return {coord.core_id: coord for coord in core_coords}


def _broadcast_groups(entries: List[LayoutEntry], tensor_kind: str) -> Tuple[BroadcastGroup, ...]:
    range_groups: Dict[Tuple[int, int, int, int, int, int, int, int], List[LayoutEntry]] = {}
    for entry in entries:
        tensor_range = entry.tensor_range
        key = (
            tensor_range.c.start,
            tensor_range.c.end,
            tensor_range.b.start,
            tensor_range.b.end,
            tensor_range.h.start,
            tensor_range.h.end,
            tensor_range.w.start,
            tensor_range.w.end,
        )
        range_groups.setdefault(key, []).append(entry)
    groups: List[BroadcastGroup] = []
    for group_id, grouped_entries in enumerate(range_groups.values()):
        if len(grouped_entries) <= 1:
            continue
        source = min(grouped_entries, key=lambda entry: (entry.core_id, entry.partition_id))
        groups.append(
            BroadcastGroup(
                group_id=group_id,
                tensor_kind=tensor_kind,
                source_core_id=source.core_id,
                target_core_ids=tuple(sorted(entry.core_id for entry in grouped_entries)),
                volume=source.tensor_range.volume,
            )
        )
    return tuple(groups)


def _tensor_layout(entries: List[LayoutEntry], tensor_kind: str) -> TensorLayout:
    groups = _broadcast_groups(entries, tensor_kind)
    unique_keys = {
        (
            entry.tensor_range.c.start,
            entry.tensor_range.c.end,
            entry.tensor_range.b.start,
            entry.tensor_range.b.end,
            entry.tensor_range.h.start,
            entry.tensor_range.h.end,
            entry.tensor_range.w.start,
            entry.tensor_range.w.end,
        )
        for entry in entries
    }
    unique_volume = 0
    for key in unique_keys:
        unique_volume += (key[1] - key[0]) * (key[3] - key[2]) * (key[5] - key[4]) * (key[7] - key[6])
    return TensorLayout(
        tensor_kind=tensor_kind,
        entries=tuple(entries),
        broadcast_groups=groups,
        total_volume=sum(entry.tensor_range.volume for entry in entries),
        unique_volume=unique_volume,
    )


def build_layout_model(graph: WorkloadGraph, partition_plan: PartitionPlan, placement_plan: PlacementPlan) -> LayoutModel:
    core_map = _core_lookup(placement_plan.core_coords)
    layer_layouts: List[LayerLayout] = []
    layer_plan_by_id = {plan.layer_index: plan for plan in partition_plan.layer_plans}
    placement_by_id = {placement.layer_index: placement for placement in placement_plan.layer_placements}
    segment_crossing_count = 0
    local_overlap_volume = 0
    total_overlap_volume = 0
    remote_weight_volume = 0
    total_weight_volume = 0

    for layer in graph.layers:
        plan = layer_plan_by_id[layer.index]
        placement = placement_by_id[layer.index]
        ofm_entries: List[LayoutEntry] = []
        ifm_entries: List[LayoutEntry] = []
        wgt_entries: List[LayoutEntry] = []
        for partition_id, core_id in enumerate(placement.partition_to_core):
            coord = core_map[core_id]
            ofm_range = _ofm_range(layer, plan, partition_id)
            ifm_range = _convert_range(layer.required_input_range(ofm_range))
            wgt_range = _convert_range(layer.required_weight_range(ofm_range))
            ofm_entries.append(LayoutEntry(partition_id, core_id, coord.chiplet_id, coord.x, coord.y, ofm_range, "ofm"))
            ifm_entries.append(LayoutEntry(partition_id, core_id, coord.chiplet_id, coord.x, coord.y, ifm_range, "ifm", source_layer=layer.prevs[0] if layer.prevs else None))
            if layer.has_weights:
                wgt_entries.append(LayoutEntry(partition_id, core_id, coord.chiplet_id, coord.x, coord.y, wgt_range, "wgt"))
        layer_layouts.append(
            LayerLayout(
                layer_index=layer.index,
                ifm_layout=_tensor_layout(ifm_entries, "ifm"),
                wgt_layout=_tensor_layout(wgt_entries, "wgt"),
                ofm_layout=_tensor_layout(ofm_entries, "ofm"),
                ofm_entries=ofm_entries,
                ifm_entries=ifm_entries,
                wgt_entries=wgt_entries,
            )
        )

    layer_layout_by_id = {layout.layer_index: layout for layout in layer_layouts}
    for layer in graph.layers:
        placement = placement_by_id[layer.index]
        for prev_idx in layer.prevs:
            prev_placement = placement_by_id[prev_idx]
            if placement.segment_id != prev_placement.segment_id:
                segment_crossing_count += 1
            prev_layout = layer_layout_by_id[prev_idx]
            curr_layout = layer_layout_by_id[layer.index]
            for prev_entry in prev_layout.ofm_entries:
                for next_entry in curr_layout.ifm_entries:
                    overlap = prev_entry.tensor_range.intersect(next_entry.tensor_range).volume
                    if overlap <= 0:
                        continue
                    total_overlap_volume += overlap
                    if prev_entry.core_id == next_entry.core_id:
                        local_overlap_volume += overlap

    for layer_layout in layer_layouts:
        chiplet_weight_volume: Dict[int, int] = {}
        for entry in layer_layout.wgt_entries:
            volume = entry.tensor_range.volume
            total_weight_volume += volume
            chiplet_weight_volume[entry.chiplet_id] = chiplet_weight_volume.get(entry.chiplet_id, 0) + volume
        if chiplet_weight_volume:
            primary_chiplet = max(chiplet_weight_volume, key=chiplet_weight_volume.get)
            for entry in layer_layout.wgt_entries:
                if entry.chiplet_id != primary_chiplet:
                    remote_weight_volume += entry.tensor_range.volume

    locality_score = local_overlap_volume / max(total_overlap_volume, 1)
    remote_weight_share = remote_weight_volume / max(total_weight_volume, 1)
    return LayoutModel(layer_layouts=layer_layouts, locality_score=locality_score, remote_weight_share=remote_weight_share, segment_crossing_count=segment_crossing_count)
