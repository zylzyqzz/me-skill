# 周一：触发后回顾最近 7 天

安装时在当前用户授权范围建立独立的周一 09:00 任务，按 me.json 的实际时区。提示词要包含本协议的完整顺序、实际安装路径与解释器。不要只设置“每周提交 PR”而遗漏收集步骤。

1. 触发后读取当前用户限制与 me.json；用户暂停则停止。保留当前安装身份。运行 `python scripts/me.py review-plan`，固定最近 7 天的带时区窗口。本周已成功提交则结束。即使 pending_count=0，也应按 review_due 回顾历史。
2. 此时才用本 AI 宿主的授权会话接口读取窗口内真实用户消息。列表可用于定位，助手总结、标题与工具输出不能冒充用户证据。只读本用户、本 AI 的可访问记录，不读取其他产品、凭据或无关业务文件。不长期复制原始聊天。
3. 汇总主要活动、使用方式、明确纠正、持续习惯及未确定倾向。注明覆盖的来源、会话数和限制；partial 不冒称完整，unavailable 不冒称用户没使用。
4. 对照画像，仅真实长期变更才按 profile.md 更新本地。一次性需求不升级；未被本周证据支持的旧积压不顺带上传。参照 [review-format.md](review-format.md) 写 .local/weekly-review.json，activities/habits 引用证据，profile_evidence 只列本次支持的变更 id。
5. 执行 `python scripts/me.py prepare --review /absolute/local/weekly-review.json`。准备不联网；脚本检查 7 天窗口、来源引用、配置和基础敏感信息。语义去敏与真假仍由执行代理负责。
6. 审查 outbox 的 JSON 与 Markdown 正文。只含最小去敏摘要、来源、范围与建议，不上传原始聊天、客户资料、联系方式、账户财务、生产地址或凭据。
7. 使用当前宿主的既有认证，执行 `python scripts/submit_pr.py --bundle /absolute/local/outbox/BUNDLE.json` 只读预检；目标和内容确认后加 --write。必须是 me.json 指定的个人私有仓库且有权限。脚本禁止把个人内容提交到公共模板，其他公开仓库也会在写入前被拒绝。
8. 固定 `me/<agent_id>/<UTC-ISO-week>` 分支，PR 只含 `proposals/<week>/<agent_id>.json`。核验 base/head/文件及远端内容，成功后登记 receipt。失败沿同一分支重试；已关闭、合并、夹带其他修改时先核对，不重复创建。不自动合并、不改 main。

每安装每 UTC ISO 周最多一份，宿主调度时间仍使用用户时区。首次安装不要伪造过往记录。有真实活动但没新偏好可提纯使用汇总，observations=[]。无活动且已完整检查则安静结束；历史无法读取或部分为空时报告准确限制。

通知仅用于成功、失败或需要用户处理的事项；无变化不反复打扰。用户审核各 AI 建议后，整理统一画像与个人版本，再由周五同步。周一任务不自动升级程序，也不把其他 AI 的历史混进本安装复盘。
