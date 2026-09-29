# 周复盘输入格式（schema 2 的 review）

所有时间使用带时区 ISO 8601。先调用 review-plan 得到准确窗口；下列仅为**合成演示，不得作为真实周报上传**。sources 是已读取的、不敏感的来源标识；evidence.at 是原始事件时间，不是助手总结时间。

```json
{
  "period_start": "2026-09-21T09:00:00+00:00",
  "period_end": "2026-09-28T09:00:00+00:00",
  "coverage": {
    "status": "partial",
    "sources": ["synthetic-session-a"],
    "sessions_reviewed": 1,
    "limitations": ["合成示例：仅一个会话，不代表完整历史"]
  },
  "evidence": [{"id": "e1", "at": "2026-09-27T10:00:00+00:00", "source": "synthetic-session-a", "summary": "合成示例：用户要求先检查问题再实施"}],
  "activities": [{"summary": "合成示例：本周进行一次故障检查", "evidence_ids": ["e1"]}],
  "habits": [{"summary": "合成示例：仍按检查阶段控制实施范围", "assessment": "unchanged", "evidence_ids": ["e1"]}],
  "profile_evidence": {}
}
```

coverage.status：complete 仅表示已完整覆盖本 AI 声明的可访问来源；partial 必须写限制；unavailable 必须写原因且 evidence 为空、sessions_reviewed=0。不能把其他 AI 的使用包含在 complete 中。

activities 与 habits 的每项都引用真实 evidence_ids。habits.assessment 只允许 confirmed/candidate/unchanged，结构通过不等于已证明稳定习惯。证据必须在窗口内、引用存在，原话真伪仍由执行代理核实。

profile_evidence 是“本地待提交画像 id → 本周证据 id 数组”。例如 {"weekly-format":["e1"]} 仅在本周证据确实支持该改动且已 apply 到本地时使用。不改画像就保持 {}。PR 中 observations 仅选这些记录，不自动打包全部旧积压。

输出 bundle 的 schema_version 为 2，保留原 repository/week/agent_id/platform/baseline_version/canonical_hash/observations 字段并增加 review。schema 1 只兼容历史读取。无实际活动不创建空提案；不可读取历史单独返回 history-unavailable。
