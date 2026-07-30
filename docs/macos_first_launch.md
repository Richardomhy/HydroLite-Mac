# macOS 首次启动

从 Finder 打开 HydroLite Studio 后，原生启动页会显示版本、运行模式和数据/日志目录，并等待本地 Streamlit 健康检查。欢迎流程可创建项目、打开项目中心或运行轻量 Demo。

首次启动不会下载大型数据、登录 GEE/Earthdata/CDS、运行 QGIS/HEC-HMS、迁移 `~/.hydrolite` 或安装依赖。旧 runtime 只检测并给出迁移计划，默认继续使用旧路径。

退出 App 会仅停止其记录的后端进程并保留成果。异常退出后下次启动会检测 stale lock、数据库和 interrupted Run。
