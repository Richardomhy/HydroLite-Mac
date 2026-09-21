# M9A.2 点源证据闭环

只处理点源身份、坐标、证据匹配、源端负荷与人工系数决策。不计算污染物动员、输移或入河负荷；`water_quality` 仍为 `planned`。

## 操作顺序

```bash
python -m hydrolite water-environment evidence-refresh --source-root <只读资料目录>
python -m hydrolite water-environment point-source-status
python -m hydrolite water-environment point-source-map
python -m hydrolite water-environment point-source-load
python -m hydrolite water-environment data-request
```

默认读取既有 M9A/M9A.1 冻结资料，在 `output/water_environment/m9a2/` 写入新的工作成果，不重跑水文、不更改旧证据。

## 六张业务模板

生成的 `requests/m9a2_point_source_data_template.xlsx` 含排口基础信息、排放水量、污染物监测、受纳水体、污水处理设施、系数审批。模板没有伪造示例数据。

字段使用稳定的英文键；Source ID 需对应已有清单。实际流量填 `measured_flow` 或 `reported_actual_flow`，设计能力填 `design_capacity`，许可能力填 `permitted_capacity`，估算填 `estimated_flow`。流量单位支持 m3/s、m3/day，时段体积使用 m3 和明确起止时刻。监测角色填写 `outfall_effluent`、`wwtp_effluent`、`wwtp_influent` 或 `river_water`。报送源负荷须填写 `reporting_authority`、`load_scope=source_emission` 及明确时段。COD/CODCr 不能当成 CODMn。

```bash
python -m hydrolite water-environment evidence-refresh --template <已填工作簿>
python -m hydrolite water-environment evidence-review --output-dir output/water_environment/m9a2 --object-id <证据ID> --action confirm --actor <审核人> --comment <依据>
python -m hydrolite water-environment factor-set --output-dir output/water_environment/m9a2 --object-id <系数ID> --action approved_for_project --actor <负责人> --comment <适用依据>
python -m hydrolite water-environment point-source-status
```

导入产生候选，不批准证据或系数。系数审批表导入仅形成提议；必须经过明确的单条项目操作。新增、变更文件按 checksum 识别，未变更文件不重复解析；旧版证据保留为 superseded，源文件丢失标记 external_evidence_missing。可以不传 source-root，仅处理补充模板，不再扫描原目录。

## 空间确认

坐标范围不证明 CRS。自动确认只接受明确 CRS 的原始点图层、唯一 Source ID/名称匹配及实际 geometry 来源。手工确认需原始坐标依据；禁止仅填写一个 EPSG 号就声称事实已核验。

正式河段继续使用 M8B 对应表 `configs/m9a1/reach_crosswalk.csv`。没有计算 reach_id 的调查河线只能作候选。项目水体别名与阈值可放在工作区 `configs/m9a2/point_source.yaml`，键为 `waterbody_aliases` 和 `thresholds`；别名不写入通用代码。

接收水体名称匹配必须与空间一致。未知 CRS、纯最近距离不自动高可信；图层 CRS 未确认时 GeoJSON 不发布假定的 WGS84 点几何。坐标原值和候选距离保留在审核表。

## 负荷与门禁

只连接同源、实际水量与出口浓度。exact/same_day 可以形成观测排放率，same_period 只记录待审，不把部分时间重叠视为代表整个时期。瞬时排放率不证明连续排放。设计能力、河水浓度、无语义报送值不能参与源端计算。

实测和报送记录并列保留，时段不同不强比；同段相对差异超过 20% 标记 material_disagreement，阻止静默选择。该阈值仅为审计提示，不是科学一致性验证。多条观测不自动平均，须明确核算期。

正式点源资格要求同一组源同时具备完整污染物负荷和可信空间关系，不分别凑覆盖率。源量化、空间及各点源类别覆盖默认 80%，不得降低 M9A 基线。无重要性数据时显示 `importance_weighted_coverage=unavailable`；有权重时同时检查加权覆盖。

`point_source_m9b_eligibility` 与总体门禁分开；面源保持 blocked，点源结果不能代表全流域。缺失保持 NA。

## 版本与审计

新的身份、坐标、决策包和门禁结果可形成新 snapshot，显式 `point-source-status --finalize` 建立 Version 5，父版本为 Version 4。归档复用项目版本、血缘、成果中心、技术审核与完整性检查；仍有 P0 时仅 reviewed，不 approved_for_delivery。冻结目录拒绝改写；后续修订指定新 `--output-dir`，不覆盖旧成果。

真实填报、坐标、浓度、运行数据和项目决定仅留在外部工作区与 ignored output，不能提交到 Git。软件测试只用匿名数据。
