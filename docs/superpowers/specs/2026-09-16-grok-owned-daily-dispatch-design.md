# Grok 接管每日双人推送：设计

日期：2026-09-16。状态：Carlos 已选择方案一；待本人复核本书面规格后实施。

## 目标与边界

由 Grok Bot 的云端 routine 按 `Asia/Shanghai` 每天 09:00 发起一次 GitHub Actions `workflow_dispatch`。GitHub Actions 仍然生成一份当天内容（含同一句英文情话），按现有顺序分别向 CN 和 SELF 的微信测试号 OpenID 发送；WeChat 和 DeepSeek 密钥只留在 GitHub Secrets。Grok 只取得这个私有仓库的 GitHub Actions 触发及查看运行所必需的权限，不取得上述密钥。将独立的只读巡检改为识别 Grok 派发、当天日期和两端结果，用于观察缺发或部分失败，而不是再发一遍。

本次不改消息文案、城市、日期、收件人，也不迁移微信发送脚本到 Grok。不会因为 Actions 接受触发、绿色运行或微信接口接受请求就声称两部手机已收到；首次切换后仍需 Carlos 核对两端实收。

## 职责与消息流

1. Grok 的 routine 在上海 09:00 使用单仓库、`Actions: write` 的细粒度令牌触发 `daily-push.yml`，选择专用 `daily-both` 模式、`slot=both`、`ref=main`，并传入 `delivery_date=YYYY-MM-DD`（上海当天）。指示 routine 只触发一次、不自行重试真发；这只是操作规则，不能代替下述持久防重。它根据运行结果报告，而不是复制微信/API 凭据。
2. 工作流在 `validate-dispatch`、job 条件和 Python 发送门禁三层核对：事件确为 `workflow_dispatch`、专用模式及槽位、仓库和主分支、预期 GitHub 账号身份、首次运行、两个每日开关均为 `1`，并且输入日期等于运行时的上海当天日期。发送前还要重新校验上海日期，禁止跨日排队使标记日期与实际内容日期不一致。旧的 `live-self` / `live-cn` 人工门禁维持不变；`preview` 永远不加载 `WECHAT_*`。
3. 独立的领取 job 不加载微信/DeepSeek Secrets，使用该 job 的短期 `GITHUB_TOKEN`（`contents: write`）原子创建 `refs/tags/ldr-daily-YYYY-MM-DD`，作为当天唯一的自动双人发送尝试标记。GitHub 创建 ref 若报告冲突，必须再读取**准确的同名 ref**：确已存在才安全停止、不再次调用微信；其他权限、校验或网络错误必须失败，不能按“已发送”处理。标记不包含 OpenID、密钥或情话。
4. 只有首次取得标记，后续只读权限的发送 job 才加载 GitHub Secrets，沿用 Python 双人发送路径生成一次内容，依次发送给 CN 和 SELF。日志只记录脱敏状态、日期、运行链接和哪个接收步骤成功或失败，不回显密钥或 OpenID。

标记意味着“当天已开始自动双人真发尝试”，**不意味着两端都收到了**。发送前后遇到失败、仅一人成功或运行超时，均不自动删除标记、不自动补发；只报警并由 Carlos 看运行记录和手机，再人工决定如何恢复。这样避免自动重试导致已经收到的一方重复收到。同一上海自然日第二次**自动双人派发**（包括手动再点、routine 重试及 Re-run）不得再次发送；保留的单人 `live-self` / `live-cn` 是另外的人工测试门禁，不属于这个防重保证。

## 安全切换顺序

1. 先实现三层门禁、每日标记和离线测试；在原有 GitHub 09:00 定时尚开启时部署代码，但先不启用 Grok 的每日真发 routine。迁移期原有 `scheduled-both` 也必须走**同一个**每日标记，防止试运行派发与原定时各发一次。对 `preview/slot=both` 做一次不加载微信凭据的远端预览，确认仍生成同一份内容。
2. Carlos 在 GitHub 建立只授予 `carloshuangspec/wechat-ldr-daily-push` 的新细粒度 PAT，仓库权限 `Actions: write`（Metadata 只读为 GitHub 默认要求）；通过 Grok 的安全输入框授权给 Build，不把值贴聊天、不让 Codex 查看或存盘。现有只读 PAT 可继续用于巡检。先证实 Build 能以该令牌触发**预览**并读取该次运行结果；失败则不切换原有定时。
3. 确认预览成功后，从仓库工作流中删除旧的 `schedule` 入口及只为 schedule 服务的 jobs，再验证远端工作流仍可 `workflow_dispatch`。检查**当天以及排队中/运行中**的旧 SHA `schedule` 运行，待它们全部结束；如果当天旧版已发过，等到下一上海自然日再启用 Grok 的 09:00 `daily-both` routine。旧 cron 移除与新 routine 启用之间不得同时有两个自动真发源，也不得有旧版运行仍可能在后台发送。
4. 首次真实的 Grok 定时运行后检查 Actions 完整运行及两部手机。若未收到、部分成功或 Grok 没触发，只报警，不通过另一路自动补发；问题查清后单独决定人工恢复。时间是目标而非秒级保证，云端 routine、GitHub 排队及微信平台都可能延迟。

## 权限与风险

`Actions: write` 是 GitHub 创建 workflow dispatch 所需的仓库级权限，并非“只能触发这一个工作流”的按钮；同一令牌也具有其他 Actions 写操作能力。应限制为此仓库、设置有效期并仅交给 Grok 安全凭据界面。Grok 各 Bot 可能共用云电脑与命令行凭据，不能以 Build 名称当作密钥隔离保证。双人微信与 DeepSeek Secrets 仍留 GitHub，运行中不把它们传给 Grok。

在 GitHub 的**独立领取 job** 内给短期 `GITHUB_TOKEN` 增加 `contents: write`，其余 jobs 继续 `contents: read`，所有 checkout 继续 `persist-credentials: false`。该权限本身也能修改仓库内容，并非只能建标记；只有领取 job 使用它，且该 job 不加载发送密钥。每日标记会使私有仓库出现按日期的轻量 Git ref。任何删除标记、补发或撤销标记后的再试，均需单独核对收件情况，不属于自动 routine。

## 验证与完成标准

- 离线测试：拒绝错模式、错槽位、错仓库/分支/身份、重跑、关闭任一开关、日期不匹配；预览无微信凭据；同日重复标记、API 错误、第二位发送失败均不造成自动重发；原有单人手动测试门禁不回归。
- 远端预览：Build 用新令牌触发 `preview/slot=both`，观察运行成功与共用内容；预览只说明组装完成，不表示微信已发送。
- 切换审计：远端 `main` 的旧 `schedule` 已移除，旧版排队/运行中的定时任务已结束，Grok routine 在 `Asia/Shanghai` 09:00 启用，Build 能看到触发的运行链接；09:20 巡检已从查 `schedule/scheduled-both` 改为查 Grok `workflow_dispatch/daily-both`、当天标记和两端结果，且其只读凭据仍可用。
- 首次真发：一个上海日期只出现一个有效标记和一份共用内容；运行结果表明两个独立发送步骤成功，Carlos 再确认两端手机都收到相同内容。只有这四点合在一起，才宣布交接完成。
