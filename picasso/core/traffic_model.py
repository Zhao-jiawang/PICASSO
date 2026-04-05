from __future__ import annotations

import math
from typing import Any, Dict, List, Tuple

from .common_math import clamp
from .data_layout import FeatureMapRange, LayoutModel
from .layer_engine import LayerEnginePlan
from .legality import geometry
from .models import MappingModelResult, NormalizedPoint, SearchState, TrafficModelResult
from .placement_engine import CoreCoord, PlacementPlan
from .registries import interface_metrics
from .workload_graph import WorkloadGraph


Coord = Tuple[int, int]
BANDWIDTH_NORMALIZER = 64.0


def chiplet_coordinates(xcut: int, ycut: int) -> List[Coord]:
    return [(x, y) for y in range(ycut) for x in range(xcut)]


def chiplet_distance(src: Coord, dst: Coord) -> int:
    return abs(src[0] - dst[0]) + abs(src[1] - dst[1])


def build_traffic_matrix(chiplet_count: int, total_interchip_bw: float, locality: float, xcut: int = 1, ycut: int = 1) -> List[List[float]]:
    if chiplet_count <= 1:
        return [[0.0]]

    coords = chiplet_coordinates(xcut, ycut)
    weights: Dict[Tuple[int, int], float] = {}
    total_weight = 0.0
    for src in range(chiplet_count):
        for dst in range(chiplet_count):
            if src == dst:
                continue
            dist = max(chiplet_distance(coords[src], coords[dst]), 1)
            weight = (1.0 / dist) * (1.0 + (1.75 * locality if dist == 1 else -0.35 * locality))
            weight = max(weight, 0.05)
            weights[(src, dst)] = weight
            total_weight += weight

    matrix = [[0.0 for _ in range(chiplet_count)] for _ in range(chiplet_count)]
    if total_weight <= 0.0:
        return matrix

    for (src, dst), weight in weights.items():
        matrix[src][dst] = round(total_interchip_bw * weight / total_weight, 6)
    return matrix


def _range_overlap(lhs: FeatureMapRange, rhs: FeatureMapRange) -> int:
    return lhs.intersect(rhs).volume


def _is_nop_x(boundary_x: int, point: NormalizedPoint) -> bool:
    if point.xcut <= 1:
        return False
    x_step = max(point.xx // point.xcut, 1)
    return boundary_x // x_step != (boundary_x + 1) // x_step


def _is_nop_y(boundary_y: int, point: NormalizedPoint) -> bool:
    if point.ycut <= 1:
        return False
    y_step = max(point.yy // point.ycut, 1)
    return boundary_y // y_step != (boundary_y + 1) // y_step


def _adaptive_policy(src: CoreCoord, dst: CoreCoord, fallback: str) -> str:
    dx = abs(dst.x - src.x)
    dy = abs(dst.y - src.y)
    if dx == dy:
        return fallback
    return "xy" if dx >= dy else "yx"


def _path_segments(src: CoreCoord, dst: CoreCoord, point: NormalizedPoint, axis_order: Tuple[str, str]) -> List[Tuple[str, Tuple[str, int, int]]]:
    current_x = src.x
    current_y = src.y
    segments: List[Tuple[str, Tuple[str, int, int]]] = []
    for axis in axis_order:
        if axis == "x":
            step = 1 if dst.x >= current_x else -1
            for x in range(current_x, dst.x, step):
                boundary_x = x if step > 0 else x - 1
                key = ("x", boundary_x, current_y)
                segments.append(("nop" if _is_nop_x(boundary_x, point) else "noc", key))
            current_x = dst.x
        else:
            step = 1 if dst.y >= current_y else -1
            for y in range(current_y, dst.y, step):
                boundary_y = y if step > 0 else y - 1
                key = ("y", current_x, boundary_y)
                segments.append(("nop" if _is_nop_y(boundary_y, point) else "noc", key))
            current_y = dst.y
    return segments


def _path_score(
    segments: List[Tuple[str, Tuple[str, int, int]]],
    bandwidth: float,
    noc_links: Dict[Tuple[str, int, int], float],
    nop_links: Dict[Tuple[str, int, int], float],
) -> Tuple[float, float, int]:
    if not segments:
        return 0.0, 0.0, 0
    loads = []
    for target_name, key in segments:
        target = nop_links if target_name == "nop" else noc_links
        loads.append(target.get(key, 0.0) + bandwidth)
    return max(loads), sum(loads), len(segments)


def _apply_segments(
    segments: List[Tuple[str, Tuple[str, int, int]]],
    bandwidth: float,
    noc_links: Dict[Tuple[str, int, int], float],
    nop_links: Dict[Tuple[str, int, int], float],
) -> Tuple[int, int]:
    noc_hops = 0
    nop_hops = 0
    for target_name, key in segments:
        target = nop_links if target_name == "nop" else noc_links
        target[key] = target.get(key, 0.0) + bandwidth
        if target_name == "nop":
            nop_hops += 1
        else:
            noc_hops += 1
    return noc_hops, nop_hops


def _channel_ids_by_chiplet(chiplet_count: int, channel_count_available: int) -> Dict[int, Tuple[int, ...]]:
    if chiplet_count <= 0 or channel_count_available <= 0:
        return {chiplet_id: (0,) for chiplet_id in range(max(chiplet_count, 1))}
    mapping: Dict[int, List[int]] = {chiplet_id: [] for chiplet_id in range(chiplet_count)}
    for channel_id in range(channel_count_available):
        mapping[channel_id % chiplet_count].append(channel_id)
    for chiplet_id in range(chiplet_count):
        if not mapping[chiplet_id]:
            mapping[chiplet_id].append(chiplet_id % channel_count_available)
    return {chiplet_id: tuple(channel_ids) for chiplet_id, channel_ids in mapping.items()}


def _route_with_policy(
    src: CoreCoord,
    dst: CoreCoord,
    bandwidth: float,
    point: NormalizedPoint,
    policy: str,
    noc_links: Dict[Tuple[str, int, int], float],
    nop_links: Dict[Tuple[str, int, int], float],
) -> Tuple[int, int]:
    if src.x == dst.x and src.y == dst.y:
        return 0, 0

    fallback = _adaptive_policy(src, dst, "xy" if point.chiplet_count <= 1 else "yx")
    if policy == "adaptive":
        xy_segments = _path_segments(src, dst, point, ("x", "y"))
        yx_segments = _path_segments(src, dst, point, ("y", "x"))
        xy_score = _path_score(xy_segments, bandwidth, noc_links, nop_links)
        yx_score = _path_score(yx_segments, bandwidth, noc_links, nop_links)
        segments = xy_segments if xy_score <= yx_score else yx_segments
    else:
        axis_order = ("x", "y") if policy == "xy" else ("y", "x")
        if policy not in {"xy", "yx"}:
            axis_order = ("x", "y") if fallback == "xy" else ("y", "x")
        segments = _path_segments(src, dst, point, axis_order)
    return _apply_segments(segments, bandwidth, noc_links, nop_links)


def _chiplet_anchor(point: NormalizedPoint, chiplet_id: int, row_bias: int, ingress: bool) -> CoreCoord:
    x_step = max(point.xx // max(point.xcut, 1), 1)
    y_step = max(point.yy // max(point.ycut, 1), 1)
    chiplet_x = chiplet_id % max(point.xcut, 1)
    chiplet_y = chiplet_id // max(point.xcut, 1)
    x_min = chiplet_x * x_step
    x_max = min(x_min + x_step - 1, point.xx - 1)
    y_min = chiplet_y * y_step
    y_max = min(y_min + y_step - 1, point.yy - 1)

    if chiplet_x == 0:
        x = x_min
    elif chiplet_x == point.xcut - 1:
        x = x_max
    else:
        x = x_min if ingress else x_max

    y = min(max(row_bias, y_min), y_max)
    if chiplet_y == 0 and ingress:
        y = y_min
    elif chiplet_y == point.ycut - 1 and not ingress:
        y = y_max

    return CoreCoord(
        core_id=-1,
        x=x,
        y=y,
        chiplet_x=chiplet_x,
        chiplet_y=chiplet_y,
        chiplet_id=chiplet_id,
    )


def _chiplet_coord(point: NormalizedPoint, chiplet_id: int) -> Coord:
    return chiplet_id % max(point.xcut, 1), chiplet_id // max(point.xcut, 1)


def _group_by_chiplet(core_ids: Tuple[int, ...], core_lookup: Dict[int, CoreCoord]) -> Dict[int, List[int]]:
    grouped: Dict[int, List[int]] = {}
    for core_id in core_ids:
        grouped.setdefault(core_lookup[core_id].chiplet_id, []).append(core_id)
    return grouped


def evaluate_traffic_model(
    point: NormalizedPoint,
    state: SearchState,
    mapping: MappingModelResult,
    motif: Dict[str, float],
    bundle: Any,
    service_window_cycles: int,
    graph: WorkloadGraph,
    layout_model: LayoutModel,
    placement_plan: PlacementPlan,
    layer_engine_plan: LayerEnginePlan | None = None,
) -> TrafficModelResult:
    geom = geometry(point)
    chiplet_count = max(geom["chiplet_count"], 1)
    interface_eff = float(bundle.legality["interface_efficiency"][point.IO_type])
    route_scale = float(bundle.legality["package_route_scale"][point.package_type])
    channel_bw = float(bundle.legality["memory_channel_bandwidth_gbps"][point.ddr_type])
    lane_rate = float(bundle.legality["interface_lane_rate_gbps"][point.IO_type])
    interface_info = interface_metrics(bundle, point.IO_type, point.package_type, point.tech)
    channel_count_available = max(1, math.ceil(point.memory_bandwidth_gbps / channel_bw))
    channel_map = _channel_ids_by_chiplet(chiplet_count, channel_count_available)
    channel_loads = {channel_id: 0.0 for channel_id in range(channel_count_available)}
    memory_pressure_scale = 1.0 + max(1.0 - mapping.spm_residency, 0.0)

    core_lookup = {coord.core_id: coord for coord in placement_plan.core_coords}
    layer_layouts = {layout.layer_index: layout for layout in layout_model.layer_layouts}
    layer_records = layer_engine_plan.layer_by_index if layer_engine_plan is not None else {}
    light_layers = layer_engine_plan.light_placement.layer_by_index if layer_engine_plan is not None else {}

    chiplet_pair_volume: Dict[Tuple[int, int], float] = {}
    noc_links: Dict[Tuple[str, int, int], float] = {}
    nop_links: Dict[Tuple[str, int, int], float] = {}
    total_noc_hop_volume = 0.0
    total_nop_hop_volume = 0.0
    total_dram_access_volume = 0.0
    total_interchip_volume = 0.0
    local_activation_hits = 0.0
    total_activation_hits = 0.0
    memory_volume = 0.0
    writeback_volume = 0.0

    def route_coords(src: CoreCoord, dst: CoreCoord, volume: float, policy: str) -> None:
        nonlocal total_noc_hop_volume, total_nop_hop_volume, total_interchip_volume
        if volume <= 0.0 or (src.x == dst.x and src.y == dst.y):
            return
        bandwidth = volume / max(service_window_cycles * BANDWIDTH_NORMALIZER, 1.0)
        noc_hops, nop_hops = _route_with_policy(src, dst, bandwidth, point, policy, noc_links, nop_links)
        total_noc_hop_volume += volume * noc_hops
        total_nop_hop_volume += volume * nop_hops
        if src.chiplet_id != dst.chiplet_id:
            total_interchip_volume += volume
            chiplet_pair_volume[(src.chiplet_id, dst.chiplet_id)] = chiplet_pair_volume.get((src.chiplet_id, dst.chiplet_id), 0.0) + volume

    def route_pair(src_core: int, dst_core: int, volume: float, policy: str) -> None:
        if volume <= 0.0 or src_core == dst_core:
            return
        route_coords(core_lookup[src_core], core_lookup[dst_core], volume, policy)

    def add_unicast_flow(src_core: int, dst_core: int, volume: float, policy: str) -> None:
        route_pair(src_core, dst_core, volume, policy)

    def add_multicast_flow(src_core: int, dst_cores: Tuple[int, ...], volume: float, policy: str, root_core: int | None = None) -> None:
        unique_dsts = tuple(sorted({core_id for core_id in dst_cores if core_id != src_core}))
        if volume <= 0.0 or not unique_dsts:
            return
        actual_root = src_core if root_core is None or root_core < 0 else root_core
        if actual_root != src_core:
            route_pair(src_core, actual_root, volume, policy)
        grouped = _group_by_chiplet(unique_dsts, core_lookup)
        root_coord = core_lookup[actual_root]
        for chiplet_id, chiplet_dsts in grouped.items():
            chiplet_anchor = _chiplet_anchor(
                point,
                chiplet_id,
                row_bias=round(sum(core_lookup[core_id].y for core_id in chiplet_dsts) / max(len(chiplet_dsts), 1)),
                ingress=True,
            )
            representative = min(
                chiplet_dsts,
                key=lambda core_id: abs(core_lookup[core_id].x - chiplet_anchor.x) + abs(core_lookup[core_id].y - chiplet_anchor.y),
            )
            if chiplet_id != root_coord.chiplet_id:
                route_coords(root_coord, chiplet_anchor, volume, policy)
                route_coords(chiplet_anchor, core_lookup[representative], volume, policy)
            elif representative != actual_root:
                route_pair(actual_root, representative, volume, policy)
            for core_id in chiplet_dsts:
                if core_id != representative:
                    route_pair(representative, core_id, volume, policy)

    def add_memory_flow(core_id: int, volume: float, layer_index: int, tensor_kind: str, incoming: bool) -> None:
        nonlocal total_noc_hop_volume, total_nop_hop_volume, total_dram_access_volume, total_interchip_volume, memory_volume, writeback_volume
        if volume <= 0.0:
            return
        coord = core_lookup[core_id]
        policy = layer_records[layer_index].path_policy if layer_index in layer_records else ("adaptive" if state.interleave else "xy")
        scaled_volume = volume * memory_pressure_scale
        bandwidth = scaled_volume / max(service_window_cycles * BANDWIDTH_NORMALIZER, 1.0)
        chiplet_candidates: Tuple[int, ...]
        if layer_index in light_layers:
            attachment = light_layers[layer_index].dram_attachment
            if tensor_kind == "wgt":
                chiplet_candidates = attachment.weight_sources
            elif tensor_kind == "ofm":
                chiplet_candidates = attachment.ofmap_targets
            else:
                chiplet_candidates = attachment.ifmap_sources
        else:
            chiplet_candidates = (coord.chiplet_id,)
        candidate_pairs = []
        for chiplet_id in chiplet_candidates or (coord.chiplet_id,):
            for channel_id in channel_map.get(chiplet_id, (chiplet_id % channel_count_available,)):
                candidate_pairs.append(
                    (
                        channel_loads[channel_id],
                        chiplet_distance(_chiplet_coord(point, chiplet_id), (coord.chiplet_x, coord.chiplet_y)),
                        channel_id,
                        chiplet_id,
                    )
                )
        _, _, chosen_channel, chosen_chiplet = min(candidate_pairs) if candidate_pairs else (0.0, 0, 0, coord.chiplet_id)
        anchor = _chiplet_anchor(point, chosen_chiplet, coord.y, incoming)
        if incoming:
            noc_hops, nop_hops = _route_with_policy(anchor, coord, bandwidth, point, policy, noc_links, nop_links)
        else:
            noc_hops, nop_hops = _route_with_policy(coord, anchor, bandwidth, point, policy, noc_links, nop_links)
        total_noc_hop_volume += scaled_volume * noc_hops
        total_nop_hop_volume += scaled_volume * nop_hops
        if anchor.chiplet_id != coord.chiplet_id:
            total_interchip_volume += scaled_volume
            if incoming:
                chiplet_pair_volume[(anchor.chiplet_id, coord.chiplet_id)] = chiplet_pair_volume.get((anchor.chiplet_id, coord.chiplet_id), 0.0) + scaled_volume
            else:
                chiplet_pair_volume[(coord.chiplet_id, anchor.chiplet_id)] = chiplet_pair_volume.get((coord.chiplet_id, anchor.chiplet_id), 0.0) + scaled_volume
        channel_loads[chosen_channel] += bandwidth
        total_dram_access_volume += scaled_volume
        memory_volume += scaled_volume
        if not incoming:
            writeback_volume += scaled_volume

    for layer in graph.layers:
        layout = layer_layouts[layer.index]
        record = layer_records.get(layer.index)
        policy = record.path_policy if record is not None else ("adaptive" if state.interleave else "xy")
        root_core = light_layers[layer.index].multicast_root_core if layer.index in light_layers else None

        if not layer.prevs:
            for entry in layout.ifm_entries:
                add_memory_flow(entry.core_id, entry.tensor_range.volume, layer.index, "ifm", incoming=True)
        else:
            for prev_idx in layer.prevs:
                prev_layout = layer_layouts[prev_idx]
                if layer.collective_kind == "all_reduce":
                    if root_core is not None and root_core >= 0:
                        for src_entry in prev_layout.ofm_entries:
                            add_unicast_flow(src_entry.core_id, root_core, src_entry.tensor_range.volume / BANDWIDTH_NORMALIZER, policy)
                        add_multicast_flow(root_core, tuple(entry.core_id for entry in layout.ifm_entries), sum(entry.tensor_range.volume for entry in prev_layout.ofm_entries) / BANDWIDTH_NORMALIZER, policy, root_core=root_core)
                    continue
                if layer.collective_kind == "all_gather":
                    for src_entry in prev_layout.ofm_entries:
                        add_multicast_flow(src_entry.core_id, tuple(entry.core_id for entry in layout.ifm_entries), src_entry.tensor_range.volume / BANDWIDTH_NORMALIZER, policy, root_core=root_core)
                    continue

                for dst_entry in layout.ifm_entries:
                    matched_sources: List[Tuple[int, float]] = []
                    dst_hit = 0.0
                    for src_entry in prev_layout.ofm_entries:
                        overlap = _range_overlap(src_entry.tensor_range, dst_entry.tensor_range)
                        if overlap <= 0:
                            continue
                        volume = overlap * (1.0 + 0.10 * mapping.collective_pressure if layer.collective_kind in {"dispatch", "combine", "attention"} else 1.0)
                        matched_sources.append((src_entry.core_id, volume))
                        dst_hit += volume
                        total_activation_hits += volume
                        if src_entry.core_id == dst_entry.core_id:
                            local_activation_hits += volume
                    if not matched_sources:
                        add_memory_flow(dst_entry.core_id, dst_entry.tensor_range.volume, layer.index, "ifm", incoming=True)
                        continue
                    if layer.collective_kind in {"dispatch", "combine", "attention"} and len(matched_sources) > 1:
                        src_core = max(matched_sources, key=lambda item: item[1])[0]
                        add_multicast_flow(src_core, (dst_entry.core_id,), sum(volume for _, volume in matched_sources), policy, root_core=root_core)
                    else:
                        for src_core, volume in matched_sources:
                            add_unicast_flow(src_core, dst_entry.core_id, volume, policy)

        for entry in layout.wgt_entries:
            weight_multiplier = max(light_layers[layer.index].partition.fetch_weight if layer.index in light_layers else 1, 1)
            add_memory_flow(entry.core_id, entry.tensor_range.volume * weight_multiplier, layer.index, "wgt", incoming=True)

        if layer.writes_to_memory:
            for entry in layout.ofm_entries:
                add_memory_flow(entry.core_id, entry.tensor_range.volume, layer.index, "ofm", incoming=False)

    total_interchip_bw = total_interchip_volume / max(service_window_cycles * BANDWIDTH_NORMALIZER, 1.0)
    traffic_matrix = [[0.0 for _ in range(chiplet_count)] for _ in range(chiplet_count)]
    for (src_chiplet, dst_chiplet), volume in chiplet_pair_volume.items():
        traffic_matrix[src_chiplet][dst_chiplet] += volume / max(service_window_cycles * BANDWIDTH_NORMALIZER, 1.0)
    traffic_matrix = [[round(value, 6) for value in row] for row in traffic_matrix]

    peak_noc_link_gbps = max(noc_links.values(), default=0.0)
    peak_nop_link_gbps = max(nop_links.values(), default=0.0)
    available_memory_bw = point.memory_bandwidth_gbps * clamp(state.memory_balance, 0.70, 1.25)
    memory_required_bw = memory_volume / max(service_window_cycles * BANDWIDTH_NORMALIZER, 1.0)
    channel_count_required = max(1, math.ceil(memory_required_bw / channel_bw))
    peak_dram_channel_gbps = max(channel_loads.values(), default=0.0)

    edge_capacity = geom["total_exposed_edge_slots"] * point.nop_bw * interface_eff * (0.88 + (0.05 if state.interleave else 0.0))
    route_budget = edge_capacity * route_scale * clamp(state.route_slack, 0.65, 1.25)
    chiplet_egress = [sum(row) for row in traffic_matrix]
    chiplet_ingress = [sum(traffic_matrix[src][dst] for src in range(chiplet_count)) for dst in range(chiplet_count)]
    memory_edge_bandwidth = 0.0 if chiplet_count <= 1 else memory_required_bw / chiplet_count * (1.0 + 0.12 * layout_model.remote_weight_share)
    edge_demand = max(chiplet_egress + chiplet_ingress + [0.0]) + memory_edge_bandwidth
    route_demand = peak_nop_link_gbps + memory_edge_bandwidth
    phy_count = 0 if chiplet_count <= 1 else math.ceil((point.nop_bw * 8.0) / max(lane_rate, 1.0)) * max(geom["total_exposed_edge_slots"], 1)

    total_noc_bw = sum(noc_links.values())
    total_nop_bw = sum(nop_links.values())
    average_noc_hops = total_noc_hop_volume / max(total_noc_bw * service_window_cycles * BANDWIDTH_NORMALIZER, 1.0)
    average_nop_hops = total_nop_hop_volume / max(total_nop_bw * service_window_cycles * BANDWIDTH_NORMALIZER, 1.0)

    effective_noc_bw = max(point.noc * clamp(state.noc_balance, 0.75, 1.25), 1.0)
    effective_nop_bw = max(point.nop_bw * interface_eff * route_scale, 1.0)
    serialization_ratio = route_demand / effective_nop_bw if chiplet_count > 1 else 0.0
    peak_route_link_gbps = max(peak_noc_link_gbps, peak_nop_link_gbps)
    average_channel_bw = memory_required_bw / max(channel_count_available, 1)
    dram_channel_imbalance = (
        peak_dram_channel_gbps / max(average_channel_bw, 1e-9) - 1.0
        if average_channel_bw > 0.0
        else 0.0
    )
    noc_pressure = peak_noc_link_gbps / effective_noc_bw
    nop_pressure = route_demand / effective_nop_bw if chiplet_count > 1 else 0.0
    dram_pressure = peak_dram_channel_gbps / channel_bw

    inferred_locality = local_activation_hits / max(total_activation_hits, 1.0)
    locality = clamp((inferred_locality + layout_model.locality_score + mapping.locality_score) / 3.0, 0.0, 1.0)
    del interface_info, motif, bundle

    return TrafficModelResult(
        traffic_matrix=traffic_matrix,
        peak_noc_link_gbps=peak_noc_link_gbps,
        peak_nop_link_gbps=peak_nop_link_gbps,
        peak_route_link_gbps=peak_route_link_gbps,
        peak_dram_channel_gbps=peak_dram_channel_gbps,
        average_noc_hops=average_noc_hops,
        average_nop_hops=average_nop_hops,
        total_noc_hop_volume=total_noc_hop_volume,
        total_nop_hop_volume=total_nop_hop_volume,
        total_dram_access_volume=total_dram_access_volume,
        total_interchip_bw=total_interchip_bw,
        edge_demand=edge_demand,
        edge_capacity=edge_capacity,
        route_demand=route_demand,
        route_budget=route_budget,
        memory_required_bw=memory_required_bw,
        available_memory_bw=available_memory_bw,
        channel_count_available=channel_count_available,
        channel_count_required=channel_count_required,
        phy_count=phy_count,
        locality=locality,
        serialization_ratio=serialization_ratio,
        dram_channel_imbalance=dram_channel_imbalance,
        noc_pressure=noc_pressure,
        nop_pressure=nop_pressure,
        dram_pressure=dram_pressure,
    )
