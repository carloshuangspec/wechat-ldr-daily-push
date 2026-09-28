# Changelog

## 2026-09-28

- daily-both 精确 09:00:00（Asia/Shanghai）发送：全部门禁、claim、日期校验、天气与 DeepSeek 生成完成后，紧挨微信发送前，若早于 `delivery_date` 09:00:00 且差值 ≤ 15 分钟则等待至 09:00:00，再连续发 CN 与 SELF；已到/已过 09:00 立即发送；早于 15 分钟以上不等待、立即发送（`send_hold=skipped reason=too_early`）。
- 等待以 ≤30 秒分段 sleep 并每段重读墙钟，单调时钟兜底总时长 ≤ cap+5 秒；固定日志 `send_hold=waited seconds=N` / `send_hold=none` / `send_hold=skipped reason=...`，不含正文或凭据。
- 仅 `workflow_dispatch` + `LIVE_DISPATCH_MODE=daily-both` + `LIVE_RECIPIENT=both` 生效；live-self、live-cn、schedule 从不等待；preview both 只记录 `send_hold=would_wait seconds=N`。
- LIVE Both job `timeout-minutes` 10 → 25 以容纳等待。

## 2026-09-27

- DeepSeek 英文情话：修复 `invalid_text` 反复失败。提示词目标长度收紧到约 40 字符（硬上限仍 48）、只用 ASCII 直撇号、单行、无引号/Markdown/标签。
- 仅对生成文本做确定性清理：首尾空白、一对包裹引号/反引号、弯引号转 ASCII、em/en dash 转 `-`、合并行内空白；不截断、不替换、`Note:` 仍硬拒绝；手写 `exact` 校验不变。
- 文案类失败重试次数 3 → 5；HTTP/鉴权/网络错误仍立即失败。
- 新增固定诊断：`line_failure=invalid_text reason=...`、`line_retry=N ...`、`line_normalized=...`，不含正文、主题或 Key。

## 2026-09-15

- 阶段 C：发送入口改为 `SEND_MODE=dry-run|live` 的 fail-closed 模式，并为一次受控 CN 真发增加工作流与 Python 双重防误操作门禁；普通本机入口默认拒绝真发。
- 预览与真发拆成独立 job；只有 `live-cn` 最后一步加载微信 Secrets，所有 schedule 与 US 路径固定 dry-run。
- 定时任务改用 GitHub Actions 时区调度，并把官方 actions 升级到 Node.js 24 系列。
- 微信异常脱敏并严格校验成功响应；QWeather 改用账号 Host 与请求头认证。
- 增加日期三态、署名字段和 stdlib 单元测试。
