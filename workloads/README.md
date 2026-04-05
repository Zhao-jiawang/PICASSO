# Workload Notes

This directory is the PICASSO-facing home for workload definitions and generated traces.

Current workload state:

- The unified runner now uses Python-native workload bindings from JSON.
- Workload selection is resolved through `picasso_workload` in workload definition files.
- Runnable workload definitions:
  - `cnn_inference.json`
  - `long_context_prefill.json`
  - `kv_heavy_decode.json`
  - `dense_decoder_block.json`
  - `mixtral_moe_trace.json`
  - `megatron_collective_trace.json`
- Trace generation:
  - `../scripts/generate_workload_traces.sh`
  - `../pyscripts/workloads/generate_workload_traces.py`
- Generated trace outputs:
  - `generated/mixtral_moe_trace.json`
  - `generated/megatron_collective_trace.json`

All six PICASSO workload motifs are now runnable through the Python-native config layer. The generated trace files remain deterministic artifacts that feed workload metadata into the evaluator and canonical design records.
