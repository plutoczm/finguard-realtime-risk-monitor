package com.finguard.function;

import com.finguard.model.RiskAlert;
import com.finguard.utils.RiskAlertFactory;
import com.finguard.utils.RuleConstants;
import org.apache.flink.streaming.api.functions.windowing.ProcessWindowFunction;
import org.apache.flink.streaming.api.windowing.windows.TimeWindow;
import org.apache.flink.util.Collector;

import java.util.LinkedHashMap;
import java.util.Map;

public class UserAmountWindowFunction extends ProcessWindowFunction<Double, RiskAlert, String, TimeWindow> {
    private final double threshold;

    public UserAmountWindowFunction(double threshold) {
        this.threshold = threshold;
    }

    @Override
    public void process(String userId, Context context, Iterable<Double> elements, Collector<RiskAlert> out) {
        double amount = elements.iterator().next();
        if (amount > threshold) {
            Map<String, String> evidence = new LinkedHashMap<>();
            evidence.put("user_id", userId);
            evidence.put("total_amount", String.format("%.2f", amount));
            evidence.put("threshold", String.format("%.2f", threshold));
            evidence.put("window", "5 minute sliding event-time window");
            out.collect(RiskAlertFactory.fromWindow(
                    RuleConstants.R002,
                    RuleConstants.R002_NAME,
                    RuleConstants.HIGH,
                    RuleConstants.R002_REASON,
                    "user_id",
                    userId,
                    context.window().getStart(),
                    context.window().getEnd(),
                    evidence
            ));
        }
    }
}
