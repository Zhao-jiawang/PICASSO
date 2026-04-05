from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from .models import NormalizedPoint


@dataclass(frozen=True)
class BufferSpec:
    name: str
    size_bytes: int
    read_cost: float
    write_cost: float
    read_bw: float
    write_bw: float


@dataclass(frozen=True)
class PolarArraySpec:
    vec_size: int
    lane_count: int
    activation_bus: int
    output_bus: int
    hop_cost: float
    bus_bandwidth: float


@dataclass(frozen=True)
class EyerissArraySpec:
    array_x: int
    array_y: int
    bus_cost: float
    bus_bandwidth: float


@dataclass(frozen=True)
class CoreSpec:
    microarch: str
    mac_count: int
    lr_mac_count: int
    lr_mac_cost: float
    ubuf: BufferSpec
    l1_activation: BufferSpec
    l1_weight: BufferSpec
    l1_output: BufferSpec
    l2_activation: BufferSpec
    l2_weight: BufferSpec
    l2_output: BufferSpec
    polar: PolarArraySpec | None = None
    eyeriss: EyerissArraySpec | None = None


@dataclass(frozen=True)
class CoreLibrary:
    spec: CoreSpec
    chiplet_core_count: int
    total_core_count: int
    process_frequency_ghz: float


def _factor_rectangle(total: int) -> tuple[int, int]:
    root = int(math.sqrt(max(total, 1)))
    for y in range(root, 0, -1):
        if total % y == 0:
            return total // y, y
    return total, 1


def build_core_library(point: NormalizedPoint, bundle: Any) -> CoreLibrary:
    process_cfg = bundle.process_nodes.get(point.tech, {})
    frequency_ghz = float(process_cfg.get("frequency_ghz", 1.0))
    chiplet_core_count = max((point.xx * point.yy) // max(point.chiplet_count, 1), 1)
    ubuf_per_core = point.ul3_bytes_per_core
    mac_count = max(point.mac, 1)
    lr_mac_count = max(mac_count // 2, 1)
    power_factor = float(process_cfg.get("power_factor", 1.0))
    lr_mac_cost = 0.65 * power_factor

    if point.microarch_name == "polar":
        vec_size = 8 if mac_count >= 64 else 4
        lane_count = max(mac_count // max(vec_size * 4, 1), 4)
        activation_bus = max(int(round(math.sqrt(max(chiplet_core_count, 1)))), 1)
        output_bus = max(int(math.ceil(chiplet_core_count / activation_bus)), 1)
        polar = PolarArraySpec(
            vec_size=vec_size,
            lane_count=lane_count,
            activation_bus=activation_bus,
            output_bus=output_bus,
            hop_cost=0.020 * power_factor,
            bus_bandwidth=max(point.noc / max(point.xx * point.yy, 1), 1.0),
        )
        eyeriss = None
    else:
        array_x, array_y = _factor_rectangle(max(mac_count, 1))
        eyeriss = EyerissArraySpec(
            array_x=array_x,
            array_y=array_y,
            bus_cost=0.018 * power_factor,
            bus_bandwidth=max(point.noc / max(point.xx * point.yy, 1), 1.0),
        )
        polar = None

    l1_base = max(ubuf_per_core // 16, 1024)
    l2_base = max(ubuf_per_core // 4, 8 * 1024)
    ubuf = BufferSpec("ubuf", ubuf_per_core, 0.010 * power_factor, 0.012 * power_factor, max(point.noc, 1), max(point.noc, 1))
    l1_activation = BufferSpec("l1_activation", l1_base, 0.006 * power_factor, 0.007 * power_factor, max(point.noc * 1.5, 1), max(point.noc * 1.2, 1))
    l1_weight = BufferSpec("l1_weight", l1_base, 0.0065 * power_factor, 0.0075 * power_factor, max(point.noc * 1.2, 1), max(point.noc * 1.1, 1))
    l1_output = BufferSpec("l1_output", l1_base, 0.0055 * power_factor, 0.0065 * power_factor, max(point.noc * 1.4, 1), max(point.noc * 1.4, 1))
    l2_activation = BufferSpec("l2_activation", l2_base, 0.008 * power_factor, 0.009 * power_factor, max(point.noc, 1), max(point.noc, 1))
    l2_weight = BufferSpec("l2_weight", l2_base, 0.0085 * power_factor, 0.0095 * power_factor, max(point.noc, 1), max(point.noc, 1))
    l2_output = BufferSpec("l2_output", l2_base, 0.0075 * power_factor, 0.0085 * power_factor, max(point.noc, 1), max(point.noc, 1))

    spec = CoreSpec(
        microarch=point.microarch_name,
        mac_count=mac_count,
        lr_mac_count=lr_mac_count,
        lr_mac_cost=lr_mac_cost,
        ubuf=ubuf,
        l1_activation=l1_activation,
        l1_weight=l1_weight,
        l1_output=l1_output,
        l2_activation=l2_activation,
        l2_weight=l2_weight,
        l2_output=l2_output,
        polar=polar,
        eyeriss=eyeriss,
    )
    return CoreLibrary(
        spec=spec,
        chiplet_core_count=chiplet_core_count,
        total_core_count=max(point.xx * point.yy, 1),
        process_frequency_ghz=frequency_ghz,
    )
