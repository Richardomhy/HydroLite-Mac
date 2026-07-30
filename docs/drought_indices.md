# Drought Indices

支持气象 SPI/SPEI、农业土壤水百分位和蒸散亏缺、水文 SSI/径流/基流百分位、地下水与水库百分位，以及显示分量和权重的综合指数。

SPI、SPEI、SSI 支持 1/3/6/12/24 个月。基线期必须由配置指定或明确建议；概率分布只在基线期拟合。Gamma、Normal 和经验百分位可选，拟合失败转为带原因的经验百分位。记录不足时标记 `limited_record`，不声称统计分布稳定。

默认等级是 `diagnostic_default_thresholds`，不等于当地法定干旱预警标准。
