# 实时指标样例

Flink 作业默认将实时指标写入：

```text
data/output/realtime_metrics/
```

样例 JSON Lines：

```json
{"metric_id":"m-001","metric_name":"transaction_count_1m","dimensions":{},"value":1260.0,"count":1260,"window_start":1778378400000,"window_end":1778378460000,"emit_time":1778378461200}
{"metric_id":"m-002","metric_name":"transaction_amount_5m","dimensions":{},"value":386520.75,"count":0,"window_start":1778378100000,"window_end":1778378400000,"emit_time":1778378401300}
{"metric_id":"m-003","metric_name":"channel_success_rate_5m","dimensions":{"channel":"APP","success":"488","total":"520"},"value":0.938461,"count":520,"window_start":1778378100000,"window_end":1778378400000,"emit_time":1778378401400}
{"metric_id":"m-004","metric_name":"merchant_realtime_amount_5m","dimensions":{"merchant_id":"merchant-risk-spike"},"value":95200.00,"count":0,"window_start":1778378100000,"window_end":1778378400000,"emit_time":1778378401500}
{"metric_id":"m-005","metric_name":"risk_alert_count_1m","dimensions":{},"value":18.0,"count":18,"window_start":1778378400000,"window_end":1778378460000,"emit_time":1778378461600}
```

可用于 Dashboard 的核心指标：

- 近 1 分钟交易笔数：`transaction_count_1m`
- 近 5 分钟交易金额：`transaction_amount_5m`
- 各支付渠道成功率：`channel_success_rate_5m`
- 各商户实时收款金额：`merchant_realtime_amount_5m`
- 高风险告警数量：`high_risk_alert_count_1m`
- 风险告警数量：`risk_alert_count_1m`
