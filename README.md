# 异地恋微信每日推送

双城天气 + 当地时间 + 相爱天数 + 见面倒计时 + 一句中文情话，经 **微信测试号** 模板消息推送。由 GitHub Actions 定时跑（中国 / 美东各一次）。

占位城市：`Ann Arbor` / `Shanghai`。

## 快速开始

1. **Fork** 本仓库
2. 仓库 **Settings → Secrets and variables → Actions** 添加 Secrets（见下表）
3. **Actions** 页启用工作流，点 **Run workflow** 试跑（可选 `cn` / `us` / `both`）
4. 确认手机收到测试号模板消息

本地试跑（不发微信）：

```bash
cp config.example.env .env   # 按需填写；无 key 也可 DRY_RUN
set -a && source .env && set +a
pip install -r requirements.txt
DRY_RUN=1 python src/main.py
```

## 申请链接

| 服务 | 链接 |
|------|------|
| 微信测试号 | https://mp.weixin.qq.com/debug/cgi-bin/sandbox?t=sandbox/login |
| 和风天气 | https://dev.qweather.com/ |
| Gemini API | https://aistudio.google.com/apikey |

## Secrets / 变量

**必填 Secrets**

| Name | 说明 |
|------|------|
| `WECHAT_APP_ID` | 测试号 appID |
| `WECHAT_APP_SECRET` | 测试号 appsecret |
| `WECHAT_TEMPLATE_ID` | 模板 ID |
| `WECHAT_OPENID_CN` | 中国槽位接收方 openid |
| `WECHAT_OPENID_US` | 美东槽位接收方 openid |
| `LOVE_START_DATE` | 在一起日 `YYYY-MM-DD` |
| `NEXT_MEET_DATE` | 下次见面日 `YYYY-MM-DD` |
| `QWEATHER_KEY` | 和风 Key |
| `GEMINI_API_KEY` | Gemini Key（可空，失败用内置情话） |

**可选**

| Name | 说明 |
|------|------|
| `QWEATHER_API_HOST` | 默认 `https://devapi.qweather.com`；商业版填自定义 Host |
| Variables：`CITY_A` / `CITY_B` / `CITY_A_TZ` / `CITY_B_TZ` | 默认 Ann Arbor / Shanghai，时区 America/Detroit / Asia/Shanghai |
| Variable：`DRY_RUN` | 设为 `1` 只打印 JSON 不发送 |

## 微信模板（复制到测试号）

新增模板，字段名必须一致（测试号关键词有长度限制，文案宜短）：

```
{{greeting.DATA}}
A：{{city_a.DATA}} {{time_a.DATA}} {{weather_a.DATA}}
B：{{city_b.DATA}} {{time_b.DATA}} {{weather_b.DATA}}
相爱：{{love_days.DATA}}
见面：{{meet_days.DATA}}
{{love_line.DATA}}
```

示例效果：

```
早安，想你了
A：Ann Arbor 20:00 晴 12°C
B：Shanghai 08:00 多云 22°C
相爱：第100天
见面：还有30天
想你的心，比时差更准时。
```

扫测试号二维码关注后，页面上的 **微信号** 即 openid。

## 定时（cron → UTC）

| 目标当地时间 | Cron (UTC) | Job |
|--------------|------------|-----|
| 中国 08:00 `Asia/Shanghai`（UTC+8） | `0 0 * * *` | `push-cn` |
| 美东约 08:00 `America/New_York` | `0 13 * * *`（按 **EST 冬令时** UTC-5） | `push-us` |

说明：GitHub cron **只认 UTC**，不跟夏令时。夏令时 EDT (UTC-4) 时，`13:00 UTC` ≈ 当地 **09:00**。若要严格夏令时 08:00，可把美东 cron 改成 `0 12 * * *`。

也支持 `workflow_dispatch` 手动跑。

## 项目结构

```
src/main.py          # 读环境变量、组数据、发送
src/weather.py       # 和风 geo + weather/now
src/dates.py         # love_days / meet_days / 当地时间
src/gemini_line.py   # Gemini 情话 + 静态回退
src/wechat.py        # access_token + template/send
.github/workflows/daily-push.yml
config.example.env
```

## 行为摘要

- `PUSH_SLOT=cn|us` → 使用 `WECHAT_OPENID_CN` / `WECHAT_OPENID_US`（可回退 `WECHAT_OPENID`）
- `DRY_RUN=1` → 打印完整 JSON，跳过发送
- 无和风 Key / 请求失败 → 天气显示「天气暂不可用」，不中断推送
- Gemini 失败 → 使用内置中文短句列表

Python **3.11+**，依赖：`requests`。
