# 水库调蓄 MVP

HydroLite 使用 level-pool 连续性演算，要求高程-库容曲线和明确泄流曲线。库容曲线只描述蓄水关系，不能推导真实泄流能力；缺泄流曲线时状态为 `discharge_curve_missing`，不执行路由。当前原创 demo 为合成数据，仅用于软件验证，不用于工程调度、闸门优化、蒸发或渗漏估计。

水量平衡审计使用完整退水过程线；用于跨模型展示的 comparison window 不参与体积守恒判定。HEC-HMS 4.13 Outflow Curve 需要 storage-discharge 配对数据，stage-discharge 必须先在共同高程范围转换。
