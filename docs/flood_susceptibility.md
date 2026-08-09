# 洪水易发性实验 MVP

本阶段实现静态洪水易发性概率实验，不实现动态洪水预报、淹没水深、暴露度、脆弱性或损失计算。

流程为：洪水清单质量检查、条件因子检查、空间独立划分、监督基线、概率校准、独立测试区评价、相对易发性制图、非因果解释。模型包括 prevalence、逻辑回归、随机森林和梯度提升。模型、阈值和校准方法只用训练集与验证集确定，测试集只做最终评价。

Demo 使用 2400 个合成点、24 个空间块和 18 个条件因子，所有产物均标记 `SYNTHETIC DEMO`。合成结果只验证软件方法，不能证明真实流域泛化能力。

```bash
python -m hydrolite susceptibility demo
python -m hydrolite susceptibility validate
python -m hydrolite susceptibility report
```

本实现借鉴公开论文中的通用方法思想，为 HydroLite 独立设计，不构成原论文模型的精确复现。
