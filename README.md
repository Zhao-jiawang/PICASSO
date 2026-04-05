# PICASSO

This repository provides the current Python-native PICASSO runtime, experiment pipeline, and paper-facing artifact outputs.

Primary entry documents:

- [docs/README.md](/home/zhaojw/Chip/PICASSO/docs/README.md)
- [docs/REPRODUCE.md](/home/zhaojw/Chip/PICASSO/docs/REPRODUCE.md)
- [docs/PAPER_MAPPING.md](/home/zhaojw/Chip/PICASSO/docs/PAPER_MAPPING.md)
- [docs/PROJECT_STATEMENT_CODEX.md](/home/zhaojw/Chip/PICASSO/docs/PROJECT_STATEMENT_CODEX.md)
- [docs/OPEN_SOURCE_STRUCTURE.md](/home/zhaojw/Chip/PICASSO/docs/OPEN_SOURCE_STRUCTURE.md)
- [docs/REFACTOR_DECISIONS.md](/home/zhaojw/Chip/PICASSO/docs/REFACTOR_DECISIONS.md)
- [docs/CODE_REFACTOR_CHECKLIST.md](/home/zhaojw/Chip/PICASSO/docs/CODE_REFACTOR_CHECKLIST.md)
- [LICENSE](/home/zhaojw/Chip/PICASSO/LICENSE)
- [NOTICE](/home/zhaojw/Chip/PICASSO/NOTICE)
- [ACKNOWLEDGMENTS.md](/home/zhaojw/Chip/PICASSO/ACKNOWLEDGMENTS.md)

Current accepted artifact status:

- `docs/ACCEPTANCE_STATUS.md`
- `docs/CALIBRATION_STATUS_ZH.md`
- `results/acceptance/current_acceptance_audit.json`

Structured commands:

```bash
./scripts/generate_workload_traces.sh
./scripts/run_smoke.sh
./scripts/run_paper_core.sh
./scripts/run_paper_full.sh
python3 pyscripts/analysis/gen_validation.py
./scripts/run_backend_smoke.sh
./scripts/run_backend_core.sh
./scripts/run_backend_full.sh
./scripts/run_figure4.sh
./scripts/run_figure5.sh
./scripts/run_figure6.sh
./scripts/run_figure7.sh
./scripts/run_figure8.sh
```

Current runtime scope:

- unified JSON configs under `configs/`
- Python-native runtime under `picasso/`
- categorized Python entrypoints under `pyscripts/`
- unified shell entrypoints under `scripts/`
- run bundles under `results/raw/`, `results/aggregated/`, and `results/plot_ready/`
- canonical design records under each aggregated run bundle
- figure outputs under `results/figures/` and `paper/figures/`
- backend projections and closure summaries under `results/backend/` and `results/backend_aggregated/`
- six runnable workload motifs in `workloads/`

The code-refactor gate is complete. The active execution path no longer depends on the pre-refactor C++ tree or root-level sweep scripts. The current default mainline is paper-sync, artifact interpretation, and open-source surface cleanup on top of this Python-native runtime.

## License and Acknowledgment

- This repository is released under Apache-2.0. See `LICENSE`.
- Project-level attribution and release notes are recorded in `NOTICE`.
- Research-context acknowledgments are recorded in `ACKNOWLEDGMENTS.md`.

## Public Release Scope

- This public source release keeps the latest accepted official bundles and paper-facing figures.
- Historical run bundles and generated backend tool-input directories are intentionally omitted from the public repository surface.
- Regenerate backend tool-input bundles locally with the scripts under `scripts/` when needed.
