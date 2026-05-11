package com.finguard.utils;

import com.finguard.model.RiskAlert;
import com.finguard.model.TransactionEvent;

import java.nio.charset.StandardCharsets;
import java.util.Map;
import java.util.UUID;

public final class RiskAlertFactory {
    private RiskAlertFactory() {
    }

    public static RiskAlert fromEvent(
            String ruleId,
            String ruleName,
            String riskLevel,
            String reason,
            TransactionEvent event,
            Map<String, String> evidence
    ) {
        RiskAlert alert = new RiskAlert();
        alert.setAlertId(stableId(ruleId, event.getEventId()));
        alert.setRuleId(ruleId);
        alert.setRuleName(ruleName);
        alert.setRiskLevel(riskLevel);
        alert.setReason(reason);
        alert.setEventId(event.getEventId());
        alert.setTransactionId(event.getTransactionId());
        alert.setUserId(event.getUserId());
        alert.setAccountId(event.getAccountId());
        alert.setCardId(event.getCardId());
        alert.setMerchantId(event.getMerchantId());
        alert.setDeviceId(event.getDeviceId());
        alert.setAmount(event.getAmount());
        alert.setEventTime(event.getEventTime());
        alert.setAlertTime(System.currentTimeMillis());
        alert.setEvidence(evidence);
        return alert;
    }

    public static RiskAlert fromWindow(
            String ruleId,
            String ruleName,
            String riskLevel,
            String reason,
            String keyName,
            String keyValue,
            long windowStart,
            long windowEnd,
            Map<String, String> evidence
    ) {
        RiskAlert alert = new RiskAlert();
        alert.setAlertId(stableId(ruleId, keyName, keyValue, String.valueOf(windowStart), String.valueOf(windowEnd)));
        alert.setRuleId(ruleId);
        alert.setRuleName(ruleName);
        alert.setRiskLevel(riskLevel);
        alert.setReason(reason);
        alert.setWindowStart(windowStart);
        alert.setWindowEnd(windowEnd);
        alert.setAlertTime(System.currentTimeMillis());
        alert.setEvidence(evidence);
        if ("user_id".equals(keyName)) {
            alert.setUserId(keyValue);
        } else if ("device_id".equals(keyName)) {
            alert.setDeviceId(keyValue);
        } else if ("card_id".equals(keyName)) {
            alert.setCardId(keyValue);
        } else if ("merchant_id".equals(keyName)) {
            alert.setMerchantId(keyValue);
        }
        return alert;
    }

    public static String stableId(String... parts) {
        String joined = String.join("|", parts);
        return UUID.nameUUIDFromBytes(joined.getBytes(StandardCharsets.UTF_8)).toString();
    }
}
