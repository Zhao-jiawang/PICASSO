from __future__ import annotations

import math
from typing import Any, Dict

from .area_model import compute_area_model
from .baselines import BaselineProfile
from .buffer_model import evaluate_buffer_usage
from .common_math import clamp, stable_int
from .cost_model import compute_cost_model
from .data_layout import build_layout_model
from .layer_engine import build_layer_engine_plan
from .latency_model import compute_latency_model
from .legality import assess_legality, geometry
from .mapping_model import derive_mapping_model
from .models import EvaluationResult, NormalizedPoint, SearchState
from .partition_engine import choose_partition_plan
from .placement_engine import build_placement_plan
from .registries import interface_metrics, motif_model
from .traffic_model import evaluate_traffic_model
from .workload_graph import build_workload_graph


MICROARCH_PERF = {
    "polar": 1.00,
    "eyeriss": 0.93,
}


def _rough_service_window_cycles(point: NormalizedPoint, state: SearchState, motif: Dict[str, float], bundle: Any) -> int:
    process_cfg = bundle.process_nodes.get(point.tech, {})
    frequency_ghz = float(process_cfg.get("frequency_ghz", 1.0))
    process_perf = 1.0 + (frequency_ghz - 1.0) * 0.55
    microarch_perf = MICROARCH_PERF.get(point.microarch_name, 1.0)
    workload_scale = 1.0 + float(motif["edge_factor"]) + 0.55 * float(motif["memory_factor"]) + 0.30 * float(motif["route_factor"])
    compute_util = clamp(
        0.56
        + 0.08 * state.mapping_tiling
        + 0.04 * state.pipeline_depth
        + 0.04 * state.spm_level
        + (0.03 if state.interleave else 0.0)
        + (0.03 if state.batch_cluster else -0.01)
        - 0.05 * abs(state.placement_skew),
        0.42,
        1.32,
    )
    effective_compute = max(float(point.tops_target_tops) * process_perf * microarch_perf * compute_util, 1.0)
    return int(float(point.tops_target_tops) * 32_000.0 * workload_scale / effective_compute)


def _traffic_service_window_cycles(
    point: NormalizedPoint,
    state: SearchState,
    motif: Dict[str, float],
    bundle: Any,
    layer_engine_plan: Any,
    segment_count: int,
) -> int:
    base_window = _rough_service_window_cycles(point, state, motif, bundle)
    if layer_engine_plan is None or not layer_engine_plan.layer_records:
        return max(base_window, 1)

    stage_windows: Dict[int, Dict[int, int]] = {}
    for record in layer_engine_plan.layer_records:
        segment_stages = stage_windows.setdefault(record.segment_id, {})
        segment_stages[record.stage_id] = max(segment_stages.get(record.stage_id, 0), record.compute_cycles)

    serial_window = sum(sum(stage_cycles.values()) for stage_cycles in stage_windows.values())
    pipeline_overlap = max(min(max(state.pipeline_depth, 1), max(segment_count, 1)), 1)
    scheduled_window = int(math.ceil(serial_window / pipeline_overlap))
    return max(base_window, scheduled_window, 1)


def evaluate_candidate(point: NormalizedPoint, state: SearchState, profile: BaselineProfile, bundle: Any) -> EvaluationResult:
    geom = geometry(point)
    motif = dict(motif_model(bundle, point.workload_motif))
    trace_scalars = point.workload_trace_scalars or {}
    motif["edge_factor"] = float(motif["edge_factor"]) * float(trace_scalars.get("edge_factor_scale", 1.0))
    motif["route_factor"] = float(motif["route_factor"]) * float(trace_scalars.get("route_factor_scale", 1.0))
    motif["memory_factor"] = float(motif["memory_factor"]) * float(trace_scalars.get("memory_factor_scale", 1.0))

    graph = build_workload_graph(point)
    partition_plan = choose_partition_plan(point, state, graph)
    placement_plan = build_placement_plan(point, state, graph, partition_plan)
    layout_model = build_layout_model(graph, partition_plan, placement_plan)
    layer_engine_plan = build_layer_engine_plan(point, state, graph, partition_plan, placement_plan, layout_model, bundle)
    core_buffer_capacity_bytes = (
        layer_engine_plan.core_library.spec.ubuf.size_bytes
        + layer_engine_plan.core_library.spec.l1_activation.size_bytes
        + layer_engine_plan.core_library.spec.l1_weight.size_bytes
        + layer_engine_plan.core_library.spec.l1_output.size_bytes
        + layer_engine_plan.core_library.spec.l2_activation.size_bytes
        + layer_engine_plan.core_library.spec.l2_weight.size_bytes
        + layer_engine_plan.core_library.spec.l2_output.size_bytes
    )
    buffer_usage = evaluate_buffer_usage(
        point,
        layout_model,
        layer_engine_plan=layer_engine_plan,
        capacity_bytes=core_buffer_capacity_bytes,
    )

    area = compute_area_model(point, state, bundle, core_library=layer_engine_plan.core_library)
    mapping = derive_mapping_model(
        point,
        state,
        motif,
        bundle,
        graph=graph,
        partition_plan=partition_plan,
        placement_plan=placement_plan,
        layout_model=layout_model,
        buffer_usage=buffer_usage,
        layer_engine_plan=layer_engine_plan,
    )
    service_window_cycles = _traffic_service_window_cycles(
        point,
        state,
        motif,
        bundle,
        layer_engine_plan,
        mapping.segment_count,
    )
    traffic = evaluate_traffic_model(
        point,
        state,
        mapping,
        motif,
        bundle,
        service_window_cycles,
        graph,
        layout_model,
        placement_plan,
        layer_engine_plan=layer_engine_plan,
    )
    latency = compute_latency_model(
        point,
        state,
        mapping,
        traffic,
        motif,
        profile,
        bundle,
        graph=graph,
        layout_model=layout_model,
        buffer_usage=buffer_usage,
        layer_engine_plan=layer_engine_plan,
    )

    memory_cfg = bundle.memories[point.ddr_type]
    interface_info = interface_metrics(bundle, point.IO_type, point.package_type, point.tech)
    interface_eff = float(bundle.legality["interface_efficiency"][point.IO_type])
    channel_bw = float(bundle.legality["memory_channel_bandwidth_gbps"][point.ddr_type])
    effective_noc_bw = max(point.noc * clamp(state.noc_balance, 0.75, 1.25), 1.0)
    io_limit = float(bundle.legality["io_die_limit_mm2"])
    mono_limit = float(bundle.legality["mono_die_limit_mm2"])
    io_competition_score = area.io_die_area / (io_limit if geom["chiplet_count"] > 1 else mono_limit)

    legality = assess_legality(
        edge_capacity=traffic.edge_capacity,
        edge_demand=traffic.edge_demand,
        route_budget=traffic.route_budget,
        route_demand=traffic.route_demand,
        available_memory_bw=traffic.available_memory_bw,
        memory_required_bw=traffic.memory_required_bw,
        channel_count_available=traffic.channel_count_available,
        channel_count_required=traffic.channel_count_required,
        io_competition_score=io_competition_score,
        noc_capacity=effective_noc_bw,
        noc_demand=traffic.peak_noc_link_gbps,
        peak_dram_channel_gbps=traffic.peak_dram_channel_gbps,
        channel_bandwidth_gbps=channel_bw,
        buffer_capacity_bytes=core_buffer_capacity_bytes,
        peak_buffer_bytes=buffer_usage.peak_bytes,
        overflow_core_count=buffer_usage.overflow_core_count,
        buffer_overflow_ratio=buffer_usage.overflow_ratio,
    )

    workload_scale = 1.0 + float(motif["edge_factor"]) + 0.55 * float(motif["memory_factor"]) + 0.30 * float(motif["route_factor"])
    process_cfg = bundle.process_nodes.get(point.tech, {})
    frequency_ghz = float(process_cfg.get("frequency_ghz", 1.0))
    process_perf = 1.0 + (frequency_ghz - 1.0) * 0.55

    base_compute_energy = float(point.tops_target_tops) * 250_000.0 * workload_scale * profile.score_bias
    mapped_mac_energy = sum(record.mac_energy for record in layer_engine_plan.layer_records)
    mapped_buffer_energy = sum(record.buffer_energy for record in layer_engine_plan.layer_records)
    mapped_interconnect_energy = sum(record.interconnect_energy for record in layer_engine_plan.layer_records)
    mac_energy = max(mapped_mac_energy / max(process_perf, 0.1), base_compute_energy * 0.25) / max(mapping.weight_reuse_factor, 0.85)
    ubuf_energy = mapped_buffer_energy * 0.28
    buf_energy = mapped_buffer_energy * 0.52
    bus_energy = mapped_interconnect_energy * 0.40
    noc_energy = traffic.total_noc_hop_volume * 0.020 / max(clamp(state.noc_balance, 0.75, 1.25), 0.25)
    nop_energy = traffic.total_nop_hop_volume * interface_info["hop_cost"] * 0.022 / max(interface_eff, 0.30)
    dram_energy = traffic.total_dram_access_volume * (float(memory_cfg["dram_access_cost"]) / 84.0 + 0.35) * 0.018
    if geom["chiplet_count"] == 1:
        nop_energy *= 0.10
    if profile.name == "Memory-off":
        dram_energy *= 1.18
    total_energy = ubuf_energy + buf_energy + bus_energy + mac_energy + noc_energy + nop_energy + dram_energy
    edp = total_energy * latency.total_cycles

    cost = compute_cost_model(point, area, float(memory_cfg["unit_cost_per_gbps"]))

    if point.objective_name == "latency":
        objective_score = float(latency.total_cycles)
    elif point.objective_name == "energy":
        objective_score = total_energy
    else:
        objective_score = edp
    objective_score *= 1.0 + 0.002 * profile.rank + (stable_int(profile.name) % 17) * 1e-6
    if not legality.legal:
        objective_score *= 1.0 + 0.20 + 0.08 * len(legality.illegal_reasons)

    derived_terms = {
        **legality.derived_terms,
        "segment_count": float(mapping.segment_count),
        "boundary_count": float(mapping.boundary_count),
        "spm_residency": mapping.spm_residency,
        "spm_overflow_ratio": mapping.spm_overflow_ratio,
        "multicast_degree": mapping.multicast_degree,
        "collective_pressure": mapping.collective_pressure,
        "locality_score": mapping.locality_score,
        "layout_locality_score": layout_model.locality_score,
        "segment_crossing_count": float(layout_model.segment_crossing_count),
        "remote_weight_share": layout_model.remote_weight_share,
        "graph_layer_count": float(len(graph.layers)),
        "schedule_tree_height": float(layer_engine_plan.schedule_tree.height),
        "segment_stage_count_avg": sum(segment.stage_count for segment in layer_engine_plan.segment_records) / max(len(layer_engine_plan.segment_records), 1),
        "shortcut_input_count": float(sum(len(segment.shortcut_inputs) for segment in layer_engine_plan.segment_records)),
        "avg_partition_utilization": sum(layer_plan.utilization for layer_plan in partition_plan.layer_plans) / max(len(partition_plan.layer_plans), 1),
        "avg_mapped_utilization": sum(record.mapped_utilization for record in layer_engine_plan.layer_records) / max(len(layer_engine_plan.layer_records), 1),
        "peak_ubuf_bytes": float(max((record.ubuf_bytes for record in layer_engine_plan.layer_records), default=0)),
        "total_interchip_bw": traffic.total_interchip_bw,
        "peak_noc_link_gbps": traffic.peak_noc_link_gbps,
        "peak_nop_link_gbps": traffic.peak_nop_link_gbps,
        "peak_route_link_gbps": traffic.peak_route_link_gbps,
        "peak_dram_channel_gbps": traffic.peak_dram_channel_gbps,
        "dram_channel_imbalance": traffic.dram_channel_imbalance,
        "serialization_ratio": traffic.serialization_ratio,
        "compute_cycles": float(latency.compute_cycles),
        "noc_service_cycles": float(latency.noc_service_cycles),
        "nop_service_cycles": float(latency.nop_service_cycles),
        "dram_service_cycles": float(latency.dram_service_cycles),
        "endpoint_latency_cycles": float(latency.endpoint_latency_cycles),
        "segment_sync_cycles": float(latency.segment_sync_cycles),
        "phy_count": float(traffic.phy_count),
        "per_compute_die_area": area.per_compute_die_area,
        "compute_array_area": area.compute_array_area,
        "buffer_area": area.buffer_area,
        "control_area": area.control_area,
        "buffer_peak_bytes": float(buffer_usage.peak_bytes),
        "buffer_capacity_bytes": float(core_buffer_capacity_bytes),
        "buffer_average_bytes": buffer_usage.average_bytes,
        "buffer_overflow_core_count": float(buffer_usage.overflow_core_count),
        "buffer_overflow_ratio": buffer_usage.overflow_ratio,
        "raw_die_cost": cost.raw_die_cost,
        "defect_die_cost": cost.defect_die_cost,
        "raw_package_cost": cost.raw_package_cost,
        "package_defect_cost": cost.package_defect_cost,
        "assembly_waste_cost": cost.assembly_waste_cost,
        "chip_nre": cost.chip_nre,
        "module_nre": cost.module_nre,
        "package_nre": cost.package_nre,
        "amortized_nre_cost": cost.amortized_nre_cost,
        "package_area": cost.package_area,
        "interposer_area": cost.interposer_area,
        "distinct_chip_type_count": float(cost.distinct_chip_type_count),
    }

    return EvaluationResult(
        objective_score=objective_score,
        cycle=latency.total_cycles,
        energy=total_energy,
        edp=edp,
        cost_overall=cost.cost_soc,
        legal=legality.legal,
        legality_flags=legality.legality_flags,
        illegal_reasons=legality.illegal_reasons,
        energy_breakdown={
            "ubuf": ubuf_energy,
            "buf": buf_energy,
            "bus": bus_energy,
            "mac": mac_energy,
            "noc": noc_energy,
            "nop": nop_energy,
            "dram": dram_energy,
        },
        cost_breakdown={
            "cost_chip": cost.cost_chip,
            "cost_package": cost.cost_package,
            "cost_system_package": cost.cost_system_package,
            "cost_soc": cost.cost_soc,
        },
        die_area_breakdown={
            "compute_die_area": area.total_compute_area,
            "io_die_area": area.io_die_area,
            "total_die_area": area.total_die_area,
        },
        derived_terms=derived_terms,
    )
