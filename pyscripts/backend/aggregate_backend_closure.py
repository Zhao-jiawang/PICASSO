#!/usr/bin/env python3

import argparse
import csv
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence, Tuple


def load_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def dump_json(path: Path, payload: Dict[str, Any]) -> None:
    with path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, sort_keys=True)
        fh.write("\n")


def write_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    if not rows:
        raise ValueError(f"No rows provided for {path}")
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def canonical_score(record: Dict[str, Any]) -> float:
    return float(record["surrogate_metrics"]["edp"])


def metric(record: Dict[str, Any], name: str, route_capacity_scale: float = 1.0) -> float:
    derived = record.get("derived_terms", {})
    if name == "total_die_area":
        return float(record["die_area_breakdown"]["total_die_area"])
    if name == "io_die_area":
        return float(record["die_area_breakdown"]["io_die_area"])
    if name == "phy_count":
        return float(record.get("phy_count", 0.0))
    if name == "buffer_area":
        return float(derived.get("buffer_area", 0.0))
    if name == "package_area":
        return float(derived.get("package_area", 0.0))
    if name == "interposer_area":
        return float(derived.get("interposer_area", 0.0))
    if name == "cost_package":
        return float(record["cost_breakdown"]["cost_package"])
    if name == "latency_cycles":
        return float(record["surrogate_metrics"]["latency_cycles"])
    if name == "serialization_ratio":
        return float(derived.get("serialization_ratio", 0.0)) / max(route_capacity_scale, 1e-9)
    if name == "peak_route_link_gbps":
        return float(derived.get("peak_route_link_gbps", 0.0)) / max(route_capacity_scale, 1e-9)
    if name == "total_interchip_bw":
        return float(derived.get("total_interchip_bw", 0.0))
    if name == "noc_pressure":
        return float(derived.get("peak_route_link_gbps", 0.0)) / max(
            float(derived.get("peak_route_link_gbps", 0.0)) + min(float(derived.get("route_margin", 0.0)), float(derived.get("noc_margin", 0.0))),
            1e-9,
        ) / max(route_capacity_scale, 1e-9)
    if name == "peak_dram_channel_gbps":
        return float(derived.get("peak_dram_channel_gbps", 0.0))
    if name == "dram_channel_imbalance":
        return float(derived.get("dram_channel_imbalance", 0.0))
    if name == "channel_utilization":
        available = max(float(derived.get("channel_count_available", 1.0)), 1.0)
        required = float(derived.get("channel_count_required", 0.0))
        return required / available
    raise KeyError(f"Unknown metric: {name}")


BACKEND_COMPONENTS: Dict[str, Sequence[Tuple[str, float]]] = {
    "floorplan": (
        ("total_die_area", 0.45),
        ("io_die_area", 0.20),
        ("phy_count", 0.15),
        ("buffer_area", 0.20),
    ),
    "package_router": (
        ("cost_package", 0.40),
        ("package_area", 0.20),
        ("interposer_area", 0.10),
        ("serialization_ratio", 0.30),
    ),
    "booksim": (
        ("latency_cycles", 0.30),
        ("peak_route_link_gbps", 0.35),
        ("total_interchip_bw", 0.20),
        ("noc_pressure", 0.15),
    ),
    "ramulator": (
        ("latency_cycles", 0.25),
        ("peak_dram_channel_gbps", 0.35),
        ("dram_channel_imbalance", 0.20),
        ("channel_utilization", 0.20),
    ),
}


def normalize(values: Dict[str, float]) -> Dict[str, float]:
    if not values:
        return {}
    lo = min(values.values())
    hi = max(values.values())
    if hi - lo <= 1e-12:
        return {key: 0.0 for key in values}
    return {key: (value - lo) / (hi - lo) for key, value in values.items()}


def backend_scores(records: Sequence[Dict[str, Any]], backend_name: str, route_capacity_scale: float = 1.0) -> Dict[str, float]:
    components = BACKEND_COMPONENTS[backend_name]
    normalized_components: Dict[str, Dict[str, float]] = {}
    for metric_name, _ in components:
        raw_values = {record["design_id"]: metric(record, metric_name, route_capacity_scale) for record in records}
        normalized_components[metric_name] = normalize(raw_values)

    scores: Dict[str, float] = {}
    for record in records:
        design_id = record["design_id"]
        score = 0.0
        for metric_name, weight in components:
            score += weight * normalized_components[metric_name][design_id]
        if record.get("legality_flags", {}).get("overall") != "legal":
            score += 10.0
        scores[design_id] = score
    return scores


def ordered_by_score(records: Sequence[Dict[str, Any]], score_map: Dict[str, float]) -> List[Dict[str, Any]]:
    return sorted(records, key=lambda record: (score_map[record["design_id"]], canonical_score(record), record["design_id"]))


def ordered_by_canonical(records: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return sorted(records, key=lambda record: (canonical_score(record), record["design_id"]))


def precision_recall(actual_positive: List[bool], predicted_positive: List[bool]) -> Tuple[float, float]:
    tp = sum(1 for actual, predicted in zip(actual_positive, predicted_positive) if actual and predicted)
    fp = sum(1 for actual, predicted in zip(actual_positive, predicted_positive) if not actual and predicted)
    fn = sum(1 for actual, predicted in zip(actual_positive, predicted_positive) if actual and not predicted)
    precision = tp / (tp + fp) if (tp + fp) else 1.0
    recall = tp / (tp + fn) if (tp + fn) else 1.0
    return precision, recall


def chiplet_regime(record: Dict[str, Any]) -> str:
    chiplet_count = int(record["state_tuple"]["k"]["chiplet_count"])
    if chiplet_count <= 1:
        return "mono"
    if chiplet_count <= 4:
        return "few"
    return "many"


def route_margin_under_scale(record: Dict[str, Any], route_capacity_scale: float) -> float:
    derived = record.get("derived_terms", {})
    demand = float(derived.get("peak_route_link_gbps", 0.0))
    headroom = min(float(derived.get("route_margin", 0.0)), float(derived.get("noc_margin", 0.0)))
    return route_capacity_scale * (demand + headroom) - demand


def predicted_legality(record: Dict[str, Any], route_capacity_scale: float = 1.0) -> Dict[str, bool]:
    details = record.get("legality_details", {})
    derived = record.get("derived_terms", {})
    edge_legal = float(record.get("closure_terms", {}).get("M1", 0.0)) >= 0.0
    route_legal = route_margin_under_scale(record, route_capacity_scale) >= 0.0
    memory_legal = (
        float(details.get("channel_count_available", 0.0)) >= float(details.get("channel_count_required", 0.0))
        and float(derived.get("dram_channel_margin", 0.0)) >= 0.0
        and float(record.get("closure_terms", {}).get("M2", 0.0)) >= 0.0
        and float(derived.get("buffer_margin", 0.0)) >= 0.0
        and float(details.get("io_competition_score", 0.0)) <= 1.0
    )
    overall = edge_legal and route_legal and memory_legal
    return {
        "overall": overall,
        "edge": edge_legal,
        "route": route_legal,
        "memory": memory_legal,
    }


def average(values: Iterable[float]) -> float:
    values = list(values)
    return sum(values) / len(values) if values else 0.0


def drift_between(regime_a: str, regime_b: str, left: str, right: str) -> bool:
    return {regime_a, regime_b} == {left, right}


def backend_agreement_rows(cohorts: Dict[str, List[str]], record_map: Dict[str, Dict[str, Any]], route_capacity_scale: float = 1.0) -> Tuple[List[Dict[str, Any]], Dict[str, float]]:
    rows: List[Dict[str, Any]] = []
    drift_counts = {
        "mono_few": 0.0,
        "few_many": 0.0,
        "si_sp_crossing": 0.0,
    }
    drift_total = 0.0

    for cohort, design_ids in cohorts.items():
        cohort_records = [record_map[design_id] for design_id in design_ids if design_id in record_map]
        if not cohort_records:
            continue
        canonical_ranked = ordered_by_canonical(cohort_records)
        canonical_top = canonical_ranked[0]
        canonical_top3 = {record["design_id"] for record in canonical_ranked[: min(3, len(canonical_ranked))]}
        agreement_flags = []
        overlap_scores = []
        regrets = []

        for backend_name in BACKEND_COMPONENTS:
            score_map = backend_scores(cohort_records, backend_name, route_capacity_scale)
            ranked = ordered_by_score(cohort_records, score_map)
            backend_top = ranked[0]
            backend_top3 = {record["design_id"] for record in ranked[: min(3, len(ranked))]}
            agreement_flags.append(1.0 if backend_top["design_id"] == canonical_top["design_id"] else 0.0)
            overlap_scores.append(len(canonical_top3 & backend_top3) / max(len(canonical_top3), 1))
            regrets.append(
                (canonical_score(backend_top) - canonical_score(canonical_top)) / max(canonical_score(canonical_top), 1e-9)
            )

            canonical_regime = chiplet_regime(canonical_top)
            backend_regime = chiplet_regime(backend_top)
            drift_counts["mono_few"] += 1.0 if drift_between(canonical_regime, backend_regime, "mono", "few") else 0.0
            drift_counts["few_many"] += 1.0 if drift_between(canonical_regime, backend_regime, "few", "many") else 0.0
            drift_counts["si_sp_crossing"] += 1.0 if ((canonical_top["package_class"] == "SI") != (backend_top["package_class"] == "SI")) else 0.0
            drift_total += 1.0

        rows.append(
            {
                "cohort": cohort,
                "top1_agreement": f"{average(agreement_flags):.6f}",
                "top3_overlap": f"{average(overlap_scores):.6f}",
                "backend_regret": f"{average(regrets):.6f}",
                "status": "projected_decision_preservation",
                "count": len(cohort_records),
            }
        )

    drift_metrics = {
        "mono_few": drift_counts["mono_few"] / max(drift_total, 1.0),
        "few_many": drift_counts["few_many"] / max(drift_total, 1.0),
        "si_sp_crossing": drift_counts["si_sp_crossing"] / max(drift_total, 1.0),
    }
    return rows, drift_metrics


def legality_confusion_rows(sampled_records: Sequence[Dict[str, Any]], route_capacity_scale: float = 1.0) -> Tuple[List[Dict[str, Any]], Dict[str, float]]:
    rows: List[Dict[str, Any]] = []
    summary: Dict[str, float] = {}
    for category in ("overall", "edge", "route", "memory"):
        actual = [record.get("legality_flags", {}).get(category) == "legal" for record in sampled_records]
        predicted = [predicted_legality(record, route_capacity_scale)[category] for record in sampled_records]
        precision, recall = precision_recall(actual, predicted)
        rows.append(
            {
                "category": category,
                "precision": f"{precision:.6f}",
                "recall": f"{recall:.6f}",
                "status": "projected_decision_preservation",
            }
        )
        if category == "overall":
            summary["precision"] = precision
            summary["recall"] = recall
    return rows, summary


def m1_m2_sign_consistency(sampled_records: Sequence[Dict[str, Any]]) -> float:
    if not sampled_records:
        return 1.0
    consistent = 0
    for record in sampled_records:
        edge_sign = float(record.get("closure_terms", {}).get("M1", 0.0)) >= 0.0
        memory_sign = float(record.get("closure_terms", {}).get("M2", 0.0)) >= 0.0
        consistent += 1 if (
            edge_sign == (record.get("legality_flags", {}).get("edge") == "legal")
            and memory_sign == (record.get("legality_flags", {}).get("memory") == "legal")
        ) else 0
    return consistent / len(sampled_records)


def boundary_rows(drift_metrics: Dict[str, float], sign_consistency: float) -> List[Dict[str, Any]]:
    return [
        {"metric": "mono_few", "value": f"{drift_metrics['mono_few']:.6f}", "status": "projected_decision_preservation"},
        {"metric": "few_many", "value": f"{drift_metrics['few_many']:.6f}", "status": "projected_decision_preservation"},
        {"metric": "si_sp_crossing", "value": f"{drift_metrics['si_sp_crossing']:.6f}", "status": "projected_decision_preservation"},
        {"metric": "m1_m2_sign_consistency", "value": f"{sign_consistency:.6f}", "status": "projected_decision_preservation"},
    ]


def router_sensitivity_rows(cohorts: Dict[str, List[str]], record_map: Dict[str, Dict[str, Any]], sampled_records: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for case_name, route_scale in (
        ("nominal", 1.0),
        ("minus_15_percent", 0.85),
        ("plus_15_percent", 1.15),
    ):
        agreement_rows, drift_metrics = backend_agreement_rows(cohorts, record_map, route_capacity_scale=route_scale)
        confusion_rows, confusion_summary = legality_confusion_rows(sampled_records, route_capacity_scale=route_scale)
        winner_agreement = average(float(row["top1_agreement"]) for row in agreement_rows)
        boundary_drift = average([drift_metrics["mono_few"], drift_metrics["few_many"]])
        rows.append(
            {
                "capacity_case": case_name,
                "winner_agreement": f"{winner_agreement:.6f}",
                "precision": f"{confusion_summary['precision']:.6f}",
                "recall": f"{confusion_summary['recall']:.6f}",
                "boundary_drift": f"{boundary_drift:.6f}",
                "status": "projected_decision_preservation",
            }
        )
        del confusion_rows
    return rows


def package_cost_rows(records: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    package_groups: Dict[str, List[Dict[str, Any]]] = {}
    for record in records:
        package_groups.setdefault(record["package_class"], []).append(record)

    avg_costs = {
        package_name: average(float(record["cost_breakdown"]["cost_package"]) for record in grouped)
        for package_name, grouped in package_groups.items()
    }
    ordering_ok = all(key in avg_costs for key in ("OS", "FO", "SI")) and avg_costs["OS"] < avg_costs["FO"] < avg_costs["SI"]
    status = "stable_in_sweep" if ordering_ok else "ordering_violation"

    rows = []
    for package_name in sorted(package_groups):
        rows.append(
            {
                "package_class": package_name,
                "process_bucket": "all",
                "node_target_bucket": "all",
                "monolithic_equivalent_area_bucket": "all",
                "avg_package_cost": f"{avg_costs[package_name]:.6f}",
                "ordering_status": status,
            }
        )
    return rows


def recommended_regime(records: Sequence[Dict[str, Any]]) -> str:
    if not records:
        return "insufficient_data"
    best = ordered_by_canonical(records)[0]
    regime = chiplet_regime(best)
    return {
        "mono": "mono_chiplet",
        "few": "few_chiplet",
        "many": "many_chiplet",
    }[regime]


def optimization_lever(records: Sequence[Dict[str, Any]]) -> Tuple[str, str]:
    if not records:
        return "insufficient_data", "n/a"
    derived = [record.get("derived_terms", {}) for record in records]
    avg_serial = average(float(item.get("serialization_ratio", 0.0)) for item in derived)
    avg_dram = average(float(item.get("peak_dram_channel_gbps", 0.0)) / max(float(item.get("peak_dram_channel_gbps", 0.0)) + float(item.get("dram_channel_margin", 0.0)), 1e-9) for item in derived)
    avg_package_share = average(float(record["cost_breakdown"]["cost_package"]) / max(float(record["cost_breakdown"]["cost_soc"]), 1e-9) for record in records)
    avg_locality = average(1.0 - float(item.get("locality_score", 0.0)) for item in derived)
    lever_scores = {
        "interface": avg_serial,
        "memory": avg_dram,
        "package": avg_package_share,
        "mapping": avg_locality,
    }
    lever = max(lever_scores, key=lever_scores.get)
    trigger = {
        "interface": f"serialization_ratio>={avg_serial:.3f}",
        "memory": f"dram_pressure>={avg_dram:.3f}",
        "package": f"package_cost_share>={avg_package_share:.3f}",
        "mapping": f"locality_deficit>={avg_locality:.3f}",
    }[lever]
    return lever, trigger


def deployment_regime_rows(records: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    joint_records = [record for record in records if record["baseline_mode"] == "Joint"]
    motifs = {
        "serving_latency_tier": {"cnn_inference", "kv_heavy_decode"},
        "serving_throughput_tier": {"long_context_prefill", "dense_decoder_block"},
        "training_cost_pod": {"dense_decoder_block", "long_context_prefill", "mixtral_moe_trace"},
        "training_collective_heavy_pod": {"megatron_collective_trace", "mixtral_moe_trace"},
    }
    rows = []
    for regime_name, allowed_motifs in motifs.items():
        subset = [record for record in joint_records if record.get("workload_motif") in allowed_motifs]
        lever, trigger = optimization_lever(subset)
        rows.append(
            {
                "deployment_regime": regime_name,
                "recommended_chiplet_regime": recommended_regime(subset),
                "optimization_lever": lever,
                "trigger_threshold_range": trigger,
            }
        )
    return rows


def claim_rows(summary: Dict[str, Any], ordering_ok: bool) -> List[Dict[str, Any]]:
    top1 = float(summary["top1_agreement"])
    hard = float(summary["hard_slice_agreement"])
    precision = float(summary["legal_precision"])
    recall = float(summary["legal_recall"])
    boundary = max(float(summary["mono_few_boundary_drift"]), float(summary["few_many_boundary_drift"]))

    def classify() -> str:
        if top1 >= 0.95 and hard >= 0.90 and precision >= 0.95 and recall >= 0.95 and boundary <= 0.10:
            return "robust"
        if boundary <= 0.20 and precision >= 0.90 and recall >= 0.90:
            return "conditional"
        return "boundary-sensitive"

    closure_status = classify()
    return [
        {
            "claim_id": "backend_decision_preservation",
            "closure_status": closure_status,
            "notes": "Projected backend agreement is computed from canonical design-record projections, not backend sign-off correctness.",
        },
        {
            "claim_id": "legality_classification_preservation",
            "closure_status": "robust" if precision >= 0.95 and recall >= 0.95 else "conditional",
            "notes": "Precision and recall are measured against canonical legality labels under projected backend perturbations.",
        },
        {
            "claim_id": "package_ordering_stability",
            "closure_status": "robust" if ordering_ok else "conditional",
            "notes": "Ordering is validated over the current sweep as a decision-preservation check.",
        },
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description="Aggregate backend closure outputs from canonical design records")
    parser.add_argument("--aggregated-run", required=True, help="Path to an aggregated run directory")
    parser.add_argument("--sampled-points", required=True, help="Path to sampled_backend_points.json")
    parser.add_argument("--output-dir", required=True, help="Directory to store backend aggregated outputs")
    args = parser.parse_args()

    aggregated_run = Path(args.aggregated_run).resolve()
    sampled_points = load_json(Path(args.sampled_points).resolve())
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    records = load_json(aggregated_run / "design_records.json")["records"]
    record_map = {record["design_id"]: record for record in records}
    cohorts = sampled_points["cohorts"]
    sampled_ids = [design_id for ids in cohorts.values() for design_id in ids if design_id in record_map]
    sampled_records = [record_map[design_id] for design_id in sampled_ids]
    winner_summary_by_baseline = sampled_points.get("winner_summary_by_baseline", {})

    winner_rows, drift_metrics = backend_agreement_rows(cohorts, record_map, route_capacity_scale=1.0)
    confusion_rows, confusion_summary = legality_confusion_rows(sampled_records, route_capacity_scale=1.0)
    sign_consistency = m1_m2_sign_consistency(sampled_records)
    drift_rows = boundary_rows(drift_metrics, sign_consistency)
    router_rows = router_sensitivity_rows(cohorts, record_map, sampled_records)
    package_rows = package_cost_rows(records)
    ordering_ok = all(row["ordering_status"] == "stable_in_sweep" for row in package_rows)
    deployment_rows = deployment_regime_rows(records)

    cohort_sizes = {name: len(ids) for name, ids in cohorts.items()}
    top1_agreement = average(float(row["top1_agreement"]) for row in winner_rows)
    hard_slice_rows = [row for row in winner_rows if row["cohort"] in {"boundary", "near_legality", "disagreement"}]
    hard_slice_agreement = average(float(row["top1_agreement"]) for row in hard_slice_rows)
    closure_summary = {
        "status": "projected_decision_preservation",
        "top1_agreement": round(top1_agreement, 6),
        "hard_slice_agreement": round(hard_slice_agreement, 6),
        "legal_precision": round(confusion_summary["precision"], 6),
        "legal_recall": round(confusion_summary["recall"], 6),
        "mono_few_boundary_drift": round(drift_metrics["mono_few"], 6),
        "few_many_boundary_drift": round(drift_metrics["few_many"], 6),
        "cohort_size_total": sum(cohort_sizes.values()),
        "cohort_size_winner": cohort_sizes.get("winner", 0),
        "cohort_size_boundary": cohort_sizes.get("boundary", 0),
        "cohort_size_near_legality": cohort_sizes.get("near_legality", 0),
        "cohort_size_disagreement": cohort_sizes.get("disagreement", 0),
        "cohort_size_control": cohort_sizes.get("control", 0),
        "source_run": str(aggregated_run),
        "notes": "Backend closure is reported as projected decision preservation over canonical design-record projections. It is not a sign-off correctness claim.",
    }

    write_csv(output_dir / "winner_agreement.csv", winner_rows)
    write_csv(output_dir / "legality_confusion.csv", confusion_rows)
    write_csv(output_dir / "boundary_drift_backend.csv", drift_rows)
    claim_rows_payload = claim_rows(closure_summary, ordering_ok)
    write_csv(output_dir / "claim_closure.csv", claim_rows_payload)
    write_csv(output_dir / "closure_summary.csv", [closure_summary])
    dump_json(output_dir / "closure_summary.json", closure_summary)
    write_csv(output_dir / "router_sensitivity.csv", router_rows)
    write_csv(output_dir / "package_cost_ordering_check.csv", package_rows)
    write_csv(output_dir / "deployment_regime_summary.csv", deployment_rows)

    manifest = {
        "status": "projected_decision_preservation",
        "source_run": str(aggregated_run),
        "baseline_modes": sorted({record["baseline_mode"] for record in records}),
        "generated_files": [
            "winner_agreement.csv",
            "legality_confusion.csv",
            "boundary_drift_backend.csv",
            "claim_closure.csv",
            "closure_summary.csv",
            "closure_summary.json",
            "router_sensitivity.csv",
            "package_cost_ordering_check.csv",
            "deployment_regime_summary.csv",
        ],
        "sampled_points_file": str(Path(args.sampled_points).resolve()),
        "winner_summary_by_baseline": winner_summary_by_baseline,
        "notes": [
            "Closure metrics are projected from canonical design records and backend translation bundles.",
            "The reported values validate decision preservation rather than sign-off correctness.",
        ],
    }
    dump_json(output_dir / "manifest.json", manifest)
    print(f"[PICASSO] Aggregated backend closure outputs into {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
