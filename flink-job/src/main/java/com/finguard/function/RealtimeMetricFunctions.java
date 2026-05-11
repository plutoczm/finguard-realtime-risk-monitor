package com.finguard.function;

import com.finguard.model.ChannelStats;
import com.finguard.model.RealtimeMetric;
import com.finguard.model.RiskAlert;
import com.finguard.model.TransactionEvent;
import org.apache.flink.api.common.functions.AggregateFunction;
import org.apache.flink.streaming.api.functions.windowing.ProcessAllWindowFunction;
import org.apache.flink.streaming.api.functions.windowing.ProcessWindowFunction;
import org.apache.flink.streaming.api.windowing.windows.TimeWindow;
import org.apache.flink.util.Collector;

public final class RealtimeMetricFunctions {
    private RealtimeMetricFunctions() {
    }

    public static class TransactionCountWindow extends ProcessAllWindowFunction<Long, RealtimeMetric, TimeWindow> {
        @Override
        public void process(Context context, Iterable<Long> elements, Collector<RealtimeMetric> out) {
            long count = elements.iterator().next();
            out.collect(RealtimeMetric.of("transaction_count_1m", count, count, context.window().getStart(), context.window().getEnd()));
        }
    }

    public static class TransactionAmountWindow extends ProcessAllWindowFunction<Double, RealtimeMetric, TimeWindow> {
        @Override
        public void process(Context context, Iterable<Double> elements, Collector<RealtimeMetric> out) {
            double amount = elements.iterator().next();
            out.collect(RealtimeMetric.of("transaction_amount_5m", amount, 0L, context.window().getStart(), context.window().getEnd()));
        }
    }

    public static class MerchantAmountWindow extends ProcessWindowFunction<Double, RealtimeMetric, String, TimeWindow> {
        @Override
        public void process(String merchantId, Context context, Iterable<Double> elements, Collector<RealtimeMetric> out) {
            double amount = elements.iterator().next();
            RealtimeMetric metric = RealtimeMetric.of("merchant_realtime_amount_5m", amount, 0L, context.window().getStart(), context.window().getEnd());
            metric.getDimensions().put("merchant_id", merchantId);
            out.collect(metric);
        }
    }

    public static class AlertCountWindow extends ProcessAllWindowFunction<Long, RealtimeMetric, TimeWindow> {
        @Override
        public void process(Context context, Iterable<Long> elements, Collector<RealtimeMetric> out) {
            long count = elements.iterator().next();
            out.collect(RealtimeMetric.of("risk_alert_count_1m", count, count, context.window().getStart(), context.window().getEnd()));
        }
    }

    public static class HighRiskAlertCountWindow extends ProcessAllWindowFunction<Long, RealtimeMetric, TimeWindow> {
        @Override
        public void process(Context context, Iterable<Long> elements, Collector<RealtimeMetric> out) {
            long count = elements.iterator().next();
            out.collect(RealtimeMetric.of("high_risk_alert_count_1m", count, count, context.window().getStart(), context.window().getEnd()));
        }
    }

    public static class ChannelSuccessRateAggregate implements AggregateFunction<TransactionEvent, ChannelStats, ChannelStats> {
        @Override
        public ChannelStats createAccumulator() {
            return new ChannelStats();
        }

        @Override
        public ChannelStats add(TransactionEvent value, ChannelStats accumulator) {
            accumulator.add("SUCCESS".equalsIgnoreCase(value.getTransactionStatus()));
            return accumulator;
        }

        @Override
        public ChannelStats getResult(ChannelStats accumulator) {
            return accumulator;
        }

        @Override
        public ChannelStats merge(ChannelStats a, ChannelStats b) {
            ChannelStats merged = new ChannelStats();
            merged.setTotal(a.getTotal() + b.getTotal());
            merged.setSuccess(a.getSuccess() + b.getSuccess());
            return merged;
        }
    }

    public static class ChannelSuccessRateWindow extends ProcessWindowFunction<ChannelStats, RealtimeMetric, String, TimeWindow> {
        @Override
        public void process(String channel, Context context, Iterable<ChannelStats> elements, Collector<RealtimeMetric> out) {
            ChannelStats stats = elements.iterator().next();
            RealtimeMetric metric = RealtimeMetric.of(
                    "channel_success_rate_5m",
                    stats.successRate(),
                    stats.getTotal(),
                    context.window().getStart(),
                    context.window().getEnd()
            );
            metric.getDimensions().put("channel", channel);
            metric.getDimensions().put("success", String.valueOf(stats.getSuccess()));
            metric.getDimensions().put("total", String.valueOf(stats.getTotal()));
            out.collect(metric);
        }
    }

    public static boolean isHighRisk(RiskAlert alert) {
        return "HIGH".equalsIgnoreCase(alert.getRiskLevel());
    }
}
