# 可复现运行

每次 Run 记录配置 checksum、代码 commit、软件/Python 版本、环境快照、输入 checksum、任务日志和成果索引。

Reproduction package 只包含小型配置、标准化输入、checksum、依赖版本和运行说明。凭证、DSS、HDF5、external 和模型权重不会打包。

`compare_runs` 可比较两次 Run 的配置、环境、代码和状态差异。
