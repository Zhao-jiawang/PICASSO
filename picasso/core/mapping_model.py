from __future__ import annotations

import math
from typing import Any, Dict

from .buffer_model import BufferUsageResult
from .common_math import clamp
from .data_layout import LayoutModel
from .layer_engine import LayerEnginePlan
from .legality import geometry
from .models import MappingModelResult, NormalizedPoint, SearchState
from .partition_engine import PartitionPlan
from .placement_engine import PlacementPlan
from .workload_graph import WorkloadGraph


BASE_LAYER_COUNT = {
    "cnn_inference": 24,
    "dense_decoder_block": 16,
    "kv_heavy_decode": 20,
    "long_context_prefill": 20,
    "megatron_collective_trace": 32,
    "mixtral_moe_trace": 24,
}


def _collective_pressure(trace_summary: Dict[str, Any]) -> float:
    if not trace_summary:
        return 0.0
    trace_type = trace_summary.get("trace_type")
    if trace_type == "mixtral_moe_trace":
        imbalance = max(float(trace_summary.get("load_imbalance_factor", 1.0)) - 1.0, 0.0)
        top_k = max(int(trace_summary.get("top_k", 1)) - 1, 0)
        locality_penalty = 1.0 - float(trace_summary.get("locality_probability", 0.5))
        return imbalance * 0.75 + top_k * 0.12 + locality_penalty * 0.35
    if trace_type == "megatron_collective_trace":
        phase_count = max(int(trace_summary.get("phase_count", 0)), 1)
        all_reduce_ratio = int(trace_summary.get("all_reduce_count", 0)) / phase_count
        high_route_ratio = int(trace_summary.get("high_route_phase_count", 0)) / phase_count
        high_memory_ratio = int(trace_summary.get("high_memory_phase_count", 0)) / phase_count
        return all_reduce_ratio * 0.55 + high_route_ratio * 0.40 + high_memory_ratio * 0.30
    return 0.0


def derive_mapping_model(
    point: NormalizedPoint,
    state: SearchState,
    motif: Dict[str, float],
    bundle: Any,
    graph: WorkloadGraph | None = None,
    partition_plan: PartitionPlan | None = None,
    placement_plan: PlacementPlan | None = None,
    layout_model: LayoutModel | None = None,
    buffer_usage: BufferUsageResult | None = None,
    layer_engine_plan: LayerEnginePlan | None = None,
) -> MappingModelResult:
    del bundle
    geom = geometry(point)
    chiplet_count = max(geom["chiplet_count"], 1)
    trace_summary = point.workload_trace_summary or {}

    layer_count = BASE_LAYER_COUNT.get(point.workload_motif or point.workload_name, 16)
    if trace_summary.get("phase_count"):
        layer_count += max(int(trace_summary["phase_count"]) // 2, 1)
    if trace_summary.get("expert_count"):
        layer_count += max(int(trace_summary["expert_count"]) // 4, 1)
    if graph is not None:
        layer_count = len(graph.layers)
    if layer_engine_plan is not None:
        layer_count = len(layer_engine_plan.layer_records)

    segment_count = max(1, math.ceil(layer_count / max(state.segment_span, 1)))
    if placement_plan is not None and placement_plan.layer_placements:
        segment_count = max(placement.segment_id for placement in placement_plan.layer_placements) + 1
    if layer_engine_plan is not None and layer_engine_plan.segment_records:
        segment_count = len(layer_engine_plan.segment_records)

    boundary_count = max(segment_count - 1, 0)
    if layout_model is not None:
        boundary_count = layout_model.segment_crossing_count
    if layer_engine_plan is not None:
        boundary_count = len(layer_engine_plan.segment_scheme.boundaries_after)

    pipeline_wave_count = max(1, state.pipeline_depth + boundary_count)
    trace_collective_pressure = _collective_pressure(trace_summary)

    average_chiplet_span = float(max(chiplet_count, 1))
    avg_partition_util = 1.0
    if placement_plan is not None and placement_plan.layer_placements:
        core_chiplet = {coord.core_id: coord.chiplet_id for coord in placement_plan.core_coords}
        spans = [len({core_chiplet[core_id] for core_id in placement.partition_to_core}) for placement in placement_plan.layer_placements]
        average_chiplet_span = sum(spans) / max(len(spans), 1)
    if layer_engine_plan is not None and layer_engine_plan.segment_records:
        average_chiplet_span = sum(len(segment.active_chiplets) for segment in layer_engine_plan.segment_records) / len(layer_engine_plan.segment_records)
        avg_partition_util = sum(record.mapped_utilization for record in layer_engine_plan.layer_records) / max(len(layer_engine_plan.layer_records), 1)

    placement_dispersion = clamp(
        0.05
        + (average_chiplet_span - 1.0) / max(chiplet_count - 1, 1)
        + abs(state.placement_skew) * 0.18,
        0.05,
        1.25,
    )

    if partition_plan is not None and partition_plan.layer_plans and layer_engine_plan is None:
        avg_partition_util = sum(layer_plan.utilization for layer_plan in partition_plan.layer_plans) / len(partition_plan.layer_plans)

    collective_layer_fraction = 0.0
    expert_fraction = 0.0
    if graph is not None and graph.layers:
        collective_layer_fraction = sum(1 for layer in graph.layers if layer.collective_kind or layer.kind in {"attention", "collective", "dispatch", "combine"}) / len(graph.layers)
        expert_fraction = sum(1 for layer in graph.layers if layer.kind == "expert_ffn") / len(graph.layers)
    if layer_engine_plan is not None and layer_engine_plan.layer_records:
        collective_layer_fraction = sum(1 for record in layer_engine_plan.layer_records if record.multicast_fanout > 0) / len(layer_engine_plan.layer_records)
        expert_fraction = sum(1 for record in layer_engine_plan.layer_records if graph is not None and graph.layers[record.layer_index].kind == "expert_ffn") / len(layer_engine_plan.layer_records)

    collective_pressure = clamp(
        trace_collective_pressure
        + collective_layer_fraction * 0.45
        + expert_fraction * 0.20
        + (boundary_count / max(layer_count, 1)) * 0.30
        + (
            sum(record.multicast_fanout for record in layer_engine_plan.layer_records) / max(len(layer_engine_plan.layer_records), 1) * 0.03
            if layer_engine_plan is not None and layer_engine_plan.layer_records
            else 0.0
        ),
        0.0,
        1.6,
    )

    locality_terms = [
        float(motif["locality"]),
        clamp(1.0 - placement_dispersion * 0.55, 0.0, 1.0),
        avg_partition_util,
    ]
    if layout_model is not None:
        locality_terms.append(layout_model.locality_score)
    if layer_engine_plan is not None and layer_engine_plan.segment_records:
        locality_terms.append(
            clamp(
                1.0
                - (
                    sum(len(segment.shortcut_inputs) for segment in layer_engine_plan.segment_records)
                    / max(layer_count, 1)
                )
                * 0.25,
                0.0,
                1.0,
            )
        )
    locality_score = clamp(sum(locality_terms) / len(locality_terms) + (0.03 if state.batch_cluster else -0.02), 0.10, 0.98)

    cross_chip_share = clamp(
        (1.0 - locality_score) * 0.72
        + ((average_chiplet_span - 1.0) / max(chiplet_count, 1)) * 0.35
        + 0.10 * collective_pressure
        + 0.02 * boundary_count,
        0.0,
        1.45,
    )
    multicast_degree = clamp(
        1.0
        + collective_layer_fraction * max(average_chiplet_span, 1.0)
        + 0.14 * max(state.mapping_tiling - 1, 0)
        + 0.08 * expert_fraction * max(chiplet_count - 1, 0),
        1.0,
        float(max(chiplet_count, 1)),
    )
    multicast_efficiency = clamp(0.84 + 0.10 * avg_partition_util + 0.06 * (multicast_degree - 1.0) - 0.08 * placement_dispersion, 0.70, 1.35)

    buffer_pressure = 0.0
    working_set_ratio = float(motif["memory_factor"])
    if buffer_usage is not None:
        capacity_bytes = point.ul3_bytes_per_core
        working_set_ratio = max(buffer_usage.peak_bytes / max(capacity_bytes, 1), 0.25)
        buffer_pressure = buffer_usage.overflow_ratio

    remote_weight_share = layout_model.remote_weight_share if layout_model is not None else 0.0
    spm_residency = clamp(
        0.42
        + 0.14 * state.spm_level
        + 0.05 * state.memory_prefetch
        + 0.06 * avg_partition_util
        - 0.10 * remote_weight_share
        - 0.18 * buffer_pressure,
        0.08,
        0.98,
    )
    spm_overflow_ratio = clamp(max(buffer_pressure, 1.0 - spm_residency * (1.0 + 0.08 * state.mapping_tiling)), 0.0, 1.25)
    weight_reuse_factor = clamp(0.95 + 0.14 * state.mapping_tiling + 0.08 * state.spm_level + 0.10 * avg_partition_util - 0.04 * remote_weight_share, 0.80, 2.30)
    activation_reuse_factor = clamp(
        0.90
        + 0.22 * locality_score
        + 0.04 * state.segment_span
        + 0.03 * state.pipeline_depth
        + (0.06 if state.batch_cluster else 0.0),
        0.85,
        2.20,
    )
    batch_reuse_factor = clamp(0.92 + 0.12 * (1 if state.batch_cluster else 0) + 0.05 * state.mapping_tiling + 0.04 * avg_partition_util, 0.80, 1.70)
    memory_stream_count = max(
        1,
        min(
            chiplet_count if chiplet_count > 1 else 2,
            1 + state.memory_prefetch + int(buffer_pressure > 0.0) + int(remote_weight_share > 0.20),
        ),
    )
    working_set_scale = clamp(
        working_set_ratio
        * (1.0 + 0.08 * boundary_count + 0.08 * collective_pressure + 0.04 * remote_weight_share),
        0.60,
        2.60,
    )
    latency_sensitivity = clamp(
        1.0
        + 0.08 * boundary_count
        + 0.12 * collective_pressure
        + 0.06 * float(motif["route_factor"])
        + 0.10 * buffer_pressure,
        1.0,
        2.7,
    )

    return MappingModelResult(
        estimated_layer_count=layer_count,
        segment_count=segment_count,
        boundary_count=boundary_count,
        pipeline_wave_count=pipeline_wave_count,
        locality_score=locality_score,
        placement_dispersion=placement_dispersion,
        cross_chip_share=cross_chip_share,
        multicast_degree=multicast_degree,
        multicast_efficiency=multicast_efficiency,
        spm_residency=spm_residency,
        spm_overflow_ratio=spm_overflow_ratio,
        weight_reuse_factor=weight_reuse_factor,
        activation_reuse_factor=activation_reuse_factor,
        batch_reuse_factor=batch_reuse_factor,
        memory_stream_count=memory_stream_count,
        working_set_scale=working_set_scale,
        collective_pressure=collective_pressure,
        latency_sensitivity=latency_sensitivity,
    )
