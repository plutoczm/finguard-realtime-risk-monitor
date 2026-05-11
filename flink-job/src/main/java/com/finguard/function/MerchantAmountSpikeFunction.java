package com.finguard.function;

import com.finguard.model.MerchantAmountStats;
import com.finguard.model.MerchantWindowAmount;
import com.finguard.model.RiskAlert;
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

public class MerchantAmountSpikeFunction extends KeyedProcessFunction<String, MerchantWindowAmount, RiskAlert> {
    private final int minWindows;
    private final double multiplier;
    private transient ValueState<MerchantAmountStats> statsState;

    public MerchantAmountSpikeFunction(int minWindows, double multiplier) {
        this.minWindows = minWindows;
        this.multiplier = multiplier;
    }

    @Override
    public void open(Configuration parameters) {
        StateTtlConfig ttlConfig = StateTtlConfig
                .newBuilder(Time.days(14))
                .setUpdateType(StateTtlConfig.UpdateType.OnCreateAndWrite)
                .cleanupFullSnapshot()
                .build();
        ValueStateDescriptor<MerchantAmountStats> descriptor = new ValueStateDescriptor<>("merchant-window-amount-stats", MerchantAmountStats.class);
        descriptor.enableTimeToLive(ttlConfig);
        statsState = getRuntimeContext().getState(descriptor);
    }

    @Override
    public void processElement(MerchantWindowAmount value, Context ctx, Collector<RiskAlert> out) throws Exception {
        MerchantAmountStats stats = statsState.value();
        if (stats == null) {
            stats = new MerchantAmountStats();
        }

        double avg = stats.averageWindowAmount();
        if (stats.getWindowCount() >= minWindows && avg > 0 && value.getAmount() > avg * multiplier) {
            Map<String, String> evidence = new LinkedHashMap<>();
            evidence.put("merchant_id", value.getMerchantId());
            evidence.put("current_window_amount", String.format("%.2f", value.getAmount()));
            evidence.put("historical_avg_window_amount", String.format("%.2f", avg));
            evidence.put("history_window_count", String.valueOf(stats.getWindowCount()));
            evidence.put("multiplier", String.format("%.1f", multiplier));
            out.collect(RiskAlertFactory.fromWindow(
                    RuleConstants.R008,
                    RuleConstants.R008_NAME,
                    RuleConstants.HIGH,
                    RuleConstants.R008_REASON,
                    "merchant_id",
                    value.getMerchantId(),
                    value.getWindowStart(),
                    value.getWindowEnd(),
                    evidence
            ));
        }

        stats.addWindow(value.getAmount());
        statsState.update(stats);
    }
}
