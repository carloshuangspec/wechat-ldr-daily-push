# 异地恋微信每日推送

双城天气 + 当地时间 + 相爱天数 + 见面倒计时 + 一句中文情话，经微信测试号模板消息推送。默认城市是 `Ann Arbor` / `Shanghai`。

当前处于“阶段 C”：只准备一次受控 CN 真发。所有定时任务、所有 US 任务和默认手动任务都只预览；一次 CN 成功后，再由 Carlos 决定是否配置双端发送。

## 安全运行模式

应用层 `SEND_MODE` 只接受两个值：

- `dry-run`：只打印脱敏预览，不发送；缺失时也是此模式。
- `live`：仅允许 `PUSH_SLOT=cn`，且必须同时设置精确确认短语
  `LIVE_CONFIRMATION=SEND_CN_ONCE`。阶段 C 还要求受控 GitHub Actions
  `workflow_dispatch` 上下文；普通本机运行会安全停止。其他槽位、缺确认或
  未知值都会在任何外部请求前安全停止。

这层 `GITHUB_*` 检查用于防误操作，不是不可伪造的远程身份证明；环境变量在
本机仍可人为伪造。因此真实微信凭据只应保存在 GitHub Secrets，不要写入本机
`.env`。阶段 C 没有提供或记录本机真发流程。

旧 `DRY_RUN` 已不参与发送决策；它缺失或为 `0` 都不能触发真实发送。

本地离线预览不需要任何 API 凭据：

```bash
PUSH_SLOT=cn \
SEND_MODE=dry-run \
LOVE_START_DATE=2024-01-01 \
NEXT_MEET_DATE=2026-12-25 \
python src/main.py
```

## 阶段 C：GitHub Actions 操作

Carlos 必须本人在仓库 `Settings → Secrets and variables → Actions` 配置真实发送所需值。任何 Secret、Key、OpenID 或 token 都不要粘贴到聊天中。

手动运行 `daily-push` 时：

- 安全预览：选择 `mode=preview`；`slot` 可选 `cn`、`us` 或 `both`，无需 confirmation。
- 唯一真发路径：同时选择 `mode=live-cn`、`slot=cn`，并在 confirmation 精确输入 `SEND_CN_ONCE`。
- `live-cn` 还被限制在本仓库 `main` 分支、仓库所有者首次执行的 run；对该 run 点 Re-run 会被拒绝。
- `live-cn` 的槽位、确认短语、分支、触发者或 run attempt 不匹配时，门禁 job 会失败，发送 job 不运行。

阶段 C 将预览与真发拆成独立 job：两个预览 job 和所有 schedule 永远使用 `SEND_MODE=dry-run`，并且完全不加载任何 `WECHAT_*`；只有唯一的 `live-cn` job 会把已验证的手动选择映射为 `SEND_MODE=live`，其最后一步才可以读取 CN 真发所需的四个微信 Secrets。工作流会在加载这些 Secrets 前先安装依赖并运行单元测试。

`SEND_CN_ONCE` 是意图确认短语，不是真正的一次性令牌。不要连续创建多个新的 `live-cn` run；第一次手机确认收到后，应先关闭临时真发入口，再决定下一阶段。

## 配置：必填与可选

运行预览所需日期：

| Name | 类型 | 说明 |
|------|------|------|
| `LOVE_START_DATE` | Actions Secret | 在一起日，`YYYY-MM-DD` |
| `NEXT_MEET_DATE` | Actions Secret | 下次见面日，`YYYY-MM-DD` |

仅阶段 C 的 CN 真发必填：

| Name | 类型 | 说明 |
|------|------|------|
| `WECHAT_APP_ID` | Actions Secret | 微信测试号 appID |
| `WECHAT_APP_SECRET` | Actions Secret | 微信测试号 appsecret |
| `WECHAT_TEMPLATE_ID` | Actions Secret | 模板 ID |
| `WECHAT_OPENID_CN` | Actions Secret | CN 槽位接收方 openid |

可选增强：

| Name | 类型 | 说明 |
|------|------|------|
| `QWEATHER_KEY` | Actions Secret | QWeather Key；必须与账号专属 Host 成对配置 |
| `QWEATHER_API_HOST` | Actions Secret | QWeather 控制台给出的 `*.qweatherapi.com` 账号专属 API Host；无默认公共 Host |
| `GEMINI_API_KEY` | Actions Secret | Gemini Key；缺失或失败时使用内置短句 |
| `GEMINI_MODEL` | Actions Variable | 可选模型 |
| `CITY_A` / `CITY_B` | Actions Variable | 默认 `Ann Arbor` / `Shanghai` |
| `CITY_A_TZ` / `CITY_B_TZ` | Actions Variable | 默认 `America/Detroit` / `Asia/Shanghai` |

QWeather Key 与 Host 任一缺失时，天气会安全降级为不含配置值的状态文案；API 失败也不会中断整条消息。Key 通过 `X-QW-Api-Key` 请求头发送，不放在 query 中。

QWeather 的 `/v7/weather/now` 计划于 **2027-06-01** 停止服务；阶段 C 暂不迁移 v1，后续必须在停服前安排迁移。

## 服务入口

| 服务 | 链接 |
|------|------|
| 微信测试号 | https://mp.weixin.qq.com/debug/cgi-bin/sandbox?t=sandbox/login |
| QWeather | https://www.qweather.com |
| QWeather 开发平台 | https://dev.qweather.com/ |
| Gemini API | https://aistudio.google.com/apikey |

## 微信模板

测试号模板字段必须与下面一致。`weather_source` 用于显示 QWeather 名称与官网链接：

```text
{{greeting.DATA}}
A：{{city_a.DATA}} {{time_a.DATA}} {{weather_a.DATA}}
B：{{city_b.DATA}} {{time_b.DATA}} {{weather_b.DATA}}
相爱：{{love_days.DATA}}
见面：{{meet_days.DATA}}
{{love_line.DATA}}
天气：{{weather_source.DATA}}
```

示例：

```text
早安，想你了
A：Ann Arbor 20:00 晴 12°C
B：Shanghai 08:00 多云 22°C
相爱：第100天
见面：还有30天
想你的心，比时差更准时。
天气：QWeather https://www.qweather.com
```

见面日期有三种文案：未来显示“还有 N 天”，当天显示“就是今天”，过去显示“见面日已过”。CN 槽位按 `CITY_B_TZ` 计算日期，US 槽位按 `CITY_A_TZ` 计算日期。

## 定时任务

GitHub Actions schedule 使用 IANA 时区，并避开整点：

| 目标当地时间 | Cron + timezone | Job | 阶段 C 行为 |
|--------------|-----------------|-----|-------------|
| 中国约 08:07 | `7 8 * * *` + `Asia/Shanghai` | `preview-cn` | dry-run |
| Detroit 约 08:13 | `13 8 * * *` + `America/Detroit` | `preview-us` | dry-run |

## 项目结构与测试

```text
src/main.py          # fail-closed 模式、数据组装、发送入口
src/weather.py       # QWeather geo + weather/now
src/dates.py         # 相爱天数、见面三态、当地日期时间
src/gemini_line.py   # Gemini 短句 + 静态回退
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
