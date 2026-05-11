package com.finguard;

import com.finguard.model.RiskAlert;
import com.finguard.model.TransactionEvent;
import com.finguard.utils.RiskAlertFactory;
import com.finguard.utils.RuleConstants;
import org.junit.jupiter.api.Test;

import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;

class RiskAlertFactoryTest {
    @Test
    void eventAlertIdIsDeterministic() {
        TransactionEvent event = new TransactionEvent();
        event.setEventId("evt-test-001");
        event.setTransactionId("txn-test-001");
        event.setUserId("user-test");
        event.setDeviceId("device-test");
        event.setCardId("card-test");
        event.setMerchantId("merchant-test");
        event.setAmount(100.0);
        event.setEventTime("2026-05-10T02:00:00Z");

        RiskAlert first = RiskAlertFactory.fromEvent(
                RuleConstants.R006,
                RuleConstants.R006_NAME,
                RuleConstants.HIGH,
                RuleConstants.R006_REASON,
                event,
                Map.of("device_id", "device-test")
        );

        RiskAlert second = RiskAlertFactory.fromEvent(
                RuleConstants.R006,
                RuleConstants.R006_NAME,
                RuleConstants.HIGH,
                RuleConstants.R006_REASON,
                event,
                Map.of("device_id", "device-test")
        );

        assertEquals(first.getAlertId(), second.getAlertId());
        assertEquals(RuleConstants.R006, first.getRuleId());
    }
}
