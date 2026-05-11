package com.finguard.function;

import com.finguard.model.RiskAlert;
import com.finguard.model.TransactionEvent;
import com.finguard.utils.RiskAlertFactory;
import org.apache.flink.streaming.api.functions.windowing.ProcessWindowFunction;
import org.apache.flink.streaming.api.windowing.windows.TimeWindow;
import org.apache.flink.util.Collector;

import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;

public class DistinctUserWindowFunction extends ProcessWindowFunction<TransactionEvent, RiskAlert, String, TimeWindow> {
    private final String ruleId;
    private final String ruleName;
    private final String riskLevel;
    private final String reason;
    private final String keyName;
    private final int threshold;

    public DistinctUserWindowFunction(
            String ruleId,
            String ruleName,
            String riskLevel,
            String reason,
            String keyName,
            int threshold
    ) {
        this.ruleId = ruleId;
        this.ruleName = ruleName;
        this.riskLevel = riskLevel;
        this.reason = reason;
        this.keyName = keyName;
        this.threshold = threshold;
    }

    @Override
    public void process(String key, Context context, Iterable<TransactionEvent> elements, Collector<RiskAlert> out) {
        Set<String> users = new LinkedHashSet<>();
        for (TransactionEvent event : elements) {
            users.add(event.getUserId());
        }
        if (users.size() > threshold) {
            Map<String, String> evidence = new LinkedHashMap<>();
            evidence.put(keyName, key);
            evidence.put("distinct_user_count", String.valueOf(users.size()));
            evidence.put("threshold", String.valueOf(threshold));
            evidence.put("sample_user_ids", users.stream().limit(8).collect(Collectors.joining(",")));
            evidence.put("window", "10 minute sliding event-time window");
            out.collect(RiskAlertFactory.fromWindow(
                    ruleId,
                    ruleName,
                    riskLevel,
                    reason,
                    keyName,
                    key,
                    context.window().getStart(),
                    context.window().getEnd(),
                    evidence
            ));
        }
    }
}
