# Flink 作业设计

## 1. 作业入口

主类：

```text
com.finguard.RiskMonitorJob
```

打包：

```bash
cd flink-job
mvn -q -DskipTests package
```

提交：

```bash
make submit-job
```

## 2. 作业参数

| 参数 | 默认值 | 说明 |
|---|---|---|
| `--bootstrap-servers` | `localhost:9092` | Kafka 地址 |
| `--transaction-topic` | `payment_transaction_events` | 交易输入 Topic |
| `--metric-output` | `file:///opt/finguard/data/output/realtime_metrics` | 指标输出 |
| `--alert-output` | `file:///opt/finguard/data/alerts/risk_alerts` | 告警输出 |
| `--late-output` | `file:///opt/finguard/data/late_events` | 迟到事件输出 |
| `--dead-letter-output` | `file:///opt/finguard/data/output/dead_letter` | 死信输出 |
| `--checkpoint-dir` | `file:///opt/finguard/data/checkpoints` | Checkpoint 目录 |
| `--parallelism` | `2` | 作业并行度 |
| `--watermark-seconds` | `60` | 乱序容忍秒数 |

## 3. 数据流

```text
KafkaSource
  -> parse/validate
  -> watermark
  -> event_id dedup
  -> late event side output
  -> rules
  -> metrics
  -> file sinks
```

## 4. 规则实现

| 规则 | 实现方式 |
|---|---|
| R001 用户短时高频 | `keyBy(user_id)` + 1 分钟滚动窗口 + count |
| R002 用户短时大额 | `keyBy(user_id)` + 5 分钟滑动窗口 + sum |
| R003 设备多用户 | `keyBy(device_id)` + 10 分钟滑动窗口 + distinct user |
| R004 银行卡多用户 | `keyBy(card_id)` + 10 分钟滑动窗口 + distinct user |
| R005 连续失败 | `keyBy(user_id)` + `ValueState<Integer>` |
| R006 黑名单设备 | 单事件规则，检查 `is_black_device` |
| R007 用户金额突增 | `keyBy(user_id)` + 历史均值 `ValueState<UserAmountStats>` |
| R008 商户收款突增 | 商户 5 分钟窗口金额 + 历史窗口均值状态 |

## 5. 实时指标

已实现：

- 近 1 分钟交易笔数：`transaction_count_1m`
- 近 5 分钟交易金额：`transaction_amount_5m`
- 各支付渠道成功率：`channel_success_rate_5m`
- 各商户实时收款金额：`merchant_realtime_amount_5m`
- 高风险交易/告警数量：`high_risk_alert_count_1m`
- 风险告警数量：`risk_alert_count_1m`

文档化扩展：

- 各城市交易金额 TopN：可按 `city` 做 5 分钟窗口金额聚合，再使用窗口结束时间二次 keyBy 做 TopN。
- 连续失败支付用户数：可将 R005 命中用户写入指标流后按窗口 distinct user。

## 6. Checkpoint

代码中启用：

```text
Checkpoint interval: 60s
Checkpoint mode: EXACTLY_ONCE
Min pause: 20s
Timeout: 10min
Max concurrent checkpoints: 1
Externalized checkpoints: retain on cancellation
```

Checkpoint 存储路径可由 `--checkpoint-dir` 调整。

## 7. 反压排查

排查顺序：

1. Flink UI 查看 Back Pressure、Busy Time、Checkpoint Duration。
2. Kafka 查看 consumer lag 是否持续上涨。
3. 检查热点 key，例如单个用户、设备或商户流量过高。
4. 检查窗口大小、滑动步长和 State TTL。
5. 检查文件 Sink 是否生成过多小文件。
6. 增加 Kafka 分区、Flink 并行度和 TaskManager slot。

常见优化：

- 对热点商户做两阶段聚合。
- 调整文件 Sink rolling policy。
- 对高基数状态设置 TTL。
- 将本地文件 Sink 替换为吞吐更高的对象存储或 ClickHouse。
