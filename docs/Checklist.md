# PICASSO ACCEPTANCE CHECKLIST

Current audited state is recorded separately in:

- `docs/ACCEPTANCE_STATUS.md`
- `results/acceptance/current_acceptance_audit.json`

Use the acceptance audit as the authoritative current-state board for the latest accepted bootstrap artifact. Keep this checklist as the full paper-artifact gate and reviewer-facing reference, especially for items that are broader than the current machine audit.

## Repo structure and entrypoints

- [ ] `configs/`, `workloads/`, `scripts/`, `results/raw/`, `results/aggregated/`, `results/plot_ready/`, `results/figures/`, `results/backend/floorplan/`, `results/backend/package/`, `results/backend/nop/`, `results/backend/memory/`, `results/backend_aggregated/`, `results/backend_figures/`, `docs/`, and `paper/figures/` exist.
- [ ] `scripts/run_smoke.sh`, `scripts/run_paper_core.sh`, and `scripts/run_paper_full.sh` exist and are documented.
- [ ] `scripts/run_figure4.sh`, `scripts/run_figure5.sh`, `scripts/run_figure6.sh`, `scripts/run_figure7.sh`, and `scripts/run_figure8.sh` exist.
- [ ] `scripts/run_backend_smoke.sh`, `scripts/run_backend_core.sh`, and `scripts/run_backend_full.sh` exist.
- [ ] Legacy root-level DSE scripts are either wrapped or clearly documented as compatibility entrypoints only.

## State/config/schema

- [ ] The repo defines the explicit search state `d=(m,a,k,i,p,b)`.
- [ ] Interface, package, and memory are first-class state dimensions rather than late-stage parameters.
- [ ] The unified config schema covers workload, node target, process node, chiplet count, interface class, package class, memory class, seed, proposal budget, and time cap.
- [ ] Every design point receives a unique `design_id`.
- [ ] Every run saves a config snapshot with sweep config, seed, git commit, timestamp, and command line.

## Legality and evaluator

- [ ] Latency, energy, and cost are decomposed in the evaluator.
- [ ] NoP terms explicitly depend on interface and package.
- [ ] The evaluator models PHY area, endpoint latency, bandwidth density, energy per bit, route budget, edge demand, idle-PHY energy, and yield-aware cost.
- [ ] Edge legality is enforced inside the search loop.
- [ ] Route legality is enforced inside the search loop.
- [ ] Memory legality is enforced inside the search loop.
- [ ] Memory legality includes attachment style, channel count, I/O-die organization constraints, and D2D edge competition.
- [ ] Illegal reasons are emitted in structured logs.
- [ ] `results/aggregated/model_parameterization.json` is generated.
- [ ] `model_parameterization.json` explains `Be(i,p)`, `Gedge(p,k)`, `Rbudget(p)`, `I(d)`, and `P(d)`.

## Workloads and traces

- [ ] CNN inference workload exists.
- [ ] Long-context prefill workload exists.
- [ ] KV-heavy decode workload exists.
- [ ] Dense decoder block workload exists.
- [ ] Mixtral-style MoE trace exists.
- [ ] Megatron-style collective trace exists.
- [ ] MoE trace includes 8 experts, top-2 dispatch, `1.35x` imbalance, and `0.34` locality probability.
- [ ] Collective trace uses bucketized all-reduce or all-gather with default `128MB` buckets.
- [ ] Validation data generation is implemented with `pyscripts/analysis/gen_validation.py`.

## Search and baselines

- [ ] Joint search uses multiple legal seeds, move families, annealed acceptance, and a Pareto archive.
- [ ] Joint uses 8 seeds and a shared budget of `60k proposals/seed` or `15 min/seed`.
- [ ] The move family includes map, arch, split, interface-package, memory, and coupled moves.
- [ ] Stage-wise baseline exists.
- [ ] Package-oblivious baseline exists.
- [ ] Architecture-first baseline exists.
- [ ] Partition-first baseline exists.
- [ ] Cost/interface-first baseline exists.
- [ ] Outer-loop repair baseline exists and is not intentionally weakened.
- [ ] Memory-off baseline exists.
- [ ] Interface-fixed and package-fixed controls exist.
- [ ] All projected baselines share the same seeds, evaluator, and budgets as Joint.
- [ ] Raw logs include round, seed, move family, accepted, legal, illegal reason, best score, temperature, and elapsed time.

## Result pipeline

- [ ] Each experiment point produces raw JSON logs.
- [ ] Raw outputs are stored under `results/raw/`.
- [ ] Aggregated outputs are stored under `results/aggregated/`.
- [ ] Plot-ready outputs are stored under `results/plot_ready/`.
- [ ] Final figures are stored under `results/figures/`.
- [ ] Any figure can be traced back to raw logs and design IDs.
- [ ] Figure rebuild works without rerunning search when raw or aggregated data already exist.
- [ ] Aggregation scripts fail loudly on missing columns, empty files, and invalid values.
- [ ] Plotting scripts fail loudly on missing inputs.
- [ ] Failed workloads or baselines are recorded in summary outputs rather than silently skipped.

## Figure 3 to Figure 8 outputs

- [ ] Fig. 3 data exist via `validation/*.csv`.
- [ ] Fig. 3 figure files exist as `fig3_validation.pdf` and `fig3_validation.png`.
- [ ] `winner_change_matrix.csv` exists.
- [ ] `reevaluated_loss.csv` exists.
- [ ] Fig. 4 figure files exist as `fig4_baselines.pdf` and `fig4_baselines.png`.
- [ ] `interface_vs_package.csv` exists.
- [ ] `memory_off_ablation.csv` exists.
- [ ] Fig. 5 figure files exist as `fig5_interface_memory.pdf` and `fig5_interface_memory.png`.
- [ ] `phase_boundary.csv` exists.
- [ ] `split_margin.csv` exists.
- [ ] Fig. 6 figure files exist as `fig6_phase_map.pdf` and `fig6_phase_map.png`.
- [ ] `pareto_points.csv` exists.
- [ ] `energy_breakdown.csv` exists.
- [ ] Fig. 7 figure files exist as `fig7_pareto_energy.pdf` and `fig7_pareto_energy.png`.
- [ ] `boundary_drift.csv` exists.
- [ ] `sensitivity_tags.csv` exists.
- [ ] Fig. 8 figure files exist as `fig8_closure.pdf` and `fig8_closure.png`.
- [ ] `illegal_breakdown.csv` exists.
- [ ] `weight_shift_summary.csv` exists.

## Backend closure outputs

- [ ] `pyscripts/analysis/export_design_records.py` exists.
- [ ] `pyscripts/backend/sample_backend_points.py` exists.
- [ ] `pyscripts/backend/translate_to_openroad.py` exists.
- [ ] `pyscripts/backend/translate_to_package_router.py` exists.
- [ ] `pyscripts/backend/translate_to_booksim.py` exists.
- [ ] `pyscripts/backend/translate_to_ramulator.py` exists.
- [ ] Every backend input is derived from the same canonical design record.
- [ ] `winner_agreement.csv` exists.
- [ ] `legality_confusion.csv` exists.
- [ ] `boundary_drift_backend.csv` exists.
- [ ] `claim_closure.csv` exists.
- [ ] `closure_summary.csv` exists.
- [ ] `closure_summary.json` exists.
- [ ] `router_sensitivity.csv` exists and includes nominal, `-15%`, and `+15%` capacity cases.
- [ ] `package_cost_ordering_check.csv` exists.
- [ ] `deployment_regime_summary.csv` exists.
- [ ] `paper-core` backend closure uses the five required cohorts with total size `220`.
- [ ] Hardest slices are rerun at least once.

## Documentation and paper sync

- [ ] `docs/README.md` exists and documents smoke, paper-core, and paper-full.
- [ ] `docs/REPRODUCE.md` exists and documents figure rebuild and backend closure rebuild.
- [ ] `docs/PAPER_MAPPING.md` exists.
- [ ] `docs/PAPER_MAPPING.md` maps every paper figure and table to scripts and data files in both directions.
- [ ] `docs/README.md` and `docs/PAPER_MAPPING.md` cite `results/aggregated/model_parameterization.json`.
- [ ] Generated figures are copied or linked into `paper/figures/`.
- [ ] The paper build uses the latest generated figures.
- [ ] `paper_figure_manifest.json` exists and lists figure number, caption, source data, generated path, LaTeX include path, and generation command.

## Smoke / paper-core / paper-full runs

- [ ] `scripts/run_smoke.sh` completes and validates the end-to-end pipeline.
- [ ] `scripts/run_paper_core.sh` completes with the core matrix and closure cohorts.
- [ ] `scripts/run_paper_full.sh` completes with the full matrix.
- [ ] Runtime expectations and output locations are documented for all three tiers.
- [ ] Failure cases are summarized rather than silently skipped.

## Final reviewer-facing hardening

- [ ] Backend closure is described as decision preservation, not sign-off correctness.
- [ ] Figure 8(c), closure tables, README, AD or AE appendix, and aggregated CSV or JSON outputs use the same claims.
- [ ] `package_cost_ordering_check.csv` supports the `OS -> RDL -> SI` ordering stability claim over the main sweep.
- [ ] `deployment_regime_summary.csv` maps regimes to system-facing meanings and optimization levers.
- [ ] `closure_summary.csv/json` report `top1_agreement`, `hard_slice_agreement`, `legal_precision`, `legal_recall`, `mono_few_boundary_drift`, `few_many_boundary_drift`, and cohort sizes.
- [ ] The final artifact does not rely on hand-entered paper numbers, hand-edited plots, or hand-edited aggregate data.
