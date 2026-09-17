# 异地恋微信每日推送

双城天气 + 当地时间 + 相爱天数 + 见面倒计时 + 一句英文情话，经微信测试号模板消息推送。默认城市是 `Ann Arbor` / `Shanghai`。

当前处于“阶段 C”：两次彼此独立的手动真发（先 SELF/US，再 CN）已有微信 API 接受结果；本人手机已确认修复后的英文情话显示，女友手机尚未确认。手动任务默认预览；同一个上海 09:00 定时事件下有两条独立的真发路径。Carlos 本轮明确要求两端同步日推，SELF 与 CN 的每日开关现均已开启；首次定时运行及两部手机的实际内容仍待验收。

## 安全运行模式

应用层 `SEND_MODE` 只接受两个值：

- `dry-run`：只打印脱敏预览，不发送；缺失时也是此模式。
- `live`：手动真发必须精确匹配 `LIVE_RECIPIENT=self`、`PUSH_SLOT=us`、
  `LIVE_CONFIRMATION=SEND_SELF_ONCE`，或 `LIVE_RECIPIENT=cn`、`PUSH_SLOT=cn`、
  `LIVE_CONFIRMATION=SEND_CN_ONCE`，并满足受控 GitHub Actions
  `workflow_dispatch` 上下文。定时真发只接受 `schedule` 事件、
  `GITHUB_EVENT_SCHEDULE=0 9 * * *`，以及对应的 `LIVE_RECIPIENT=cn` / `PUSH_SLOT=cn` /
  `ENABLE_CN_DAILY=1` 或 `LIVE_RECIPIENT=self` / `PUSH_SLOT=us` /
  `ENABLE_SELF_DAILY=1`；它不读取手动确认短语。两种路径均须匹配 GitHub Actions、
  本仓库 `main` 和首次 run，其他情况在任何天气或发送请求前停止。

这层 `GITHUB_*` 检查用于防误操作，不是不可伪造的远程身份证明；环境变量在
本机仍可人为伪造。因此真实微信凭据只应保存在 GitHub Secrets，不要写入本机
`.env`。阶段 C 没有提供或记录本机真发流程。

旧 `DRY_RUN` 已不参与发送决策；它缺失或为 `0` 都不能触发真实发送。

本地预览不会加载微信凭据，但默认短句需要有效 `DEEPSEEK_API_KEY`；缺失或生成失败就整条跳过。CN 当天若有有效的手写 `exact` 可不调用 AI。未配置 QWeather 时会联网读取 Open-Meteo 的公开天气，网络失败则显示英文降级文案。下面仅是运行格式；没有通过安全环境提供 DeepSeek Key（或当天有效 `exact`）时会预期失败，不会发送微信：

```bash
PUSH_SLOT=cn \
SEND_MODE=dry-run \
LOVE_START_DATE=2026-07-08 \
NEXT_MEET_DATE=2026-12-20 \
python src/main.py
```

`KNOWN_START_DATE` 是可选的约数起点，未设置时使用 `2019-09-02`。它不表示已核实的相识日；消息中的 `Known: ≈N days` 与确定的在一起天数分开计算。`NEXT_MEET_DATE=2026-12-20` 是 Carlos 本次确认的下次见面日期，仍按收件人当地日期计算倒计时。

## 阶段 C：GitHub Actions 操作

Carlos 必须本人在仓库 `Settings → Secrets and variables → Actions` 配置真实发送所需值。任何 Secret、Key、OpenID 或 token 都不要粘贴到聊天中。

手动运行 `daily-push` 时：

- 安全预览：选择 `mode=preview`；`slot` 可选 `cn`、`us` 或 `both`，无需 confirmation。
- 本人测试：选择 `mode=live-self`、`slot=us`，并在 confirmation 精确输入 `SEND_SELF_ONCE`。该 job 只能使用 `WECHAT_OPENID_SELF`，不能读取 CN 收件人的 OpenID。
- 女友测试：选择 `mode=live-cn`、`slot=cn`，并在 confirmation 精确输入 `SEND_CN_ONCE`。该 job 只能使用 `WECHAT_OPENID_CN`，不能读取本人的 OpenID。
- 两条真发路径都限制为本仓库 `main` 分支、仓库所有者首次执行的手动 run；对该 run 点 Re-run 会被拒绝。槽位、短语、仓库、分支、触发者或 run attempt 不匹配时，门禁 job 会失败，发送 job 不运行；定时事件也不能进入它们。

阶段 C 将预览与真发拆成独立 job：`preview-cn` / `preview-us` 均使用 `SEND_MODE=dry-run`，完全不加载任何 `WECHAT_*`。每位收件人启用定时真发后，只有其对应的自动预览被跳过；手动预览仍可用。手动 `live-self` / `live-cn` 与定时 `scheduled-self` / `scheduled-cn` 均只加载各自的收件人 OpenID；定时任务分别要求对应的 `ENABLE_SELF_DAILY=1` / `ENABLE_CN_DAILY=1`。四个真发 job 都只在各自的发送步骤加载对应 OpenID 与共用的三个微信 Secrets，并先运行单元测试。

`SEND_SELF_ONCE` 与 `SEND_CN_ONCE` 是手动测试的意图确认短语，不是真正的一次性令牌；“首次 run”只限制单个 run 的重试，不会阻止创建新的手动 run。API 接受和绿色 job 本身均不等于手机收到；SELF 手机已确认先前手动测试，CN 手机与首次定时运行尚未确认。若发现收件人或内容错误，应立即关闭对应的每日开关并排查，不自动重发。

若手机收到了消息却看不到英文情话，先手动运行独立的 `inspect-template` 工作流（无需输入）。它只读取当前 `WECHAT_TEMPLATE_ID` 对应的在线模板，输出 `template_found` 和 `missing_fields`，不加载任何收件 OpenID、也不发送微信。`missing_fields` 含 `love_line` 表示当前在线模板没有 `{{love_line.DATA}}`；若工作流报 `template_check_failed`，则只表示接口检查未完成，不能据此推断模板字段缺失。模板含有字段也不能保证微信客户端卡片将它显示出来。当前观察到的测试号卡片只显示双城天气、Together 和 Next meeting；程序因此将同一句英文情话也附在 Next meeting 行中，仍须在手机上确认最终呈现。不要盲目重发。

## 配置：必填与可选

运行预览所需日期：

| Name | 类型 | 说明 |
|------|------|------|
| `LOVE_START_DATE` | Actions Secret | 在一起日，`YYYY-MM-DD` |
| `NEXT_MEET_DATE` | Actions Secret | 下次见面日，`YYYY-MM-DD` |

仅阶段 C 对应收件人的真发必填（每条 job 只加载各自的 OpenID）：

| Name | 类型 | 说明 |
|------|------|------|
| `WECHAT_APP_ID` | Actions Secret | 微信测试号 appID |
| `WECHAT_APP_SECRET` | Actions Secret | 微信测试号 appsecret |
| `WECHAT_TEMPLATE_ID` | Actions Secret | 模板 ID |
| `WECHAT_OPENID_SELF` | Actions Secret | Carlos 本人的 US 槽位 openid，仅 `live-self` / `scheduled-self` 读取 |
| `WECHAT_OPENID_CN` | Actions Secret | 女友的 CN 槽位 openid，仅 `live-cn` / `scheduled-cn` 读取 |

短句默认运行必填；仅 CN 当天有有效 `exact` 时可跳过 API：

| Name | 类型 | 说明 |
|------|------|------|
| `DEEPSEEK_API_KEY` | Actions Secret | 英文短句由 `deepseek-flash` 生成；失败/无效/缺 Key 均不发送；不会改用 Gemini 或静态短句 |

可选增强与单日编辑：

| Name | 类型 | 说明 |
|------|------|------|
| `QWEATHER_KEY` | Actions Secret | 可选的 QWeather Key；必须与账号专属 Host 成对配置 |
| `QWEATHER_API_HOST` | Actions Secret | 可选的 QWeather 控制台 `*.qweatherapi.com` 账号专属 API Host |
| `DAILY_MESSAGE_CONFIG` | Actions Secret | 仅 CN 当天单日主题或手写英文原句；US/SELF 不加载；不配置则直接调用 DeepSeek |
| `KNOWN_START_DATE` | Actions Variable | 可选约数起点，默认 `2019-09-02`，不是已核实的相识日 |
| `CITY_A` / `CITY_B` | Actions Variable | 默认 `Ann Arbor` / `Shanghai` |
| `CITY_A_TZ` / `CITY_B_TZ` | Actions Variable | 默认 `America/Detroit` / `Asia/Shanghai` |

每日发送使用两个独立的 Actions Variable 开关：`ENABLE_SELF_DAILY` 控制本人、`ENABLE_CN_DAILY` 控制女友；**不存在或不等于精确的 `1` 时均关闭**，不是 Secret。按 Carlos 本轮的双端同步要求，两者现在都设为 `1`；女友手机尚未确认新版本内容，不能把开关已开启视为她已收到。要关闭某人的日推，立即将对应变量改成 `0` 或删除；已开始的运行无法靠关闭开关撤回，仍需核对运行与手机状态。手动确认短语不能代替每日开关。

QWeather Key 与 Host 都配置时优先使用 QWeather；任一缺失时使用无需密钥的 [Open-Meteo 免费非商业 API](https://open-meteo.com/en/terms)。默认城市会加国家限制以避免同名地点选错；其他城市可用英文 `City, Country` 缩小搜索范围。Open-Meteo 的[城市定位数据基于 GeoNames](https://open-meteo.com/en/docs/geocoding-api)，天气代码会转换成简短英文并将温度四舍五入，因此消息中的 `adapted` 标明了改动。其数据按 [CC BY 4.0 许可](https://creativecommons.org/licenses/by/4.0/)使用；模板的天气来源字段显示 Open-Meteo 官网、GeoNames、许可链接和改动说明。API 失败只显示英文状态，不会中断整条消息。QWeather Key 只经 `X-QW-Api-Key` 请求头发往校验过的 Host；所有天气请求均拒绝自动重定向。

每天默认请求 DeepSeek 的 `deepseek-flash` 生成一条不超过 20 个可打印 ASCII 字符的英文短句，正式请求只在 HTTPS 固定端点发送 `Authorization: Bearer`，禁止自动重定向。若仅文案不合格，会在任何微信发送前最多再生成两次；三次仍不合格或接口/鉴权失败则跳过整条，不替换固定句子，**绝不自动重试微信发送**。失败日志只记录固定类别（如 `invalid_text`），不包含响应正文。ASCII 校验不能百分之百判定语义是否英语，故真发前先看预览。真实 Key 只放在 `DEEPSEEK_API_KEY` Actions Secret，不放仓库、本地 `.env`、聊天或日志；Secret 已保存也不代表实际有效。

想调整某个上海日期的内容，可在 Mac 上双击 `scripts/edit-daily-message.command`，填日期（默认上海今天）、可选主题 `theme`、可选手写英文原句 `exact`；至少填一项。`theme` 最多 120 字符，可写中英文，会发给 DeepSeek 引导生成；`exact` 必须为单行 1–20 个可打印 ASCII 字符，优先级高于主题且不请求 AI，原样进入消息。工具本地显示输入供确认后，仅通过标准输入将单个 JSON 对象写入 `DAILY_MESSAGE_CONFIG` Secret，不写入 Git 历史或临时文件。替换时需重新填完整内容，不能从 GitHub Secret 读回；工具可经单独确认删除此 Secret。日期不匹配的旧配置会被忽略，格式无效的配置会让运行安全失败。这个 Secret 仅加载到 CN 的预览和发送 job，SELF/US 不读取。

GitHub 在工作流**排队时**读取仓库 Secret，故要在下一次 run 排队前完成编辑；排队后再更新或删除，不会更改那一次运行。DeepSeek [官方缓存说明](https://api-docs.deepseek.com/guides/kv_cache/)指出输入/输出前缀可能写入缓存，不要在主题中填写未经双方同意的聊天档案、凭据或第三方隐私。`exact` 不送 DeepSeek，但最终微信消息及当前预览日志都会展示它；Secret 的加密不隐藏已渲染的预览内容，仓库日志读取者可见。

先使用 `mode=preview`、`slot=cn`，只检查该 job 的实际 `Preview CN` 步骤：`line_source=deepseek` 说明这一步的 API 结果通过校验；当天手写 `exact` 则为 `line_source=manual`，**不能证明 API 可用**。前面的 `Run tests` 步骤只用模拟响应，不能作为真实生成的证据。预览中的 `deepseek_key_set` 仅说明配置非空，不证明 Key 有效。主题预览和后续真发是两个独立请求，不保证生成同一句；手写原文在同一日期稳定。手动预览 job 始终不加载任何 `WECHAT_*`，不会发送微信消息；即使每日开关已开启，手动预览仍是安全的。

QWeather 的 `/v7/weather/now` 计划于 **2027-06-01** 停止服务；阶段 C 暂不迁移 v1，后续必须在停服前安排迁移。

## 服务入口

| 服务 | 链接 |
|------|------|
| 微信测试号 | https://mp.weixin.qq.com/debug/cgi-bin/sandbox?t=sandbox/login |
| QWeather | https://www.qweather.com |
| QWeather 开发平台 | https://dev.qweather.com/ |
| DeepSeek API | https://platform.deepseek.com/ |

## 微信模板

测试号模板字段必须与下面一致，固定标签请用英文。无需为认识天数添加模板字段：`love_line` 包含两行英文文本，先是情话，再是 `Known: ≈N days`。为适配目前只显示中间四行的测试号卡片，`meet_days` 会显示 `in N days | 英文情话`；独立 `love_line` 字段仍保留。`weather_source` 会标明本次选择的天气服务和官网链接；目前的卡片也可能不显示这一行，仍须核对手机实际呈现：

```text
{{greeting.DATA}}
A: {{city_a.DATA}} {{time_a.DATA}} {{weather_a.DATA}}
B: {{city_b.DATA}} {{time_b.DATA}} {{weather_b.DATA}}
Together: {{love_days.DATA}}
Next meeting: {{meet_days.DATA}}
{{love_line.DATA}}
Weather: {{weather_source.DATA}}
```

示例（日期数值以 2026-09-16 为计算日；天气与时间仅为格式示意）：

```text
Good morning, love!
A: Ann Arbor 20:00 Sunny 12°C
B: Shanghai 08:00 Cloudy 22°C
Together: 71 days
Next meeting: in 95 days | I choose you, always
I choose you, always
Known: ≈2572 days
Weather: Open-Meteo https://open-meteo.com | GeoNames | CC BY 4.0 https://creativecommons.org/licenses/by/4.0/ | adapted
```

见面日期有三种英文文案：未来显示 “in N days”，当天显示 “today”，过去显示 “date passed”。CN 槽位按 `CITY_B_TZ` 计算日期，US 槽位按 `CITY_A_TZ` 计算日期。模板更新后需将**新模板的 ID** 保存为 `WECHAT_TEMPLATE_ID`，否则程序仍引用旧模板。

## 定时任务

GitHub Actions schedule 使用 IANA 时区；每天的唯一触发时间配置为上海 09:00：

| 目标当地时间 | Cron + timezone | Job | 阶段 C 行为 |
|--------------|-----------------|-----|-------------|
| 中国约 09:00 | `0 9 * * *` + `Asia/Shanghai` | `scheduled-self` 或 `preview-us` | `ENABLE_SELF_DAILY=1` 时只给本人真发，否则只预览 |
| 中国约 09:00 | `0 9 * * *` + `Asia/Shanghai` | `scheduled-cn` 或 `preview-cn` | `ENABLE_CN_DAILY=1` 时只给女友真发，否则只预览 |

上海 09:00 在底特律夏令时是前一天 21:00，冬令时是前一天 20:00；无法让两地全年都固定在 09:00 / 21:00。两端分别按各自当地日期计算天数，DeepSeek 独立生成短句（未必相同），仅 CN 使用当天的单日编辑；问候按收件人的当地时间选择。GitHub 定时是云端保存的，不依赖本机开机，但整点触发可能排队、延迟或丢弃；即便事件按时开始，安装依赖和发送也会再耗时。既有两次预览未在声明的当地时间附近启动，原因未定；新时刻须以实际运行记录验收，不能承诺每天手机 09:00 准点收到。

## 项目结构与测试

```text
src/main.py          # fail-closed 模式、数据组装、发送入口
src/weather.py       # QWeather 或无密钥 Open-Meteo 双城天气
src/dates.py         # 相爱天数、见面三态、当地日期时间
src/deepseek_line.py # DeepSeek 英文短句；失败不发
src/wechat.py        # 脱敏的 token 与 template/send 调用
src/daily_content.py # 仅 CN 的日期、主题和手写原句校验
scripts/edit-daily-message.command # 本机单日内容编辑入口
tests/               # stdlib unittest
.github/workflows/daily-push.yml
config.example.env
```

运行测试：

```bash
python -m unittest discover -s tests -v
```

Python **3.11+**，依赖：`requests`。
