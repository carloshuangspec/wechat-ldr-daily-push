# 异地恋微信每日推送

双城天气 + 当地时间 + 相爱天数 + 见面倒计时 + 一句英文情话，经微信测试号模板消息推送。默认城市是 `Ann Arbor` / `Shanghai`。

当前处于“阶段 C”：两次彼此独立的手动真发（先 SELF/US，再 CN）已有微信 API 接受结果；本人手机已确认收到，女友手机尚未确认。手动任务默认预览；定时 CN 真发代码仅处于准备态，须在两部手机的收件与内容均核对后另行开启。US 自测不会开启给 Carlos 的每日推送。

## 安全运行模式

应用层 `SEND_MODE` 只接受两个值：

- `dry-run`：只打印脱敏预览，不发送；缺失时也是此模式。
- `live`：手动真发必须精确匹配 `LIVE_RECIPIENT=self`、`PUSH_SLOT=us`、
  `LIVE_CONFIRMATION=SEND_SELF_ONCE`，或 `LIVE_RECIPIENT=cn`、`PUSH_SLOT=cn`、
  `LIVE_CONFIRMATION=SEND_CN_ONCE`，并满足受控 GitHub Actions
  `workflow_dispatch` 上下文。独立的 CN 定时真发只接受 `schedule` 事件、
  `GITHUB_EVENT_SCHEDULE=7 8 * * *`、`LIVE_RECIPIENT=cn`、`PUSH_SLOT=cn` 和
  `ENABLE_CN_DAILY=1`；它不读取手动确认短语。两种路径均须匹配 GitHub Actions、
  本仓库 `main` 和首次 run，其他情况在任何天气或发送请求前停止。

这层 `GITHUB_*` 检查用于防误操作，不是不可伪造的远程身份证明；环境变量在
本机仍可人为伪造。因此真实微信凭据只应保存在 GitHub Secrets，不要写入本机
`.env`。阶段 C 没有提供或记录本机真发流程。

旧 `DRY_RUN` 已不参与发送决策；它缺失或为 `0` 都不能触发真实发送。

本地预览不需要任何 API 凭据；未配置 QWeather 时会联网读取 Open-Meteo 的公开天气，网络失败则显示英文降级文案：

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

阶段 C 将预览与真发拆成独立 job：`preview-cn` / `preview-us` 即使启用定时 CN 也始终使用 `SEND_MODE=dry-run`，完全不加载任何 `WECHAT_*`。手动 `live-self` / `live-cn` 只加载各自的收件人 OpenID；另有默认关闭的 `scheduled-cn`，仅在精确的 CN cron 和 `ENABLE_CN_DAILY=1` 时进入。三个真发 job 都只在各自的发送步骤加载对应 OpenID 与共用的三个微信 Secrets，并先运行单元测试。

`SEND_SELF_ONCE` 与 `SEND_CN_ONCE` 是手动测试的意图确认短语，不是真正的一次性令牌；“首次 run”只限制单个 run 的重试，不会阻止创建新的手动 run。API 接受和绿色 job 本身均不等于手机收到；SELF 手机已确认，但仍需 CN 收件人确认收到，并核对消息、换行和天气来源，然后才决定是否开启定时 CN。若发现问题先排查，不自动重发。

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
| `WECHAT_OPENID_SELF` | Actions Secret | Carlos 本人的 US 槽位 openid，仅 `live-self` 读取 |
| `WECHAT_OPENID_CN` | Actions Secret | 女友的 CN 槽位 openid，仅 `live-cn` / `scheduled-cn` 读取 |

可选增强：

| Name | 类型 | 说明 |
|------|------|------|
| `QWEATHER_KEY` | Actions Secret | 可选的 QWeather Key；必须与账号专属 Host 成对配置 |
| `QWEATHER_API_HOST` | Actions Secret | 可选的 QWeather 控制台 `*.qweatherapi.com` 账号专属 API Host |
| `GEMINI_API_KEY` | Actions Secret | 可选，生成英文情话；失败或返回非 ASCII / 超长内容时使用内置英文短句 |
| `GEMINI_MODEL` | Actions Variable | 可选模型 |
| `KNOWN_START_DATE` | Actions Variable | 可选约数起点，默认 `2019-09-02`，不是已核实的相识日 |
| `CITY_A` / `CITY_B` | Actions Variable | 默认 `Ann Arbor` / `Shanghai` |
| `CITY_A_TZ` / `CITY_B_TZ` | Actions Variable | 默认 `America/Detroit` / `Asia/Shanghai` |

CN 每日发送的单独开关 `ENABLE_CN_DAILY` 是 Actions Variable，**不存在或不等于精确的 `1` 时均关闭**，不是 Secret。只有两部手机都确认实际收件、内容无误后，才由 Carlos 明确决定是否在仓库 `Settings → Secrets and variables → Actions → Variables` 中设为 `1`；准备代码和提交本身不应设置它。要关闭 CN 日推，立即在同一位置删除该变量或改成 `0`；已开始的运行无法靠关闭开关撤回，仍需核对运行与手机状态。不要用手动的 `SEND_CN_ONCE` 代替这个开关。

QWeather Key 与 Host 都配置时优先使用 QWeather；任一缺失时使用无需密钥的 [Open-Meteo 免费非商业 API](https://open-meteo.com/en/terms)。默认城市会加国家限制以避免同名地点选错；其他城市可用英文 `City, Country` 缩小搜索范围。Open-Meteo 的[城市定位数据基于 GeoNames](https://open-meteo.com/en/docs/geocoding-api)，天气代码会转换成简短英文并将温度四舍五入，因此消息中的 `adapted` 标明了改动。其数据按 [CC BY 4.0 许可](https://creativecommons.org/licenses/by/4.0/)使用；模板的天气来源字段显示 Open-Meteo 官网、GeoNames、许可链接和改动说明。API 失败只显示英文状态，不会中断整条消息。QWeather Key 只经 `X-QW-Api-Key` 请求头发往校验过的 Host；所有天气请求均拒绝自动重定向。

Gemini 提示词为英文，返回非 ASCII、超长或无效文本时使用内置英文短句；未配置 Key 时直接轮换内置短句。提示词不能百分之百保证语言，例如非英语但仅含 ASCII 字符的短句仍可能通过字符校验。

QWeather 的 `/v7/weather/now` 计划于 **2027-06-01** 停止服务；阶段 C 暂不迁移 v1，后续必须在停服前安排迁移。

## 服务入口

| 服务 | 链接 |
|------|------|
| 微信测试号 | https://mp.weixin.qq.com/debug/cgi-bin/sandbox?t=sandbox/login |
| QWeather | https://www.qweather.com |
| QWeather 开发平台 | https://dev.qweather.com/ |
| Gemini API | https://aistudio.google.com/apikey |

## 微信模板

测试号模板字段必须与下面一致，固定标签请用英文。无需为认识天数添加模板字段：现有 `love_line` 会包含两行英文文本，先是 `Known: ≈N days`，再是情话。`weather_source` 会标明本次选择的天气服务和官网链接：

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
Next meeting: in 95 days
Known: ≈2572 days
Thinking of you
Weather: Open-Meteo https://open-meteo.com | GeoNames | CC BY 4.0 https://creativecommons.org/licenses/by/4.0/ | adapted
```

见面日期有三种英文文案：未来显示 “in N days”，当天显示 “today”，过去显示 “date passed”。CN 槽位按 `CITY_B_TZ` 计算日期，US 槽位按 `CITY_A_TZ` 计算日期。模板更新后需将**新模板的 ID** 保存为 `WECHAT_TEMPLATE_ID`，否则程序仍引用旧模板。

## 定时任务

GitHub Actions schedule 使用 IANA 时区，并避开整点：

| 目标当地时间 | Cron + timezone | Job | 阶段 C 行为 |
|--------------|-----------------|-----|-------------|
| 中国约 08:07 | `7 8 * * *` + `Asia/Shanghai` | `preview-cn` | 始终 dry-run |
| 中国约 08:07 | `7 8 * * *` + `Asia/Shanghai` | `scheduled-cn` | 默认跳过；仅开关为 `1` 且通过事件、仓库、分支与首次运行门禁才真发 CN |
| Detroit 约 08:13 | `13 8 * * *` + `America/Detroit` | `preview-us` | 始终 dry-run，不提供定时 US 真发 |

约 08:07 是配置的上海当地时间，实际 GitHub Actions 启动时间可能延迟；美国时段的 cron 不能触发 CN 真发。

## 项目结构与测试

```text
src/main.py          # fail-closed 模式、数据组装、发送入口
src/weather.py       # QWeather 或无密钥 Open-Meteo 双城天气
src/dates.py         # 相爱天数、见面三态、当地日期时间
src/gemini_line.py   # Gemini 英文情话 + 英文静态回退
src/wechat.py        # 脱敏的 token 与 template/send 调用
tests/               # stdlib unittest
.github/workflows/daily-push.yml
config.example.env
```

运行测试：

```bash
python -m unittest discover -s tests -v
```

Python **3.11+**，依赖：`requests`。
