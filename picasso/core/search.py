from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass, replace
from typing import Callable, List

from .baselines import BaselineProfile
from .common_math import clamp, clamp_int
from .models import EvaluationResult, NormalizedPoint, SearchState, SearchTraceEntry


@dataclass(frozen=True)
class SearchLoopResult:
    best_state: SearchState
    best_eval: EvaluationResult
    best_round: int
    accepted_moves: int
    legal_moves: int
    proposal_budget: int
    runtime_seconds: float
    trace_entries: List[SearchTraceEntry]


def initial_state(rng: random.Random, profile: BaselineProfile) -> SearchState:
    return SearchState(
        mapping_tiling=2 + (profile.rank % 2),
        pipeline_depth=1 + (1 if profile.family != "ablation" else 0),
        segment_span=1 + (profile.rank % 3),
        interleave=profile.package_blindness < 0.2,
        spm_level=1 if profile.name != "Package-oblivious" else 0,
        memory_prefetch=1 if profile.memory_blindness < 0.2 else 0,
        route_slack=0.95 - 0.12 * profile.package_blindness + rng.uniform(-0.03, 0.03),
        memory_balance=0.97 - 0.15 * profile.memory_blindness + rng.uniform(-0.03, 0.03),
        noc_balance=0.98 + rng.uniform(-0.04, 0.04),
        placement_skew=rng.uniform(-0.10, 0.10),
        batch_cluster=profile.family != "ablation",
    )


def choose_move_family(rng: random.Random, profile: BaselineProfile) -> str:
    total = sum(profile.move_weights.values())
    pick = rng.uniform(0.0, total)
    running = 0.0
    for family, weight in profile.move_weights.items():
        running += weight
        if pick <= running:
            return family
    return "coupled"


def mutate_state(rng: random.Random, state: SearchState, move_family: str) -> SearchState:
    updated = state
    if move_family == "map":
        if rng.random() < 0.5:
            updated = replace(updated, mapping_tiling=clamp_int(updated.mapping_tiling + rng.choice([-1, 1]), 1, 4))
        else:
            updated = replace(updated, pipeline_depth=clamp_int(updated.pipeline_depth + rng.choice([-1, 1]), 1, 4))
    elif move_family == "arch":
        if rng.random() < 0.5:
            updated = replace(updated, spm_level=clamp_int(updated.spm_level + rng.choice([-1, 1]), 0, 3))
        else:
            updated = replace(updated, noc_balance=clamp(updated.noc_balance + rng.uniform(-0.08, 0.08), 0.75, 1.25))
    elif move_family == "split":
        if rng.random() < 0.5:
            updated = replace(updated, segment_span=clamp_int(updated.segment_span + rng.choice([-1, 1]), 1, 4))
        else:
            updated = replace(updated, placement_skew=clamp(updated.placement_skew + rng.uniform(-0.10, 0.10), -0.35, 0.35))
        updated = replace(updated, route_slack=clamp(updated.route_slack + rng.uniform(-0.08, 0.08), 0.65, 1.25))
    elif move_family == "interface-package":
        if rng.random() < 0.5:
            updated = replace(updated, interleave=not updated.interleave)
        updated = replace(updated, route_slack=clamp(updated.route_slack + rng.uniform(-0.10, 0.10), 0.65, 1.25))
        updated = replace(updated, noc_balance=clamp(updated.noc_balance + rng.uniform(-0.05, 0.05), 0.75, 1.25))
    elif move_family == "memory":
        if rng.random() < 0.5:
            updated = replace(updated, memory_prefetch=clamp_int(updated.memory_prefetch + rng.choice([-1, 1]), 0, 3))
        updated = replace(updated, memory_balance=clamp(updated.memory_balance + rng.uniform(-0.08, 0.08), 0.70, 1.25))
    else:
        updated = mutate_state(rng, updated, rng.choice(["map", "arch", "split", "interface-package", "memory"]))
        updated = mutate_state(rng, updated, rng.choice(["map", "arch", "split", "interface-package", "memory"]))

    if rng.random() < 0.15:
        updated = replace(updated, batch_cluster=not updated.batch_cluster)
    return updated


def run_search_loop(
    point: NormalizedPoint,
    profile: BaselineProfile,
    rng: random.Random,
    evaluate_state: Callable[[SearchState], EvaluationResult],
    proposal_budget: int,
    time_cap_seconds: float | None,
) -> SearchLoopResult:
    start = time.monotonic()
    current_state = initial_state(rng, profile)
    current_eval = evaluate_state(current_state)
    for _ in range(12):
        if current_eval.legal:
            break
        current_state = mutate_state(rng, current_state, "coupled")
        current_eval = evaluate_state(current_state)

    best_state = current_state
    best_eval = current_eval
    best_round = 0
    accepted_moves = 0
    legal_moves = 0
    trace_entries: List[SearchTraceEntry] = []

    for round_idx in range(1, proposal_budget + 1):
        if time_cap_seconds is not None and (time.monotonic() - start) >= time_cap_seconds:
            break

        move_family = choose_move_family(rng, profile)
        candidate_state = mutate_state(rng, current_state, move_family)
        candidate_eval = evaluate_state(candidate_state)
        temperature = max(0.025, profile.initial_temperature * (profile.cooling ** round_idx))
        accepted = False
        delta = candidate_eval.objective_score - current_eval.objective_score
        if candidate_eval.legal and not current_eval.legal:
            accepted = True
        elif delta <= 0:
            accepted = True
        else:
            threshold = math.exp(-delta / max(temperature * max(abs(current_eval.objective_score), 1.0), 1.0))
            accepted = rng.random() < min(1.0, threshold)

        if accepted:
            current_state = candidate_state
            current_eval = candidate_eval
            accepted_moves += 1
        if candidate_eval.legal:
            legal_moves += 1
            if (not best_eval.legal) or candidate_eval.objective_score < best_eval.objective_score:
                best_state = candidate_state
                best_eval = candidate_eval
                best_round = round_idx

        trace_entries.append(
            SearchTraceEntry(
                round=round_idx,
                seed=point.seed,
                move_family=move_family,
                accepted=accepted,
                legal=candidate_eval.legal,
                illegal_reason="|".join(candidate_eval.illegal_reasons),
                best_score=best_eval.objective_score,
                temperature=temperature,
                elapsed_time=time.monotonic() - start,
            )
        )

    return SearchLoopResult(
        best_state=best_state,
        best_eval=best_eval,
        best_round=best_round,
        accepted_moves=accepted_moves,
        legal_moves=legal_moves,
        proposal_budget=proposal_budget,
        runtime_seconds=time.monotonic() - start,
        trace_entries=trace_entries,
    )

