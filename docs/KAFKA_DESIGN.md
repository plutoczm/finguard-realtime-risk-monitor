# Kafka 设计

## 1. Topic 设计

FinGuard 按事件语义拆分 Topic，避免把交易、用户行为、告警和错误数据混在一个流里。

| Topic | 类型 | 说明 | 默认分区 |
|---|---|---|---:|
| `payment_transaction_events` | 输入 | 支付交易主事件流 | 6 |
| `payment_user_events` | 输入 | 登录、绑卡、设备变更等用户行为 | 3 |
| `payment_risk_alerts` | 输出 | 风控告警扩展 Topic | 3 |
| `payment_realtime_metrics` | 输出 | 实时指标扩展 Topic | 3 |
| `payment_late_events` | 输出 | 严重迟到事件扩展 Topic | 3 |
| `payment_dead_letter_events` | 输出 | 解析失败、非法事件扩展 Topic | 3 |

创建命令：

```bash
make create-topics
```

或：

```bash
bash scripts/create_topics.sh
```

## 2. 分区键设计

交易事件默认使用 `user_id` 作为 Producer key，原因是用户维度规则最多：

- R001 用户 1 分钟交易次数。
- R002 用户 5 分钟交易金额。
- R005 连续支付失败。
- R007 用户历史均值突增。

设备、银行卡和商户维度规则在 Flink 中通过 `keyBy(device_id/card_id/merchant_id)` 重新分区。生产环境可以根据流量与热点情况拆分不同 Topic 或做多路写入。

## 3. 事件模型

交易事件包含：

```json
{
  "event_id": "evt-xxx",
  "transaction_id": "txn-xxx",
  "user_id": "user-00001",
  "account_id": "acct-00001",
  "card_id": "card-00001",
  "merchant_id": "merchant-0001",
  "device_id": "device-00001",
  "amount": 188.88,
  "transaction_type": "PAY",
  "transaction_status": "SUCCESS",
  "event_time": "2026-05-10T02:00:00Z",
  "process_time": "2026-05-10T02:00:01Z",
  "is_black_device": false,
  "risk_label": "NORMAL"
}
```

完整 schema 见 `producer/event_schema.json`。

## 4. Producer 能力

`producer/generate_transactions.py` 支持离线生成 JSON Lines：

```bash
python producer/generate_transactions.py --count 1000 --output data/sample_events/transactions.json
```

`producer/kafka_producer.py` 支持按 QPS 写 Kafka：

```bash
python producer/kafka_producer.py --bootstrap-server localhost:9092 --topic payment_transaction_events --qps 50 --duration 300
python producer/kafka_producer.py --mode abnormal --abnormal-rate 0.15 --qps 100 --duration 600
python producer/kafka_producer.py --mode late --count 200
```

支持模式：

- `normal`：正常交易。
- `mixed`：正常与异常混合。
- `abnormal`：高频、大额、黑名单、失败、商户突增等混合异常。
- `late`：事件时间明显早于当前时间。
- `duplicate`：重复 `event_id`。
- `out_of_order`：乱序事件。
- `peak`：高峰流量标签。
- `remote`：异地行为模拟。

## 5. 消费语义

Flink Kafka Source 通过 Checkpoint 管理消费 Offset。作业失败恢复时，会从最近一次成功 Checkpoint 中保存的 Offset 继续处理。

语义边界：

- Kafka -> Flink 状态：启用 Checkpoint 后可达到 Flink 状态层面的 exactly-once。
- Flink -> 文件 Sink：依赖 checkpoint-aware File Sink 和文件系统提交语义。
- 下游读取：仍需用 `event_id`、`alert_id` 做幂等。
