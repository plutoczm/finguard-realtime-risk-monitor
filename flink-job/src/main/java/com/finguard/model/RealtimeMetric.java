package com.finguard.model;

import com.fasterxml.jackson.databind.PropertyNamingStrategies;
import com.fasterxml.jackson.databind.annotation.JsonNaming;

import java.io.Serializable;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.UUID;

@JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
public class RealtimeMetric implements Serializable {
    private String metricId = UUID.randomUUID().toString();
    private String metricName;
    private Map<String, String> dimensions = new LinkedHashMap<>();
    private double value;
    private long count;
    private long windowStart;
    private long windowEnd;
    private long emitTime;

    public RealtimeMetric() {
    }

    public static RealtimeMetric of(String name, double value, long count, long windowStart, long windowEnd) {
        RealtimeMetric metric = new RealtimeMetric();
        metric.setMetricName(name);
        metric.setValue(value);
        metric.setCount(count);
        metric.setWindowStart(windowStart);
        metric.setWindowEnd(windowEnd);
        metric.setEmitTime(System.currentTimeMillis());
        return metric;
    }

    public String getMetricId() {
        return metricId;
    }

    public void setMetricId(String metricId) {
        this.metricId = metricId;
    }

    public String getMetricName() {
        return metricName;
    }

    public void setMetricName(String metricName) {
        this.metricName = metricName;
    }

    public Map<String, String> getDimensions() {
        return dimensions;
    }

    public void setDimensions(Map<String, String> dimensions) {
        this.dimensions = dimensions;
    }

    public double getValue() {
        return value;
    }

    public void setValue(double value) {
        this.value = value;
    }

    public long getCount() {
        return count;
    }

    public void setCount(long count) {
        this.count = count;
    }

    public long getWindowStart() {
        return windowStart;
    }

    public void setWindowStart(long windowStart) {
        this.windowStart = windowStart;
    }

    public long getWindowEnd() {
        return windowEnd;
    }

    public void setWindowEnd(long windowEnd) {
        this.windowEnd = windowEnd;
    }

    public long getEmitTime() {
        return emitTime;
    }

    public void setEmitTime(long emitTime) {
        this.emitTime = emitTime;
    }
}
