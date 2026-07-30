# 多事件洪水回放验证

历史回放（hindcast）使用完整已发生事件检验模型；forecast 只可使用预报时刻已知信息。流程为观测 QC、事件目录、测站映射、按时间划分、率定事件参数搜索、独立验证/测试、多事件指标和最差事件审查。

合成 Demo 仅验证软件链路，不能形成真实适用性结论。真实等级按合格事件和独立划分提升，少量事件不得声称 `operational`。

```bash
python -m hydrolite hindcast readiness <workspace>
python -m hydrolite hindcast run-batch <project>
python -m hydrolite hindcast summarize output/hindcast_validation
```
