# 有证据的个人画像

每条记录含 id、topic、statement、use、scope、status、reviewed_on 和 evidence。statement 描述偏好/事实，use 说明如何影响协作，scope 限定适用范围。

- confirmed：明确用户证据，或至少两条独立用户来源支持的稳定偏好；不能伪造出处。
- historical：有日期和范围的历史背景，不能当实时项目状态。
- candidate：尚未确认、但对协作有用的假设，不作硬约束。
- retired：不再使用。

证据类别为 direct_user、historical_user、user_document、inference。结构检查不会证明来源真实。一次性要求、沉默、点赞和助手自己的重复总结不能确认长期偏好。

补丁示例（下面是合成示范，必须换成当前用户的真实内容）：

```json
{
  "expected_revision": 0,
  "reason": "Synthetic example of an explicit preference",
  "upsert": [{
    "id": "response-style",
    "topic": "Communication",
    "statement": "Synthetic user prefers short answers",
    "use": "Start concise unless the current request asks for detail",
    "scope": "global",
    "status": "confirmed",
    "reviewed_on": "2026-01-01",
    "evidence": [{"kind": "direct_user", "reference": "synthetic-message-1", "summary": "Synthetic example only"}]
  }]
}
```

先读取实际 revision，不照抄 0。初始统一画像在用户自己的私有仓库写入：

```text
python scripts/profile_store.py --store references/profile.json apply --patch /absolute/local/initial-profile.json
python scripts/profile_store.py --store references/profile.json apply --patch /absolute/local/initial-profile.json --write
```

日常仅当用户明确要求即时维护时写本地；周一复盘也可以形成有证据的本地改动：

```text
python scripts/me.py view
python scripts/me.py apply --patch /absolute/local/patch.json
python scripts/me.py apply --patch /absolute/local/patch.json --write
python scripts/me.py validate
```

写入前预览并核查。结构存储有版本校验、写锁、原子替换与历史回退。统一画像不能由普通周报直接修改；用户审核后用单独维护提交整理采纳内容并更新 me.json 版本。多个安装冲突应明确列出，不丢弃另一方记录。

用户明确即时改了长期偏好，可按其授权刷新本机全局区块；周一候选不自动变成统一默认。只保留必要、去敏信息，不保留原始对话或秘密。

遗忘：me.py forget --id RECORD_ID --expected CURRENT_REVISION --write 删除本地及相应历史并产生删除建议，还需检查同义记录、全局区块、备份、outbox 和导出副本。个人仓库 main、旧 PR、Git 历史不自动消失，不能承诺跨所有设备彻底抹除。暂停/撤回授权时立即停止相应新增操作。
