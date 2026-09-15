# Changelog

## 2026-09-15

- 阶段 C：发送入口改为 `SEND_MODE=dry-run|live` 的 fail-closed 模式，并为一次受控 CN 真发增加工作流与 Python 双重防误操作门禁；普通本机入口默认拒绝真发。
- 预览与真发拆成独立 job；只有 `live-cn` 最后一步加载微信 Secrets，所有 schedule 与 US 路径固定 dry-run。
- 定时任务改用 GitHub Actions 时区调度，并把官方 actions 升级到 Node.js 24 系列。
- 微信异常脱敏并严格校验成功响应；QWeather 改用账号 Host 与请求头认证。
- 增加日期三态、署名字段和 stdlib 单元测试。
