# 场景中心

场景中心注册 12 个首批业务场景：历史洪水复盘、洪水预测、干旱监测、水库调蓄、流域水文、河流水质数据分析、多站点水质方法实验、洪水易发性、水土流失、GEE 数据检索、模型对比和高级自定义流程。

每个场景包含业务问题、必需和可选数据、自动数据来源、能力、Workflow、就绪度规则、输出类型、验证等级、生产状态、限制和适用边界。六步向导统一为 Goal、Data、Readiness、Configuration、Review、Run。

Run 步骤调用现有 `Run Manager` 和 `Workflow Engine`。缺少数据时显示下一步建议，例如获取 DEM、上传流量、完成站点映射或修复单位/CRS，而不是只显示错误。

CLI：

```bash
python -m hydrolite scenarios list
python -m hydrolite scenarios show SC08
python -m hydrolite scenarios readiness SC08
```
