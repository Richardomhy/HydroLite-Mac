# Drought Forecast MVP

预测链路为：历史连续状态 -> 分析日期 -> 多成员气象 forcing -> 各成员连续模型 -> SPI/SPEI/SSI/土壤水/地下水/水库 -> 1/3/6/12 月指标 -> 分类与分位数。

覆盖不足的提前期自动跳过，失败成员独立记录。连续水量门禁失败时关闭预测。普通情景集合只报告 `scenario_member_fraction`；只有正式概率集合才能称 probability。

当前能力为 `partial`。合成 Demo 不是业务预报，真实项目需要长期连续观测、已发布气象预报、偏差订正和独立验证。
