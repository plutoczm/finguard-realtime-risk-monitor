# 状态与可靠性设计

## 1. 状态清单

| 状态 | Key | 类型 | TTL | 用途 |
|---|---|---|---|---|
| `seen-event-id` | `event_id` | `ValueState<Boolean>` | 24 小时 | 输入去重 |
| `consecutive-failure-count` | `user_id` | `ValueState<Integer>` | 6 小时 | 连续失败支付 |
| `user-amount-stats` | `user_id` | `ValueState<UserAmountStats>` | 30 天 | 用户历史交易均值 |
| `merchant-window-amount-stats` | `merchant_id` | `ValueState<MerchantAmountStats>` | 14 天 | 商户历史窗口均值 |
| Window State | user/device/card/merchant | Flink 托管窗口状态 | 与窗口和 Watermark 相关 | 窗口聚合 |

## 2. 为什么需要 State TTL

风控系统 key 基数很高，用户、设备、卡和商户会持续增长。如果不设置 TTL，状态会无限膨胀，导致 Checkpoint 变慢、恢复时间增加和状态存储压力上升。因此高基数 Keyed State 必须有明确生命周期。

## 3. Checkpoint 配置

`RiskMonitorJob` 中启用：

```text
Checkpoint interval: 60 seconds
Mode: EXACTLY_ONCE
Min pause: 20 seconds
Timeout: 10 minutes
Max concurrent checkpoints: 1
Externalized cleanup: retain on cancellation
```

Checkpoint 覆盖 Kafka Source Offset、Keyed State、Window State 和 File Sink 提交状态。

## 4. 失败恢复

当 TaskManager 或作业失败：

1. Flink 根据重启策略拉起任务。
2. 从最近成功 Checkpoint 恢复状态。
3. Kafka Source 从 Checkpoint 中记录的 Offset 继续消费。
4. 窗口状态、定时器和 Watermark 继续推进。
5. File Sink 根据 Checkpoint 提交状态恢复 pending/in-progress 文件。

## 5. 一致性边界

必须区分状态一致性与任意外部系统的端到端一致性：

```text
Kafka -> Flink 状态：Checkpoint 协调 Source Offset 与算子状态。
Flink 内部窗口和 Keyed State：由 Flink 托管并随 Checkpoint 恢复。
Flink -> File Sink：使用 checkpoint-aware File Sink 的提交协议。
后续消费者：仍应基于 event_id / alert_id / metric_id 实现业务幂等。
```

项目不宣称跨任意第三方系统的全局 exactly-once。未来若替换 Sink，应重新评估目标系统的事务、幂等和失败恢复语义，而不是沿用当前结论。

## 6. event_id 去重

实现：

```text
keyBy(event_id)
  -> ValueState<Boolean> seen
  -> seen=true 则丢弃
  -> 否则写 seen=true 并放行
```

TTL 为 24 小时，覆盖普通重放和短期重复投递。超出 TTL 的旧重复事件可能再次进入计算，这是资源成本和去重准确性的折中。

## 7. 告警幂等

告警 ID 稳定生成：

- 单事件规则：`hash(rule_id, event_id)`
- 窗口规则：`hash(rule_id, key, window_start, window_end)`

即使 Flink 恢复后出现重复可见结果，下游仍可基于 `alert_id` 做幂等处理。

## 8. 反压排查

重点信号包括 Kafka consumer lag、Flink backpressure、Checkpoint duration、Watermark 推进速度、Sink 小文件数量和各 subtask records in/out。

优先优化顺序：先识别瓶颈，再调整并行度和分区；检查热点 key；减少无意义状态；调整窗口与滚动策略；最后才考虑替换存储或增加基础设施组件。
