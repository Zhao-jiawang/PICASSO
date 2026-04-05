from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Tuple

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from picasso.core.models import NormalizedPoint


@dataclass(frozen=True)
class Shape4D:
    c: int
    h: int
    w: int
    b: int = 1

    @property
    def volume(self) -> int:
        return max(self.c, 0) * max(self.h, 0) * max(self.w, 0) * max(self.b, 0)


@dataclass(frozen=True)
class ExternalInputSpec:
    name: str
    shape: Shape4D


@dataclass(frozen=True)
class LayerSpec:
    index: int
    name: str
    kind: str
    ifmap_shape: Shape4D
    ofmap_shape: Shape4D
    weight_shape: Shape4D
    prevs: Tuple[int, ...]
    external_inputs: Tuple[str, ...] = ()
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


@dataclass(frozen=True)
class NetworkSpec:
    exec_binding: str
    motif: str
    external_inputs: Tuple[ExternalInputSpec, ...]
    layers: Tuple[LayerSpec, ...]
    metadata: Dict[str, Any]


def _hidden_size(point: "NormalizedPoint") -> int:
    if point.tops_target_tops >= 512:
        return 4096
    if point.tops_target_tops >= 128:
        return 2048
    return 1024


def _cnn_network(point: "NormalizedPoint") -> NetworkSpec:
    batch = max(point.bb, 1)
    channels = [64, 128, 256, 512, 1024]
    spatial = [56, 28, 14, 7, 1]
    layers = []
    prev = ()
    in_c = 3
    in_h = 112
    in_w = 112
    for idx, (out_c, out_hw) in enumerate(zip(channels, spatial)):
        layers.append(
            LayerSpec(
                index=idx,
                name=f"conv_block_{idx}",
                kind="conv",
                ifmap_shape=Shape4D(in_c, in_h, in_w, batch),
                ofmap_shape=Shape4D(out_c, out_hw, out_hw, batch),
                weight_shape=Shape4D(out_c, in_c, 3, 3),
                prevs=prev,
                external_inputs=("image",) if idx == 0 else (),
                stride_h=2 if idx > 0 else 1,
                stride_w=2 if idx > 0 else 1,
                kernel_h=3,
                kernel_w=3,
                writes_to_memory=(idx == len(channels) - 1),
                input_merge="concat",
            )
        )
        prev = (idx,)
        in_c = out_c
        in_h = out_hw
        in_w = out_hw
    return NetworkSpec(
        exec_binding=point.workload_exec_name,
        motif=point.workload_motif or point.workload_name,
        external_inputs=(ExternalInputSpec("image", Shape4D(3, 112, 112, batch)),),
        layers=tuple(layers),
        metadata={"family": "cnn", "network": point.workload_exec_name},
    )


def _decoder_block_network(point: "NormalizedPoint", seq_len: int, kv_heavy: bool) -> NetworkSpec:
    batch = max(point.bb, 1)
    hidden = _hidden_size(point)
    ffn = hidden * 4
    kv_scale = 2 if kv_heavy else 1
    external_inputs = [ExternalInputSpec("tokens", Shape4D(hidden, seq_len, 1, batch))]
    if kv_heavy:
        cache_len = 4096 if point.tops_target_tops >= 512 else 2048
        external_inputs.append(ExternalInputSpec("kv_cache", Shape4D(hidden, cache_len, 1, batch)))
    layers = [
        LayerSpec(
            index=0,
            name="qkv_proj",
            kind="linear",
            ifmap_shape=Shape4D(hidden, seq_len, 1, batch),
            ofmap_shape=Shape4D(hidden * 3, seq_len, 1, batch),
            weight_shape=Shape4D(hidden * 3, hidden, 1, 1),
            prevs=(),
            external_inputs=("tokens",),
        ),
    ]
    if kv_heavy:
        layers.append(
            LayerSpec(
                index=1,
                name="kv_cache_read",
                kind="cache",
                ifmap_shape=Shape4D(hidden, cache_len, 1, batch),
                ofmap_shape=Shape4D(hidden, seq_len, 1, batch),
                weight_shape=Shape4D(0, 0, 0, 0),
                prevs=(),
                external_inputs=("kv_cache",),
                has_weights=False,
                weight_from_memory=False,
                input_merge="passthrough",
            )
        )
        attn_prevs = (0, 1)
        attn_ifmap = Shape4D(hidden * 4, seq_len, 1, batch)
        attn_index = 2
    else:
        attn_prevs = (0,)
        attn_ifmap = Shape4D(hidden * 3, seq_len, 1, batch)
        attn_index = 1
    layers.extend(
        [
            LayerSpec(
                index=attn_index,
                name="attention_scores",
                kind="attention",
                ifmap_shape=attn_ifmap,
                ofmap_shape=Shape4D(hidden, seq_len, 1, batch),
                weight_shape=Shape4D(hidden * kv_scale, hidden, 1, 1) if not kv_heavy else Shape4D(0, 0, 0, 0),
                prevs=attn_prevs,
                has_weights=not kv_heavy,
                collective_kind="attention",
                input_merge="collective",
            ),
            LayerSpec(
                index=attn_index + 1,
                name="out_proj",
                kind="linear",
                ifmap_shape=Shape4D(hidden, seq_len, 1, batch),
                ofmap_shape=Shape4D(hidden, seq_len, 1, batch),
                weight_shape=Shape4D(hidden, hidden, 1, 1),
                prevs=(attn_index,),
            ),
            LayerSpec(
                index=attn_index + 2,
                name="mlp_in",
                kind="linear",
                ifmap_shape=Shape4D(hidden, seq_len, 1, batch),
                ofmap_shape=Shape4D(ffn, seq_len, 1, batch),
                weight_shape=Shape4D(ffn, hidden, 1, 1),
                prevs=(attn_index + 1,),
            ),
            LayerSpec(
                index=attn_index + 3,
                name="mlp_out",
                kind="linear",
                ifmap_shape=Shape4D(ffn, seq_len, 1, batch),
                ofmap_shape=Shape4D(hidden, seq_len, 1, batch),
                weight_shape=Shape4D(hidden, ffn, 1, 1),
                prevs=(attn_index + 2,),
                writes_to_memory=True,
            ),
        ]
    )
    return NetworkSpec(
        exec_binding=point.workload_exec_name,
        motif=point.workload_motif or point.workload_name,
        external_inputs=tuple(external_inputs),
        layers=tuple(layers),
        metadata={"family": "decoder", "seq_len": seq_len, "kv_heavy": kv_heavy},
    )


def _mixtral_network(point: "NormalizedPoint") -> NetworkSpec:
    batch = max(point.bb, 1)
    hidden = _hidden_size(point)
    seq_len = 1024 if point.tops_target_tops >= 512 else 512
    trace = point.workload_trace_summary or {}
    expert_count = max(int(trace.get("expert_count", 8)), 2)
    top_k = max(int(trace.get("top_k", 2)), 1)
    layers = [
        LayerSpec(
            index=0,
            name="router",
            kind="router",
            ifmap_shape=Shape4D(hidden, seq_len, 1, batch),
            ofmap_shape=Shape4D(expert_count, seq_len, 1, batch),
            weight_shape=Shape4D(expert_count, hidden, 1, 1),
            prevs=(),
            external_inputs=("tokens",),
        ),
        LayerSpec(
            index=1,
            name="dispatch",
            kind="dispatch",
            ifmap_shape=Shape4D(expert_count, seq_len, 1, batch),
            ofmap_shape=Shape4D(hidden, seq_len, top_k, batch),
            weight_shape=Shape4D(0, 0, 0, 0),
            prevs=(0,),
            has_weights=False,
            collective_kind="dispatch",
            input_merge="collective",
        ),
    ]
    per_expert_tokens = max(seq_len // max(top_k, 1), 1)
    for expert_idx in range(expert_count):
        layers.append(
            LayerSpec(
                index=len(layers),
                name=f"expert_{expert_idx}",
                kind="expert_ffn",
                ifmap_shape=Shape4D(hidden, per_expert_tokens, top_k, batch),
                ofmap_shape=Shape4D(hidden, per_expert_tokens, top_k, batch),
                weight_shape=Shape4D(hidden * 4, hidden, 1, 1),
                prevs=(1,),
                expert_group=f"expert_{expert_idx}",
                input_merge="collective",
            )
        )
    layers.append(
        LayerSpec(
            index=len(layers),
            name="combine",
            kind="combine",
            ifmap_shape=Shape4D(hidden, seq_len, top_k, batch),
            ofmap_shape=Shape4D(hidden, seq_len, 1, batch),
            weight_shape=Shape4D(hidden, hidden, 1, 1),
            prevs=tuple(range(2, 2 + expert_count)),
            collective_kind="combine",
            writes_to_memory=True,
            input_merge="collective",
        )
    )
    return NetworkSpec(
        exec_binding=point.workload_exec_name,
        motif=point.workload_motif or point.workload_name,
        external_inputs=(ExternalInputSpec("tokens", Shape4D(hidden, seq_len, 1, batch)),),
        layers=tuple(layers),
        metadata={"family": "moe", "expert_count": expert_count, "top_k": top_k},
    )


def _megatron_network(point: "NormalizedPoint") -> NetworkSpec:
    batch = max(point.bb, 1)
    hidden = _hidden_size(point)
    seq_len = 2048 if point.tops_target_tops >= 512 else 1024
    trace = point.workload_trace_summary or {}
    phase_count = max(int(trace.get("phase_count", 6)), 2)
    layers = []
    prev = ()
    for phase in range(phase_count):
        compute_idx = len(layers)
        layers.append(
            LayerSpec(
                index=compute_idx,
                name=f"compute_{phase}",
                kind="linear",
                ifmap_shape=Shape4D(hidden, seq_len, 1, batch),
                ofmap_shape=Shape4D(hidden, seq_len, 1, batch),
                weight_shape=Shape4D(hidden, hidden, 1, 1),
                prevs=prev,
                external_inputs=("tokens",) if not prev else (),
            )
        )
        collective = "all_reduce" if phase % 2 == 0 else "all_gather"
        collective_idx = len(layers)
        layers.append(
            LayerSpec(
                index=collective_idx,
                name=f"collective_{phase}",
                kind="collective",
                ifmap_shape=Shape4D(hidden, seq_len, 1, batch),
                ofmap_shape=Shape4D(hidden, seq_len, 1, batch),
                weight_shape=Shape4D(0, 0, 0, 0),
                prevs=(compute_idx,),
                has_weights=False,
                collective_kind=collective,
                writes_to_memory=(phase == phase_count - 1),
                input_merge="collective",
            )
        )
        prev = (collective_idx,)
    return NetworkSpec(
        exec_binding=point.workload_exec_name,
        motif=point.workload_motif or point.workload_name,
        external_inputs=(ExternalInputSpec("tokens", Shape4D(hidden, seq_len, 1, batch)),),
        layers=tuple(layers),
        metadata={"family": "megatron", "phase_count": phase_count},
    )


def resolve_model_spec(point: "NormalizedPoint") -> NetworkSpec:
    motif = point.workload_motif or point.workload_name
    exec_binding = point.workload_exec_name
    if motif == "cnn_inference" or exec_binding in {"resnext50", "resnet50", "googlenet", "densenet"}:
        return _cnn_network(point)
    if motif == "mixtral_moe_trace":
        return _mixtral_network(point)
    if motif == "megatron_collective_trace":
        return _megatron_network(point)
    if motif == "long_context_prefill" or exec_binding == "gpt2_prefill_block":
        return _decoder_block_network(point, seq_len=4096 if point.tops_target_tops >= 512 else 2048, kv_heavy=False)
    if motif == "kv_heavy_decode" or exec_binding == "gpt2_decode_block":
        return _decoder_block_network(point, seq_len=32 if point.tops_target_tops >= 512 else 8, kv_heavy=True)
    if motif == "dense_decoder_block" or exec_binding == "bert_block":
        return _decoder_block_network(point, seq_len=512, kv_heavy=False)
    if exec_binding == "transformer":
        return _megatron_network(point)
    return _decoder_block_network(point, seq_len=512, kv_heavy=False)
