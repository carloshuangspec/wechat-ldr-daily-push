# 异地恋微信每日推送

双城天气 + 当地时间 + 相爱天数 + 见面倒计时 + 一句英文情话，经微信测试号模板消息推送。默认城市是 `Ann Arbor` / `Shanghai`。

当前处于“阶段 C”：本人单条手动真发已有微信 API 接受结果；手机实测发现倒计时旁的情话被程序截成 `...`，因此改为完整短句或安全拒发，改后手机呈现仍待复验。Grok 的例程已启用，每天上海 09:00 只负责拉起本仓库 `main` 上的 `daily-both`；GitHub Actions 组装同一份内容并依次调用微信接口发送给两人。仓库自身不再配置定时触发；两部手机收到及显示同一句的本次结果仍须分别验收。

## 安全运行模式

应用层 `SEND_MODE` 只接受两个值：

- `dry-run`：只打印脱敏预览，不发送；缺失时也是此模式。
- `live`：单人手动真发必须精确匹配 `LIVE_RECIPIENT=self`、`PUSH_SLOT=us`、
  `LIVE_CONFIRMATION=SEND_SELF_ONCE`，或 `LIVE_RECIPIENT=cn`、`PUSH_SLOT=cn`、
  `LIVE_CONFIRMATION=SEND_CN_ONCE`，并满足受控 GitHub Actions
  `workflow_dispatch` 上下文。每日双端真发通过 `workflow_dispatch` 的
  `mode=daily-both`、`slot=both`、空确认短语及当天上海日期进入；两开关
  都为 `1`、日期 claim 成功且两位收件人不同才允许发送。两种路径均须匹配 GitHub Actions、
  本仓库 `main` 和首次 run，其他情况在任何天气或发送请求前停止。

这层 `GITHUB_*` 检查用于防误操作，不是不可伪造的远程身份证明；环境变量在
本机仍可人为伪造。因此真实微信凭据只应保存在 GitHub Secrets，不要写入本机
`.env`。阶段 C 没有提供或记录本机真发流程。

旧 `DRY_RUN` 已不参与发送决策；它缺失或为 `0` 都不能触发真实发送。

本地预览不会加载微信凭据，但默认短句需要有效 `DEEPSEEK_API_KEY`；缺失或生成失败就整条跳过。CN 单人或双端共用路径当天若有有效的手写 `exact` 可不调用 AI。未配置 QWeather 时会联网读取 Open-Meteo 的公开天气，网络失败则显示英文降级文案。下面仅是运行格式；没有通过安全环境提供 DeepSeek Key（或当天有效 `exact`）时会预期失败，不会发送微信：

```bash
PUSH_SLOT=cn \
SEND_MODE=dry-run \
LOVE_START_DATE=2026-07-08 \
NEXT_MEET_DATE=2026-12-20 \
python src/main.py
```

`KNOWN_START_DATE` 是可选的约数起点，未设置时使用 `2019-09-02`。它不表示已核实的相识日；消息中的 `Known: ≈N days` 与确定的在一起天数分开计算。`NEXT_MEET_DATE=2026-12-20` 是 Carlos 本次确认的下次见面日期。双端同步定时按上海日期计算全部天数和倒计时；单人路径仍按对应收件人的当地日期计算。

## 阶段 C：GitHub Actions 操作

Carlos 必须本人在仓库 `Settings → Secrets and variables → Actions` 配置真实发送所需值。任何 Secret、Key、OpenID 或 token 都不要粘贴到聊天中。

手动运行 `daily-push` 时：

- 安全预览：选择 `mode=preview`；`slot=cn` 或 `us` 查看单人内容，`slot=both` 查看单次生成的双端共用内容，无需 confirmation。
- 本人测试：选择 `mode=live-self`、`slot=us`，并在 confirmation 精确输入 `SEND_SELF_ONCE`。该 job 只能使用 `WECHAT_OPENID_SELF`，不能读取 CN 收件人的 OpenID。
- 女友测试：选择 `mode=live-cn`、`slot=cn`，并在 confirmation 精确输入 `SEND_CN_ONCE`。该 job 只能使用 `WECHAT_OPENID_CN`，不能读取本人的 OpenID。
- 双端每日：仅在两个每日开关都精确为 `1` 时，可选择 `mode=daily-both`、`slot=both`、空 confirmation，并将 `delivery_date` 精确填为当天上海日期 `YYYY-MM-DD`。门禁会同时校验仓库、`main`、发起人与首次 run；先由唯一拥有 `contents: write` 权限的 claim job 为该上海日期创建 Git ref，再允许只读的 `daily-both` sender 运行。claim job 不读取微信或 DeepSeek 配置；sender 没有 GitHub 写 token。Git ref 已存在、任何值不匹配或 Re-run 都不会发送，也不会自动重试。
- 所有真发入口都限制为本仓库 `main` 分支、仓库所有者首次执行的 `workflow_dispatch` run；对该 run 点 Re-run 会被拒绝。槽位、短语、日期、仓库、分支、触发者或 run attempt 不匹配时，门禁 job 会失败，发送 job 不运行。

阶段 C 将预览与真发拆成独立 job：`preview-cn` / `preview-us` / `preview-both` 均使用 `SEND_MODE=dry-run`，完全不加载任何 `WECHAT_*`。Grok 每天只派发 `daily-both`：双开关均为 `1` 且取得日期 claim 后才能真发；任一开关关闭就不自动发送，单人定时 job 因 GitHub `schedule` 已撤除而不再被触发。手动预览始终可用。手动 `live-self` / `live-cn` 只加载各自 OpenID；`daily-both` 的发送步骤须加载并校验两个不同的 OpenID，再组装一次内容并依次发送。所有真发 job 在发送步骤前运行单元测试。

`SEND_SELF_ONCE` 与 `SEND_CN_ONCE` 是手动测试的意图确认短语，不是真正的一次性令牌；“首次 run”只限制单个 run 的重试，不会阻止创建新的手动 run。双端真发是两次顺序调用微信接口，并非原子事务或两部手机同时送达；第一人成功而第二人失败时，日志应保留第一人的脱敏接受状态，不盲目重试整个任务，以免重复发送。API 接受和绿色 job 本身均不等于手机收到；SELF 手机已确认先前手动测试，CN 手机与首次双端定时运行尚未确认。若发现收件人或内容错误，应立即关闭对应的每日开关并排查，不自动重发。

若手机收到了消息却看不到独立的英文短笺，先运行 `inspect-template` 工作流（无需输入）。它只读取当前 `WECHAT_TEMPLATE_ID` 对应的在线模板，输出 `template_found` 和 `missing_fields`，不加载任何收件 OpenID、也不发送微信。`missing_fields` 含 `love_line` 表示当前在线模板没有 `{{love_line.DATA}}`；若工作流报 `template_check_failed`，不能据此推断模板字段缺失。即使字段存在，也不能保证手机卡片显示它。`meet_days` 镜像同一条完整情话，绝不由程序截断加 `...`；超出倒计时旁的可见预算则整条安全失败，不发送半句话。两个字段若都显示，卡片可能重复，须以本人手机核对；不要盲目重发。可用 `preview-both`（`mode=preview`、`slot=both`）先核对字段组装。

## 配置：必填与可选

运行预览所需日期：

| Name | 类型 | 说明 |
|------|------|------|
| `LOVE_START_DATE` | Actions Secret | 在一起日，`YYYY-MM-DD` |
| `NEXT_MEET_DATE` | Actions Secret | 下次见面日，`YYYY-MM-DD` |

仅阶段 C 真发必填（单人 job 只加载对应 OpenID；双端 job 同时校验两个）：

| Name | 类型 | 说明 |
|------|------|------|
| `WECHAT_APP_ID` | Actions Secret | 微信测试号 appID |
| `WECHAT_APP_SECRET` | Actions Secret | 微信测试号 appsecret |
| `WECHAT_TEMPLATE_ID` | Actions Secret | 模板 ID |
| `WECHAT_OPENID_SELF` | Actions Secret | Carlos 本人的 US 槽位 openid，`live-self` / `scheduled-self` / `daily-both` 读取 |
| `WECHAT_OPENID_CN` | Actions Secret | 女友的 CN 槽位 openid，`live-cn` / `scheduled-cn` / `daily-both` 读取 |

短句默认运行必填；CN 单人或双端共用路径当天有有效 `exact` 时可跳过 API：

| Name | 类型 | 说明 |
|------|------|------|
| `DEEPSEEK_API_KEY` | Actions Secret | 英文短句由 `deepseek-flash` 生成；失败/无效/缺 Key 均不发送；不会改用 Gemini 或静态短句 |

可选增强与单日编辑：

| Name | 类型 | 说明 |
|------|------|------|
| `QWEATHER_KEY` | Actions Secret | 可选的 QWeather Key；必须与账号专属 Host 成对配置 |
| `QWEATHER_API_HOST` | Actions Secret | 可选的 QWeather 控制台 `*.qweatherapi.com` 账号专属 API Host |
| `DAILY_MESSAGE_CONFIG` | Actions Secret | CN 单人路径及双端共用路径的上海日期主题或手写英文原句；SELF 单人路径不加载；不配置则调用 DeepSeek |
| `KNOWN_START_DATE` | Actions Variable | 可选约数起点，默认 `2019-09-02`，不是已核实的相识日 |
| `CITY_A` / `CITY_B` | Actions Variable | 默认 `Ann Arbor` / `Shanghai` |
| `CITY_A_TZ` / `CITY_B_TZ` | Actions Variable | 默认 `America/Detroit` / `Asia/Shanghai` |

每日发送使用两个 Actions Variable 开关：`ENABLE_SELF_DAILY` 控制本人、`ENABLE_CN_DAILY` 控制女友；**不存在或不等于精确的 `1` 时均关闭**，不是 Secret。Grok 只派发双端模式，所以两个开关必须都为 `1` 才能自动发送；关闭任一个会使当日双端派发在门禁处失败，不会改发单人版。开关已开启不代表手机已收到。要暂停日推，将任一变量改成 `0` 或删除；已开始的运行无法靠关闭开关撤回，仍需核对运行与手机状态。手动确认短语不能代替每日开关。

QWeather Key 与 Host 都配置时优先使用 QWeather；任一缺失时使用无需密钥的 [Open-Meteo 免费非商业 API](https://open-meteo.com/en/terms)。默认城市会加国家限制以避免同名地点选错；其他城市可用英文 `City, Country` 缩小搜索范围。Open-Meteo 的[城市定位数据基于 GeoNames](https://open-meteo.com/en/docs/geocoding-api)，天气代码会转换成简短英文并将温度四舍五入，因此消息中的 `adapted` 标明了改动。其数据按 [CC BY 4.0 许可](https://creativecommons.org/licenses/by/4.0/)使用；模板的天气来源字段显示 Open-Meteo 官网、GeoNames、许可链接和改动说明。API 失败只显示英文状态，不会中断整条消息。QWeather Key 只经 `X-QW-Api-Key` 请求头发往校验过的 Host；所有天气请求均拒绝自动重定向。

每天默认请求 DeepSeek 的 `deepseek-flash` 生成一条不超过 48 个可打印 ASCII 字符、句尾完整的原创英文情话（无 `Note:` 标签；Known 在 `greeting`），同一句发给两位收件人。提示词要求直接表达对她的爱意、思念或珍惜，而不是天气简报或泛泛问候；两端当地时段与无城市名天气只作背景，不得编造私密回忆、普通生活事件（如咖啡/通勤）、地名或对方感受。无手动主题时可选不同语气，**Garden 连续故事感仅偶尔使用**，不是每日打卡仪式，也不是固定句库。有手动 `theme` 时优先服从主题并仍受硬性边界约束；有效 `exact` 跳过 AI。正式请求只在 HTTPS 固定端点发送 `Authorization: Bearer`，禁止自动重定向。若仅文案不合格，会在任何微信发送前最多再生成两次；三次仍不合格或接口/鉴权失败则跳过整条，不替换固定句子，**绝不自动重试微信发送**。失败日志只记录固定类别（如 `invalid_text`），不包含响应正文。长度、标点和 ASCII 校验不能百分之百判定感情质量，故真发前先看预览。真实 Key 只放在 `DEEPSEEK_API_KEY` Actions Secret，不放仓库、本地 `.env`、聊天或日志；Secret 已保存也不代表实际有效。

想调整某个上海日期的内容，可在 Mac 上双击 `scripts/edit-daily-message.command`，填日期（默认上海今天）、可选主题 `theme`、可选手写英文原句 `exact`；至少填一项。`theme` 最多 120 字符，可写中英文，会发给 DeepSeek 引导生成；`exact` 必须为单行 1–48 个可打印 ASCII 字符，优先级高于主题且不请求 AI，原样进入独立 `love_line` 字段、去掉两端空格后完整镜像到倒计时旁；若倒计时太长仍放不下，则安全拒发，绝不截句。工具本地显示输入供确认后，仅通过标准输入将单个 JSON 对象写入 `DAILY_MESSAGE_CONFIG` Secret，不写入 Git 历史或临时文件。替换时需重新填完整内容，不能从 GitHub Secret 读回；工具可经单独确认删除此 Secret。日期不匹配的旧配置会被忽略，格式无效的配置会让运行安全失败。这个 Secret 加载到 CN 单人或双端共用的预览和发送 job；SELF/US 单人路径不读取。

GitHub 在工作流**排队时**读取仓库 Secret，故要在下一次 run 排队前完成编辑；排队后再更新或删除，不会更改那一次运行。DeepSeek [官方缓存说明](https://api-docs.deepseek.com/guides/kv_cache/)指出输入/输出前缀可能写入缓存，不要在主题中填写未经双方同意的聊天档案、凭据或第三方隐私。`exact` 不送 DeepSeek，但最终微信消息及当前预览日志都会展示它；Secret 的加密不隐藏已渲染的预览内容，仓库日志读取者可见。

先使用 `mode=preview`、`slot=both`，只检查 `Preview Both` 步骤：`line_source=deepseek` 说明这一步的 API 结果通过校验；当天手写 `exact` 则为 `line_source=manual`，**不能证明 API 可用**。前面的 `Run tests` 步骤只用模拟响应，不能作为真实生成的证据。预览中的 `deepseek_key_set` 仅说明配置非空，不证明 Key 有效。预览与后续真发是两个独立请求，不保证生成同一句；双端同一次真发则共用一条通过校验的情话和全部其他字段。手写原文在同一日期稳定。手动预览 job 始终不加载任何 `WECHAT_*`，不会发送微信消息；即使每日开关已开启，手动预览仍是安全的。

QWeather 的 `/v7/weather/now` 计划于 **2027-06-01** 停止服务；阶段 C 暂不迁移 v1，后续必须在停服前安排迁移。

## 服务入口

| 服务 | 链接 |
|------|------|
| 微信测试号 | https://mp.weixin.qq.com/debug/cgi-bin/sandbox?t=sandbox/login |
| QWeather | https://www.qweather.com |
| QWeather 开发平台 | https://dev.qweather.com/ |
| DeepSeek API | https://platform.deepseek.com/ |

## 微信模板

测试号模板字段必须与下面一致，固定标签请用英文。无 Hello / Good morning 等问候语；`greeting` 字段本身是 Known 行（如 `Known: ≈N days`，大 N 时缩短为 `Known ≈Nd`，且 ≤20）；`meet_days` 是见面倒计时加 ` | ` 和同一条完整情话，总长 ≤64；`love_line` 保留无标题英文原句（不加 `Note:` 或 Known），长度 ≤48。手机是否显示 `greeting` / `love_line` 取决于在线测试号模板；`weather_source` 在卡片上也可能不显示，须核对手机实际呈现：

```text
{{greeting.DATA}}
A: {{city_a.DATA}} {{time_a.DATA}} {{weather_a.DATA}}
B: {{city_b.DATA}} {{time_b.DATA}} {{weather_b.DATA}}
Together: {{love_days.DATA}}
Next meeting: {{meet_days.DATA}}
{{love_line.DATA}}
Weather: {{weather_source.DATA}}
```

示例（日期、天气和当地时间仅为格式示意；双端真发时这份字段不因收件人而改变）：

```text
Known: ≈2573 days
A: Ann Arbor 21:00 Sunny 12°C
B: Shanghai 09:00 Cloudy 22°C
Together: 72 days
Next meeting: in 94 days | Sharing this quiet stretch of sky with you.
Sharing this quiet stretch of sky with you.
Weather: Open-Meteo https://open-meteo.com | GeoNames | CC BY 4.0 https://creativecommons.org/licenses/by/4.0/ | adapted
```

见面日期有三种英文文案：未来显示 “in N days”，当天显示 “today”，过去显示 “date passed”。单人 CN 槽位按 `CITY_B_TZ` 计算日期，单人 US 槽位按 `CITY_A_TZ` 计算日期；双端共用路径统一按 `CITY_B_TZ`（默认上海）日期计算相爱、相识约数和见面倒计时；Known 经 `greeting` 字段输出，不再使用时段问候。模板更新后需将**新模板的 ID** 保存为 `WECHAT_TEMPLATE_ID`，否则程序仍引用旧模板。

## 定时任务

Grok 的已启用例程每天上海 09:00 拉起一次 GitHub Actions `workflow_dispatch`：在本仓库 `main` 指定 `mode=daily-both`、`slot=both`、空 `confirmation`，并填写当天上海日期 `delivery_date=YYYY-MM-DD`。Grok 只负责拉起工作流，不生成情话或调用微信；本仓库已撤除 GitHub Actions 原生 `schedule`，避免双重自动入口。

| 每日开关 | Job | 自动派发结果 |
|----------|-----|-------------|
| 两个都为 `1` | `claim-daily` → `daily-both` | 先为上海日期创建不可重复的 claim，再组装一份内容，依次请求发送给女友和本人 |
| 任一不为 `1` | `validate-dispatch` | 门禁失败，不自动发送；仍可单独手动预览 |

上海 09:00 在底特律夏令时是前一天 21:00，冬令时是前一天 20:00；无法让两地全年都固定在 09:00 / 21:00。双端任务只组装一次天气、当地时间、上海日期天数和英文情话（DeepSeek 可按无效文案规则在发送前重新生成），当天的 `DAILY_MESSAGE_CONFIG` 同时作用于两份相同内容；随后以两个不同 OpenID 顺序请求微信接口，不是原子事务。日期 claim 在发送前创建；任一端失败也不能盲目重跑整条，以免重复发送。Grok 例程和 GitHub Actions 均在云端，不依赖本机开机；派发、排队、安装依赖与两次微信 API 请求都可能延迟。运行成功或微信 API 接受不等于两部手机收到；时间和显示内容须分别在手机验收，不能承诺每天 09:00 准点或同一秒收到。

## 项目结构与测试

```text
src/main.py          # fail-closed 模式、数据组装、发送入口
src/weather.py       # QWeather 或无密钥 Open-Meteo 双城天气
src/dates.py         # 相爱天数、见面三态、当地日期时间
src/deepseek_line.py # DeepSeek 英文短句；失败不发
src/wechat.py        # 脱敏的 token 与 template/send 调用
src/daily_content.py # CN 单人及双端共用的日期、主题和手写原句校验
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
