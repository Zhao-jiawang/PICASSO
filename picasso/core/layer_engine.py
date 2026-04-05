from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Tuple

from .core_mapping_engine import LayerMapMetrics, map_layer_to_core
from .core_model import CoreLibrary, build_core_library
from .data_layout import LayoutModel
from .light_placement_engine import LightPlacementPlan, build_light_placement_plan
from .models import NormalizedPoint, SearchState
from .partition_engine import PartitionPlan
from .placement_engine import PlacementPlan
from .schedule_tree import LayerTreeNode, ScheduleTreeNode, build_layer_tree, build_schedule_tree
from .segmentation_engine import SegmentScheme, build_segment_scheme
from .workload_graph import LayerNode, WorkloadGraph


@dataclass(frozen=True)
class LayerExecutionRecord:
    layer_index: int
    segment_id: int
    stage_id: int
    active_core_ids: Tuple[int, ...]
    compute_cycles: int
    ifmap_bytes: int
    weight_bytes: int
    output_bytes: int
    working_set_bytes: int
    multicast_fanout: int
    direct_prev_layers: Tuple[int, ...]
    path_policy: str
    rounded_op_count: int
    mapped_utilization: float
    mac_energy: float
    buffer_energy: float
    interconnect_energy: float
    resident_ifmap_bytes: int
    resident_weight_bytes: int
    resident_output_bytes: int
    resident_total_bytes: int
    ubuf_bytes: int
    l1_bytes: int
    l2_bytes: int
    fetch_rounds: int


@dataclass(frozen=True)
class SegmentExecutionRecord:
    segment_id: int
    layer_indices: Tuple[int, ...]
    stage_count: int
    batch_group_count: int
    batch_group_size: int
    active_core_ids: Tuple[int, ...]
    active_chiplets: Tuple[int, ...]
    shortcut_inputs: Tuple[int, ...]
    to_memory: bool
    path_policy: str


@dataclass(frozen=True)
class LayerEnginePlan:
    segment_scheme: SegmentScheme
    layer_tree: LayerTreeNode
    schedule_tree: ScheduleTreeNode
    light_placement: LightPlacementPlan
    core_library: CoreLibrary
    layer_records: Tuple[LayerExecutionRecord, ...]
    segment_records: Tuple[SegmentExecutionRecord, ...]
    layer_by_index: Dict[int, LayerExecutionRecord]
    segment_by_id: Dict[int, SegmentExecutionRecord]


def _layout_lookup(layout_model: LayoutModel) -> Dict[int, int]:
    working_set_by_layer: Dict[int, int] = {}
    for layer_layout in layout_model.layer_layouts:
        ifm_bytes = layer_layout.ifm_layout.total_volume
        ofm_bytes = layer_layout.ofm_layout.total_volume
        wgt_bytes = layer_layout.wgt_layout.total_volume
        working_set_by_layer[layer_layout.layer_index] = ifm_bytes + ofm_bytes + wgt_bytes
    return working_set_by_layer


def build_layer_engine_plan(
    point: NormalizedPoint,
    state: SearchState,
    graph: WorkloadGraph,
    partition_plan: PartitionPlan,
    placement_plan: PlacementPlan,
    layout_model: LayoutModel,
    bundle: object,
) -> LayerEnginePlan:
    segment_scheme = build_segment_scheme(point, state, graph)
    light_plan = build_light_placement_plan(point, state, graph, segment_scheme, partition_plan, placement_plan, layout_model)
    layer_tree = build_layer_tree(graph, segment_scheme, max(point.bb, 1))
    schedule_tree = build_schedule_tree(layer_tree, light_plan)
    core_library = build_core_library(point, bundle)

    working_set_by_layer = _layout_lookup(layout_model)
    layer_lookup = {layer.index: layer for layer in graph.layers}
    partition_lookup = {plan.layer_index: plan for plan in partition_plan.layer_plans}
    layer_records = []
    layer_by_index: Dict[int, LayerExecutionRecord] = {}
    segment_records = []
    segment_by_id: Dict[int, SegmentExecutionRecord] = {}

    for segment in segment_scheme.segments:
        segment_light = next(item for item in light_plan.segments if item.segment_id == segment.segment_id)
        segment_record = SegmentExecutionRecord(
            segment_id=segment.segment_id,
            layer_indices=segment.layer_indices,
            stage_count=segment.stage_count,
            batch_group_count=segment.batch_group_count,
            batch_group_size=segment.batch_group_size,
            active_core_ids=segment_light.active_core_ids,
            active_chiplets=segment_light.active_chiplets,
            shortcut_inputs=segment.shortcut_inputs,
            to_memory=segment.to_memory,
            path_policy=segment_light.path_policy,
        )
        segment_records.append(segment_record)
        segment_by_id[segment.segment_id] = segment_record

        for offset, layer_index in enumerate(segment.layer_indices):
            layer: LayerNode = layer_lookup[layer_index]
            light_assignment = light_plan.layer_by_index[layer_index]
            mapping_metrics: LayerMapMetrics = map_layer_to_core(
                layer,
                partition_lookup[layer_index],
                core_library,
                len(light_assignment.active_core_ids),
            )
            record = LayerExecutionRecord(
                layer_index=layer_index,
                segment_id=segment.segment_id,
                stage_id=segment.stage_ids[offset],
                active_core_ids=light_assignment.active_core_ids,
                compute_cycles=mapping_metrics.compute_cycles,
                ifmap_bytes=layer.activation_bytes,
                weight_bytes=layer.weight_bytes,
                output_bytes=layer.output_bytes,
                working_set_bytes=working_set_by_layer.get(layer_index, 0),
                multicast_fanout=max(len(light_assignment.active_core_ids) - 1, 0) if layer.collective_kind else 0,
                direct_prev_layers=tuple(layer.prevs),
                path_policy=light_assignment.path_policy,
                rounded_op_count=mapping_metrics.rounded_op_count,
                mapped_utilization=mapping_metrics.utilization,
                mac_energy=mapping_metrics.mac_energy,
                buffer_energy=mapping_metrics.buffer_energy,
                interconnect_energy=mapping_metrics.interconnect_energy,
                resident_ifmap_bytes=mapping_metrics.resident_ifmap_bytes,
                resident_weight_bytes=mapping_metrics.resident_weight_bytes,
                resident_output_bytes=mapping_metrics.resident_output_bytes,
                resident_total_bytes=mapping_metrics.resident_total_bytes,
                ubuf_bytes=mapping_metrics.ubuf_bytes,
                l1_bytes=mapping_metrics.l1_bytes,
                l2_bytes=mapping_metrics.l2_bytes,
                fetch_rounds=mapping_metrics.fetch_rounds,
            )
            layer_records.append(record)
            layer_by_index[layer_index] = record

    return LayerEnginePlan(
        segment_scheme=segment_scheme,
        layer_tree=layer_tree,
        schedule_tree=schedule_tree,
        light_placement=light_plan,
        core_library=core_library,
        layer_records=tuple(layer_records),
        segment_records=tuple(segment_records),
        layer_by_index=layer_by_index,
        segment_by_id=segment_by_id,
    )
