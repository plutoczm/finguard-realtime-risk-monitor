package com.finguard.function;

import com.finguard.model.RiskAlert;
import com.finguard.model.TransactionEvent;
import com.finguard.model.UserAmountStats;
import com.finguard.utils.RiskAlertFactory;
import com.finguard.utils.RuleConstants;
import org.apache.flink.api.common.state.StateTtlConfig;
import org.apache.flink.api.common.state.ValueState;
import org.apache.flink.api.common.state.ValueStateDescriptor;
import org.apache.flink.api.common.time.Time;
import org.apache.flink.configuration.Configuration;
import org.apache.flink.streaming.api.functions.KeyedProcessFunction;
import org.apache.flink.util.Collector;

import java.util.LinkedHashMap;
import java.util.Map;

public class UserAmountSpikeFunction extends KeyedProcessFunction<String, TransactionEvent, RiskAlert> {
    private final int minSamples;
    private final double multiplier;
    private transient ValueState<UserAmountStats> statsState;

    public UserAmountSpikeFunction(int minSamples, double multiplier) {
        this.minSamples = minSamples;
        this.multiplier = multiplier;
    }

    @Override
    public void open(Configuration parameters) {
        StateTtlConfig ttlConfig = StateTtlConfig
                .newBuilder(Time.days(30))
                .setUpdateType(StateTtlConfig.UpdateType.OnCreateAndWrite)
                .cleanupFullSnapshot()
                .build();
        ValueStateDescriptor<UserAmountStats> descriptor = new ValueStateDescriptor<>("user-amount-stats", UserAmountStats.class);
        descriptor.enableTimeToLive(ttlConfig);
        statsState = getRuntimeContext().getState(descriptor);
    }

    @Override
    public void processElement(TransactionEvent event, Context ctx, Collector<RiskAlert> out) throws Exception {
        if (!"SUCCESS".equalsIgnoreCase(event.getTransactionStatus())) {
            return;
        }

        UserAmountStats stats = statsState.value();
        if (stats == null) {
            stats = new UserAmountStats();
        }

        double avg = stats.average();
        if (stats.getCount() >= minSamples && avg > 0 && event.getAmount() > avg * multiplier) {
            Map<String, String> evidence = new LinkedHashMap<>();
            evidence.put("user_id", event.getUserId());
            evidence.put("current_amount", String.format("%.2f", event.getAmount()));
            evidence.put("historical_avg_amount", String.format("%.2f", avg));
            evidence.put("history_count", String.valueOf(stats.getCount()));
            evidence.put("multiplier", String.format("%.1f", multiplier));
            out.collect(RiskAlertFactory.fromEvent(
                    RuleConstants.R007,
                    RuleConstants.R007_NAME,
                    RuleConstants.MEDIUM,
                    RuleConstants.R007_REASON,
                    event,
                    evidence
            ));
        }

        stats.add(event.getAmount());
        statsState.update(stats);
    }
}
