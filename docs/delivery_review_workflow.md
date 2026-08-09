# Delivery Review Workflow

M7B1 提供本地逻辑审核，不提供账号认证、法律电子签名或云端协作。

## States

`draft -> submitted_for_review -> reviewed -> approved_for_delivery`

可从提交或复核阶段进入 `changes_requested` 后修订并重新提交；也可 `rejected`。已批准交付物可 `superseded`，最终可 `archived`。

角色仅用于本地流程门禁：analyst 可 prepare/submit；technical_reviewer 可 review/request changes；project_manager 可 approve/reject/supersede；viewer 只读。

每个动作必须有 comment，并写入 ReviewRecord 和 Audit Event。`reviewer_name` 是人工输入，不是 authenticated digital signature。

## Approval gate

批准前必须存在 Project Version、Data Snapshot、Configuration Snapshot、完成且已版本化的 Run、有效成果 hash、报告、科学验证等级、限制、审核记录和关键警告确认。缺一即 blocked。

关键 warning 必须逐项确认，不能“一键忽略全部”。Acknowledged 只说明 reviewer 已理解影响，不代表问题已解决。

```bash
python -m hydrolite delivery submit <deliverable_id> --comment "submit"
python -m hydrolite delivery review <deliverable_id> --comment "technical review"
python -m hydrolite delivery acknowledge-warning <deliverable_id> <warning_code> --comment "reviewed"
python -m hydrolite delivery approve <deliverable_id> --comment "approved for delivery"
```
