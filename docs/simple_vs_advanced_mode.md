# Simple Mode 与 Advanced Mode

默认 Simple Mode 面向业务用户，只显示场景、数据、运行摘要、结果、可信度、限制和下一步建议。用户无需理解 YAML、CLI、DSS、模型目录或内部 stage。

Advanced Mode 显示 Workflow、Model Registry、Research、Environment、任务、日志和详细成果。两种模式只改变 UI 显示，不改变科学计算、参数、输入或输出。

建议普通用户使用 Simple Mode 完成项目和场景工作流；模型开发者、环境维护者和高级审计人员再切换 Advanced Mode。任何依赖缺失、数据无效或模型阻断都会显示分类错误与建议操作，技术 traceback 仅在 Advanced Mode 展开。
