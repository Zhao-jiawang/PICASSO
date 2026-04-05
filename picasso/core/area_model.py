from __future__ import annotations

from typing import Any

from .core_model import CoreLibrary, build_core_library
from .legality import geometry
from .models import AreaModelResult, NormalizedPoint, SearchState
from .registries import interface_metrics


def compute_area_model(point: NormalizedPoint, state: SearchState, bundle: Any, core_library: CoreLibrary | None = None) -> AreaModelResult:
    geom = geometry(point)
    process_cfg = bundle.process_nodes.get(point.tech, {})
    process_area_scale = float(process_cfg.get("scale_factor", 1.0))
    interface_info = interface_metrics(bundle, point.IO_type, point.package_type, point.tech)
    memory_cfg = bundle.memories[point.ddr_type]
    core_library = core_library or build_core_library(point, bundle)
    core_spec = core_library.spec

    chiplet_count = max(geom["chiplet_count"], 1)
    total_cores = point.total_core_count
    bytes_per_mib = 1024.0 * 1024.0
    core_array_area = (core_spec.mac_count / 1024.0) * (0.18 if point.microarch_name == "polar" else 0.21)
    l1_area = (
        core_spec.l1_activation.size_bytes + core_spec.l1_weight.size_bytes + core_spec.l1_output.size_bytes
    ) / bytes_per_mib * 0.18
    l2_area = (
        core_spec.l2_activation.size_bytes + core_spec.l2_weight.size_bytes + core_spec.l2_output.size_bytes
    ) / bytes_per_mib * 0.32
    ubuf_area = core_spec.ubuf.size_bytes / bytes_per_mib * 0.48
    compute_array_area = total_cores * core_array_area * (0.92 + 0.05 * state.mapping_tiling) * process_area_scale
    buffer_area = (l1_area + l2_area + ubuf_area) * total_cores * (0.92 + 0.06 * state.spm_level) * process_area_scale
    control_area = (
        0.45 * state.pipeline_depth
        + 0.25 * state.mapping_tiling
        + 0.20 * max(state.segment_span - 1, 0)
        + 0.15 * abs(state.placement_skew) * chiplet_count
        + 0.09 * total_cores
    )
    chiplet_overhead = 1.0 + 0.03 * max(chiplet_count - 1, 0)
    total_compute_area = (compute_array_area + buffer_area + control_area) * chiplet_overhead
    per_compute_die_area = total_compute_area / chiplet_count

    phy_area = 0.0
    if chiplet_count > 1:
        phy_area = (
            geom["per_die_exposed_edges"]
            * point.nop_bw
            * interface_info["density_area_per_gbps"]
            / 10000.0
            * 0.012
            * chiplet_count
        )

    memory_phy_area = (
        point.memory_bandwidth_gbps
        * float(memory_cfg["phy_density_area_per_gbps"])
        / 10000.0
        * (1.0 + 0.08 * state.memory_prefetch)
    )
    io_control_area = max(chiplet_count - 1, 0) * 0.85 + 0.35 * state.memory_prefetch + 0.20 * state.pipeline_depth
    io_die_area = memory_phy_area * 0.72 + phy_area * 0.58 + io_control_area
    total_die_area = total_compute_area + io_die_area

    return AreaModelResult(
        compute_array_area=compute_array_area,
        buffer_area=buffer_area,
        control_area=control_area,
        total_compute_area=total_compute_area,
        per_compute_die_area=per_compute_die_area,
        phy_area=phy_area,
        memory_phy_area=memory_phy_area,
        io_die_area=io_die_area,
        total_die_area=total_die_area,
    )
