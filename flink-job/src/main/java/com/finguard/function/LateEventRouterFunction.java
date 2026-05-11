package com.finguard.function;

import com.finguard.model.TransactionEvent;
import org.apache.flink.streaming.api.functions.ProcessFunction;
import org.apache.flink.util.Collector;
import org.apache.flink.util.OutputTag;

public class LateEventRouterFunction extends ProcessFunction<TransactionEvent, TransactionEvent> {
    private final OutputTag<TransactionEvent> lateEventTag;

    public LateEventRouterFunction(OutputTag<TransactionEvent> lateEventTag) {
        this.lateEventTag = lateEventTag;
    }

    @Override
    public void processElement(TransactionEvent value, Context ctx, Collector<TransactionEvent> out) {
        long watermark = ctx.timerService().currentWatermark();
        if (watermark > Long.MIN_VALUE && value.getEventTimeMillis() < watermark) {
            ctx.output(lateEventTag, value);
        } else {
            out.collect(value);
        }
    }
}
