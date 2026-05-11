# 风控规则设计

## 1. 规则输出格式

每条规则输出统一 `RiskAlert`：

| 字段 | 说明 |
|---|---|
| `alert_id` | 稳定告警 ID，用于幂等 |
| `rule_id` | 规则编号 |
| `rule_name` | 规则名称 |
| `risk_level` | 风险等级 |
| `reason` | 命中原因 |
| `event_id` | 单事件规则关联事件 |
| `window_start/window_end` | 窗口规则时间范围 |
| `evidence` | 命中证据 |

## 2. 规则明细

| Rule ID | Rule Name | Risk Level | 实现方式 | Reason |
|---|---|---|---|---|
| R001 | 用户短时高频交易 | MEDIUM | `user_id` 1 分钟滚动窗口 count | 同一用户在1分钟窗口内交易次数超过10次 |
| R002 | 用户短时大额交易 | HIGH | `user_id` 5 分钟滑动窗口 sum | 同一用户在5分钟窗口内累计交易金额超过20000元 |
| R003 | 设备多用户关联 | HIGH | `device_id` 10 分钟滑动窗口 distinct user | 同一设备在10分钟内关联超过5个用户 |
| R004 | 银行卡多用户关联 | HIGH | `card_id` 10 分钟滑动窗口 distinct user | 同一银行卡在10分钟内关联超过3个用户 |
| R005 | 连续支付失败 | MEDIUM | `user_id` Keyed State 记录连续失败次数 | 同一用户连续支付失败次数达到5次 |
| R006 | 黑名单设备交易 | HIGH | 单事件判断 `is_black_device=true` | 当前交易设备命中黑名单设备 |
| R007 | 用户交易金额突增 | MEDIUM | `user_id` 历史均值状态 | 当前交易金额超过用户历史平均交易金额5倍 |
| R008 | 商户收款突增 | HIGH | 商户 5 分钟窗口金额与历史窗口均值比较 | 同一商户5分钟收款金额超过历史5分钟平均水平3倍 |

## 3. 告警幂等

单事件规则：

```text
alert_id = hash(rule_id, event_id)
```

窗口规则：

```text
alert_id = hash(rule_id, key_name, key_value, window_start, window_end)
```

这样 Flink 失败恢复或下游重复读取文件时，可以基于 `alert_id` 做去重。

## 4. 规则扩展

可扩展方向：

- 将阈值放入 Kafka 规则配置流，并用 Broadcast State 热更新。
- 增加 IP 风险地区、设备指纹、黑名单卡、商户行业等维表。
- 增加告警冷却时间，避免同一用户短时间重复刷屏。
- 将规则命中结果写回特征流，形成实时画像。
