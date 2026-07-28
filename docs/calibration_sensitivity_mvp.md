# 轻量参数敏感性与率定 MVP

HydroLite Studio 的本阶段实现是受控的单事件参数诊断：先识别目标来源，再以固定随机种子运行 OAT 和最多 40 个多参数候选。默认搜索 30 个候选，候选运行在 `output/calibration/workspaces/`，不会写回项目原始 CSV 或 YAML。

## 术语

- 存在非 synthetic 实测流量时：`observed_calibration`，可称模型率定。
- 使用 HEC-HMS 结果时：`hms_cross_model_alignment`，只能称跨模型对齐，不能称实测率定。
- demo/synthetic 流量时：`synthetic_demo_calibration`，仅验证流程。

## 参数与边界

- CN：基线 +/-15，截断为 30--98。
- 初损比：0.05--0.30，且不超过 0.50。
- lag 与 Muskingum K：基线 0.5--2.0 倍，均为正数。
- Muskingum X：0.05--0.45；每个候选重新检查 `2*K*X <= dt <= 2*K*(1-X)`。

## 命令

```bash
python -m hydrolite calibration target projects/qgis_workflow_project output/hec_hms_comparison
python -m hydrolite calibration sensitivity projects/qgis_workflow_project output/hec_hms_comparison
python -m hydrolite calibration search projects/qgis_workflow_project output/hec_hms_comparison --max-candidates 30
```

单一事件的 `validation_status` 永远是 `unavailable_single_event`，不得将同一事件后 25% 的时间段称为独立验证。

## 目标函数与解读

候选按 NSE、KGE、PBIAS、RMSE、峰值误差、峰现时间与总量误差的可用项加权排序；在 HEC-HMS 模式该值标记为 `alignment_score`，不使用 `observed_calibration_score`。结果只能说明本次事件中的模型差异是否缩小，不能据此宣称预测能力或工程设计可靠性。应保留基线、检查参数是否贴边，并在取得第二场独立事件后再作验证。
