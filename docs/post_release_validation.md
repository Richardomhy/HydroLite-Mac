# HydroLite Studio v0.6.0-beta 发布后验证清单

本文档用于 `v0.6.0-beta` 发布后检查 GitHub、Streamlit Cloud、文档和安全边界是否正常。

## GitHub Release 检查

- 确认仓库地址为 <https://github.com/Richardomhy/HydroLite-Mac.git>。
- 确认 tag `v0.6.0-beta` 存在，且没有被移动。
- 确认 Release 标题、说明、版本号和日期与 README 一致。
- 确认 Release 页面说明本版本是 beta 测试版本，不是正式工程设计软件。

## Release Assets 检查

- 检查 `release/v0.6.0-beta/` 中的 manifest、demo project package、data template bundle 和 report bundle。
- 下载 assets 并确认可以正常解压。
- 确认 assets 不包含 `data_raw`、Google credentials、tokens、service account json、外部 OpenHydroNet 仓库、模型权重或 checkpoint。

## Streamlit Cloud 检查

- 打开在线地址：<https://hydrolite-mac-6zljwlwgtiwhkwneromuak.streamlit.app>。
- 确认首页显示当前版本、GitHub 仓库和在线版/本地版差异说明。
- 打开“教程与 Demo”“数据模板”“项目向导”“报告与导出”“Beta 反馈”页面。
- 确认云端限制说明清晰：GEE 登录、SWMM 后端和 OpenHydroNet 外部仓库可在本地完整配置。

## README 链接检查

- 检查 GitHub 仓库地址。
- 检查 Streamlit Cloud 在线体验地址。
- 检查 Quick Start、本地运行、部署、教程、数据模板和反馈入口链接。
- 确认 README 中没有密钥、私有路径或未公开账号信息。

## 文档链接检查

- 检查 `docs/quickstart_zh.md`、`docs/user_guide_zh.md`、`docs/tutorial_demo.md`、`docs/project_wizard.md`、`docs/data_templates.md`。
- 检查本文件、`docs/cloud_smoke_test.md`、`docs/local_smoke_test.md`、`docs/beta_feedback_workflow.md`。
- 确认文档说明在线版适合演示，本地版适合完整 GEE/SWMM/OpenHydroNet 工作流。

## No Secrets 检查

运行：

```bash
git ls-files | rg -i "secrets.toml|credentials|service-account|\\.pt$|\\.pth$|\\.ckpt$|\\.onnx$|^external/"
```

预期没有输出。若有输出，停止发布并移除相关文件。

## 回退方式

- 如果在线版异常，先回退 Streamlit Cloud 到上一可用 commit。
- 如果 GitHub Release 说明有误，优先更新 Release 文案，不移动已有 tag。
- 如果发现敏感文件已经提交，立即撤销公开访问、轮换密钥，并重写仓库历史前先评估影响范围。

## 问题记录方式

- Bug：使用 GitHub Issue 的 `Bug report` 模板。
- 功能建议：使用 `Feature request` 模板。
- Beta 体验反馈：使用 `Beta feedback` 模板。
- 数据模板问题：使用 `Data template issue` 模板。
