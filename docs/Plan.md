# PICASSO IMPLEMENTATION PLAN

This plan assumes the repository is still in its pre-refactor mixed state and that the PICASSO target architecture has not been implemented yet.

## Phase 0: Audit current repo and establish target scaffold

**Inputs**

- Current root files:
  - `README.md`
  - `makefile`
  - `requirements.txt`
  - `summary.sh`
  - `72tops_dse13.sh`
  - `72tops_dse16.sh`
  - `72tops_dse17.sh`
  - `128tops_dse.sh`
  - `512tops_dse13.sh`
  - `512tops_dse16.sh`
  - `512tops_dse17.sh`
- Current source layout:
  - `include/`
  - `src/`
  - `pyscripts/`
- Current archival inputs:
  - `Project_Statement/`

**Required code or script outputs**

- A documented inventory of previous entrypoints, current output files, and reusable model pieces.
- The initial PICASSO scaffold:
  - `configs/`
  - `workloads/`
  - `scripts/`
  - `results/raw/`
  - `results/aggregated/`
  - `results/plot_ready/`
  - `results/figures/`
  - `results/backend/floorplan/`
  - `results/backend/package/`
  - `results/backend/nop/`
  - `results/backend/memory/`
  - `results/backend_aggregated/`
  - `results/backend_figures/`
  - `docs/README.md`
  - `docs/REPRODUCE.md`
  - `docs/PAPER_MAPPING.md`
  - `paper/figures/`

**New directories or files to create**

- The scaffold listed above.
- Compatibility wrappers if needed for previous root-level DSE scripts.

**Exit criteria**

- The repo has a visible target scaffold.
- Legacy root-level scripts are identified as compatibility inputs, not as the final execution surface.
- The implementation team can see where configuration, workloads, results, documentation, and paper figures will live.

**Dependency on previous phases**

- None.

## Phase 1: Define unified schema and state tuple

**Inputs**

- The audited previous CLI arguments and sweep axes.
- The target PICASSO state definition from `PROJECT_STATEMENT_CODEX.md`.

**Required code or script outputs**

- A unified config schema covering:
  - workload
  - node target
  - process node
  - chiplet count
  - interface class
  - package class
  - memory class
  - seed
  - proposal budget
  - time cap
- A canonical state representation for `d=(m,a,k,i,p,b)`.
- A deterministic `design_id` generation rule.
- Standardized config snapshot generation.
- Canonical experiment entrypoints:
  - `scripts/run_smoke.sh`
  - `scripts/run_paper_core.sh`
  - `scripts/run_paper_full.sh`

**New directories or files to create**

- Config files under `configs/`
- Schema validation helpers in `pyscripts/` and or the C++ core
- Snapshot output paths under `results/raw/`

**Exit criteria**

- New experiments no longer depend on positional shell parameters alone.
- Every candidate point can be represented as a complete PICASSO state tuple.
- Every run can emit a config snapshot that is stable and reproducible.

**Dependency on previous phases**

- Depends on Phase 0 scaffold and audit results.

## Phase 2: Refactor evaluator, legality, and parameterization

**Inputs**

- Existing compute, NoC, and package-related code in `src/` and `include/`
- Unified state and schema from Phase 1

**Required code or script outputs**

- Refactored latency, energy, and cost evaluation paths.
- Centralized parameter tables for:
  - interface envelopes
  - package classes
  - memory classes
- Inner-loop legality checks for:
  - edge
  - route
  - memory
- Structured illegal-reason output.
- Export support for `results/aggregated/model_parameterization.json`.

**New directories or files to create**

- Central parameter files under `configs/`
- Model and legality helpers in `src/` and `include/`
- Export helpers for explainability artifacts in `pyscripts/`

**Exit criteria**

- The evaluator consumes the full state tuple.
- NoP behavior explicitly depends on interface and package.
- Memory legality models attachment constraints, not only bandwidth.
- The repo can export `model_parameterization.json` with `Be(i,p)`, `Gedge(p,k)`, `Rbudget(p)`, `I(d)`, and `P(d)`.

**Dependency on previous phases**

- Depends on Phase 1 state and schema.

## Phase 3: Build workloads and trace generation

**Inputs**

- Phase 1 schema
- Phase 2 evaluator assumptions

**Required code or script outputs**

- Workload definitions and trace generation for:
  - CNN inference
  - long-context prefill
  - KV-heavy decode
  - dense decoder block
  - Mixtral-style MoE trace
  - Megatron-style collective trace
- Deterministic trace generation scripts, including at least:
  - MoE trace generation
  - collective trace generation
- Validation data generation with `pyscripts/analysis/gen_validation.py`

**New directories or files to create**

- Workload configs under `workloads/`
- Trace generation scripts under `pyscripts/`
- Validation data under `results/aggregated/validation/` or an equivalent documented location

**Exit criteria**

- All six workload motifs exist and are runnable through the unified config layer.
- MoE traces include 8 experts, top-2 dispatch, `1.35x` imbalance, and `0.34` locality probability.
- Collective traces include bucketized all-reduce or all-gather with default `128MB` buckets.

**Dependency on previous phases**

- Depends on Phase 1 schema and Phase 2 evaluator definitions.

## Phase 4: Implement joint search and projected baselines

**Inputs**

- Unified state and evaluator from Phases 1 and 2
- Workloads from Phase 3

**Required code or script outputs**

- Joint search implementation with:
  - multiple legal seeds
  - move family
  - annealed acceptance
  - Pareto archive
- Baseline implementations for:
  - Joint
  - Stage-wise
  - Package-oblivious
  - Architecture-first
  - Partition-first
  - Cost/interface-first
  - Outer-loop repair
  - Memory-off
- Fixed-mode switches:
  - interface-fixed
  - package-fixed
- Shared-budget execution logic:
  - 8 seeds
  - 60k proposals per seed or 15-minute cap
- Logging fields:
  - round
  - seed
  - move family
  - accepted
  - legal
  - illegal reason
  - best score
  - temperature
  - elapsed time

**New directories or files to create**

- Search and baseline modules under `src/` and `include/`
- Run-mode configuration files under `configs/`
- Structured raw logs under `results/raw/`

**Exit criteria**

- Joint and all projected baselines run on the same evaluator and budgets.
- Illegal reasons are visible in raw logs.
- Each run emits design points with unique `design_id` values and config snapshots.

**Dependency on previous phases**

- Depends on Phases 1 to 3.

## Phase 5: Build result pipeline and figure-specific aggregation

**Inputs**

- Raw logs from search runs in Phase 4
- Validation outputs from Phase 3

**Required code or script outputs**

- Raw JSON logging for experiment points.
- Aggregation scripts for figure and table data, including:
  - `pyscripts/analysis/gen_validation.py`
  - `pyscripts/analysis/aggregate_illegal_breakdown.py`
  - `pyscripts/analysis/aggregate_weight_sweep.py`
  - `pyscripts/aggregate_figure4.py`
  - `pyscripts/aggregate_figure5.py`
  - `pyscripts/aggregate_figure6.py`
  - `pyscripts/aggregate_figure7.py`
  - `pyscripts/aggregate_figure8.py`
- Plotting scripts for paper-facing figures:
  - `pyscripts/plot_figure3.py`
  - `pyscripts/plot_figure4.py`
  - `pyscripts/plot_figure5.py`
  - `pyscripts/plot_figure6.py`
  - `pyscripts/plot_figure7.py`
  - `pyscripts/plot_figure8.py`
- Figure wrapper entrypoints:
  - `scripts/run_figure4.sh`
  - `scripts/run_figure5.sh`
  - `scripts/run_figure6.sh`
  - `scripts/run_figure7.sh`
  - `scripts/run_figure8.sh`
- Required aggregate outputs:
  - `winner_change_matrix.csv`
  - `reevaluated_loss.csv`
  - `interface_vs_package.csv`
  - `memory_off_ablation.csv`
  - `phase_boundary.csv`
  - `split_margin.csv`
  - `pareto_points.csv`
  - `energy_breakdown.csv`
  - `boundary_drift.csv`
  - `sensitivity_tags.csv`
  - `illegal_breakdown.csv`
  - `weight_shift_summary.csv`

**New directories or files to create**

- `results/raw/`
- `results/aggregated/`
- `results/plot_ready/`
- `results/figures/`

**Exit criteria**

- The result pipeline is fully automated from raw logs to plot-ready data to figures.
- Figures output both PDF and PNG files with final paper-facing names.
- Any figure can be rebuilt from raw or aggregated data without rerunning the search when inputs already exist.

**Dependency on previous phases**

- Depends on Phases 3 and 4.

## Phase 6: Add Combo-A sampled backend closure

**Inputs**

- Design points and winners from Phase 5
- Canonical state and evaluator outputs from earlier phases

**Required code or script outputs**

- Canonical record export:
  - `pyscripts/analysis/export_design_records.py`
- Backend sampling:
  - `pyscripts/backend/sample_backend_points.py`
- Backend translators:
  - `pyscripts/backend/translate_to_openroad.py`
  - `pyscripts/backend/translate_to_package_router.py`
  - `pyscripts/backend/translate_to_booksim.py`
  - `pyscripts/backend/translate_to_ramulator.py`
- Backend runners:
  - `scripts/run_backend_smoke.sh`
  - `scripts/run_backend_core.sh`
  - `scripts/run_backend_full.sh`
- Closure aggregation and plotting:
  - `pyscripts/backend/aggregate_backend_closure.py`
  - `pyscripts/plot_backend_closure.py`
- Required backend aggregate outputs:
  - `winner_agreement.csv`
  - `legality_confusion.csv`
  - `boundary_drift_backend.csv`
  - `claim_closure.csv`
  - `closure_summary.csv`
  - `closure_summary.json`
  - `router_sensitivity.csv`
  - `package_cost_ordering_check.csv`
  - `deployment_regime_summary.csv`

**New directories or files to create**

- `results/backend/floorplan/`
- `results/backend/package/`
- `results/backend/nop/`
- `results/backend/memory/`
- `results/backend_aggregated/`
- `results/backend_figures/`

**Exit criteria**

- Every sampled backend point traces back to a canonical design record and `design_id`.
- All four backends run from unified entrypoints.
- Backend closure produces decision-preservation metrics rather than only average error summaries.
- `paper-core` closure uses the five required cohorts and default total size `220`.

**Dependency on previous phases**

- Depends on Phase 5 and the stable evaluator outputs from earlier phases.

## Phase 7: Sync README, REPRODUCE, PAPER_MAPPING, and paper figures

**Inputs**

- Figure outputs from Phase 5
- Backend closure outputs from Phase 6

**Required code or script outputs**

- `docs/README.md`
- `docs/REPRODUCE.md`
- `docs/PAPER_MAPPING.md`
- `paper_figure_manifest.json`
- Synchronized paper figure copies under `paper/figures/`
- Updated paper include paths, including `main.tex` if required

**New directories or files to create**

- `paper/figures/`
- Any missing paper-side manifest or include metadata files

**Exit criteria**

- README documents smoke, paper-core, and paper-full commands and expected outputs.
- REPRODUCE documents figure rebuild and backend closure rebuild.
- PAPER_MAPPING links each figure and table to scripts and data files in both directions.
- The paper build consumes the latest generated figures rather than historical ones.

**Dependency on previous phases**

- Depends on Phases 5 and 6.

## Phase 8: Run smoke, paper-core, paper-full, then harden reviewer-facing outputs

**Inputs**

- Full pipeline from Phases 0 through 7

**Required code or script outputs**

- Successful `scripts/run_smoke.sh`
- Successful `scripts/run_paper_core.sh`
- Successful `scripts/run_paper_full.sh`
- Reviewer-facing hardening outputs:
  - `results/backend_aggregated/closure_summary.csv`
  - `results/backend_aggregated/closure_summary.json`
  - `results/backend_aggregated/router_sensitivity.csv`
  - `results/backend_aggregated/package_cost_ordering_check.csv`
  - `results/backend_aggregated/deployment_regime_summary.csv`
  - `results/aggregated/model_parameterization.json`
  - `paper_figure_manifest.json`

**New directories or files to create**

- Final run summaries under `results/`
- Final failure summaries if any workload or baseline fails

**Exit criteria**

- Smoke validates the end-to-end pipeline quickly.
- Paper-core validates the central experiment matrix and the `220`-point closure cohort.
- Paper-full covers the full published matrix.
- Figure 8(c), closure tables, README, AD or AE appendix, and the aggregated CSV or JSON outputs all use consistent claims.
- The final artifact can be audited without hand-entered paper values.

**Dependency on previous phases**

- Depends on all previous phases.
