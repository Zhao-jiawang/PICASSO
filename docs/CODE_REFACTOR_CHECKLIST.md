# PICASSO Code Refactor Checklist

This checklist tracks the code-refactor gate itself. Once these items are complete, remaining PICASSO artifact work continues on the refactored Python-native runtime and does not reopen the refactor gate.

## Refactor Exit Gate

- [x] Normal execution no longer depends on `src/`, `include/`, `makefile`, old root-level shell sweeps, or removed compatibility directories.
- [x] Previous compatibility artifacts are removed from the final repository surface.
- [x] `legality` remains an explicit PICASSO core capability and is implemented in the Python-native runtime.
- [x] The final PICASSO repository does not retain original C++ source files from the pre-refactor implementation.
- [x] Final Python modules are PICASSO-owned implementations rather than line-by-line ports of the previous source layout.
- [x] The refactor preserves clean directory management and readable module boundaries.
- [x] `scripts/run_smoke.sh`, `scripts/run_paper_core.sh`, `scripts/run_paper_full.sh`, figure rebuild scripts, backend scripts, and workload-generation scripts run through Python-only execution paths.
- [x] Long point-sweep experiments can be executed through Python-native parallel shard entrypoints instead of only serial single-process runners.

## Runtime Structure

- [x] Runtime logic lives under `picasso/`.
- [x] Shell orchestration lives under `scripts/`.
- [x] Thin CLI entrypoints live under categorized `pyscripts/` subdirectories.
- [x] Parallel point orchestration lives under `scripts/run_points_parallel.sh` with workload-specific wrappers such as `scripts/run_paper_full_parallel.sh`.
- [x] `picasso/core/engine.py` is split into focused modules.
- [x] Search policy and move-family logic live in `picasso/core/search.py`.
- [x] Evaluator math lives in `picasso/core/evaluator.py`.
- [x] Legality checks live in `picasso/core/legality.py`.
- [x] Result serialization lives in `picasso/core/result_serialization.py`.
- [x] Registry loading remains isolated from evaluator logic.
- [x] `picasso/core/__init__.py` exposes a stable public API.
- [x] File and module names communicate primary responsibility directly from the path.
- [x] Workload graph reconstruction lives in `picasso/core/workload_graph.py`.
- [x] Explicit workload-library ownership lives in `picasso/workloads/model_library.py`.
- [x] Partition planning lives in `picasso/core/partition_engine.py`.
- [x] Placement planning lives in `picasso/core/placement_engine.py`.
- [x] Core-cluster ownership lives in `picasso/core/cluster_model.py`.
- [x] Tensor-range ownership and layout reconstruction live in `picasso/core/data_layout.py`.
- [x] Per-core buffer accounting lives in `picasso/core/buffer_model.py`.
- [x] Explicit core-library ownership lives in `picasso/core/core_model.py`.
- [x] Microarchitecture-aware core mapping lives in `picasso/core/core_mapping_engine.py`.

## State, Schema, and Workloads

- [x] The canonical Python state is the PICASSO tuple `d=(m,a,k,i,p,b)` and is emitted in run bundles.
- [x] Schema validation lives in a dedicated Python layer: `picasso/pipeline/schema.py`.
- [x] Deterministic `design_id` generation lives in a reusable helper: `picasso/pipeline/design_ids.py`.
- [x] Workload resolution lives in a package-owned layer: `picasso/workloads/catalog.py`.
- [x] Config snapshots emit command provenance, git commit, timestamp, and normalized config metadata from shared helpers.
- [x] Interface, package, and memory remain first-class evaluation inputs throughout the Python core.
- [x] Edge, route, and memory legality are implemented as structured Python checks.
- [x] Illegal reasons are emitted in machine-readable form and flow into the result pipeline.
- [x] All six PICASSO workload motifs are runnable through the Python-native config layer.
- [x] `configs/paper_full.json` now covers `cnn_inference`, `long_context_prefill`, `kv_heavy_decode`, `dense_decoder_block`, `mixtral_moe_trace`, and `megatron_collective_trace`.

## Verification

- [x] `python3 -m py_compile` passes for the active package and script entrypoints.
- [x] `./scripts/generate_workload_traces.sh` passes.
- [x] `./scripts/run_smoke.sh` passes.
- [x] `./scripts/run_paper_core.sh` passes.
- [x] `./scripts/run_paper_full.sh` passes.
- [x] `./scripts/run_paper_full_parallel.sh --run-name 20260405_093025_paper_full_bootstrap --jobs 16` passes and completes a full reuse/postprocess cycle.
- [x] `./scripts/run_backend_smoke.sh`, `./scripts/run_backend_core.sh`, and `./scripts/run_backend_full.sh` pass.
- [x] `./scripts/run_figure4.sh`, `./scripts/run_figure5.sh`, `./scripts/run_figure6.sh`, `./scripts/run_figure7.sh`, and `./scripts/run_figure8.sh` pass.
- [x] `python3 pyscripts/analysis/gen_validation.py` passes.
- [x] No default script in `scripts/` calls the old C++ binary or depends on `makefile`.
- [x] Historical `src/` and `include/` runtime responsibilities were re-audited against `docs/SRC_SEMANTIC_RECOVERY_LEDGER.md` and no ownership gaps remain open.

## Post-Refactor Continuation

- Continue remaining PICASSO artifact calibration, paper hardening, and backend-quality work on top of this Python-native runtime.
- Do not reintroduce `src/`, `include/`, root-level sweep scripts, or compatibility-only directories.
- Treat the code refactor as complete; subsequent work is artifact expansion, not migration.
