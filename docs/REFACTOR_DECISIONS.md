# PICASSO Refactor Decisions

This file records concrete refactor decisions for the Python-native PICASSO codebase.

## Principles

- Refactor toward a clean PICASSO runtime, not toward historical mirroring.
- Keep active runtime code under `picasso/` and keep script entrypoints thin.
- Remove compatibility-only naming when clearer PICASSO-facing names are available.
- Improve a historical design only when the issue is encountered during refactor and the old structure is clearly harmful.

## Implemented Decisions

- Search orchestration remains exposed through `pyscripts/pipeline/picasso_runner.py`, but reusable pipeline logic lives under `picasso/pipeline/`.
- Search loop mechanics live in `picasso/core/search.py`.
- Evaluator orchestration lives in `picasso/core/evaluator.py`.
- Area terms live in `picasso/core/area_model.py`.
- Mapping-derived state reconstruction lives in `picasso/core/mapping_model.py`.
- Workload graph reconstruction lives in `picasso/core/workload_graph.py`.
- Explicit workload-library ownership lives in `picasso/workloads/model_library.py`.
- Partition planning lives in `picasso/core/partition_engine.py`.
- Placement planning lives in `picasso/core/placement_engine.py`.
- Core-grid and chiplet-geometry ownership live in `picasso/core/cluster_model.py`.
- Tensor-range ownership and layout reconstruction live in `picasso/core/data_layout.py`.
- Per-core buffer accounting lives in `picasso/core/buffer_model.py`.
- Explicit core-library ownership lives in `picasso/core/core_model.py`.
- Microarchitecture-aware core mapping lives in `picasso/core/core_mapping_engine.py`.
- Traffic and hop/bandwidth modeling live in `picasso/core/traffic_model.py`.
- Latency decomposition lives in `picasso/core/latency_model.py`.
- Yield-aware package cost lives in `picasso/core/cost_model.py`.
- Legality checks live in `picasso/core/legality.py`.
- Result-token serialization lives in `picasso/core/result_serialization.py`.
- Shared scalar helpers live in `picasso/core/common_math.py`.
- Workload resolution and trace-derived metadata live in `picasso/workloads/catalog.py`.
- Deterministic `design_id` generation and config-shape validation live in dedicated pipeline helpers.
- The pre-refactor C++ tree, root-level sweep scripts, `legacy/`, and `pyscripts/legacy_utils/` are removed.

## Current Outcomes

- The repository executes entirely through the Python-native PICASSO runtime.
- Module names are responsibility-oriented rather than history-oriented.
- `paper_full` now covers all six PICASSO workload motifs on the active execution surface.
- The active runtime now has explicit Python-native owners for historical network, layer, partition, placement, datalayout, coremapping, cluster, core, schedule-tree, NoC, and cost responsibilities.
- The active evaluator path is now `area -> mapping -> traffic -> latency -> cost -> legality`, instead of a single surrogate-heavy formula block.
- The active runtime path now explicitly builds `workload graph -> partition -> placement -> data layout -> buffer usage -> traffic/latency/legality`.
- The active runtime now explicitly builds `workload library -> workload graph -> partition candidate search -> placement schedule -> data layout -> core mapping -> traffic/latency/legality`.
- Inter-chip traffic, peak NoC/NoP pressure, DRAM-channel pressure, decomposed latency, and yield-aware package cost are explicit runtime outputs.
- Long point sweeps now have Python-native parallel shard entrypoints instead of depending on a single serial runner.
- Backend sampling, translation, aggregation, validation, and figure rebuild flows run on top of the refactored runtime.
- The historical `src/` and `include/` tree has been re-audited against `docs/SRC_SEMANTIC_RECOVERY_LEDGER.md`, and no runtime ownership gaps remain open.

## Remaining Artifact Scope

- Tighten evaluator and legality calibration against the paper specification.
- Tighten figure semantics and reviewer-facing hardening outputs.
- Continue backend closure quality work on the existing canonical design-record flow.
- Treat remaining work as calibration and artifact hardening only, not as missing source-responsibility recovery.
