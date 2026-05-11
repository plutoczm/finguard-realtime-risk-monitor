package com.finguard.function;

import com.finguard.model.TransactionEvent;
import com.finguard.utils.JsonUtils;
import org.apache.flink.streaming.api.functions.ProcessFunction;
import org.apache.flink.util.Collector;
import org.apache.flink.util.OutputTag;

public class ParseTransactionProcessFunction extends ProcessFunction<String, TransactionEvent> {
    private final OutputTag<String> deadLetterTag;

    public ParseTransactionProcessFunction(OutputTag<String> deadLetterTag) {
        this.deadLetterTag = deadLetterTag;
    }

    @Override
    public void processElement(String value, Context ctx, Collector<TransactionEvent> out) {
        try {
            TransactionEvent event = JsonUtils.parseTransaction(value);
            validate(event);
            out.collect(event);
        } catch (Exception e) {
            ctx.output(deadLetterTag, value);
        }
    }

    private void validate(TransactionEvent event) {
        if (isBlank(event.getEventId())
                || isBlank(event.getUserId())
                || isBlank(event.getTransactionId())
                || isBlank(event.getDeviceId())
                || isBlank(event.getCardId())
                || isBlank(event.getMerchantId())
                || isBlank(event.getEventTime())) {
            throw new IllegalArgumentException("Missing required transaction field");
        }
        if (isBlank(event.getChannel()) || isBlank(event.getTransactionStatus()) || isBlank(event.getTransactionType())) {
            throw new IllegalArgumentException("Missing required transaction enum field");
        }
        if (event.getAmount() < 0) {
            throw new IllegalArgumentException("Negative amount is not allowed");
        }
    }

    private boolean isBlank(String value) {
        return value == null || value.isBlank();
    }
}
