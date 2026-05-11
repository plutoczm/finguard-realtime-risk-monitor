# Watermark 与迟到数据处理

## 1. 为什么使用 Event Time

支付风控判断应基于交易真实发生时间，而不是 Flink 处理到事件的时间。Kafka 积压、网络抖动、客户端补发都会造成事件到达顺序与发生顺序不一致，因此 FinGuard 使用 `event_time` 作为核心时间语义。

## 2. Watermark 策略

Flink 作业使用 bounded out-of-orderness：

```text
watermark = max(event_time) - 60s
```

默认值可通过参数调整：

```bash
--watermark-seconds 60
```

如果乱序更严重，可以把容忍时间调大；代价是窗口触发更慢，告警延迟增加。

## 3. 窗口触发

窗口依据 Watermark 触发，而不是依据机器当前时间触发。

示例：

```text
窗口: 10:00:00 - 10:01:00
乱序容忍: 60 秒
当 Watermark 推进到 >= 10:01:00 时，窗口可触发计算
```

## 4. 迟到事件处理

FinGuard 在 `LateEventRouterFunction` 中判断：

```text
if event_time < current_watermark:
    side output -> late-events
else:
    main stream -> rules and metrics
```

迟到事件输出到：

```text
data/late_events/
```

用途：

- 保留审计证据。
- 后续离线补偿。
- 分析上游延迟质量。
- 验证 Watermark 配置是否合理。

## 5. 乱序、迟到、补发的区别

| 类型 | 说明 | 处理 |
|---|---|---|
| 轻微乱序 | 在 Watermark 容忍范围内到达 | 正常进入窗口 |
| 严重迟到 | 落后当前 Watermark | 写入 late events |
| 历史补发 | 大批量历史数据重放 | 建议独立 replay topic 和回放作业 |
| 重复事件 | 相同 `event_id` 再次出现 | 进入 event_id 去重逻辑 |

## 6. 面试表达

可以这样讲：

> 我没有用 Processing Time 做风控窗口，因为 Kafka 消费延迟会改变窗口归属。FinGuard 用事件自身的 `event_time` 分配 Watermark，允许 60 秒乱序。超过 Watermark 的事件不会直接污染实时窗口，而是通过 side output 写入迟到事件目录，后续用于审计或补偿。
