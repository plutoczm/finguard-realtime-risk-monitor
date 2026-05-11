package com.finguard.model;

import java.io.Serializable;

public class ChannelStats implements Serializable {
    private long total;
    private long success;

    public ChannelStats() {
    }

    public void add(boolean isSuccess) {
        total++;
        if (isSuccess) {
            success++;
        }
    }

    public double successRate() {
        return total == 0 ? 0.0 : (double) success / total;
    }

    public long getTotal() {
        return total;
    }

    public void setTotal(long total) {
        this.total = total;
    }

    public long getSuccess() {
        return success;
    }

    public void setSuccess(long success) {
        this.success = success;
    }
}
