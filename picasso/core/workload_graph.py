from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List, Tuple

from picasso.workloads.model_library import LayerSpec, NetworkSpec, Shape4D, resolve_model_spec

from .models import NormalizedPoint


@dataclass(frozen=True)
class TensorShape:
    c: int
    h: int
    w: int
    b: int

    @property
    def volume(self) -> int:
        return max(self.c, 0) * max(self.h, 0) * max(self.w, 0) * max(self.b, 0)


@dataclass(frozen=True)
class DimRange:
    start: int
    end: int

    @property
    def size(self) -> int:
        return max(self.end - self.start, 0)


@dataclass(frozen=True)
class FeatureMapRange:
    c: DimRange
    b: DimRange
    h: DimRange
    w: DimRange

    @property
    def volume(self) -> int:
        return self.c.size * self.b.size * self.h.size * self.w.size


@dataclass(frozen=True)
class LayerNode:
    index: int
    name: str
    kind: str
    ifmap_shape: TensorShape
    ofmap_shape: TensorShape
    weight_shape: TensorShape
    prevs: List[int]
    external_inputs: List[str]
    stride_h: int = 1
    stride_w: int = 1
    kernel_h: int = 1
    kernel_w: int = 1
    has_weights: bool = True
    weight_from_memory: bool = True
    writes_to_memory: bool = False
    collective_kind: str | None = None
    expert_group: str | None = None
    input_merge: str = "concat"
    bitwidth: int = 8

    @property
    def activation_bytes(self) -> int:
        return self.ifmap_shape.volume

    @property
    def output_bytes(self) -> int:
        return self.ofmap_shape.volume

    @property
    def weight_bytes(self) -> int:
        return self.weight_shape.volume if self.has_weights else 0

    @property
    def op_count(self) -> int:
        if self.kind == "conv":
            return self.ofmap_shape.volume * max(self.ifmap_shape.c, 1) * max(self.kernel_h * self.kernel_w, 1)
        if self.kind in {"linear", "expert_ffn", "router"}:
            return self.ofmap_shape.volume * max(self.ifmap_shape.c, 1)
        if self.kind in {"attention", "collective", "dispatch", "combine"}:
            return self.output_bytes * max(self.ifmap_shape.c, 1)
        if self.kind == "cache":
            return self.output_bytes
        return self.output_bytes * max(self.kernel_h * self.kernel_w, 1)

    def required_input_range(self, output_range: FeatureMapRange) -> FeatureMapRange:
        if self.kind == "conv":
            h_start = max(output_range.h.start * self.stride_h, 0)
            w_start = max(output_range.w.start * self.stride_w, 0)
            h_end = min((output_range.h.end - 1) * self.stride_h + self.kernel_h, self.ifmap_shape.h) if output_range.h.end > output_range.h.start else h_start
            w_end = min((output_range.w.end - 1) * self.stride_w + self.kernel_w, self.ifmap_shape.w) if output_range.w.end > output_range.w.start else w_start
            return FeatureMapRange(
                c=DimRange(0, self.ifmap_shape.c),
                b=output_range.b,
                h=DimRange(h_start, h_end),
                w=DimRange(w_start, w_end),
            )
        return FeatureMapRange(
            c=DimRange(0, self.ifmap_shape.c),
            b=output_range.b,
            h=output_range.h if self.ifmap_shape.h > 1 else DimRange(0, self.ifmap_shape.h),
            w=output_range.w if self.ifmap_shape.w > 1 else DimRange(0, self.ifmap_shape.w),
        )

    def required_weight_range(self, output_range: FeatureMapRange) -> FeatureMapRange:
        if not self.has_weights:
            return FeatureMapRange(DimRange(0, 0), DimRange(0, 0), DimRange(0, 0), DimRange(0, 0))
        return FeatureMapRange(
            c=output_range.c,
            b=DimRange(0, max(self.weight_shape.b, 1)),
            h=DimRange(0, max(self.weight_shape.h, 1)),
            w=DimRange(0, max(self.weight_shape.w, 1)),
        )

    def ifmap_part_bytes(self, tensor_range: FeatureMapRange, fetch_b: int, fetch_h: int, fetch_w: int) -> int:
        batch = max(math.ceil(tensor_range.b.size / max(fetch_b, 1)), 1)
        height = tensor_range.h.size
        width = tensor_range.w.size
        if self.kind == "conv":
            if fetch_h > 1 and height > 0:
                height = max(math.ceil(max(height - self.kernel_h + self.stride_h, 1) / (self.stride_h * fetch_h)) * self.stride_h - self.stride_h + self.kernel_h, self.kernel_h)
            if fetch_w > 1 and width > 0:
                width = max(math.ceil(max(width - self.kernel_w + self.stride_w, 1) / (self.stride_w * fetch_w)) * self.stride_w - self.stride_w + self.kernel_w, self.kernel_w)
        return max(batch, 0) * max(tensor_range.c.size, 0) * max(height, 0) * max(width, 0)

    def weight_part_bytes(self, tensor_range: FeatureMapRange, fetch_k: int, fetch_b: int = 1) -> int:
        if not self.has_weights:
            return 0
        per_k = max(math.ceil(tensor_range.c.size / max(fetch_k, 1)), 1)
        return max(math.ceil(tensor_range.b.size / max(fetch_b, 1)), 1) * per_k * max(tensor_range.h.size, 0) * max(tensor_range.w.size, 0)


@dataclass(frozen=True)
class WorkloadGraph:
    workload_name: str
    motif: str
    exec_binding: str
    layers: List[LayerNode]
    external_inputs: Dict[str, TensorShape]
    metadata: Dict[str, object]


def _shape(spec: Shape4D) -> TensorShape:
    return TensorShape(spec.c, spec.h, spec.w, spec.b)


def _merge_input_shape(layer: LayerSpec, prev_shapes: List[TensorShape], external_shapes: List[TensorShape]) -> TensorShape:
    inputs = prev_shapes + external_shapes
    if not inputs:
        return _shape(layer.ifmap_shape)
    if layer.input_merge == "passthrough":
        return inputs[0]
    if layer.input_merge == "collective":
        max_h = max(shape.h for shape in inputs)
        max_w = max(shape.w for shape in inputs)
        max_b = max(shape.b for shape in inputs)
        max_c = max(shape.c for shape in inputs)
        return TensorShape(max_c, max_h, max_w, max_b)
    ref_h = inputs[0].h
    ref_w = inputs[0].w
    ref_b = inputs[0].b
    for shape in inputs[1:]:
        if shape.h != ref_h or shape.w != ref_w or shape.b != ref_b:
            raise ValueError(f"Layer '{layer.name}' has incompatible input shapes for concat merge")
    return TensorShape(sum(shape.c for shape in inputs), ref_h, ref_w, ref_b)


def _validate_layer(spec: LayerSpec, merged_ifmap: TensorShape) -> None:
    expected = _shape(spec.ifmap_shape)
    if spec.input_merge == "collective":
        if merged_ifmap.b <= 0 or expected.b <= 0:
            raise ValueError(f"Layer '{spec.name}' collective inputs must keep a valid batch dimension")
        return
    if merged_ifmap != expected:
        raise ValueError(f"Layer '{spec.name}' expected ifmap {expected} but got {merged_ifmap}")


def _build_nodes(spec: NetworkSpec) -> List[LayerNode]:
    external_inputs = {input_spec.name: _shape(input_spec.shape) for input_spec in spec.external_inputs}
    nodes: List[LayerNode] = []
    node_by_index: Dict[int, LayerNode] = {}
    for layer in spec.layers:
        prev_shapes = [node_by_index[idx].ofmap_shape for idx in layer.prevs]
        ext_shapes = [external_inputs[name] for name in layer.external_inputs]
        merged_ifmap = _merge_input_shape(layer, prev_shapes, ext_shapes)
        _validate_layer(layer, merged_ifmap)
        node = LayerNode(
            index=layer.index,
            name=layer.name,
            kind=layer.kind,
            ifmap_shape=_shape(layer.ifmap_shape),
            ofmap_shape=_shape(layer.ofmap_shape),
            weight_shape=_shape(layer.weight_shape),
            prevs=list(layer.prevs),
            external_inputs=list(layer.external_inputs),
            stride_h=layer.stride_h,
            stride_w=layer.stride_w,
            kernel_h=layer.kernel_h,
            kernel_w=layer.kernel_w,
            has_weights=layer.has_weights,
            weight_from_memory=layer.weight_from_memory,
            writes_to_memory=layer.writes_to_memory,
            collective_kind=layer.collective_kind,
            expert_group=layer.expert_group,
            input_merge=layer.input_merge,
            bitwidth=layer.bitwidth,
        )
        nodes.append(node)
        node_by_index[node.index] = node
    return nodes


def build_workload_graph(point: NormalizedPoint) -> WorkloadGraph:
    spec = resolve_model_spec(point)
    external_inputs = {input_spec.name: _shape(input_spec.shape) for input_spec in spec.external_inputs}
    layers = _build_nodes(spec)
    return WorkloadGraph(
        workload_name=point.workload_name,
        motif=point.workload_motif or point.workload_name,
        exec_binding=spec.exec_binding,
        layers=layers,
        external_inputs=external_inputs,
        metadata=spec.metadata,
    )
