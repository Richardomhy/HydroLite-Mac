# Streamlit Cloud Smoke Test

用于发布后快速检查在线演示版是否可用。

## 1. 打开在线地址

访问：

<https://hydrolite-mac-6zljwlwgtiwhkwneromuak.streamlit.app>

确认页面可以加载，没有 Python traceback。

## 2. 检查首页

- 显示 HydroLite Studio 当前版本。
- 显示 GitHub 仓库地址。
- 显示在线版适合演示、本地版适合完整工作流。
- 显示 Beta 反馈入口和敏感数据提醒。

## 3. 打开教程与 Demo

- 进入“教程与 Demo”页面。
- 确认推荐路线 A/B/C 可以阅读。
- 确认每个步骤显示 CLI 等价命令和预期结果。
- 完成演示后，按提示进入“Beta 反馈”页面记录问题。

## 4. 查看数据模板

- 进入“数据模板”页面。
- 确认模板列表、字段说明和下载入口可见。
- 下载模板时不要上传真实敏感工程数据。

## 5. 查看项目向导

- 进入“项目向导”页面。
- 预览 basic 或 full_demo 模板。
- 云端如不能写入指定路径，应显示清晰说明，而不是崩溃。

## 6. 查看报告导出页

- 进入“报告与导出”页面。
- 确认已有报告、Markdown/HTML/Word 或项目包入口可见。
- 云端如缺少某些本地依赖，应显示降级说明。

## 7. 下载模板

- 尝试下载数据模板或示例报告。
- 确认下载文件不包含 credentials、tokens、service account json、external 仓库或模型权重。

## 8. 确认云端限制说明

云端演示版不强制执行：

- GEE 认证；
- SWMM 本地隔离求解器；
- OpenHydroNet 外部仓库；
- 大规模 AI 推理。

完整工作流建议在本地环境运行。

## 9. 记录问题

使用 GitHub Issues：

- Bug report；
- Feature request；
- Beta feedback；
- Data template issue。

提交反馈前请删除敏感数据、私有路径、账号、token 和工程涉密信息。
