# HydroLite 干旱分析中文指南

## 快速演示

```bash
bash scripts/create_hydrolite_science_env.sh
conda run -n hydrolite-science python -m hydrolite continuous run data_demo/drought/continuous_model_config.yaml
conda run -n hydrolite-science python -m hydrolite drought indices data_demo/drought
conda run -n hydrolite-science python -m hydrolite drought events data_demo/drought
conda run -n hydrolite-science python -m hydrolite drought monitor data_demo/drought
conda run -n hydrolite-science python -m hydrolite drought forecast-demo
conda run -n hydrolite-science python -m hydrolite drought assimilation data_demo/drought
conda run -n hydrolite-science python -m hydrolite drought report output/drought_model
```

先看连续水量门禁，再解释土壤水/地下水/流量/水库状态，然后按气象、农业、水文、水库、地下水和综合干旱分开分析。基线期、时间尺度、分布、时效和数据缺口必须随结果报告。

真实项目应上传长期日气象；PET 可提供或由合格输入计算；流量、土壤水、地下水和水库观测用于验证/同化。原始数据只读，标准化与修正写入 `standardized/` 或 `derived/`。

在线版适合查看预生成成果和小型 Demo；本地版用于科学环境、长期序列和受控连接器。当前不是法定干旱预警系统，也不包含 MODFLOW、作物模型或水资源优化配置。
