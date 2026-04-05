# Backend Inputs

This public repository keeps backend aggregate summaries under `results/backend_aggregated/`.

Per-design tool input bundles under `results/backend/floorplan/`, `results/backend/package/`,
`results/backend/nop/`, and `results/backend/memory/` are intentionally omitted from the
public source release to keep the repository readable and to prevent generated shell/Tcl
artifacts from dominating repository language statistics.

Regenerate these directories locally with:

- `./scripts/run_backend_smoke.sh`
- `./scripts/run_backend_core.sh`
- `./scripts/run_backend_full.sh`
