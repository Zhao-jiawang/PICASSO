# PICASSO 项目改造说明

## 项目背景与目标

`Project_Statement` 的目标是把仓库整理为可持续演进的 PICASSO 工程，而不是继续维持一个混合 C++ / Python、入口分散、结果链路难追踪的旧式 DSE 项目。

当前阶段已经完成“代码重构”主线：运行面已经完全切到 Python-native PICASSO。后续工作不再是迁移旧代码，而是在这个新的运行面上继续补齐 PICASSO 论文和 artifact 语义。

## 术语边界说明

- 需要移除的是重构前遗留代码、兼容目录、过渡命名和旧入口，不是 PICASSO 的核心能力。
- `legality` 是 PICASSO 的核心约束系统，包含 edge / route / memory legality，必须保留并继续完善。
- 因此，“去掉遗留项”不等于“去掉 legality”。

## 当前仓库现状

当前仓库已经不是重构前的旧组织方式，而是一个 Python-native PICASSO 仓库。

### 当前实际目录

当前根目录的核心内容包括：

- `configs/`：配置、baseline、interface / package / memory / legality registry
- `docs/`：PICASSO 文档体系
- `paper/figures/`：论文插图副本
- `picasso/`：核心运行时代码
- `pyscripts/`：按职责分类的 Python 脚本入口
- `scripts/`：统一 shell 入口
- `results/`：`raw / aggregated / plot_ready / figures / backend / backend_aggregated`
- `validation/`：Fig. 3 相关验证数据
- `workloads/`：六类 workload 定义与生成 trace
- `Project_Statement/`：原始任务书输入材料
- `requirements.txt`、`pyproject.toml`、`README.md`

### 已移除的重构前遗留项

以下内容已经不再是仓库的一部分：

- `src/`
- `include/`
- `build/`
- `makefile`
- `summary.sh`
- 根目录 `72tops_* / 128tops_* / 512tops_*` sweep 脚本
- `legacy/`
- `pyscripts/legacy_utils/`

### 当前仓库的事实特征

- 主运行入口已经统一到 `scripts/`。
- 核心运行逻辑已经集中到 `picasso/`。
- `pyscripts/` 已按 `analysis / backend / pipeline / workloads` 分类，不再是根目录脚本堆。
- `engine.py` 已拆分为 `search.py`、`evaluator.py`、`legality.py`、`result_serialization.py` 等职责明确的模块。
- 评估链已经从单段 surrogate 公式升级为显式的：
  - `area_model.py`
  - `mapping_model.py`
  - `traffic_model.py`
  - `latency_model.py`
  - `cost_model.py`
- 当前 Python 运行面已经显式输出和使用：
  - inter-chip traffic
  - peak NoC / NoP pressure
  - DRAM channel pressure
  - decomposed latency terms
  - yield-aware package cost
- `paper_full` 运行矩阵已经覆盖 6 类 workload motif：
  - `cnn_inference`
  - `long_context_prefill`
  - `kv_heavy_decode`
  - `dense_decoder_block`
  - `mixtral_moe_trace`
  - `megatron_collective_trace`
- 当前结果链路已经是：
  - `results/raw/`
  - `results/aggregated/`
  - `results/plot_ready/`
  - `results/figures/`
  - `paper/figures/`

## 目标态仓库结构

当前仓库的最终代码结构已经基本稳定，核心结构如下：

```text
repo_root/
  configs/
  docs/
  paper/
    figures/
  picasso/
    core/
    pipeline/
    workloads/
  pyscripts/
    analysis/
    backend/
    pipeline/
    workloads/
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
  scripts/
  validation/
  workloads/
```

这个结构的重点是：

- `picasso/` 放可复用运行时代码
- `pyscripts/` 放明确职责的 Python 入口
- `scripts/` 放复现实验的一键入口
- `results/` 放全链路产物
- `docs/` 放规范、计划、说明、验收

## 必须完成的改造范围

代码重构阶段已经完成的关键项包括：

- C++ 运行面完全退出仓库执行路径
- 统一 Python runner 和 run bundle
- evaluator / search / legality / serialization 拆分
- workload 解析独立成 `picasso/workloads`
- 6 类 workload motif 全部可运行
- 后端抽样、转换、聚合和图表重建可以在 Python-native 运行面上继续执行

接下来仍需继续推进的不是“重构”，而是 PICASSO artifact 本身的完善，例如：

- evaluator / legality 的进一步校准
- figure 语义与论文 claim 的进一步收敛
- backend closure 的进一步增强
- reviewer-facing hardening

## 结果链路与论文映射要求

当前仓库已经具备可追踪的结果链路：

- 每个 run 都有 `config_snapshot.json`
- 每个 point 都有 `point_snapshot.json`、`search_trace.jsonl`、`stdout.log`、`stderr.log`
- 每个 aggregated run 都有 `result.csv`、`manifest.json`、`design_records/`
- plot-ready CSV、最终 figures、paper figures 都可以沿链路回溯

因此，后续工作应继续沿 `raw -> aggregated -> plot_ready -> figures -> paper` 这条链路推进，而不是重新引入临时脚本或手工汇总。

## 后端闭环与 reviewer hardening 要求

当前仓库已经能生成：

- `closure_summary.csv / json`
- `winner_agreement.csv`
- `legality_confusion.csv`
- `boundary_drift_backend.csv`
- `router_sensitivity.csv`
- `package_cost_ordering_check.csv`
- `deployment_regime_summary.csv`

后续要做的是提高这些输出与论文最终 claim 的一致性，而不是重回旧项目的非结构化流程。

## 文档关系说明

5 份核心文档的角色如下：

- `PROJECT_STATEMENT_CODEX.md`：定义“要什么”
- `AGENT.md`：定义“执行时不能违反什么”
- `Plan.md`：定义“原始实施蓝图”
- `Checklist.md`：定义“论文 artifact 什么时候算完成”
- `PICASSO_Modification_Guide_ZH.md`：定义“给用户看的中文解释和导读”

另外，`CODE_REFACTOR_CHECKLIST.md` 只负责回答一个问题：代码重构是否完成。

补充一份面向重构准确性的台账：

- `SRC_SEMANTIC_RECOVERY_LEDGER.md`：逐项说明历史 `src/` 文件的语义职责、当前 Python 对应位置，以及当前的恢复结论。

当前这份台账已经完成了一轮对历史 `src/` / `include/` 的逐项复核，结论是：

- 历史运行时职责已经全部有明确的 Python-native owner。
- 当前已经不存在“运行路径上仍缺失 owner 的 `Partial / Missing` 项”。
- 后续工作重点是校准与论文 artifact hardening，而不是继续补“谁来承接原 `src` 语义”。

## 当前校准判断

当前已经可以把“继续修 calibration”从默认主线移走。

原因是：

- package / interface / compute-grounding 的基础口径已经回到合理范围。
- 最新自动化验收上下文已经显示：
  - `paper_smoke = 1 / 1`
  - `paper_core = 24 / 24`
  - `paper_full = 64 / 64`
- 最新 backend closure 输出已经不再带 placeholder。

这意味着后续不该继续做大范围 evaluator 主链改写，默认主线应回到 PICASSO artifact 本身。

对应说明见：

- `docs/CALIBRATION_STATUS_ZH.md`
- `docs/ACCEPTANCE_STATUS.md`

## 后续执行建议

接下来的工作应按下面顺序继续：

1. 保持 calibration 冻结，除非新的 acceptance audit 再次暴露回归。
2. 继续推进文档、paper 映射、closure wording 和 reviewer-facing hardening。
3. 保持 `scripts/` 作为唯一正式入口，不再新增根目录临时脚本。
4. 所有新增模块继续放在职责直观的位置，避免重新出现大杂烩文件。
5. 所有后续 PICASSO 工作都基于当前重构后的目录结构推进，而不是再回头参考或恢复旧工程组织方式。
