# PICASSO 校准状态说明

## 当前结论

当前 calibration 可以默认冻结。

这里的含义是：

- 不需要再把 evaluator / legality / traffic / cost 的主链修复作为默认主线。
- 当前默认工作应回到 PICASSO 项目本身的 artifact、paper sync、reviewer-facing hardening 和开源整理。
- 只有当新的自动化验收再次暴露回归时，才重新打开 calibration 主线。

## 当前判断依据

当前以自动化验收审计为准：

- `docs/ACCEPTANCE_STATUS.md`
- `results/acceptance/current_acceptance_audit.json`
- `results/acceptance/current_acceptance_audit.md`

当前审计上下文：

- `results/aggregated/20260405_205311_paper_smoke`
- `results/aggregated/20260405_205311_paper_core_bootstrap`
- `results/aggregated/20260405_205311_paper_full_bootstrap`

### 1. 主运行链已全部合法

当前最新审计结果：

- `paper_smoke`: `1 / 1` legal
- `paper_core_bootstrap`: `24 / 24` legal
- `paper_full_bootstrap`: `64 / 64` legal

这说明此前阻塞 artifact 交付的 legality 回归已经收口。

### 2. backend closure 已不再是 placeholder

当前以下输出已经生成实际值，而不是 placeholder：

- `winner_agreement.csv`
- `legality_confusion.csv`
- `boundary_drift_backend.csv`
- `claim_closure.csv`
- `closure_summary.csv / json`
- `router_sensitivity.csv`
- `deployment_regime_summary.csv`

这些输出当前描述的是：

- `projected decision preservation`

而不是：

- backend sign-off correctness

这个边界必须保留。

### 3. validation 锚点仍保持合理

当前文件：

- `validation/package_yield_anchor.csv`
- `validation/interface_envelope.csv`
- `validation/compute_grounding.csv`

仍满足：

- package cost 顺序保持 `OS < FO < SI`
- interface envelope 没有出现明显逆序或离谱量级
- compute grounding 维持保守可信的 fallback 口径

## 当前建议

当前默认执行策略是：

1. 冻结 calibration 主线。
2. 回到 PICASSO 项目本身。
3. 继续做：
   - 文档与 paper 映射
   - figure / table 语义收敛
   - reviewer-facing hardening
   - 开源仓库整理

也就是说，接下来的主问题不再是“继续修模型”，而是：

- 保持 artifact 输出和 paper claim 一致
- 继续加强 closure 的解释质量
- 整理仓库表面与复现说明

## 什么时候重新打开 calibration

只有出现下面任一情况时，才建议重新投入 calibration：

### 1. 最新验收审计再次出现 legality 回归

例如：

- `smoke` 不是 `1 / 1`
- `paper_core` 不是 `24 / 24`
- `paper_full` 不是 `64 / 64`

### 2. package / interface / compute grounding 再次异常

例如：

- `OS < FO < SI` 被破坏
- compute grounding 又出现明显失真的 process advantage

### 3. 新增数据后，paper-facing claim 与当前模型出现系统性矛盾

例如：

- figure claim 与 closure summary 不一致
- 新增可比 process anchors 后，当前 fallback grounding 不再足够

## 执行结论

当前正式结论是：

- calibration 可以默认冻结
- 默认主线回到 PICASSO artifact 和项目本身
- 如果后续 acceptance audit 再次出现回归，再重新打开 calibration
