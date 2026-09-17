# M9A.1 污染源证据闭环

本阶段只核算源端产生、削减和净排放证据。不执行污染物动员、输移、入河负荷、浓度模拟或源解析。`water_quality` 保持 `planned`。

## 使用

```bash
python -m hydrolite water-environment evidence --source-root <外部真实资料目录>
python -m hydrolite water-environment evidence-review
python -m hydrolite water-environment factor-candidates
python -m hydrolite water-environment factor-set
python -m hydrolite water-environment spatial-map
python -m hydrolite water-environment readiness
```

首次扫描使用 M9A 原有 Source ID。只查看相关格式、文件名和表头，跳过模型 TxtInOut、重复文件和超限文件；PDF 不做 OCR。读取失败会保留文件名和错误原因。所有检索结果先成为候选；精确源标识、明确采样时间及单位的数值浓度可按显式规则确认提取，但不自动证明连续排放或监测合规。

## 审核

```bash
python -m hydrolite water-environment evidence-review --object-id <evidence_id> --action confirm --actor <审核人> --comment <依据>
python -m hydrolite water-environment factor-set --object-id <factor_id> --action approved_for_project --actor <批准人> --comment <适用性依据>
```

证据还可 `reject`、`keep_unresolved`；系数可 `reviewed`、`rejected`、`superseded`。UI 为逐项审核，不提供全部批准。身份、单位或时段缺失时确认被阻止，不能用一句审批意见补造数据。审核使用既有 runtime audit events，并使产物标记为过期。重新运行 readiness 才更新工作账本。

示例系数不得批准；官方来源也必须经过项目决定。系数指纹变化使旧批准失效。多个同类型同污染物系数不自动平均或任选一个，须解决适用性冲突。公开候选原始单位为 g/person/day，转换为 kg/day/person；COD 不能代替 CODMn。鄂州地方表与国家手册对应值并非独立观测。

## 空间与负荷

复用 M8B 已处理空间图层，不重新生成河网。经纬度格式不等于已知坐标基准。未有坐标证据时保持低可信。最近河线记录距离，但不会凭距离给出高可信；实测河线没有正式计算 reach_id 时仅记录 candidate_river_line。

可提供工作区 `configs/m9a1/reach_crosswalk.csv`，字段 `name,reach_id,evidence,approved`。目标 ID 必须存在于 M8B reaches，名称必须唯一，证据和批准均必填；不把所有源自动分配给聚合出口。`review_state.json` 的 spatial 字段保留坐标来源说明，真实配置不得提交版本库。

同源、同时段、同时间基础的出口流量和浓度优先形成实测源端排放率。出水实测值不反推产生量或削减量，二者保持 NA。直接报送负荷必须注明报告机构和 source_emission 语义。设计能力不当作实际流量。多条相冲突活动记录保留待解，不采用最后一行覆盖。

## 门禁与交付

维持 M9A 的源量化、子流域和可信河段覆盖 80% 阈值，低可信归属仍阻断。不完整类别不能外推全流域总量。点源和面源门禁分别报告，overall 必须两者可用；未来仅点源阶段需另行明确范围。水文 `ready_with_warnings` 及真实诊断限制继续保留。

`readiness --finalize` 仅在 Version 3 为当前父版本时冻结一次 Version 4，保存证据、活动、审批集合、映射、缺口和就绪度，登记成果与技术审核。技术审核不等于独立科学验证或用户项目系数批准。冻结产物不可原地重算；后续审核变更应使用新输出目录和新版本。

默认输出 `output/water_environment/m9a1/`，M9A 成果不覆盖。缺失结果以状态/缺口表表示，负荷不是 0。补资料清单按 P0/P1 分类提供字段、单位、时间/空间范围、替代证据和示例格式。

## 官方候选来源

- [生态环境部发布公告](https://www.mee.gov.cn/xxgk2018/xxgk/xxgk01/202106/t20210618_839512.html)
- [生活污染源系数手册，PDF 第 19 页](https://www.mee.gov.cn/uplodfile/附3生活源-附表%20生活源产排污系数手册.pdf)
- [鄂州市农村生活污水治理专项规划，表 3.2-1](https://sthjj.ezhou.gov.cn/xxgk/fdzdgknr/hbgh/202111/t20211123_442998.html)

仓库仅保留少量系数事实、书目及适用性说明，不保存标准全文、真实源表、位置、审批成果或项目报告。
