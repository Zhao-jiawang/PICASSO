# PICASSO README

This document describes the current Python-native execution surface of the PICASSO repository.

## Current Status

- The code-refactor gate is complete.
- The latest automated acceptance audit supports freezing calibration by default.
- The current official bundles are `1/1`, `24/24`, and `64/64` legal for `smoke`, `paper_core`, and `paper_full`.
- Current backend closure outputs are present as projected decision-preservation summaries, not sign-off correctness claims.

See:

- `docs/CODE_REFACTOR_CHECKLIST.md`
- `docs/ACCEPTANCE_STATUS.md`
- `docs/CALIBRATION_STATUS_ZH.md`
- `results/acceptance/current_acceptance_audit.json`
- `LICENSE`
- `NOTICE`
- `ACKNOWLEDGMENTS.md`

## What Is Implemented Now

- Unified runtime code under `picasso/`
- Categorized Python entrypoints under `pyscripts/`
- Reproducible shell entrypoints under `scripts/`
- Central config registries under `configs/`
- Six runnable workload motifs under `workloads/`
- Run bundles under `results/raw/`, `results/aggregated/`, and `results/plot_ready/`
- Canonical design records and model-parameterization exports
- Validation data plus Fig. 3 to Fig. 8 rendering into `results/figures/` and `paper/figures/`
- Backend aggregate summaries under `results/backend_aggregated/`, plus regenerable local tool-input directories under `results/backend/`
- A source-semantic recovery ledger under `docs/SRC_SEMANTIC_RECOVERY_LEDGER.md`

The code-refactor gate is complete. The repository no longer depends on the pre-refactor C++ tree or root-level sweep scripts.

The public repository intentionally omits historical run bundles and generated backend tool-input directories beyond the latest accepted bundles. Rebuild them locally from `scripts/` when needed.

## Current Commands

Run the workload traces:

```bash
./scripts/generate_workload_traces.sh
```

Run the three main execution tiers:

```bash
./scripts/run_smoke.sh
./scripts/run_paper_core.sh
./scripts/run_paper_full.sh
./scripts/run_paper_full_parallel.sh --jobs 16
```

Generate validation and figures:

```bash
python3 pyscripts/analysis/gen_validation.py
./scripts/run_figure4.sh
./scripts/run_figure5.sh
./scripts/run_figure6.sh
./scripts/run_figure7.sh
./scripts/run_figure8.sh
```

Generate backend closure summaries:

```bash
./scripts/run_backend_smoke.sh
./scripts/run_backend_core.sh
./scripts/run_backend_full.sh
```

Run the acceptance audit:

```bash
python3 pyscripts/analysis/audit_acceptance.py
```

This refreshes:

- `docs/ACCEPTANCE_STATUS.md`
- `results/acceptance/current_acceptance_audit.md`
- `results/acceptance/current_acceptance_audit.json`

Resume an interrupted run bundle in place:

```bash
PICASSO_RUN_NAME=<existing_run_name> ./scripts/run_paper_full.sh
```

## Current Default Work

Default work is no longer migration or evaluator rescue. It is PICASSO artifact work on top of the accepted runtime, including:

- keeping paper wording aligned with generated figures and closure summaries
- keeping backend closure language scoped to projected decision preservation
- continuing documentation sync as the artifact matures
- continuing reviewer-facing hardening and open-source cleanup
- using `results/aggregated/model_parameterization.json` as the cited parameter dictionary for README and paper mapping
