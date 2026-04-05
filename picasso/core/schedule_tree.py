from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple

from .light_placement_engine import LightPlacementPlan
from .segmentation_engine import SegmentDescriptor, SegmentScheme
from .workload_graph import LayerNode, WorkloadGraph


@dataclass(frozen=True)
class LayerTreeNode:
    node_id: str
    node_type: str
    layer_indices: Tuple[int, ...]
    total_batch: int
    batch_group_count: int
    stage_by_child: Tuple[int, ...]
    num_stage: int
    unit_time: float
    height: int
    to_memory: bool
    direct_prev_layers: Tuple[int, ...]
    children: Tuple["LayerTreeNode", ...]


@dataclass(frozen=True)
class ScheduleTreeNode:
    node_id: str
    node_type: str
    layer_indices: Tuple[int, ...]
    segment_ids: Tuple[int, ...]
    active_core_ids: Tuple[int, ...]
    total_batch: int
    batch_group_count: int
    stage_by_child: Tuple[int, ...]
    num_stage: int
    unit_time: float
    height: int
    to_memory: bool
    direct_prev_layers: Tuple[int, ...]
    children: Tuple["ScheduleTreeNode", ...]


def _layer_lookup(graph: WorkloadGraph) -> Dict[int, LayerNode]:
    return {layer.index: layer for layer in graph.layers}


def _direct_prevs(graph: WorkloadGraph, layer_indices: Tuple[int, ...]) -> Tuple[int, ...]:
    layer_set = set(layer_indices)
    lookup = _layer_lookup(graph)
    direct = set()
    for layer_index in layer_indices:
        for prev in lookup[layer_index].prevs:
            if prev not in layer_set:
                direct.add(prev)
    return tuple(sorted(direct))


def _leaf_unit_time(layer: LayerNode) -> float:
    base = (layer.output_bytes + int(layer.weight_bytes * 0.35) + int(layer.activation_bytes * 0.20)) / 8192.0
    if layer.collective_kind:
        base *= 1.15
    if layer.kind in {"attention", "dispatch", "combine", "collective"}:
        base *= 1.12
    if layer.kind == "expert_ffn":
        base *= 1.08
    return max(base, 1.0)


def _build_leaf(layer: LayerNode, total_batch: int, batch_group_count: int) -> LayerTreeNode:
    return LayerTreeNode(
        node_id=f"L{layer.index}",
        node_type="L",
        layer_indices=(layer.index,),
        total_batch=total_batch,
        batch_group_count=batch_group_count,
        stage_by_child=(),
        num_stage=1,
        unit_time=_leaf_unit_time(layer),
        height=0,
        to_memory=layer.writes_to_memory,
        direct_prev_layers=tuple(layer.prevs),
        children=(),
    )


def _aggregate_node(
    node_id: str,
    node_type: str,
    total_batch: int,
    batch_group_count: int,
    stage_by_child: Tuple[int, ...],
    children: Tuple[LayerTreeNode, ...],
    graph: WorkloadGraph,
) -> LayerTreeNode:
    layer_indices = tuple(layer_index for child in children for layer_index in child.layer_indices)
    child_unit_time = sum(child.unit_time for child in children)
    num_stage = max(stage_by_child, default=0) + 1 if stage_by_child else 1
    unit_time = child_unit_time
    if node_type == "S":
        unit_time *= (batch_group_count + num_stage) / max(batch_group_count, 1)
    height = (max((child.height for child in children), default=-1) + 1) if children else 0
    direct_prev_layers = _direct_prevs(graph, layer_indices)
    return LayerTreeNode(
        node_id=node_id,
        node_type=node_type,
        layer_indices=layer_indices,
        total_batch=total_batch,
        batch_group_count=batch_group_count,
        stage_by_child=stage_by_child,
        num_stage=num_stage,
        unit_time=unit_time,
        height=height,
        to_memory=any(child.to_memory for child in children),
        direct_prev_layers=direct_prev_layers,
        children=children,
    )


def _build_segment_subtree(segment: SegmentDescriptor, graph: WorkloadGraph, total_batch: int) -> LayerTreeNode:
    lookup = _layer_lookup(graph)
    layers = [lookup[layer_index] for layer_index in segment.layer_indices]
    if len(layers) == 1:
        return _build_leaf(layers[0], total_batch, segment.batch_group_count)

    stage_groups: Dict[int, List[LayerNode]] = {}
    for layer_index, stage_id in zip(segment.layer_indices, segment.stage_ids):
        stage_groups.setdefault(stage_id, []).append(lookup[layer_index])

    stage_nodes: List[LayerTreeNode] = []
    for stage_id in sorted(stage_groups):
        stage_layers = stage_groups[stage_id]
        if len(stage_layers) == 1:
            stage_nodes.append(_build_leaf(stage_layers[0], total_batch, segment.batch_group_count))
            continue
        leaves = tuple(_build_leaf(layer, total_batch, segment.batch_group_count) for layer in stage_layers)
        stage_nodes.append(
            _aggregate_node(
                node_id=f"T_seg{segment.segment_id}_stage{stage_id}",
                node_type="T",
                total_batch=total_batch,
                batch_group_count=segment.batch_group_count,
                stage_by_child=tuple(range(len(leaves))),
                children=leaves,
                graph=graph,
            )
        )

    if len(stage_nodes) == 1:
        return stage_nodes[0]

    return _aggregate_node(
        node_id=f"S_seg{segment.segment_id}",
        node_type="S",
        total_batch=total_batch,
        batch_group_count=segment.batch_group_count,
        stage_by_child=tuple(sorted(stage_groups)),
        children=tuple(stage_nodes),
        graph=graph,
    )


def build_layer_tree(graph: WorkloadGraph, segment_scheme: SegmentScheme, total_batch: int) -> LayerTreeNode:
    if not segment_scheme.segments:
        return LayerTreeNode(
            node_id="T_root",
            node_type="T",
            layer_indices=(),
            total_batch=total_batch,
            batch_group_count=1,
            stage_by_child=(),
            num_stage=1,
            unit_time=0.0,
            height=0,
            to_memory=False,
            direct_prev_layers=(),
            children=(),
        )

    segment_nodes = tuple(_build_segment_subtree(segment, graph, total_batch) for segment in segment_scheme.segments)
    return _aggregate_node(
        node_id="T_root",
        node_type="T",
        total_batch=total_batch,
        batch_group_count=1,
        stage_by_child=tuple(range(len(segment_nodes))),
        children=segment_nodes,
        graph=graph,
    )


def _active_cores(light_plan: LightPlacementPlan, layer_indices: Tuple[int, ...]) -> Tuple[int, ...]:
    core_ids = []
    seen = set()
    for layer_index in layer_indices:
        assignment = light_plan.layer_by_index[layer_index]
        for core_id in assignment.active_core_ids:
            if core_id not in seen:
                seen.add(core_id)
                core_ids.append(core_id)
    return tuple(core_ids)


def _segment_ids(light_plan: LightPlacementPlan, layer_indices: Tuple[int, ...]) -> Tuple[int, ...]:
    segment_ids = []
    seen = set()
    for layer_index in layer_indices:
        segment_id = light_plan.layer_by_index[layer_index].segment_id
        if segment_id not in seen:
            seen.add(segment_id)
            segment_ids.append(segment_id)
    return tuple(segment_ids)


def _build_schedule_node(layer_tree: LayerTreeNode, light_plan: LightPlacementPlan) -> ScheduleTreeNode:
    children = tuple(_build_schedule_node(child, light_plan) for child in layer_tree.children)
    return ScheduleTreeNode(
        node_id=layer_tree.node_id,
        node_type=layer_tree.node_type,
        layer_indices=layer_tree.layer_indices,
        segment_ids=_segment_ids(light_plan, layer_tree.layer_indices) if layer_tree.layer_indices else (),
        active_core_ids=_active_cores(light_plan, layer_tree.layer_indices) if layer_tree.layer_indices else (),
        total_batch=layer_tree.total_batch,
        batch_group_count=layer_tree.batch_group_count,
        stage_by_child=layer_tree.stage_by_child,
        num_stage=layer_tree.num_stage,
        unit_time=layer_tree.unit_time,
        height=layer_tree.height,
        to_memory=layer_tree.to_memory,
        direct_prev_layers=layer_tree.direct_prev_layers,
        children=children,
    )


def build_schedule_tree(layer_tree: LayerTreeNode, light_plan: LightPlacementPlan) -> ScheduleTreeNode:
    return _build_schedule_node(layer_tree, light_plan)
