from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict


DEFAULT_EXEC_BINDINGS = {
    "cnn_inference": "resnext50",
    "long_context_prefill": "gpt2_prefill_block",
    "kv_heavy_decode": "gpt2_decode_block",
    "dense_decoder_block": "bert_block",
    "mixtral_moe_trace": "gpt2_decode_block",
    "megatron_collective_trace": "transformer",
}


@dataclass(frozen=True)
class ResolvedWorkload:
    name: str
    exec_binding: str
    motif: str
    definition_ref: str | None
    status: str
    trace_ref: str | None
    trace_summary: Dict[str, Any]
    trace_scalars: Dict[str, float]


def load_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def relative_to_repo(path: Path | None, repo_root: Path) -> str | None:
    if path is None:
        return None
    return str(path.relative_to(repo_root))


def resolve_trace_path(trace_ref: str | None, repo_root: Path) -> Path | None:
    if not trace_ref:
        return None
    path = Path(trace_ref)
    return path if path.is_absolute() else repo_root / path


def summarize_trace(workload_name: str, trace_payload: Dict[str, Any]) -> tuple[Dict[str, Any], Dict[str, float]]:
    if workload_name == "mixtral_moe_trace":
        experts = [str(expert) for expert in trace_payload.get("experts", [])]
        tokens = trace_payload.get("tokens", [])
        token_count = len(tokens)
        locality_hits = sum(1 for token in tokens if token.get("locality_hit"))
        locality_probability = (
            locality_hits / token_count
            if token_count
            else float(trace_payload.get("required_properties", {}).get("locality_probability", 0.0))
        )
        top_k = max((len(token.get("top2_experts", [])) for token in tokens), default=0)
        imbalance_factor = float(trace_payload.get("required_properties", {}).get("load_imbalance_factor", 1.0))
        summary = {
            "trace_type": workload_name,
            "expert_count": len(experts),
            "token_count": token_count,
            "top_k": top_k,
            "load_imbalance_factor": imbalance_factor,
            "locality_probability": round(locality_probability, 6),
        }
        scalars = {
            "edge_factor_scale": round(1.0 + max(0.0, imbalance_factor - 1.0) * 0.30 + max(0.0, top_k - 1) * 0.08, 6),
            "route_factor_scale": round(1.0 + (1.0 - locality_probability) * 0.20, 6),
            "memory_factor_scale": round(1.0 + max(0.0, imbalance_factor - 1.0) * 0.18, 6),
        }
        return summary, scalars

    if workload_name == "megatron_collective_trace":
        phases = trace_payload.get("phases", [])
        phase_count = len(phases)
        all_reduce_count = sum(1 for phase in phases if phase.get("collective") == "all_reduce")
        all_gather_count = sum(1 for phase in phases if phase.get("collective") == "all_gather")
        high_route_count = sum(1 for phase in phases if phase.get("route_pressure_tag") == "high")
        high_memory_count = sum(1 for phase in phases if phase.get("memory_attachment_pressure") == "high")
        bucket_size_mb = int(trace_payload.get("required_properties", {}).get("bucket_size_mb", 0))
        phase_denominator = max(phase_count, 1)
        summary = {
            "trace_type": workload_name,
            "phase_count": phase_count,
            "bucket_size_mb": bucket_size_mb,
            "all_reduce_count": all_reduce_count,
            "all_gather_count": all_gather_count,
            "high_route_phase_count": high_route_count,
            "high_memory_phase_count": high_memory_count,
        }
        scalars = {
            "edge_factor_scale": round(1.0 + (high_route_count / phase_denominator) * 0.18, 6),
            "route_factor_scale": round(
                1.0
                + (all_reduce_count / phase_denominator) * 0.20
                + (high_route_count / phase_denominator) * 0.12,
                6,
            ),
            "memory_factor_scale": round(1.0 + (high_memory_count / phase_denominator) * 0.16, 6),
        }
        return summary, scalars

    return {}, {}


def build_inline_workload(point: Dict[str, Any]) -> ResolvedWorkload:
    workload_name = str(point["workload"])
    return ResolvedWorkload(
        name=workload_name,
        exec_binding=DEFAULT_EXEC_BINDINGS.get(workload_name, workload_name),
        motif=str(point.get("workload_motif", workload_name)),
        definition_ref=None,
        status=str(point.get("workload_status", "inline_binding")),
        trace_ref=None,
        trace_summary={},
        trace_scalars={},
    )


def load_workload_definition(point: Dict[str, Any], repo_root: Path) -> ResolvedWorkload:
    workload_ref = Path(point["workload_ref"])
    definition_path = workload_ref if workload_ref.is_absolute() else repo_root / workload_ref
    workload_payload = load_json(definition_path)

    workload_name = workload_payload.get("picasso_workload")
    if not workload_name:
        raise ValueError(f"workload_ref '{point['workload_ref']}' does not expose a runnable picasso_workload")

    trace_path = resolve_trace_path(
        workload_payload.get("trace_ref") or workload_payload.get("generated_output"),
        repo_root,
    )
    trace_summary: Dict[str, Any] = {}
    trace_scalars: Dict[str, float] = {}
    if trace_path and trace_path.exists():
        trace_summary, trace_scalars = summarize_trace(str(workload_name), load_json(trace_path))

    return ResolvedWorkload(
        name=str(workload_name),
        exec_binding=str(workload_payload.get("execution_binding", DEFAULT_EXEC_BINDINGS.get(str(workload_name), str(workload_name)))),
        motif=str(workload_payload.get("motif", workload_name)),
        definition_ref=relative_to_repo(definition_path, repo_root),
        status=str(workload_payload.get("status", "declared")),
        trace_ref=relative_to_repo(trace_path, repo_root),
        trace_summary=trace_summary,
        trace_scalars=trace_scalars,
    )


def resolve_workload(repo_root: Path, point: Dict[str, Any]) -> Dict[str, Any]:
    resolved_workload = load_workload_definition(point, repo_root) if "workload_ref" in point else build_inline_workload(point)
    resolved = dict(point)
    resolved["workload"] = resolved_workload.name
    resolved["workload_exec_binding"] = resolved_workload.exec_binding
    resolved["workload_motif"] = resolved_workload.motif
    resolved["workload_ref"] = resolved_workload.definition_ref
    resolved["workload_status"] = resolved_workload.status
    resolved["workload_trace_ref"] = resolved_workload.trace_ref
    resolved["workload_trace_summary"] = resolved_workload.trace_summary
    resolved["workload_trace_scalars"] = resolved_workload.trace_scalars
    return resolved
