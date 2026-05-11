package com.finguard.utils;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.PropertyNamingStrategies;
import com.finguard.model.TransactionEvent;

public final class JsonUtils {
    private static final ObjectMapper MAPPER = new ObjectMapper()
            .setPropertyNamingStrategy(PropertyNamingStrategies.SNAKE_CASE);

    private JsonUtils() {
    }

    public static TransactionEvent parseTransaction(String raw) throws JsonProcessingException {
        return MAPPER.readValue(raw, TransactionEvent.class);
    }

    public static String toJson(Object value) {
        try {
            return MAPPER.writeValueAsString(value);
        } catch (JsonProcessingException e) {
            throw new IllegalArgumentException("Failed to serialize object as JSON", e);
        }
    }
}
