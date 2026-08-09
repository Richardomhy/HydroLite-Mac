# Scientific Validation vs Delivery Review

HydroLite 同时显示两套独立状态。

## Scientific / Model Validation

`synthetic_demo`、`framework_ready`、`ready_with_warnings`、`real_data_tested`、`independently_validated`、`production_ready`。

## Delivery Review

`draft`、`submitted_for_review`、`changes_requested`、`reviewed`、`approved_for_delivery`、`rejected`、`superseded`、`archived`。

`approved_for_delivery` 不等于 `scientifically_validated`，也不等于 `production_ready`。审核动作不能修改科学验证状态。

实验能力允许审核和打包，但 Manifest、UI 和报告必须显著标记 `EXPERIMENTAL`，并声明尚未完成真实项目独立验证。`water_quality=planned` 允许数据分析、方法实验和需求报告，但不能形成声称为 Production Water Quality Simulation Result 的交付物。

当前科学状态保持：`water_quality=planned`；洪水/干旱预测及 Gamma、河网图、趋势、多提前期、水质实验和易发性能力维持既有 partial/experimental 证据等级。
