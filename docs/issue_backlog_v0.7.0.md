# v0.7.0 GitHub Issue Backlog

以下条目可复制到 GitHub Issues，并按 M1-M6 挂到 milestone。

## Issue 1：QGIS 环境诊断 CLI

- 类型：feature
- 背景：v0.7.0 需要判断用户本机是否有 QGIS、`qgis_process` 或 PyQGIS。
- 任务：新增诊断命令，输出 QGIS 路径、版本、Python 环境和常见错误。
- 验收标准：无 QGIS 时不崩溃；有 QGIS 时能读版本。
- 风险：macOS app bundle 路径差异。
- 优先级：P0

## Issue 2：QGIS 图层导出 HydroLite 模板草案

- 类型：feature
- 背景：用户希望从 QGIS 子流域、河网、边界进入 HydroLite。
- 任务：定义 GeoPackage/GeoJSON/CSV 到 HydroLite 模板字段映射。
- 验收标准：能生成 rainfall/subbasin/reach/boundary 模板草案。
- 风险：图层字段命名不一致。
- 优先级：P1

## Issue 3：Excel 导入最小路径

- 类型：feature
- 背景：真实项目数据常以 Excel 交付。
- 任务：读取指定 sheet，映射到 rainfall/subbasin/reach/observed 模板。
- 验收标准：错误能定位 sheet、行、列。
- 风险：Excel 格式自由度太高。
- 优先级：P0

## Issue 4：批量 CSV 检查与字段映射

- 类型：feature
- 背景：单文件校验不足以覆盖项目数据包。
- 任务：扫描目录中的 CSV，检查字段、单位、空值和负值。
- 验收标准：生成汇总表和错误清单。
- 风险：字段别名规则膨胀。
- 优先级：P1

## Issue 5：单位转换助手

- 类型：feature
- 背景：真实数据常混用 mm、m、ha、km2、cms。
- 任务：支持常见水文单位转换并记录转换说明。
- 验收标准：转换前后字段和单位可追踪。
- 风险：自动推断单位可能误判。
- 优先级：P1

## Issue 6：轻量参数扫描

- 类型：feature
- 背景：需要比较 CN、lag_time、Muskingum K/X 对结果的影响。
- 任务：对给定参数范围做小规模组合或单因素扰动。
- 验收标准：输出指标表、最优候选和图表。
- 风险：组合数过大导致运行时间增加。
- 优先级：P0

## Issue 7：率定指标报告

- 类型：feature
- 背景：已有观测流量评估需要进入报告。
- 任务：输出 NSE、RMSE、KGE、峰值误差、总量误差。
- 验收标准：生成 xlsx、png 和 markdown 报告。
- 风险：观测数据缺失导致指标不可比。
- 优先级：P1

## Issue 8：中文工程报告模板

- 类型：feature
- 背景：当前报告更偏通用 demo。
- 任务：新增中文封面、目录、图表编号、免责声明。
- 验收标准：demo_project 可导出中文报告。
- 风险：Word/PDF 跨平台样式差异。
- 优先级：P1

## Issue 9：本地启动器技术验证

- 类型：test
- 背景：用户希望像桌面软件一样打开工作台。
- 任务：评估 PySide6、Tauri、Electron、shell/AppleScript 启动器。
- 验收标准：推荐一种最小路线。
- 风险：桌面打包复杂度过高。
- 优先级：P2

## Issue 10：SWAT/GEE/QGIS 数据关系说明

- 类型：docs
- 背景：用户需要理解 HydroLite 与 SWAT、GEE、QGIS 的边界。
- 任务：写清目录关系、边界互转和前处理定位。
- 验收标准：文档可指导用户组织项目资料。
- 风险：误导为 SWAT 完整集成。
- 优先级：P2
