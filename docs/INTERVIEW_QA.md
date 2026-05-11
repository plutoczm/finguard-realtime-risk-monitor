# FinGuard 面试问答

## 1. 项目整体

1. Q：FinGuard 是什么项目？  
A：FinGuard 是一个支付交易实时风控项目，用 Kafka 接入交易事件，用 Flink 做事件时间窗口、状态计算、去重、迟到数据处理和风险规则告警，默认将指标与告警写入文件 Sink。

2. Q：核心链路是什么？  
A：Python Producer 生成交易事件，写入 Kafka `payment_transaction_events`，Flink `RiskMonitorJob` 消费后输出 `realtime_metrics`、`risk_alerts`、`late_events` 和 `dead_letter` 文件。

3. Q：这个项目和普通规则 Demo 有什么区别？  
A：它不仅实现规则，还覆盖乱序、Watermark、窗口、Keyed State、TTL、Checkpoint、迟到旁路、重复事件、文件 Sink 和一致性边界。

4. Q：这个项目能写进简历的亮点是什么？  
A：Kafka + Flink 实时链路、8 条支付风控规则、事件时间与 Watermark、状态去重、Checkpoint 容错、Windows Docker 本地可运行、完整文档和测试。

## 2. Kafka

5. Q：为什么用 Kafka？  
A：Kafka 提供高吞吐、持久化、可重放、分区扩展和消费者解耦，适合承载支付交易事件流。

6. Q：Kafka 分区键怎么设计？  
A：默认按 `user_id` 写入，因为用户维度规则最多；设备、银行卡、商户维度在 Flink 内部再 `keyBy` 重分区。

7. Q：如何保证同一用户事件局部有序？  
A：Producer 使用同一 `user_id` 作为 key，同一 key 会进入同一 Kafka 分区，在单分区内 Kafka 保证顺序。

8. Q：Topic 为什么要拆分？  
A：交易、用户行为、告警、指标、迟到、死信语义不同，拆分 Topic 有利于权限、扩容、保留策略和下游消费。

9. Q：Kafka 消息会不会重复？  
A：可能会。Producer 重试、Flink 恢复、手动重放都可能带来重复，所以项目用 `event_id` 做输入去重，用 `alert_id` 做告警幂等。

10. Q：消息积压怎么办？  
A：先看 consumer lag，再看 Flink 反压、并行度、Kafka 分区数、热点 key 和 Sink 吞吐。处理方式包括扩分区、提高并行度、优化状态和 Sink。

## 3. Flink

11. Q：为什么用 Flink？  
A：Flink 原生支持事件时间、Watermark、低延迟有状态计算、窗口、Checkpoint 和 Exactly-once 状态恢复，适合实时风控。

12. Q：Flink 和 Spark Streaming 的区别？  
A：Flink 是原生流处理，事件级低延迟和状态能力更强；传统 Spark Streaming 是微批模型，延迟和事件时间处理方式不同。

13. Q：Event Time 和 Processing Time 区别？  
A：Event Time 是事件真实发生时间，Processing Time 是算子处理时间。风控窗口应使用 Event Time，避免 Kafka 延迟改变窗口归属。

14. Q：Watermark 是什么？  
A：Watermark 是 Flink 对事件时间进度的估计，用来判断窗口何时触发，并容忍一定程度的乱序。

15. Q：Watermark 太短有什么问题？  
A：乱序事件更容易被判定为迟到，窗口结果不完整。

16. Q：Watermark 太长有什么问题？  
A：窗口触发和告警输出延迟增加。

17. Q：迟到数据怎么处理？  
A：超过当前 Watermark 的事件进入 side output，并写入 `data/late_events/`，用于审计、补偿和延迟质量分析。

18. Q：窗口怎么选？  
A：固定周期统计用滚动窗口，例如 R001；最近一段时间内持续监测用滑动窗口，例如 R002、R003、R004、R008。

19. Q：Tumbling Window 和 Sliding Window 区别？  
A：滚动窗口不重叠，适合周期统计；滑动窗口可重叠，适合“最近 N 分钟”类规则。

20. Q：为什么要用 Keyed State？  
A：风控需要按用户、设备、卡、商户维护上下文，例如连续失败次数、历史均值、去重标记。

21. Q：Keyed State 存了什么？  
A：`event_id` 去重标记、用户连续失败次数、用户历史金额统计、商户历史窗口金额统计等。

22. Q：State TTL 为什么需要？  
A：防止用户、设备、卡等高基数状态无限增长，降低 Checkpoint 和恢复成本。

23. Q：Checkpoint 是什么？  
A：Checkpoint 是 Flink 的容错快照，保存 Kafka offset、算子状态、窗口状态和 Sink 提交状态。

24. Q：Savepoint 是什么？  
A：Savepoint 是人为触发的状态快照，适合作业升级、迁移、回滚和调整并行度。

25. Q：Flink 如何实现 exactly-once？  
A：Flink 通过 Checkpoint 协调 Source Offset、算子状态和支持事务或提交协议的 Sink。

26. Q：你的项目是否端到端 exactly-once？  
A：Kafka 到 Flink 状态层面可以达到 exactly-once；文件输出依赖 checkpoint-aware File Sink；下游读取仍需基于 `event_id` 或 `alert_id` 做幂等，因此不夸大全链路绝对 exactly-once。

## 4. 规则与状态

27. Q：event_id 去重怎么做？  
A：对流按 `event_id` keyBy，使用 `ValueState<Boolean>` 记录是否处理过，TTL 为 24 小时，重复事件直接丢弃。

28. Q：连续失败支付怎么判断？  
A：按 `user_id` keyBy，`FAILED` 时状态加 1，非失败时清零，达到 5 次输出 R005 告警。

29. Q：黑名单设备怎么处理？  
A：当前版本读取事件字段 `is_black_device`，命中即输出 R006。生产可扩展为 Kafka 黑名单流 + Broadcast State。

30. Q：商户突增怎么判断？  
A：先按商户做 5 分钟窗口金额，再用 Keyed State 保存历史窗口均值，当前窗口金额超过历史均值 3 倍输出 R008。

31. Q：用户金额突增怎么判断？  
A：按用户保存历史成功交易金额均值，当前成功交易金额超过历史均值 5 倍且历史样本足够时输出 R007。

32. Q：告警重复怎么办？  
A：生成稳定 `alert_id`。单事件规则基于 `rule_id + event_id`，窗口规则基于 `rule_id + key + window_start + window_end`，下游按 `alert_id` 去重。

33. Q：如何避免告警风暴？  
A：增加告警冷却状态、合并窗口告警、按用户或商户聚合摘要、设置风险等级策略、下游使用 `alert_id` 和规则版本去重。

## 5. 运维与扩展

34. Q：高峰流量怎么压测？  
A：使用 `kafka_producer.py --mode peak --qps 1000 --duration 600` 提高 QPS，观察 Kafka lag、Flink records/s、Checkpoint 和 Sink 输出。

35. Q：反压怎么排查？  
A：先看 Flink UI backpressure、busy time 和 checkpoint，再看 Kafka lag、热点 key、状态大小、Sink 吞吐和 TaskManager 资源。

36. Q：状态过大怎么办？  
A：设置 TTL、减少明细状态、使用聚合状态、启用 RocksDB、拆分热点 key、缩短窗口或调大滑动步长。

37. Q：Sink 写入失败怎么办？  
A：依赖 Checkpoint 恢复；外部数据库 Sink 要用主键幂等或事务；文件 Sink 下游不要读取 in-progress 文件。

38. Q：Kafka 消费失败怎么办？  
A：Flink 作业从最近 Checkpoint 恢复 Kafka offset；如果长时间失败，需要检查 Kafka 可用性、Topic 权限和反序列化错误。

39. Q：如何扩展到更高 QPS？  
A：增加 Kafka 分区，提高 Flink 并行度和 TaskManager slot，优化 key 分布，使用批量/异步 Sink，并对热点商户做两阶段聚合。

40. Q：项目最大难点是什么？  
A：难点不是单条规则，而是乱序、迟到、重复、状态膨胀、恢复一致性、反压和告警幂等这些真实流处理问题的组合。

41. Q：这个项目和离线数仓项目有什么区别？  
A：离线数仓关注 T+1 汇总和历史分析；实时风控关注秒级发现、事件时间语义、有状态规则和故障恢复。

42. Q：如何支持规则热更新？  
A：将规则配置写入独立 Kafka Topic，Flink 使用 Broadcast State 广播到所有并行算子，并给规则配置加版本号。

43. Q：为什么默认用文件 Sink？  
A：文件 Sink 依赖少，保证本地最小链路可跑。数据库和 Dashboard 可以通过 SQL 文件扩展。

44. Q：ClickHouse 幂等怎么做？  
A：可以用 `alert_id` 作为去重键，结合 `ReplacingMergeTree` 或查询侧 `argMax` 去重，但它是最终一致，不应说成强 exactly-once。

45. Q：上生产还缺什么？  
A：Schema Registry、认证鉴权、多副本 Kafka、持久化 Checkpoint、规则平台、可观测告警、压测、CI/CD、灾备和数据治理。
