# Continuous Water Balance

每个子流域逐日保存以下账本：

`precipitation - interception_evaporation - actual_et - surface_runoff - interflow - baseflow - deep_loss - storage_change = residual`

`storage_change` 包括冠层、地表、上下层土壤、地下水和雪占位储量。河道另以 `inflow - outflow - channel_storage_change = residual` 审计，末日库容不强制释放。

缺测降雨或 PET 会阻止运行，绝不按零处理。默认日残差容差为 `1e-6 mm`、时期累计残差容差为 `1e-4 mm`；门禁失败时不得生成正式干旱预测。
