# AGENT CONTRACT

## Mission

Continue building the PICASSO artifact on top of the current Python-native repository.

The implementation target is a reproducible, paper-aligned artifact. The target is not a recommendation memo, a partial patch, or a plotting-only update.

Start from the repository as it actually exists today:

- unified runtime code under `picasso/`
- categorized Python entrypoints under `pyscripts/`
- reproducible shell entrypoints under `scripts/`
- structured outputs under `results/`
- no remaining C++ execution surface

## Source of Truth Order

Read and follow sources in this order:

1. `docs/PROJECT_STATEMENT_CODEX.md`
2. `docs/AGENT.md`
3. `docs/Plan.md`
4. `docs/Checklist.md`
5. Repository inline comments and current implementation details

When historical implementation details conflict with the PICASSO specification, the PICASSO specification wins.

## Non-negotiable Constraints

- Previous compatibility artifacts must not be reintroduced.
- `legality` is a mandatory PICASSO core capability and must not be removed.
- The search state must remain `d=(m,a,k,i,p,b)`.
- Do not perform line-by-line translation from any historical implementation.
- Treat future work as PICASSO artifact work on top of a completed refactor, not as another migration pass.
- Maintain clean directory management and readable module boundaries.
- Use filenames and module names that make the primary responsibility obvious without opening the file.
- Interface, package, and memory must remain inside the search state.
- Edge, route, and memory legality must act inside the inner loop.
- Memory legality must not be reduced to an unconstrained bandwidth scalar.
- The required workload set must include all six PICASSO motifs.
- The required baseline set must include Joint plus the declared projected baselines.
- All paper-facing results must follow `raw -> aggregated -> plot_ready -> figures -> paper`.
- All sampled backend closure points must originate from one canonical design record.

## Execution Priorities

1. Preserve the Python-native runtime surface.
2. Tighten evaluator, legality checks, and centralized parameterization.
3. Keep workload and trace handling in the package-owned workload layer.
4. Keep search, baselines, and budgets fair and traceable.
5. Keep aggregation, plot-ready outputs, figure generation, and backend closure reproducible.
6. Sync README, REPRODUCE, PAPER_MAPPING, and paper figure paths after code changes.
7. Run smoke, then paper-core, then paper-full, then backend and figure rebuilds.

## Required Logging and Traceability

- Every design point must carry a unique `design_id`.
- Every experiment output must save a config snapshot with at least:
  - sweep config
  - git commit
  - timestamp
  - command line
- Every search run must log at least:
  - round
  - seed
  - move family
  - accepted or rejected
  - legal or illegal
  - illegal reason
  - best score
  - temperature
  - elapsed time
- Every figure must be traceable back to plot-ready data, aggregated data, raw logs, and `design_id` sets.
- Every backend replay point must be traceable back to the canonical design record.

## Result Integrity Rules

- Never hand-edit CSV, JSON, PDF, or PNG outputs.
- Never weaken projected baselines to favor Joint.
- Never hardcode paper numbers into plotting or summary scripts.
- Never let different backends consume different logical inputs for the same sampled point.
- Never silently skip failed workloads, baselines, or missing data files.
- Never describe backend closure as sign-off correctness. Use decision-preservation language only.

## Failure Handling

- Fail loudly on missing inputs, missing columns, empty aggregate files, malformed snapshots, or missing figure dependencies.
- Record workload or baseline failures in summary outputs instead of silently skipping them.
- If a measured trend disagrees with the paper direction, investigate model definition, workload traces, legality criteria, and baseline fairness before adjusting claims.
