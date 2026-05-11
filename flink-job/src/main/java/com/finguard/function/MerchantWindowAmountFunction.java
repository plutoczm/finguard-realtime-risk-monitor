package com.finguard.function;

import com.finguard.model.MerchantWindowAmount;
import org.apache.flink.streaming.api.functions.windowing.ProcessWindowFunction;
import org.apache.flink.streaming.api.windowing.windows.TimeWindow;
import org.apache.flink.util.Collector;

public class MerchantWindowAmountFunction extends ProcessWindowFunction<Double, MerchantWindowAmount, String, TimeWindow> {
    @Override
    public void process(String merchantId, Context context, Iterable<Double> elements, Collector<MerchantWindowAmount> out) {
        double amount = elements.iterator().next();
        out.collect(new MerchantWindowAmount(
                merchantId,
                amount,
                context.window().getStart(),
                context.window().getEnd()
        ));
    }
}
