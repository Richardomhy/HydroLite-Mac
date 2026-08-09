# 河网水文因果约束

预测目标为节点 `N` 在 `t+h` 的状态时，特征只允许来自：

1. 节点 `N` 在 `issue_time` 及以前的历史；
2. 能沿上游到下游有向路径到达 `N` 的节点；
3. `issue_time` 及以前已知的物理状态、Gamma 特征和外生 forcing。

禁止下游观测反向传播、测试期状态、目标时刻之后的观测和 centered rolling window。循环河网返回 `invalid_hydrologic_cycle`，不会删除边来“修复”。水库是带调蓄状态的拓扑节点，入库和出库关系仍可追溯。

输出 provenance 能回答某个预测使用了哪些上游节点与历史时段。数据驱动残差如后续接入，必须与 physical prediction 分列，并保持 HydroLite 水量账本权威。
