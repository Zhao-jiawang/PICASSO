from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List, Tuple

from .common_math import clamp
from .models import NormalizedPoint, SearchState
from .workload_graph import LayerNode, WorkloadGraph


@dataclass(frozen=True)
class SegmentDescriptor:
    segment_id: int
    layer_indices: Tuple[int, ...]
    stage_ids: Tuple[int, ...]
    stage_count: int
    batch_group_count: int
    batch_group_size: int
    boundaries_after: Tuple[int, ...]
    shortcut_inputs: Tuple[int, ...]
    to_memory: bool
    score: float


@dataclass(frozen=True)
class SegmentScheme:
    order: Tuple[int, ...]
    boundaries_after: Tuple[int, ...]
    segments: Tuple[SegmentDescriptor, ...]


def _layer_lookup(graph: WorkloadGraph) -> Dict[int, LayerNode]:
    return {layer.index: layer for layer in graph.layers}


def _segment_stage_ids(graph: WorkloadGraph, layer_indices: Tuple[int, ...]) -> Tuple[int, ...]:
    layer_set = set(layer_indices)
    stage_map: Dict[int, int] = {}
    lookup = _layer_lookup(graph)
    for layer_index in layer_indices:
        layer = lookup[layer_index]
        stage = 0
        for prev in layer.prevs:
            if prev in layer_set:
                stage = max(stage, stage_map[prev] + 1)
        stage_map[layer_index] = stage
    return tuple(stage_map[layer_index] for layer_index in layer_indices)


def _segment_shortcuts(graph: WorkloadGraph, layer_indices: Tuple[int, ...], stage_ids: Tuple[int, ...]) -> Tuple[int, ...]:
    stage_lookup = {layer_index: stage_ids[offset] for offset, layer_index in enumerate(layer_indices)}
    layer_set = set(layer_indices)
    shortcuts = set()
    lookup = _layer_lookup(graph)
    for layer_index in layer_indices:
        layer = lookup[layer_index]
        for prev in layer.prevs:
            if prev not in layer_set:
                shortcuts.add(prev)
                continue
            if stage_lookup[layer_index] > stage_lookup[prev] + 1:
                shortcuts.add(prev)
    return tuple(sorted(shortcuts))


def _segment_batching(point: NormalizedPoint, state: SearchState, layers: List[LayerNode], stage_count: int) -> Tuple[int, int]:
    total_batch = max(point.bb, 1)
    if total_batch == 1:
        return 1, 1

    batch_groups = 1
    if state.batch_cluster:
        batch_groups += 1
    if stage_count > 1:
        batch_groups += 1
    if any(layer.kind in {"conv", "dispatch", "combine", "collective"} for layer in layers):
        batch_groups += 1

    batch_groups = min(batch_groups, total_batch)
    batch_group_size = max(math.ceil(total_batch / batch_groups), 1)
    return batch_groups, batch_group_size


def _segment_score(
    point: NormalizedPoint,
    state: SearchState,
    graph: WorkloadGraph,
    start: int,
    end: int,
    desired_span: int,
) -> Tuple[float, Tuple[int, ...], Tuple[int, ...]]:
    layer_indices = tuple(layer.index for layer in graph.layers[start:end])
    segment_layers = graph.layers[start:end]
    stage_ids = _segment_stage_ids(graph, layer_indices)
    shortcut_inputs = _segment_shortcuts(graph, layer_indices, stage_ids)
    stage_count = max(stage_ids, default=0) + 1

    total_weight = sum(layer.weight_bytes for layer in segment_layers)
    total_activation = sum(layer.activation_bytes + layer.output_bytes for layer in segment_layers)
    collective_layers = sum(1 for layer in segment_layers if layer.collective_kind or layer.kind in {"dispatch", "combine", "collective", "attention"})
    expert_layers = sum(1 for layer in segment_layers if layer.kind == "expert_ffn")
    writeback_layers = sum(1 for layer in segment_layers if layer.writes_to_memory)

    span = len(segment_layers)
    span_penalty = abs(span - desired_span) * 0.18
    stage_penalty = max(stage_count - max(state.pipeline_depth, 1), 0) * 0.16
    shortcut_penalty = len(shortcut_inputs) * 0.12
    weight_pressure = total_weight / max(total_activation + total_weight, 1)
    batching_bonus = 0.10 if state.batch_cluster and any(layer.kind == "conv" for layer in segment_layers) else 0.0
    collective_bonus = 0.08 * collective_layers if point.chiplet_count > 1 else 0.03 * collective_layers
    expert_bonus = 0.06 * expert_layers
    residency_bonus = 0.05 * state.spm_level + 0.03 * state.memory_prefetch
    writeback_bonus = 0.05 if writeback_layers > 0 else 0.0

    score = (
        batching_bonus
        + collective_bonus
        + expert_bonus
        + residency_bonus
        + writeback_bonus
        - span_penalty
        - stage_penalty
        - shortcut_penalty
        - 0.25 * weight_pressure
    )
    return score, stage_ids, shortcut_inputs


def build_segment_scheme(point: NormalizedPoint, state: SearchState, graph: WorkloadGraph) -> SegmentScheme:
    if not graph.layers:
        return SegmentScheme(order=(), boundaries_after=(), segments=())

    desired_span = max(state.segment_span, 1)
    min_span = max(1, desired_span // 2)
    max_span = max(desired_span * 2, desired_span)
    layer_count = len(graph.layers)

    best_score = [-1.0e18] * (layer_count + 1)
    prev_cut = [-1] * (layer_count + 1)
    stage_cache: Dict[Tuple[int, int], Tuple[int, ...]] = {}
    shortcut_cache: Dict[Tuple[int, int], Tuple[int, ...]] = {}
    best_score[0] = 0.0

    for start in range(layer_count):
        if best_score[start] <= -1.0e17:
            continue
        for end in range(start + min_span, min(layer_count, start + max_span) + 1):
            score, stage_ids, shortcut_inputs = _segment_score(point, state, graph, start, end, desired_span)
            if best_score[start] + score > best_score[end]:
                best_score[end] = best_score[start] + score
                prev_cut[end] = start
                stage_cache[(start, end)] = stage_ids
                shortcut_cache[(start, end)] = shortcut_inputs

    if prev_cut[layer_count] < 0:
        # Fallback to periodic segmentation if DP degenerates.
        boundaries = tuple(
            graph.layers[layer_index].index
            for layer_index in range(desired_span - 1, layer_count - 1, desired_span)
        )
        segments: List[SegmentDescriptor] = []
        start = 0
        segment_id = 0
        boundary_set = set(boundaries)
        while start < layer_count:
            end = min(start + desired_span, layer_count)
            while end < layer_count and graph.layers[end - 1].index not in boundary_set and end - start < max_span:
                end += 1
            layer_indices = tuple(layer.index for layer in graph.layers[start:end])
            stage_ids = _segment_stage_ids(graph, layer_indices)
            stage_count = max(stage_ids, default=0) + 1
            batch_groups, batch_group_size = _segment_batching(point, state, graph.layers[start:end], stage_count)
            shortcut_inputs = _segment_shortcuts(graph, layer_indices, stage_ids)
            segments.append(
                SegmentDescriptor(
                    segment_id=segment_id,
                    layer_indices=layer_indices,
                    stage_ids=stage_ids,
                    stage_count=stage_count,
                    batch_group_count=batch_groups,
                    batch_group_size=batch_group_size,
                    boundaries_after=(() if end == layer_count else (graph.layers[end - 1].index,)),
                    shortcut_inputs=shortcut_inputs,
                    to_memory=any(layer.writes_to_memory for layer in graph.layers[start:end]),
                    score=0.0,
                )
            )
            segment_id += 1
            start = end
        return SegmentScheme(
            order=tuple(layer.index for layer in graph.layers),
            boundaries_after=tuple(boundaries),
            segments=tuple(segments),
        )

    intervals: List[Tuple[int, int]] = []
    cursor = layer_count
    while cursor > 0:
        start = prev_cut[cursor]
        intervals.append((start, cursor))
        cursor = start
    intervals.reverse()

    segments: List[SegmentDescriptor] = []
    boundaries: List[int] = []
    for segment_id, (start, end) in enumerate(intervals):
        layer_indices = tuple(layer.index for layer in graph.layers[start:end])
        segment_layers = graph.layers[start:end]
        stage_ids = stage_cache[(start, end)]
        shortcut_inputs = shortcut_cache[(start, end)]
        stage_count = max(stage_ids, default=0) + 1
        batch_groups, batch_group_size = _segment_batching(point, state, segment_layers, stage_count)
        boundary_after = ()
        if end < layer_count:
            boundary_after = (graph.layers[end - 1].index,)
            boundaries.append(graph.layers[end - 1].index)
        segments.append(
            SegmentDescriptor(
                segment_id=segment_id,
                layer_indices=layer_indices,
                stage_ids=stage_ids,
                stage_count=stage_count,
                batch_group_count=batch_groups,
                batch_group_size=batch_group_size,
                boundaries_after=boundary_after,
                shortcut_inputs=shortcut_inputs,
                to_memory=any(layer.writes_to_memory for layer in segment_layers),
                score=best_score[end] - best_score[start],
            )
        )

    return SegmentScheme(
        order=tuple(layer.index for layer in graph.layers),
        boundaries_after=tuple(boundaries),
        segments=tuple(segments),
    )
