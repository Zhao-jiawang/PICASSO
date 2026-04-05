# PICASSO Paper Mapping

This file maps the current artifact outputs to paper-facing figures and tables.

## Current Status

- The runtime refactor is complete.
- The figure pipeline for Fig. 3 to Fig. 8 is wired and renders into `results/figures/` and `paper/figures/`.
- `results/aggregated/model_parameterization.json` is the current exported parameter dictionary for `Be(i,p)`, `Gedge(p,k)`, `Rbudget(p)`, `I(d)`, and `P(d)`.
- The latest acceptance status is recorded in `docs/ACCEPTANCE_STATUS.md`.
- The latest backend closure outputs are non-placeholder projected decision-preservation summaries.
- The current accepted figure set is the latest generated content under `results/figures/` and `paper/figures/`.

## Figure and Table Mapping

| Paper element | Script | Source data | Generated artifact | Current status |
| --- | --- | --- | --- | --- |
| Fig. 3 Validation chain | `python3 pyscripts/analysis/gen_validation.py` | `validation/compute_grounding.csv`, `validation/interface_envelope.csv`, `validation/package_yield_anchor.csv` | `results/figures/fig3_validation.pdf`, `results/figures/fig3_validation.png`, `paper/figures/fig3_validation.pdf` | rendered |
| Fig. 4 Stronger baselines | `./scripts/run_figure4.sh` | latest `results/plot_ready/*/winner_change_matrix.csv`, `reevaluated_loss.csv` | `results/figures/fig4_baselines.pdf`, `results/figures/fig4_baselines.png`, `paper/figures/fig4_baselines.pdf` | rendered |
| Fig. 5 Interface vs package + memory ablation | `./scripts/run_figure5.sh` | latest `results/plot_ready/*/interface_vs_package.csv`, `memory_off_ablation.csv` | `results/figures/fig5_interface_memory.pdf`, `results/figures/fig5_interface_memory.png`, `paper/figures/fig5_interface_memory.pdf` | rendered |
| Fig. 6 Phase map | `./scripts/run_figure6.sh` | latest `results/plot_ready/*/phase_boundary.csv`, `split_margin.csv` | `results/figures/fig6_phase_map.pdf`, `results/figures/fig6_phase_map.png`, `paper/figures/fig6_phase_map.pdf` | rendered |
| Fig. 7 Pareto + energy | `./scripts/run_figure7.sh` | latest `results/plot_ready/*/pareto_points.csv`, `energy_breakdown.csv` | `results/figures/fig7_pareto_energy.pdf`, `results/figures/fig7_pareto_energy.png`, `paper/figures/fig7_pareto_energy.pdf` | rendered |
| Fig. 8 Sensitivity + closure | `./scripts/run_figure8.sh` | latest `results/plot_ready/*/boundary_drift.csv`, `sensitivity_tags.csv`, latest `results/backend_aggregated/*` closure files | `results/figures/fig8_closure.pdf`, `results/figures/fig8_closure.png`, `paper/figures/fig8_closure.pdf` | rendered |
| Illegal breakdown table | `pyscripts/pipeline/aggregate_plot_ready.py` | latest `results/plot_ready/*/illegal_breakdown.csv` | CSV only | rendered |
| Weight shift summary | `pyscripts/pipeline/aggregate_plot_ready.py` | latest `results/plot_ready/*/weight_shift_summary.csv` | CSV only | rendered |
| Closure summary | `python3 pyscripts/backend/aggregate_backend_closure.py ...` via `./scripts/run_backend_*.sh` | latest `results/backend_aggregated/*/closure_summary.csv`, `closure_summary.json` | CSV + JSON | rendered |
| Router sensitivity | `python3 pyscripts/backend/aggregate_backend_closure.py ...` via `./scripts/run_backend_*.sh` | latest `results/backend_aggregated/*/router_sensitivity.csv` | CSV only | rendered |
| Package cost ordering check | `python3 pyscripts/backend/aggregate_backend_closure.py ...` via `./scripts/run_backend_*.sh` | latest `results/backend_aggregated/*/package_cost_ordering_check.csv` | CSV only | rendered |
| Deployment regime summary | `python3 pyscripts/backend/aggregate_backend_closure.py ...` via `./scripts/run_backend_*.sh` | latest `results/backend_aggregated/*/deployment_regime_summary.csv` | CSV only | rendered |

## Reverse Lookup

If a paper-facing asset changes, trace it back using this order:

1. `paper/figures/*.pdf`
2. `results/figures/*.pdf` or `*.png`
3. latest `results/plot_ready/<run>/` or `results/backend_aggregated/<run>/`
4. `results/aggregated/<run>/design_records.json` and `result.csv`
5. `results/raw/<run>/<design_id>/point_snapshot.json` and `search_trace.jsonl`

## Manifest and Parameterization References

- Figure metadata is exported to `results/figures/paper_figure_manifest.json`.
- README and this mapping both treat `results/aggregated/model_parameterization.json` as the current parameter dictionary reference.

## Scope Notes

- Backend closure outputs should continue to be described as `projected decision preservation`, not backend sign-off correctness.
- If a future `docs/ACCEPTANCE_STATUS.md` report shows legality regressions or new placeholder rows, figure and table claims become provisional again until the bundle is refreshed.
