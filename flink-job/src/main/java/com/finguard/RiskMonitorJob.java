package com.finguard;

import com.finguard.function.AmountAggregateFunction;
import com.finguard.function.BlackDeviceRuleFunction;
import com.finguard.function.ConsecutiveFailureFunction;
import com.finguard.function.CountAggregateFunction;
import com.finguard.function.DistinctUserWindowFunction;
import com.finguard.function.EventDeduplicateFunction;
import com.finguard.function.LateEventRouterFunction;
import com.finguard.function.MerchantAmountSpikeFunction;
import com.finguard.function.MerchantWindowAmountFunction;
import com.finguard.function.ParseTransactionProcessFunction;
import com.finguard.function.RealtimeMetricFunctions;
import com.finguard.function.UserAmountSpikeFunction;
import com.finguard.function.UserAmountWindowFunction;
import com.finguard.function.UserTxnCountWindowFunction;
import com.finguard.model.MerchantWindowAmount;
import com.finguard.model.RealtimeMetric;
import com.finguard.model.RiskAlert;
import com.finguard.model.TransactionEvent;
import com.finguard.sink.FileSinkFactory;
import com.finguard.utils.JsonUtils;
import com.finguard.utils.RuleConstants;
import org.apache.flink.api.common.eventtime.WatermarkStrategy;
import org.apache.flink.api.common.restartstrategy.RestartStrategies;
import org.apache.flink.api.common.serialization.SimpleStringSchema;
import org.apache.flink.api.java.utils.ParameterTool;
import org.apache.flink.connector.kafka.source.KafkaSource;
import org.apache.flink.connector.kafka.source.enumerator.initializer.OffsetsInitializer;
import org.apache.flink.streaming.api.CheckpointingMode;
import org.apache.flink.streaming.api.datastream.DataStream;
import org.apache.flink.streaming.api.datastream.SingleOutputStreamOperator;
import org.apache.flink.streaming.api.environment.CheckpointConfig;
import org.apache.flink.streaming.api.environment.StreamExecutionEnvironment;
import org.apache.flink.streaming.api.windowing.assigners.SlidingEventTimeWindows;
import org.apache.flink.streaming.api.windowing.assigners.TumblingEventTimeWindows;
import org.apache.flink.streaming.api.windowing.time.Time;
import org.apache.flink.util.OutputTag;

import java.time.Duration;

public class RiskMonitorJob {
    private static final String DEFAULT_BOOTSTRAP = "localhost:9092";
    private static final String DEFAULT_TOPIC = "payment_transaction_events";

    public static void main(String[] args) throws Exception {
        ParameterTool params = ParameterTool.fromArgs(args);
        String bootstrapServers = params.get("bootstrap-servers", DEFAULT_BOOTSTRAP);
        String transactionTopic = params.get("transaction-topic", DEFAULT_TOPIC);
        String metricOutput = params.get("metric-output", "file:///opt/finguard/data/output/realtime_metrics");
        String alertOutput = params.get("alert-output", "file:///opt/finguard/data/alerts/risk_alerts");
        String lateOutput = params.get("late-output", "file:///opt/finguard/data/late_events");
        String deadLetterOutput = params.get("dead-letter-output", "file:///opt/finguard/data/output/dead_letter");
        String checkpointDir = params.get("checkpoint-dir", "file:///opt/finguard/data/checkpoints");
        int parallelism = params.getInt("parallelism", 2);
        int watermarkSeconds = params.getInt("watermark-seconds", 60);

        StreamExecutionEnvironment env = StreamExecutionEnvironment.getExecutionEnvironment();
        env.setParallelism(parallelism);
        env.enableCheckpointing(60_000L, CheckpointingMode.EXACTLY_ONCE);
        env.getCheckpointConfig().setCheckpointStorage(checkpointDir);
        env.getCheckpointConfig().setMinPauseBetweenCheckpoints(20_000L);
        env.getCheckpointConfig().setCheckpointTimeout(10 * 60_000L);
        env.getCheckpointConfig().setMaxConcurrentCheckpoints(1);
        env.getCheckpointConfig().setExternalizedCheckpointCleanup(CheckpointConfig.ExternalizedCheckpointCleanup.RETAIN_ON_CANCELLATION);
        env.setRestartStrategy(RestartStrategies.fixedDelayRestart(3, org.apache.flink.api.common.time.Time.seconds(10)));
        env.getConfig().setAutoWatermarkInterval(1_000L);

        OutputTag<String> deadLetterTag = new OutputTag<String>("dead-letter-events") {
        };
        OutputTag<TransactionEvent> lateEventTag = new OutputTag<TransactionEvent>("late-events") {
        };

        KafkaSource<String> source = KafkaSource.<String>builder()
                .setBootstrapServers(bootstrapServers)
                .setTopics(transactionTopic)
                .setGroupId("finguard-risk-monitor")
                .setStartingOffsets(OffsetsInitializer.latest())
                .setValueOnlyDeserializer(new SimpleStringSchema())
                .build();

        DataStream<String> rawEvents = env.fromSource(source, WatermarkStrategy.noWatermarks(), "Kafka transaction source");

        SingleOutputStreamOperator<TransactionEvent> parsedEvents = rawEvents
                .process(new ParseTransactionProcessFunction(deadLetterTag))
                .name("parse-and-validate-transaction");

        WatermarkStrategy<TransactionEvent> watermarkStrategy = WatermarkStrategy
                .<TransactionEvent>forBoundedOutOfOrderness(Duration.ofSeconds(watermarkSeconds))
                .withTimestampAssigner((event, timestamp) -> event.getEventTimeMillis())
                .withIdleness(Duration.ofMinutes(1));

        SingleOutputStreamOperator<TransactionEvent> deduplicatedEvents = parsedEvents
                .assignTimestampsAndWatermarks(watermarkStrategy)
                .keyBy(TransactionEvent::getEventId)
                .process(new EventDeduplicateFunction())
                .uid("event-id-deduplicate")
                .name("event-id-deduplicate");

        SingleOutputStreamOperator<TransactionEvent> onTimeEvents = deduplicatedEvents
                .process(new LateEventRouterFunction(lateEventTag))
                .uid("late-event-router")
                .name("late-event-router");

        DataStream<TransactionEvent> successfulPayments = onTimeEvents
                .filter(event -> "SUCCESS".equalsIgnoreCase(event.getTransactionStatus()))
                .name("success-transactions");

        DataStream<RiskAlert> rule001 = onTimeEvents
                .keyBy(TransactionEvent::getUserId)
                .window(TumblingEventTimeWindows.of(Time.minutes(1)))
                .aggregate(new CountAggregateFunction<>(), new UserTxnCountWindowFunction(10))
                .uid("rule-r001-user-frequency")
                .name("R001 user frequency");

        DataStream<RiskAlert> rule002 = successfulPayments
                .keyBy(TransactionEvent::getUserId)
                .window(SlidingEventTimeWindows.of(Time.minutes(5), Time.minutes(1)))
                .aggregate(new AmountAggregateFunction(), new UserAmountWindowFunction(20_000.0))
                .uid("rule-r002-user-amount")
                .name("R002 user amount");

        DataStream<RiskAlert> rule003 = onTimeEvents
                .keyBy(TransactionEvent::getDeviceId)
                .window(SlidingEventTimeWindows.of(Time.minutes(10), Time.minutes(1)))
                .process(new DistinctUserWindowFunction(
                        RuleConstants.R003,
                        RuleConstants.R003_NAME,
                        RuleConstants.HIGH,
                        RuleConstants.R003_REASON,
                        "device_id",
                        5
                ))
                .uid("rule-r003-device-users")
                .name("R003 device users");

        DataStream<RiskAlert> rule004 = onTimeEvents
                .keyBy(TransactionEvent::getCardId)
                .window(SlidingEventTimeWindows.of(Time.minutes(10), Time.minutes(1)))
                .process(new DistinctUserWindowFunction(
                        RuleConstants.R004,
                        RuleConstants.R004_NAME,
                        RuleConstants.HIGH,
                        RuleConstants.R004_REASON,
                        "card_id",
                        3
                ))
                .uid("rule-r004-card-users")
                .name("R004 card users");

        DataStream<RiskAlert> rule005 = onTimeEvents
                .keyBy(TransactionEvent::getUserId)
                .process(new ConsecutiveFailureFunction(5))
                .uid("rule-r005-consecutive-failure")
                .name("R005 consecutive failure");

        DataStream<RiskAlert> rule006 = onTimeEvents
                .process(new BlackDeviceRuleFunction())
                .uid("rule-r006-black-device")
                .name("R006 black device");

        DataStream<RiskAlert> rule007 = successfulPayments
                .keyBy(TransactionEvent::getUserId)
                .process(new UserAmountSpikeFunction(5, 5.0))
                .uid("rule-r007-user-amount-spike")
                .name("R007 user amount spike");

        DataStream<MerchantWindowAmount> merchantWindowAmounts = successfulPayments
                .keyBy(TransactionEvent::getMerchantId)
                .window(SlidingEventTimeWindows.of(Time.minutes(5), Time.minutes(1)))
                .aggregate(new AmountAggregateFunction(), new MerchantWindowAmountFunction())
                .uid("merchant-window-amount")
                .name("merchant 5m window amount");

        DataStream<RiskAlert> rule008 = merchantWindowAmounts
                .keyBy(MerchantWindowAmount::getMerchantId)
                .process(new MerchantAmountSpikeFunction(3, 3.0))
                .uid("rule-r008-merchant-spike")
                .name("R008 merchant spike");

        DataStream<RiskAlert> alerts = rule001.union(rule002, rule003, rule004, rule005, rule006, rule007, rule008);

        DataStream<RealtimeMetric> txnCountMetric = onTimeEvents
                .windowAll(TumblingEventTimeWindows.of(Time.minutes(1)))
                .aggregate(new CountAggregateFunction<>(), new RealtimeMetricFunctions.TransactionCountWindow())
                .name("metric transaction count 1m");

        DataStream<RealtimeMetric> amountMetric = successfulPayments
                .windowAll(SlidingEventTimeWindows.of(Time.minutes(5), Time.minutes(1)))
                .aggregate(new AmountAggregateFunction(), new RealtimeMetricFunctions.TransactionAmountWindow())
                .name("metric transaction amount 5m");

        DataStream<RealtimeMetric> channelSuccessRate = onTimeEvents
                .keyBy(TransactionEvent::getChannel)
                .window(SlidingEventTimeWindows.of(Time.minutes(5), Time.minutes(1)))
                .aggregate(new RealtimeMetricFunctions.ChannelSuccessRateAggregate(), new RealtimeMetricFunctions.ChannelSuccessRateWindow())
                .name("metric channel success rate");

        DataStream<RealtimeMetric> merchantAmountMetric = successfulPayments
                .keyBy(TransactionEvent::getMerchantId)
                .window(SlidingEventTimeWindows.of(Time.minutes(5), Time.minutes(1)))
                .aggregate(new AmountAggregateFunction(), new RealtimeMetricFunctions.MerchantAmountWindow())
                .name("metric merchant amount");

        DataStream<RealtimeMetric> alertCountMetric = alerts
                .windowAll(TumblingEventTimeWindows.of(Time.minutes(1)))
                .aggregate(new CountAggregateFunction<>(), new RealtimeMetricFunctions.AlertCountWindow())
                .name("metric alert count");

        DataStream<RealtimeMetric> highRiskAlertMetric = alerts
                .filter(RealtimeMetricFunctions::isHighRisk)
                .windowAll(TumblingEventTimeWindows.of(Time.minutes(1)))
                .aggregate(new CountAggregateFunction<>(), new RealtimeMetricFunctions.HighRiskAlertCountWindow())
                .name("metric high risk alert count");

        DataStream<RealtimeMetric> metrics = txnCountMetric
                .union(amountMetric, channelSuccessRate, merchantAmountMetric, alertCountMetric, highRiskAlertMetric);

        alerts
                .map(JsonUtils::toJson)
                .sinkTo(FileSinkFactory.jsonLineSink(alertOutput))
                .uid("file-sink-risk-alerts")
                .name("file sink risk alerts");

        metrics
                .map(JsonUtils::toJson)
                .sinkTo(FileSinkFactory.jsonLineSink(metricOutput))
                .uid("file-sink-realtime-metrics")
                .name("file sink realtime metrics");

        onTimeEvents.getSideOutput(lateEventTag)
                .map(JsonUtils::toJson)
                .sinkTo(FileSinkFactory.jsonLineSink(lateOutput))
                .uid("file-sink-late-events")
                .name("file sink late events");

        parsedEvents.getSideOutput(deadLetterTag)
                .sinkTo(FileSinkFactory.jsonLineSink(deadLetterOutput))
                .uid("file-sink-dead-letter")
                .name("file sink dead letter");

        env.execute("FinGuard Realtime Risk Monitor");
    }
}
