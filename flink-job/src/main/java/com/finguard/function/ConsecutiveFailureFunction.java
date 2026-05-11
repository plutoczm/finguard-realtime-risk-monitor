package com.finguard.function;

import com.finguard.model.RiskAlert;
import com.finguard.model.TransactionEvent;
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

public class ConsecutiveFailureFunction extends KeyedProcessFunction<String, TransactionEvent, RiskAlert> {
    private final int threshold;
    private transient ValueState<Integer> failureCountState;

    public ConsecutiveFailureFunction(int threshold) {
        this.threshold = threshold;
    }

    @Override
    public void open(Configuration parameters) {
        StateTtlConfig ttlConfig = StateTtlConfig
                .newBuilder(Time.hours(6))
                .setUpdateType(StateTtlConfig.UpdateType.OnCreateAndWrite)
                .cleanupFullSnapshot()
                .build();
        ValueStateDescriptor<Integer> descriptor = new ValueStateDescriptor<>("consecutive-failure-count", Integer.class);
        descriptor.enableTimeToLive(ttlConfig);
        failureCountState = getRuntimeContext().getState(descriptor);
    }

    @Override
    public void processElement(TransactionEvent event, Context ctx, Collector<RiskAlert> out) throws Exception {
        if ("FAILED".equalsIgnoreCase(event.getTransactionStatus())) {
            Integer current = failureCountState.value();
            int next = current == null ? 1 : current + 1;
            failureCountState.update(next);
            if (next >= threshold) {
                Map<String, String> evidence = new LinkedHashMap<>();
                evidence.put("user_id", event.getUserId());
                evidence.put("consecutive_failed_count", String.valueOf(next));
                evidence.put("threshold", String.valueOf(threshold));
                out.collect(RiskAlertFactory.fromEvent(
                        RuleConstants.R005,
                        RuleConstants.R005_NAME,
                        RuleConstants.MEDIUM,
                        RuleConstants.R005_REASON,
                        event,
                        evidence
                ));
            }
        } else {
            failureCountState.clear();
        }
    }
}
