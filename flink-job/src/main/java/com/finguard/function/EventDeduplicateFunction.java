package com.finguard.function;

import com.finguard.model.TransactionEvent;
import org.apache.flink.api.common.state.StateTtlConfig;
import org.apache.flink.api.common.state.ValueState;
import org.apache.flink.api.common.state.ValueStateDescriptor;
import org.apache.flink.api.common.time.Time;
import org.apache.flink.configuration.Configuration;
import org.apache.flink.streaming.api.functions.KeyedProcessFunction;
import org.apache.flink.util.Collector;

public class EventDeduplicateFunction extends KeyedProcessFunction<String, TransactionEvent, TransactionEvent> {
    private transient ValueState<Boolean> seenState;

    @Override
    public void open(Configuration parameters) {
        StateTtlConfig ttlConfig = StateTtlConfig
                .newBuilder(Time.hours(24))
                .setUpdateType(StateTtlConfig.UpdateType.OnCreateAndWrite)
                .cleanupFullSnapshot()
                .build();
        ValueStateDescriptor<Boolean> descriptor = new ValueStateDescriptor<>("seen-event-id", Boolean.class);
        descriptor.enableTimeToLive(ttlConfig);
        seenState = getRuntimeContext().getState(descriptor);
    }

    @Override
    public void processElement(TransactionEvent value, Context ctx, Collector<TransactionEvent> out) throws Exception {
        Boolean seen = seenState.value();
        if (seen != null && seen) {
            return;
        }
        seenState.update(true);
        out.collect(value);
    }
}
