package com.finguard.utils;

public final class RuleConstants {
    public static final String MEDIUM = "MEDIUM";
    public static final String HIGH = "HIGH";

    public static final String R001 = "R001";
    public static final String R001_NAME = "用户短时高频交易";
    public static final String R001_REASON = "同一用户在1分钟窗口内交易次数超过10次";

    public static final String R002 = "R002";
    public static final String R002_NAME = "用户短时大额交易";
    public static final String R002_REASON = "同一用户在5分钟窗口内累计交易金额超过20000元";

    public static final String R003 = "R003";
    public static final String R003_NAME = "设备多用户关联";
    public static final String R003_REASON = "同一设备在10分钟内关联超过5个用户";

    public static final String R004 = "R004";
    public static final String R004_NAME = "银行卡多用户关联";
    public static final String R004_REASON = "同一银行卡在10分钟内关联超过3个用户";

    public static final String R005 = "R005";
    public static final String R005_NAME = "连续支付失败";
    public static final String R005_REASON = "同一用户连续支付失败次数达到5次";

    public static final String R006 = "R006";
    public static final String R006_NAME = "黑名单设备交易";
    public static final String R006_REASON = "当前交易设备命中黑名单设备";

    public static final String R007 = "R007";
    public static final String R007_NAME = "用户交易金额突增";
    public static final String R007_REASON = "当前交易金额超过用户历史平均交易金额5倍";

    public static final String R008 = "R008";
    public static final String R008_NAME = "商户收款突增";
    public static final String R008_REASON = "同一商户5分钟收款金额超过历史5分钟平均水平3倍";

    private RuleConstants() {
    }
}
