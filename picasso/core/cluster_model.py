from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, Iterable, List, Tuple

from .models import NormalizedPoint


@dataclass(frozen=True)
class ClusterCoord:
    core_id: int
    x: int
    y: int
    chiplet_x: int
    chiplet_y: int
    chiplet_id: int


@dataclass(frozen=True)
class ClusterAllocation:
    core_ranges: Tuple[Tuple[int, int], ...]
    core_counts: Tuple[int, ...]
    max_time: float
    utilization: float


@dataclass(frozen=True)
class CoreCluster:
    total_x: int
    total_y: int
    xcut: int
    ycut: int
    core_ids: Tuple[int, ...]
    coords: Tuple[ClusterCoord, ...]

    @property
    def chiplet_count(self) -> int:
        return max(self.xcut * self.ycut, 1)

    @property
    def coord_by_core(self) -> Dict[int, ClusterCoord]:
        return {coord.core_id: coord for coord in self.coords}

    def num_cores(self) -> int:
        return len(self.core_ids)

    def core_coord(self, core_id: int) -> ClusterCoord:
        return self.coord_by_core[core_id]

    def subcluster(self, core_ids: Iterable[int]) -> "CoreCluster":
        keep = tuple(core_ids)
        coord_lookup = self.coord_by_core
        return CoreCluster(
            total_x=self.total_x,
            total_y=self.total_y,
            xcut=self.xcut,
            ycut=self.ycut,
            core_ids=keep,
            coords=tuple(coord_lookup[core_id] for core_id in keep),
        )

    def allocate_by_ops(self, ops: Iterable[int], stride: int = 1) -> ClusterAllocation:
        op_list = [max(int(op), 1) for op in ops]
        child_count = len(op_list)
        total_cores = self.num_cores()
        if child_count == 0:
            return ClusterAllocation(core_ranges=(), core_counts=(), max_time=0.0, utilization=1.0)
        if child_count > total_cores:
            raise ValueError("cannot allocate more children than available cores")
        total_ops = sum(op_list)
        raw_counts = [max(1, int(math.floor(total_cores * op / max(total_ops, 1)))) for op in op_list]
        stride = max(stride, 1)
        raw_counts = [max(stride, (count // stride) * stride) for count in raw_counts]
        used = sum(raw_counts)
        while used > total_cores:
            idx = max(range(child_count), key=lambda item: raw_counts[item] - total_cores * op_list[item] / max(total_ops, 1))
            if raw_counts[idx] > stride:
                raw_counts[idx] -= stride
                used -= stride
            else:
                break
        while used < total_cores:
            idx = min(range(child_count), key=lambda item: raw_counts[item] - total_cores * op_list[item] / max(total_ops, 1))
            raw_counts[idx] += stride
            used += stride
        if used != total_cores:
            raw_counts[-1] += total_cores - used
        start = 0
        ranges: List[Tuple[int, int]] = []
        max_time = 0.0
        for op, count in zip(op_list, raw_counts):
            end = start + count
            ranges.append((start, end))
            max_time = max(max_time, op / max(count, 1))
            start = end
        utilization = total_ops / max(total_cores * max_time, 1.0)
        return ClusterAllocation(core_ranges=tuple(ranges), core_counts=tuple(raw_counts), max_time=max_time, utilization=utilization)

    def nearest_dram_chiplet(self, core_ids: Iterable[int]) -> int:
        selected = list(core_ids)
        if not selected:
            return 0
        coord_lookup = self.coord_by_core
        center_x = sum(coord_lookup[core_id].x for core_id in selected) / len(selected)
        center_y = sum(coord_lookup[core_id].y for core_id in selected) / len(selected)
        best_chiplet = 0
        best_distance = float("inf")
        for chiplet_id in range(self.chiplet_count):
            chiplet_x = chiplet_id % max(self.xcut, 1)
            chiplet_y = chiplet_id // max(self.xcut, 1)
            x_step = max(self.total_x // max(self.xcut, 1), 1)
            y_step = max(self.total_y // max(self.ycut, 1), 1)
            center_chiplet_x = chiplet_x * x_step + (x_step - 1) / 2.0
            center_chiplet_y = chiplet_y * y_step + (y_step - 1) / 2.0
            distance = abs(center_x - center_chiplet_x) + abs(center_y - center_chiplet_y)
            if distance < best_distance:
                best_distance = distance
                best_chiplet = chiplet_id
        return best_chiplet


def build_core_cluster(point: NormalizedPoint) -> CoreCluster:
    x_step = max(point.xx // max(point.xcut, 1), 1)
    y_step = max(point.yy // max(point.ycut, 1), 1)
    coords: List[ClusterCoord] = []
    for y in range(point.yy):
        for x in range(point.xx):
            chiplet_x = x // x_step
            chiplet_y = y // y_step
            coords.append(
                ClusterCoord(
                    core_id=y * point.xx + x,
                    x=x,
                    y=y,
                    chiplet_x=chiplet_x,
                    chiplet_y=chiplet_y,
                    chiplet_id=chiplet_y * max(point.xcut, 1) + chiplet_x,
                )
            )
    return CoreCluster(
        total_x=point.xx,
        total_y=point.yy,
        xcut=point.xcut,
        ycut=point.ycut,
        core_ids=tuple(coord.core_id for coord in coords),
        coords=tuple(coords),
    )
