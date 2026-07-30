# Evapotranspiration Methods

方法优先级：合格的用户 PET -> 输入完整的 FAO56 Penman–Monteith -> 有温度和纬度的 Hargreaves–Samani -> 仅限合成 Demo 的温度气候态。

FAO56 需要平均温度、太阳辐射、相对湿度和风速；缺少这些变量时不会伪造 Penman–Monteith 结果。Hargreaves 需要最低、最高、平均温度和纬度。所有 PET 统一为 `mm/day`，负值与缺失值拒绝。

实际蒸散由 PET、植被系数和土壤含水状态约束。`pet_method_report.md` 记录输入、假设、单位与限制。
