package com.finguard.model;

import java.io.Serializable;

public class MerchantAmountStats implements Serializable {
    private long windowCount;
    private double totalWindowAmount;

    public MerchantAmountStats() {
    }

    public double averageWindowAmount() {
        return windowCount == 0 ? 0.0 : totalWindowAmount / windowCount;
    }

    public void addWindow(double amount) {
        windowCount++;
        totalWindowAmount += amount;
    }

    public long getWindowCount() {
        return windowCount;
    }

    public void setWindowCount(long windowCount) {
        this.windowCount = windowCount;
    }

    public double getTotalWindowAmount() {
        return totalWindowAmount;
    }

    public void setTotalWindowAmount(double totalWindowAmount) {
        this.totalWindowAmount = totalWindowAmount;
    }
}
