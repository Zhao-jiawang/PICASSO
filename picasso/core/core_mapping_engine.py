from __future__ import annotations

import math
from dataclasses import dataclass

from .core_model import CoreLibrary
from .partition_engine import LayerPartitionPlan
from .workload_graph import LayerNode


@dataclass(frozen=True)
class LayerMapMetrics:
    layer_index: int
    compute_cycles: int
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
    utilization: float
    rounded_op_count: int
    fetch_rounds: int


@dataclass(frozen=True)
class MappingAggregate:
    total_compute_cycles: int
    total_mac_energy: float
    total_buffer_energy: float
    total_interconnect_energy: float
    peak_ubuf_bytes: int
    average_utilization: float


def _ceil_div(value: int, factor: int) -> int:
    return max(int(math.ceil(value / max(factor, 1))), 1)


def _partitioned_output_bytes(layer: LayerNode, plan: LayerPartitionPlan) -> int:
    return _ceil_div(layer.output_bytes, plan.factors.size)


def _partitioned_input_bytes(layer: LayerNode, plan: LayerPartitionPlan) -> int:
    channels = _ceil_div(layer.ifmap_shape.c, plan.factors.k)
    batch = _ceil_div(layer.ifmap_shape.b, plan.factors.b)
    height = _ceil_div(layer.ifmap_shape.h, plan.factors.h)
    width = _ceil_div(layer.ifmap_shape.w, plan.factors.w)
    if layer.kind == "conv":
        height = min((height - 1) * layer.stride_h + layer.kernel_h, layer.ifmap_shape.h)
        width = min((width - 1) * layer.stride_w + layer.kernel_w, layer.ifmap_shape.w)
    return max(channels * batch * height * width, 1)


def _partitioned_weight_bytes(layer: LayerNode, plan: LayerPartitionPlan) -> int:
    if not layer.has_weights:
        return 0
    weight_k = _ceil_div(layer.weight_shape.c, plan.factors.k)
    return max(weight_k * max(layer.weight_shape.b, 1) * max(layer.weight_shape.h, 1) * max(layer.weight_shape.w, 1), 1)


def map_layer_to_core(layer: LayerNode, plan: LayerPartitionPlan, core_library: CoreLibrary, active_core_count: int) -> LayerMapMetrics:
    spec = core_library.spec
    core_buffer_capacity = (
        spec.ubuf.size_bytes
        + spec.l1_activation.size_bytes
        + spec.l1_weight.size_bytes
        + spec.l1_output.size_bytes
        + spec.l2_activation.size_bytes
        + spec.l2_weight.size_bytes
        + spec.l2_output.size_bytes
    )
    input_bytes = _partitioned_input_bytes(layer, plan)
    weight_bytes = _partitioned_weight_bytes(layer, plan)
    output_bytes = _partitioned_output_bytes(layer, plan)
    fetch_rounds = max(plan.fetch_plan.ifm_fetch * plan.fetch_plan.wgt_fetch, 1)
    resident_input_bytes = _ceil_div(input_bytes, max(plan.fetch_plan.ifm_fetch, 1))
    resident_weight_bytes = _ceil_div(weight_bytes, max(plan.fetch_plan.wgt_fetch, 1)) if weight_bytes > 0 else 0
    non_output_resident = resident_input_bytes + resident_weight_bytes
    if output_bytes + non_output_resident <= core_buffer_capacity:
        output_fetch = 1
        resident_output_bytes = output_bytes
    else:
        output_budget = max(core_buffer_capacity - non_output_resident, core_buffer_capacity // 8, 4 * 1024)
        output_fetch = max(_ceil_div(output_bytes, output_budget), 1)
        resident_output_bytes = _ceil_div(output_bytes, output_fetch)
    fetch_rounds *= output_fetch
    resident_total_bytes = resident_input_bytes + resident_weight_bytes + resident_output_bytes

    if spec.polar is not None:
        rounded_c = _ceil_div(max(layer.ifmap_shape.c, 1), spec.polar.vec_size) * spec.polar.vec_size
        rounded_k = _ceil_div(max(layer.ofmap_shape.c, 1), spec.polar.lane_count) * spec.polar.lane_count
        rounded_ops = max(layer.op_count, 1)
        if layer.kind in {"conv", "linear", "expert_ffn", "router"}:
            rounded_ops = max(rounded_ops, rounded_c * rounded_k * max(layer.ofmap_shape.h * layer.ofmap_shape.w * layer.ofmap_shape.b, 1))
        effective_macs = max(spec.mac_count * max(active_core_count, 1), 1)
        compute_cycles = int(math.ceil(rounded_ops * fetch_rounds / effective_macs))
        utilization = min(layer.op_count / max(rounded_ops, 1), 1.0) * plan.utilization
        mac_energy = rounded_ops * 0.0038
        buffer_energy = (
            input_bytes * spec.l1_activation.read_cost
            + weight_bytes * spec.l1_weight.read_cost
            + output_bytes * spec.l1_output.write_cost
        ) * fetch_rounds * (1.0 + 0.06 * max(output_fetch - 1, 0))
        interconnect_energy = (
            (input_bytes + weight_bytes + output_bytes)
            * spec.polar.hop_cost
            * (1.0 + 0.15 * max(plan.factors.h * plan.factors.w - 1, 0))
        ) * (1.0 + 0.04 * max(output_fetch - 1, 0))
        l1_bytes = resident_input_bytes + resident_weight_bytes + resident_output_bytes
        l2_bytes = int((resident_input_bytes + resident_weight_bytes) * (1.0 + 0.08 * max(plan.fetch_plan.wgt_fetch - 1, 0)))
        ubuf_bytes = int(max(resident_total_bytes, l2_bytes + resident_output_bytes * 0.35))
    else:
        array_capacity = max(spec.mac_count, 1)
        fold_factor = max(_ceil_div(max(layer.ifmap_shape.c, 1), max(spec.eyeriss.array_y if spec.eyeriss else 1, 1)), 1)
        reply_factor = max(_ceil_div(max(layer.ofmap_shape.c, 1), max(spec.eyeriss.array_x if spec.eyeriss else 1, 1)), 1)
        rounded_ops = max(layer.op_count * fold_factor * reply_factor, layer.op_count)
        compute_cycles = int(math.ceil(rounded_ops * fetch_rounds / max(array_capacity * max(active_core_count, 1), 1)))
        utilization = min(layer.op_count / max(rounded_ops, 1), 1.0) * plan.utilization
        mac_energy = rounded_ops * 0.0035
        buffer_energy = (
            input_bytes * spec.l1_activation.read_cost
            + weight_bytes * spec.l1_weight.read_cost
            + output_bytes * spec.l1_output.write_cost
        ) * fetch_rounds * 1.08 * (1.0 + 0.06 * max(output_fetch - 1, 0))
        interconnect_energy = (
            (input_bytes + weight_bytes + output_bytes)
            * (spec.eyeriss.bus_cost if spec.eyeriss else 0.02)
            * (1.0 + 0.10 * max(plan.factors.k - 1, 0))
        ) * (1.0 + 0.04 * max(output_fetch - 1, 0))
        l1_bytes = int((resident_input_bytes + resident_output_bytes) * 0.75 + resident_weight_bytes * 0.50)
        l2_bytes = int((resident_input_bytes + resident_weight_bytes) * (1.0 + 0.10 * max(plan.fetch_plan.ifm_fetch - 1, 0)))
        ubuf_bytes = int(max(resident_total_bytes, l2_bytes + resident_output_bytes * 0.25))

    return LayerMapMetrics(
        layer_index=layer.index,
        compute_cycles=max(compute_cycles, 1),
        mac_energy=mac_energy,
        buffer_energy=buffer_energy,
        interconnect_energy=interconnect_energy,
        resident_ifmap_bytes=resident_input_bytes,
        resident_weight_bytes=resident_weight_bytes,
        resident_output_bytes=resident_output_bytes,
        resident_total_bytes=resident_total_bytes,
        ubuf_bytes=ubuf_bytes,
        l1_bytes=l1_bytes,
        l2_bytes=l2_bytes,
        utilization=max(min(utilization, 1.0), 0.05),
        rounded_op_count=rounded_ops,
        fetch_rounds=fetch_rounds,
    )
