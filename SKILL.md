---
name: me-skill
description: Build the current user's personal assistant from an empty, evidence-based profile. Use for first-time setup, user-wide instruction onboarding, explicit profile maintenance, Monday retrospective PRs, and Friday updates from the user's own private repository. Configure the owner and timezone before writing personal data. Never send personal profiles to the public template or claim unsupported global memory and scheduling.
---

# Me Skill：我的分身

这是空白的个人助理系统，不是作者的画像。安装后由当前用户的真实资料形成自己的默认协作方式。三个交付：用户级全局画像、周一复盘 PR、周五同步审核后的个人版本。

## 首次安装

按 [setup.md](references/setup.md) 完成，不止复制文件：

1. 识别实际宿主、工具、现有个人指令与任务；不为初始化扫描无关项目。使用当前用户的资料，未知内容保持未知。
2. 集中询问缺少的称呼、主要目标、工作/沟通习惯、授权与验收偏好、时区及自己的私有仓库。已有信息不要重复问。模板语言不是用户的默认语言。
3. 仓库模板仅提供程序。先创建/核验当前用户自己的私有仓库，再配置 `me.json`；不要把公开模板设为个人仓库或在它的 PR/Issue 上传画像。现有登录即可，不索取聊天中的 token。
4. 用真实证据建立初始画像，并交用户核对关键事实和边界。confirmed/historical/candidate 分开，不编造能力分数、人格标签或项目现状。
5. 使用当前宿主正式支持的用户级全局个人指令入口，把自包含画像接入其中。`onboard.py` 保留原内容，只更新自己的标记块。仅当前聊天或项目级生效不算全局接入。
6. 通过正式调度工具建立或复用两项独立任务，默认周一/周五 09:00，使用用户确认的时区。记录平台返回的 id 与实际状态。无调度或全局配置能力时准确报告缺口。
7. 核验新对话和不同项目能否默认带入；不能启动独立验证时标明未验证。安装完成后日常不要求用户再次手动调用 Skill。

脚本需要已核验的 Python 3.10+，只有标准库依赖。仓库根目录就是 `me-skill` 的安装内容。示例中的路径、平台与仓库必须替换成实际值。

## 日常协作与显式维护

日常按常驻画像和当前指令工作，未覆盖的地方用专业判断补位。画像不新增业务权限，不替代事实核查。用户当下纠正立即服从；“这次”不自动升级为长期习惯。

日常不为周报逐轮收集日志、扫描会话或修改画像。用户明确要求记住/更改/遗忘时按 [profile.md](references/profile.md) 维护；否则周一触发后再复盘。

画像是有来源的统一理解，不是全部私人信息，不等于所有对话实时互通。跨设备、其他产品与已有对话的刷新依宿主能力；不能承诺无条件全局记忆。

## 周一：触发后复盘

按 [weekly.md](references/weekly.md)，任务触发后才读取本 AI 有权访问的最近 7 天用户记录，汇总活动与习惯，再去敏提出 PR。每安装有独立稳定身份，每 UTC ISO 周最多一份。纯使用汇总可以没有画像变更；没有活动不造空 PR，读不到记录不等于用户没使用。

周报只写个人私有仓库 `proposals/`，验证远端后才登记成功；用户负责汇总、更新统一画像并合并。普通周报不得直接修改主分支、脚本或规则。

## 周五：自动同步个人版本

按 [updates.md](references/updates.md)，从 `me.json` 指定的个人私有仓库 main 获取已审核更新，验证、备份、安装，再刷新同一全局入口。无更新安静结束；失败保留现状或安全回退。不覆盖用户改动、不降级、不自动合并 PR。

公开模板 main 是框架来源，个人私有仓库 main 是用户画像的统一来源。不能混淆两者。框架升级需要在个人仓库中审查兼容性，不能把个人配置和画像替换成模板空白值。

## 验收与汇报

分别说明：画像来源、个人仓库隐私、全局指令入口、新会话/跨项目验证、周一任务、周五任务、GitHub 权限。运行 `python -m unittest discover -s tests` 和 `python scripts/validate_package.py`。只有纯空白公开模板发布时才加 `--template`。

不上传凭据、联系方式、客户数据、财务账户、生产地址或原始聊天。用户撤回记录/提交/升级授权或暂停时按其要求停止对应动作。保留本地 `.local/`，不复制给另一安装或提交到任何仓库。
