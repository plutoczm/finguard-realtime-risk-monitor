package com.finguard.function;

import com.finguard.model.TransactionEvent;
import org.apache.flink.api.common.functions.AggregateFunction;

public class AmountAggregateFunction implements AggregateFunction<TransactionEvent, Double, Double> {
    @Override
    public Double createAccumulator() {
        return 0.0;
    }

    @Override
    public Double add(TransactionEvent value, Double accumulator) {
        return accumulator + value.getAmount();
    }

    @Override
    public Double getResult(Double accumulator) {
        return accumulator;
    }

    @Override
    public Double merge(Double a, Double b) {
        return a + b;
    }
}
