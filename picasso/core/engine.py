from __future__ import annotations

import random
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict

from .baselines import load_baseline_profile
from .common_math import stable_int
from .evaluator import evaluate_candidate
from .models import NormalizedPoint, SearchExecution
from .registries import load_registry_bundle
from .result_serialization import result_tokens
from .search import run_search_loop


def point_from_dict(point: Dict[str, Any]) -> NormalizedPoint:
    return NormalizedPoint(**point)


def run_python_search(repo_root: Path, point_payload: Dict[str, Any], design_id: str) -> SearchExecution:
    point = point_from_dict(point_payload)
    bundle = load_registry_bundle(str(repo_root))
    profile = load_baseline_profile(repo_root, point.baseline_mode)
    rng = random.Random(point.seed + stable_int(point.baseline_mode) % 10_000)

    proposal_budget = max(1, int(point.proposal_budget or max(16, point.rr * 64)))
    time_cap_seconds = float(point.time_cap_minutes or 0.0) * 60.0 if point.time_cap_minutes else None
    loop_result = run_search_loop(
        point=point,
        profile=profile,
        rng=rng,
        evaluate_state=lambda state: evaluate_candidate(point, state, profile, bundle),
        proposal_budget=proposal_budget,
        time_cap_seconds=time_cap_seconds,
    )

    raw_tokens = result_tokens(point, loop_result.best_eval, loop_result.best_round)
    summary = {
        "engine": "python_native",
        "baseline_mode": point.baseline_mode,
        "best_round": loop_result.best_round,
        "proposal_budget": loop_result.proposal_budget,
        "accepted_moves": loop_result.accepted_moves,
        "legal_moves": loop_result.legal_moves,
        "runtime_seconds": loop_result.runtime_seconds,
        "best_state": asdict(loop_result.best_state),
        "best_eval": {
            "objective_score": loop_result.best_eval.objective_score,
            "cycle": loop_result.best_eval.cycle,
            "energy": loop_result.best_eval.energy,
            "edp": loop_result.best_eval.edp,
            "cost_overall": loop_result.best_eval.cost_overall,
            "legal": loop_result.best_eval.legal,
            "legality_flags": loop_result.best_eval.legality_flags,
            "illegal_reasons": loop_result.best_eval.illegal_reasons,
            "derived_terms": loop_result.best_eval.derived_terms,
        },
    }
    stdout = (
        f"[PICASSO] Python engine completed {design_id}\n"
        f"[PICASSO] baseline={point.baseline_mode} proposals={loop_result.proposal_budget} "
        f"accepted={loop_result.accepted_moves} legal={loop_result.legal_moves}\n"
        f"[PICASSO] best_round={loop_result.best_round} objective={loop_result.best_eval.objective_score:.5f} "
        f"cycle={loop_result.best_eval.cycle} energy={loop_result.best_eval.energy:.5f}\n"
    )
    return SearchExecution(
        raw_tokens=raw_tokens,
        trace_entries=loop_result.trace_entries,
        stdout=stdout,
        stderr="",
        summary=summary,
    )
