package com.finguard.model;

import java.io.Serializable;

public class MerchantWindowAmount implements Serializable {
    private String merchantId;
    private double amount;
    private long windowStart;
    private long windowEnd;

    public MerchantWindowAmount() {
    }

    public MerchantWindowAmount(String merchantId, double amount, long windowStart, long windowEnd) {
        this.merchantId = merchantId;
        this.amount = amount;
        this.windowStart = windowStart;
        this.windowEnd = windowEnd;
    }

    public String getMerchantId() {
        return merchantId;
    }

    public void setMerchantId(String merchantId) {
        this.merchantId = merchantId;
    }

    public double getAmount() {
        return amount;
    }

    public void setAmount(double amount) {
        this.amount = amount;
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
}
