# 真实项目 HydroLite 模型诊断（M8B）

M8B 复用 M8A 已建立的受治理工作区，生成标准 HydroLite 输入，调用正式 `hydrolite.runner.run_case` 执行产汇流，并形成水量平衡、事件诊断、what-if 情景对比和受审核交付记录。它不修改外部真实资料。

## 运行入口

```bash
python -m hydrolite real-project model /path/to/source \
  --workspace-dir ~/.hydrolite/workspaces/gaoqiao-river-basin-real-validation \
  --output-dir output/real_project_validation
```

`--output-dir` 指向 M8A 基线输出根目录；M8B 成果写入其 `m8b/` 子目录。运行前必须已存在 M8A 工作区、项目 Version 1 和基线 Manifest。

## 输入与成果

- 输入：受审查的流域/河网几何、降雨、观测流量、初始参数与可选湿天水质观测。
- 模型成果：`result_flow.csv`、`summary.xlsx`、`water_balance.xlsx` 及正式 Run Manifest。
- 诊断成果：事件就绪度、水文指标、观测与模拟序列、水量平衡门禁。
- 情景成果：降雨倍率敏感性对比，统一标记为 `what_if_sensitivity_scenario`。
- 水质成果：只允许湿天观测和估算瞬时通量诊断，不输出污染物过程模拟或来源归因。

## 科学与交付边界

- 科学状态固定为 `real_data_diagnostic`，表示真实项目数据诊断，不表示独立事件验证。
- CN、lag、Muskingum K/X 如未率定，必须保留低置信度 provenance，不得将初始值包装为校准参数。
- what-if 情景不是概率预报、重现期洪水或气候预测。
- `water_quality` 主能力继续保持 `planned`；本阶段不建立水质过程模型。
- 交付审核与科学验证分离；`reviewed` 不等于模型已独立验证。
- M9 未实施。只有水文门禁为 `ready` 或 `ready_with_warnings` 时，才可讨论后续节点。

## 安全边界

外部原始数据只读，处理后几何、标准化表格、Run 产物和报告仅写入工作区或 `output/` 。不将真实 GIS、降雨、流量、水质、运行产物、凭证、模型权重或外部仓库纳入 Git。
