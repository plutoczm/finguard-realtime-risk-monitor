package com.finguard.model;

import java.io.Serializable;

public class UserAmountStats implements Serializable {
    private long count;
    private double totalAmount;

    public UserAmountStats() {
    }

    public UserAmountStats(long count, double totalAmount) {
        this.count = count;
        this.totalAmount = totalAmount;
    }

    public double average() {
        return count == 0 ? 0.0 : totalAmount / count;
    }

    public void add(double amount) {
        count++;
        totalAmount += amount;
    }

    public long getCount() {
        return count;
    }

    public void setCount(long count) {
        this.count = count;
    }

    public double getTotalAmount() {
        return totalAmount;
    }

    public void setTotalAmount(double totalAmount) {
        this.totalAmount = totalAmount;
    }
}
