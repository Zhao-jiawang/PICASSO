# PICASSO Acceptance Status

Generated from `pyscripts/analysis/audit_acceptance.py` on `2026-04-05T14:45:23.662932+00:00`.

## Summary

- Calibration freeze recommended: `True`
- Passed checks: `77`
- Open checks: `0`

## Current Contexts

- `paper_smoke`: `results/aggregated/20260405_205311_paper_smoke`
- `paper_core`: `results/aggregated/20260405_205311_paper_core_bootstrap`
- `paper_full`: `results/aggregated/20260405_205311_paper_full_bootstrap`
- `plot_smoke`: `results/plot_ready/20260405_205311_paper_smoke`
- `plot_core`: `results/plot_ready/20260405_205311_paper_core_bootstrap`
- `plot_full`: `results/plot_ready/20260405_205311_paper_full_bootstrap`
- `backend_smoke`: `results/backend_aggregated/20260405_205311_paper_smoke`
- `backend_core`: `results/backend_aggregated/20260405_205311_paper_core_bootstrap`
- `backend_full`: `results/backend_aggregated/20260405_205311_paper_full_bootstrap`

## Run Legality

- `paper_smoke`: `1/1` legal from `results/aggregated/20260405_205311_paper_smoke`
- `paper_core`: `24/24` legal from `results/aggregated/20260405_205311_paper_core_bootstrap`
- `paper_full`: `64/64` legal from `results/aggregated/20260405_205311_paper_full_bootstrap`

## Validation Anchors

- Package ordering: `{'FO': 5.700171, 'OS': 0.848748, 'SI': 12.134084}`
- Compute grounding sanity: `[{'process_node': '7', 'latency_advantage_vs_12nm': '2.653061', 'latency_advantage_basis': 'process_registry_fallback', 'matched_anchor_count': '0'}, {'process_node': '12', 'latency_advantage_vs_12nm': '1.000000', 'latency_advantage_basis': 'baseline', 'matched_anchor_count': '0'}]`

## Open Items

- None.

## Recommended Focus

- Default work should stay on PICASSO artifact and paper-sync tasks rather than reopening evaluator calibration.
- Use this audit together with `docs/Checklist.md` to distinguish completed scaffolding from still-open hardening tasks.

