from __future__ import annotations

import math
from typing import Any, Dict

from .buffer_model import BufferUsageResult
from .common_math import clamp
from .data_layout import LayoutModel
from .layer_engine import LayerEnginePlan
from .models import LatencyModelResult, MappingModelResult, NormalizedPoint, SearchState, TrafficModelResult
from .registries import interface_metrics
from .workload_graph import WorkloadGraph


MICROARCH_PERF = {
    "polar": 1.00,
    "eyeriss": 0.93,
}


def compute_latency_model(
    point: NormalizedPoint,
    state: SearchState,
    mapping: MappingModelResult,
    traffic: TrafficModelResult,
    motif: Dict[str, float],
    profile: Any,
    bundle: Any,
    graph: WorkloadGraph | None = None,
    layout_model: LayoutModel | None = None,
    buffer_usage: BufferUsageResult | None = None,
    layer_engine_plan: LayerEnginePlan | None = None,
) -> LatencyModelResult:
    process_cfg = bundle.process_nodes.get(point.tech, {})
    frequency_ghz = float(process_cfg.get("frequency_ghz", 1.0))
    process_perf = 1.0 + (frequency_ghz - 1.0) * 0.55
    microarch_perf = MICROARCH_PERF.get(point.microarch_name, 1.0)
    interface_info = interface_metrics(bundle, point.IO_type, point.package_type, point.tech)

    compute_util = clamp(
        0.56
        + 0.08 * state.mapping_tiling
        + 0.04 * state.pipeline_depth
        + 0.04 * state.spm_level
        + (0.03 if state.interleave else 0.0)
        + (0.03 if state.batch_cluster else -0.01)
        - 0.05 * mapping.placement_dispersion
        - 0.03 * mapping.spm_overflow_ratio,
        0.42,
        1.32,
    )
    workload_scale = 1.0 + float(motif["edge_factor"]) + 0.55 * float(motif["memory_factor"]) + 0.30 * float(motif["route_factor"])
    graph_depth = 1
    graph_scale = 1.0
    mapped_compute_cycles = 0
    mapped_util = compute_util
    if layer_engine_plan is not None and layer_engine_plan.layer_records:
        graph_depth = len(layer_engine_plan.layer_records)
        mapped_compute_cycles = sum(record.compute_cycles for record in layer_engine_plan.layer_records)
        mapped_util = sum(record.mapped_utilization for record in layer_engine_plan.layer_records) / len(layer_engine_plan.layer_records)
        schedule_depth = max(layer_engine_plan.schedule_tree.height, 1)
        graph_scale *= clamp(1.0 + 0.04 * schedule_depth, 0.9, 1.4)
    elif graph is not None and graph.layers:
        graph_depth = len(graph.layers)
        graph_volume = sum(layer.output_bytes + int(layer.weight_bytes * 0.35) for layer in graph.layers)
        graph_scale = clamp(math.log2(max(graph_volume, 2)) / 18.0, 0.78, 1.45)

    if mapped_compute_cycles > 0:
        compute_cycles = int(math.ceil(mapped_compute_cycles * profile.score_bias / max(process_perf * microarch_perf, 0.1) / max(mapped_util, 0.15)))
    else:
        effective_compute = max(float(point.tops_target_tops) * process_perf * microarch_perf * compute_util, 1.0)
        compute_cycles = int(float(point.tops_target_tops) * 32_000.0 * workload_scale / effective_compute * profile.score_bias * graph_scale)

    segment_crossings = layout_model.segment_crossing_count if layout_model is not None else mapping.boundary_count
    buffer_penalty = 1.0 + (0.18 * buffer_usage.overflow_ratio if buffer_usage is not None else 0.0)
    stage_pressure = 0.0
    if layer_engine_plan is not None and layer_engine_plan.segment_records:
        stage_pressure = sum(segment.stage_count for segment in layer_engine_plan.segment_records) / max(len(layer_engine_plan.segment_records), 1)

    noc_service_cycles = math.ceil(
        compute_cycles
        * max(traffic.noc_pressure, 0.02)
        * (0.22 + 0.06 * traffic.average_noc_hops + 0.04 * mapping.collective_pressure + 0.02 * stage_pressure)
    )
    nop_service_cycles = math.ceil(
        compute_cycles
        * max(traffic.nop_pressure, 0.02)
        * (0.24 + 0.08 * traffic.average_nop_hops + 0.03 * segment_crossings + 0.03 * stage_pressure)
    )
    dram_service_cycles = math.ceil(
        compute_cycles
        * max(traffic.dram_pressure, 0.02)
        * (0.30 + 0.08 * mapping.working_set_scale + 0.08 * mapping.spm_overflow_ratio)
        * buffer_penalty
    )
    endpoint_latency_cycles = int(
        12
        + traffic.average_nop_hops * (2.0 + 0.85 * interface_info["hop_cost"])
        + 3.0 * math.log2(max(graph_depth, 2))
        + 6.0 * mapping.collective_pressure
        + (2.0 * max(layer_engine_plan.schedule_tree.height - 1, 0) if layer_engine_plan is not None else 0.0)
        + (4.0 if point.chiplet_count > 1 else 1.0)
    )
    segment_sync_cycles = int(
        segment_crossings * (12 + 4 * state.pipeline_depth)
        + max(mapping.segment_count - 1, 0) * 8 * (0.7 if state.interleave else 1.0)
        + (sum(len(segment.shortcut_inputs) for segment in layer_engine_plan.segment_records) * 3 if layer_engine_plan is not None else 0)
    )
    overlap_discount = clamp(
        0.16
        + 0.07 * state.memory_prefetch
        + (0.05 if state.interleave else 0.0)
        - (0.05 * buffer_usage.overflow_ratio if buffer_usage is not None else 0.0),
        0.0,
        0.45,
    )
    communication_cycles = max(noc_service_cycles, nop_service_cycles, dram_service_cycles) + endpoint_latency_cycles + segment_sync_cycles
    total_cycles = int(compute_cycles + communication_cycles * (1.0 - overlap_discount))

    return LatencyModelResult(
        compute_cycles=compute_cycles,
        noc_service_cycles=noc_service_cycles,
        nop_service_cycles=nop_service_cycles,
        dram_service_cycles=dram_service_cycles,
        endpoint_latency_cycles=endpoint_latency_cycles,
        segment_sync_cycles=segment_sync_cycles,
        overlap_discount=overlap_discount,
        total_cycles=total_cycles,
    )
