from __future__ import annotations

from typing import Dict, List

from .models import LegalityAssessment, NormalizedPoint


def geometry_from_partition(xx: int, yy: int, xcut: int, ycut: int) -> Dict[str, int]:
    chiplet_count = xcut * ycut
    x_step = xx // xcut
    y_step = yy // ycut
    if chiplet_count == 1:
        per_die_exposed_edges = 0
    elif chiplet_count == 2:
        per_die_exposed_edges = 2 * y_step
    else:
        per_die_exposed_edges = 2 * x_step + 2 * y_step
    total_exposed_edge_slots = per_die_exposed_edges * max(chiplet_count, 1)
    return {
        "chiplet_count": chiplet_count,
        "x_step": x_step,
        "y_step": y_step,
        "per_die_exposed_edges": per_die_exposed_edges,
        "total_exposed_edge_slots": total_exposed_edge_slots,
    }


def geometry(point: NormalizedPoint) -> Dict[str, int]:
    return geometry_from_partition(point.xx, point.yy, point.xcut, point.ycut)


def build_traffic_matrix(chiplet_count: int, total_interchip_bw: float, locality: float) -> List[List[float]]:
    if chiplet_count <= 1:
        return [[0.0]]

    matrix = [[0.0 for _ in range(chiplet_count)] for _ in range(chiplet_count)]
    offdiag_pairs = chiplet_count * (chiplet_count - 1)
    base_share = total_interchip_bw * (1.0 - locality) / offdiag_pairs if offdiag_pairs else 0.0
    neighbor_share = total_interchip_bw * locality / (2 * chiplet_count)

    for src in range(chiplet_count):
        for dst in range(chiplet_count):
            if src == dst:
                continue
            matrix[src][dst] = base_share

    for src in range(chiplet_count):
        matrix[src][(src + 1) % chiplet_count] += neighbor_share
        matrix[src][(src - 1) % chiplet_count] += neighbor_share

    return [[round(value, 6) for value in row] for row in matrix]


def assess_legality(
    edge_capacity: float,
    edge_demand: float,
    route_budget: float,
    route_demand: float,
    available_memory_bw: float,
    memory_required_bw: float,
    channel_count_available: int,
    channel_count_required: int,
    io_competition_score: float,
    noc_capacity: float | None = None,
    noc_demand: float | None = None,
    peak_dram_channel_gbps: float | None = None,
    channel_bandwidth_gbps: float | None = None,
    buffer_capacity_bytes: int | None = None,
    peak_buffer_bytes: int | None = None,
    overflow_core_count: int = 0,
    buffer_overflow_ratio: float = 0.0,
) -> LegalityAssessment:
    illegal_reasons: List[str] = []
    edge_margin = edge_capacity - edge_demand
    route_margin = route_budget - route_demand
    memory_margin = available_memory_bw - memory_required_bw
    noc_margin = (noc_capacity - noc_demand) if noc_capacity is not None and noc_demand is not None else 0.0
    dram_channel_margin = (
        channel_bandwidth_gbps - peak_dram_channel_gbps
        if channel_bandwidth_gbps is not None and peak_dram_channel_gbps is not None
        else 0.0
    )
    buffer_margin = (
        float(buffer_capacity_bytes - peak_buffer_bytes)
        if buffer_capacity_bytes is not None and peak_buffer_bytes is not None
        else 0.0
    )

    edge_legal = edge_margin >= 0.0
    route_legal = route_margin >= 0.0
    buffer_legal = buffer_margin >= 0.0 and overflow_core_count == 0 and buffer_overflow_ratio <= 0.0
    memory_legal = memory_margin >= 0.0 and channel_count_available >= channel_count_required and io_competition_score <= 1.0 and buffer_legal
    noc_legal = noc_margin >= 0.0 if noc_capacity is not None and noc_demand is not None else True
    dram_channel_legal = dram_channel_margin >= 0.0 if channel_bandwidth_gbps is not None and peak_dram_channel_gbps is not None else True

    if not edge_legal:
        illegal_reasons.append("edge_capacity_exceeded")
    if not route_legal:
        illegal_reasons.append("route_budget_exceeded")
    if not noc_legal:
        illegal_reasons.append("noc_bandwidth_exceeded")
    if not memory_legal:
        if memory_margin < 0.0:
            illegal_reasons.append("memory_bandwidth_exceeded")
        if channel_count_available < channel_count_required:
            illegal_reasons.append("memory_channel_count_exceeded")
        if io_competition_score > 1.0:
            illegal_reasons.append("io_die_area_exceeded")
        if not buffer_legal:
            illegal_reasons.append("buffer_capacity_exceeded")
    if not dram_channel_legal:
        illegal_reasons.append("memory_channel_peak_exceeded")

    legal = edge_legal and route_legal and memory_legal and noc_legal and dram_channel_legal
    return LegalityAssessment(
        legal=legal,
        legality_flags={
            "edge": "legal" if edge_legal else "illegal",
            "route": "legal" if route_legal else "illegal",
            "noc": "legal" if noc_legal else "illegal",
            "memory": "legal" if memory_legal else "illegal",
            "buffer": "legal" if buffer_legal else "illegal",
            "memory_channel": "legal" if dram_channel_legal else "illegal",
            "overall": "legal" if legal else "illegal",
        },
        illegal_reasons=illegal_reasons,
        derived_terms={
            "edge_margin": edge_margin,
            "route_margin": route_margin,
            "memory_margin": memory_margin,
            "noc_margin": noc_margin,
            "dram_channel_margin": dram_channel_margin,
            "buffer_margin": buffer_margin,
            "channel_count_available": float(channel_count_available),
            "channel_count_required": float(channel_count_required),
            "io_competition_score": io_competition_score,
            "overflow_core_count": float(overflow_core_count),
            "buffer_overflow_ratio": buffer_overflow_ratio,
        },
    )
