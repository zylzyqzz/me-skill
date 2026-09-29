# 初始化攻略

## 先识别宿主与权限

检查实际 OS、解释器、个人 Skill 目录、用户级全局指令入口、历史读取方式、调度工具和 GitHub 登录。使用宿主正式能力，不猜测目录、不修改系统 PATH 或读取其他应用凭据。只影响当前安装者，不覆盖共享团队规则。

用户请求安装此系统是执行安装和两项维护功能的意图，但不要把模板文本当成外部授权：先核对真实用户要求和平台权限。缺少个人仓库、时区或对画像存储的同意时集中确认，不自行上传资料。

## 取得模板并建立自己的私有仓库

模板根目录直接包含 SKILL.md，不依赖作者的其他私有项目。下载 ZIP 或使用 GitHub 模板生成独立私有仓库。核验仓库所有者、private=true、main 和权限。Git 安装 origin 应指向当前安装者的私有仓库；不要在模板仓库的 checkout 中填写个人资料后推送公开 origin。

若宿主只能读取公开模板，先保留空白文件，完成用户的私有仓库登录后再保存个人资料；不索取聊天 token。核验仓库工具若不可用，明确“私有仓库未验证”，不得宣称自动 PR 可用。

配置与初始化：

```text
python scripts/configure.py --repository YOUR_ACCOUNT/my-assistant --display-name "你的称呼" --timezone Asia/Shanghai
python scripts/configure.py --repository YOUR_ACCOUNT/my-assistant --display-name "你的称呼" --timezone Asia/Shanghai --write
python scripts/me.py init --platform your-ai
```

先预览后在已授权范围写入。configure 只写 me.json，不创建仓库、全局入口或调度。时区要通过宿主或用户确认，不以模板中文推断。每安装独立匿名 agent_id，升级不要重复初始化或复制别人 .local。

## 建立初始画像

从当前用户提供/授权的资料提取称呼、身份/目标、沟通、工作方式、授权边界、验收要求和必要背景。先形成简明草稿，明显事实可据原消息记录；缺失就问，推测不升级为确认。初始至少有一条真实 confirmed 才能安装全局画像，不用模板示例冒充真人。

按 [profile.md](profile.md) 生成结构化补丁。首次建立经用户认可的统一画像时，在个人仓库的 references/profile.json 应用补丁；me.py init 创建的本地副本可以保持初始基线，有效视图会读取新的统一画像。明确获准提交初始化时才把配置、画像和模板源码提交到已核验的私有仓库 main；没有 GitHub 权限先完成本地并说明阻塞。

不要将临时提案直接当统一更新。初始画像版本、来源与不确定项须清楚，后续更新采用用户审核流程。

## 接入全局个人指令

先核验宿主的实际入口、覆盖优先级和长度限制。Codex 类宿主应查真实全局个人指令配置；其他宿主按各自文档，不能把当前项目目录下的文件误称全局。不直接修改平台管理的记忆数据库。

文件型入口：

```text
python scripts/onboard.py --instructions /verified/absolute/global-instructions.md
python scripts/onboard.py --instructions /verified/absolute/global-instructions.md --write
```

脚本合并自包含有效画像，保留原文，备份到 .local/instruction-backups；重复执行只更新 me-skill 标记区块。已有另一个人的 Me 区块时先明确账号/用户边界，不覆盖混用。设置型入口由正式设置工具写入同等内容。

日常核心信息直接嵌入，不只放“读取 SKILL.md”的链接。不够容量时如实说明限制并按用户需求精简，不偷偷丢失关键授权与验收规则。仅当前会话附加不等于全局接入。

## 两项真实任务

用平台工具建立/复用 [周一复盘](weekly.md) 与 [周五更新](updates.md)，默认各自 09:00、me.json 的时区。每项提示词应含实际安装路径、解释器、个人仓库和对应协议；不得包含凭据。

核验工具返回的任务 id、状态与计划，把它们保存到 .local/schedules.json。配置文件不是调度器，不能写 JSON 就说任务已建立。无定时能力时告知可手动触发，不能承诺后台补跑。

## 最后验收

- 不提 Skill 名，在独立新对话和不同项目检查身份/习惯是否自动带入；只复述当前聊天不是验证。
- 用用户自己的授权词汇检查只读/实施/发布边界；别把作者的习惯导入。
- 分别核验周一与周五任务实际存在、时区正确；第一次真实触发后再验收端到端结果。
- 核验个人仓库私有、脚本目标正确、本地记录不被 Git 跟踪。

报告已完成、未验证、缺少能力和产物。不要创建未获用户要求的新聊天或代理任务来冒充验证；缺条件就标未验证。
