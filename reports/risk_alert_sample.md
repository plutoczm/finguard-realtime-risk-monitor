# 风险告警样例

Flink 作业默认将风险告警写入：

```text
data/alerts/risk_alerts/
```

样例告警：

```json
{"alert_id":"a9fb4c35-82e4-35dd-94da-7683f78f2ac2","rule_id":"R001","rule_name":"用户短时高频交易","risk_level":"MEDIUM","reason":"同一用户在1分钟窗口内交易次数超过10次","user_id":"user-demo-hf","window_start":1778378400000,"window_end":1778378460000,"evidence":{"user_id":"user-demo-hf","transaction_count":"12","threshold":"10","window":"1 minute tumbling event-time window"}}
{"alert_id":"8a1ce115-f0f4-3e3e-86e3-71c038da2019","rule_id":"R006","rule_name":"黑名单设备交易","risk_level":"HIGH","reason":"当前交易设备命中黑名单设备","event_id":"evt-sample-003","transaction_id":"txn-sample-003","user_id":"user-demo-black","device_id":"device-black-001","amount":899.0,"event_time":"2026-05-10T02:00:10Z","evidence":{"device_id":"device-black-001","is_black_device":"true","source":"event_flag"}}
{"alert_id":"c2aa47f2-b157-3b29-b9e7-86b238a29f83","rule_id":"R004","rule_name":"银行卡多用户关联","risk_level":"HIGH","reason":"同一银行卡在10分钟内关联超过3个用户","card_id":"card-demo-shared","window_start":1778378400000,"window_end":1778379000000,"evidence":{"card_id":"card-demo-shared","distinct_user_count":"5","threshold":"3","sample_user_ids":"user-demo-card-00,user-demo-card-01,user-demo-card-02,user-demo-card-03,user-demo-card-04","window":"10 minute sliding event-time window"}}
```

告警 ID 生成方式：

- 单事件规则：`hash(rule_id, event_id)`
- 窗口规则：`hash(rule_id, key_name, key_value, window_start, window_end)`

下游数据库或告警平台可以用 `alert_id` 做幂等去重。
