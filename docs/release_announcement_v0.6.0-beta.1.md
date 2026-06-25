# HydroLite Studio v0.6.0-beta.1 补丁发布说明

HydroLite Studio v0.6.0-beta.1 是基于 `v0.6.0-beta` 的补丁版本。本次不新增模型算法，不训练 OpenHydroNet，也不运行真实大规模 AI 推理；重点是把 beta 反馈闭环、Issue 模板、smoke test 文档和发布后验证流程纳入正式补丁 release。

## 在线体验

https://hydrolite-mac-6zljwlwgtiwhkwneromuak.streamlit.app

## GitHub 仓库

https://github.com/Richardomhy/HydroLite-Mac.git

## 本次补丁包含

- GitHub Issue 模板；
- Streamlit `Beta 反馈` 页面；
- `python -m hydrolite beta ...` CLI；
- 云端 smoke test 文档；
- 本地 smoke test 文档；
- 发布后验证文档；
- beta feedback workflow；
- `release/v0.6.0-beta.1/` 发布包和 manifest。

## 推荐反馈方式

请在 GitHub Issues 中选择合适模板：

- Bug report：功能异常、页面崩溃、CLI 报错；
- Feature request：功能建议；
- Beta feedback：整体 beta 体验反馈；
- Data template issue：数据模板或字段规范问题。

## 安全提醒

提交反馈前请删除：

- Google credentials、token、API key、service account json；
- 私有工程数据、涉密路径、账号信息；
- 外部仓库内容；
- 模型权重、checkpoint、训练数据大文件。

## 当前限制

- 在线版适合演示、教程、模板下载和查看示例输出；
- 完整 GEE/SWMM/OpenHydroNet 工作流建议在本地配置；
- OpenHydroNet 当前只准备 input package，不训练模型，不运行大规模推理；
- 真实工程结论需要专业人员复核。

## 后续计划

- 根据 beta 反馈修复高优先级问题；
- 改进数据模板和项目向导体验；
- 强化报告导出和在线演示说明；
- 保持模型算法变更进入单独规划，不混入反馈补丁。
