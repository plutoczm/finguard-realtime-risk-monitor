package com.finguard.utils;

import java.time.Instant;

public final class TimeUtils {
    private TimeUtils() {
    }

    public static long parseIsoMillis(String value) {
        if (value == null || value.isBlank()) {
            return 0L;
        }
        return Instant.parse(value).toEpochMilli();
    }
}
