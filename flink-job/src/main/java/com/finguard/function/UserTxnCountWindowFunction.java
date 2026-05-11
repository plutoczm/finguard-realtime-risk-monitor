package com.finguard.function;

import com.finguard.model.RiskAlert;
import com.finguard.utils.RiskAlertFactory;
import com.finguard.utils.RuleConstants;
import org.apache.flink.streaming.api.functions.windowing.ProcessWindowFunction;
import org.apache.flink.streaming.api.windowing.windows.TimeWindow;
import org.apache.flink.util.Collector;

import java.util.LinkedHashMap;
import java.util.Map;

public class UserTxnCountWindowFunction extends ProcessWindowFunction<Long, RiskAlert, String, TimeWindow> {
    private final long threshold;

    public UserTxnCountWindowFunction(long threshold) {
        this.threshold = threshold;
    }

    @Override
    public void process(String userId, Context context, Iterable<Long> elements, Collector<RiskAlert> out) {
        long count = elements.iterator().next();
        if (count > threshold) {
            Map<String, String> evidence = new LinkedHashMap<>();
            evidence.put("user_id", userId);
            evidence.put("transaction_count", String.valueOf(count));
            evidence.put("threshold", String.valueOf(threshold));
            evidence.put("window", "1 minute tumbling event-time window");
            out.collect(RiskAlertFactory.fromWindow(
                    RuleConstants.R001,
                    RuleConstants.R001_NAME,
                    RuleConstants.MEDIUM,
                    RuleConstants.R001_REASON,
                    "user_id",
                    userId,
                    context.window().getStart(),
                    context.window().getEnd(),
                    evidence
            ));
        }
    }
}
