# HydroLite 有向河网图特征

M4 将子流域、河段、水库、监测站和出口组织成显式有向图。边方向固定为 `upstream_to_downstream`，用于描述真实水文连通关系，不替代 HydroLite 的 Muskingum 路由和水量账本。

## 数据契约

- 节点类型：`subbasin`、`reach`、`monitoring_station`、`reservoir`、`outlet`、`water_quality_station`。
- 边必须有唯一 ID、源节点、目标节点、边类型和方向。
- 旅行时间优先使用配置值，其次是距离/假定流速，最后才是拓扑步长 fallback。假定值会记录方法和低置信度。
- 必需节点必须能沿有向边到达出口；可选监测站断开时仅告警。

## 特征

图特征只聚合当前节点和真实上游节点，支持求和、平均、面积加权、最大/最小、旅行时间加权和距离衰减。每项特征保留来源节点、来源时间范围、变换、参数、因果性和 feature group。

本阶段不是 GCN/GAT/GNN，也不训练神经网络。synthetic demo 只验证软件接口和因果门禁，不代表真实项目表现。
