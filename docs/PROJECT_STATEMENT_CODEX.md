# PROJECT STATEMENT FOR CODEX

This document is the normalized Markdown version of the archival source at `Project_Statement/Codex_Prompt_SC26_PICASSO_ComboA_Final_Rev3_TemplateStyle.docx`.

Use this file as the machine-friendly task specification for Codex and other engineering agents. Keep the original `docx` as the archival source of record.

## Project Goal

- Transform the reference codebase into a full experimental artifact that supports the SC2026 paper:
  - `PICASSO: In-the-Loop Co-Exploration of Packages, D2D Interfaces, and Chiplets for AI Accelerator Nodes`
- Deliver a repo that is runnable, reproducible, figure-generating, and suitable for README, AD/AE, and paper integration.
- The target is not tapeout sign-off and not global optimality. The target is architecture-level feasibility-aware joint exploration, ranking, and sampled surrogate-to-backend closure.

## Mandatory Deliverables

- Updated runnable code.
- Automated experiment scripts.
- Raw logs.
- Aggregated CSV and JSON outputs.
- Plot-ready CSV and JSON outputs.
- Final PDF and PNG figures.
- Reproduction documentation.
- Figure and table to script and data mapping.
- A traceable output chain that supports:
  - build
  - smoke test
  - paper-core run
  - paper-full run
  - aggregation
  - plotting
  - final checks

## Non-goals

- Do not build RTL, detailed layout, real SI/PI analysis, or full package-routing sign-off flows.
- Do not depend on proprietary traces, proprietary tools, or licenses that prevent public reproduction.
- Do not only redraw old figures. Every figure must come from a real, rerunnable data pipeline.
- Do not collapse all logic into one giant script. The repo must be modular and documented.

## Required State / Model / Search Changes

### Required State and Configuration

- Extend the search state to `d=(m, a, k, i, p, b)`.
- Meanings:
  - `m`: mapping
  - `a`: on-die microarchitecture
  - `k`: chiplet organization
  - `i`: D2D interface
  - `p`: package class and topology
  - `b`: memory and I/O provisioning
- Define a unified configuration schema that covers at least:
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
- Promote interface, package, and memory from auxiliary parameters into first-class search state.
- Every design point must have a unique `design_id`.
- Legacy entry scripts may remain as compatibility wrappers, but the new repo must expose unified entrypoints, including:
  - `scripts/run_smoke.sh`
  - `scripts/run_paper_core.sh`
  - `scripts/run_paper_full.sh`
  - `scripts/run_figure4.sh`
  - `scripts/run_figure5.sh`
  - `scripts/run_figure6.sh`
  - `scripts/run_figure7.sh`
  - `scripts/run_figure8.sh`

### Required Model and Legality Changes

- Implement decomposed latency, energy, and cost models.
- The NoP term must explicitly depend on both interface and package.
- Model at least the following quantities:
  - PHY area
  - endpoint latency
  - bandwidth density
  - energy per bit
  - route budget
  - edge demand
  - idle-PHY energy
  - yield-aware cost
- Enforce architecture-level feasibility in the inner loop. At minimum:
  - `edge demand <= available edge`
  - `route demand <= package budget`
  - `memory attachment legality`
- Memory legality must not be reduced to a bandwidth cap. It must model:
  - channel count
  - HBM/GDDR/LPDDR attachment style
  - whether I/O-die organization permits the attachment
  - competition between memory attachment and D2D edge usage
- Keep centralized parameterized envelopes for:
  - `XSR-like`, `USR-like`, `UCIe-like`
  - `OS`, `RDL fan-out`, `Si interposer`
  - `LPDDR5-like`, `GDDR6X-like`, `HBM-like`
- Do not scatter hardcoded model constants across the codebase.

### Required Search and Baselines

- Implement a simple, auditable, reproducible joint search:
  - multiple legal seeds
  - move family
  - annealed acceptance
  - Pareto archive
- Default comparison budget:
  - 8 legal seeds
  - 60k proposals per seed
  - 15 minutes per seed cap
- The move family must include at least:
  - map
  - arch
  - split
  - interface-package
  - memory
  - coupled moves
- Required baseline modes:
  - Joint
  - Stage-wise
  - Package-oblivious
  - Architecture-first
  - Partition-first
  - Cost/interface-first
  - Outer-loop repair
  - Memory-off
- Required switches:
  - interface-fixed
  - package-fixed
- All projected baselines must share:
  - the same seeds
  - the same evaluator
  - the same budgets
- Only the variable ordering and repair order may differ across baselines.
- `Outer-loop repair` must be a strong baseline. It must not be intentionally weakened.
- Per-round logging must include at least:
  - round
  - seed
  - move family
  - accepted
  - legal
  - illegal reason
  - best score
  - temperature
  - elapsed time

## Required Workloads and Traces

The artifact must include six workload motifs.

- CNN inference
  - low `phi`
  - regular memory access
  - corner case where package-oblivious can appear less wrong
- Long-context prefill
  - high sustained activation movement
  - used to raise `phi` and effective monolithic area pressure
- KV-heavy decode
  - lower utilization
  - stronger endpoint and idle-PHY costs
- Dense decoder block
  - representative modern dense LLM block
  - intermediate between prefill and decode
- Mixtral-style MoE trace
  - at least 8 experts
  - top-2 dispatch
  - `1.35x` load imbalance
  - `0.34` locality probability
  - bursty and topology-sensitive behavior
- Megatron-style collective trace
  - bucketized all-reduce and all-gather phases
  - default `128MB` bucket
  - route budget and memory attachment pressure

## Figure and Table Binding

Every paper-facing figure or table must be generated by scripts and data files. No paper number may be hand-entered.

| Paper element | Required script or data | Minimum acceptance condition |
| --- | --- | --- |
| Fig. 3 Validation chain | `pyscripts/analysis/gen_validation.py` + `validation/*.csv` | Produces compute grounding, interface envelope, and package/yield anchor panels with the expected trend direction |
| Fig. 4 Stronger baselines | `scripts/run_figure4.sh` + `winner_change_matrix.csv` + `reevaluated_loss.csv` | MoE and collective show higher winner-change than CNN; package-oblivious is the weakest baseline |
| Fig. 5 Interface vs package + memory ablation | `scripts/run_figure5.sh` + `interface_vs_package.csv` + `memory_off_ablation.csv` | Interface upgrade beats package-only upgrade as `phi` grows; `memory-off` flips winners more often under high pressure |
| Fig. 6 Phase map | `scripts/run_figure6.sh` + `phase_boundary.csv` + `split_margin.csv` | Broad 2 to 4 chiplet middle regime appears; many-chiplet region is more fragile |
| Fig. 7 Pareto + energy | `scripts/run_figure7.sh` + `pareto_points.csv` + `energy_breakdown.csv` | `OS`, `RDL`, and `SI` form distinct cost bands; NoP and idle-PHY dominate the differences |
| Fig. 8 Sensitivity + tags | `scripts/run_figure8.sh` + `boundary_drift.csv` + `sensitivity_tags.csv` | Outputs `robust`, `conditional`, and `boundary-sensitive` tags with boundary drift |
| Table: illegal breakdown | `pyscripts/analysis/aggregate_illegal_breakdown.py` + `illegal_breakdown.csv` | Splits illegal causes into edge, route, and memory; decode skews memory-heavy, MoE and collective skew route plus memory |
| Table: weight stress test | `pyscripts/analysis/aggregate_weight_sweep.py` + `weight_shift_summary.csv` | Shows how latency, energy, and cost weights move regime boundaries |

Final paper figures must be generated to both:

- `results/figures/`
- `paper/figures/` or the equivalent paper figure directory

Required paper-facing figure filenames:

- `fig3_validation.pdf`
- `fig3_validation.png`
- `fig4_baselines.pdf`
- `fig4_baselines.png`
- `fig5_interface_memory.pdf`
- `fig5_interface_memory.png`
- `fig6_phase_map.pdf`
- `fig6_phase_map.png`
- `fig7_pareto_energy.pdf`
- `fig7_pareto_energy.png`
- `fig8_closure.pdf`
- `fig8_closure.png`

The repo must also produce `paper_figure_manifest.json` with:

- `figure_number`
- `paper_caption_short`
- `source_csv/json`
- `generated_figure_path`
- `latex_include_path`
- `generation_command`

## Experiment Matrix

The artifact must explicitly separate `smoke`, `paper-core`, and `paper-full`.

| Dimension | Required coverage |
| --- | --- |
| Node target | `72`, `128`, `256`, `512`, `1024` TOPS |
| Process | `12nm`, `7nm` |
| Interface | `XSR-like`, `USR-like`, `UCIe-like` |
| Package | `OS`, `RDL fan-out`, `Si interposer` |
| Memory | `LPDDR5-like`, `GDDR6X-like`, `HBM-like` |
| Workload | `CNN`, `Prefill`, `Decode`, `Dense block`, `MoE`, `Collective` |
| Seeds | `8` |
| Budget | `60k proposals/seed` or `15 min/seed` |

All baselines must use the same seed and budget configuration for fairness.

## Required Repository Layout

The target repo layout is:

```text
repo_root/
  include/
  src/
  pyscripts/
  configs/
  workloads/
  scripts/
    run_smoke.sh
    run_paper_core.sh
    run_paper_full.sh
    run_figure4.sh
    run_figure5.sh
    run_figure6.sh
    run_figure7.sh
    run_figure8.sh
    run_backend_smoke.sh
    run_backend_core.sh
    run_backend_full.sh
  results/
    raw/
    aggregated/
    plot_ready/
    figures/
    backend/
      floorplan/
      package/
      nop/
      memory/
    backend_aggregated/
    backend_figures/
  docs/
    README.md
    REPRODUCE.md
    PAPER_MAPPING.md
  paper/
    figures/
  requirements.txt
  makefile
  summary.sh
```

The repo may retain compatible wrappers for older entrypoints during transition, but the target user experience must be one-command build, rerun, and figure generation.

## Required Reproducibility Outputs

- Every figure must have a clear generation command.
- Every figure must have at least one aggregated or plot-ready data file.
- Every figure command must appear in the reproduction documentation.
- Every experiment output must carry a config snapshot with at least:
  - sweep configuration
  - seed
  - git commit
  - timestamp
  - command line
- It must be possible to trace any figure file back to raw logs.
- The artifact must support figure rebuild without rerunning search if raw and aggregated data already exist.
- Core aggregation scripts must fail early on:
  - missing columns
  - empty files
  - invalid values
- Plotting scripts must fail loudly when inputs are missing. Do not silently generate empty plots.
- If a workload or baseline fails, the failure must appear in the summary. It must not be silently skipped.

Required intermediate and aggregate outputs include at least:

- `winner_change_matrix.csv`
- `reevaluated_loss.csv`
- `interface_vs_package.csv`
- `memory_off_ablation.csv`
- `illegal_breakdown.csv`
- `phase_boundary.csv`
- `split_margin.csv`
- `pareto_points.csv`
- `energy_breakdown.csv`
- `boundary_drift.csv`
- `sensitivity_tags.csv`
- `weight_shift_summary.csv`
- `model_parameterization.json`

## Combo-A Backend Closure

### Goal and Allowed Scope

- Use exactly Combo-A:
  - OpenROAD
  - custom semi-physical package router
  - BookSim 2.0
  - Ramulator 2.0
- Do not replace Combo-A with proprietary EDA or non-public alternatives.
- The purpose is not industrial sign-off.
- The purpose is sampled backend replay for:
  - winner preservation
  - legality classification
  - regime and boundary stability
- Continue to use the project's industrial package cost anchor for package cost.
- The new package backend is only responsible for route, hop, congestion, escape, and legality behavior.

### Required Backend Responsibilities

| Backend slice | Tool | What it checks | Required outputs |
| --- | --- | --- | --- |
| Floorplan and perimeter | OpenROAD | whether PHY and memory macros fit, edge pressure, placement congestion | `edge_overflow_ratio`, `macro_packing_pressure`, `placement_congestion_score`, `global_routing_overflow`, `status` |
| Package and routing | semi-physical package router | route budget, hop richness, topology-induced congestion, escape pressure | `route_overflow_ratio`, `avg_hops`, `p95_hops`, `congestion_hotspot_count`, `escape_pressure`, `package_status` |
| NoP timing and energy | BookSim 2.0 | endpoint latency, serialization, contention, topology effects | `average_latency`, `p95_latency`, `throughput_saturation`, `link_utilization`, `nop_replay_summary` |
| Memory backend | Ramulator 2.0 | attachment legality and timing pressure for HBM/direct-attached/I/O-die memory | `avg_latency`, `tail_latency`, `channel_imbalance`, `queue_depth_proxy`, `memory_stall_proxy`, `memory_status` |

### Canonical Design Record

The backend closure flow must use a single canonical design record generated by `pyscripts/analysis/export_design_records.py`.

Every record must include at least:

- `design_id`
- `baseline_mode`
- `workload`
- `trace_id`
- `tops_target`
- `process_node`
- `seed`
- full state tuple `d=(m,a,k,i,p,b)`
- traffic matrix
- per-edge bandwidth
- die area breakdown
- PHY count
- package class
- memory attachment
- surrogate latency
- surrogate energy
- surrogate cost
- legality flags
- `M1`
- `M2`
- `Si`
- `Sp`

From the same canonical design record, automatically derive:

- `floorplan_input.json`
- `package_input.json`
- `booksim_config.json`
- `ramulator_config.yaml`

No backend may consume a hand-edited input file.

### Sampling Rules

Implement `pyscripts/backend/sample_backend_points.py` and sample the following cohorts:

- Winner set
  - top-1 and top-3 points for each mode
- Boundary set
  - points where `|M1|` or `|M2|` is near zero
- Near-legality set
  - points where edge, route, or memory legality are near threshold
- Disagreement set
  - winner flips
  - memory-off flips
  - 6 to 8 chiplet cases
  - hardest MoE and collective cases
- Control set
  - random legal points

Recommended `paper-core` cohort sizes:

- Winner: `80`
- Boundary: `40`
- Near-legality: `40`
- Disagreement: `40`
- Control: `20`

If runtime is limited, allow a reduced smoke version, but keep the same code paths and schemas.

### Required Backend Scripts, Directories, and Outputs

Required backend scripts:

- `pyscripts/backend/translate_to_openroad.py`
- `pyscripts/backend/translate_to_package_router.py`
- `pyscripts/backend/translate_to_booksim.py`
- `pyscripts/backend/translate_to_ramulator.py`
- `scripts/run_backend_smoke.sh`
- `scripts/run_backend_core.sh`
- `scripts/run_backend_full.sh`
- `pyscripts/backend/aggregate_backend_closure.py`
- `pyscripts/plot_backend_closure.py`

Required backend directories:

- `results/backend/floorplan`
- `results/backend/package`
- `results/backend/nop`
- `results/backend/memory`
- `results/backend_aggregated`
- `results/backend_figures`

Required backend aggregate outputs:

- `winner_agreement.csv`
- `legality_confusion.csv`
- `boundary_drift_backend.csv`
- `claim_closure.csv`

### Required Wording and Completion Gate

- Describe backend closure as `decision preservation`, not sign-off correctness.
- Use wording such as:
  - backend replay validates winner identity
  - backend replay validates legality classification
  - backend replay validates boundary stability for the ranking questions posed in the paper
- Do not claim that the backend confirms absolute correctness.
- If backend replay makes the many-chiplet frontier more fragile, mark the claim as `conditional` or `boundary-sensitive`. Do not hardcode the model to make it look robust.

Backend closure is only complete when all of the following hold:

- all four backends run from unified entrypoints
- every sampled point traces back to the canonical design record
- winner agreement, legality confusion, and boundary drift are automatically aggregated
- hardest slices are rerun at least once
- README, AD/AE, paper text, and Codex-facing documentation use consistent closure wording

## Reviewer-Driven Hardening

### Required Closure Summary Outputs

Generate the following files under `results/backend_aggregated/`:

- `closure_summary.csv`
- `closure_summary.json`
- `router_sensitivity.csv`
- `package_cost_ordering_check.csv`
- `deployment_regime_summary.csv`

`closure_summary.csv` and `closure_summary.json` must include at least:

- `top1_agreement`
- `hard_slice_agreement`
- `legal_precision`
- `legal_recall`
- `mono_few_boundary_drift`
- `few_many_boundary_drift`
- `cohort_size_total`
- `cohort_size_winner`
- `cohort_size_boundary`
- `cohort_size_near_legality`
- `cohort_size_disagreement`
- `cohort_size_control`

`router_sensitivity.csv` must report nominal, `-15%`, and `+15%` route-capacity cases with:

- winner agreement
- precision and recall
- boundary drift

`package_cost_ordering_check.csv` must validate ordering stability of package cost over:

- `OS` vs `RDL` vs `SI`
- monolithic-equivalent area buckets
- process buckets
- node target buckets

`deployment_regime_summary.csv` must include at least:

- `serving_latency_tier`
- `serving_throughput_tier`
- `training_cost_pod`
- `training_collective_heavy_pod`

For each regime, report:

- recommended chiplet regime
- preferred optimization levers
- threshold ranges that trigger regime shifts

### Required Model Explainability Output

Generate `results/aggregated/model_parameterization.json`.

It must explicitly document:

- `Be(i,p)`:
  - raw interface envelope
  - usable bandwidth factor
  - serialization and utilization loss
  - package and topology penalty
- `Gedge(p,k)`:
  - package-specific exposed perimeter
  - keep-out reservation
  - memory-edge reservation
  - organization-dependent edge availability
- `Rbudget(p)`:
  - route-capacity template
  - package-class richness scaling
  - topology penalty
- `I(d)` and `P(d)`:
  - which interface or package upgrades are feasible while holding the rest of the state fixed

README and `PAPER_MAPPING.md` must cite this file and explain the mapping between paper symbols and artifact outputs.

### Required README, PAPER_MAPPING, and AD Sync

The final docs must include:

- the sampled Combo-A closure cohort size for paper-core, including the five cohort categories
- generation commands for:
  - `closure_summary.csv/json`
  - `router_sensitivity.csv`
  - `package_cost_ordering_check.csv`
  - `deployment_regime_summary.csv`
- bidirectional mapping between figures or tables and the data files that support them

### Final Figure Landing Requirement

The latest generated paper figures must be the ones consumed by the paper build.

- If `main.tex` points to older filenames or paths, update it or overwrite the previous figure paths.
- The compiled paper must use the figures from the current automated pipeline, not historical figures.

## Red Lines

- Do not hand-edit CSV, PDF, or PNG files to match a target story.
- Do not update only plotting code while leaving the underlying model unchanged.
- Do not weaken projected baselines to make joint search look stronger.
- Do not simplify memory legality into a single unconstrained bandwidth scalar.
- Do not claim reproducibility without preserving raw logs and aggregation scripts.
- Do not let different backends consume inconsistent inputs.
- Do not report only average backend error while omitting decision-preservation metrics.
- Do not validate only joint winners and skip baseline winners.
- Do not ship paper figures that are not generated from the current automated run outputs.

## Completion Criteria

The work is complete only when all of the following are true:

- the repo supports explicit state `d=(m,a,k,i,p,b)` in configuration, logs, and snapshots
- Joint and the required projected baselines are all runnable
- edge, route, and memory legality all act inside the search loop with traceable illegal reasons
- the full chain `raw -> aggregated -> plot_ready -> figures` is automated
- every paper figure and table has a mapped script, input, output, and README command example
- smoke, paper-core, and paper-full entrypoints all exist and are documented
- Combo-A backend closure is wired end-to-end with canonical design records
- `closure_summary.csv/json`, `router_sensitivity.csv`, `package_cost_ordering_check.csv`, `deployment_regime_summary.csv`, `model_parameterization.json`, and `paper_figure_manifest.json` are generated and documented
- README, AD/AE, paper text, and generated CSV or JSON outputs use consistent wording and claims
