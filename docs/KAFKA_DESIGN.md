# Kafka 设计

## 1. Topic 设计

FinGuard 当前运行链路只创建一个业务 Topic：

| Topic | 类型 | 说明 | 默认分区 |
|---|---|---|---:|
| `payment_transaction_events` | 输入 | 支付交易事件流 | 6 |

这是刻意的范围控制：Flink 当前从该 Topic 消费交易事件，告警、指标、迟到事件和死信均由 checkpoint-aware File Sink 输出，因此不为尚未接入的下游预建 Kafka Topic。

创建命令：

```bash
make create-topics
```

## 2. 本地 Kafka 模式

Docker Compose 使用单节点 KRaft combined mode，去掉 ZooKeeper，仅用于本地开发与作品演示。生产部署应拆分 broker/controller、配置多副本、安全认证和持久化存储。

## 3. 分区键设计

交易 Producer 使用 `user_id` 作为 key，使用户维度事件在 Kafka 层保持稳定分区。Flink 内部再根据规则使用 `keyBy(user_id/device_id/card_id/merchant_id)` 进行逻辑重分区。

当前 6 分区用于本地并行度实验，不代表生产容量结论；真实分区数应由目标吞吐、消费者并行度、单分区处理能力和 key 倾斜测试共同决定。

## 4. 事件模型

```json
{
  "event_id": "evt-xxx",
  "transaction_id": "txn-xxx",
  "user_id": "user-00001",
  "card_id": "card-00001",
  "merchant_id": "merchant-0001",
  "device_id": "device-00001",
  "amount": 188.88,
  "transaction_status": "SUCCESS",
  "event_time": "2026-05-10T02:00:00Z",
  "channel": "APP",
  "is_black_device": false,
  "risk_label": "NORMAL"
}
```

完整约束见 `producer/event_schema.json`。

## 5. Producer 与压测

```bash
python producer/generate_transactions.py --count 1000 --output data/sample_events/transactions.json
python producer/kafka_producer.py --bootstrap-server localhost:9092 --topic payment_transaction_events --qps 50 --duration 300
python producer/kafka_producer.py --mode abnormal --abnormal-rate 0.15 --qps 100 --duration 600
```

支持正常、混合异常、迟到、重复、乱序和峰值流量等测试模式，用于验证 Watermark、State、去重与 backpressure 行为。

## 6. 消费与一致性边界

Flink Kafka Source 通过 Checkpoint 保存消费进度。失败恢复时，Source offset 与算子状态一起恢复。

- Kafka → Flink state：Checkpoint 提供一致性恢复边界。
- Flink → File Sink：依赖 checkpoint-aware File Sink 的提交语义。
- 告警使用稳定 `alert_id`，为后续幂等消费提供键。
- 项目不宣称跨任意外部系统的全链路 exactly-once。
