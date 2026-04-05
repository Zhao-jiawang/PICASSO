# Reproduce PICASSO Artifact

This file documents the current Python-native reproduction flow and the acceptance audit that should be run after each official bundle refresh.

## Prerequisites

- Python 3
- Python packages from `requirements.txt`

Install dependencies:

```bash
pip install -r requirements.txt
```

## Generate Workload Traces

```bash
./scripts/generate_workload_traces.sh
```

## Main Run Tiers

Smoke:

```bash
./scripts/run_smoke.sh
```

Paper core:

```bash
./scripts/run_paper_core.sh
```

Paper full:

```bash
./scripts/run_paper_full.sh
```

Parallel paper full:

```bash
./scripts/run_paper_full_parallel.sh --jobs 16
```

The latest official bundles are stored under:

- `results/raw/`
- `results/aggregated/`
- `results/plot_ready/`

Each point emits:

- `stdout.log`
- `stderr.log`
- `point_snapshot.json`
- `search_trace.jsonl`

Each aggregated bundle emits:

- `result.csv`
- `manifest.json`
- `design_records.json`

The aggregated parameter dictionary is exported to:

- `results/aggregated/model_parameterization.json`

This file is the current artifact-side reference for `Be(i,p)`, `Gedge(p,k)`, `Rbudget(p)`, `I(d)`, and `P(d)`.

## Validation and Figure Rebuild

Generate validation outputs and Fig. 3:

```bash
python3 pyscripts/analysis/gen_validation.py
```

Generate Fig. 4 to Fig. 8:

```bash
./scripts/run_figure4.sh
./scripts/run_figure5.sh
./scripts/run_figure6.sh
./scripts/run_figure7.sh
./scripts/run_figure8.sh
```

Rendered figures are refreshed under:

- `results/figures/`
- `paper/figures/`

Plot-ready CSVs are refreshed under the latest bundle in:

- `results/plot_ready/`

## Backend Closure Rebuild

```bash
./scripts/run_backend_smoke.sh
./scripts/run_backend_core.sh
./scripts/run_backend_full.sh
```

Backend replay inputs and aggregated closure outputs live under:

- `results/backend/`
- `results/backend_aggregated/`

Current backend aggregate files include:

- `winner_agreement.csv`
- `legality_confusion.csv`
- `boundary_drift_backend.csv`
- `claim_closure.csv`
- `closure_summary.csv`
- `closure_summary.json`
- `router_sensitivity.csv`
- `package_cost_ordering_check.csv`
- `deployment_regime_summary.csv`

## Acceptance Audit

After refreshing an official run bundle, regenerate the acceptance audit:

```bash
python3 pyscripts/analysis/audit_acceptance.py
```

This produces:

- `docs/ACCEPTANCE_STATUS.md`
- `results/acceptance/current_acceptance_audit.md`
- `results/acceptance/current_acceptance_audit.json`

Use this audit as the current-state source of truth for:

- whether calibration can be frozen
- whether latest `smoke / paper_core / paper_full` bundles are fully legal
- whether backend closure still contains placeholder rows

## Notes

- `docs/Checklist.md` remains the exit-gate checklist.
- `docs/ACCEPTANCE_STATUS.md` records the current audited state against that checklist.
- The current accepted bundle keeps calibration frozen by default; reopen calibration only if the audit reports legality regressions or backend placeholder rows.
