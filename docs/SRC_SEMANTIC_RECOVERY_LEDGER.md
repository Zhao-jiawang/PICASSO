# PICASSO Source Semantic Recovery Ledger

## Purpose

This ledger exists to prevent semantic loss during the C++ to Python refactor.

The historical `src/` tree does not need to survive as C++ runtime code, but its modeling responsibilities must not be dropped. Any historical file that contributed to compute, mapping, communication, latency, legality, or cost must be explicitly accounted for here.

## Status Legend

- `Recovered`: the historical responsibility has an explicit Python-native owner and is active on the runtime path.
- `Partial`: some semantics were reconstructed, but important object-level behavior or coupling is still missing.
- `Missing`: no meaningful Python-native replacement exists yet.
- `Infra Replaced`: low-level utility code was intentionally replaced by Python builtins or standard libraries.

## Recovery Rules

- Do not treat `Partial` as safe enough.
- Do not delete a historical responsibility from planning until a Python-native owner is explicit.
- Prefer responsibility-oriented Python module names over historical file-name mirroring.
- Reconstruct tight coupling chains together when accuracy depends on cross-file behavior.

## Historical To Current Mapping

| Historical file(s) | Historical role | Current PICASSO owner(s) | Status | Notes / next action |
| --- | --- | --- | --- | --- |
| `src/main.cpp` | top-level SA orchestration, config parsing, run control, output emission | `pyscripts/pipeline/picasso_runner.py`, `picasso/pipeline/run_bundle.py`, `picasso/core/engine.py`, `picasso/core/search.py`, `picasso/core/result_serialization.py` | Recovered | Entry-point responsibility is already Python-native. |
| `src/network.cpp`, `include/network.h` | layer graph, dependency edges, external inputs, shape checks | `picasso/workloads/catalog.py`, `picasso/workloads/model_library.py`, `picasso/pipeline/point_normalization.py`, `picasso/core/workload_graph.py` | Recovered | The runtime now instantiates explicit network specs with external inputs, dependency edges, and shape validation on the active path. |
| `src/layer.cpp`, `include/layer.h` | layer/workload objects, shape transforms, fetch logic, op counts | `picasso/core/workload_graph.py`, `picasso/core/partition_engine.py`, `picasso/core/data_layout.py`, `picasso/core/core_mapping_engine.py` | Recovered | Layer objects now carry explicit op-count, fetch-size, input-range, and weight-range behavior used directly by partitioning, layout, and mapping. |
| `src/nns/*.cpp`, `src/front_end_IRs/*.json`, `include/nns/nns.h` | model libraries and workload instantiation | `workloads/*.json`, `workloads/generated/*.json`, `picasso/workloads/catalog.py`, `picasso/workloads/model_library.py` | Recovered | Workload resolution now lands in a Python-native model library that reconstructs network stacks rather than only motif labels. |
| `src/partition.cpp`, `include/partition.h` | partition enumeration, factor search, utilization constraints, fetch scheme | `picasso/core/partition_engine.py`, `picasso/core/mapping_model.py`, `picasso/core/search.py` | Recovered | The active runtime now enumerates explicit partition candidates, ranks them, and records fetch-plan plus search-space metadata. |
| `src/placement.cpp`, `include/placement.h` | placement schedule, permutation order, layout initialization | `picasso/core/placement_engine.py`, `picasso/core/cluster_model.py`, `picasso/core/light_placement_engine.py` | Recovered | Placement now owns explicit schedule objects, permutation order, ordered core lists, and cluster-backed geometry on the runtime path. |
| `src/datalayout.cpp`, `include/datalayout.h` | data-range ownership, broadcast structure, layout volume tracking, buffer update hooks | `picasso/core/data_layout.py`, `picasso/core/traffic_model.py`, `picasso/core/buffer_model.py` | Recovered | Tensor layouts, broadcast groups, unique-volume tracking, and source ownership are now explicit Python-native objects that feed traffic and buffer accounting. |
| `src/coremapping.cpp`, `include/coremapping.h` | microarchitecture-specific tile mapping, MAC/util/buffer tradeoffs | `picasso/core/core_mapping_engine.py`, `picasso/core/core_model.py`, `picasso/core/layer_engine.py` | Recovered | The active runtime now uses explicit Polar/Eyeriss-aware core-library and core-mapping objects to drive cycles, utilization, and energy terms. |
| `src/layerengine.cpp`, `include/layerengine.h` | partition + placement + mapping fill-in, tile cost assembly, NoC integration | `picasso/core/layer_engine.py`, `picasso/core/evaluator.py`, `picasso/core/mapping_model.py`, `picasso/core/traffic_model.py`, `picasso/core/latency_model.py` | Recovered | A Python-native `LayerEnginePlan` now owns segment, stage, schedule-tree, placement, and execution records on the active runtime path. |
| `src/noc.cpp`, `include/noc.h` | NoC/NoP/DRAM hop accounting, link load, service time, multicast/unicast | `picasso/core/traffic_model.py`, `picasso/core/latency_model.py`, `picasso/core/legality.py`, `picasso/core/light_placement_engine.py` | Recovered | The active runtime now uses load-aware adaptive routing, multicast trunking through chiplet ingress anchors, explicit DRAM-channel assignment, and peak-link / peak-channel service coupling. |
| `src/cost.cpp`, `include/cost.h` | die yield, wafer cost, package cost, defect cost, NRE | `picasso/core/cost_model.py` | Recovered | The active runtime now carries die/package defect costs plus chip/module/package NRE through `cost_system_package`, `cost_soc`, and derived reporting terms. |
| `src/spatial_mapping/segmentation.cpp`, `include/spatial_mapping/segmentation.h` | segment boundaries, reorder/move/flip, SA over segmentation, fallback behavior | `picasso/core/segmentation_engine.py`, `picasso/core/layer_engine.py`, `picasso/core/search.py`, `picasso/core/mapping_model.py` | Recovered | Segment descriptors, stage assignment, fallback behavior, and DP-backed boundary selection are now explicit Python-native owners on the runtime path. |
| `src/spatial_mapping/light_placement.cpp`, `include/spatial_mapping/light_placement.h` | per-segment light placement, layer-core assignment, DRAM source mutation | `picasso/core/light_placement_engine.py`, `picasso/core/layer_engine.py`, `picasso/core/traffic_model.py` | Recovered | Per-layer light placement, active-core ownership, DRAM attachment, multicast roots, and path policy are now explicit runtime objects. |
| `src/spatial_mapping/DP.cpp`, `include/spatial_mapping/DP.h` | dynamic-programming helper path in spatial mapping | `picasso/core/segmentation_engine.py` | Recovered | DP-style segmentation search is now handled directly inside the Python-native segmentation engine. |
| `src/schnode.cpp`, `include/schnode.h` | schedule-node tree, energy records, cluster/buffer state, recursive schedule assembly | `picasso/core/schedule_tree.py`, `picasso/core/layer_engine.py`, `pyscripts/analysis/export_design_records.py` | Recovered | The runtime now builds explicit schedule-tree nodes and segment execution records instead of exporting only flat derived terms. |
| `src/ltreenode.cpp`, `include/ltreenode.h` | layer-tree topology and segment tree operations | `picasso/core/schedule_tree.py`, `picasso/core/layer_engine.py` | Recovered | A Python-native layer-tree representation is now active and feeds schedule assembly plus latency/mapping terms. |
| `src/cluster.cpp`, `include/cluster.h` | core-grid abstraction, allocation, coordinates, chiplet geometry | `picasso/core/cluster_model.py`, `picasso/core/placement_engine.py`, `picasso/core/traffic_model.py` | Recovered | Core-cluster objects now own coordinate lookup, chiplet geometry, allocator behavior, and nearest-DRAM selection on the runtime path. |
| `src/core.cpp`, `include/core.h` | core buffers, MAC resources, core-specific energy/time parameters | `picasso/core/core_model.py`, `picasso/core/core_mapping_engine.py`, `picasso/core/area_model.py`, `picasso/core/latency_model.py` | Recovered | Explicit core objects now carry buffer, MAC, bus, and microarchitecture parameters that feed mapping, area, and latency. |
| `src/bufferusage.cpp`, `include/bufferusage.h` | per-core buffer occupancy tracking and validity | `picasso/core/buffer_model.py`, `picasso/core/legality.py`, `picasso/core/mapping_model.py` | Recovered | A Python-native per-core buffer model is now active on the runtime path and feeds mapping plus legality. Further tuning is about fidelity, not ownership absence. |
| `src/bitset.cpp`, `include/bitset.h` | compact set utility for layer and dependency tracking | Python sets / ints / lists | Infra Replaced | Utility replacement is fine. No model semantics are lost here by itself. |
| `src/util.cpp`, `include/util.h`, `include/debug.h` | helpers, macros, printing/debug support | Python stdlib, `picasso/core/common_math.py` | Infra Replaced | Utility replacement is fine. |
| `src/json/*`, `include/json/*` | JSON parser library | Python `json` module | Infra Replaced | Utility replacement is fine. |

## High-Risk Chains After Recovery

These chains have explicit Python-native owners on the active runtime path. What remains here is calibration work, not missing ownership.

### Chain 1: Layer Graph -> Partition -> Placement -> DataLayout -> NoC/DRAM

Historical files:
- `src/network.cpp`
- `src/layer.cpp`
- `src/partition.cpp`
- `src/placement.cpp`
- `src/datalayout.cpp`
- `src/noc.cpp`

Current status:
- recovered by `model_library.py`, `workload_graph.py`, `partition_engine.py`, `placement_engine.py`, `cluster_model.py`, `data_layout.py`, `traffic_model.py`, and `latency_model.py`

Main calibration focus:
- tune workload-library edge cases and layout-update details without reopening ownership gaps.

### Chain 2: Segmentation -> Light Placement -> Schedule Tree -> Layer Engine

Historical files:
- `src/spatial_mapping/segmentation.cpp`
- `src/spatial_mapping/light_placement.cpp`
- `src/ltreenode.cpp`
- `src/schnode.cpp`
- `src/layerengine.cpp`

Current status:
- reconstructed by `segmentation_engine.py`, `light_placement_engine.py`, `schedule_tree.py`, and `layer_engine.py`

Main gap:
- the Python-native object graph is now active; remaining work is fidelity tuning rather than missing ownership.

### Chain 3: Core Mapping -> Buffer Usage -> Latency/Energy

Historical files:
- `src/coremapping.cpp`
- `src/core.cpp`
- `src/bufferusage.cpp`
- `src/layerengine.cpp`

Current status:
- recovered by `core_model.py`, `core_mapping_engine.py`, `buffer_model.py`, `layer_engine.py`, `area_model.py`, and `latency_model.py`

Main calibration focus:
- tighten mapper constants and microarchitecture calibration where higher fidelity is still useful.

### Chain 4: Yield / Package / Memory Attachment -> Final Cost

Historical files:
- `src/cost.cpp`
- `src/noc.cpp`
- `src/network.cpp`

Current status:
- materially reconstructed in `cost_model.py` plus registry-backed memory/interface/package configuration

Main gap:
- remaining work is calibration of deployment assumptions, not missing cost ownership on the active runtime path.

## Recommended Calibration Order

1. Tighten workload-library and fetch-policy fidelity on top of the recovered graph/partition/layout path.
2. Tighten core-mapper constants now that core-library and mapping ownership are explicit.
3. Tighten placement and layout update fidelity where historical `PlaceSch` behavior was richer than the current surrogate.
4. Continue calibration against historical edge cases rather than reopening ownership gaps that are already closed.

## Completion Standard

A historical file should only move from `Partial` or `Missing` to `Recovered` when:

- its responsibility has a named Python-native owner,
- the coupling path into latency / energy / legality / cost is explicit,
- and the runtime uses that Python-native owner on the active execution path.

Current audit status:

- The historical `src/` and `include/` runtime responsibilities now have explicit Python-native owners on the active PICASSO execution path.
- Remaining work is calibration and paper-facing hardening, not missing source-ownership recovery.
