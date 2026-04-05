# Paper Directory

This directory stores paper-facing figure copies for PICASSO.

## Scope

- `paper/figures/` contains the current generated figure assets that paper text should include.
- These files are derived from `results/figures/`.
- The source of truth remains the generated artifact chain:
  - `results/raw/`
  - `results/aggregated/`
  - `results/plot_ready/`
  - `results/figures/`

## Update Rule

- Do not hand-edit files under `paper/figures/`.
- Refresh figures through the normal scripts in `scripts/` and `pyscripts/analysis/`.
- Use `results/figures/paper_figure_manifest.json` to trace each paper-facing figure back to its inputs and generation command.
