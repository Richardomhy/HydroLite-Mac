# Soil Water Model

MVP 使用上下两层土壤桶，包含入渗、土壤蒸发、蒸腾、上层向下层渗漏、壤中流和地下水补给。参数必须满足：

`wilting_point < field_capacity < saturation`

土壤深度、根系深度和饱和导水率必须为正。真实项目缺参数时可按土类映射，但结果标记 `parameter_uncertain`；Demo 默认值不可当作真实率定参数。
