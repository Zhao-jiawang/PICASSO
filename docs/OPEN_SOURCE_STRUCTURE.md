# Open Source Structure

## Runtime Code Ownership

- `picasso/`
  - Primary runtime package.
  - Reusable evaluator, legality, search, pipeline, and workload logic live here.
- `pyscripts/`
  - Script entrypoints grouped by responsibility.
  - These should stay thin and call into `picasso/`.
- `scripts/`
  - Reproducible shell wrappers for smoke, paper-core, paper-full, backend, and figure rebuild flows.

## Data and Artifacts

- `configs/`: experiment and model registries.
- `workloads/`: workload identities and generated traces.
- `results/`: raw, aggregated, plot-ready, figure, and backend outputs.
- `paper/figures/`: paper-facing figure copies.
- `docs/`: execution, mapping, planning, and checklist documents.

## Legacy Policy

- The pre-refactor C++ tree has already been removed.
- Do not reintroduce `src/`, `include/`, root-level sweep scripts, or compatibility-only directories.
- Historical ideas may be referenced conceptually, but final code must remain PICASSO-owned Python code.

## Contributor Rules

- Keep core runtime changes in `picasso/`.
- Keep directories responsibility-oriented and easy to scan.
- Prefer small, purpose-specific modules over large catch-all files.
- Place new files where a reader would expect to find them from the path alone.
- Use explicit names that reveal the file's main job from the filename alone.
- Avoid vague names such as `utils.py`, `helpers.py`, `common.py`, `misc.py`, or `temp.py` unless the abstraction is genuinely narrow and obvious.
- Keep cross-cutting data contracts explicit in `configs/picasso_runner_schema.json`.
- Do not add hidden defaults in shell wrappers.
- Every new output table or figure must remain traceable back to `results/raw/` design IDs.
