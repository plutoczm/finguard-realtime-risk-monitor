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

风控系统 key 基数很高，用户、设备、卡和商户会持续增长。如果不设置 TTL，状态会无限膨胀，导致：

- Checkpoint 变慢。
- 恢复时间变长。
- RocksDB 或内存压力上升。
- 历史无效用户长期占用资源。

本项目对高基数 Keyed State 均设置 TTL。

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

Checkpoint 覆盖：

- Kafka Source Offset
- Keyed State
- Window State
- File Sink 提交状态

## 4. 失败恢复

当 TaskManager 或作业失败：

1. Flink 根据重启策略拉起任务。
2. 从最近成功 Checkpoint 恢复状态。
3. Kafka Source 从 Checkpoint 中记录的 Offset 继续消费。
4. 窗口状态、定时器和 Watermark 继续推进。
5. File Sink 根据 Checkpoint 提交状态恢复 pending/in-progress 文件。

## 5. 一致性边界

必须诚实说明：

```text
Kafka -> Flink 状态：启用 Checkpoint 后可达到 exactly-once 状态一致性。
Flink 内部窗口和 Keyed State：由 Flink 托管，恢复后状态一致。
Flink -> File Sink：使用 checkpoint-aware File Sink 时，可在可靠文件系统上接近 exactly-once 可见文件。
下游读取文件或写数据库：需要基于 event_id / alert_id / metric_id 做幂等。
```

本项目不承诺“任何外部系统端到端绝对 exactly-once”。如果扩展到 PostgreSQL，建议使用 `alert_id` 主键和 `ON CONFLICT`；如果扩展到 ClickHouse，建议使用 `ReplacingMergeTree` 或业务去重查询，但 ClickHouse 去重是最终一致。

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

即使 Flink 恢复后重复输出，下游也可基于 `alert_id` 去重。

## 8. 反压排查

信号：

- Kafka consumer lag 上升。
- Flink UI backpressure 变红。
- Checkpoint duration 增大。
- Watermark 长时间不推进。
- Sink 小文件数量过多。
- 某些 subtask records in/out 明显偏高。

处理：

- 增加 Kafka 分区和 Flink 并行度。
- 排查热点 key。
- 调整窗口大小和滑动步长。
- 缩短无意义状态 TTL。
- 优化 Sink rolling policy。
- 对商户大流量规则做两阶段聚合。
