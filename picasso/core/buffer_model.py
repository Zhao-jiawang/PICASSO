from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

from .data_layout import LayoutModel
from .layer_engine import LayerEnginePlan
from .models import NormalizedPoint


@dataclass(frozen=True)
class CoreBufferUsage:
    core_id: int
    ifm_bytes: int
    ofm_bytes: int
    wgt_bytes: int
    total_bytes: int
    overflow_ratio: float


@dataclass(frozen=True)
class BufferUsageResult:
    per_core: List[CoreBufferUsage]
    peak_bytes: int
    average_bytes: float
    overflow_core_count: int
    overflow_ratio: float


def evaluate_buffer_usage(
    point: NormalizedPoint,
    layout_model: LayoutModel,
    layer_engine_plan: LayerEnginePlan | None = None,
    capacity_bytes: int | None = None,
) -> BufferUsageResult:
    capacity_bytes = max(capacity_bytes or point.ul3_bytes_per_core, 1)
    per_core_peak: Dict[int, Dict[str, int]] = {}
    if layer_engine_plan is not None and layer_engine_plan.layer_records:
        for record in layer_engine_plan.layer_records:
            for core_id in record.active_core_ids:
                stats = {
                    "ifm": record.resident_ifmap_bytes,
                    "ofm": record.resident_output_bytes,
                    "wgt": record.resident_weight_bytes,
                    "total": record.resident_total_bytes,
                }
                current = per_core_peak.setdefault(core_id, {"ifm": 0, "ofm": 0, "wgt": 0, "total": 0})
                if stats["total"] > current["total"]:
                    current.update(stats)
    else:
        for layer_layout in layout_model.layer_layouts:
            layer_bytes: Dict[int, Dict[str, int]] = {}
            for entry in layer_layout.ifm_entries:
                stats = layer_bytes.setdefault(entry.core_id, {"ifm": 0, "ofm": 0, "wgt": 0})
                stats["ifm"] += entry.tensor_range.volume
            for entry in layer_layout.ofm_entries:
                stats = layer_bytes.setdefault(entry.core_id, {"ifm": 0, "ofm": 0, "wgt": 0})
                stats["ofm"] += entry.tensor_range.volume
            for entry in layer_layout.wgt_entries:
                stats = layer_bytes.setdefault(entry.core_id, {"ifm": 0, "ofm": 0, "wgt": 0})
                stats["wgt"] += entry.tensor_range.volume
            for core_id, stats in layer_bytes.items():
                total = stats["ifm"] + stats["ofm"] + stats["wgt"]
                current = per_core_peak.setdefault(core_id, {"ifm": 0, "ofm": 0, "wgt": 0, "total": 0})
                if total > current["total"]:
                    current["ifm"] = stats["ifm"]
                    current["ofm"] = stats["ofm"]
                    current["wgt"] = stats["wgt"]
                    current["total"] = total

    usages: List[CoreBufferUsage] = []
    for core_id in sorted(per_core_peak):
        stats = per_core_peak[core_id]
        overflow_ratio = max(stats["total"] / capacity_bytes - 1.0, 0.0)
        usages.append(
            CoreBufferUsage(
                core_id=core_id,
                ifm_bytes=stats["ifm"],
                ofm_bytes=stats["ofm"],
                wgt_bytes=stats["wgt"],
                total_bytes=stats["total"],
                overflow_ratio=overflow_ratio,
            )
        )

    peak_bytes = max((usage.total_bytes for usage in usages), default=0)
    average_bytes = sum(usage.total_bytes for usage in usages) / max(len(usages), 1)
    overflow_core_count = sum(1 for usage in usages if usage.overflow_ratio > 0.0)
    overflow_ratio = max(peak_bytes / capacity_bytes - 1.0, 0.0)
    return BufferUsageResult(
        per_core=usages,
        peak_bytes=peak_bytes,
        average_bytes=average_bytes,
        overflow_core_count=overflow_core_count,
        overflow_ratio=overflow_ratio,
    )
