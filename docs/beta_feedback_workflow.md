# Beta 反馈闭环

本文档说明 HydroLite Studio v0.6.0-beta 发布后如何收集、分类、处理和关闭用户反馈。

## 用户如何提交反馈

推荐使用 GitHub Issues：

- Bug：选择 `Bug report`。
- 功能建议：选择 `Feature request`。
- Beta 体验反馈：选择 `Beta feedback`。
- 数据模板问题：选择 `Data template issue`。

在线体验地址：

<https://hydrolite-mac-6zljwlwgtiwhkwneromuak.streamlit.app>

GitHub 仓库：

<https://github.com/Richardomhy/HydroLite-Mac.git>

提交前请删除敏感数据、私有路径、账号、token、service account json、工程涉密资料和模型权重。

## 开发者如何分类反馈

- `bug`：功能异常、页面崩溃、CLI 报错、输出文件缺失。
- `enhancement`：流程优化、新入口、新展示方式、交互改进。
- `documentation`：README、教程、部署说明、FAQ 不清晰。
- `data-template`：字段说明、模板格式、校验规则、示例数据问题。
- `backend-dependency`：GEE、SWMM、OpenHydroNet、Streamlit Cloud 或系统依赖问题。

## 优先级

- P0：数据安全、secrets 泄露、无法启动、核心 demo 完全不可用。
- P1：项目校验、情景运行、报告导出、主要页面不可用。
- P2：部分后端依赖失败但主流程可降级、文档缺口、模板边界问题。
- P3：体验优化、文案调整、非阻塞建议。

## 处理流程

1. 复现问题，确认版本、环境和输入数据类型。
2. 标记分类和优先级。
3. 判断是否涉及敏感数据；如涉及，要求用户删除或脱敏。
4. 对 bug 建立最小复现路径。
5. 修复后运行轻量检查和相关测试。
6. 在 Issue 中说明修复 commit、验证命令和剩余限制。

## 关闭标准

- Bug：有复现说明、修复 commit、测试或手动验证结果。
- Enhancement：需求被实现、延期或明确不纳入当前范围。
- Documentation：文档已更新并链接到相关入口。
- Data template：模板、校验器或示例说明已更新。
- Backend dependency：给出本地/云端差异、降级行为或安装建议。

## 下个版本处理

每轮 beta 反馈应汇总到下一版本计划中：

- 高频阻塞问题优先进入补丁版本；
- 易用性问题进入 v0.6.x；
- 新模型算法、训练和大规模推理不在反馈闭环中直接新增，应单独规划。
