package com.finguard.function;

import com.finguard.model.RiskAlert;
import com.finguard.model.TransactionEvent;
import com.finguard.utils.RiskAlertFactory;
import com.finguard.utils.RuleConstants;
import org.apache.flink.streaming.api.functions.ProcessFunction;
import org.apache.flink.util.Collector;

import java.util.LinkedHashMap;
import java.util.Map;

public class BlackDeviceRuleFunction extends ProcessFunction<TransactionEvent, RiskAlert> {
    @Override
    public void processElement(TransactionEvent event, Context ctx, Collector<RiskAlert> out) {
        if (event.isBlackDevice()) {
            Map<String, String> evidence = new LinkedHashMap<>();
            evidence.put("device_id", event.getDeviceId());
            evidence.put("is_black_device", "true");
            evidence.put("source", "event_flag");
            out.collect(RiskAlertFactory.fromEvent(
                    RuleConstants.R006,
                    RuleConstants.R006_NAME,
                    RuleConstants.HIGH,
                    RuleConstants.R006_REASON,
                    event,
                    evidence
            ));
        }
    }
}
